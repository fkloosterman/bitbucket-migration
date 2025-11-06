"""
Tests for BitbucketClient API interactions.

This file tests the Bitbucket API client including:
- Initialization and configuration
- Pagination logic
- Data fetching (issues, PRs, milestones, comments, attachments, changes)
- User info fetching
- Error handling
- Network error scenarios
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
from requests.exceptions import RequestException, HTTPError

from bitbucket_migration.clients.bitbucket_client import BitbucketClient
from bitbucket_migration.exceptions import APIError, AuthenticationError, NetworkError, ValidationError


class TestBitbucketClientInitialization:
    """Test client initialization and configuration."""
    
    def test_init_with_valid_params(self):
        """Test successful client initialization."""
        client = BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token",
            dry_run=False
        )
        
        assert client.workspace == "test-workspace"
        assert client.repo == "test-repo"
        assert client.email == "test@example.com"
        assert client.token == "test-token"
        assert client.dry_run is False
        assert client.base_url == "https://api.bitbucket.org/2.0/repositories/test-workspace/test-repo"
    
    def test_init_dry_run_mode(self):
        """Test dry-run mode initialization."""
        client = BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token",
            dry_run=True
        )
        
        assert client.dry_run is True
    
    def test_init_empty_workspace_raises_error(self):
        """Test that empty workspace raises ValidationError."""
        with pytest.raises(ValidationError, match="workspace cannot be empty"):
            BitbucketClient(workspace="", repo="test-repo", email="test@example.com", token="test-token")
    
    def test_init_whitespace_only_workspace_raises_error(self):
        """Test that whitespace-only workspace raises ValidationError."""
        with pytest.raises(ValidationError, match="workspace cannot be empty"):
            BitbucketClient(workspace="   ", repo="test-repo", email="test@example.com", token="test-token")
    
    def test_init_empty_repo_raises_error(self):
        """Test that empty repo raises ValidationError."""
        with pytest.raises(ValidationError, match="repository cannot be empty"):
            BitbucketClient(workspace="test-workspace", repo="", email="test@example.com", token="test-token")
    
    def test_init_empty_email_raises_error(self):
        """Test that empty email raises ValidationError."""
        with pytest.raises(ValidationError, match="email cannot be empty"):
            BitbucketClient(workspace="test-workspace", repo="test-repo", email="", token="test-token")
    
    def test_init_empty_token_raises_error(self):
        """Test that empty token raises ValidationError."""
        with pytest.raises(ValidationError, match="token cannot be empty"):
            BitbucketClient(workspace="test-workspace", repo="test-repo", email="test@example.com", token="")


class TestBitbucketClientPagination:
    """Test pagination logic."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_paginate_single_page(self, mock_get, client):
        """Test pagination with single page."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [{'id': 1}, {'id': 2}],
            'next': None
        }
        mock_get.return_value = mock_response
        
        results = client._paginate('/test/endpoint')
        
        assert len(results) == 2
        assert results[0]['id'] == 1
        assert results[1]['id'] == 2
    
    @patch('requests.Session.get')
    def test_paginate_multiple_pages(self, mock_get, client):
        """Test pagination across multiple pages."""
        # Page 1
        response1 = Mock()
        response1.status_code = 200
        response1.json.return_value = {
            'values': [{'id': 1}, {'id': 2}],
            'next': 'https://api.bitbucket.org/page2'
        }
        
        # Page 2
        response2 = Mock()
        response2.status_code = 200
        response2.json.return_value = {
            'values': [{'id': 3}, {'id': 4}],
            'next': None
        }
        
        mock_get.side_effect = [response1, response2]
        
        results = client._paginate('/test/endpoint')
        
        assert len(results) == 4
        assert [r['id'] for r in results] == [1, 2, 3, 4]
    
    @patch('requests.Session.get')
    def test_paginate_with_params(self, mock_get, client):
        """Test pagination with query parameters on first request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [{'id': 1}],
            'next': None
        }
        mock_get.return_value = mock_response
        
        results = client._paginate('/test/endpoint', {'pagelen': 100})
        
        # Verify that params were passed to first request
        mock_get.assert_called_once_with('/test/endpoint', params={'pagelen': 100})
        assert len(results) == 1
    
    @patch('requests.Session.get')
    def test_paginate_404_endpoint_not_found(self, mock_get, client):
        """Test pagination with 404 endpoint (should return empty list)."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = HTTPError()
        mock_get.return_value = mock_response
        
        results = client._paginate('/test/endpoint')
        
        # Should return empty list for 404 endpoints
        assert results == []
    
    @patch('requests.Session.get')
    def test_paginate_502_bad_gateway_with_results(self, mock_get, client):
        """Test 502 bad gateway when we already have some results."""
        # First page with results
        response1 = Mock()
        response1.status_code = 200
        response1.json.return_value = {
            'values': [{'id': 1}, {'id': 2}],
            'next': 'https://api.bitbucket.org/page2'
        }
        
        # Second page returns 502
        response2 = Mock()
        response2.status_code = 502
        response2.raise_for_status.side_effect = HTTPError()
        
        mock_get.side_effect = [response1, response2]
        
        results = client._paginate('/test/endpoint')
        
        # Should return what we have so far
        assert len(results) == 2
        assert [r['id'] for r in results] == [1, 2]
    
    @patch('requests.Session.get')
    def test_paginate_502_bad_gateway_no_results(self, mock_get, client):
        """Test 502 bad gateway with no previous results."""
        mock_response = Mock()
        mock_response.status_code = 502
        mock_response.raise_for_status.side_effect = HTTPError()
        mock_get.return_value = mock_response
        
        with pytest.raises(APIError):
            client._paginate('/test/endpoint')
    
    @patch('requests.Session.get')
    def test_paginate_response_without_values(self, mock_get, client):
        """Test pagination with response that doesn't have 'values' key."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 1,
            'data': 'test'
        }
        mock_get.return_value = mock_response
        
        results = client._paginate('/test/endpoint')
        
        # Should treat the response as a single item
        assert len(results) == 1
        assert results[0]['id'] == 1
        assert results[0]['data'] == 'test'


class TestBitbucketClientRepositoryOperations:
    """Test repository operations."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_list_repositories_success(self, mock_get, client):
        """Test successful repository listing."""
        # First page
        response1 = Mock()
        response1.status_code = 200
        response1.json.return_value = {
            'values': [
                {'name': 'repo1', 'description': 'Test repo 1'},
                {'name': 'repo2', 'description': 'Test repo 2'}
            ],
            'next': 'https://api.bitbucket.org/2.0/repositories/test-workspace?page=2'
        }
        
        # Second page
        response2 = Mock()
        response2.status_code = 200
        response2.json.return_value = {
            'values': [
                {'name': 'repo3', 'description': 'Test repo 3'}
            ],
            'next': None
        }
        
        mock_get.side_effect = [response1, response2]
        
        repos = client.list_repositories()
        
        assert len(repos) == 3
        assert repos[0]['name'] == 'repo1'
        assert repos[1]['name'] == 'repo2'
        assert repos[2]['name'] == 'repo3'
    
    @patch('requests.Session.get')
    def test_list_repositories_empty(self, mock_get, client):
        """Test listing repositories when none exist."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [],
            'next': None
        }
        mock_get.return_value = mock_response
        
        repos = client.list_repositories()
        
        assert repos == []


class TestBitbucketClientIssues:
    """Test issue fetching."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_get_issues_success(self, mock_get, client):
        """Test successful issue fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 1, 'title': 'Issue 1'},
                {'id': 2, 'title': 'Issue 2'}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        issues = client.get_issues()
        
        assert len(issues) == 2
        assert issues[0]['id'] == 1
        assert issues[1]['id'] == 2
    
    @patch('requests.Session.get')
    def test_get_issues_sorted_by_id(self, mock_get, client):
        """Test that issues are sorted by ID."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 3, 'title': 'Issue 3'},
                {'id': 1, 'title': 'Issue 1'},
                {'id': 2, 'title': 'Issue 2'}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        issues = client.get_issues()
        
        assert [i['id'] for i in issues] == [1, 2, 3]


class TestBitbucketClientPullRequests:
    """Test pull request fetching."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_get_pull_requests_success(self, mock_get, client):
        """Test successful PR fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 1, 'title': 'PR 1'},
                {'id': 2, 'title': 'PR 2'}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        prs = client.get_pull_requests()
        
        assert len(prs) == 2
        assert prs[0]['id'] == 1
    
    @patch('requests.Session.get')
    def test_get_pull_requests_sorted_by_id(self, mock_get, client):
        """Test that PRs are sorted by ID."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 3, 'title': 'PR 3'},
                {'id': 1, 'title': 'PR 1'},
                {'id': 2, 'title': 'PR 2'}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        prs = client.get_pull_requests()
        
        assert [p['id'] for p in prs] == [1, 2, 3]


class TestBitbucketClientMilestones:
    """Test milestone fetching."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_get_milestones_success(self, mock_get, client):
        """Test successful milestone fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 1, 'name': 'v1.0'},
                {'id': 2, 'name': 'v2.0'}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        milestones = client.get_milestones()
        
        assert len(milestones) == 2
        assert milestones[0]['name'] == 'v1.0'
        assert milestones[1]['name'] == 'v2.0'


class TestBitbucketClientComments:
    """Test comment fetching."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_get_comments_for_issue(self, mock_get, client):
        """Test fetching comments for an issue."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 1, 'content': {'raw': 'Comment 1'}},
                {'id': 2, 'content': {'raw': 'Comment 2'}}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        comments = client.get_comments('issue', 1)
        
        assert len(comments) == 2
        assert comments[0]['id'] == 1
        assert comments[1]['id'] == 2
    
    @patch('requests.Session.get')
    def test_get_comments_for_pr(self, mock_get, client):
        """Test fetching comments for a PR."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 1, 'content': {'raw': 'PR Comment 1'}},
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        comments = client.get_comments('pr', 1)
        
        assert len(comments) == 1
        assert comments[0]['id'] == 1
        
        # Verify correct endpoint was called
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert 'pullrequests/1/comments' in call_args[0][0]
    
    def test_get_comments_invalid_item_type(self, client):
        """Test that invalid item_type raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid item type"):
            client.get_comments('invalid', 1)
    
    def test_get_comments_invalid_issue_id(self, client):
        """Test that invalid issue ID raises ValidationError."""
        with pytest.raises(ValidationError, match="Pull request ID must be a positive integer"):
            client.get_activity(0)


class TestBitbucketClientActivity:
    """Test PR activity fetching."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_get_activity_success(self, mock_get, client):
        """Test successful PR activity fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 1, 'activity_type': 'comment'},
                {'id': 2, 'activity_type': 'approval'}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        activity = client.get_activity(1)
        
        assert len(activity) == 2
        assert activity[0]['activity_type'] == 'comment'
        assert activity[1]['activity_type'] == 'approval'
    
    def test_get_activity_invalid_pr_id(self, client):
        """Test that invalid PR ID raises ValidationError."""
        with pytest.raises(ValidationError, match="Pull request ID must be a positive integer"):
            client.get_activity(0)
    
    def test_get_activity_negative_pr_id(self, client):
        """Test that negative PR ID raises ValidationError."""
        with pytest.raises(ValidationError, match="Pull request ID must be a positive integer"):
            client.get_activity(-1)
    
    def test_get_activity_non_integer_pr_id(self, client):
        """Test that non-integer PR ID raises ValidationError."""
        with pytest.raises(ValidationError, match="Pull request ID must be a positive integer"):
            client.get_activity("not-an-int")


class TestBitbucketClientAttachments:
    """Test attachment fetching."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_get_attachments_for_issue(self, mock_get, client):
        """Test fetching attachments for an issue."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 1, 'name': 'attachment1.png'},
                {'id': 2, 'name': 'attachment2.pdf'}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        attachments = client.get_attachments('issue', 1)
        
        assert len(attachments) == 2
        assert attachments[0]['name'] == 'attachment1.png'
        assert attachments[1]['name'] == 'attachment2.pdf'
    
    @patch('requests.Session.get')
    def test_get_attachments_not_found(self, mock_get, client):
        """Test fetching attachments when none exist (404)."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = HTTPError()
        mock_get.return_value = mock_response
        
        attachments = client.get_attachments('issue', 1)
        
        # Should return empty list for 404
        assert attachments == []
    
    @patch('requests.Session.get')
    def test_get_attachments_for_pr_not_found(self, mock_get, client):
        """Test fetching attachments for PR when API endpoint doesn't exist."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = HTTPError()
        mock_get.return_value = mock_response
        
        attachments = client.get_attachments('pr', 1)
        
        # Should return empty list for PRs with no attachments endpoint
        assert attachments == []
    
    def test_get_attachments_invalid_item_type(self, client):
        """Test that invalid item_type raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid item type"):
            client.get_attachments('invalid', 1)


class TestBitbucketClientChanges:
    """Test issue changes fetching."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_get_changes_success(self, mock_get, client):
        """Test successful changes fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'values': [
                {'id': 1, 'change_type': 'status_changed'},
                {'id': 2, 'change_type': 'assignee_changed'}
            ],
            'next': None
        }
        mock_get.return_value = mock_response
        
        changes = client.get_changes(1)
        
        assert len(changes) == 2
        assert changes[0]['change_type'] == 'status_changed'
        assert changes[1]['change_type'] == 'assignee_changed'
    
    @patch('requests.Session.get')
    def test_get_changes_not_found(self, mock_get, client):
        """Test fetching changes when none exist (404)."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = HTTPError()
        mock_get.return_value = mock_response
        
        changes = client.get_changes(1)
        
        # Should return empty list for 404
        assert changes == []


class TestBitbucketClientUserInfo:
    """Test user information fetching."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_get_user_info_success(self, mock_get, client):
        """Test successful user info fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'username': 'testuser',
            'display_name': 'Test User',
            'account_id': '12345',
            'nickname': 'test'
        }
        mock_get.return_value = mock_response
        
        user_info = client.get_user_info('12345')
        
        assert user_info is not None
        assert user_info['username'] == 'testuser'
        assert user_info['display_name'] == 'Test User'
        assert user_info['account_id'] == '12345'
        assert user_info['nickname'] == 'test'
    
    @patch('requests.Session.get')
    def test_get_user_info_not_found(self, mock_get, client):
        """Test user not found returns None."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        user_info = client.get_user_info('12345')
        
        assert user_info is None
    
    @patch('requests.Session.get')
    def test_get_user_info_partial_data(self, mock_get, client):
        """Test user info with missing fields."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'username': 'testuser',
            'account_id': '12345'
            # Missing display_name and nickname
        }
        mock_get.return_value = mock_response
        
        user_info = client.get_user_info('12345')
        
        assert user_info is not None
        assert user_info['username'] == 'testuser'
        assert user_info['account_id'] == '12345'
        assert user_info['display_name'] is None
        assert user_info['nickname'] is None


class TestBitbucketClientConnectionTest:
    """Test connection testing."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_connection_test_success(self, mock_get, client):
        """Test successful connection test."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'name': 'test-repo'}
        mock_get.return_value = mock_response
        
        result = client.test_connection()
        
        assert result is True
    
    @patch('requests.Session.get')
    def test_detailed_connection_test_success(self, mock_get, client):
        """Test successful detailed connection test."""
        # Repository response
        repo_response = Mock()
        repo_response.status_code = 200
        repo_response.json.return_value = {'name': 'test-repo'}
        
        # Issues response
        issues_response = Mock()
        issues_response.status_code = 200
        issues_response.json.return_value = {}
        
        # PRs response
        prs_response = Mock()
        prs_response.status_code = 200
        prs_response.json.return_value = {}
        
        mock_get.side_effect = [repo_response, issues_response, prs_response]
        
        result = client.test_connection(detailed=True)
        
        assert result is True
        assert mock_get.call_count == 3
    
    def test_connection_test_dry_run(self):
        """Test connection test in dry-run mode."""
        client = BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token",
            dry_run=True
        )
        
        # Should not make API calls in dry-run mode
        with patch('requests.Session.get') as mock_get:
            result = client.test_connection()
            
            assert result is True
            mock_get.assert_not_called()


class TestBitbucketClientErrorHandling:
    """Test error scenarios."""
    
    @pytest.fixture
    def client(self):
        """Create BitbucketClient for testing."""
        return BitbucketClient(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_auth_error_401(self, mock_get, client):
        """Test 401 authentication error."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = HTTPError()
        mock_get.return_value = mock_response
        
        with pytest.raises(AuthenticationError):
            client.get_issues()
    
    @patch('requests.Session.get')
    def test_auth_error_403(self, mock_get, client):
        """Test 403 authentication error."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = HTTPError()
        mock_get.return_value = mock_response
        
        with pytest.raises(AuthenticationError):
            client.get_issues()
    
    @patch('requests.Session.get')
    def test_not_found_error_404(self, mock_get, client):
        """Test 404 not found error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = HTTPError()
        mock_get.return_value = mock_response
        
        with pytest.raises(APIError):
            client.get_issues()
    
    @patch('requests.Session.get')
    def test_network_error(self, mock_get, client):
        """Test network error handling."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        with pytest.raises(NetworkError):
            client.get_issues()
    
    @patch('requests.Session.get')
    def test_timeout_error(self, mock_get, client):
        """Test timeout error handling."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        with pytest.raises(NetworkError):
            client.get_issues()
    
    @patch('requests.Session.get')
    def test_unexpected_error(self, mock_get, client):
        """Test unexpected error handling."""
        mock_get.side_effect = Exception("Unexpected error")
        
        with pytest.raises(APIError, match="Unexpected error"):
            client.get_issues()
    
    @patch('requests.Session.get')
    def test_pagination_auth_error_401(self, mock_get, client):
        """Test 401 error during pagination."""
        # First page succeeds
        response1 = Mock()
        response1.status_code = 200
        response1.json.return_value = {
            'values': [{'id': 1}],
            'next': 'https://api.bitbucket.org/page2'
        }
        
        # Second page fails with 401
        response2 = Mock()
        response2.status_code = 401
        response2.raise_for_status.side_effect = HTTPError()
        
        mock_get.side_effect = [response1, response2]
        
        with pytest.raises(AuthenticationError):
            client.get_issues()
    
    @patch('requests.Session.get')
    def test_pagination_network_error(self, mock_get, client):
        """Test network error during pagination."""
        # First page succeeds
        response1 = Mock()
        response1.status_code = 200
        response1.json.return_value = {
            'values': [{'id': 1}],
            'next': 'https://api.bitbucket.org/page2'
        }
        
        # Second page fails with network error
        mock_get.side_effect = [response1, requests.exceptions.ConnectionError("Connection failed")]
        
        with pytest.raises(NetworkError):
            client.get_issues()