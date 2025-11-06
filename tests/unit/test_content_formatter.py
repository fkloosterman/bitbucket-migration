"""
Tests for content formatters.

Tests the core formatting logic that transforms Bitbucket content to GitHub format,
including user mapping, date formatting, link rewriting integration, and inline images.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from bitbucket_migration.formatters.content_formatter import (
    IssueContentFormatter,
    PullRequestContentFormatter,
    CommentContentFormatter
)


class TestContentFormatter:
    """Test the concrete formatter implementations for date formatting."""

    def test_format_date_valid_iso_issue_formatter(self):
        """Test formatting valid ISO date string using IssueContentFormatter."""
        user_mapper = MagicMock()
        link_rewriter = MagicMock()
        attachment_handler = MagicMock()
        formatter = IssueContentFormatter(user_mapper, link_rewriter, attachment_handler)
        
        result = formatter._format_date("2024-01-15T10:30:45.000000+00:00")
        
        assert result == "January 15, 2024 at 10:30 AM UTC"

    def test_format_date_valid_z_suffix_comment_formatter(self):
        """Test formatting date with Z suffix using CommentContentFormatter."""
        user_mapper = MagicMock()
        link_rewriter = MagicMock()
        attachment_handler = MagicMock()
        formatter = CommentContentFormatter(user_mapper, link_rewriter, attachment_handler)
        
        result = formatter._format_date("2024-01-15T10:30:45Z")
        
        assert result == "January 15, 2024 at 10:30 AM UTC"

    def test_format_date_empty_string_pr_formatter(self):
        """Test formatting empty date string using PullRequestContentFormatter."""
        user_mapper = MagicMock()
        link_rewriter = MagicMock()
        attachment_handler = MagicMock()
        formatter = PullRequestContentFormatter(user_mapper, link_rewriter, attachment_handler)
        
        result = formatter._format_date("")
        
        assert result == ""

    def test_format_date_none_issue_formatter(self):
        """Test formatting None date using IssueContentFormatter."""
        user_mapper = MagicMock()
        link_rewriter = MagicMock()
        attachment_handler = MagicMock()
        formatter = IssueContentFormatter(user_mapper, link_rewriter, attachment_handler)
        
        result = formatter._format_date(None)
        
        assert result == ""

    def test_format_date_invalid_format_comment_formatter(self):
        """Test formatting invalid date format (returns original) using CommentContentFormatter."""
        user_mapper = MagicMock()
        link_rewriter = MagicMock()
        attachment_handler = MagicMock()
        formatter = CommentContentFormatter(user_mapper, link_rewriter, attachment_handler)
        
        result = formatter._format_date("invalid-date")
        
        assert result == "invalid-date"


class TestIssueContentFormatter:
    """Test issue content formatting."""

    @pytest.fixture
    def mock_formatter(self):
        """Create mock dependencies for IssueContentFormatter."""
        user_mapper = MagicMock()
        link_rewriter = MagicMock()
        attachment_handler = MagicMock()
        return IssueContentFormatter(user_mapper, link_rewriter, attachment_handler)

    @pytest.fixture
    def sample_issue(self):
        """Create a sample Bitbucket issue."""
        return {
            'id': 123,
            'title': 'Test Issue',
            'content': {
                'raw': 'This is a test issue description.'
            },
            'state': 'new',
            'kind': 'bug',
            'priority': 'major',
            'created_on': '2024-01-15T10:30:45.000000+00:00',
            'updated_on': '2024-01-16T14:20:30.000000+00:00',
            'reporter': {
                'display_name': 'Test User',
                'account_id': 'test-account-123'
            },
            'links': {
                'html': {
                    'href': 'https://bitbucket.org/test/repo/issues/123'
                }
            }
        }

    def test_format_basic_issue(self, mock_formatter, sample_issue):
        """Test formatting a basic issue."""
        # Mock the link rewriter to return unchanged content
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            'This is a test issue description.', 0, [], 0, 0, [], []
        )
        
        # Mock attachment handler
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            'This is a test issue description.', []
        )
        
        # Mock user mapper to return None (no GitHub mapping)
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, links_count, inline_images = mock_formatter.format(sample_issue)
        
        # Verify the formatted content includes metadata
        assert 'Test User** *(no GitHub account)*' in result_body
        assert 'January 15, 2024 at 10:30 AM UTC' in result_body
        assert 'https://bitbucket.org/test/repo/issues/123' in result_body
        assert 'bug' in result_body
        assert 'major' in result_body
        assert 'This is a test issue description.' in result_body
        
        assert links_count == 0
        assert inline_images == []

    def test_format_issue_with_mapped_user(self, mock_formatter, sample_issue):
        """Test formatting issue with user mapped to GitHub."""
        # Setup user mapper to return GitHub username
        mock_formatter.user_mapper.map_user.return_value = 'github_user'
        
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_issue['content']['raw'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_issue['content']['raw'], []
        )
        
        result_body, _, _ = mock_formatter.format(sample_issue)
        
        # Should use GitHub username
        assert '@github_user' in result_body
        assert '* *(no GitHub account)*' not in result_body

    def test_format_issue_with_deleted_user(self, mock_formatter, sample_issue):
        """Test formatting issue with deleted user."""
        # Simulate deleted user (no reporter info)
        issue_with_deleted_user = sample_issue.copy()
        issue_with_deleted_user['reporter'] = None
        
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_issue['content']['raw'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_issue['content']['raw'], []
        )
        
        result_body, _, _ = mock_formatter.format(issue_with_deleted_user)
        
        # Should show as deleted user
        assert 'Unknown (deleted user)' in result_body

    def test_format_issue_with_inline_images(self, mock_formatter, sample_issue):
        """Test formatting issue with inline images."""
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_issue['content']['raw'], 0, [], 0, 0, [], []
        )
        
        # Mock inline images returned
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            'This is a test issue description.', 
            [{'filename': 'test.png', 'url': 'https://bitbucket.org/test/image.png'}]
        )
        
        result_body, _, inline_images = mock_formatter.format(sample_issue)
        
        assert len(inline_images) == 1
        assert inline_images[0]['filename'] == 'test.png'

    def test_format_issue_skip_link_rewriting(self, mock_formatter, sample_issue):
        """Test formatting issue with link rewriting skipped."""
        # Setup all mocks to provide expected return values
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            'mocked_content', 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_issue['content']['raw'], []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, links_count, _ = mock_formatter.format(
            sample_issue,
            skip_link_rewriting=True
        )
        
        # Link rewriter should not be called when skipping
        mock_formatter.link_rewriter.rewrite_links.assert_not_called()
        
        # Should still format metadata
        assert 'Test User' in result_body
        assert 'January 15, 2024 at 10:30 AM UTC' in result_body
        assert links_count == 0

    def test_format_issue_with_link_rewriting(self, mock_formatter, sample_issue):
        """Test formatting issue with link rewriting enabled."""
        # Mock link rewriter to return rewritten content
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            'Rewritten content with links', 2, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            'Rewritten content with links', []
        )
        
        result_body, links_count, _ = mock_formatter.format(sample_issue)
        
        # Link rewriter should be called
        mock_formatter.link_rewriter.rewrite_links.assert_called_once()
        
        # Should use rewritten content
        assert 'Rewritten content with links' in result_body
        assert links_count == 2

    def test_format_issue_custom_date_formatting(self, mock_formatter):
        """Test date formatting edge cases."""
        issue = {
            'id': 123,
            'content': {'raw': 'Test'},
            'reporter': {'display_name': 'User'},
            'created_on': '2023-12-25T23:59:59.999999+00:00',
            'links': {'html': {'href': 'https://test.com'}}
        }
        
        mock_formatter.link_rewriter.rewrite_links.return_value = ('Test', 0, [], 0, 0, [], [])
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = ('Test', [])
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, _, _ = mock_formatter.format(issue)
        
        # Should format Christmas date correctly
        assert 'December 25, 2023 at 11:59 PM UTC' in result_body


class TestPullRequestContentFormatter:
    """Test pull request content formatting."""

    @pytest.fixture
    def mock_formatter(self):
        """Create mock dependencies for PullRequestContentFormatter."""
        user_mapper = MagicMock()
        link_rewriter = MagicMock()
        attachment_handler = MagicMock()
        return PullRequestContentFormatter(user_mapper, link_rewriter, attachment_handler)

    @pytest.fixture
    def sample_pr(self):
        """Create a sample Bitbucket PR."""
        return {
            'id': 456,
            'title': 'Test PR',
            'description': 'This is a test PR description.',
            'state': 'OPEN',
            'source': {'branch': {'name': 'feature-branch'}},
            'destination': {'branch': {'name': 'main'}},
            'created_on': '2024-01-15T10:30:45.000000+00:00',
            'updated_on': '2024-01-16T14:20:30.000000+00:00',
            'author': {
                'display_name': 'PR Author',
                'account_id': 'author-123'
            },
            'links': {
                'html': {
                    'href': 'https://bitbucket.org/test/repo/pull-requests/456'
                }
            }
        }

    def test_format_pr_as_issue(self, mock_formatter, sample_pr):
        """Test formatting PR as issue (for closed PRs)."""
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_pr['description'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_pr['description'], []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, links_count, _ = mock_formatter.format(
            sample_pr, 
            as_issue=True
        )
        
        # Should include PR metadata warning
        assert '⚠️ **This was a Pull Request on Bitbucket (migrated as an issue)**' in result_body
        assert 'PR Author** *(no GitHub account)*' in result_body
        assert 'feature-branch' in result_body
        assert 'main' in result_body
        assert 'January 15, 2024 at 10:30 AM UTC' in result_body
        assert sample_pr['description'] in result_body
        
        # Should include note about PR state
        assert 'Note: This PR was open on Bitbucket' in result_body
        
        assert links_count == 0

    def test_format_pr_as_pr(self, mock_formatter, sample_pr):
        """Test formatting PR as actual PR."""
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_pr['description'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_pr['description'], []
        )
        mock_formatter.user_mapper.map_user.return_value = 'github_author'
        
        result_body, links_count, _ = mock_formatter.format(sample_pr)
        
        # Should not have PR warning
        assert '⚠️' not in result_body
        
        # Should have simple PR format
        assert 'Migrated from Bitbucket' in result_body
        assert '@github_author' in result_body
        assert sample_pr['description'] in result_body
        
        # Should not include branch info
        assert 'feature-branch' not in result_body

    def test_format_pr_with_mapped_author(self, mock_formatter, sample_pr):
        """Test PR formatting with GitHub-mapped author."""
        mock_formatter.user_mapper.map_user.return_value = 'github_author'
        
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_pr['description'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_pr['description'], []
        )
        
        result_body, _, _ = mock_formatter.format(sample_pr)
        
        # Should use GitHub username
        assert '@github_author' in result_body

    def test_format_pr_with_deleted_author(self, mock_formatter, sample_pr):
        """Test PR formatting with deleted author."""
        # Simulate deleted author
        pr_with_deleted_author = sample_pr.copy()
        pr_with_deleted_author['author'] = None
        
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_pr['description'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_pr['description'], []
        )
        
        result_body, _, _ = mock_formatter.format(pr_with_deleted_author)
        
        # Should show as deleted user
        assert 'Unknown (deleted user)' in result_body

    def test_format_pr_skip_link_rewriting(self, mock_formatter, sample_pr):
        """Test PR formatting with link rewriting skipped."""
        # Setup all mocks to provide expected return values
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            'mocked_content', 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_pr['description'], []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, links_count, _ = mock_formatter.format(
            sample_pr,
            skip_link_rewriting=True
        )
        
        # Link rewriter should not be called when skipping
        mock_formatter.link_rewriter.rewrite_links.assert_not_called()
        
        assert links_count == 0

    def test_format_pr_with_inline_images(self, mock_formatter, sample_pr):
        """Test PR formatting with inline images."""
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_pr['description'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_pr['description'],
            [{'filename': 'screenshot.png', 'url': 'https://bitbucket.org/test/screenshot.png'}]
        )
        
        result_body, _, inline_images = mock_formatter.format(sample_pr)
        
        assert len(inline_images) == 1
        assert inline_images[0]['filename'] == 'screenshot.png'

    def test_format_pr_merged_state(self, mock_formatter):
        """Test PR formatting for merged PR."""
        pr = {
            'id': 789,
            'title': 'Merged PR',
            'description': 'This PR was merged.',
            'state': 'MERGED',
            'source': {'branch': {'name': 'feature'}},
            'destination': {'branch': {'name': 'main'}},
            'created_on': '2024-01-15T10:30:45.000000+00:00',
            'author': {'display_name': 'Author'},
            'links': {'html': {'href': 'https://test.com'}}
        }
        
        mock_formatter.link_rewriter.rewrite_links.return_value = (pr['description'], 0, [], 0, 0, [], [])
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (pr['description'], [])
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, _, _ = mock_formatter.format(pr, as_issue=True)
        
        # Should mention it was merged
        assert 'Note: This PR was merged on Bitbucket' in result_body


class TestCommentContentFormatter:
    """Test comment content formatting."""

    @pytest.fixture
    def mock_formatter(self):
        """Create mock dependencies for CommentContentFormatter."""
        user_mapper = MagicMock()
        link_rewriter = MagicMock()
        attachment_handler = MagicMock()
        return CommentContentFormatter(user_mapper, link_rewriter, attachment_handler)

    @pytest.fixture
    def sample_comment(self):
        """Create a sample Bitbucket comment."""
        return {
            'id': 999,
            'content': {
                'raw': 'This is a test comment.'
            },
            'created_on': '2024-01-15T10:30:45.000000+00:00',
            'user': {
                'display_name': 'Commenter',
                'account_id': 'commenter-123'
            }
        }

    def test_format_basic_comment(self, mock_formatter, sample_comment):
        """Test formatting a basic comment."""
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_comment['content']['raw'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_comment['content']['raw'], []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, links_count, _ = mock_formatter.format(
            sample_comment,
            item_type='issue',
            item_number=123
        )
        
        # Should include commenter and date
        assert '**Comment by **Commenter** *(no GitHub account)* on January 15, 2024 at 10:30 AM UTC:**' in result_body
        assert 'This is a test comment.' in result_body
        assert links_count == 0

    def test_format_comment_with_mapped_user(self, mock_formatter, sample_comment):
        """Test formatting comment with GitHub-mapped user."""
        mock_formatter.user_mapper.map_user.return_value = 'github_commenter'
        
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_comment['content']['raw'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_comment['content']['raw'], []
        )
        
        result_body, _, _ = mock_formatter.format(
            sample_comment,
            item_type='issue',
            item_number=123
        )
        
        # Should use GitHub username
        assert '@github_commenter' in result_body
        assert '* *(no GitHub account)*' not in result_body

    def test_format_comment_with_inline_code_context(self, mock_formatter, sample_comment):
        """Test formatting comment with inline code context."""
        comment_with_inline = sample_comment.copy()
        comment_with_inline['inline'] = {
            'path': 'src/main.py',
            'to': 42,
            'from': 40
        }
        
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            comment_with_inline['content']['raw'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            comment_with_inline['content']['raw'], []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, _, _ = mock_formatter.format(
            comment_with_inline,
            item_type='pr',
            item_number=456,
            commit_id='abc123def456'
        )
        
        # Should include code context (actual format may be slightly different)
        assert '💬 **Code comment on `src/main.py`' in result_body
        assert 'line 42' in result_body
        assert 'abc123d' in result_body

    def test_format_comment_with_changes(self, mock_formatter, sample_comment):
        """Test formatting comment with change log."""
        changes = [
            {
                'changes': {
                    'priority': {'old': 'minor', 'new': 'major'},
                    'assignee': {'old': 'user1', 'new': 'user2'}
                }
            }
        ]
        
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_comment['content']['raw'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_comment['content']['raw'], []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, _, _ = mock_formatter.format(
            sample_comment,
            changes=changes
        )
        
        # Should include change information (format may be slightly different)
        assert 'priority' in result_body
        assert 'minor' in result_body
        assert 'major' in result_body
        assert 'assignee' in result_body
        assert 'user1' in result_body
        assert 'user2' in result_body

    def test_format_comment_with_inline_images(self, mock_formatter, sample_comment):
        """Test formatting comment with inline images."""
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_comment['content']['raw'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_comment['content']['raw'],
            [{'filename': 'error.png', 'url': 'https://bitbucket.org/test/error.png'}]
        )
        
        result_body, _, inline_images = mock_formatter.format(
            sample_comment,
            item_type='issue',
            item_number=123
        )
        
        assert len(inline_images) == 1
        assert inline_images[0]['filename'] == 'error.png'

    def test_format_comment_skip_link_rewriting(self, mock_formatter, sample_comment):
        """Test formatting comment with link rewriting skipped."""
        # Setup all mocks to provide expected return values
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            'mocked_content', 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_comment['content']['raw'], []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, links_count, _ = mock_formatter.format(
            sample_comment,
            item_type='issue',
            item_number=123,
            skip_link_rewriting=True
        )
        
        # Link rewriter should not be called when skipping
        mock_formatter.link_rewriter.rewrite_links.assert_not_called()
        
        assert links_count == 0

    def test_format_comment_with_link_rewriting(self, mock_formatter, sample_comment):
        """Test formatting comment with link rewriting enabled."""
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            'Comment with rewritten links', 1, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            'Comment with rewritten links', []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        result_body, links_count, _ = mock_formatter.format(
            sample_comment,
            item_type='issue',
            item_number=123
        )
        
        # Link rewriter should be called
        mock_formatter.link_rewriter.rewrite_links.assert_called_once()
        
        assert 'Comment with rewritten links' in result_body
        assert links_count == 1

    def test_format_comment_context_parameters(self, mock_formatter, sample_comment):
        """Test comment formatting with different context parameters."""
        mock_formatter.link_rewriter.rewrite_links.return_value = (
            sample_comment['content']['raw'], 0, [], 0, 0, [], []
        )
        mock_formatter.attachment_handler.extract_and_download_inline_images.return_value = (
            sample_comment['content']['raw'], []
        )
        mock_formatter.user_mapper.map_user.return_value = None
        
        # Call with different context
        result_body, _, _ = mock_formatter.format(
            sample_comment,
            item_type='pr',
            item_number=789,
            commit_id='commit123',
            comment_seq=1,
            comment_id=999
        )
        
        # Link rewriter should be called with correct context
        mock_formatter.link_rewriter.rewrite_links.assert_called_with(
            'This is a test comment.',
            'pr',
            789,
            comment_seq=1,
            comment_id=999
        )