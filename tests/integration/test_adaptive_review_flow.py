"""Integration tests for the full adaptive review flow."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

from pr_review_agent.analysis.pre_analyzer import analyze_pr, PRType, RiskLevel
from pr_review_agent.execution.retry_handler import retry_with_adaptation


@dataclass
class MockPRData:
    """Mock PR data for testing."""

    number: int
    repo: str
    owner: str
    author: str
    title: str
    description: str
    files_changed: list
    lines_changed: int
    lines_added: int
    lines_removed: int
    diff: str
    base_branch: str = "main"
    head_branch: str = "feature"
    url: str = "https://github.com/owner/repo/pull/1"


@pytest.fixture
def small_feature_pr():
    return MockPRData(
        number=1,
        repo="owner/repo",
        owner="owner",
        author="alice",
        title="feat: add helper function",
        description="Adds a utility function for string formatting",
        files_changed=["src/utils.py", "tests/test_utils.py"],
        lines_changed=45,
        lines_added=40,
        lines_removed=5,
        diff="+ def format_string(s): ...",
    )


@pytest.fixture
def large_security_pr():
    return MockPRData(
        number=2,
        repo="owner/repo",
        owner="owner",
        author="bob",
        title="security: update authentication flow",
        description="Patches authentication vulnerability",
        files_changed=["src/auth.py", "src/crypto.py", "src/session.py"],
        lines_changed=280,
        lines_added=200,
        lines_removed=80,
        diff="+ def validate_token(token): ...",
    )


@pytest.fixture
def test_only_pr():
    return MockPRData(
        number=3,
        repo="owner/repo",
        owner="owner",
        author="carol",
        title="test: add unit tests for utils",
        description="Improves test coverage",
        files_changed=["tests/test_utils.py", "tests/test_helpers.py"],
        lines_changed=150,
        lines_added=150,
        lines_removed=0,
        diff="+ def test_format_string(): ...",
    )


class TestPreAnalysisIntegration:
    """Test pre-analysis correctly categorizes different PR types."""

    def test_small_feature_pr_analysis(self, small_feature_pr):
        analysis = analyze_pr(small_feature_pr)

        assert analysis.pr_type == PRType.FEATURE
        assert analysis.complexity == "low"
        assert analysis.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
        assert "haiku" in analysis.suggested_model.lower()

    def test_security_pr_gets_high_risk(self, large_security_pr):
        analysis = analyze_pr(large_security_pr)

        assert analysis.pr_type == PRType.SECURITY
        assert analysis.risk_level == RiskLevel.CRITICAL
        assert "vulnerabilities" in analysis.focus_areas
        assert "sonnet" in analysis.suggested_model.lower()

    def test_test_pr_gets_low_risk(self, test_only_pr):
        analysis = analyze_pr(test_only_pr)

        assert analysis.pr_type == PRType.TEST
        assert analysis.risk_level == RiskLevel.LOW
        assert "security_scan" in analysis.skip_checks


class TestRetryIntegration:
    """Test retry handler integrates correctly with operations."""

    def test_successful_operation_no_retry(self):
        """Successful operations should not retry."""
        call_count = 0

        def operation(strategy):
            nonlocal call_count
            call_count += 1
            return {"result": "success", "model": strategy.model}

        result = retry_with_adaptation(
            operation=operation,
            base_model="claude-sonnet-4-20250514",
            max_attempts=3,
        )

        assert result["result"] == "success"
        assert call_count == 1

    @patch("time.sleep")
    def test_retry_adapts_on_failure(self, mock_sleep):
        """Strategy should adapt on failure."""
        import anthropic

        strategies_used = []

        mock_response = Mock()
        mock_response.status_code = 429

        def operation(strategy):
            strategies_used.append(strategy.model)
            if len(strategies_used) < 2:
                raise anthropic.RateLimitError("rate limit", response=mock_response, body={})
            return "success"

        result = retry_with_adaptation(
            operation=operation,
            base_model="claude-sonnet-4-20250514",
            max_attempts=3,
        )

        assert result == "success"
        assert len(strategies_used) == 2
        # Second attempt should use Haiku after rate limit
        assert "haiku" in strategies_used[1].lower()


class TestAdaptiveFlowIntegration:
    """Test the full adaptive review flow."""

    def test_small_pr_uses_haiku(self, small_feature_pr):
        # Analyze and verify Haiku is selected
        analysis = analyze_pr(small_feature_pr)

        assert "haiku" in analysis.suggested_model.lower()

    def test_security_pr_uses_sonnet(self, large_security_pr):
        # Analyze and verify Sonnet is selected
        analysis = analyze_pr(large_security_pr)

        assert "sonnet" in analysis.suggested_model.lower()

    def test_analysis_determines_checks_to_skip(self, test_only_pr):
        analysis = analyze_pr(test_only_pr)

        # Test-only PRs should skip security scan
        assert "security_scan" in analysis.skip_checks
        assert "llm_review" in analysis.suggested_checks


class TestEndToEndFlow:
    """End-to-end tests simulating real usage."""

    def test_large_pr_flagged_as_high_complexity(self):
        """Test that large PRs are flagged correctly."""
        large_pr = MockPRData(
            number=99,
            repo="owner/repo",
            owner="owner",
            author="dave",
            title="feat: massive refactor",
            description="",
            files_changed=[f"file{i}.py" for i in range(30)],
            lines_changed=800,
            lines_added=600,
            lines_removed=200,
            diff="..." * 1000,
        )

        # Analysis should flag as high complexity
        analysis = analyze_pr(large_pr)
        assert analysis.complexity == "high"

        # Should use Sonnet for high complexity
        assert "sonnet" in analysis.suggested_model.lower()

    def test_full_analysis_pipeline(self, small_feature_pr):
        """Test complete analysis pipeline."""
        # 1. Pre-analysis
        analysis = analyze_pr(small_feature_pr)
        assert analysis.pr_type == PRType.FEATURE
        assert analysis.complexity == "low"

        # 2. Check gates are suggested
        assert "size_gate" in analysis.suggested_checks
        assert "lint_gate" in analysis.suggested_checks
        assert "llm_review" in analysis.suggested_checks

        # 3. Model selection based on analysis
        assert "haiku" in analysis.suggested_model.lower()

        # 4. Focus areas should be relevant
        assert "logic_correctness" in analysis.focus_areas
