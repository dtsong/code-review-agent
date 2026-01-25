"""Tests for code suggestion validation."""

from pr_review_agent.review.suggestion_validator import validate_suggestion


class TestValidateSuggestion:
    """Tests for validate_suggestion function."""

    def test_none_suggestion_returns_none(self):
        """None input returns None."""
        assert validate_suggestion(None, "file.py") is None

    def test_empty_suggestion_returns_none(self):
        """Empty string returns None."""
        assert validate_suggestion("", "file.py") is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only suggestion returns None."""
        assert validate_suggestion("   \n\t  ", "file.py") is None

    def test_valid_python_passes(self):
        """Valid Python code passes validation."""
        code = "x = 1\ny = 2"
        assert validate_suggestion(code, "file.py") == code

    def test_valid_python_with_indentation(self):
        """Valid indented Python code passes."""
        code = "    if x:\n        return y"
        assert validate_suggestion(code, "file.py") == code

    def test_invalid_python_syntax_returns_none(self):
        """Invalid Python syntax returns None."""
        code = "def foo(\n    # missing closing paren"
        assert validate_suggestion(code, "file.py") is None

    def test_non_python_file_skips_ast_check(self):
        """Non-Python files skip AST validation."""
        # This would be invalid Python but valid for other files
        code = "const x = { a: 1 };"
        assert validate_suggestion(code, "file.js") == code

    def test_typescript_file_skips_ast_check(self):
        """TypeScript files skip AST validation."""
        code = "const x: number = 1;"
        assert validate_suggestion(code, "file.ts") == code

    def test_mixed_indentation_returns_none(self):
        """Mixed tabs and spaces returns None."""
        code = "    x = 1\n\ty = 2"
        assert validate_suggestion(code, "file.py") is None

    def test_valid_multiline_python(self):
        """Valid multiline Python passes."""
        code = '''def foo():
    x = get_data()
    if x is None:
        return None
    return process(x)'''
        assert validate_suggestion(code, "file.py") == code

    def test_python_expression_valid(self):
        """Single expression is valid Python."""
        code = "result = calculate(a, b)"
        assert validate_suggestion(code, "file.py") == code

    def test_python_with_comments_valid(self):
        """Python with comments is valid."""
        code = "# Fix the bug\nx = get_value()"
        assert validate_suggestion(code, "file.py") == code

    def test_pyi_file_uses_python_validation(self):
        """Python stub files use Python validation."""
        code = "def foo() -> int: ..."
        assert validate_suggestion(code, "types.pyi") == code

    def test_loop_header_without_body_valid(self):
        """Loop header without body is valid (partial replacement)."""
        code = "    for i in range(len(items)):"
        assert validate_suggestion(code, "file.py") == code

    def test_if_header_without_body_valid(self):
        """If statement header without body is valid."""
        code = "if x is not None:"
        assert validate_suggestion(code, "file.py") == code

    def test_function_def_without_body_valid(self):
        """Function definition without body is valid."""
        code = "def process_data(items: list) -> int:"
        assert validate_suggestion(code, "file.py") == code

    def test_class_def_without_body_valid(self):
        """Class definition without body is valid."""
        code = "class MyHandler(BaseHandler):"
        assert validate_suggestion(code, "file.py") == code
