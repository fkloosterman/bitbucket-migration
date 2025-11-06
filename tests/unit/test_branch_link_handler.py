"""
Unit tests for BranchLinkHandler.

Tests the branch link rewriting functionality including both URL patterns
and URL encoding for special characters.
"""

import pytest

from bitbucket_migration.services.branch_link_handler import BranchLinkHandler


class TestBranchLinkHandler:
    """Test BranchLinkHandler functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_environment, mock_state):
        """Set up test fixtures."""
        self.handler = BranchLinkHandler(mock_environment, mock_state)
        yield

    @pytest.mark.parametrize("url,expected_branch", [
        # /branch/ pattern tests
        ("https://bitbucket.org/test_workspace/test_repo/branch/main", "main"),
        ("https://bitbucket.org/test_workspace/test_repo/branch/feature-branch", "feature-branch"),
        ("https://bitbucket.org/test_workspace/test_repo/branch/feature/my-branch", "feature/my-branch"),
        ("https://bitbucket.org/test_workspace/test_repo/branch/release/v1.0.0", "release/v1.0.0"),
        ("https://bitbucket.org/test_workspace/test_repo/branch/fix/bug-123", "fix/bug-123"),

        # /commits/branch/ pattern tests
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/main", "main"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/feature-branch", "feature-branch"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/feature/my-branch", "feature/my-branch"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/release/v1.0.0", "release/v1.0.0"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/fix/bug-123", "fix/bug-123"),
    ])
    def test_can_handle_both_patterns(self, url, expected_branch):
        """Test that handler can detect both URL patterns."""
        assert self.handler.can_handle(url) is True

    @pytest.mark.parametrize("url", [
        "https://bitbucket.org/test_workspace/test_repo/issues/123",
        "https://bitbucket.org/test_workspace/test_repo/pull-requests/45",
        "https://bitbucket.org/test_workspace/test_repo/commits/abc123",
        "https://github.com/owner/repo/tree/main",
        "https://example.com",
    ])
    def test_can_handle_rejects_non_matching_urls(self, url):
        """Test that handler rejects non-matching URLs."""
        assert self.handler.can_handle(url) is False

    @pytest.mark.parametrize("url,expected_branch,expected_encoded", [
        # Basic branch names
        ("https://bitbucket.org/test_workspace/test_repo/branch/main", "main", "main"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/main", "main", "main"),

        # Branch names with slashes
        ("https://bitbucket.org/test_workspace/test_repo/branch/feature/my-branch", "feature/my-branch", "feature%2Fmy-branch"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/feature/my-branch", "feature/my-branch", "feature%2Fmy-branch"),

        # Branch names with special characters
        ("https://bitbucket.org/test_workspace/test_repo/branch/fix#123", "fix#123", "fix%23123"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/fix#123", "fix#123", "fix%23123"),

        ("https://bitbucket.org/test_workspace/test_repo/branch/branch with spaces", "branch with spaces", "branch%20with%20spaces"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/branch with spaces", "branch with spaces", "branch%20with%20spaces"),

        ("https://bitbucket.org/test_workspace/test_repo/branch/user@domain", "user@domain", "user%40domain"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/user@domain", "user@domain", "user%40domain"),

        # Complex branch names
        ("https://bitbucket.org/test_workspace/test_repo/branch/release/v1.0.0-beta", "release/v1.0.0-beta", "release%2Fv1.0.0-beta"),
        ("https://bitbucket.org/test_workspace/test_repo/commits/branch/release/v1.0.0-beta", "release/v1.0.0-beta", "release%2Fv1.0.0-beta"),
    ])
    def test_handle_url_encoding(self, url, expected_branch, expected_encoded):
        """Test URL encoding of branch names with special characters."""
        context = {'details': []}
        result = self.handler.handle(url, context)

        assert result is not None
        expected_gh_url = f"https://github.com/test_owner/test_repo/tree/{expected_encoded}"
        
        # Note should be present in result
        assert f"`{expected_branch}`" in result
        assert expected_gh_url in result

        # Verify tracking information
        assert 'details' in context
        assert len(context['details']) == 1
        link_detail = context['details'][0]
        assert link_detail['original'] == url
        assert link_detail['rewritten'] == result
        assert link_detail['type'] == 'branch_link'
        assert link_detail['reason'] == 'mapped'

    def test_handle_non_matching_url(self):
        """Test handling of non-matching URLs."""
        context = {'details': []}
        result = self.handler.handle("https://example.com", context)

        assert result is None
        assert len(context['details']) == 0

    def test_priority(self):
        """Test handler priority."""
        assert self.handler.get_priority() == 4

    def test_pattern_compilation(self):
        """Test that patterns are properly compiled."""
        # Test that the pattern works correctly
        pattern1 = r'https://bitbucket\.org/test_workspace/test_repo/branch/(.+)'
        pattern2 = r'https://bitbucket\.org/test_workspace/test_repo/commits/branch/(.+)'
        combined_pattern = f'(?:{pattern1})|(?:{pattern2})'

        assert self.handler.PATTERN.pattern == combined_pattern

    @pytest.mark.parametrize("url", [
        "https://bitbucket.org/test_workspace/test_repo/branch/feature/my-branch",
        "https://bitbucket.org/test_workspace/test_repo/commits/branch/feature/my-branch",
        "https://bitbucket.org/test_workspace/test_repo/branch/fix%23123",
        "https://bitbucket.org/test_workspace/test_repo/commits/branch/fix%23123",
    ])
    def test_github_url_uses_tree_path(self, url):
        """Test that GitHub URLs use /tree/ path instead of /commits/."""
        context = {'details': []}
        result = self.handler.handle(url, context)

        assert result is not None
        # Should contain /tree/ not /commits/
        assert "github.com/test_owner/test_repo/tree/" in result
        assert "github.com/test_owner/test_repo/commits/" not in result

    def test_branch_name_extraction_from_groups(self):
        """Test that branch names are correctly extracted from either capture group."""
        # Test /branch/ pattern (group 1)
        url1 = "https://bitbucket.org/test_workspace/test_repo/branch/test-branch"
        match1 = self.handler.PATTERN.match(url1)
        assert match1 is not None
        assert match1.group(1) == "test-branch"
        assert match1.group(2) is None

        # Test /commits/branch/ pattern (group 2)
        url2 = "https://bitbucket.org/test_workspace/test_repo/commits/branch/test-branch"
        match2 = self.handler.PATTERN.match(url2)
        assert match2 is not None
        assert match2.group(1) is None
        assert match2.group(2) == "test-branch"

        # Test that handler correctly uses either group
        context1 = {'details': []}
        context2 = {'details': []}
        result1 = self.handler.handle(url1, context1)
        result2 = self.handler.handle(url2, context2)

        assert result1 is not None
        assert result2 is not None
        assert "test-branch" in result1
        assert "test-branch" in result2
        
        # Verify context was updated
        assert 'details' in context1
        assert 'details' in context2