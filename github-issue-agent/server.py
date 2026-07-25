import os
import sys
import time
import json
import asyncio
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from agent.state import AgentState
from agent.graph import app as graph_app
from agent.github_auth import authenticate_github_via_browser

api = FastAPI(title="GitHub Issue Agent API")

# Global active workflow state storage
current_workflow = {
    "status": "idle",  # "idle", "running", "waiting_approval", "completed", "failed"
    "state": None,
    "user_decision": None,  # dict with {"approved": bool, "feedback": str}
    "event_queue": []
}

class RunRequest(BaseModel):
    repo_url: str
    mode: str = "issue"  # "issue" or "smart"
    issue_number: Optional[int] = 0
    problem_description: Optional[str] = ""
    token: Optional[str] = ""

class ApprovalRequest(BaseModel):
    approved: bool
    feedback: Optional[str] = ""


# Custom web-adapted human approval node function wrapper
def web_human_approval_node(state: AgentState) -> Dict[str, Any]:
    """Web-adapted approval node: pauses workflow and waits for API approval decision."""
    current_workflow["status"] = "waiting_approval"
    current_workflow["state"] = state
    current_workflow["user_decision"] = None
    
    print("\n[WEB UI] Workflow paused. Waiting for user approval on web interface...")
    
    # Poll until user submits approval or rejection via web UI API
    while current_workflow["user_decision"] is None:
        time.sleep(0.5)

    decision = current_workflow["user_decision"]
    human_approved = decision.get("approved", False)
    feedback = decision.get("feedback", "").strip()
    retry_count = state.get("retry_count", 0)

    messages = list(state.get("messages", []))
    if not human_approved:
        retry_count += 1
        if feedback:
            from langchain_core.messages import HumanMessage
            messages.append(HumanMessage(content=f"Feedback: {feedback}"))

    current_workflow["status"] = "running"
    
    return {
        "human_approved": human_approved,
        "retry_count": retry_count,
        "messages": messages
    }


# Serve Static Assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    api.mount("/static", StaticFiles(directory=static_dir), name="static")


@api.get("/", response_class=HTMLResponse)
def read_root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>GitHub Issue Agent Web UI</h1><p>Index file not found in static directory.</p>"


@api.get("/api/config")
def get_config():
    token = os.getenv("GITHUB_TOKEN", "").strip()
    has_token = bool(token and token != "your_github_personal_access_token_here")
    return {
        "has_token": has_token,
        "model": "Llama 3.2 (via Ollama)",
        "status": current_workflow["status"]
    }


@api.get("/api/auth/github/login")
def github_oauth_login():
    """1-Click OAuth: Redirect user directly to GitHub authorization screen."""
    client_id = os.getenv("GITHUB_CLIENT_ID", "").strip()
    if not client_id:
        return RedirectResponse(url="/?oauth_error=no_client_id")
    
    redirect_uri = "http://127.0.0.1:8000/api/auth/github/callback"
    oauth_url = f"https://github.com/login/oauth/authorize?client_id={client_id}&scope=repo%20workflow&redirect_uri={redirect_uri}"
    return RedirectResponse(url=oauth_url)


@api.get("/api/auth/github/callback", response_class=HTMLResponse)
def github_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    """1-Click OAuth Callback: Automatically exchanges auth code for user access token."""
    if error or not code:
        return HTMLResponse(content=f"<h3>Authentication Failed</h3><p>{error or 'No code received'}</p><a href='/'>Return to App</a>")

    client_id = os.getenv("GITHUB_CLIENT_ID", "").strip()
    client_secret = os.getenv("GITHUB_CLIENT_SECRET", "").strip()

    import requests
    res = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": "http://127.0.0.1:8000/api/auth/github/callback"
        }
    )
    data = res.json()
    token = data.get("access_token")

    if not token:
        return HTMLResponse(content=f"<h3>OAuth Exchange Error</h3><p>{data.get('error_description', 'Token exchange failed.')}</p><a href='/'>Return to App</a>")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Authentication Successful</title></head>
    <body style="background:#090d16; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
        <h2>✅ Successfully Connected to GitHub!</h2>
        <p>Redirecting back to your application...</p>
        <script>
            sessionStorage.setItem('user_github_token', '{token}');
            window.location.href = '/';
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@api.post("/api/auth/github")
def trigger_github_auth():
    """Trigger browser popup OAuth flow and return user token."""
    token = authenticate_github_via_browser()
    return {"success": bool(token), "token": token if token else ""}




@api.post("/api/run")
async def run_agent_workflow(req: RunRequest):
    if current_workflow["status"] in ["running", "waiting_approval"]:
        raise HTTPException(status_code=400, detail="A workflow is already currently running.")

    token = req.token or os.getenv("GITHUB_TOKEN", "").strip()
    if token == "your_github_personal_access_token_here":
        token = ""

    initial_state = {
        "repo_url": req.repo_url.strip(),
        "issue_number": req.issue_number or 0,
        "token": token,
        "problem_description": req.problem_description.strip(),
        "mode": "issue" if (req.issue_number and req.issue_number > 0) else req.mode,
        "issue_title": "",
        "issue_body": "",
        "relevant_files": [],
        "proposed_fix": "",
        "tests_written": "",
        "pr_url": "",
        "messages": [],
        "human_approved": False,
        "retry_count": 0,
        "llm_calls": 0,
        "errors": []
    }

    current_workflow["status"] = "running"
    current_workflow["state"] = initial_state

    # Execute workflow in background task
    def execute_graph():
        import time
        try:
            # We patch human_approval_node dynamically for the web session
            from agent.graph import build_graph
            import agent.nodes as nodes_mod
            
            original_node = nodes_mod.human_approval_node
            nodes_mod.human_approval_node = web_human_approval_node
            
            try:
                compiled_app = build_graph()
                final_state = compiled_app.invoke(initial_state)
                current_workflow["state"] = final_state
                current_workflow["status"] = "completed" if final_state.get("pr_url") else "finished"
            finally:
                nodes_mod.human_approval_node = original_node

        except Exception as e:
            current_workflow["status"] = "failed"
            if current_workflow["state"]:
                current_workflow["state"]["errors"].append(str(e))

    asyncio.get_event_loop().run_in_executor(None, execute_graph)

    return {"status": "started", "mode": initial_state["mode"]}


@api.get("/api/status")
def get_workflow_status():
    state = current_workflow.get("state") or {}
    return {
        "status": current_workflow["status"],
        "repo_url": state.get("repo_url", ""),
        "mode": state.get("mode", ""),
        "issue_title": state.get("issue_title", ""),
        "issue_body": state.get("issue_body", ""),
        "relevant_files": state.get("relevant_files", []),
        "proposed_fix": state.get("proposed_fix", ""),
        "tests_written": state.get("tests_written", ""),
        "pr_url": state.get("pr_url", ""),
        "retry_count": state.get("retry_count", 0),
        "llm_calls": state.get("llm_calls", 0),
        "errors": state.get("errors", [])
    }


@api.post("/api/approval")
def submit_approval(req: ApprovalRequest):
    if current_workflow["status"] != "waiting_approval":
        raise HTTPException(status_code=400, detail="Workflow is not currently waiting for approval.")

    current_workflow["user_decision"] = {
        "approved": req.approved,
        "feedback": req.feedback or ""
    }
    return {"status": "decision_submitted", "approved": req.approved}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:api", host="127.0.0.1", port=8000, reload=True)
