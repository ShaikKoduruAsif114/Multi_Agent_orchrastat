import re
from typing import Dict, Any, List
from langchain_core.tools import tool
from github import Github, GithubException, InputGitTreeElement


def parse_repo_name(repo_url: str) -> str:
    """Extract owner/repo string from a GitHub repository URL or full name."""
    repo_url = repo_url.strip().rstrip("/")
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    
    # Match https://github.com/owner/repo or github.com/owner/repo or owner/repo
    match = re.search(r"(?:github\.com/)?([^/]+/[^/]+)$", repo_url)
    if match:
        return match.group(1)
    return repo_url


@tool
def get_github_issue(repo_url: str, issue_number: int, token: str) -> dict:
    """Fetch a GitHub issue title and body.
    
    Args:
        repo_url: URL or 'owner/repo' of the GitHub repository.
        issue_number: The integer issue number to fetch.
        token: GitHub Personal Access Token (can be empty string for public repos).
        
    Returns:
        dict: Containing 'title', 'body', 'number', and 'html_url'.
    """
    try:
        g = Github(token) if token else Github()
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(number=int(issue_number))
        return {
            "title": issue.title,
            "body": issue.body or "",
            "number": issue.number,
            "state": issue.state,
            "html_url": issue.html_url
        }
    except GithubException as e:
        return {"error": f"GitHub API error: {e.status} - {e.data.get('message', str(e))}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@tool
def list_repo_files(repo_url: str, token: str) -> list[str]:
    """List all files in a GitHub repository.
    
    Args:
        repo_url: URL or 'owner/repo' of the GitHub repository.
        token: GitHub Personal Access Token.
        
    Returns:
        list[str]: List of file paths in the repository.
    """
    try:
        g = Github(token) if token else Github()
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        default_branch = repo.default_branch
        tree = repo.get_git_tree(default_branch, recursive=True)
        return [item.path for item in tree.tree if item.type == "blob"]
    except GithubException as e:
        return [f"Error: GitHub API error {e.status} - {e.data.get('message', str(e))}"]
    except Exception as e:
        return [f"Error: {str(e)}"]


@tool
def read_file(repo_url: str, file_path: str, token: str) -> str:
    """Read the contents of a specific file in the repo.
    
    Args:
        repo_url: URL or 'owner/repo' of the GitHub repository.
        file_path: Relative file path within the repository.
        token: GitHub Personal Access Token.
        
    Returns:
        str: Decoded file content as a string.
    """
    try:
        g = Github(token) if token else Github()
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        file_content = repo.get_contents(file_path)
        if isinstance(file_content, list):
            return f"Error: '{file_path}' is a directory, not a file."
        return file_content.decoded_content.decode("utf-8", errors="replace")
    except GithubException as e:
        return f"Error reading file '{file_path}': GitHub API error {e.status} - {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error reading file '{file_path}': {str(e)}"


@tool
def search_code(repo_url: str, query: str, token: str) -> list[str]:
    """Search for specific code patterns in the repository.
    
    Args:
        repo_url: URL or 'owner/repo' of the GitHub repository.
        query: Search query string.
        token: GitHub Personal Access Token.
        
    Returns:
        list[str]: Matching file paths or code snippets.
    """
    try:
        g = Github(token) if token else Github()
        repo_name = parse_repo_name(repo_url)
        full_query = f"{query} repo:{repo_name}"
        results = g.search_code(query=full_query)
        matches = []
        for file in list(results)[:10]:
            matches.append(file.path)
        return matches
    except GithubException as e:
        return [f"Error searching code: GitHub API error {e.status} - {e.data.get('message', str(e))}"]
    except Exception as e:
        return [f"Error searching code: {str(e)}"]


@tool
def scan_for_bugs(repo_url: str, token: str) -> list[str]:
    """Scan the entire codebase and identify potential bugs or code smell areas.
    
    Args:
        repo_url: URL or 'owner/repo' of the GitHub repository.
        token: GitHub Personal Access Token.
        
    Returns:
        list[str]: List of identified files and potential bug descriptions.
    """
    try:
        g = Github(token) if token else Github()
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
        files = [item.path for item in tree.tree if item.type == "blob"]
        
        # Focus on source code files (.py, .js, .ts, .java, etc.)
        source_files = [f for f in files if f.endswith(('.py', '.js', '.ts', '.java', '.go', '.rs'))]
        return source_files[:15]
    except Exception as e:
        return [f"Error scanning codebase: {str(e)}"]


@tool
def create_branch(repo_url: str, branch_name: str, token: str) -> str:
    """Create a new branch in the repository.
    
    Args:
        repo_url: URL or 'owner/repo' of the GitHub repository.
        branch_name: Name of the new branch to create.
        token: GitHub Personal Access Token.
        
    Returns:
        str: Success message or error message.
    """
    try:
        g = Github(token)
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        default_branch = repo.get_branch(repo.default_branch)
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=default_branch.commit.sha)
        return f"Successfully created branch '{branch_name}' from '{repo.default_branch}'"
    except GithubException as e:
        return f"Error creating branch: GitHub API error {e.status} - {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error creating branch: {str(e)}"


@tool
def commit_changes(repo_url: str, branch: str, files: dict, token: str) -> str:
    """Commit file changes to a branch.
    
    Args:
        repo_url: URL or 'owner/repo' of the GitHub repository.
        branch: Target branch name.
        files: Dictionary mapping file_path (str) to file_content (str).
        token: GitHub Personal Access Token.
        
    Returns:
        str: Success message or error message.
    """
    try:
        g = Github(token)
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        
        committed_files = []
        for file_path, content in files.items():
            try:
                # Try getting existing file to update
                existing_file = repo.get_contents(file_path, ref=branch)
                repo.update_file(
                    path=file_path,
                    message=f"fix: update {file_path}",
                    content=content,
                    sha=existing_file.sha,
                    branch=branch
                )
            except GithubException:
                # File doesn't exist, create it
                repo.create_file(
                    path=file_path,
                    message=f"feat: add {file_path}",
                    content=content,
                    branch=branch
                )
            committed_files.append(file_path)
            
        return f"Successfully committed changes to {', '.join(committed_files)} on branch '{branch}'."
    except GithubException as e:
        return f"Error committing changes: GitHub API error {e.status} - {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error committing changes: {str(e)}"


@tool
def open_pull_request(repo_url: str, branch: str, title: str, body: str, token: str) -> str:
    """Open a pull request on GitHub.
    
    Args:
        repo_url: URL or 'owner/repo' of the GitHub repository.
        branch: Head branch containing the changes.
        title: PR title.
        body: PR description body.
        token: GitHub Personal Access Token.
        
    Returns:
        str: PR URL or error message.
    """
    try:
        g = Github(token)
        repo_name = parse_repo_name(repo_url)
        repo = g.get_repo(repo_name)
        base = repo.default_branch
        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base=base
        )
        return pr.html_url
    except GithubException as e:
        return f"Error opening pull request: GitHub API error {e.status} - {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error opening pull request: {str(e)}"
