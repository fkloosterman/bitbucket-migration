"""Unit tests for angle bracket escaping in LinkRewriter."""
import pytest
from unittest.mock import MagicMock
from bitbucket_migration.services.link_rewriter import LinkRewriter


class TestAngleBracketEscaping:
    """Test that non-URL angle brackets are properly escaped."""

    @pytest.fixture
    def link_rewriter(self):
        """Create a LinkRewriter instance for testing."""
        # Create mock environment
        mock_env = MagicMock()
        mock_config = MagicMock()
        mock_config.user_mapping = {}
        mock_config.bitbucket.workspace = 'test-workspace'
        mock_config.bitbucket.repo = 'test-repo'
        mock_config.github.owner = 'test-owner'
        mock_config.github.repo = 'test-repo'
        mock_config.link_rewriting_config = None
        mock_env.config = mock_config
        mock_env.logger = MagicMock()

        mock_clients = MagicMock()
        mock_clients.bb = MagicMock()
        mock_env.clients = mock_clients

        # Create mock state
        mock_state = MagicMock()
        mock_state.services = {}
        mock_state.mappings.issues = {1: 1}
        mock_state.mappings.prs = {1: 1}

        return LinkRewriter(mock_env, mock_state)

    def test_escape_cpp_type(self, link_rewriter):
        """Test that C++ types in angle brackets are escaped."""
        text = "Using <std::uint16_t> in code"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "`<std::uint16_t>`" in result

    def test_escape_nested_cpp_type(self, link_rewriter):
        """Test that nested C++ types are escaped."""
        text = "Template <std::vector<int>>"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "`<std::vector<int>>`" in result

    def test_preserve_http_autolink(self, link_rewriter):
        """Test that HTTP autolinks are preserved."""
        text = "Check <https://example.com> for info"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "<https://example.com>" in result
        assert "`<https://example.com>`" not in result

    def test_preserve_mailto_autolink(self, link_rewriter):
        """Test that mailto autolinks are preserved."""
        text = "Email <mailto:user@example.com>"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "<mailto:user@example.com>" in result
        assert "`<mailto:user@example.com>`" not in result

    def test_preserve_email_autolink(self, link_rewriter):
        """Test that email autolinks are preserved."""
        text = "Contact <john.doe@example.com>"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "<john.doe@example.com>" in result
        assert "`<john.doe@example.com>`" not in result

    def test_mixed_content(self, link_rewriter):
        """Test mixed URLs and non-URL angle brackets."""
        text = "See <https://example.com> and use <std::uint16_t>"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "<https://example.com>" in result
        assert "`<std::uint16_t>`" in result

    def test_multiple_cpp_types(self, link_rewriter):
        """Test multiple C++ types are all escaped."""
        text = "Types: <A> and <B> and <C>"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "`<A>`" in result
        assert "`<B>`" in result
        assert "`<C>`" in result

    def test_complex_nested_template(self, link_rewriter):
        """Test complex nested template syntax."""
        text = "Using <std::map<K,V>>"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "`<std::map<K,V>>`" in result

    def test_html_like_tag(self, link_rewriter):
        """Test HTML-like tags are escaped."""
        text = "HTML-like <div>"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "`<div>`" in result

    def test_no_angle_brackets(self, link_rewriter):
        """Test text without angle brackets is unchanged."""
        text = "Normal text without brackets"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert result == text

    def test_cpp_without_angle_brackets(self, link_rewriter):
        """Test C++ namespaces without angle brackets are unchanged."""
        text = "std::uint16_t without brackets"
        result, _, _, _, _, _, _ = link_rewriter.rewrite_links(text)
        assert "std::uint16_t" in result
        assert "`" not in result or "*(was" in result  # Allow backticks only from other features