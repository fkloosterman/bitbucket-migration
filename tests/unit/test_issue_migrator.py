"""
Unit tests for IssueMigrator.

Tests the core issue migration logic including:
- Issue creation and placeholder handling
- Comment migration and topological sorting
- Attachment handling
- Link rewriting integration
- Error recovery scenarios
"""

from unittest.mock import MagicMock, Mock, patch, call
from typing import Dict, Any, List
import pytest

from bitbucket_migration.migration.issue_migrator import IssueMigrator
from bitbucket_migration.exceptions import MigrationError, APIError, AuthenticationError, NetworkError, ValidationError


@pytest.fixture
def mock_environment():
    """Create a mock MigrationEnvironment for testing."""
    env = MagicMock()
    env.logger = MagicMock()
    
    # Mock clients
    env.clients = MagicMock()
    env.clients.gh = MagicMock()
    env.clients.gh.owner = "test_owner"
    env.clients.gh.repo = "test_repo"
    env.clients.bb = MagicMock()
    
    # Mock services
    env.services = MagicMock()
    env.services.get = MagicMock(side_effect=lambda name: {
        'user_mapper': MagicMock(),
        'link_rewriter': MagicMock(),
        'attachment_handler': MagicMock(),
        'formatter_factory': MagicMock()
    }.get(name))
    
    return env


@pytest.fixture
def mock_state():
    """Create a mock MigrationState for testing."""
    state = MagicMock()
    state.mappings = MagicMock()
    state.mappings.issues = {}
    state.mappings.prs = {}
    state.mappings.milestones = {}
    state.mappings.issue_types = {}
    state.mappings.issue_comments = {}
    state.issue_records = []
    
    return state


@pytest.fixture
def issue_migrator(mock_environment, mock_state):
    """Create an IssueMigrator instance for testing."""
    return IssueMigrator(mock_environment, mock_state)


class TestIssueMigratorInitialization:
    """Test IssueMigrator initialization."""
    
    def test_init_success(self, mock_environment, mock_state):
        """Test successful initialization."""
        migrator = IssueMigrator(mock_environment, mock_state)
        
        assert migrator.environment == mock_environment
        assert migrator.state == mock_state
        assert migrator.logger == mock_environment.logger
        assert migrator.user_mapper is not None
        assert migrator.link_rewriter is not None
        assert migrator.attachment_handler is not None
        assert migrator.formatter_factory is not None


class TestMigrateIssues:
    """Test migrate_issues method."""
    
    def test_migrate_empty_list(self, issue_migrator):
        """Test migrating an empty list of issues."""
        result = issue_migrator.migrate_issues([])
        
        assert result == []
        issue_migrator.logger.info.assert_any_call("No issues to migrate")
    
    def test_migrate_single_issue(self, issue_migrator, mock_environment):
        """Test migrating a single issue."""
        bb_issue = {
            'id': 1,
            'title': 'Test Issue',
            'state': 'open',
            'reporter': {'display_name': 'John Doe'},
            'kind': 'bug',
            'priority': 'major'
        }
        
        # Mock GitHub issue creation
        gh_issue = {'number': 1, 'id': 101}
        mock_environment.clients.gh.create_issue.return_value = gh_issue
        mock_environment.clients.bb.get_attachments.return_value = []
        
        result = issue_migrator.migrate_issues([bb_issue])
        
        assert len(result[0]) == 1
        assert issue_migrator.state.mappings.issues[1] == 1
        mock_environment.clients.gh.create_issue.assert_called_once()
    
    def test_migrate_with_placeholder_gaps(self, issue_migrator, mock_environment):
        """Test migrating issues with gaps (creates placeholders)."""
        bb_issues = [
            {'id': 1, 'title': 'Issue 1', 'state': 'open'},
            {'id': 5, 'title': 'Issue 5', 'state': 'open'}  # Gap from 2-4
        ]
        
        # Mock GitHub issue creation
        mock_environment.clients.gh.create_issue.return_value = {'number': 1, 'id': 101}
        mock_environment.clients.bb.get_attachments.return_value = []
        
        result = issue_migrator.migrate_issues(bb_issues)
        
        # Should create 5 issues total (1 real, 3 placeholders, 1 real)
        assert len(issue_migrator.state.mappings.issues) == 5
        assert mock_environment.clients.gh.create_issue.call_count == 5
        
        # Verify placeholder creation
        placeholder_calls = [call for call in mock_environment.clients.gh.create_issue.call_args_list
                            if '[Placeholder]' in str(call)]
        assert len(placeholder_calls) == 3
    
    def test_migrate_with_milestone(self, issue_migrator, mock_environment, mock_state):
        """Test migrating issue with milestone."""
        mock_state.mappings.milestones = {
            'v1.0': {'number': 1, 'name': 'v1.0'}
        }
        
        bb_issue = {
            'id': 1,
            'title': 'Test Issue',
            'state': 'open',
            'milestone': {'name': 'v1.0'}
        }
        
        gh_issue = {'number': 1, 'id': 101}
        mock_environment.clients.gh.create_issue.return_value = gh_issue
        mock_environment.clients.bb.get_attachments.return_value = []
        
        issue_migrator.migrate_issues([bb_issue])
        
        # Verify milestone was passed to create_issue
        call_args = mock_environment.clients.gh.create_issue.call_args
        assert call_args[1]['milestone'] == 1
    
    def test_migrate_with_assignee(self, issue_migrator, mock_environment):
        """Test migrating issue with assignee."""
        bb_issue = {
            'id': 1,
            'title': 'Test Issue',
            'state': 'open',
            'assignee': {'display_name': 'Jane Doe'}
        }
        
        # Mock user mapping
        issue_migrator.user_mapper.map_user.return_value = 'janedoe'
        
        gh_issue = {'number': 1, 'id': 101}
        mock_environment.clients.gh.create_issue.return_value = gh_issue
        mock_environment.clients.bb.get_attachments.return_value = []
        
        issue_migrator.migrate_issues([bb_issue])
        
        # Verify assignee was mapped and passed
        call_args = mock_environment.clients.gh.create_issue.call_args
        assert call_args[1]['assignees'] == ['janedoe']
    
    def test_migrate_with_issue_type_native(self, issue_migrator, mock_environment, mock_state):
        """Test migrating issue with native GitHub issue type."""
        # IMPORTANT: issue_types is accessed via self.type_mapping which is set in __init__
        # We need to set it on the migrator instance, not just the state
        issue_migrator.type_mapping = {
            'bug': {
                'id': 'bug_type_id',
                'name': 'Bug',
                'configured_name': 'Bug Report'
            }
        }
        
        bb_issue = {
            'id': 1,
            'title': 'Test Bug',
            'state': 'open',
            'kind': 'bug'
        }
        
        gh_issue = {'number': 1, 'id': 101}
        mock_environment.clients.gh.create_issue.return_value = gh_issue
        mock_environment.clients.bb.get_attachments.return_value = []
        
        result = issue_migrator.migrate_issues([bb_issue])
        
        # Verify native type was passed to create_issue
        call_args = mock_environment.clients.gh.create_issue.call_args
        # The type should be passed as a kwarg
        assert 'type' in call_args[1], f"Type parameter should be in kwargs. Got kwargs: {call_args[1].keys()}"
        assert call_args[1]['type'] == 'Bug', f"Expected type='Bug', got {call_args[1].get('type')}"
        
        # Check type stats to verify native type was recorded correctly
        type_stats = result[1]
        assert type_stats['using_native'] == 1
        assert type_stats['using_labels'] == 0
    
    def test_migrate_with_issue_type_label_fallback(self, issue_migrator, mock_environment, mock_state):
        """Test migrating issue with type falling back to label."""
        mock_state.mappings.issue_types = {}  # No native type mapping
        
        bb_issue = {
            'id': 1,
            'title': 'Test Enhancement',
            'state': 'open',
            'kind': 'enhancement'
        }
        
        gh_issue = {'number': 1, 'id': 101}
        mock_environment.clients.gh.create_issue.return_value = gh_issue
        mock_environment.clients.bb.get_attachments.return_value = []
        
        result = issue_migrator.migrate_issues([bb_issue])
        
        # Verify label was added
        call_args = mock_environment.clients.gh.create_issue.call_args
        assert 'type: enhancement' in call_args[1]['labels']
        
        # Check type stats
        type_stats = result[1]
        assert type_stats['using_labels'] == 1
        assert type_stats['using_native'] == 0
    
    def test_migrate_with_attachments(self, issue_migrator, mock_environment):
        """Test migrating issue with attachments."""
        bb_issue = {
            'id': 1,
            'title': 'Test Issue',
            'state': 'open'
        }
        
        attachments = [
            {
                'name': 'test.txt',
                'links': {'self': {'href': 'http://example.com/test.txt'}}
            }
        ]
        
        gh_issue = {'number': 1, 'id': 101}
        mock_environment.clients.gh.create_issue.return_value = gh_issue
        mock_environment.clients.bb.get_attachments.return_value = attachments
        
        # Mock attachment handling
        issue_migrator.attachment_handler.download_attachment.return_value = '/tmp/test.txt'
        
        issue_migrator.migrate_issues([bb_issue])
        
        # Verify attachment was handled
        issue_migrator.attachment_handler.download_attachment.assert_called_once()
        issue_migrator.attachment_handler.upload_to_github.assert_called_once()
    
    def test_migrate_closed_issue(self, issue_migrator, mock_environment):
        """Test migrating a closed issue."""
        bb_issue = {
            'id': 1,
            'title': 'Closed Issue',
            'state': 'resolved'
        }
        
        gh_issue = {'number': 1, 'id': 101}
        mock_environment.clients.gh.create_issue.return_value = gh_issue
        mock_environment.clients.bb.get_attachments.return_value = []
        
        issue_migrator.migrate_issues([bb_issue])
        
        # Verify issue was created as closed
        create_call = mock_environment.clients.gh.create_issue.call_args
        assert create_call[1]['state'] == 'closed'
        
        # Verify update_issue was called to close it
        mock_environment.clients.gh.update_issue.assert_called_with(1, state='closed')
    
    def test_migrate_open_issues_only_filter(self, issue_migrator, mock_environment):
        """Test open_issues_only filter."""
        bb_issues = [
            {'id': 1, 'title': 'Open Issue', 'state': 'open'},
            {'id': 2, 'title': 'Closed Issue', 'state': 'resolved'}
        ]
        
        gh_issue = {'number': 1, 'id': 101}
        mock_environment.clients.gh.create_issue.return_value = gh_issue
        mock_environment.clients.bb.get_attachments.return_value = []
        
        issue_migrator.migrate_issues(bb_issues, open_issues_only=True)
        
        # Should only create one issue (the open one)
        # Note: Placeholder for #2 is still created to maintain numbering
        assert 1 in issue_migrator.state.mappings.issues
        assert 2 not in issue_migrator.state.mappings.issues


class TestCreateGitHubIssue:
    """Test _create_gh_issue method."""
    
    def test_create_issue_success(self, issue_migrator, mock_environment):
        """Test successful issue creation."""
        mock_environment.clients.gh.create_issue.return_value = {'number': 1, 'id': 101}
        
        result = issue_migrator._create_gh_issue(
            title='Test Issue',
            body='Test body',
            labels=['bug'],
            state='open'
        )
        
        assert result['number'] == 1
        mock_environment.clients.gh.create_issue.assert_called_once()
    
    def test_create_closed_issue(self, issue_migrator, mock_environment):
        """Test creating a closed issue."""
        mock_environment.clients.gh.create_issue.return_value = {'number': 1, 'id': 101}
        
        result = issue_migrator._create_gh_issue(
            title='Test Issue',
            body='Test body',
            state='closed'
        )
        
        # Verify update_issue was called to close it
        mock_environment.clients.gh.update_issue.assert_called_with(1, state='closed')
    
    def test_create_issue_api_error(self, issue_migrator, mock_environment):
        """Test handling API error during issue creation."""
        mock_environment.clients.gh.create_issue.side_effect = APIError("API error")
        
        with pytest.raises(APIError):
            issue_migrator._create_gh_issue(title='Test', body='Test')
    
    def test_create_issue_auth_error(self, issue_migrator, mock_environment):
        """Test handling authentication error during issue creation."""
        mock_environment.clients.gh.create_issue.side_effect = AuthenticationError("Auth failed")
        
        with pytest.raises(AuthenticationError):
            issue_migrator._create_gh_issue(title='Test', body='Test')
    
    def test_create_issue_unexpected_error(self, issue_migrator, mock_environment):
        """Test handling unexpected error during issue creation."""
        mock_environment.clients.gh.create_issue.side_effect = RuntimeError("Unexpected")
        
        with pytest.raises(MigrationError) as exc_info:
            issue_migrator._create_gh_issue(title='Test', body='Test')
        
        assert "Unexpected error creating GitHub issue" in str(exc_info.value)


class TestCommentTopologicalSorting:
    """Test _sort_comments_topologically method."""
    
    def test_sort_flat_comments(self, issue_migrator):
        """Test sorting comments with no parent relationships."""
        comments = [
            {'id': 3, 'content': 'Third'},
            {'id': 1, 'content': 'First'},
            {'id': 2, 'content': 'Second'}
        ]
        
        result = issue_migrator._sort_comments_topologically(comments)
        
        # Should maintain order since no parent relationships
        assert len(result) == 3
        assert all(c in result for c in comments)
    
    def test_sort_nested_comments(self, issue_migrator):
        """Test sorting comments with parent-child relationships."""
        comments = [
            {'id': 2, 'content': 'Reply to 1', 'parent': {'id': 1}},
            {'id': 3, 'content': 'Reply to 2', 'parent': {'id': 2}},
            {'id': 1, 'content': 'Root comment'}
        ]
        
        result = issue_migrator._sort_comments_topologically(comments)
        
        # Verify parents come before children
        ids = [c['id'] for c in result]
        assert ids.index(1) < ids.index(2)
        assert ids.index(2) < ids.index(3)
    
    def test_sort_multiple_trees(self, issue_migrator):
        """Test sorting multiple comment trees."""
        comments = [
            {'id': 5, 'content': 'Second root'},
            {'id': 2, 'content': 'Reply to 1', 'parent': {'id': 1}},
            {'id': 1, 'content': 'First root'},
            {'id': 6, 'content': 'Reply to 5', 'parent': {'id': 5}}
        ]
        
        result = issue_migrator._sort_comments_topologically(comments)
        
        # Verify ordering within each tree
        ids = [c['id'] for c in result]
        assert ids.index(1) < ids.index(2)
        assert ids.index(5) < ids.index(6)
    
    def test_sort_with_missing_parent(self, issue_migrator):
        """Test sorting when parent comment is missing."""
        comments = [
            {'id': 2, 'content': 'Reply to missing', 'parent': {'id': 999}},
            {'id': 1, 'content': 'Root comment'}
        ]
        
        result = issue_migrator._sort_comments_topologically(comments)
        
        # Should handle gracefully
        assert len(result) == 2


class TestUpdateIssueContent:
    """Test update_issue_content method."""
    
    def test_update_content_with_links(self, issue_migrator, mock_environment):
        """Test updating issue content with link rewriting."""
        bb_issue = {
            'id': 1,
            'title': 'Test Issue',
            'content': {'raw': 'Issue with [link](http://example.com)'}
        }
        
        # Mock formatter
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = ('Formatted body', 2, [])
        issue_migrator.formatter_factory.get_issue_formatter.return_value = mock_formatter
        
        mock_environment.clients.bb.get_comments.return_value = []
        mock_environment.clients.bb.get_changes.return_value = []
        
        issue_migrator.update_issue_content(bb_issue, 1)
        
        # Verify issue was updated
        mock_environment.clients.gh.update_issue.assert_called_once()
        assert mock_environment.clients.gh.update_issue.call_args[0] == (1,)
    
    def test_update_content_with_comments(self, issue_migrator, mock_environment):
        """Test updating issue with comments."""
        bb_issue = {'id': 1, 'title': 'Test Issue'}
        
        comments = [
            {'id': 1, 'content': {'raw': 'First comment'}},
            {'id': 2, 'content': {'raw': 'Second comment'}}
        ]
        
        # Mock formatter
        mock_issue_formatter = MagicMock()
        mock_issue_formatter.format.return_value = ('Body', 0, [])
        issue_migrator.formatter_factory.get_issue_formatter.return_value = mock_issue_formatter
        
        mock_comment_formatter = MagicMock()
        mock_comment_formatter.format.return_value = ('Comment body', 0, [])
        issue_migrator.formatter_factory.get_comment_formatter.return_value = mock_comment_formatter
        
        mock_environment.clients.bb.get_comments.return_value = comments
        mock_environment.clients.bb.get_changes.return_value = []
        mock_environment.clients.gh.create_comment.return_value = {'id': 101}
        
        with patch('time.sleep'):  # Skip sleep delays in tests
            issue_migrator.update_issue_content(bb_issue, 1)
        
        # Verify comments were created
        assert mock_environment.clients.gh.create_comment.call_count == 2
    
    def test_update_content_skip_deleted_comments(self, issue_migrator, mock_environment):
        """Test that deleted comments are skipped."""
        bb_issue = {'id': 1, 'title': 'Test Issue'}
        
        comments = [
            {'id': 1, 'content': {'raw': 'Normal comment'}},
            {'id': 2, 'content': {'raw': 'Deleted'}, 'deleted': True}
        ]
        
        # Mock formatter
        mock_issue_formatter = MagicMock()
        mock_issue_formatter.format.return_value = ('Body', 0, [])
        issue_migrator.formatter_factory.get_issue_formatter.return_value = mock_issue_formatter
        
        mock_comment_formatter = MagicMock()
        mock_comment_formatter.format.return_value = ('Comment body', 0, [])
        issue_migrator.formatter_factory.get_comment_formatter.return_value = mock_comment_formatter
        
        mock_environment.clients.bb.get_comments.return_value = comments
        mock_environment.clients.bb.get_changes.return_value = []
        mock_environment.clients.gh.create_comment.return_value = {'id': 101}
        
        with patch('time.sleep'):
            issue_migrator.update_issue_content(bb_issue, 1)
        
        # Should only create one comment (the non-deleted one)
        assert mock_environment.clients.gh.create_comment.call_count == 1
    
    def test_update_content_with_nested_reply(self, issue_migrator, mock_environment, mock_state):
        """Test updating content with nested comment replies."""
        bb_issue = {'id': 1, 'title': 'Test Issue'}
        
        comments = [
            {'id': 1, 'content': {'raw': 'Parent comment'}},
            {'id': 2, 'content': {'raw': 'Reply'}, 'parent': {'id': 1}}
        ]
        
        # Mock formatter
        mock_issue_formatter = MagicMock()
        mock_issue_formatter.format.return_value = ('Body', 0, [])
        issue_migrator.formatter_factory.get_issue_formatter.return_value = mock_issue_formatter
        
        mock_comment_formatter = MagicMock()
        mock_comment_formatter.format.return_value = ('Comment body', 0, [])
        issue_migrator.formatter_factory.get_comment_formatter.return_value = mock_comment_formatter
        
        # Mock comment tracking
        mock_state.mappings.issue_comments = {
            1: {'gh_id': 101, 'body': 'Parent comment body'}
        }
        
        mock_environment.clients.bb.get_comments.return_value = comments
        mock_environment.clients.bb.get_changes.return_value = []
        mock_environment.clients.gh.create_comment.return_value = {'id': 102}
        
        with patch('time.sleep'):
            issue_migrator.update_issue_content(bb_issue, 1)
        
        # Verify reply comment includes parent reference
        reply_call = mock_environment.clients.gh.create_comment.call_args_list[1]
        reply_body = reply_call[0][1]
        assert 'In reply to' in reply_body or 'reply' in reply_body.lower()
    
    def test_update_content_handles_locked_issue(self, issue_migrator, mock_environment):
        """Test handling locked issue when adding comments."""
        bb_issue = {'id': 1, 'title': 'Test Issue'}
        
        comments = [
            {'id': 1, 'content': {'raw': 'Comment'}}
        ]
        
        # Mock formatter
        mock_issue_formatter = MagicMock()
        mock_issue_formatter.format.return_value = ('Body', 0, [])
        issue_migrator.formatter_factory.get_issue_formatter.return_value = mock_issue_formatter
        
        mock_comment_formatter = MagicMock()
        mock_comment_formatter.format.return_value = ('Comment body', 0, [])
        issue_migrator.formatter_factory.get_comment_formatter.return_value = mock_comment_formatter
        
        mock_environment.clients.bb.get_comments.return_value = comments
        mock_environment.clients.bb.get_changes.return_value = []
        
        # Simulate locked issue
        mock_environment.clients.gh.create_comment.side_effect = ValidationError("Issue is locked")
        
        with patch('time.sleep'):
            # Should not raise, just log warning
            issue_migrator.update_issue_content(bb_issue, 1)
        
        issue_migrator.logger.warning.assert_called()


class TestFetchMethods:
    """Test fetch methods for Bitbucket data."""
    
    def test_fetch_attachments_success(self, issue_migrator, mock_environment):
        """Test successful attachment fetching."""
        attachments = [{'name': 'file.txt'}]
        mock_environment.clients.bb.get_attachments.return_value = attachments
        
        result = issue_migrator._fetch_bb_issue_attachments(1)
        
        assert result == attachments
        mock_environment.clients.bb.get_attachments.assert_called_with("issue", 1)
    
    def test_fetch_attachments_api_error(self, issue_migrator, mock_environment):
        """Test handling API error when fetching attachments."""
        mock_environment.clients.bb.get_attachments.side_effect = APIError("API error")
        
        result = issue_migrator._fetch_bb_issue_attachments(1)
        
        # Should return empty list and log warning
        assert result == []
        issue_migrator.logger.warning.assert_called()
    
    def test_fetch_comments_success(self, issue_migrator, mock_environment):
        """Test successful comment fetching."""
        comments = [{'id': 1, 'content': {'raw': 'Comment'}}]
        mock_environment.clients.bb.get_comments.return_value = comments
        
        result = issue_migrator._fetch_bb_issue_comments(1)
        
        assert result == comments
        mock_environment.clients.bb.get_comments.assert_called_with("issue", 1)
    
    def test_fetch_comments_network_error(self, issue_migrator, mock_environment):
        """Test handling network error when fetching comments."""
        mock_environment.clients.bb.get_comments.side_effect = NetworkError("Network error")
        
        result = issue_migrator._fetch_bb_issue_comments(1)
        
        assert result == []
        issue_migrator.logger.warning.assert_called()
    
    def test_fetch_changes_success(self, issue_migrator, mock_environment):
        """Test successful changes fetching."""
        changes = [{'id': 1, 'changes': {'status': {'old': 'open', 'new': 'closed'}}}]
        mock_environment.clients.bb.get_changes.return_value = changes
        
        result = issue_migrator._fetch_bb_issue_changes(1)
        
        assert result == changes


class TestUtilityMethods:
    """Test utility methods."""
    
    def test_format_date_valid(self, issue_migrator):
        """Test formatting a valid ISO date."""
        date_str = "2024-03-15T14:30:00Z"
        
        result = issue_migrator._format_date(date_str)
        
        assert "March" in result
        assert "2024" in result
        assert "UTC" in result
    
    def test_format_date_invalid(self, issue_migrator):
        """Test formatting an invalid date."""
        date_str = "invalid-date"
        
        result = issue_migrator._format_date(date_str)
        
        # Should return original string
        assert result == date_str
    
    def test_format_date_empty(self, issue_migrator):
        """Test formatting an empty date."""
        result = issue_migrator._format_date("")
        
        assert result == ""