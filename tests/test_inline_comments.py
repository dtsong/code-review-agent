"""Tests for inline comment support."""

from unittest.mock import MagicMock, patch

from pr_review_agent.output.github_comment import build_review_comments
from pr_review_agent.review.llm_reviewer import (
    InlineComment,
    LLMReviewer,
    ReviewIssue,
)


def test_inline_comment_dataclass():
    """InlineComment can be instantiated."""
    ic = InlineComment(
        file="src/main.py",
        start_line=42,
        end_line=None,
        body="Issue description",
        suggestion=None,
    )
    assert ic.file == "src/main.py"
    assert ic.start_line == 42


def test_review_issue_has_new_fields():
    """ReviewIssue includes start_line, end_line, code_suggestion."""
    issue = ReviewIssue(
        severity="major",
        category="logic",
        file="test.py",
        line=10,
        description="Bug",
        suggestion="Fix it",
        start_line=10,
        end_line=12,
        code_suggestion="fixed_code()",
    )
    assert issue.start_line == 10
    assert issue.end_line == 12
    assert issue.code_suggestion == "fixed_code()"


def test_build_review_comments_single_line():
    """Single-line comment formatted correctly."""
    comments = build_review_comments([
        InlineComment(
            file="src/main.py",
            start_line=42,
            end_line=None,
            body="**MAJOR** (logic): Null check missing",
            suggestion=None,
        )
    ])

    assert len(comments) == 1
    assert comments[0]["path"] == "src/main.py"
    assert comments[0]["line"] == 42
    assert "Null check missing" in comments[0]["body"]
    assert "start_line" not in comments[0]


def test_build_review_comments_multi_line():
    """Multi-line comment includes start_line."""
    comments = build_review_comments([
        InlineComment(
            file="src/handler.py",
            start_line=10,
            end_line=15,
            body="**MINOR** (style): Consider refactoring",
            suggestion=None,
        )
    ])

    assert comments[0]["line"] == 15
    assert comments[0]["start_line"] == 10


def test_build_review_comments_with_code_suggestion():
    """Code suggestion added as suggestion block."""
    comments = build_review_comments([
        InlineComment(
            file="src/utils.py",
            start_line=5,
            end_line=None,
            body="**SUGGESTION** (style): Use f-string",
            suggestion='name = f"hello {user}"',
        )
    ])

    assert "```suggestion" in comments[0]["body"]
    assert 'name = f"hello {user}"' in comments[0]["body"]


def test_build_review_comments_empty_list():
    """Empty inline comments returns empty list."""
    assert build_review_comments([]) == []


@patch("pr_review_agent.review.llm_reviewer.Anthropic")
def test_reviewer_produces_inline_comments(mock_anthropic_class):
    """LLM reviewer builds inline comments from issue data."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="""{
        "summary": "Review summary",
        "issues": [
            {
                "severity": "major",
                "category": "security",
                "file": "src/auth.py",
                "start_line": 25,
                "end_line": 30,
                "description": "SQL injection vulnerability",
                "suggestion": "Use parameterized queries",
                "code_suggestion": "cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"
            },
            {
                "severity": "minor",
                "category": "style",
                "file": "src/utils.py",
                "start_line": 10,
                "end_line": null,
                "description": "Unused variable",
                "suggestion": "Remove unused variable",
                "code_suggestion": null
            }
        ],
        "strengths": [],
        "concerns": [],
        "questions": []
    }""")]
    mock_response.usage = MagicMock(input_tokens=200, output_tokens=100)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client

    from pr_review_agent.config import Config

    reviewer = LLMReviewer("fake-key")
    result = reviewer.review(
        diff="+ code",
        pr_description="Test",
        model="claude-sonnet-4-20250514",
        config=Config(),
    )

    assert len(result.inline_comments) == 2

    # First comment: multi-line with code suggestion
    ic1 = result.inline_comments[0]
    assert ic1.file == "src/auth.py"
    assert ic1.start_line == 25
    assert ic1.end_line == 30
    assert "SQL injection" in ic1.body
    assert ic1.suggestion is not None

    # Second comment: single-line without code suggestion
    ic2 = result.inline_comments[1]
    assert ic2.file == "src/utils.py"
    assert ic2.start_line == 10
    assert ic2.end_line is None
    assert ic2.suggestion is None


@patch("pr_review_agent.review.llm_reviewer.Anthropic")
def test_reviewer_backward_compat_line_field(mock_anthropic_class):
    """Issues with 'line' field (no start_line) still work."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="""{
        "summary": "OK",
        "issues": [
            {
                "severity": "minor",
                "category": "style",
                "file": "test.py",
                "line": 5,
                "description": "Minor issue",
                "suggestion": null
            }
        ],
        "strengths": [],
        "concerns": [],
        "questions": []
    }""")]
    mock_response.usage = MagicMock(input_tokens=50, output_tokens=30)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client

    from pr_review_agent.config import Config

    reviewer = LLMReviewer("fake-key")
    result = reviewer.review(
        diff="+ x",
        pr_description="Test",
        model="claude-sonnet-4-20250514",
        config=Config(),
    )

    assert len(result.inline_comments) == 1
    assert result.inline_comments[0].start_line == 5
    assert result.issues[0].line == 5
    assert result.issues[0].start_line == 5
