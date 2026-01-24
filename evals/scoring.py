"""Scoring utilities for evaluation results.

Calculates precision, recall, F1, confidence error, and other metrics
for comparing predicted vs expected review issues.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class EvalSuite:
    """Evaluation test suite definition."""
    cases: list[dict[str, Any]]
    suite_name: str


@dataclass
class EvalResult:
    """Results from running an evaluation suite."""
    suite_name: str
    case_results: list[dict[str, Any]]
    total_cost_usd: float
    duration_seconds: float


@dataclass
class EvalMetrics:
    """Calculated metrics from evaluation results."""
    precision: float
    recall: float
    f1: float
    confidence_mae: float  # Mean Absolute Error
    false_positive_rate: float
    success_rate: float
    total_predicted: int
    total_expected: int
    total_true_positives: int


def calculate_metrics(result: EvalResult) -> EvalMetrics:
    """Calculate precision, recall, F1 and other metrics from evaluation results."""
    total_predicted = 0
    total_expected = 0
    total_true_positives = 0
    confidence_errors = []
    successful_cases = 0

    for case_result in result.case_results:
        if not case_result["success"]:
            continue

        successful_cases += 1
        predicted_issues = case_result["predicted_issues"]
        expected_issues = case_result["expected_issues"]

        # Count issues
        total_predicted += len(predicted_issues)
        total_expected += len(expected_issues)

        # Calculate true positives using issue matching
        true_positives = count_true_positives(predicted_issues, expected_issues)
        total_true_positives += true_positives

        # Calculate confidence error
        predicted_conf = case_result["predicted_confidence"]
        expected_conf_range = case_result["expected_confidence_range"]
        conf_error = confidence_error(predicted_conf, expected_conf_range)
        confidence_errors.append(conf_error)

    # Calculate metrics
    precision = total_true_positives / max(total_predicted, 1)
    recall = total_true_positives / max(total_expected, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-10)

    false_positive_rate = (total_predicted - total_true_positives) / max(total_predicted, 1)
    success_rate = successful_cases / len(result.case_results)
    confidence_mae = sum(confidence_errors) / max(len(confidence_errors), 1)

    return EvalMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        confidence_mae=confidence_mae,
        false_positive_rate=false_positive_rate,
        success_rate=success_rate,
        total_predicted=total_predicted,
        total_expected=total_expected,
        total_true_positives=total_true_positives
    )


def count_true_positives(predicted_issues: list[dict], expected_issues: list[dict]) -> int:
    """Count how many predicted issues match expected issues.

    Matching criteria:
    - Same file (if specified)
    - Overlapping line ranges
    - Similar severity level
    - Similar category
    """
    true_positives = 0

    for expected in expected_issues:
        for predicted in predicted_issues:
            if _issues_match(predicted, expected):
                true_positives += 1
                break  # Each expected issue can only match once

    return true_positives


def _issues_match(predicted: dict, expected: dict) -> bool:
    """Check if a predicted issue matches an expected issue."""
    # File matching (if expected specifies file)
    if "file" in expected:
        pred_file = predicted.get("file", "")
        exp_file = expected["file"]
        if not pred_file.endswith(exp_file) and exp_file not in pred_file:
            return False

    # Line range overlap
    if "line_range" in expected:
        pred_lines = predicted.get("line_range", [])
        exp_lines = expected["line_range"]
        if not _ranges_overlap(pred_lines, exp_lines):
            return False

    # Severity matching (with tolerance)
    if "severity" in expected:
        pred_severity = predicted.get("severity", "info").lower()
        exp_severity = expected["severity"].lower()
        if not _severity_matches(pred_severity, exp_severity):
            return False

    # Category matching
    if "category" in expected:
        pred_category = predicted.get("category", "").lower()
        exp_category = expected["category"].lower()
        if exp_category not in pred_category and pred_category not in exp_category:
            return False

    # Description content check (if specified)
    if "description_contains" in expected:
        pred_desc = predicted.get("description", "").lower()
        exp_contains = expected["description_contains"].lower()
        if exp_contains not in pred_desc:
            return False

    return True


def _ranges_overlap(range1: list[int], range2: list[int]) -> bool:
    """Check if two line ranges overlap."""
    if not range1 or not range2:
        return True  # If no range specified, consider it a match

    if len(range1) < 2 or len(range2) < 2:
        return True

    start1, end1 = range1[0], range1[1]
    start2, end2 = range2[0], range2[1]

    return start1 <= end2 and start2 <= end1


def _severity_matches(pred_severity: str, exp_severity: str) -> bool:
    """Check if severity levels match with some tolerance."""
    severity_map = {
        "low": 1, "info": 1,
        "medium": 2, "warning": 2,
        "high": 3, "error": 3, "critical": 3
    }

    pred_level = severity_map.get(pred_severity, 2)
    exp_level = severity_map.get(exp_severity, 2)

    # Allow one level difference
    return abs(pred_level - exp_level) <= 1


def confidence_error(predicted: float, expected_range: list[float]) -> float:
    """Calculate confidence prediction error.

    Returns 0 if predicted confidence is within expected range,
    otherwise returns distance to closest range boundary.
    """
    if len(expected_range) != 2:
        return 0.0

    min_conf, max_conf = expected_range
    if min_conf <= predicted <= max_conf:
        return 0.0

    # Distance to closest boundary
    return min(abs(predicted - min_conf), abs(predicted - max_conf))