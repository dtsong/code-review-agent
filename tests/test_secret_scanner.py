"""Tests for secret detection in review output."""

from pr_review_agent.output.secret_scanner import (
    redact_secrets,
    scan_for_secrets,
)


class TestSecretDetection:
    """Test detection of common secret patterns."""

    def test_detects_aws_access_key(self):
        text = "Found hardcoded key: AKIAIOSFODNN7EXAMPLE"
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "aws_access_key" for m in matches)

    def test_detects_aws_secret_key(self):
        text = "aws_secret = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'"
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "aws_secret_key" for m in matches)

    def test_detects_github_token(self):
        text = "token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12"
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "github_token" for m in matches)

    def test_detects_github_pat_fine_grained(self):
        text = (
            "GITHUB_TOKEN=github_pat_11ABCDEFG0abcdefghijkl"
            "_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwx"
        )
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "github_token" for m in matches)

    def test_detects_jwt_token(self):
        text = (
            "auth = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4g"
            "RG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "jwt_token" for m in matches)

    def test_detects_private_key_pem(self):
        text = """Found in config:
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWep4PAtGoq
-----END RSA PRIVATE KEY-----"""
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "private_key" for m in matches)

    def test_detects_generic_api_key_pattern(self):
        text = "api_key = 'sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop'"
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "api_key" for m in matches)

    def test_detects_database_url_with_password(self):
        text = "DATABASE_URL=postgresql://user:p4ssw0rd@host:5432/db"
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "database_url" for m in matches)

    def test_detects_slack_webhook(self):
        # Construct URL dynamically to avoid push protection triggers
        url = "https://hooks.slack.com/services/" + "TABC12345/BDEF67890/abcdefghij1234567890abcd"
        text = f"webhook = {url}"
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "slack_webhook" for m in matches)

    def test_detects_password_assignment(self):
        text = 'password = "super_secret_123!"'
        matches = scan_for_secrets(text)
        assert any(m.secret_type == "password" for m in matches)


class TestNoFalsePositives:
    """Ensure legitimate code is not flagged."""

    def test_short_strings_not_flagged(self):
        text = "key = 'abc'"
        matches = scan_for_secrets(text)
        assert len(matches) == 0

    def test_placeholder_not_flagged(self):
        text = "api_key = 'your-api-key-here'"
        matches = scan_for_secrets(text)
        assert len(matches) == 0

    def test_example_markers_not_flagged(self):
        text = "token = 'ghp_EXAMPLE_TOKEN_REPLACE_ME'"
        matches = scan_for_secrets(text)
        assert len(matches) == 0

    def test_env_var_reference_not_flagged(self):
        text = "key = os.environ.get('API_KEY')"
        matches = scan_for_secrets(text)
        assert len(matches) == 0

    def test_hash_not_flagged(self):
        text = "sha256 = 'a3f2b8c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1'"
        matches = scan_for_secrets(text)
        assert len(matches) == 0

    def test_normal_variable_assignment(self):
        text = "password_field = 'password'"
        matches = scan_for_secrets(text)
        assert len(matches) == 0


class TestRedaction:
    """Test secret redaction in output text."""

    def test_redacts_detected_secret(self):
        text = "Key found: AKIAIOSFODNN7EXAMPLE in config"
        result = redact_secrets(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_text
        assert "[REDACTED]" in result.redacted_text
        assert result.secrets_found > 0

    def test_preserves_surrounding_context(self):
        text = "The API key AKIAIOSFODNN7EXAMPLE was in the file"
        result = redact_secrets(text)
        assert "The API key" in result.redacted_text
        assert "was in the file" in result.redacted_text

    def test_redacts_multiple_secrets(self):
        text = """Found:
- AWS: AKIAIOSFODNN7EXAMPLE
- GitHub: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12"""
        result = redact_secrets(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_text
        assert "ghp_ABCDEF" not in result.redacted_text
        assert result.secrets_found == 2

    def test_no_secrets_returns_original(self):
        text = "This is clean code with no secrets"
        result = redact_secrets(text)
        assert result.redacted_text == text
        assert result.secrets_found == 0

    def test_redaction_result_has_match_details(self):
        text = "token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12"
        result = redact_secrets(text)
        assert len(result.matches) == 1
        assert result.matches[0].secret_type == "github_token"

    def test_private_key_multiline_redacted(self):
        text = """Config contains:
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn
-----END RSA PRIVATE KEY-----
End of config."""
        result = redact_secrets(text)
        assert "MIIEpAIBAAK" not in result.redacted_text
        assert "[REDACTED]" in result.redacted_text
        assert "End of config." in result.redacted_text
