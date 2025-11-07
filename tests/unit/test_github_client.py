"""
Tests for GitHubClient API interactions.

This file tests the GitHub API client including:
- Initialization and configuration
- Rate limiting and retry logic
- Issue operations
- Comment operations
- PR operations
- Milestone operations
- Branch operations
- Error handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import RequestException, HTTPError
import requests
import time

from bitbucket_migration.clients.github_client import GitHubClient
from bitbucket_migration.exceptions import APIError, AuthenticationError, NetworkError, ValidationError


class TestGitHubClientInitialization:
    """Test client initialization and configuration."""
    
    def test_init_with_valid_params(self):
        """Test successful client initialization."""
        client = GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
        
        assert client.owner == "test-owner"
        assert client.repo == "test-repo"
        assert client.token == "test-token"
        assert client.dry_run is False
        assert client.base_url == "https://api.github.com/repos/test-owner/test-repo"
    
    def test_init_dry_run_mode(self):
        """Test dry-run mode initialization."""
        client = GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=True
        )
        
        assert client.dry_run is True
        assert client.simulated_issue_pr_counter == 1
        assert client.simulated_milestone_counter == 1
    
    def test_init_empty_owner_raises_error(self):
        """Test that empty owner raises ValidationError."""
        with pytest.raises(ValidationError, match="owner cannot be empty"):
            GitHubClient(owner="", repo="test-repo", token="test-token")
    
    def test_init_empty_repo_raises_error(self):
        """Test that empty repo raises ValidationError."""
        with pytest.raises(ValidationError, match="repository cannot be empty"):
            GitHubClient(owner="test-owner", repo="", token="test-token")
    
    def test_init_empty_token_raises_error(self):
        """Test that empty token raises ValidationError."""
        with pytest.raises(ValidationError, match="token cannot be empty"):
            GitHubClient(owner="test-owner", repo="test-repo", token="")


class TestGitHubClientRateLimiting:
    """Test rate limit handling."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    def test_rate_limit_from_headers(self, client):
        """Test extracting rate limits from response headers."""
        mock_headers = {
            'X-RateLimit-Resource': 'core',
            'X-RateLimit-Limit': '5000',
            'X-RateLimit-Remaining': '4999',
            'X-RateLimit-Reset': '1234567890',
            'X-RateLimit-Used': '1'
        }
        
        client._update_rate_limits_from_headers(mock_headers)
        
        assert client.rate_limits['core']['limit'] == 5000
        assert client.rate_limits['core']['remaining'] == 4999
        assert client.rate_limits['core']['reset'] == 1234567890
        assert client.rate_limits['core']['used'] == 1
    
    def test_rate_limit_from_headers_search_resource(self, client):
        """Test extracting rate limits from response headers for search resource."""
        mock_headers = {
            'X-RateLimit-Resource': 'search',
            'X-RateLimit-Limit': '30',
            'X-RateLimit-Remaining': '29',
            'X-RateLimit-Reset': '1234567890',
            'X-RateLimit-Used': '1'
        }
        
        client._update_rate_limits_from_headers(mock_headers)
        
        assert client.rate_limits['search']['limit'] == 30
        assert client.rate_limits['search']['remaining'] == 29
        assert client.rate_limits['search']['reset'] == 1234567890
        assert client.rate_limits['search']['used'] == 1
    
    def test_rate_limit_from_headers_unknown_resource(self, client):
        """Test ignoring unknown rate limit resources."""
        mock_headers = {
            'X-RateLimit-Resource': 'unknown',
            'X-RateLimit-Limit': '1000',
            'X-RateLimit-Remaining': '999',
        }
        
        client._update_rate_limits_from_headers(mock_headers)
        
        # Unknown resources should be ignored
        assert 'unknown' not in client.rate_limits
        assert client.rate_limits['core']['limit'] == 5000  # Should remain unchanged
        assert client.rate_limits['core']['remaining'] == 5000  # Should remain unchanged
    
    def test_rate_limit_from_headers_invalid_values(self, client):
        """Test handling invalid rate limit header values."""
        mock_headers = {
            'X-RateLimit-Resource': 'core',
            'X-RateLimit-Limit': 'invalid',
            'X-RateLimit-Remaining': 'not_a_number',
            'X-RateLimit-Reset': 'bad_value',
        }
        
        client._update_rate_limits_from_headers(mock_headers)
        
        # Should keep existing values when parsing fails
        assert client.rate_limits['core']['limit'] == 5000
        assert client.rate_limits['core']['remaining'] == 5000
        assert client.rate_limits['core']['reset'] == 0
    
    def test_wait_time_calculation_with_retry_after(self, client):
        """Test wait time calculation from Retry-After header."""
        mock_headers = {'Retry-After': '60'}
        
        wait_time = client._calculate_wait_time(mock_headers, 429)
        
        assert wait_time == 60.0
    
    def test_wait_time_calculation_with_invalid_retry_after(self, client):
        """Test wait time calculation with invalid Retry-After header."""
        mock_headers = {'Retry-After': 'invalid'}
        
        wait_time = client._calculate_wait_time(mock_headers, 429)
        
        # Should fall back to 429 secondary limit handling
        assert wait_time == 60  # Secondary rate limit fallback
    
    def test_wait_time_calculation_when_rate_limited(self, client):
        """Test wait time calculation when rate limited."""
        mock_headers = {
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': str(int(time.time()) + 60)
        }
        
        wait_time = client._calculate_wait_time(mock_headers, 403)
        
        assert wait_time > 0
        assert wait_time <= 65  # ~60 seconds plus buffer
    
    def test_wait_time_calculation_403_with_remaining_quota(self, client):
        """Test 403 error with remaining quota doesn't wait."""
        mock_headers = {
            'X-RateLimit-Remaining': '100',
            'X-RateLimit-Reset': str(int(time.time()) + 60)
        }
        
        wait_time = client._calculate_wait_time(mock_headers, 403)
        
        # Should return 0 for permission errors (not rate limit)
        assert wait_time == 0
    
    def test_wait_time_calculation_429_secondary_limit(self, client):
        """Test 429 secondary rate limit wait time."""
        mock_headers = {'X-RateLimit-Remaining': '1000'}
        
        wait_time = client._calculate_wait_time(mock_headers, 429)
        
        # Should wait 60 seconds for secondary limits
        assert wait_time == 60
    
    def test_wait_time_calculation_low_quota_warning(self, client):
        """Test wait time calculation with low remaining quota."""
        mock_headers = {'X-RateLimit-Remaining': '5'}
        
        wait_time = client._calculate_wait_time(mock_headers, 200)
        
        # Should slow down when running low
        assert wait_time == 30
    
    def test_wait_time_calculation_moderate_quota_warning(self, client):
        """Test wait time calculation with moderate remaining quota."""
        mock_headers = {'X-RateLimit-Remaining': '40'}
        
        wait_time = client._calculate_wait_time(mock_headers, 200)
        
        # Should slow down moderately
        assert wait_time == 10
    
    def test_wait_time_calculation_sufficient_quota(self, client):
        """Test wait time calculation with sufficient quota."""
        mock_headers = {'X-RateLimit-Remaining': '100'}
        
        wait_time = client._calculate_wait_time(mock_headers, 200)
        
        # No wait needed
        assert wait_time == 0


class TestGitHubClientRequestRetry:
    """Test HTTP request retry logic."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_successful_request_no_retry(self, mock_request, client):
        """Test successful request without retry."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'test': 'data'}
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client._make_request_with_retry('GET', 'https://api.github.com/test')
        
        assert result == mock_response
        assert mock_request.call_count == 1
    
    @patch('requests.Session.request')
    def test_retry_after_rate_limit_403(self, mock_request, client):
        """Test retry after rate limit 403 error."""
        # First call: rate limited
        mock_response1 = Mock()
        mock_response1.status_code = 403
        mock_response1.headers = {
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': str(int(time.time()) + 1)
        }
        
        # Second call: success
        mock_response2 = Mock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = {'test': 'data'}
        mock_response2.headers = {'X-RateLimit-Remaining': '4999'}
        
        mock_request.side_effect = [mock_response1, mock_response2]
        
        with patch('time.sleep') as mock_sleep:
            result = client._make_request_with_retry('GET', 'https://api.github.com/test', max_retries=1)
            
            assert result == mock_response2
            assert mock_request.call_count == 2
            mock_sleep.assert_called_once()
    
    @patch('requests.Session.request')
    def test_retry_after_rate_limit_429(self, mock_request, client):
        """Test retry after secondary rate limit 429 error."""
        # First call: secondary rate limited
        mock_response1 = Mock()
        mock_response1.status_code = 429
        mock_response1.headers = {'X-RateLimit-Remaining': '0'}
        
        # Second call: success
        mock_response2 = Mock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = {'test': 'data'}
        mock_response2.headers = {'X-RateLimit-Remaining': '4999'}
        
        mock_request.side_effect = [mock_response1, mock_response2]
        
        with patch('time.sleep') as mock_sleep:
            result = client._make_request_with_retry('GET', 'https://api.github.com/test', max_retries=1)
            
            assert result == mock_response2
            assert mock_request.call_count == 2
            mock_sleep.assert_called_once()
    
    @patch('requests.Session.request')
    def test_retry_after_server_error(self, mock_request, client):
        """Test retry after 5xx server error."""
        # First call: server error
        mock_response1 = Mock()
        mock_response1.status_code = 500
        mock_response1.headers = {'X-RateLimit-Remaining': '4999'}
        
        # Second call: success
        mock_response2 = Mock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = {'test': 'data'}
        mock_response2.headers = {'X-RateLimit-Remaining': '4999'}
        
        mock_request.side_effect = [mock_response1, mock_response2]
        
        with patch('time.sleep') as mock_sleep:
            result = client._make_request_with_retry('GET', 'https://api.github.com/test', max_retries=1)
            
            assert result == mock_response2
            assert mock_request.call_count == 2
            mock_sleep.assert_called_once()
    
    @patch('requests.Session.request')
    def test_retry_after_timeout(self, mock_request, client):
        """Test retry after timeout."""
        # First call: timeout
        mock_request.side_effect = requests.exceptions.Timeout("Request timed out")
        
        # Second call: success
        mock_response2 = Mock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = {'test': 'data'}
        mock_response2.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.side_effect = [requests.exceptions.Timeout("Request timed out"), mock_response2]
        
        with patch('time.sleep') as mock_sleep:
            result = client._make_request_with_retry('GET', 'https://api.github.com/test', max_retries=1)
            
            assert result == mock_response2
            assert mock_request.call_count == 2
            mock_sleep.assert_called_once()
    
    @patch('requests.Session.request')
    def test_max_retries_exhausted_rate_limit(self, mock_request, client):
        """Test that max retries raises APIError for rate limit."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {'X-RateLimit-Remaining': '0'}
        mock_request.return_value = mock_response
        
        with pytest.raises(APIError, match="rate limit exceeded"):
            client._make_request_with_retry('GET', 'https://api.github.com/test', max_retries=0)
    
    @patch('requests.Session.request')
    def test_max_retries_exhausted_429(self, mock_request, client):
        """Test that max retries raises APIError for 429."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {'X-RateLimit-Remaining': '0'}
        mock_request.return_value = mock_response
        
        with pytest.raises(APIError, match="secondary rate limit exceeded"):
            client._make_request_with_retry('GET', 'https://api.github.com/test', max_retries=0)
    
    @patch('requests.Session.request')
    def test_max_retries_exhausted_network_error(self, mock_request, client):
        """Test that max retries raises NetworkError for network failures."""
        mock_request.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        with pytest.raises(NetworkError, match="Network error after"):
            client._make_request_with_retry('GET', 'https://api.github.com/test', max_retries=0)
    
    @patch('requests.Session.request')
    def test_client_error_no_retry(self, mock_request, client):
        """Test that client errors (4xx except rate limits) don't retry."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client._make_request_with_retry('GET', 'https://api.github.com/test', max_retries=3)
        
        # Should return the error response without retry
        assert result == mock_response
        assert mock_request.call_count == 1


class TestGitHubClientIssueOperations:
    """Test issue operations."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_create_issue_success(self, mock_request, client):
        """Test successful issue creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 12345,
            'number': 1,
            'title': 'Test Issue',
            'html_url': 'https://github.com/test-owner/test-repo/issues/1'
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.create_issue(
            title="Test Issue",
            body="Test body"
        )
        
        assert result['number'] == 1
        assert result['title'] == 'Test Issue'
        
        # Verify API was called with correct parameters
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == 'POST'
        assert 'issues' in call_args[0][1]
    
    def test_create_issue_dry_run_mode(self):
        """Test that dry-run mode doesn't make actual API calls."""
        client = GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=True
        )
        
        result = client.create_issue(
            title="Test Issue",
            body="Test body"
        )
        
        # In dry-run mode, should return mock data
        assert result is not None
        assert result['number'] == 1
        assert result['title'] == 'Test Issue'
    
    def test_create_issue_empty_title_raises_error(self, client):
        """Test that empty title raises ValidationError."""
        with pytest.raises(ValidationError, match="title cannot be empty"):
            client.create_issue(title="", body="Test body")
    
    def test_create_issue_empty_body_allowed(self, client):
        """Test that empty body is allowed."""
        with patch.object(client, '_make_request_with_retry') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'id': 12345,
                'number': 1,
                'title': 'Test Issue',
                'body': '',
            }
            mock_response.headers = {'X-RateLimit-Remaining': '4999'}
            mock_request.return_value = mock_response
            
            result = client.create_issue(title="Test Issue", body="")
            
            assert result is not None
            # Verify API was called with empty body
            call_args = mock_request.call_args
            assert 'body' in call_args[1]['json']
            assert call_args[1]['json']['body'] == ''
    
    @patch('requests.Session.request')
    def test_create_issue_with_labels(self, mock_request, client):
        """Test issue creation with labels."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 12345,
            'number': 1,
            'title': 'Test Issue',
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.create_issue(
            title="Test Issue",
            body="Test body",
            labels=["bug", "enhancement"]
        )
        
        # Verify labels were included in request
        call_args = mock_request.call_args
        assert 'labels' in call_args[1]['json']
        assert call_args[1]['json']['labels'] == ["bug", "enhancement"]
    
    @patch('requests.Session.request')
    def test_create_issue_with_none_labels(self, mock_request, client):
        """Test issue creation with None labels (should be filtered out)."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 12345,
            'number': 1,
            'title': 'Test Issue',
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.create_issue(
            title="Test Issue",
            body="Test body",
            labels=None
        )
        
        # Verify None values are filtered out
        call_args = mock_request.call_args
        assert 'labels' not in call_args[1]['json']
    
    @patch('requests.Session.request')
    def test_get_issue_success(self, mock_request, client):
        """Test successful issue retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 12345,
            'number': 1,
            'title': 'Test Issue',
            'body': 'Test body',
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.get_issue(1)
        
        assert result['number'] == 1
        assert result['title'] == 'Test Issue'
        
        # Verify API was called with correct parameters
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == 'GET'
        assert 'issues/1' in call_args[0][1]
    
    def test_get_issue_invalid_number(self, client):
        """Test that invalid issue number raises ValidationError."""
        with pytest.raises(ValidationError, match="Issue number must be a positive integer"):
            client.get_issue(0)
        
        with pytest.raises(ValidationError, match="Issue number must be a positive integer"):
            client.get_issue(-1)
    
    @patch('requests.Session.request')
    def test_get_issue_not_found(self, mock_request, client):
        """Test 404 not found error for missing issue."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        
        # Create HTTPError with response object
        error = HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        mock_request.return_value = mock_response
        
        with pytest.raises(APIError, match="Issue not found"):
            client.get_issue(99999)
    
    @patch('requests.Session.request')
    def test_update_issue_success(self, mock_request, client):
        """Test successful issue update."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 12345,
            'number': 1,
            'title': 'Updated Issue',
            'state': 'closed',
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.update_issue(
            issue_number=1,
            state='closed',
            labels=['fixed']
        )
        
        assert result['state'] == 'closed'
        
        # Verify API was called with correct parameters
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == 'PATCH'
        assert 'issues/1' in call_args[0][1]
        assert call_args[1]['json']['state'] == 'closed'
        assert call_args[1]['json']['labels'] == ['fixed']
    
    def test_update_issue_no_fields(self, client):
        """Test that no fields to update raises ValidationError."""
        with pytest.raises(ValidationError, match="No fields to update"):
            client.update_issue(1)


class TestGitHubClientCommentOperations:
    """Test comment operations."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_create_comment_success(self, mock_request, client):
        """Test successful comment creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 67890,
            'body': 'Test comment',
            'html_url': 'https://github.com/test-owner/test-repo/issues/1#issuecomment-67890'
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.create_comment(
            issue_number=1,
            body="Test comment"
        )
        
        assert result['id'] == 67890
        assert result['body'] == 'Test comment'
    
    def test_create_comment_empty_body_raises_error(self, client):
        """Test that empty body raises ValidationError."""
        with pytest.raises(ValidationError, match="body cannot be empty"):
            client.create_comment(issue_number=1, body="")
    
    def test_create_comment_invalid_issue_number(self, client):
        """Test that invalid issue number raises ValidationError."""
        with pytest.raises(ValidationError, match="Issue number must be a positive integer"):
            client.create_comment(issue_number=0, body="Test comment")
    
    @patch('time.sleep')
    @patch('requests.Session.request')
    def test_create_comment_locked_issue(self, mock_request, mock_sleep, client):
        """Test locked issue error handling."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_response.json.return_value = {
            'message': 'Issue is locked'
        }
        
        # Create HTTPError with response object
        error = HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        mock_request.return_value = mock_response
        
        with pytest.raises(ValidationError, match="is locked"):
            client.create_comment(issue_number=1, body="Test comment")
    
    @patch('requests.Session.request')
    def test_update_comment_success(self, mock_request, client):
        """Test successful comment update."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 67890,
            'body': 'Updated comment',
            'html_url': 'https://github.com/test-owner/test-repo/issues/1#issuecomment-67890'
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.update_comment(
            comment_id=67890,
            body="Updated comment"
        )
        
        assert result['body'] == 'Updated comment'
    
    def test_update_comment_invalid_id(self, client):
        """Test that invalid comment ID raises ValidationError."""
        with pytest.raises(ValidationError, match="Comment ID must be a positive integer"):
            client.update_comment(comment_id=0, body="Test comment")
    
    @patch('requests.Session.request')
    def test_get_comments_success(self, mock_request, client):
        """Test successful comment retrieval with pagination."""
        # First page
        response1 = Mock()
        response1.status_code = 200
        response1.json.return_value = [
            {'id': 1, 'body': 'Comment 1'},
            {'id': 2, 'body': 'Comment 2'}
        ]
        response1.headers = {
            'X-RateLimit-Remaining': '4999',
            'Link': '<https://api.github.com/repos/test-owner/test-repo/issues/1/comments?page=2>; rel="next"'
        }
        
        # Second page
        response2 = Mock()
        response2.status_code = 200
        response2.json.return_value = [
            {'id': 3, 'body': 'Comment 3'}
        ]
        response2.headers = {'X-RateLimit-Remaining': '4999'}
        
        mock_request.side_effect = [response1, response2]
        
        result = client.get_comments(1)
        
        assert len(result) == 3
        assert result[0]['id'] == 1
        assert result[1]['id'] == 2
        assert result[2]['id'] == 3


class TestGitHubClientPullRequestOperations:
    """Test pull request operations."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_create_pull_request_success(self, mock_request, client):
        """Test successful PR creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 12345,
            'number': 1,
            'title': 'Test PR',
            'head': {'ref': 'feature-branch'},
            'base': {'ref': 'main'},
            'html_url': 'https://github.com/test-owner/test-repo/pull/1'
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.create_pull_request(
            title="Test PR",
            body="Test PR body",
            head="feature-branch",
            base="main"
        )
        
        assert result['number'] == 1
        assert result['title'] == 'Test PR'
        
        # Verify API was called with correct parameters
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == 'POST'
        assert 'pulls' in call_args[0][1]
    
    def test_create_pull_request_empty_title_raises_error(self, client):
        """Test that empty title raises ValidationError."""
        with pytest.raises(ValidationError, match="PR title cannot be empty"):
            client.create_pull_request(title="", body="Test body", head="feature", base="main")
    
    def test_create_pull_request_empty_head_raises_error(self, client):
        """Test that empty head raises ValidationError."""
        with pytest.raises(ValidationError, match="Head branch cannot be empty"):
            client.create_pull_request(title="Test", body="Test body", head="", base="main")
    
    def test_create_pull_request_empty_base_raises_error(self, client):
        """Test that empty base raises ValidationError."""
        with pytest.raises(ValidationError, match="Base branch cannot be empty"):
            client.create_pull_request(title="Test", body="Test body", head="feature", base="")
    
    @patch('requests.Session.request')
    def test_get_pull_request_success(self, mock_request, client):
        """Test successful PR retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 12345,
            'number': 1,
            'title': 'Test PR',
            'state': 'open',
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.get_pull_request(1)
        
        assert result['number'] == 1
        assert result['title'] == 'Test PR'
    
    @patch('requests.Session.request')
    def test_update_pull_request_success(self, mock_request, client):
        """Test successful PR update."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 12345,
            'number': 1,
            'title': 'Updated PR',
            'state': 'closed',
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.update_pull_request(
            pull_number=1,
            state='closed',
            title='Updated PR'
        )
        
        assert result['state'] == 'closed'
        assert result['title'] == 'Updated PR'


class TestGitHubClientMilestoneOperations:
    """Test milestone operations."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_create_milestone_success(self, mock_request, client):
        """Test successful milestone creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'number': 1,
            'title': 'v1.0',
            'state': 'open',
            'description': 'Version 1.0'
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.create_milestone(
            title="v1.0",
            description="Version 1.0"
        )
        
        assert result['number'] == 1
        assert result['title'] == 'v1.0'
    
    def test_create_milestone_empty_title_raises_error(self, client):
        """Test that empty title raises ValidationError."""
        with pytest.raises(ValidationError, match="Milestone title cannot be empty"):
            client.create_milestone(title="")
    
    def test_create_milestone_invalid_state_raises_error(self, client):
        """Test that invalid state raises ValidationError."""
        with pytest.raises(ValidationError, match="State must be 'open' or 'closed'"):
            client.create_milestone(title="v1.0", state="invalid")
    
    def test_create_milestone_dry_run(self):
        """Test milestone creation in dry-run mode."""
        client = GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=True
        )
        
        result = client.create_milestone(title="v1.0")
        
        assert result['number'] == 1
        assert result['title'] == 'v1.0'
        assert result['state'] == 'open'
    
    @patch('requests.Session.request')
    def test_get_milestones_success(self, mock_request, client):
        """Test successful milestone retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'number': 1, 'title': 'v1.0', 'state': 'open'},
            {'number': 2, 'title': 'v2.0', 'state': 'closed'}
        ]
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.get_milestones(state='all')
        
        assert len(result) == 2
        assert result[0]['title'] == 'v1.0'
        assert result[1]['title'] == 'v2.0'
    
    def test_get_milestones_invalid_state(self, client):
        """Test that invalid state raises ValidationError."""
        with pytest.raises(ValidationError, match="State must be 'open', 'closed', or 'all'"):
            client.get_milestones(state='invalid')
    
    @patch('requests.Session.request')
    def test_get_milestone_by_title_success(self, mock_request, client):
        """Test finding milestone by title."""
        # Mock get_milestones call
        with patch.object(client, 'get_milestones') as mock_get_milestones:
            mock_get_milestones.return_value = [
                {'number': 1, 'title': 'v1.0', 'state': 'open'},
                {'number': 2, 'title': 'v2.0', 'state': 'closed'},
                {'number': 3, 'title': 'v1.0', 'state': 'open'}  # Duplicate title
            ]
            
            result = client.get_milestone_by_title('v1.0')
            
            # Should return first match
            assert result['title'] == 'v1.0'
            assert result['number'] == 1
    
    def test_get_milestone_by_title_not_found(self, client):
        """Test finding milestone by title when not found."""
        with patch.object(client, 'get_milestones') as mock_get_milestones:
            mock_get_milestones.return_value = [
                {'number': 1, 'title': 'v1.0', 'state': 'open'},
            ]
            
            result = client.get_milestone_by_title('v3.0')
            
            assert result is None
    
    def test_get_milestone_by_title_empty_title(self, client):
        """Test that empty title raises ValidationError."""
        with pytest.raises(ValidationError, match="Milestone title cannot be empty"):
            client.get_milestone_by_title("")


class TestGitHubClientBranchOperations:
    """Test branch existence checking."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_branch_exists_true(self, mock_request, client):
        """Test checking for existing branch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'name': 'main'}
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.check_branch_exists("main")
        
        assert result is True
    
    @patch('requests.Session.request')
    def test_branch_exists_false(self, mock_request, client):
        """Test checking for non-existent branch."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response
        
        result = client.check_branch_exists("nonexistent-branch")
        
        assert result is False
    
    def test_check_branch_empty_name_raises_error(self, client):
        """Test that empty branch name raises ValidationError."""
        with pytest.raises(ValidationError, match="Branch name cannot be empty"):
            client.check_branch_exists("")


class TestGitHubClientRepositoryOperations:
    """Test repository operations."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_get_repository_info_success(self, mock_request, client):
        """Test successful repository info retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'name': 'test-repo',
            'owner': {'login': 'test-owner'},
            'default_branch': 'main'
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.get_repository_info()
        
        assert result['name'] == 'test-repo'
        assert result['owner']['login'] == 'test-owner'
    
    def test_get_repository_info_dry_run(self):
        """Test repository info in dry-run mode."""
        client = GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=True
        )
        
        # Should not make API calls in dry-run mode
        with patch.object(client, '_make_request_with_retry') as mock_request:
            result = client.get_repository_info()
            
            # Should call API even in dry-run mode for read operations
            mock_request.assert_called_once()


class TestGitHubClientIssueTypes:
    """Test issue types operations."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_get_issue_types_success(self, mock_request, client):
        """Test successful issue types retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'name': 'bug', 'id': 1},
            {'name': 'enhancement', 'id': 2},
            {'name': 'question', 'id': 3}
        ]
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.get_issue_types("test-org")
        
        assert len(result) == 3
        assert 'Bug' in result
        assert 'Enhancement' in result
        assert 'Question' in result
        assert result['Bug'] == 1
        assert result['Enhancement'] == 2
        assert result['Question'] == 3
    
    @patch('requests.Session.request')
    def test_get_issue_types_not_found(self, mock_request, client):
        """Test 404 not found for organization without issue types."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_response.json.return_value = {}
        
        # Create HTTPError with response object
        error = HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        mock_request.return_value = mock_response
        
        result = client.get_issue_types("test-org")
        
        assert result == {}


class TestGitHubClientReviewComments:
    """Test PR review comment operations."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_create_pr_review_comment_success(self, mock_request, client):
        """Test successful PR review comment creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 12345,
            'body': 'Review comment',
            'path': 'src/file.py',
            'line': 10,
            'side': 'RIGHT'
        }
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.create_pr_review_comment(
            pull_number=1,
            body='Review comment',
            path='src/file.py',
            line=10
        )
        
        assert result['id'] == 12345
        assert result['path'] == 'src/file.py'
        assert result['line'] == 10
    
    def test_create_pr_review_comment_invalid_pull_number(self, client):
        """Test that invalid PR number raises ValidationError."""
        with pytest.raises(ValidationError, match="Pull request number must be a positive integer"):
            client.create_pr_review_comment(
                pull_number=0,
                body='Review comment',
                path='src/file.py',
                line=10
            )
    
    def test_create_pr_review_comment_invalid_line(self, client):
        """Test that invalid line number raises ValidationError."""
        with pytest.raises(ValidationError, match="Line number must be a positive integer"):
            client.create_pr_review_comment(
                pull_number=1,
                body='Review comment',
                path='src/file.py',
                line=0
            )
    
    def test_create_pr_review_comment_invalid_side(self, client):
        """Test that invalid side raises ValidationError."""
        with pytest.raises(ValidationError, match="Side must be 'LEFT' or 'RIGHT'"):
            client.create_pr_review_comment(
                pull_number=1,
                body='Review comment',
                path='src/file.py',
                line=10,
                side='INVALID'
            )
    
    def test_create_pr_review_comment_invalid_commit_id(self, client):
        """Test that invalid commit ID raises ValidationError."""
        with pytest.raises(ValidationError, match="Commit ID must be a valid SHA hash"):
            client.create_pr_review_comment(
                pull_number=1,
                body='Review comment',
                path='src/file.py',
                line=10,
                commit_id='invalid-sha'
            )
    
    def test_create_pr_review_comment_invalid_in_reply_to(self, client):
        """Test that invalid in_reply_to raises ValidationError."""
        with pytest.raises(ValidationError, match="in_reply_to must be a positive integer"):
            client.create_pr_review_comment(
                pull_number=1,
                body='Review comment',
                path='src/file.py',
                line=10,
                in_reply_to=0
            )


class TestGitHubClientErrorHandling:
    """Test error scenarios."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_auth_error_401(self, mock_request, client):
        """Test 401 authentication error."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Bad credentials"
        
        # Create HTTPError with response object
        error = HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        mock_request.return_value = mock_response
        
        with pytest.raises(AuthenticationError):
            client.create_issue(title="Test", body="Test")
    
    @patch('requests.Session.request')
    def test_not_found_error_404(self, mock_request, client):
        """Test 404 not found error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        
        # Create HTTPError with response object
        error = HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        mock_request.return_value = mock_response
        
        with pytest.raises(APIError):
            client.get_issue(issue_number=99999)
    
    @patch('time.sleep')
    @patch('requests.Session.request')
    def test_forbidden_error_403(self, mock_request, mock_sleep, client):
        """Test 403 forbidden error."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_response.text = "Forbidden"
        mock_response.json.return_value = {'message': 'Forbidden'}
        
        # Create HTTPError with response object
        error = HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        mock_request.return_value = mock_response
        
        with pytest.raises(AuthenticationError):
            client.create_issue(title="Test", body="Test")
    
    @patch('requests.Session.request')
    def test_validation_error_422(self, mock_request, client):
        """Test 422 validation error."""
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            'message': 'Validation failed'
        }
        
        # Create HTTPError with response object
        error = HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        mock_request.return_value = mock_response
        
        with pytest.raises(ValidationError):
            client.create_issue(title="Test", body="Test")
    
    @patch('time.sleep')
    @patch('requests.Session.request')
    def test_network_error(self, mock_request, mock_sleep, client):
        """Test network error handling."""
        mock_request.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        with pytest.raises(NetworkError):
            client.create_issue(title="Test", body="Test")
    
    @patch('time.sleep')
    @patch('requests.Session.request')
    def test_timeout_error(self, mock_request, mock_sleep, client):
        """Test timeout error handling."""
        mock_request.side_effect = requests.exceptions.Timeout("Request timed out")
        
        with pytest.raises(NetworkError):
            client.create_issue(title="Test", body="Test")


class TestGitHubClientConnectionTest:
    """Test connection testing."""
    
    @pytest.fixture
    def client(self):
        """Create a GitHubClient for testing."""
        return GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=False
        )
    
    @patch('requests.Session.request')
    def test_connection_test_success(self, mock_request, client):
        """Test successful connection test."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'name': 'test-repo'}
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_request.return_value = mock_response
        
        result = client.test_connection()
        
        assert result is True
    
    @patch('requests.Session.request')
    def test_detailed_connection_test_success(self, mock_request, client):
        """Test successful detailed connection test."""
        # Repository response
        repo_response = Mock()
        repo_response.status_code = 200
        repo_response.json.return_value = {'name': 'test-repo'}
        repo_response.headers = {'X-RateLimit-Remaining': '4999'}
        
        # Issues response
        issues_response = Mock()
        issues_response.status_code = 200
        issues_response.json.return_value = []
        issues_response.headers = {'X-RateLimit-Remaining': '4999'}
        
        # PRs response
        prs_response = Mock()
        prs_response.status_code = 200
        prs_response.json.return_value = []
        prs_response.headers = {'X-RateLimit-Remaining': '4999'}
        
        mock_request.side_effect = [repo_response, issues_response, prs_response]
        
        result = client.test_connection(detailed=True)
        
        assert result is True
        assert mock_request.call_count == 3
    
    def test_connection_test_dry_run(self):
        """Test connection test in dry-run mode."""
        client = GitHubClient(
            owner="test-owner",
            repo="test-repo",
            token="test-token",
            dry_run=True
        )
        
        result = client.test_connection()
        
        assert result is True