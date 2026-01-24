"""Diff chunking for large PRs that exceed LLM context limits.

Splits diffs into manageable chunks and merges review results.
"""

import re
from dataclasses import dataclass
from enum import Enum

from pr_review_agent.review.llm_reviewer import LLMReviewResult


class ChunkStrategy(Enum):
    """Strategy for splitting diffs."""

    FILE = "file"
    LINES = "lines"
    AUTO = "auto"


@dataclass
class DiffChunk:
    """A chunk of a diff for individual review."""

    content: str
    file_path: str
    chunk_index: int
    total_chunks: int


# Pattern to match the start of a file diff
_FILE_DIFF_PATTERN = re.compile(r"^diff --git a/(.*?) b/", re.MULTILINE)


def _split_by_file(diff: str) -> list[tuple[str, str]]:
    """Split a unified diff into per-file sections.

    Returns list of (file_path, diff_content) tuples.
    """
    matches = list(_FILE_DIFF_PATTERN.finditer(diff))
    if not matches:
        return []

    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(diff)
        file_path = match.group(1)
        content = diff[start:end].rstrip()
        sections.append((file_path, content))

    return sections


def _split_by_lines(
    diff: str, file_path: str, max_lines: int
) -> list[tuple[str, str]]:
    """Split a single-file diff into line-based chunks.

    Preserves the diff header in each chunk for context.
    Returns list of (file_path, chunk_content) tuples.
    """
    lines = diff.split("\n")

    # Find the header (everything before the first hunk)
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("@@"):
            header_end = i
            break

    header = "\n".join(lines[:header_end])
    body_lines = lines[header_end:]

    if len(body_lines) <= max_lines:
        return [(file_path, diff)]

    chunks: list[tuple[str, str]] = []
    for start in range(0, len(body_lines), max_lines):
        chunk_lines = body_lines[start : start + max_lines]
        chunk_content = header + "\n" + "\n".join(chunk_lines)
        chunks.append((file_path, chunk_content.rstrip()))

    return chunks


def chunk_diff(
    diff: str,
    strategy: ChunkStrategy = ChunkStrategy.AUTO,
    max_lines: int = 200,
) -> list[DiffChunk]:
    """Split a diff into chunks using the specified strategy.

    Args:
        diff: The full unified diff text.
        strategy: Chunking strategy to use.
        max_lines: Maximum lines per chunk (for LINES and AUTO strategies).

    Returns:
        List of DiffChunk objects ready for individual review.
    """
    if not diff.strip():
        return []

    if strategy == ChunkStrategy.AUTO:
        file_sections = _split_by_file(diff)
        if len(file_sections) > 1:
            # Multiple files: use file-based chunking, then split large files
            raw_chunks: list[tuple[str, str]] = []
            for file_path, content in file_sections:
                file_lines = content.split("\n")
                if len(file_lines) > max_lines:
                    raw_chunks.extend(
                        _split_by_lines(content, file_path, max_lines)
                    )
                else:
                    raw_chunks.append((file_path, content))
        else:
            # Single file: use line-based chunking
            file_path = file_sections[0][0] if file_sections else "unknown"
            content = file_sections[0][1] if file_sections else diff
            raw_chunks = _split_by_lines(content, file_path, max_lines)

    elif strategy == ChunkStrategy.FILE:
        raw_chunks = _split_by_file(diff)

    elif strategy == ChunkStrategy.LINES:
        file_sections = _split_by_file(diff)
        raw_chunks = []
        for file_path, content in file_sections:
            raw_chunks.extend(_split_by_lines(content, file_path, max_lines))

    total = len(raw_chunks)
    return [
        DiffChunk(
            content=content,
            file_path=file_path,
            chunk_index=i,
            total_chunks=total,
        )
        for i, (file_path, content) in enumerate(raw_chunks)
    ]


def merge_review_results(results: list[LLMReviewResult]) -> LLMReviewResult:
    """Merge multiple chunk review results into a unified result.

    Combines issues (deduplicating by fingerprint), aggregates tokens/cost,
    and joins summaries.
    """
    if not results:
        return LLMReviewResult()

    if len(results) == 1:
        return results[0]

    # Deduplicate issues by fingerprint
    seen_fingerprints: set[str] = set()
    all_issues = []
    for r in results:
        for issue in r.issues:
            if issue.fingerprint and issue.fingerprint in seen_fingerprints:
                continue
            if issue.fingerprint:
                seen_fingerprints.add(issue.fingerprint)
            all_issues.append(issue)

    # Combine inline comments
    all_inline = []
    for r in results:
        all_inline.extend(r.inline_comments)

    # Join summaries
    summaries = [r.summary for r in results if r.summary]
    merged_summary = " | ".join(summaries)

    # Combine lists (deduplicate)
    all_strengths = list(dict.fromkeys(s for r in results for s in r.strengths))
    all_concerns = list(dict.fromkeys(c for r in results for c in r.concerns))
    all_questions = list(dict.fromkeys(q for r in results for q in r.questions))

    # Aggregate metrics
    total_input = sum(r.input_tokens for r in results)
    total_output = sum(r.output_tokens for r in results)
    total_cost = sum(r.cost_usd for r in results)

    # Use the model from the first result (all chunks use same model)
    model = results[0].model if results else ""

    return LLMReviewResult(
        issues=all_issues,
        inline_comments=all_inline,
        summary=merged_summary,
        strengths=all_strengths,
        concerns=all_concerns,
        questions=all_questions,
        input_tokens=total_input,
        output_tokens=total_output,
        model=model,
        cost_usd=total_cost,
    )
