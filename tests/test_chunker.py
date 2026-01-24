"""Tests for diff chunking strategy."""

from pr_review_agent.review.chunker import (
    ChunkStrategy,
    DiffChunk,
    chunk_diff,
    merge_review_results,
)
from pr_review_agent.review.llm_reviewer import LLMReviewResult, ReviewIssue


class TestChunkDiffByFile:
    """Test file-based chunking."""

    def test_single_file_no_chunking_needed(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
+import os
 def main():
     pass"""
        chunks = chunk_diff(diff, strategy=ChunkStrategy.FILE)
        assert len(chunks) == 1
        assert chunks[0].file_path == "src/app.py"
        assert "+import os" in chunks[0].content

    def test_multiple_files_split_into_chunks(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
+import os
 def main():
     pass
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,2 +1,3 @@
+import sys
 def helper():
     pass
diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1,2 +1,3 @@
+import pytest
 def test_main():
     pass"""
        chunks = chunk_diff(diff, strategy=ChunkStrategy.FILE)
        assert len(chunks) == 3
        assert chunks[0].file_path == "src/app.py"
        assert chunks[1].file_path == "src/utils.py"
        assert chunks[2].file_path == "tests/test_app.py"

    def test_empty_diff_returns_empty(self):
        chunks = chunk_diff("", strategy=ChunkStrategy.FILE)
        assert chunks == []

    def test_preserves_diff_header_per_chunk(self):
        diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,2 @@
+x = 1
 y = 2
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,1 +1,2 @@
+z = 3
 w = 4"""
        chunks = chunk_diff(diff, strategy=ChunkStrategy.FILE)
        assert "diff --git a/a.py b/a.py" in chunks[0].content
        assert "diff --git a/b.py b/b.py" in chunks[1].content


class TestChunkDiffByLines:
    """Test line-based chunking for very large files."""

    def test_small_diff_not_chunked(self):
        diff = """diff --git a/big.py b/big.py
--- a/big.py
+++ b/big.py
@@ -1,3 +1,4 @@
+line1
 line2
 line3"""
        chunks = chunk_diff(diff, strategy=ChunkStrategy.LINES, max_lines=100)
        assert len(chunks) == 1

    def test_large_file_split_by_line_limit(self):
        # Generate a diff with 50 added lines
        lines = [f"+line{i}" for i in range(50)]
        diff = (
            "diff --git a/big.py b/big.py\n"
            "--- a/big.py\n"
            "+++ b/big.py\n"
            "@@ -1,1 +1,51 @@\n"
            + "\n".join(lines)
            + "\n existing_line"
        )
        chunks = chunk_diff(diff, strategy=ChunkStrategy.LINES, max_lines=20)
        assert len(chunks) > 1
        # All chunks should reference the same file
        assert all(c.file_path == "big.py" for c in chunks)

    def test_chunk_index_tracking(self):
        lines = [f"+line{i}" for i in range(40)]
        diff = (
            "diff --git a/big.py b/big.py\n"
            "--- a/big.py\n"
            "+++ b/big.py\n"
            "@@ -1,1 +1,41 @@\n"
            + "\n".join(lines)
        )
        chunks = chunk_diff(diff, strategy=ChunkStrategy.LINES, max_lines=15)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == len(chunks)


class TestChunkDiffAuto:
    """Test automatic strategy selection."""

    def test_auto_uses_file_for_multi_file_diff(self):
        diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,2 @@
+x = 1
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,1 +1,2 @@
+y = 2"""
        chunks = chunk_diff(diff, strategy=ChunkStrategy.AUTO, max_lines=100)
        assert len(chunks) == 2

    def test_auto_uses_lines_for_single_large_file(self):
        lines = [f"+line{i}" for i in range(50)]
        diff = (
            "diff --git a/big.py b/big.py\n"
            "--- a/big.py\n"
            "+++ b/big.py\n"
            "@@ -1,1 +1,51 @@\n"
            + "\n".join(lines)
        )
        chunks = chunk_diff(diff, strategy=ChunkStrategy.AUTO, max_lines=20)
        assert len(chunks) > 1


class TestDiffChunk:
    """Test DiffChunk dataclass."""

    def test_chunk_has_required_fields(self):
        chunk = DiffChunk(
            content="diff content",
            file_path="src/app.py",
            chunk_index=0,
            total_chunks=3,
        )
        assert chunk.content == "diff content"
        assert chunk.file_path == "src/app.py"
        assert chunk.chunk_index == 0
        assert chunk.total_chunks == 3


class TestMergeReviewResults:
    """Test merging chunked review results."""

    def test_merge_empty_list(self):
        result = merge_review_results([])
        assert result.issues == []
        assert result.summary == ""

    def test_merge_single_result(self):
        r = LLMReviewResult(
            summary="Good code",
            issues=[
                ReviewIssue(
                    severity="minor",
                    category="style",
                    file="a.py",
                    line=1,
                    description="Unused var",
                    suggestion="Remove it",
                )
            ],
            strengths=["Clean"],
            concerns=["None"],
        )
        merged = merge_review_results([r])
        assert merged.summary == "Good code"
        assert len(merged.issues) == 1

    def test_merge_multiple_results_combines_issues(self):
        r1 = LLMReviewResult(
            summary="File A review",
            issues=[
                ReviewIssue(
                    severity="major",
                    category="logic",
                    file="a.py",
                    line=10,
                    description="Bug in a.py",
                    suggestion="Fix it",
                )
            ],
            strengths=["Good tests"],
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
        )
        r2 = LLMReviewResult(
            summary="File B review",
            issues=[
                ReviewIssue(
                    severity="minor",
                    category="style",
                    file="b.py",
                    line=5,
                    description="Style issue",
                    suggestion="Rename",
                )
            ],
            strengths=["Clean code"],
            concerns=["Complex logic"],
            input_tokens=80,
            output_tokens=40,
            cost_usd=0.008,
        )
        merged = merge_review_results([r1, r2])
        assert len(merged.issues) == 2
        assert merged.issues[0].file == "a.py"
        assert merged.issues[1].file == "b.py"

    def test_merge_aggregates_tokens_and_cost(self):
        r1 = LLMReviewResult(
            summary="A", input_tokens=100, output_tokens=50, cost_usd=0.01
        )
        r2 = LLMReviewResult(
            summary="B", input_tokens=200, output_tokens=100, cost_usd=0.02
        )
        merged = merge_review_results([r1, r2])
        assert merged.input_tokens == 300
        assert merged.output_tokens == 150
        assert abs(merged.cost_usd - 0.03) < 0.001

    def test_merge_combines_strengths_and_concerns(self):
        r1 = LLMReviewResult(
            summary="A", strengths=["s1"], concerns=["c1"], questions=["q1"]
        )
        r2 = LLMReviewResult(
            summary="B", strengths=["s2"], concerns=["c2"], questions=["q2"]
        )
        merged = merge_review_results([r1, r2])
        assert "s1" in merged.strengths
        assert "s2" in merged.strengths
        assert "c1" in merged.concerns
        assert "c2" in merged.concerns
        assert "q1" in merged.questions
        assert "q2" in merged.questions

    def test_merge_deduplicates_issues_by_fingerprint(self):
        """Issues with same fingerprint from overlapping chunks are deduplicated."""
        issue = ReviewIssue(
            severity="major",
            category="logic",
            file="a.py",
            line=10,
            description="Same bug",
            suggestion="Fix",
            fingerprint="abc123",
        )
        r1 = LLMReviewResult(summary="A", issues=[issue])
        r2 = LLMReviewResult(summary="B", issues=[issue])
        merged = merge_review_results([r1, r2])
        assert len(merged.issues) == 1

    def test_merge_summary_joins_chunk_summaries(self):
        r1 = LLMReviewResult(summary="File A looks good")
        r2 = LLMReviewResult(summary="File B has issues")
        merged = merge_review_results([r1, r2])
        assert "File A" in merged.summary
        assert "File B" in merged.summary
