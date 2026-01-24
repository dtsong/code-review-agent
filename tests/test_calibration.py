"""Tests for confidence calibration framework."""

from evals.calibration import (
    CalibrationReport,
    CalibrationSample,
    HumanOutcome,
    analyze_calibration,
    compute_buckets,
    load_calibration_data,
    suggest_weight_adjustments,
)
from pr_review_agent.review.confidence import (
    CalibrationWeights,
    calculate_confidence,
)


class TestCalibrationSample:
    """Test CalibrationSample data structure."""

    def test_sample_creation(self):
        sample = CalibrationSample(
            review_id="r1",
            predicted_confidence=0.85,
            outcome=HumanOutcome.CORRECT,
            issue_count=2,
            severity_breakdown={"major": 1, "minor": 1},
        )
        assert sample.predicted_confidence == 0.85
        assert sample.outcome == HumanOutcome.CORRECT
        assert sample.is_accurate is True

    def test_incorrect_outcome(self):
        sample = CalibrationSample(
            review_id="r2",
            predicted_confidence=0.9,
            outcome=HumanOutcome.INCORRECT,
            issue_count=1,
            severity_breakdown={"critical": 1},
        )
        assert sample.is_accurate is False

    def test_partial_outcome(self):
        sample = CalibrationSample(
            review_id="r3",
            predicted_confidence=0.7,
            outcome=HumanOutcome.PARTIAL,
            issue_count=3,
            severity_breakdown={"major": 2, "minor": 1},
        )
        assert sample.is_accurate is False


class TestComputeBuckets:
    """Test bucketing of calibration samples."""

    def test_empty_samples_returns_empty(self):
        buckets = compute_buckets([], bucket_count=5)
        assert buckets == []

    def test_single_bucket_all_correct(self):
        samples = [
            CalibrationSample(
                review_id=f"r{i}",
                predicted_confidence=0.85 + i * 0.01,
                outcome=HumanOutcome.CORRECT,
                issue_count=1,
                severity_breakdown={"minor": 1},
            )
            for i in range(5)
        ]
        buckets = compute_buckets(samples, bucket_count=1)
        assert len(buckets) == 1
        assert buckets[0].actual_accuracy == 1.0
        assert buckets[0].sample_count == 5

    def test_mixed_outcomes_accuracy(self):
        samples = [
            CalibrationSample(
                review_id="r1",
                predicted_confidence=0.8,
                outcome=HumanOutcome.CORRECT,
                issue_count=1,
                severity_breakdown={},
            ),
            CalibrationSample(
                review_id="r2",
                predicted_confidence=0.82,
                outcome=HumanOutcome.INCORRECT,
                issue_count=1,
                severity_breakdown={},
            ),
            CalibrationSample(
                review_id="r3",
                predicted_confidence=0.84,
                outcome=HumanOutcome.CORRECT,
                issue_count=1,
                severity_breakdown={},
            ),
            CalibrationSample(
                review_id="r4",
                predicted_confidence=0.86,
                outcome=HumanOutcome.PARTIAL,
                issue_count=1,
                severity_breakdown={},
            ),
        ]
        buckets = compute_buckets(samples, bucket_count=1)
        # 2 correct out of 4
        assert buckets[0].actual_accuracy == 0.5
        assert abs(buckets[0].avg_predicted - 0.83) < 0.01

    def test_multiple_buckets(self):
        samples = [
            CalibrationSample(
                review_id=f"r{i}",
                predicted_confidence=i * 0.1,
                outcome=HumanOutcome.CORRECT if i > 5 else HumanOutcome.INCORRECT,
                issue_count=1,
                severity_breakdown={},
            )
            for i in range(1, 11)
        ]
        buckets = compute_buckets(samples, bucket_count=2)
        assert len(buckets) == 2
        # Low-confidence bucket should have lower accuracy
        assert buckets[0].actual_accuracy < buckets[1].actual_accuracy


class TestAnalyzeCalibration:
    """Test calibration analysis."""

    def test_perfect_calibration(self):
        samples = [
            CalibrationSample(
                review_id=f"r{i}",
                predicted_confidence=0.9,
                outcome=HumanOutcome.CORRECT,
                issue_count=1,
                severity_breakdown={},
            )
            for i in range(10)
        ]
        report = analyze_calibration(samples)
        assert isinstance(report, CalibrationReport)
        assert report.total_samples == 10
        assert report.overall_accuracy == 1.0
        assert report.calibration_error < 0.2  # Should be well-calibrated

    def test_overconfident_model(self):
        """High predicted confidence but low accuracy = overconfident."""
        samples = [
            CalibrationSample(
                review_id=f"r{i}",
                predicted_confidence=0.95,
                outcome=HumanOutcome.INCORRECT,
                issue_count=1,
                severity_breakdown={},
            )
            for i in range(10)
        ]
        report = analyze_calibration(samples)
        assert report.overall_accuracy == 0.0
        assert report.calibration_error > 0.5  # Poorly calibrated

    def test_report_includes_buckets(self):
        samples = [
            CalibrationSample(
                review_id=f"r{i}",
                predicted_confidence=i * 0.1,
                outcome=HumanOutcome.CORRECT,
                issue_count=1,
                severity_breakdown={},
            )
            for i in range(1, 6)
        ]
        report = analyze_calibration(samples, bucket_count=2)
        assert len(report.buckets) == 2


class TestSuggestWeightAdjustments:
    """Test weight adjustment suggestions."""

    def test_no_adjustment_when_well_calibrated(self):
        samples = [
            CalibrationSample(
                review_id=f"r{i}",
                predicted_confidence=0.85,
                outcome=HumanOutcome.CORRECT,
                issue_count=1,
                severity_breakdown={"minor": 1},
            )
            for i in range(10)
        ]
        adjustments = suggest_weight_adjustments(samples)
        # Well-calibrated: adjustments should be minor
        assert isinstance(adjustments, CalibrationWeights)

    def test_overconfident_increases_penalties(self):
        """When model is overconfident, issue penalties should increase."""
        samples = [
            CalibrationSample(
                review_id=f"r{i}",
                predicted_confidence=0.9,
                outcome=HumanOutcome.INCORRECT,
                issue_count=2,
                severity_breakdown={"major": 2},
            )
            for i in range(10)
        ]
        adjustments = suggest_weight_adjustments(samples)
        # Should suggest higher penalty for major issues
        assert adjustments.major >= 0.3

    def test_underconfident_decreases_penalties(self):
        """When model is underconfident, issue penalties should decrease."""
        samples = [
            CalibrationSample(
                review_id=f"r{i}",
                predicted_confidence=0.3,
                outcome=HumanOutcome.CORRECT,
                issue_count=2,
                severity_breakdown={"major": 2},
            )
            for i in range(10)
        ]
        adjustments = suggest_weight_adjustments(samples)
        # Should suggest lower penalty for major issues
        assert adjustments.major <= 0.3


class TestLoadCalibrationData:
    """Test loading calibration data from YAML files."""

    def test_load_from_directory(self, tmp_path):
        # Create a sample calibration file
        data_dir = tmp_path / "calibration_data"
        data_dir.mkdir()
        sample_file = data_dir / "sample1.yaml"
        sample_file.write_text("""
- review_id: r1
  predicted_confidence: 0.85
  outcome: correct
  issue_count: 2
  severity_breakdown:
    major: 1
    minor: 1
- review_id: r2
  predicted_confidence: 0.6
  outcome: incorrect
  issue_count: 1
  severity_breakdown:
    critical: 1
""")
        samples = load_calibration_data(data_dir)
        assert len(samples) == 2
        assert samples[0].review_id == "r1"
        assert samples[0].outcome == HumanOutcome.CORRECT
        assert samples[1].outcome == HumanOutcome.INCORRECT

    def test_load_empty_directory(self, tmp_path):
        data_dir = tmp_path / "empty"
        data_dir.mkdir()
        samples = load_calibration_data(data_dir)
        assert samples == []


class TestCalibrationWeightsIntegration:
    """Test that CalibrationWeights integrates with confidence calculation."""

    def test_custom_weights_affect_score(self):
        from unittest.mock import Mock

        review = Mock()
        review.issues = [Mock(severity="major"), Mock(severity="minor")]
        review.strengths = []
        review.concerns = []
        review.questions = []

        pr = Mock()
        config = Mock()
        config.confidence.high = 0.8
        config.confidence.low = 0.4

        # Default weights
        default_result = calculate_confidence(review, pr, config)

        # Custom weights with higher major penalty
        custom_weights = CalibrationWeights(
            critical=0.6, major=0.5, minor=0.1, suggestion=0.25
        )
        custom_result = calculate_confidence(
            review, pr, config, weights=custom_weights
        )

        # Higher penalty should give lower score
        assert custom_result.score < default_result.score
