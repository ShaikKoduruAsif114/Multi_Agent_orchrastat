import re
from typing import Dict, Any, List
from langchain_core.tools import tool
from github import Github, GithubException, InputGitTreeElement


def parse_repo_name(repo_url: str) -> str:
    """Extract owner/repo string from a GitHub repository URL or full name."""
    repo_url = repo_url.strip().rstrip("/")
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    
    match = re.search(r"(?:github\.com/)?([^/]+/[^/]+)$", repo_url)
    if match:
        return match.group(1)
    return repo_url


def sanitize_ascii(text: str) -> str:
    """Sanitize non-ASCII unicode/emoji characters to clean ASCII text for PyGithub HTTP header safety."""
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    replacements = {
        "✅": "[PASSED]",
        "❌": "[FAILED]",
        "🚀": "[LAUNCH]",
        "🔑": "[KEY]",
        "🎉": "[SUCCESS]",
        "⚠️": "[WARNING]",
        "🐳": "[DOCKER]"
    }
    for emoji, text_sub in replacements.items():
        text = text.replace(emoji, text_sub)
    return text.encode("ascii", errors="ignore").decode("ascii")


@tool
def get_github_issue(repo_url: str, issue_number: int, token: str) -> dict:
    """Fetch a GitHub issue title and body."""
    try:
        clean_token = sanitize_ascii(token).strip()
        g = Github(clean_token) if clean_token else Github()
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(int(issue_number))
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "html_url": issue.html_url
        }
    except GithubException as e:
        return {"error": f"GitHub API error {e.status} - {e.data.get('message', str(e))}"}
    except Exception as e:
        return {"error": str(e)}


@tool
def list_repo_files(repo_url: str, token: str) -> list:
    """List file paths in the repository."""
    try:
        clean_token = sanitize_ascii(token).strip()
        g = Github(clean_token) if clean_token else Github()
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        
        default_branch = repo.default_branch
        tree = repo.get_git_tree(default_branch, recursive=True)
        
        file_list = []
        for item in tree.tree:
            if item.type == "blob":
                if not any(item.path.startswith(ignore) for ignore in [".git/", "node_modules/", "vendor/", "__pycache__/"]):
                    file_list.append(item.path)
        return file_list
    except GithubException as e:
        return [f"Error listing files: GitHub API error {e.status} - {e.data.get('message', str(e))}"]
    except Exception as e:
        return [f"Error listing files: {str(e)}"]


@tool
def read_file(repo_url: str, file_path: str, token: str) -> str:
    """Read the content of a file from the repository."""
    try:
        clean_token = sanitize_ascii(token).strip()
        g = Github(clean_token) if clean_token else Github()
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        content_file = repo.get_contents(file_path)
        return content_file.decoded_content.decode("utf-8", errors="replace")
    except GithubException as e:
        return f"Error reading file {file_path}: GitHub API error {e.status} - {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error reading file {file_path}: {str(e)}"


@tool
def search_code(repo_url: str, query: str, token: str) -> list:
    """Search code files in a repository for a specific query keyword."""
    try:
        clean_token = sanitize_ascii(token).strip()
        g = Github(clean_token) if clean_token else Github()
        repo_name = parse_repo_name(repo_url)
        results = g.search_code(query=f"repo:{repo_name} {query}")
        matched_files = [item.path for item in results[:10]]
        return matched_files
    except GithubException as e:
        return [f"Error searching code: GitHub API error {e.status}"]
    except Exception as e:
        return [f"Error searching code: {str(e)}"]


@tool
def scan_for_bugs(repo_url: str, token: str) -> list:
    """Scan candidate files for potential bugs or maintenance focus."""
    files = list_repo_files.invoke({"repo_url": repo_url, "token": token})
    if isinstance(files, list) and files and not files[0].startswith("Error"):
        code_files = [f for f in files if f.endswith(('.py', '.js', '.ts', '.java', '.go', '.rs')) and not f.startswith('.') and 'test' not in f.lower()]
        if code_files:
            return code_files[:5]
        return files[:5]
    
    raise ValueError(f"Could not fetch repository files. Are you sure you have access to {repo_url}?")


@tool
def create_branch(repo_url: str, branch_name: str, token: str) -> str:
    """Create a new branch in the repository."""
    try:
        clean_token = sanitize_ascii(token).strip()
        clean_branch_name = sanitize_ascii(branch_name).strip()
        g = Github(clean_token)
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        default_branch = repo.get_branch(repo.default_branch)
        repo.create_git_ref(ref=f"refs/heads/{clean_branch_name}", sha=default_branch.commit.sha)
        return f"Successfully created branch '{clean_branch_name}' from '{repo.default_branch}'"
    except GithubException as e:
        return f"Error creating branch: GitHub API error {e.status} - {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error creating branch: {str(e)}"


@tool
def commit_changes(repo_url: str, branch: str, files: dict, token: str) -> str:
    """Commit file changes to a branch."""
    try:
        clean_token = sanitize_ascii(token).strip()
        clean_branch = sanitize_ascii(branch).strip()
        g = Github(clean_token)
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        
        committed_files = []
        for file_path, content in files.items():
            clean_path = sanitize_ascii(file_path).strip()
            clean_content = sanitize_ascii(content)
            try:
                existing_file = repo.get_contents(clean_path, ref=clean_branch)
                repo.update_file(
                    path=clean_path,
                    message=f"fix: update {clean_path}",
                    content=clean_content,
                    sha=existing_file.sha,
                    branch=clean_branch
                )
            except GithubException:
                repo.create_file(
                    path=clean_path,
                    message=f"feat: add {clean_path}",
                    content=clean_content,
                    branch=clean_branch
                )
            committed_files.append(clean_path)
            
        return f"Successfully committed changes to {', '.join(committed_files)} on branch '{clean_branch}'."
    except GithubException as e:
        return f"Error committing changes: GitHub API error {e.status} - {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error committing changes: {str(e)}"


@tool
def open_pull_request(repo_url: str, branch: str, title: str, body: str, token: str) -> str:
    """Open a pull request on GitHub."""
    try:
        clean_token = sanitize_ascii(token).strip()
        clean_branch = sanitize_ascii(branch).strip()
        clean_title = sanitize_ascii(title).strip()
        clean_body = sanitize_ascii(body)

        g = Github(clean_token)
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        base = repo.default_branch

        pr = repo.create_pull(
            title=clean_title,
            body=clean_body,
            head=clean_branch,
            base=base
        )
        return pr.html_url
    except GithubException as e:
        return f"Error opening pull request: GitHub API error {e.status} - {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error opening pull request: {str(e)}"
