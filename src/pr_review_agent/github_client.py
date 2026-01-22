"""GitHub client for fetching PR data."""

import time
from dataclasses import dataclass

import jwt
import requests
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

    @classmethod
    def from_app_credentials(
        cls, app_id: str, installation_id: str, private_key: str
    ) -> "GitHubClient":
        """Create GitHubClient using GitHub App credentials.

        Args:
            app_id: GitHub App ID
            installation_id: GitHub App installation ID
            private_key: GitHub App private key (PEM format)

        Returns:
            GitHubClient instance authenticated with an installation token
        """
        # Generate JWT
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 600,
            "iss": app_id,
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")

        # Exchange JWT for installation token
        response = requests.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=30,
        )
        response.raise_for_status()
        installation_token = response.json()["token"]

        return cls(installation_token)

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
