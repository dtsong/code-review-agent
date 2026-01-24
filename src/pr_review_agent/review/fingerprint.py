"""Issue fingerprinting for regression detection.

Generates consistent fingerprints for review issues so the same logical
issue produces the same fingerprint across reviews, even if line numbers
shift slightly or description wording varies.

Fingerprint components:
- File path (exact)
- Line range bucket (bucketed to nearest 10 lines)
- Issue category (exact)
- Severity level (exact)
- Normalized description (stop words removed, lowercased, sorted)
"""

import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pr_review_agent.review.llm_reviewer import ReviewIssue

# Common English stop words to remove for description normalization
STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "this", "that", "these", "those", "it", "its",
    "and", "or", "but", "not", "no", "nor",
    "if", "then", "else", "when", "where", "which", "what", "who",
    "there", "here", "found", "also",
})

# Line bucket size - issues within this many lines are considered the same location
LINE_BUCKET_SIZE = 10


def normalize_description(desc: str) -> str:
    """Normalize description for consistent fingerprinting.

    Removes stop words, punctuation, lowercases, and sorts remaining words
    to produce a canonical form that's resistant to wording variations.
    """
    if not desc:
        return ""

    # Lowercase
    text = desc.lower()

    # Remove punctuation
    text = re.sub(r"[^\w\s]", " ", text)

    # Split and remove stop words
    words = [w for w in text.split() if w not in STOP_WORDS]

    # Sort for order-independence
    words.sort()

    return " ".join(words)


def _bucket_line(line: int | None, start_line: int | None, end_line: int | None) -> int:
    """Bucket the line number to nearest LINE_BUCKET_SIZE.

    Uses midpoint of range if start/end are provided.
    Returns 0 if no line info available.
    """
    if start_line and end_line:
        effective_line = (start_line + end_line) // 2
    elif line:
        effective_line = line
    elif start_line:
        effective_line = start_line
    else:
        return 0

    return effective_line // LINE_BUCKET_SIZE


def fingerprint_issue(issue: "ReviewIssue") -> str:
    """Generate a fingerprint for a review issue.

    Returns a 16-character hex string (8 bytes of SHA-256).
    """
    # Build canonical components
    components = [
        issue.file or "",
        str(_bucket_line(issue.line, issue.start_line, issue.end_line)),
        issue.category or "",
        issue.severity or "",
        normalize_description(issue.description or ""),
    ]

    # Join with delimiter and hash
    canonical = "|".join(components)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Return first 16 hex chars (8 bytes) - enough for uniqueness
    return digest[:16]
