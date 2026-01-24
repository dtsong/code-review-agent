"""Tests for issue fingerprinting."""

from pr_review_agent.review.fingerprint import (
    fingerprint_issue,
    normalize_description,
)
from pr_review_agent.review.llm_reviewer import ReviewIssue


class TestNormalizeDescription:
    """Test description normalization for consistent fingerprinting."""

    def test_lowercases(self):
        assert normalize_description("SQL Injection HERE") == normalize_description(
            "sql injection here"
        )

    def test_removes_stop_words(self):
        result = normalize_description("this is a SQL injection vulnerability in the code")
        assert "this" not in result
        assert "is" not in result
        assert "the" not in result
        assert "sql" in result
        assert "injection" in result

    def test_strips_whitespace(self):
        assert normalize_description("  sql  injection  ") == normalize_description(
            "sql injection"
        )

    def test_empty_string(self):
        assert normalize_description("") == ""

    def test_only_stop_words(self):
        result = normalize_description("the a an is are")
        assert result == ""

    def test_punctuation_removed(self):
        assert normalize_description("sql-injection!") == normalize_description(
            "sql injection"
        )


class TestFingerprintIssue:
    """Test fingerprint generation for review issues."""

    def test_same_issue_same_fingerprint(self):
        """Identical issues produce identical fingerprints."""
        issue = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion="Use parameterized queries",
        )

        fp1 = fingerprint_issue(issue)
        fp2 = fingerprint_issue(issue)

        assert fp1 == fp2

    def test_different_files_different_fingerprint(self):
        """Same issue in different files produces different fingerprints."""
        issue1 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )
        issue2 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/orders.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )

        assert fingerprint_issue(issue1) != fingerprint_issue(issue2)

    def test_different_category_different_fingerprint(self):
        """Same file but different category produces different fingerprints."""
        issue1 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )
        issue2 = ReviewIssue(
            severity="high",
            category="performance",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )

        assert fingerprint_issue(issue1) != fingerprint_issue(issue2)

    def test_different_severity_different_fingerprint(self):
        """Same issue with different severity produces different fingerprints."""
        issue1 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )
        issue2 = ReviewIssue(
            severity="low",
            category="security",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )

        assert fingerprint_issue(issue1) != fingerprint_issue(issue2)

    def test_minor_line_change_same_fingerprint(self):
        """Small line number changes still produce the same fingerprint.

        This tests that we use a line range bucket rather than exact line numbers,
        so that the same logical issue that shifted a few lines still matches.
        """
        issue1 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )
        issue2 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=44,  # Shifted 2 lines
            description="SQL injection vulnerability",
            suggestion=None,
        )

        assert fingerprint_issue(issue1) == fingerprint_issue(issue2)

    def test_large_line_change_different_fingerprint(self):
        """Large line shifts produce different fingerprints."""
        issue1 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )
        issue2 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=200,  # Very different location
            description="SQL injection vulnerability",
            suggestion=None,
        )

        assert fingerprint_issue(issue1) != fingerprint_issue(issue2)

    def test_description_variations_same_fingerprint(self):
        """Description wording variations produce the same fingerprint."""
        issue1 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="This is a SQL injection vulnerability in the query",
            suggestion=None,
        )
        issue2 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="A SQL injection vulnerability found in the query",
            suggestion=None,
        )

        assert fingerprint_issue(issue1) == fingerprint_issue(issue2)

    def test_completely_different_description_different_fingerprint(self):
        """Completely different descriptions produce different fingerprints."""
        issue1 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="SQL injection vulnerability",
            suggestion=None,
        )
        issue2 = ReviewIssue(
            severity="high",
            category="security",
            file="src/api/users.py",
            line=42,
            description="Cross-site scripting XSS attack",
            suggestion=None,
        )

        assert fingerprint_issue(issue1) != fingerprint_issue(issue2)

    def test_fingerprint_is_hex_string(self):
        """Fingerprint should be a hex-encoded hash string."""
        issue = ReviewIssue(
            severity="high",
            category="security",
            file="test.py",
            line=1,
            description="test issue",
            suggestion=None,
        )

        fp = fingerprint_issue(issue)
        assert isinstance(fp, str)
        assert len(fp) == 16  # 8 bytes = 16 hex chars
        assert all(c in "0123456789abcdef" for c in fp)

    def test_null_line_handled(self):
        """Issues without line numbers should still fingerprint."""
        issue = ReviewIssue(
            severity="high",
            category="security",
            file="test.py",
            line=None,
            description="SQL injection",
            suggestion=None,
        )

        fp = fingerprint_issue(issue)
        assert isinstance(fp, str)
        assert len(fp) == 16

    def test_start_end_line_range_used(self):
        """When start_line and end_line are set, the range midpoint is used."""
        issue = ReviewIssue(
            severity="high",
            category="security",
            file="test.py",
            line=10,
            description="SQL injection",
            suggestion=None,
            start_line=10,
            end_line=20,
        )

        fp = fingerprint_issue(issue)
        assert isinstance(fp, str)
        assert len(fp) == 16
