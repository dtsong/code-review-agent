"""Historical context for PR reviews.

Queries past review data to identify hot files and surface relevant past issues.
"""

from dataclasses import dataclass, field

from supabase import create_client


@dataclass
class FileHistory:
    """Historical review data for a single file."""

    file_path: str
    review_count: int = 0
    issue_count: int = 0
    common_issues: list[str] = field(default_factory=list)
    is_hot: bool = False


@dataclass
class HistoricalContext:
    """Historical context for a set of files."""

    file_histories: list[FileHistory] = field(default_factory=list)
    hot_files: list[str] = field(default_factory=list)
    past_issues_summary: str = ""


def query_file_history(
    files: list[str],
    repo: str,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
) -> HistoricalContext:
    """Query past review history for the given files.

    Args:
        files: List of file paths touched in current PR.
        repo: Repository identifier (owner/repo).
        supabase_url: Supabase URL for querying history.
        supabase_key: Supabase API key.

    Returns:
        HistoricalContext with file histories and hot file identification.
    """
    if not supabase_url or not supabase_key:
        return HistoricalContext()

    try:
        client = create_client(supabase_url, supabase_key)

        file_histories = []
        hot_files = []

        for file_path in files:
            # Query review_events for issues mentioning this file
            result = (
                client.table("review_events")
                .select("issues_found")
                .eq("repo_name", repo.split("/")[-1])
                .execute()
            )

            review_count = 0
            issue_count = 0
            common_issues: list[str] = []

            if result.data:
                for row in result.data:
                    issues = row.get("issues_found") or []
                    file_issues = [i for i in issues if i.get("file") == file_path]
                    if file_issues:
                        review_count += 1
                        issue_count += len(file_issues)
                        for issue in file_issues:
                            desc = issue.get("description", "")
                            if desc and desc not in common_issues:
                                common_issues.append(desc)

            is_hot = review_count >= 3 or issue_count >= 5
            if is_hot:
                hot_files.append(file_path)

            file_histories.append(FileHistory(
                file_path=file_path,
                review_count=review_count,
                issue_count=issue_count,
                common_issues=common_issues[:5],
                is_hot=is_hot,
            ))

        # Build summary for LLM context
        summary_parts = []
        if hot_files:
            summary_parts.append(
                f"Hot files (frequently reviewed): {', '.join(hot_files)}"
            )
        for fh in file_histories:
            if fh.common_issues:
                summary_parts.append(
                    f"{fh.file_path}: past issues include "
                    f"{'; '.join(fh.common_issues[:3])}"
                )

        return HistoricalContext(
            file_histories=file_histories,
            hot_files=hot_files,
            past_issues_summary="\n".join(summary_parts),
        )

    except Exception:
        # Don't fail the review if history query fails
        return HistoricalContext()
