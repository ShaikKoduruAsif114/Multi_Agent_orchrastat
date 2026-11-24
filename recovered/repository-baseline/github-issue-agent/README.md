# GitHub Issue Agent — Autonomous Code Fix System

An autonomous AI agent built with **LangGraph**, **LangChain**, **PyGithub**, and **Llama 3.2 via Ollama** that automatically researches a repository, writes code fixes, writes unit tests, requests human approval, and opens pull requests on GitHub.

---

## 🏗️ Architecture Diagram

```
                              [START]
                                 │
                           ┌─────▼─────┐
                           │ input_node│
                           └─────┬─────┘
                                 │
                           ┌─────▼─────┐
                           │ fetch_node│
                           └─────┬─────┘
                                 │
                         ┌───────▼───────┐
                         │ research_node │
                         └───────┬───────┘
                                 │
                        ┌────────▼────────┐
                        │ code_writer_node│◄─────────────┐
                        └────────┬────────┘              │
                                 │                       │ (If NO & Retry <= 3)
                        ┌────────▼────────┐              │
                        │ test_writer_node│              │
                        └────────┬────────┘              │
                                 │                       │
                       ┌─────────▼───────────┐           │
                       │ human_approval_node ├───────────┘
                       └─────────┬───────────┘
                                 │ (If YES)
                            ┌────▼────┐
                            │ pr_node │
                            └────┬────┘
                                 │
                              [ END ]
```

---

## 🛠️ Modes & Features

### 🌐 Automatic Browser Popup Authentication
When you run `python main.py`, the agent asks to connect your GitHub account via a **Browser Popup Window** (using GitHub's official OAuth Device Flow used by GitHub CLI and VS Code):
1. A browser window pops up automatically (`https://github.com/login/device`).
2. Enter the displayed 8-character code and click **Authorize**.
3. The token is automatically saved to `.env` — **no manual token copy-pasting required!**

### Mode 1 — Issue Mode
- **Inputs**: GitHub Repo URL + GitHub Issue Number + Personal Access Token (or Browser Popup Auth).
- **Workflow**: Fetches issue title & body via GitHub API $\rightarrow$ Researches repo $\rightarrow$ Writes fix $\rightarrow$ Writes pytest unit tests $\rightarrow$ Requests Human Approval $\rightarrow$ Opens Pull Request.

### Mode 2 — Smart Mode
- **Inputs**: GitHub Repo URL + Problem description (optional).
- **Workflow**:
  - **With Description**: Focuses on specified issue area $\rightarrow$ Researches $\rightarrow$ Writes fix $\rightarrow$ Unit tests $\rightarrow$ Approval $\rightarrow$ Open PR.
  - **Without Description**: Scans codebase for candidate bug files $\rightarrow$ Researches $\rightarrow$ Writes fix $\rightarrow$ Unit tests $\rightarrow$ Approval $\rightarrow$ Open PR.


---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- **Python 3.11+**
- **Ollama** installed with `llama3.2` model (`ollama run llama3.2`)

### 2. Installation
```bash
cd github-issue-agent
pip install -r requirements.txt
```

### 3. Environment Configuration
Create or edit `.env`:
```env
GITHUB_TOKEN=your_github_personal_access_token_here
```

### 4. Running the Agent
```bash
python main.py
```

---

## 📂 Project Structure

```
github-issue-agent/
│
├── agent/
│   ├── __init__.py
│   ├── state.py          # AgentState TypedDict schema
│   ├── tools.py          # GitHub API integration tools
│   ├── nodes.py          # 7 agent nodes (input, fetch, research, code, test, approval, pr)
│   ├── edges.py          # Retry handler & conditional edge router
│   └── graph.py          # LangGraph state machine assembly
│
├── main.py               # Interactive CLI entrypoint
├── requirements.txt      # Dependencies (LangGraph, PyGithub, pytest, etc.)
├── .env                  # Environment variables
├── .gitignore            # Ignore cached files
└── README.md             # Architecture & user guide
```

---

## 🧪 Example Output

```text
=================================================================
🚀 GITHUB ISSUE AGENT — Autonomous Code Fix System
   Powered by LangGraph & Llama 3.2 via Ollama
=================================================================

Select Execution Mode:
  [1] Issue Mode (Fetch and fix a specific GitHub Issue Number)
  [2] Smart Mode (Provide problem description OR scan repo for bugs)

Enter choice (1 or 2) [default: 1]: 1
Enter GitHub Issue Number: 42

=================================================================
HUMAN APPROVAL REQUIRED
=================================================================
Issue: Fix division by zero in calculate_rate()
Relevant Files: src/math_utils.py

--- PROPOSED FIX ---
def calculate_rate(numerator, denominator):
    if denominator == 0:
        return 0.0
    return numerator / denominator

--- UNIT TESTS ---
def test_calculate_rate_zero():
    assert calculate_rate(10, 0) == 0.0

Do you approve this fix? (yes/no): yes

=================================================================
WORKFLOW SUMMARY
=================================================================
✅ Pull Request Opened Successfully!
🔗 PR URL: https://github.com/owner/repo/pull/15
📊 Total LLM Calls: 3
=================================================================
```
