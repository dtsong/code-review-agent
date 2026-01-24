"""Tests for the evaluation framework."""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, patch

from evals.scoring import (
    calculate_metrics,
    count_true_positives,
    confidence_error,
    EvalResult,
    EvalMetrics,
)
from evals.runner import load_eval_suite


class TestScoring:
    """Test evaluation scoring functionality."""

    def test_count_true_positives_exact_match(self):
        """Test counting true positives with exact matches."""
        predicted = [
            {
                "file": "test.py",
                "line_range": [10, 15],
                "severity": "high",
                "category": "security",
                "description": "SQL injection vulnerability"
            }
        ]

        expected = [
            {
                "file": "test.py",
                "line_range": [10, 15],
                "severity": "high",
                "category": "security",
                "description_contains": "sql injection"
            }
        ]

        result = count_true_positives(predicted, expected)
        assert result == 1

    def test_count_true_positives_overlapping_ranges(self):
        """Test counting true positives with overlapping line ranges."""
        predicted = [
            {
                "file": "test.py",
                "line_range": [12, 18],
                "severity": "medium",
                "category": "security"
            }
        ]

        expected = [
            {
                "file": "test.py",
                "line_range": [10, 15],
                "severity": "high",  # Different severity but close enough
                "category": "security"
            }
        ]

        result = count_true_positives(predicted, expected)
        assert result == 1

    def test_count_true_positives_no_match(self):
        """Test counting when no issues match."""
        predicted = [
            {
                "file": "test.py",
                "line_range": [1, 5],
                "category": "style"
            }
        ]

        expected = [
            {
                "file": "other.py",
                "line_range": [10, 15],
                "category": "security"
            }
        ]

        result = count_true_positives(predicted, expected)
        assert result == 0

    def test_confidence_error_within_range(self):
        """Test confidence error when prediction is within expected range."""
        error = confidence_error(0.75, [0.7, 0.8])
        assert error == 0.0

    def test_confidence_error_outside_range(self):
        """Test confidence error when prediction is outside expected range."""
        error = confidence_error(0.9, [0.7, 0.8])
        assert abs(error - 0.1) < 1e-10  # Distance to closest boundary (0.8)

        error = confidence_error(0.6, [0.7, 0.8])
        assert abs(error - 0.1) < 1e-10  # Distance to closest boundary (0.7)

    def test_calculate_metrics_perfect_score(self):
        """Test metrics calculation with perfect prediction."""
        result = EvalResult(
            suite_name="test",
            case_results=[
                {
                    "success": True,
                    "predicted_issues": [{"category": "security"}],
                    "expected_issues": [{"category": "security"}],
                    "predicted_confidence": 0.8,
                    "expected_confidence_range": [0.7, 0.9]
                }
            ],
            total_cost_usd=0.01,
            duration_seconds=1.0
        )

        metrics = calculate_metrics(result)

        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1 == 1.0
        assert metrics.confidence_mae == 0.0
        assert metrics.success_rate == 1.0

    def test_calculate_metrics_with_failures(self):
        """Test metrics calculation with some failed cases."""
        result = EvalResult(
            suite_name="test",
            case_results=[
                {
                    "success": True,
                    "predicted_issues": [{"category": "security"}],
                    "expected_issues": [{"category": "security"}],
                    "predicted_confidence": 0.8,
                    "expected_confidence_range": [0.7, 0.9]
                },
                {
                    "success": False,
                    "predicted_issues": [],
                    "expected_issues": [{"category": "style"}],
                    "predicted_confidence": 0.0,
                    "expected_confidence_range": [0.5, 0.8],
                    "error": "API timeout"
                }
            ],
            total_cost_usd=0.02,
            duration_seconds=2.0
        )

        metrics = calculate_metrics(result)

        assert metrics.success_rate == 0.5
        # Only successful cases contribute to other metrics
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0


class TestRunner:
    """Test evaluation runner functionality."""

    def test_load_eval_suite(self):
        """Test loading evaluation suite from YAML files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir)

            # Create test case file
            case_file = suite_path / "test_case.yaml"
            case_data = {
                "name": "Test Case",
                "diff_file": "test.patch",
                "expected_issues": [{"severity": "high"}],
                "expected_confidence": [0.8, 1.0]
            }

            with open(case_file, 'w') as f:
                yaml.dump(case_data, f)

            suite = load_eval_suite(suite_path)

            assert suite.suite_name == suite_path.name
            assert len(suite.cases) == 1
            assert suite.cases[0]["name"] == "Test Case"

    def test_load_eval_suite_no_files(self):
        """Test error when no YAML files found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir)

            with pytest.raises(ValueError, match="No YAML case files found"):
                load_eval_suite(suite_path)

    @patch('pr_review_agent.review.llm_reviewer.LLMReviewer')
    @patch('pr_review_agent.config.load_config')
    def test_run_evaluation_success(self, mock_load_config, mock_reviewer_class):
        """Test successful evaluation run."""
        from evals.runner import run_evaluation
        from evals.scoring import EvalSuite

        # Mock configuration
        mock_config = Mock()
        mock_load_config.return_value = mock_config

        # Mock reviewer
        mock_reviewer = Mock()
        mock_review_result = Mock()
        mock_review_result.issues = [{"category": "security"}]
        mock_review_result.confidence = 0.8
        mock_review_result.tokens_used = 100
        mock_review_result.cost_usd = 0.001

        mock_reviewer.review.return_value = mock_review_result
        mock_reviewer_class.return_value = mock_reviewer

        # Create test suite
        suite = EvalSuite(
            suite_name="test",
            cases=[
                {
                    "name": "Test Case",
                    "diff_file": "test.patch",
                    "expected_issues": [{"category": "security"}],
                    "expected_confidence": [0.7, 0.9]
                }
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock diff file
            diff_path = Path(temp_dir) / "evals" / "diffs" / "test.patch"
            diff_path.parent.mkdir(parents=True)
            diff_path.write_text("mock diff content")

            # Change to temp directory
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)

                result = run_evaluation(suite, "fake-api-key", verbose=False)

                assert result.suite_name == "test"
                assert len(result.case_results) == 1
                assert result.case_results[0]["success"] is True
                assert result.total_cost_usd == 0.001

            finally:
                os.chdir(original_cwd)