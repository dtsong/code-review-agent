"""Tests for suggested fixes (issue #12)."""

from unittest.mock import MagicMock, patch

from pr_review_agent.output.github_comment import build_review_comments
from pr_review_agent.review.llm_reviewer import InlineComment, LLMReviewer


@patch("pr_review_agent.review.llm_reviewer.Anthropic")
def test_code_suggestion_included_for_critical(mock_anthropic_class):
    """Critical issues retain their code suggestions."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="""{
        "summary": "Security issue found",
        "issues": [
            {
                "severity": "critical",
                "category": "security",
                "file": "src/db.py",
                "start_line": 15,
                "end_line": 15,
                "description": "SQL injection vulnerability",
                "suggestion": "Use parameterized queries",
                "code_suggestion": "cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"
            }
        ],
        "strengths": [],
        "concerns": [],
        "questions": []
    }""")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client

    from pr_review_agent.config import Config

    reviewer = LLMReviewer("fake-key")
    result = reviewer.review(
        diff="+ cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')",
        pr_description="DB query",
        model="claude-sonnet-4-20250514",
        config=Config(),
    )

    assert len(result.inline_comments) == 1
    assert result.inline_comments[0].suggestion is not None
    assert "parameterized" not in result.inline_comments[0].suggestion
    assert "cursor.execute" in result.inline_comments[0].suggestion


@patch("pr_review_agent.review.llm_reviewer.Anthropic")
def test_code_suggestion_included_for_major(mock_anthropic_class):
    """Major issues retain their code suggestions."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="""{
        "summary": "Bug found",
        "issues": [
            {
                "severity": "major",
                "category": "logic",
                "file": "src/calc.py",
                "start_line": 8,
                "end_line": 8,
                "description": "Off-by-one error",
                "suggestion": "Use < instead of <=",
                "code_suggestion": "    for i in range(len(items)):"
            }
        ],
        "strengths": [],
        "concerns": [],
        "questions": []
    }""")]
    mock_response.usage = MagicMock(input_tokens=80, output_tokens=40)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client

    from pr_review_agent.config import Config

    reviewer = LLMReviewer("fake-key")
    result = reviewer.review(
        diff="+ for i in range(len(items) + 1):",
        pr_description="Loop fix",
        model="claude-sonnet-4-20250514",
        config=Config(),
    )

    assert result.inline_comments[0].suggestion is not None


@patch("pr_review_agent.review.llm_reviewer.Anthropic")
def test_code_suggestion_stripped_for_minor(mock_anthropic_class):
    """Minor issues have code suggestions filtered out."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="""{
        "summary": "Style nit",
        "issues": [
            {
                "severity": "minor",
                "category": "style",
                "file": "src/utils.py",
                "start_line": 3,
                "end_line": 3,
                "description": "Could use f-string",
                "suggestion": "Use f-string for readability",
                "code_suggestion": "    name = f'hello {user}'"
            }
        ],
        "strengths": [],
        "concerns": [],
        "questions": []
    }""")]
    mock_response.usage = MagicMock(input_tokens=60, output_tokens=30)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client

    from pr_review_agent.config import Config

    reviewer = LLMReviewer("fake-key")
    result = reviewer.review(
        diff="+ name = 'hello ' + user",
        pr_description="String format",
        model="claude-sonnet-4-20250514",
        config=Config(),
    )

    # Inline comment exists but code suggestion is filtered
    assert len(result.inline_comments) == 1
    assert result.inline_comments[0].suggestion is None
    # The raw issue still has the code_suggestion for reference
    assert result.issues[0].code_suggestion is not None


@patch("pr_review_agent.review.llm_reviewer.Anthropic")
def test_code_suggestion_stripped_for_suggestion_severity(mock_anthropic_class):
    """Suggestion-severity issues have code suggestions filtered out."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="""{
        "summary": "Nitpick",
        "issues": [
            {
                "severity": "suggestion",
                "category": "style",
                "file": "src/app.py",
                "start_line": 20,
                "end_line": 20,
                "description": "Consider using a constant",
                "suggestion": "Extract to constant",
                "code_suggestion": "MAX_RETRIES = 3"
            }
        ],
        "strengths": [],
        "concerns": [],
        "questions": []
    }""")]
    mock_response.usage = MagicMock(input_tokens=50, output_tokens=25)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client

    from pr_review_agent.config import Config

    reviewer = LLMReviewer("fake-key")
    result = reviewer.review(
        diff="+ retries = 3",
        pr_description="Config",
        model="claude-sonnet-4-20250514",
        config=Config(),
    )

    assert result.inline_comments[0].suggestion is None


@patch("pr_review_agent.review.llm_reviewer.Anthropic")
def test_mixed_severities_filter_correctly(mock_anthropic_class):
    """Mixed critical/minor issues: only critical gets code suggestion."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="""{
        "summary": "Mixed review",
        "issues": [
            {
                "severity": "critical",
                "category": "security",
                "file": "src/auth.py",
                "start_line": 10,
                "end_line": 10,
                "description": "Hardcoded secret",
                "suggestion": "Use environment variable",
                "code_suggestion": "    secret = os.environ['API_SECRET']"
            },
            {
                "severity": "minor",
                "category": "style",
                "file": "src/auth.py",
                "start_line": 15,
                "end_line": 15,
                "description": "Verbose variable name",
                "suggestion": "Shorten name",
                "code_suggestion": "    key = get_key()"
            }
        ],
        "strengths": [],
        "concerns": [],
        "questions": []
    }""")]
    mock_response.usage = MagicMock(input_tokens=120, output_tokens=60)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client

    from pr_review_agent.config import Config

    reviewer = LLMReviewer("fake-key")
    result = reviewer.review(
        diff="+ secret = 'hardcoded'\n+ very_long_variable_name = get_key()",
        pr_description="Auth",
        model="claude-sonnet-4-20250514",
        config=Config(),
    )

    assert len(result.inline_comments) == 2
    # Critical: keeps suggestion
    assert result.inline_comments[0].suggestion is not None
    # Minor: filtered out
    assert result.inline_comments[1].suggestion is None


def test_suggestion_block_rendered_in_github_comment():
    """Code suggestion renders as GitHub suggestion block in comment body."""
    comments = build_review_comments([
        InlineComment(
            file="src/db.py",
            start_line=15,
            end_line=15,
            body="**CRITICAL** (security): SQL injection",
            suggestion="cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
        )
    ])

    body = comments[0]["body"]
    assert "```suggestion" in body
    assert "cursor.execute" in body
    assert body.endswith("```")


def test_no_suggestion_block_when_suggestion_is_none():
    """No suggestion block rendered when suggestion is None."""
    comments = build_review_comments([
        InlineComment(
            file="src/utils.py",
            start_line=3,
            end_line=None,
            body="**MINOR** (style): Could use f-string",
            suggestion=None,
        )
    ])

    assert "```suggestion" not in comments[0]["body"]


def test_multiline_suggestion_block():
    """Multi-line code suggestion renders correctly."""
    multiline_fix = (
        "    x = get_data()\n"
        "    if x is None:\n"
        "        return None\n"
        "    return process(x)"
    )
    comments = build_review_comments([
        InlineComment(
            file="src/handler.py",
            start_line=10,
            end_line=12,
            body="**MAJOR** (logic): Missing null check",
            suggestion=multiline_fix,
        )
    ])

    body = comments[0]["body"]
    assert "```suggestion" in body
    assert "if x is None:" in body
    assert "return None" in body
    assert comments[0]["start_line"] == 10
    assert comments[0]["line"] == 12
