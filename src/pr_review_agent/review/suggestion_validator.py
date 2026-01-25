"""Validate code suggestions before posting to GitHub."""

import ast


def validate_suggestion(suggestion: str | None, filename: str) -> str | None:
    """Validate a code suggestion and return it if valid, None if invalid.

    Args:
        suggestion: The code suggestion to validate.
        filename: The filename to determine language-specific validation.

    Returns:
        The suggestion if valid, None if invalid.
    """
    if suggestion is None:
        return None

    # Check for empty or whitespace-only
    if not suggestion.strip():
        return None

    # Check for mixed indentation (tabs and spaces)
    if _has_mixed_indentation(suggestion):
        return None

    # For Python files, validate syntax
    if _is_python_file(filename) and not _is_valid_python(suggestion):
        return None

    return suggestion


def _is_python_file(filename: str) -> bool:
    """Check if file is a Python file."""
    return filename.endswith((".py", ".pyi"))


def _has_mixed_indentation(code: str) -> bool:
    """Check if code has mixed tabs and spaces for indentation."""
    lines = code.split("\n")
    has_tab_indent = False
    has_space_indent = False

    for line in lines:
        if not line or not line[0].isspace():
            continue
        # Check leading whitespace
        leading = len(line) - len(line.lstrip())
        leading_chars = line[:leading]
        if "\t" in leading_chars:
            has_tab_indent = True
        if " " in leading_chars:
            has_space_indent = True

    return has_tab_indent and has_space_indent


def _is_valid_python(code: str) -> bool:
    """Check if code is syntactically valid Python.

    Handles both statements and expressions, with or without indentation.
    Also handles partial code like loop/function headers without bodies.
    """
    dedented = _dedent(code)

    # Try parsing as-is
    try:
        ast.parse(dedented)
        return True
    except SyntaxError:
        pass

    # If code ends with colon, it might be a header (for, if, def, etc.)
    # Try adding 'pass' as placeholder body
    stripped = dedented.rstrip()
    if stripped.endswith(":"):
        try:
            ast.parse(stripped + "\n    pass")
            return True
        except SyntaxError:
            pass

    return False


def _dedent(code: str) -> str:
    """Remove common leading whitespace from all lines."""
    lines = code.split("\n")
    if not lines:
        return code

    # Find minimum indentation (ignoring empty lines)
    min_indent = float("inf")
    for line in lines:
        stripped = line.lstrip()
        if stripped:  # Non-empty line
            indent = len(line) - len(stripped)
            min_indent = min(min_indent, indent)

    if min_indent == float("inf") or min_indent == 0:
        return code

    # Remove the common prefix
    return "\n".join(line[int(min_indent):] if line.strip() else line for line in lines)
