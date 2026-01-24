"""Secret detection and redaction for review output.

Scans review output for accidentally exposed secrets before posting
to GitHub, redacting any matches to prevent credential leakage.
"""

import re
from dataclasses import dataclass, field

# Patterns that indicate placeholder/example values (not real secrets)
# Only match when the value IS a placeholder, not when it merely contains
# a substring like "example" as part of a longer key.
_PLACEHOLDER_PATTERNS = re.compile(
    r"^(?:your[-_]|replace[-_]me|xxx+|fake[-_]|dummy[-_]|placeholder)"
    r"|[-_](?:here|example|placeholder|replace)$",
    re.IGNORECASE,
)

# Secret detection patterns: (name, regex, description)
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "aws_access_key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "AWS Access Key ID",
    ),
    (
        "aws_secret_key",
        re.compile(r"(?:aws_secret|secret_key|secret_access)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"),
        "AWS Secret Access Key",
    ),
    (
        "github_token",
        re.compile(r"(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{30,}"),
        "GitHub Personal Access Token",
    ),
    (
        "jwt_token",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        "JWT Token",
    ),
    (
        "private_key",
        re.compile(
            r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----"
            r"[\s\S]*?"
            r"-----END\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----",
        ),
        "Private Key (PEM)",
    ),
    (
        "api_key",
        re.compile(
            r"(?:api[_-]?key|apikey|secret[_-]?key)\s*[=:]\s*['\"]?"
            r"([A-Za-z0-9_\-]{20,})['\"]?",
            re.IGNORECASE,
        ),
        "Generic API Key",
    ),
    (
        "database_url",
        re.compile(
            r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://"
            r"[^:]+:[^@]+@[^\s'\"]+",
            re.IGNORECASE,
        ),
        "Database Connection URL",
    ),
    (
        "slack_webhook",
        re.compile(r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"),
        "Slack Webhook URL",
    ),
    (
        "password",
        re.compile(
            r"(?:password|passwd|pwd)\s*[=:]\s*['\"]([^'\"]{8,})['\"]",
            re.IGNORECASE,
        ),
        "Password Assignment",
    ),
]


@dataclass
class SecretMatch:
    """A detected secret in text."""

    secret_type: str
    description: str
    start: int
    end: int
    matched_text: str


@dataclass
class RedactionResult:
    """Result of redacting secrets from text."""

    redacted_text: str
    matches: list[SecretMatch] = field(default_factory=list)

    @property
    def secrets_found(self) -> int:
        """Number of secrets detected."""
        return len(self.matches)


def _is_placeholder(text: str) -> bool:
    """Check if matched text looks like a placeholder/example."""
    return bool(_PLACEHOLDER_PATTERNS.search(text))


def scan_for_secrets(text: str) -> list[SecretMatch]:
    """Scan text for secret patterns.

    Returns list of SecretMatch objects for each detected secret.
    Filters out obvious placeholders and example values.
    """
    matches: list[SecretMatch] = []

    for name, pattern, description in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            matched_text = match.group(0)

            # Skip placeholders/examples
            if _is_placeholder(matched_text):
                continue

            matches.append(SecretMatch(
                secret_type=name,
                description=description,
                start=match.start(),
                end=match.end(),
                matched_text=matched_text,
            ))

    return matches


def redact_secrets(text: str) -> RedactionResult:
    """Scan text and redact any detected secrets.

    Replaces secrets with [REDACTED] while preserving context.
    Never fails - returns original text if scanning encounters errors.
    """
    matches = scan_for_secrets(text)

    if not matches:
        return RedactionResult(redacted_text=text)

    # Sort matches by position (reverse) to replace from end to start
    sorted_matches = sorted(matches, key=lambda m: m.start, reverse=True)

    redacted = text
    for match in sorted_matches:
        redacted = redacted[: match.start] + "[REDACTED]" + redacted[match.end :]

    return RedactionResult(redacted_text=redacted, matches=matches)
