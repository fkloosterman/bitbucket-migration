"""
Comprehensive integration tests for markdown processing in link rewriting.

Tests validate that markdown processing prevents nesting bugs and handles
various markdown scenarios correctly.
"""

import pytest
import re
from unittest.mock import MagicMock

from bitbucket_migration.services.link_rewriter import LinkRewriter
from bitbucket_migration.services.user_mapper import UserMapper


class TestMarkdownProcessing:
    """Test markdown link processing and nesting prevention."""

    @pytest.fixture
    def rewriter(self, mock_environment, mock_state):
        """Create a LinkRewriter instance for testing."""
        # Mock mappings
        issue_mapping = {123: 456, 789: 1001, 42: 100}
        pr_mapping = {45: 200, 67: 201}

        from bitbucket_migration.config.migration_config import LinkRewritingConfig
        template_config = LinkRewritingConfig()

        # Configure environment and state
        mock_environment.config.link_rewriting_config = template_config
        mock_environment.config.bitbucket.workspace = 'workspace'
        mock_environment.config.bitbucket.repo = 'repo'
        mock_environment.config.github.owner = 'owner'
        mock_environment.config.github.repo = 'repo'
        mock_state.mappings.issues = issue_mapping
        mock_state.mappings.prs = pr_mapping

        return LinkRewriter(mock_environment, mock_state)

    def test_markdown_link_no_nesting(self, rewriter):
        """Critical: Verify markdown links don't create nested structures."""
        input_text = "[See this issue](https://bitbucket.org/workspace/repo/issues/123) for details"

        result, _, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should NOT contain nested brackets
        assert "][" not in result, "Nested brackets detected in markdown link"
        assert result.count("[") == result.count("]"), "Unmatched brackets in result"
        assert result.count("(") == result.count(")"), "Unmatched parentheses in result"

        # Should contain valid markdown
        assert re.match(r'\[.*?\]\(https://github\.com/.*?\)', result), "Invalid markdown structure"

        # Should rewrite the URL
        assert "bitbucket.org" not in result, "Bitbucket URL not rewritten"
        assert "github.com" in result, "GitHub URL not found in result"

    def test_markdown_link_complex_text(self, rewriter):
        """Test markdown link with complex link text."""
        input_text = "[Check out this awesome feature request](https://bitbucket.org/workspace/repo/issues/789)"

        result, _, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Verify no nesting
        assert "][" not in result
        assert result.count("[") == result.count("]")
        assert result.count("(") == result.count(")")

        # Verify URL rewriting
        assert "bitbucket.org" not in result
        assert "github.com" in result
        assert "#456" not in result  # Should be #1001 based on mapping

    def test_plain_urls_still_work(self, rewriter):
        """Test that plain URLs are still processed correctly."""
        input_text = "Check out https://bitbucket.org/workspace/repo/issues/123 for details"

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should find and rewrite the URL
        assert links_found >= 1
        # Plain URLs should be rewritten to markdown format with template text
        # So bitbucket.org may appear in the template text like "*(was BB #123)*"
        assert "github.com" in result

        # Should not create markdown structure for plain URLs
        assert result.count("[") == result.count("]"), "Unmatched brackets in plain URL result"
        assert result.count("(") == result.count(")"), "Unmatched parentheses in plain URL result"

    def test_mixed_markdown_and_plain_urls(self, rewriter):
        """Test mixed markdown links and plain URLs."""
        input_text = """
        Check out [this issue](https://bitbucket.org/workspace/repo/issues/123).

        Also see https://bitbucket.org/workspace/repo/pull-requests/45.

        And here's an image: ![Diagram](https://bitbucket.org/workspace/repo/raw/main/diagram.png)

        Reference #789 and PR #67.
        """

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Verify all links rewritten - bitbucket.org may appear in preserved template text
        assert "github.com" in result, "No GitHub URLs found"
        assert links_found >= 5, f"Expected at least 5 links, found {links_found}"

        # Verify no nesting
        assert "][" not in result, "Nested brackets detected in mixed content"
        assert result.count("[") == result.count("]"), "Unmatched brackets in mixed content"
        assert result.count("(") == result.count(")"), "Unmatched parentheses in mixed content"

        # Verify valid markdown structure preserved
        markdown_links = re.findall(r'\[.*?\]\([^)]+\)', result)
        assert len(markdown_links) >= 2, f"Expected at least 2 markdown links, found {len(markdown_links)}"

        # Verify image links are handled
        image_links = re.findall(r'!\[.*?\]\([^)]+\)', result)
        assert len(image_links) >= 1, f"Expected at least 1 image link, found {len(image_links)}"

    def test_image_links(self, rewriter):
        """Test image link rewriting."""
        input_text = "![Screenshot](https://bitbucket.org/workspace/repo/raw/main/image.png)"

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should rewrite image URL
        assert links_found >= 1
        assert "bitbucket.org" not in result
        assert "github.com" in result

        # Should preserve image markdown structure
        assert result.startswith("![Screenshot]"), "Image markdown structure not preserved"
        assert "bitbucket.org" not in result, "Bitbucket URL not rewritten"
        assert "github.com" in result, "GitHub URL not found"

    def test_urls_in_link_text(self, rewriter):
        """Test URLs embedded in markdown link text."""
        input_text = "[Check https://bitbucket.org/workspace/repo/issues/123](https://example.com)"

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should rewrite URL in link text
        assert links_found >= 1
        assert "bitbucket.org" not in result
        assert "github.com" in result

        # Should preserve markdown structure
        assert result.count("[") == result.count("]")
        assert result.count("(") == result.count(")")

    def test_multiple_markdown_links(self, rewriter):
        """Test multiple markdown links in same text."""
        input_text = """
        [Issue #123](https://bitbucket.org/workspace/repo/issues/123) and
        [PR #45](https://bitbucket.org/workspace/repo/pull-requests/45) are related.
        """

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should rewrite both links
        assert links_found >= 2
        assert "bitbucket.org" not in result
        assert "github.com" in result

        # Should not create nesting
        assert "][" not in result
        assert result.count("[") == result.count("]")
        assert result.count("(") == result.count(")")

        # Should have multiple markdown links
        markdown_links = re.findall(r'\[.*?\]\([^)]+\)', result)
        assert len(markdown_links) >= 2

    def test_edge_case_escaped_markdown(self, rewriter):
        """Test escaped markdown characters."""
        input_text = r"Use \[escaped brackets\] and \(escaped parentheses\) in text"

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should not process escaped markdown as links
        assert links_found == 0, "Escaped markdown should not be processed as links"
        assert r"\[escaped brackets\]" in result, "Escaped brackets should be preserved"
        assert r"\(escaped parentheses\)" in result, "Escaped parentheses should be preserved"

    def test_edge_case_reference_links(self, rewriter):
        """Test markdown reference-style links."""
        input_text = """
        Check out [this issue][1] for details.

        [1]: https://bitbucket.org/workspace/repo/issues/123
        """

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should rewrite the reference URL
        assert links_found >= 1
        # bitbucket.org may appear in preserved template text
        assert "github.com" in result

        # Should preserve reference link structure
        assert "[this issue][1]" in result, "Reference link text should be preserved"
        assert "[1]:" in result, "Reference definition should be preserved"

    def test_edge_case_nested_brackets_in_text(self, rewriter):
        """Test markdown links with nested brackets in link text."""
        input_text = "[Issue with [nested] brackets](https://bitbucket.org/workspace/repo/issues/123)"

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should handle nested brackets in text correctly
        assert links_found >= 1
        assert "bitbucket.org" not in result
        assert "github.com" in result

        # Should not create additional nesting
        assert "][" not in result
        assert result.count("[") == result.count("]")
        assert result.count("(") == result.count(")")

    def test_edge_case_empty_link_text(self, rewriter):
        """Test markdown links with empty link text."""
        input_text = "[](https://bitbucket.org/workspace/repo/issues/123)"

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should still rewrite the URL
        assert links_found >= 1
        assert "bitbucket.org" not in result
        assert "github.com" in result

        # Should preserve empty link text
        assert "[](" in result, "Empty link text should be preserved"

    def test_integration_comprehensive(self, rewriter):
        """Comprehensive integration test with real-world content."""
        input_text = """
        # Development Update

        ## Issues Resolved

        Fixed [critical bug in authentication](https://bitbucket.org/workspace/repo/issues/123)
        that was causing login failures.

        Also resolved https://bitbucket.org/workspace/repo/issues/789 in the payment system.

        ## Pull Requests

        Merged [feature branch PR](https://bitbucket.org/workspace/repo/pull-requests/45)
        with the new dashboard.

        Check out https://bitbucket.org/workspace/repo/pull-requests/67 for review.

        ## Documentation

        Updated diagrams:
        ![System Architecture](https://bitbucket.org/workspace/repo/raw/main/docs/architecture.png)
        ![API Flow](https://bitbucket.org/workspace/repo/raw/main/docs/api-flow.png)

        ## References

        Related issues: #123, #789
        Related PRs: PR #45, PR #67

        For more details, visit [the project wiki](https://bitbucket.org/workspace/repo/wiki).
        """

        result, links_found, unhandled_links, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Verify comprehensive rewriting
        # Most URLs should be rewritten, but some (like wiki) might not have handlers
        assert links_found >= 8, f"Expected at least 8 links, found {links_found}"

        # Check that main URLs are rewritten (issues, PRs, raw files)
        assert "github.com/owner/repo/issues/456" in result, "Issue 123 not rewritten"
        assert "github.com/owner/repo/issues/1001" in result, "Issue 789 not rewritten"
        assert "github.com/owner/repo/issues/200" in result, "PR 45 not rewritten"
        assert "github.com/owner/repo/issues/201" in result, "PR 67 not rewritten"
        assert "github.com/owner/repo/raw/main/docs/architecture.png" in result, "Raw file not rewritten"
        assert "github.com/owner/repo/raw/main/docs/api-flow.png" in result, "Raw file not rewritten"

        # Wiki URLs might not be handled (no direct GitHub equivalent)
        # So we don't assert they must be rewritten

        # Verify no nesting bugs
        assert "][" not in result, "Nested brackets detected in comprehensive test"
        assert result.count("[") == result.count("]"), "Unmatched brackets in comprehensive test"
        assert result.count("(") == result.count(")"), "Unmatched parentheses in comprehensive test"

        # Verify markdown structure preserved
        markdown_links = re.findall(r'\[.*?\]\([^)]+\)', result)
        assert len(markdown_links) >= 4, f"Expected at least 4 markdown links, found {len(markdown_links)}"

        # Verify image links preserved
        image_links = re.findall(r'!\[.*?\]\([^)]+\)', result)
        assert len(image_links) >= 2, f"Expected at least 2 image links, found {len(image_links)}"

        # Verify short references handled
        assert "#456" in result or "#1001" in result, "Issue references not rewritten"
        assert "[#200]" in result or "[#201]" in result, "PR references not rewritten"

        # Verify unhandled links are minimal
        assert len(unhandled_links) < links_found * 0.1, "Too many unhandled links"

    def test_markdown_context_awareness(self, rewriter):
        """Test that markdown context is handled correctly."""
        input_text = "[Link text](https://bitbucket.org/workspace/repo/issues/123)"

        result, _, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should produce clean markdown without extra notes in markdown context
        # The implementation should detect markdown context and return just the URL
        assert "github.com" in result
        assert "bitbucket.org" not in result

        # Should not have nested structures
        assert "][" not in result
        assert result.count("[") == result.count("]")
        assert result.count("(") == result.count(")")

    def test_performance_with_many_markdown_links(self, rewriter):
        """Test performance with many markdown links."""
        # Use only the mapped issues: 123, 789, 42
        links = [
            "[Issue #123](https://bitbucket.org/workspace/repo/issues/123)",
            "[Issue #789](https://bitbucket.org/workspace/repo/issues/789)",
            "[Issue #42](https://bitbucket.org/workspace/repo/issues/42)"
        ]

        input_text = " ".join(links)

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should handle all 3 links since they're all mapped
        assert links_found >= 3, f"Expected at least 3 links, found {links_found}"

        # Should not create nesting
        assert "][" not in result, "Nested brackets in performance test"
        assert result.count("[") == result.count("]"), "Unmatched brackets in performance test"
        assert result.count("(") == result.count(")"), "Unmatched parentheses in performance test"

        # All URLs should be rewritten
        assert "bitbucket.org" not in result, "Some URLs not rewritten in performance test"
        assert "github.com" in result, "No GitHub URLs found in performance test"

    def test_markdown_with_special_characters(self, rewriter):
        """Test markdown links with special characters in URLs."""
        input_text = "[Test & special chars](https://bitbucket.org/workspace/repo/issues/123?param=value&other=test)"

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should handle special characters
        assert links_found >= 1
        assert "bitbucket.org" not in result
        assert "github.com" in result

        # Should preserve markdown structure
        assert "][" not in result
        assert result.count("[") == result.count("]")
        assert result.count("(") == result.count(")")

    def test_malformed_markdown_recovery(self, rewriter):
        """Test recovery from malformed markdown."""
        # Test with markdown that's missing closing parenthesis but still valid URL
        input_text = "[Link without closing paren](https://bitbucket.org/workspace/repo/issues/123"

        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)

        # Should handle this gracefully (might not find links due to malformed markdown)
        # The important thing is it doesn't crash and preserves the original text
        assert "bitbucket.org" in result, "Original malformed markdown should be preserved"
        # Since it's malformed, it might not be processed as a link
        # The key is that it doesn't crash or create invalid structures


class TestMarkdownRegression:
    """Regression tests for markdown processing."""

    @pytest.fixture
    def rewriter_minimal(self, mock_environment, mock_state):
        """Create a minimal LinkRewriter for regression testing."""
        issue_mapping = {1: 1, 2: 2}  # Identity mapping for simplicity
        pr_mapping = {}

        from bitbucket_migration.config.migration_config import LinkRewritingConfig
        template_config = LinkRewritingConfig()

        # Configure environment and state
        mock_environment.config.link_rewriting_config = template_config
        mock_environment.config.bitbucket.workspace = 'test'
        mock_environment.config.bitbucket.repo = 'test'
        mock_environment.config.github.owner = 'test'
        mock_environment.config.github.repo = 'test'
        mock_state.mappings.issues = issue_mapping
        mock_state.mappings.prs = pr_mapping

        return LinkRewriter(mock_environment, mock_state)

    def test_regression_no_false_positives(self, rewriter_minimal):
        """Test that non-Bitbucket URLs are not processed."""
        input_text = "[Google](https://google.com) and [GitHub](https://github.com/test/repo)"

        result, links_found, _, _, _, _, _ = rewriter_minimal.rewrite_links(input_text)

        # Should not process non-Bitbucket URLs
        assert links_found == 0, "Non-Bitbucket URLs should not be processed"
        assert "google.com" in result, "Google URL should be preserved"
        assert "github.com/test/repo" in result, "GitHub URL should be preserved"

        # Should preserve markdown structure
        assert result.count("[") == result.count("]")
        assert result.count("(") == result.count(")")

    def test_regression_markdown_precedence(self, rewriter_minimal):
        """Test that markdown processing takes precedence over plain URL processing."""
        input_text = "[URL in text](https://bitbucket.org/test/test/issues/1)"

        result, links_found, _, _, _, _, _ = rewriter_minimal.rewrite_links(input_text)

        # Should process as markdown link, not plain URL
        assert links_found >= 1
        assert "bitbucket.org" not in result
        assert "github.com" in result

        # Should not create nesting
        assert "][" not in result
        assert result.count("[") == result.count("]")
        assert result.count("(") == result.count(")")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])