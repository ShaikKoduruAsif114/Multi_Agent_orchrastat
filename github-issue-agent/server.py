import os
import sys
import time
import json
import asyncio
from typing import Dict, Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from agent.state import AgentState
from agent.graph import app as graph_app
from agent.github_auth import authenticate_github_via_browser
from agent.workflow_state import CURRENT_WORKFLOW as current_workflow

api = FastAPI(title="GitHub Issue Agent API")


class RunRequest(BaseModel):
    repo_url: str
    mode: str = "issue"  # "issue" or "smart"
    issue_number: Optional[int] = 0
    problem_description: Optional[str] = ""
    token: Optional[str] = ""

class ApprovalRequest(BaseModel):
    approved: bool
    feedback: Optional[str] = ""


# Serve Static Assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    api.mount("/static", StaticFiles(directory=static_dir), name="static")


@api.get("/", response_class=HTMLResponse)
def index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>GitHub Issue Agent API</h1>"


@api.get("/api/config")
def get_config():
    token = os.getenv("GITHUB_TOKEN", "").strip()
    has_token = bool(token and token != "your_github_personal_access_token_here")
    return {
        "has_github_token": has_token,
        "ollama_model": "llama3.2",
    }


@api.get("/api/auth/github/login")
def github_oauth_login():
    client_id = os.getenv("GITHUB_CLIENT_ID", "").strip()
    redirect_uri = "http://127.0.0.1:8000/api/auth/github/callback"
    if not client_id:
        return RedirectResponse(url="https://github.com/settings/tokens/new?scopes=repo,workflow&description=GitHub+Issue+Agent")

    oauth_url = f"https://github.com/login/oauth/authorize?client_id={client_id}&scope=repo%20workflow&redirect_uri={redirect_uri}"
    return RedirectResponse(url=oauth_url)


@api.get("/api/auth/github/callback", response_class=HTMLResponse)
def github_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
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
    <head><title>GitHub Connected</title></head>
    <body style="font-family:sans-serif; background:#0f172a; color:#fff; display:flex; align-items:center; justify-content:center; height:100vh; margin:0;">
        <div style="text-align:center; padding:30px; background:#1e293b; border-radius:16px; border:1px solid #334155;">
            <h2 style="color:#10b981;">✅ GitHub Connected Successfully!</h2>
            <p>Your session token is saved. Closing popup...</p>
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{ type: "GITHUB_AUTH_SUCCESS", token: "{token}" }}, "*");
                    window.close();
                }} else {{
                    sessionStorage.setItem("user_github_token", "{token}");
                    window.location.href = "/";
                }}
            </script>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@api.get("/api/auth/github/popup")
def trigger_github_auth():
    token = authenticate_github_via_browser()
    return {"success": bool(token), "token": token if token else ""}


@api.post("/api/run")
async def run_agent_workflow(req: RunRequest):
    current_workflow["status"] = "idle"
    current_workflow["user_decision"] = None

    token = req.token or os.getenv("GITHUB_TOKEN", "").strip()
    if token == "your_github_personal_access_token_here":
        token = ""

    initial_state = {
        "repo_url": req.repo_url.strip(),
        "issue_number": req.issue_number or 0,
        "token": token,
        "problem_description": req.problem_description.strip(),
        "mode": "issue" if (req.issue_number and req.issue_number > 0) else req.mode,
        "is_web": True,
        "issue_title": "",
        "issue_body": "",
        "relevant_files": [],
        "proposed_fix": "",
        "tests_written": "",
        "tests_passed": False,
        "test_results": "",
        "pr_url": "",
        "messages": [],
        "human_approved": False,
        "retry_count": 0,
        "llm_calls": 0,
        "errors": []
    }


    current_workflow["status"] = "running"
    current_workflow["state"] = initial_state

    def execute_graph():
        try:
            final_state = graph_app.invoke(initial_state)
            current_workflow["state"] = final_state
            current_workflow["status"] = "completed" if final_state.get("pr_url") else "finished"
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
        "tests_passed": state.get("tests_passed", False),
        "test_results": state.get("test_results", ""),
        "pr_url": state.get("pr_url", ""),

        "human_approved": state.get("human_approved", False),
        "retry_count": state.get("retry_count", 0),
        "llm_calls": state.get("llm_calls", 0),
        "errors": state.get("errors", []),
        "logs": current_workflow.get("logs", [])
    }



@api.post("/api/approval")
def post_approval_decision(req: ApprovalRequest):
    if current_workflow["status"] != "waiting_approval":
        raise HTTPException(status_code=400, detail="Workflow is not currently awaiting approval.")

    current_workflow["user_decision"] = {
        "approved": req.approved,
        "feedback": req.feedback or ""
    }
    return {"status": "decision_received", "approved": req.approved}
