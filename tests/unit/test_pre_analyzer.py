"""Unit tests for pre-analyzer."""

import pytest
from unittest.mock import Mock

from pr_review_agent.analysis.pre_analyzer import (
    PRType,
    RiskLevel,
    PRAnalysis,
    categorize_files,
    infer_pr_type,
    assess_risk,
    assess_complexity,
    get_focus_areas,
    get_check_recommendations,
    analyze_pr,
)


class TestCategorizeFiles:
    """Test file categorization."""

    def test_categorizes_test_files(self):
        files = ["tests/test_main.py", "src/main.py"]
        result = categorize_files(files)

        assert "tests/test_main.py" in result["test"]
        assert "src/main.py" in result["core"]

    def test_categorizes_spec_files_as_test(self):
        files = ["spec/feature_spec.py", "tests/unit_spec.py"]
        result = categorize_files(files)

        assert len(result["test"]) == 2

    def test_categorizes_config_files(self):
        files = ["config.yaml", ".env", "settings.json", "pyproject.toml", "config.ini"]
        result = categorize_files(files)

        assert len(result["config"]) == 5

    def test_categorizes_security_files(self):
        files = ["src/auth.py", "lib/crypto.py", "utils/password.py", "token_handler.py"]
        result = categorize_files(files)

        assert len(result["security"]) == 4

    def test_categorizes_docs(self):
        files = ["README.md", "docs/guide.rst", "CHANGELOG.txt"]
        result = categorize_files(files)

        assert len(result["docs"]) == 3

    def test_categorizes_api_files(self):
        files = ["src/api/routes.py", "endpoints/users.py", "handlers/request.py"]
        result = categorize_files(files)

        assert len(result["api"]) == 3

    def test_categorizes_ui_files(self):
        files = ["components/Button.tsx", "pages/Home.vue", "views/Dashboard.js"]
        result = categorize_files(files)

        assert len(result["ui"]) == 3

    def test_empty_files_list(self):
        result = categorize_files([])

        assert all(len(v) == 0 for v in result.values())


class TestInferPRType:
    """Test PR type inference."""

    def test_bugfix_from_title(self):
        assert infer_pr_type("fix: resolve login issue", "", {}) == PRType.BUGFIX
        assert infer_pr_type("bug: null pointer exception", "", {}) == PRType.BUGFIX
        assert infer_pr_type("patch: memory leak", "", {}) == PRType.BUGFIX
        assert infer_pr_type("Issue #123 fix", "", {}) == PRType.BUGFIX

    def test_feature_from_title(self):
        assert infer_pr_type("feat: add dark mode", "", {}) == PRType.FEATURE
        assert infer_pr_type("implement user dashboard", "", {}) == PRType.FEATURE
        assert infer_pr_type("Add new payment method", "", {}) == PRType.FEATURE
        assert infer_pr_type("New feature: notifications", "", {}) == PRType.FEATURE

    def test_refactor_from_title(self):
        assert infer_pr_type("refactor: cleanup auth module", "", {}) == PRType.REFACTOR
        assert infer_pr_type("Reorganize project structure", "", {}) == PRType.REFACTOR

    def test_security_from_title(self):
        assert infer_pr_type("security: patch CVE-2024-1234", "", {}) == PRType.SECURITY
        assert infer_pr_type("Fix vulnerability in auth", "", {}) == PRType.SECURITY

    def test_test_from_title(self):
        assert infer_pr_type("test: add unit tests", "", {}) == PRType.TEST
        assert infer_pr_type("Improve coverage", "", {}) == PRType.TEST

    def test_docs_from_title(self):
        assert infer_pr_type("doc: update README", "", {}) == PRType.DOCS
        assert infer_pr_type("Update comments", "", {}) == PRType.DOCS

    def test_dependency_from_title(self):
        assert infer_pr_type("dep: upgrade lodash", "", {}) == PRType.DEPENDENCY
        assert infer_pr_type("Bump version to 2.0", "", {}) == PRType.DEPENDENCY
        assert infer_pr_type("Upgrade to latest version", "", {}) == PRType.DEPENDENCY

    def test_test_from_file_patterns(self):
        file_patterns = {
            "test": ["test_a.py", "test_b.py", "test_c.py"],
            "core": ["main.py"],
            "config": [],
            "docs": [],
            "security": [],
            "api": [],
            "ui": [],
        }
        assert infer_pr_type("update tests", "", file_patterns) == PRType.TEST

    def test_docs_from_file_patterns(self):
        file_patterns = {
            "docs": ["README.md", "CONTRIBUTING.md"],
            "core": [],
            "test": [],
            "config": [],
            "security": [],
            "api": [],
            "ui": [],
        }
        assert infer_pr_type("update documentation", "", file_patterns) == PRType.DOCS

    def test_security_from_file_patterns(self):
        file_patterns = {
            "security": ["auth.py"],
            "core": [],
            "test": [],
            "config": [],
            "docs": [],
            "api": [],
            "ui": [],
        }
        # Security files should flag as security PR
        assert infer_pr_type("some update", "", file_patterns) == PRType.SECURITY

    def test_config_from_file_patterns(self):
        file_patterns = {
            "config": ["config.yaml", ".env"],
            "core": [],
            "test": [],
            "docs": [],
            "security": [],
            "api": [],
            "ui": [],
        }
        assert infer_pr_type("update config", "", file_patterns) == PRType.CONFIG

    def test_defaults_to_feature(self):
        file_patterns = {
            "core": ["main.py"],
            "test": [],
            "config": [],
            "docs": [],
            "security": [],
            "api": [],
            "ui": [],
        }
        assert infer_pr_type("some changes", "", file_patterns) == PRType.FEATURE


class TestAssessRisk:
    """Test risk assessment."""

    def test_critical_for_security_files(self):
        file_patterns = {
            "security": ["auth.py"],
            "api": [],
            "core": [],
            "test": [],
            "docs": [],
            "config": [],
            "ui": [],
        }
        pr = Mock(lines_changed=10)

        assert assess_risk(pr, file_patterns) == RiskLevel.CRITICAL

    def test_high_for_large_prs(self):
        file_patterns = {
            "security": [],
            "api": [],
            "core": ["a.py"],
            "test": [],
            "docs": [],
            "config": [],
            "ui": [],
        }
        pr = Mock(lines_changed=400)

        assert assess_risk(pr, file_patterns) == RiskLevel.HIGH

    def test_high_for_many_api_changes(self):
        file_patterns = {
            "security": [],
            "api": ["a.py", "b.py", "c.py", "d.py"],
            "core": [],
            "test": [],
            "docs": [],
            "config": [],
            "ui": [],
        }
        pr = Mock(lines_changed=50)

        assert assess_risk(pr, file_patterns) == RiskLevel.HIGH

    def test_medium_for_core_changes(self):
        file_patterns = {
            "security": [],
            "api": [],
            "core": ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            "test": [],
            "docs": [],
            "config": [],
            "ui": [],
        }
        pr = Mock(lines_changed=100)

        assert assess_risk(pr, file_patterns) == RiskLevel.MEDIUM

    def test_low_for_test_only(self):
        file_patterns = {
            "test": ["test_a.py", "test_b.py"],
            "core": [],
            "security": [],
            "api": [],
            "docs": [],
            "config": [],
            "ui": [],
        }
        pr = Mock(lines_changed=50)

        assert assess_risk(pr, file_patterns) == RiskLevel.LOW

    def test_low_for_docs_only(self):
        file_patterns = {
            "docs": ["README.md", "CONTRIBUTING.md"],
            "core": [],
            "test": [],
            "security": [],
            "api": [],
            "config": [],
            "ui": [],
        }
        pr = Mock(lines_changed=50)

        assert assess_risk(pr, file_patterns) == RiskLevel.LOW


class TestAssessComplexity:
    """Test complexity assessment."""

    def test_high_complexity_large_lines(self):
        pr = Mock(lines_changed=250, files_changed=3)
        assert assess_complexity(pr) == "high"

    def test_high_complexity_many_files(self):
        pr = Mock(lines_changed=50, files_changed=15)
        assert assess_complexity(pr) == "high"

    def test_medium_complexity(self):
        pr = Mock(lines_changed=75, files_changed=4)
        assert assess_complexity(pr) == "medium"

    def test_low_complexity(self):
        pr = Mock(lines_changed=30, files_changed=2)
        assert assess_complexity(pr) == "low"

    def test_boundary_high_complexity_lines(self):
        # Exactly at boundary
        pr = Mock(lines_changed=200, files_changed=3)
        assert assess_complexity(pr) == "high"

    def test_boundary_medium_complexity(self):
        # Exactly at boundary
        pr = Mock(lines_changed=50, files_changed=5)
        assert assess_complexity(pr) == "medium"


class TestGetFocusAreas:
    """Test focus area determination."""

    def test_feature_focus_areas(self):
        focus = get_focus_areas(PRType.FEATURE, RiskLevel.MEDIUM)
        assert "logic_correctness" in focus
        assert "test_coverage" in focus

    def test_bugfix_focus_areas(self):
        focus = get_focus_areas(PRType.BUGFIX, RiskLevel.MEDIUM)
        assert "root_cause" in focus
        assert "regression_risk" in focus

    def test_refactor_focus_areas(self):
        focus = get_focus_areas(PRType.REFACTOR, RiskLevel.MEDIUM)
        assert "behavior_preservation" in focus
        assert "code_quality" in focus

    def test_security_focus_areas(self):
        focus = get_focus_areas(PRType.SECURITY, RiskLevel.CRITICAL)
        assert "vulnerabilities" in focus
        assert "input_validation" in focus

    def test_high_risk_adds_security_focus(self):
        focus = get_focus_areas(PRType.FEATURE, RiskLevel.HIGH)
        assert "security_implications" in focus

    def test_critical_risk_adds_security_focus(self):
        focus = get_focus_areas(PRType.REFACTOR, RiskLevel.CRITICAL)
        assert "security_implications" in focus

    def test_low_risk_feature_no_security_focus(self):
        focus = get_focus_areas(PRType.FEATURE, RiskLevel.LOW)
        assert "security_implications" not in focus


class TestGetCheckRecommendations:
    """Test check recommendations."""

    def test_test_pr_skips_security_scan(self):
        suggested, skip = get_check_recommendations(PRType.TEST, RiskLevel.LOW)

        assert "security_scan" in skip
        assert "llm_review" in suggested

    def test_docs_pr_skips_security_scan(self):
        suggested, skip = get_check_recommendations(PRType.DOCS, RiskLevel.LOW)

        assert "security_scan" in skip
        assert "test_coverage" in skip

    def test_security_pr_runs_all_checks(self):
        suggested, skip = get_check_recommendations(PRType.SECURITY, RiskLevel.CRITICAL)

        assert len(skip) == 0
        assert "security_scan" in suggested

    def test_critical_risk_runs_all_checks(self):
        suggested, skip = get_check_recommendations(PRType.FEATURE, RiskLevel.CRITICAL)

        assert len(skip) == 0

    def test_default_skips_security_scan(self):
        suggested, skip = get_check_recommendations(PRType.FEATURE, RiskLevel.MEDIUM)

        assert "security_scan" in skip
        assert "llm_review" in suggested


class TestAnalyzePR:
    """Test full PR analysis."""

    def test_returns_complete_analysis(self):
        pr = Mock(
            title="feat: add user authentication",
            description="Implements OAuth2 login",
            files_changed=["src/auth.py", "tests/test_auth.py"],
            lines_changed=120,
        )

        analysis = analyze_pr(pr)

        assert isinstance(analysis, PRAnalysis)
        assert analysis.pr_type is not None
        assert analysis.risk_level is not None
        assert analysis.complexity in ["low", "medium", "high"]
        assert len(analysis.focus_areas) > 0
        assert analysis.suggested_model is not None

    def test_small_feature_uses_haiku(self):
        pr = Mock(
            title="feat: add helper function",
            description="Small utility",
            files_changed=["src/utils.py"],
            lines_changed=30,
        )

        analysis = analyze_pr(pr)

        assert "haiku" in analysis.suggested_model.lower()

    def test_security_pr_uses_sonnet(self):
        pr = Mock(
            title="security: fix auth vulnerability",
            description="Critical fix",
            files_changed=["src/auth.py"],
            lines_changed=50,
        )

        analysis = analyze_pr(pr)

        assert "sonnet" in analysis.suggested_model.lower()

    def test_high_complexity_uses_sonnet(self):
        pr = Mock(
            title="feat: major refactor",
            description="Large changes",
            files_changed=["src/a.py", "src/b.py"] + [f"src/f{i}.py" for i in range(10)],
            lines_changed=300,
        )

        analysis = analyze_pr(pr)

        assert "sonnet" in analysis.suggested_model.lower()

    def test_test_only_pr_analysis(self):
        pr = Mock(
            title="test: add unit tests",
            description="Improve coverage",
            files_changed=["tests/test_main.py", "tests/test_utils.py"],
            lines_changed=150,
        )

        analysis = analyze_pr(pr)

        assert analysis.pr_type == PRType.TEST
        assert analysis.risk_level == RiskLevel.LOW
        assert "security_scan" in analysis.skip_checks
