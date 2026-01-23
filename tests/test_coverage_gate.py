"""Tests for coverage gate."""

from pathlib import Path

from pr_review_agent.config import Config, CoverageConfig
from pr_review_agent.gates.coverage_gate import check_coverage, parse_coverage_xml

SAMPLE_COVERAGE_XML = """\
<?xml version="1.0" ?>
<coverage line-rate="0.85">
    <packages>
        <package name="src" line-rate="0.85">
            <classes>
                <class name="main.py" filename="src/main.py" line-rate="0.9">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="1"/>
                        <line number="3" hits="0"/>
                        <line number="10" hits="1"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""

LOW_COVERAGE_XML = """\
<?xml version="1.0" ?>
<coverage line-rate="0.50">
    <packages>
        <package name="src" line-rate="0.50">
            <classes>
                <class name="main.py" filename="src/main.py" line-rate="0.50">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="0"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""


def test_parse_coverage_xml(tmp_path: Path):
    """Parse a valid coverage XML report."""
    report = tmp_path / "coverage.xml"
    report.write_text(SAMPLE_COVERAGE_XML)

    coverage_pct, uncovered = parse_coverage_xml(report)

    assert coverage_pct == 85.0
    assert "src/main.py:3" in uncovered


def test_parse_coverage_xml_missing_file(tmp_path: Path):
    """Missing report returns zero coverage."""
    coverage_pct, uncovered = parse_coverage_xml(tmp_path / "nonexistent.xml")

    assert coverage_pct == 0.0
    assert uncovered == []


def test_check_coverage_disabled():
    """Disabled coverage gate always passes."""
    config = Config(coverage=CoverageConfig(enabled=False))

    result = check_coverage(Path("missing.xml"), None, config)

    assert result.passed is True


def test_check_coverage_report_not_found(tmp_path: Path):
    """Missing report skips check gracefully."""
    config = Config(coverage=CoverageConfig(enabled=True))

    result = check_coverage(tmp_path / "missing.xml", None, config)

    assert result.passed is True
    assert "not found" in result.reason


def test_check_coverage_passes_above_threshold(tmp_path: Path):
    """Coverage above threshold passes."""
    report = tmp_path / "coverage.xml"
    report.write_text(SAMPLE_COVERAGE_XML)

    config = Config(coverage=CoverageConfig(enabled=True, min_coverage=80.0))

    result = check_coverage(report, None, config)

    assert result.passed is True
    assert result.current_coverage == 85.0


def test_check_coverage_fails_below_threshold(tmp_path: Path):
    """Coverage below threshold fails."""
    report = tmp_path / "coverage.xml"
    report.write_text(LOW_COVERAGE_XML)

    config = Config(coverage=CoverageConfig(enabled=True, min_coverage=80.0))

    result = check_coverage(report, None, config)

    assert result.passed is False
    assert "below minimum" in result.reason


def test_check_coverage_delta_decrease_fails(tmp_path: Path):
    """Coverage decrease fails when fail_on_decrease is enabled."""
    current = tmp_path / "current.xml"
    current.write_text(LOW_COVERAGE_XML)  # 50%

    base = tmp_path / "base.xml"
    base.write_text(SAMPLE_COVERAGE_XML)  # 85%

    config = Config(coverage=CoverageConfig(
        enabled=True, min_coverage=40.0, fail_on_decrease=True
    ))

    result = check_coverage(current, base, config)

    assert result.passed is False
    assert result.delta < 0
    assert "decreased" in result.reason


def test_check_coverage_delta_decrease_allowed(tmp_path: Path):
    """Coverage decrease passes when fail_on_decrease is disabled."""
    current = tmp_path / "current.xml"
    current.write_text(LOW_COVERAGE_XML)  # 50%

    base = tmp_path / "base.xml"
    base.write_text(SAMPLE_COVERAGE_XML)  # 85%

    config = Config(coverage=CoverageConfig(
        enabled=True, min_coverage=40.0, fail_on_decrease=False
    ))

    result = check_coverage(current, base, config)

    assert result.passed is True
    assert result.delta < 0
