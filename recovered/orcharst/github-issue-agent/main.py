import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from agent.graph import app
from agent.github_auth import authenticate_github_via_browser


def main():
    print("=" * 65)
    print("🚀 GITHUB ISSUE AGENT — Autonomous Code Fix System")
    print("   Powered by LangGraph & Llama 3.2 via Ollama")
    print("=" * 65)

    # 1. GitHub Token / Browser OAuth Connection
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token or token == "your_github_personal_access_token_here":
        print("\n🔑 GitHub Connection Required to push branches & open PRs.")
        choice = input("Do you want to connect your GitHub account via Browser Popup? (Y/n): ").strip().lower()
        if choice in ["", "y", "yes"]:
            token = authenticate_github_via_browser()
        else:
            token = input("Enter your GitHub Personal Access Token manually: ").strip()
    else:
        print(f"\n🔑 Connected using GITHUB_TOKEN from .env")
        reconnect = input("Press ENTER to continue (or type 'auth' to reconnect via Browser Popup): ").strip().lower()
        if reconnect == "auth":
            token = authenticate_github_via_browser()

    # 2. Repository URL
    repo_url = input("\nEnter GitHub Repository URL (e.g. https://github.com/owner/repo): ").strip()
    while not repo_url:
        print("Error: Repository URL cannot be empty.")
        repo_url = input("Enter GitHub Repository URL: ").strip()

    # 3. Select Mode
    print("\nSelect Execution Mode:")
    print("  [1] Issue Mode (Fetch and fix a specific GitHub Issue Number)")
    print("  [2] Smart Mode (Provide problem description OR scan repo for bugs)")
    mode_choice = input("Enter choice (1 or 2) [default: 1]: ").strip()

    issue_number = 0
    problem_description = ""

    if mode_choice == "2":
        print("\n--- Smart Mode Selected ---")
        problem_description = input("Enter problem description (optional, press Enter to scan repo): ").strip()
    else:
        print("\n--- Issue Mode Selected ---")
        issue_str = input("Enter GitHub Issue Number: ").strip()
        try:
            issue_number = int(issue_str)
        except ValueError:
            print("Invalid issue number. Defaulting to 0 (Smart Mode).")
            issue_number = 0

    # Initial State
    initial_state = {
        "repo_url": repo_url,
        "issue_number": issue_number,
        "token": token,
        "problem_description": problem_description,
        "mode": "issue" if issue_number > 0 else "smart",
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

    print("\n" + "=" * 65)
    print("Starting Autonomous Agent Workflow...")
    print("=" * 65)

    # Run LangGraph App
    final_state = app.invoke(initial_state)

    print("\n" + "=" * 65)
    print("WORKFLOW SUMMARY")
    print("=" * 65)

    if final_state.get("pr_url"):
        print(f"✅ Pull Request Opened Successfully!")
        print(f"🔗 PR URL: {final_state['pr_url']}")
    elif final_state.get("human_approved") is False:
        print("❌ Workflow ended without opening PR (Fix rejected or retries exceeded).")
    else:
        print("⚠️ Workflow finished.")

    print(f"📊 Total LLM Calls: {final_state.get('llm_calls', 0)}")
    if final_state.get("errors"):
        print(f"⚠️ Errors encountered: {final_state['errors']}")
        if any("401" in str(err) or "Bad credentials" in str(err) for err in final_state["errors"]):
            print("\n" + "!" * 65)
            print("🔑 GITHUB TOKEN AUTHENTICATION FAILURE (401 Bad Credentials)")
            print("!" * 65)
            print("The GitHub Personal Access Token provided was missing, invalid, or expired.")
            print("\nTo fix this:")
            print("1. Go to GitHub -> Settings -> Developer Settings -> Personal Access Tokens (Tokens classic)")
            print("2. Click 'Generate new token' and check the 'repo' scope (Full control of private & public repos).")
            print("3. Copy the token (starts with ghp_...) and paste it into your '.env' file:")
            print("   GITHUB_TOKEN=ghp_your_actual_token_here")
            print("!" * 65)
    print("=" * 65)


if __name__ == "__main__":
    main()

