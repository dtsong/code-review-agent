"""Prompt injection sanitizer for PR diffs.

Detects and neutralizes injection attempts that could manipulate
the LLM review process through malicious content in diffs.
"""

import re
from dataclasses import dataclass, field

# Unicode characters used in direction/visibility attacks
DANGEROUS_UNICODE = {
    "\u202a",  # Left-to-right embedding
    "\u202b",  # Right-to-left embedding
    "\u202c",  # Pop directional formatting
    "\u202d",  # Left-to-right override
    "\u202e",  # Right-to-left override
    "\u2066",  # Left-to-right isolate
    "\u2067",  # Right-to-left isolate
    "\u2068",  # First strong isolate
    "\u2069",  # Pop directional isolate
    "\u200b",  # Zero-width space
    "\u200c",  # Zero-width non-joiner
    "\u200d",  # Zero-width joiner
    "\ufeff",  # Zero-width no-break space (BOM)
}

# Patterns that indicate injection attempts
# Each tuple: (compiled_regex, pattern_type, description)
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # System prompt overrides
    (
        re.compile(
            r"(?:^|\s)system\s*:\s*.{10,}",
            re.IGNORECASE,
        ),
        "system_prompt_override",
        "Attempt to inject system-level instructions",
    ),
    # Role switches
    (
        re.compile(
            r"you\s+are\s+now\s+(?:an?\s+)?(?:assistant|ai|helper|bot|code\s+(?:reviewer|approver))",
            re.IGNORECASE,
        ),
        "role_switch",
        "Attempt to redefine the AI's role",
    ),
    (
        re.compile(
            r"(?:^|\s)assistant\s*:\s*.{10,}",
            re.IGNORECASE,
        ),
        "role_switch",
        "Attempt to inject assistant response",
    ),
    # Instruction injection
    (
        re.compile(
            r"ignore\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+instructions",
            re.IGNORECASE,
        ),
        "instruction_injection",
        "Attempt to override previous instructions",
    ),
    (
        re.compile(
            r"(?:disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|your)\s+(?:instructions|rules|guidelines|prompts)",
            re.IGNORECASE,
        ),
        "instruction_injection",
        "Attempt to override instructions",
    ),
    # Delimiter manipulation
    (
        re.compile(
            r"end\s+of\s+(?:diff|code|input|context)\s*[.!]?\s*(?:new|begin|start)\s+(?:system|instructions|prompt)",
            re.IGNORECASE,
        ),
        "delimiter_manipulation",
        "Attempt to inject new context boundary",
    ),
    # Response injection - trying to dictate the JSON output
    (
        re.compile(
            r"respond\s+with\s+(?:this\s+)?(?:json|the\s+following)",
            re.IGNORECASE,
        ),
        "response_injection",
        "Attempt to dictate response format/content",
    ),
    (
        re.compile(
            r"(?:output|return|respond)\s*:\s*\{[\"'](?:summary|issues)",
            re.IGNORECASE,
        ),
        "response_injection",
        "Attempt to inject JSON response",
    ),
]


@dataclass
class InjectionAttempt:
    """Record of a detected injection attempt."""

    pattern_type: str
    description: str
    matched_text: str
    line_number: int


@dataclass
class SanitizationResult:
    """Result of sanitizing a diff."""

    sanitized_diff: str
    attempts_detected: list[InjectionAttempt] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Whether the diff had no injection attempts."""
        return len(self.attempts_detected) == 0


def _check_unicode_attacks(line: str, line_number: int) -> list[InjectionAttempt]:
    """Check for dangerous Unicode characters in a line."""
    found = []
    dangerous_in_line = [ch for ch in line if ch in DANGEROUS_UNICODE]
    if dangerous_in_line:
        found.append(InjectionAttempt(
            pattern_type="unicode_attack",
            description="Dangerous Unicode control characters detected",
            matched_text=repr(dangerous_in_line[:3]),
            line_number=line_number,
        ))
    return found


def _strip_unicode(line: str) -> str:
    """Remove dangerous Unicode characters from a line."""
    return "".join(ch for ch in line if ch not in DANGEROUS_UNICODE)


def _is_diff_content_line(line: str) -> bool:
    """Check if line is an added line in diff (content we should scan)."""
    return line.startswith("+") and not line.startswith("+++")


def sanitize_diff(diff: str) -> SanitizationResult:
    """Sanitize a diff by detecting and neutralizing injection attempts.

    Scans added lines in the diff for prompt injection patterns.
    Replaces detected injections with a sanitized marker while
    preserving legitimate code.

    Args:
        diff: The raw diff text to sanitize.

    Returns:
        SanitizationResult with sanitized diff and detected attempts.
    """
    attempts: list[InjectionAttempt] = []
    lines = diff.split("\n")
    sanitized_lines: list[str] = []

    for line_idx, line in enumerate(lines):
        line_number = line_idx + 1

        # Only scan added lines for injection patterns
        if not _is_diff_content_line(line):
            sanitized_lines.append(line)
            continue

        # Check for Unicode attacks
        unicode_attempts = _check_unicode_attacks(line, line_number)
        if unicode_attempts:
            attempts.extend(unicode_attempts)
            line = _strip_unicode(line)

        # Check text-based injection patterns
        line_content = line[1:]  # Strip the leading +
        line_modified = False

        for pattern, pattern_type, description in _INJECTION_PATTERNS:
            match = pattern.search(line_content)
            if match:
                matched_text = match.group(0)
                attempts.append(InjectionAttempt(
                    pattern_type=pattern_type,
                    description=description,
                    matched_text=matched_text,
                    line_number=line_number,
                ))
                # Replace the matched injection with a sanitized marker
                prefix = line_content[:match.start()]
                suffix = line_content[match.end():]
                line_content = f"{prefix}[SANITIZED:{pattern_type}]{suffix}"
                line_modified = True

        if line_modified:
            line = "+" + line_content

        sanitized_lines.append(line)

    sanitized_diff = "\n".join(sanitized_lines)

    return SanitizationResult(
        sanitized_diff=sanitized_diff,
        attempts_detected=attempts,
    )
