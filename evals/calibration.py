"""Confidence calibration framework.

Compares predicted confidence scores against human-labeled outcomes
to measure and improve calibration accuracy.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

from pr_review_agent.review.confidence import CalibrationWeights


class HumanOutcome(Enum):
    """Human-labeled outcome for a review prediction."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"


@dataclass
class CalibrationSample:
    """A single calibration data point."""

    review_id: str
    predicted_confidence: float
    outcome: HumanOutcome
    issue_count: int
    severity_breakdown: dict[str, int]

    @property
    def is_accurate(self) -> bool:
        """Whether the review prediction was correct."""
        return self.outcome == HumanOutcome.CORRECT


@dataclass
class CalibrationBucket:
    """A bucket of samples in a confidence range."""

    range_low: float
    range_high: float
    avg_predicted: float
    actual_accuracy: float
    sample_count: int


@dataclass
class CalibrationReport:
    """Report from calibration analysis."""

    total_samples: int
    overall_accuracy: float
    calibration_error: float
    buckets: list[CalibrationBucket] = field(default_factory=list)


def load_calibration_data(data_dir: Path) -> list[CalibrationSample]:
    """Load calibration samples from YAML files in a directory."""
    samples: list[CalibrationSample] = []

    if not data_dir.exists():
        return samples

    for yaml_file in sorted(data_dir.glob("*.yaml")):
        with open(yaml_file) as f:
            entries = yaml.safe_load(f)

        if not entries:
            continue

        for entry in entries:
            samples.append(CalibrationSample(
                review_id=entry["review_id"],
                predicted_confidence=entry["predicted_confidence"],
                outcome=HumanOutcome(entry["outcome"]),
                issue_count=entry["issue_count"],
                severity_breakdown=entry.get("severity_breakdown", {}),
            ))

    return samples


def compute_buckets(
    samples: list[CalibrationSample],
    bucket_count: int = 5,
) -> list[CalibrationBucket]:
    """Group samples into confidence buckets and compute accuracy per bucket."""
    if not samples:
        return []

    # Sort by predicted confidence
    sorted_samples = sorted(samples, key=lambda s: s.predicted_confidence)

    # Split into equal-sized buckets
    bucket_size = max(1, len(sorted_samples) // bucket_count)
    buckets: list[CalibrationBucket] = []

    for i in range(0, len(sorted_samples), bucket_size):
        bucket_samples = sorted_samples[i : i + bucket_size]
        if not bucket_samples:
            continue

        correct_count = sum(1 for s in bucket_samples if s.is_accurate)
        avg_pred = sum(s.predicted_confidence for s in bucket_samples) / len(
            bucket_samples
        )

        buckets.append(CalibrationBucket(
            range_low=bucket_samples[0].predicted_confidence,
            range_high=bucket_samples[-1].predicted_confidence,
            avg_predicted=avg_pred,
            actual_accuracy=correct_count / len(bucket_samples),
            sample_count=len(bucket_samples),
        ))

    # Merge excess buckets if we have too many
    while len(buckets) > bucket_count and len(buckets) > 1:
        # Merge the two smallest adjacent buckets
        min_idx = min(
            range(len(buckets) - 1),
            key=lambda j: buckets[j].sample_count + buckets[j + 1].sample_count,
        )
        b1, b2 = buckets[min_idx], buckets[min_idx + 1]
        total = b1.sample_count + b2.sample_count
        merged = CalibrationBucket(
            range_low=b1.range_low,
            range_high=b2.range_high,
            avg_predicted=(
                b1.avg_predicted * b1.sample_count
                + b2.avg_predicted * b2.sample_count
            )
            / total,
            actual_accuracy=(
                b1.actual_accuracy * b1.sample_count
                + b2.actual_accuracy * b2.sample_count
            )
            / total,
            sample_count=total,
        )
        buckets[min_idx : min_idx + 2] = [merged]

    return buckets


def analyze_calibration(
    samples: list[CalibrationSample],
    bucket_count: int = 5,
) -> CalibrationReport:
    """Analyze calibration of confidence predictions vs actual outcomes."""
    if not samples:
        return CalibrationReport(
            total_samples=0,
            overall_accuracy=0.0,
            calibration_error=0.0,
        )

    correct = sum(1 for s in samples if s.is_accurate)
    overall_accuracy = correct / len(samples)

    buckets = compute_buckets(samples, bucket_count=bucket_count)

    # Expected Calibration Error (ECE):
    # Weighted average of |predicted - actual| per bucket
    ece = 0.0
    for bucket in buckets:
        weight = bucket.sample_count / len(samples)
        ece += weight * abs(bucket.avg_predicted - bucket.actual_accuracy)

    return CalibrationReport(
        total_samples=len(samples),
        overall_accuracy=overall_accuracy,
        calibration_error=ece,
        buckets=buckets,
    )


def suggest_weight_adjustments(
    samples: list[CalibrationSample],
) -> CalibrationWeights:
    """Suggest adjusted severity weights based on calibration data.

    If the model is overconfident (high predicted, low actual accuracy),
    increase penalties. If underconfident, decrease them.
    """
    from pr_review_agent.review.confidence import DEFAULT_WEIGHTS

    if not samples:
        return DEFAULT_WEIGHTS

    # Compute overall bias: avg(predicted) - accuracy
    avg_predicted = sum(s.predicted_confidence for s in samples) / len(samples)
    accuracy = sum(1 for s in samples if s.is_accurate) / len(samples)
    bias = avg_predicted - accuracy  # positive = overconfident

    # Adjust weights based on bias direction
    # Overconfident: increase penalties (multiply by 1 + bias)
    # Underconfident: decrease penalties (multiply by 1 + bias, where bias < 0)
    adjustment = 1 + bias

    return CalibrationWeights(
        critical=max(0.1, min(1.0, DEFAULT_WEIGHTS.critical * adjustment)),
        major=max(0.1, min(1.0, DEFAULT_WEIGHTS.major * adjustment)),
        minor=max(0.01, min(0.5, DEFAULT_WEIGHTS.minor * adjustment)),
        suggestion=max(0.01, min(0.5, DEFAULT_WEIGHTS.suggestion * adjustment)),
    )
