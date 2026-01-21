"""GitHub client for fetching PR data."""

from dataclasses import dataclass

from github import Github


@dataclass
class PRData:
    """PR data container."""

    owner: str
    repo: str
    number: int
    title: str
    author: str
    description: str
    diff: str
    files_changed: list[str]
    lines_added: int
    lines_removed: int
    base_branch: str
    head_branch: str
    url: str


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(self, token: str):
        """Initialize with GitHub token."""
        self.client = Github(token)

    def fetch_pr(self, owner: str, repo: str, pr_number: int) -> PRData:
        """Fetch all PR data needed for review."""
        repo_obj = self.client.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(pr_number)

        # Get file changes and build diff
        files = list(pr.get_files())
        file_names = [f.filename for f in files]

        # Combine patches into full diff
        diff_parts = []
        for f in files:
            if f.patch:
                diff_parts.append(f"--- a/{f.filename}\n+++ b/{f.filename}\n{f.patch}")

        return PRData(
            owner=owner,
            repo=repo,
            number=pr_number,
            title=pr.title,
            author=pr.user.login,
            description=pr.body or "",
            diff="\n".join(diff_parts),
            files_changed=file_names,
            lines_added=pr.additions,
            lines_removed=pr.deletions,
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            url=pr.html_url,
        )

    def post_comment(self, owner: str, repo: str, pr_number: int, body: str) -> str:
        """Post a comment on a PR. Returns the comment URL."""
        repo_obj = self.client.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(pr_number)
        comment = pr.create_issue_comment(body)
        return comment.html_url
