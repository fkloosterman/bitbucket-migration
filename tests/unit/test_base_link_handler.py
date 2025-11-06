"""
Unit tests for BaseLinkHandler utility methods.

Tests the URL encoding functionality and other base handler methods.
"""

import pytest

from bitbucket_migration.services.base_link_handler import BaseLinkHandler
from bitbucket_migration.services.issue_link_handler import IssueLinkHandler
from bitbucket_migration.services.branch_link_handler import BranchLinkHandler
from bitbucket_migration.config.migration_config import LinkRewritingConfig


class TestEncodeUrlComponent:
    """Test the encode_url_component static method."""

    @pytest.mark.parametrize("input_str,safe,expected", [
        # Basic encoding tests
        ("feature/my-branch", "", "feature%2Fmy-branch"),
        ("path/to/file.py", "/", "path/to/file.py"),
        ("fix#123", "", "fix%23123"),
        ("branch with spaces", "", "branch%20with%20spaces"),
        ("user@domain.com", "", "user%40domain.com"),
        ("file+plus", "", "file%2Bplus"),
        ("file%percent", "", "file%25percent"),
        ("file&amp", "", "file%26amp"),
        ("file=equals", "", "file%3Dequals"),
        ("file?question", "", "file%3Fquestion"),
        ("file[squares]", "", "file%5Bsquares%5D"),
        ("file{braces}", "", "file%7Bbraces%7D"),
        ("file|pipe", "", "file%7Cpipe"),
        ("file^caret", "", "file%5Ecaret"),
        ("file`backtick", "", "file%60backtick"),
        ("file~tilde", "", "file~tilde"),  # tilde is safe by default
        ("file.dots", "", "file.dots"),
        ("file-dashes", "", "file-dashes"),
        ("file_underscores", "", "file_underscores"),
        ("", "", ""),
        ("normal_chars_123", "", "normal_chars_123"),
    ])
    def test_basic_encoding(self, input_str, safe, expected):
        """Test basic URL encoding functionality."""
        result = BaseLinkHandler.encode_url_component(input_str, safe=safe)
        assert result == expected

    def test_safe_characters_preserved(self):
        """Test that safe characters are not encoded."""
        # Test with forward slash as safe
        result = BaseLinkHandler.encode_url_component("path/to/file.py", safe="/")
        assert result == "path/to/file.py"

        # Test with multiple safe characters
        result = BaseLinkHandler.encode_url_component("path/to/file.py", safe="/.")
        assert result == "path/to/file.py"

        # Test with no safe characters (default behavior)
        result = BaseLinkHandler.encode_url_component("path/to/file.py", safe="")
        assert result == "path%2Fto%2Ffile.py"

    def test_special_characters_common_in_git(self):
        """Test encoding of characters commonly found in Git branch names and paths."""
        test_cases = [
            ("feature/branch-name", "feature%2Fbranch-name"),
            ("release/v1.0.0", "release%2Fv1.0.0"),
            ("hotfix/bug-123", "hotfix%2Fbug-123"),
            ("user/feature-branch", "user%2Ffeature-branch"),
            ("main", "main"),  # Should remain unchanged
            ("master", "master"),  # Should remain unchanged
        ]

        for input_str, expected in test_cases:
            result = BaseLinkHandler.encode_url_component(input_str)
            assert result == expected

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty string
        assert BaseLinkHandler.encode_url_component("") == ""

        # String with only safe characters
        assert BaseLinkHandler.encode_url_component("abc123") == "abc123"

        # String with only unsafe characters
        assert BaseLinkHandler.encode_url_component(" /#?") == "%20%2F%23%3F"

        # Unicode characters (should be encoded)
        assert BaseLinkHandler.encode_url_component("café") == "caf%C3%A9"

    def test_method_is_static(self, mock_environment, mock_state):
        """Test that the method is static and can be called without instance."""
        # Should work without creating an instance
        result = BaseLinkHandler.encode_url_component("test/branch")
        assert result == "test%2Fbranch"

        # Should also work on instance (though not recommended for static method)
        # Note: We can't instantiate BaseLinkHandler directly since it's abstract,
        # but we can test that the method exists and is callable on subclasses
        handler = IssueLinkHandler(mock_environment, mock_state)
        result = handler.encode_url_component("test/branch")
        assert result == "test%2Fbranch"


class TestBaseLinkHandlerMethods:
    """Test other BaseLinkHandler methods using a concrete implementation."""

    def test_priority_default(self, mock_environment, mock_state):
        """Test default priority value."""
        handler = IssueLinkHandler(mock_environment, mock_state)
        assert handler.get_priority() == 1  # IssueLinkHandler sets priority=1

    def test_priority_custom(self, mock_environment, mock_state):
        """Test custom priority value."""
        # BranchLinkHandler sets priority=4
        handler = BranchLinkHandler(mock_environment, mock_state)
        assert handler.get_priority() == 4

    def test_can_handle_with_pattern(self, mock_environment, mock_state):
        """Test can_handle behavior with a pattern set."""
        handler = IssueLinkHandler(mock_environment, mock_state)
        # Should return True for URLs matching the pattern
        assert handler.can_handle("https://bitbucket.org/test_workspace/test_repo/issues/123") is True
        # Should return False for non-matching URLs
        assert handler.can_handle("https://example.com") is False

    def test_handle_implemented(self, mock_environment, mock_state):
        """Test that handle method is implemented in concrete classes."""
        handler = IssueLinkHandler(mock_environment, mock_state)
        # The handle method should be implemented in the concrete class
        # For non-matching URLs, it should return None
        context = {'details': []}
        result = handler.handle("https://example.com", context)
        assert result is None


class TestFormatNote:
    """Test the format_note method functionality."""

    def test_format_note_without_template_config(self, mock_environment, mock_state):
        """Test format_note returns empty string when no template config provided."""
        # Create environment without template config
        mock_environment.config.link_rewriting_config.enable_notes = False
        handler = IssueLinkHandler(mock_environment, mock_state)
        result = handler.format_note("issue_link", bb_num="123", bb_url="https://example.com")
        assert result == ""

    def test_format_note_with_notes_disabled(self, mock_environment, mock_state):
        """Test format_note returns empty string when notes are disabled."""
        # Disable notes in config
        mock_environment.config.link_rewriting_config.enable_notes = False
        
        handler = IssueLinkHandler(mock_environment, mock_state)
        result = handler.format_note("issue_link", bb_num="123", bb_url="https://example.com")
        assert result == ""

    def test_format_note_successful_interpolation(self, mock_environment, mock_state):
        """Test format_note with successful template interpolation."""
        # Create config with custom template
        mock_environment.config.link_rewriting_config.note_templates = {
            'issue_link': 'Issue #{bb_num} from {bb_url}',
            'default': 'Migrated link'
        }
        
        handler = IssueLinkHandler(mock_environment, mock_state)
        result = handler.format_note("issue_link", bb_num="123", bb_url="https://bitbucket.org")
        assert result == "Issue #123 from https://bitbucket.org"

    def test_format_note_missing_variables(self, mock_environment, mock_state):
        """Test format_note handles missing template variables gracefully."""
        # Create config with template that requires missing variables
        mock_environment.config.link_rewriting_config.note_templates = {
            'issue_link': 'Issue #{bb_num} from {bb_url}',
            'default': 'Migrated link'
        }
        
        handler = IssueLinkHandler(mock_environment, mock_state)
        # Missing bb_url variable should trigger fallback to default template
        result = handler.format_note("issue_link", bb_num="123")
        assert result == "Migrated link"

    def test_format_note_fallback_to_default(self, mock_environment, mock_state):
        """Test format_note falls back to default template for unknown link types."""
        # Create config with default template
        mock_environment.config.link_rewriting_config.note_templates = {
            'default': 'Migrated link'
        }
        
        handler = IssueLinkHandler(mock_environment, mock_state)
        result = handler.format_note("unknown_link_type", bb_num="123")
        assert result == "Migrated link"

    def test_format_note_default_templates(self, mock_environment, mock_state):
        """Test format_note with default templates from LinkRewritingConfig."""
        # Use default templates (already set in mock)
        handler = IssueLinkHandler(mock_environment, mock_state)

        # Test issue link template
        result = handler.format_note("issue_link", bb_num="123", bb_url="https://bitbucket.org/workspace/repo/issues/123")
        assert result == " *(was [BB #123](https://bitbucket.org/workspace/repo/issues/123))*"

        # Test PR link template
        result = handler.format_note("pr_link", bb_num="456", bb_url="https://bitbucket.org/workspace/repo/pull-requests/456")
        assert result == " *(was [BB PR #456](https://bitbucket.org/workspace/repo/pull-requests/456))*"

        # Test short issue ref template
        result = handler.format_note("short_issue_ref", bb_num="789")
        assert result == " *(was BB `#789`)*"

    def test_format_note_empty_template(self, mock_environment, mock_state):
        """Test format_note with empty template."""
        # Create config with empty template
        mock_environment.config.link_rewriting_config.note_templates = {
            'empty_link': '',
            'default': 'Migrated link'
        }
        
        handler = IssueLinkHandler(mock_environment, mock_state)
        result = handler.format_note("empty_link")
        assert result == ""