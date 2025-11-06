"""
Tests for GitHubCliClient interactions.

This file tests the GitHub CLI client including:
- Initialization and validation
- CLI availability detection
- Authentication checking and flow
- File upload functionality
- Version detection
- Error handling
- Dry-run mode behavior
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess
from pathlib import Path

from bitbucket_migration.clients.github_cli_client import GitHubCliClient
from bitbucket_migration.exceptions import APIError, AuthenticationError, NetworkError, ValidationError


class TestGitHubCliClientInitialization:
    """Test client initialization and validation."""
    
    def test_init_with_valid_params(self):
        """Test successful client initialization."""
        client = GitHubCliClient(
            token="test-token",
            dry_run=False
        )
        
        assert client.token == "test-token"
        assert client.dry_run is False
        assert client.logger is not None
    
    def test_init_dry_run_mode(self):
        """Test dry-run mode initialization."""
        client = GitHubCliClient(
            token="test-token",
            dry_run=True
        )
        
        assert client.dry_run is True
        assert client.token == "test-token"
    
    def test_init_empty_token_raises_error(self):
        """Test that empty token raises ValidationError."""
        with pytest.raises(ValidationError, match="GitHub token cannot be empty"):
            GitHubCliClient(token="")
    
    def test_init_whitespace_only_token_raises_error(self):
        """Test that whitespace-only token raises ValidationError."""
        with pytest.raises(ValidationError, match="GitHub token cannot be empty"):
            GitHubCliClient(token="   ")
    
    def test_init_with_none_token_raises_error(self):
        """Test that None token raises ValidationError."""
        with pytest.raises(ValidationError, match="GitHub token cannot be empty"):
            GitHubCliClient(token=None)


class TestGitHubCliClientAvailability:
    """Test CLI availability detection."""
    
    @pytest.fixture
    def client(self):
        """Create GitHubCliClient for testing."""
        return GitHubCliClient(
            token="test-token",
            dry_run=False
        )
    
    def test_is_available_success(self, client):
        """Test successful CLI availability check."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = client.is_available()
            
            assert result is True
            mock_run.assert_called_once_with(
                ['gh', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
    
    def test_is_available_cli_not_found(self, client):
        """Test CLI not found error."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("gh: command not found")
            
            result = client.is_available()
            
            assert result is False
            mock_run.assert_called_once()
    
    def test_is_available_timeout(self, client):
        """Test CLI availability check timeout."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('gh', 5)
            
            result = client.is_available()
            
            assert result is False
            mock_run.assert_called_once()
    
    def test_is_available_unexpected_error(self, client):
        """Test unexpected error during availability check."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Unexpected error")
            
            with pytest.raises(APIError, match="Error checking GitHub CLI availability"):
                client.is_available()
    
    def test_is_available_dry_run_mode(self, client):
        """Test CLI availability in dry-run mode."""
        # Override client to be in dry run mode
        client.dry_run = True
        
        result = client.is_available()
        
        # In dry run mode, should always return True
        assert result is True
        
        # Should not make any subprocess calls
        with patch('subprocess.run') as mock_run:
            result = client.is_available()
            assert result is True
            mock_run.assert_not_called()


class TestGitHubCliClientAuthentication:
    """Test authentication checking and flow."""
    
    @pytest.fixture
    def client(self):
        """Create GitHubCliClient for testing."""
        return GitHubCliClient(
            token="test-token",
            dry_run=False
        )
    
    def test_is_authenticated_success(self, client):
        """Test successful authentication check."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Logged in to github.com as user"
            mock_run.return_value = mock_result
            
            result = client.is_authenticated()
            
            assert result is True
            mock_run.assert_called_once_with(
                ['gh', 'auth', 'status'],
                capture_output=True,
                text=True,
                timeout=5
            )
    
    def test_is_authenticated_not_logged_in(self, client):
        """Test not authenticated state."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = "You are not logged in to any GitHub host"
            mock_run.return_value = mock_result
            
            result = client.is_authenticated()
            
            assert result is False
            mock_run.assert_called_once()
    
    def test_is_authenticated_timeout(self, client):
        """Test authentication check timeout."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('gh', 5)
            
            result = client.is_authenticated()
            
            assert result is False
            mock_run.assert_called_once()
    
    def test_is_authenticated_unexpected_error(self, client):
        """Test unexpected error during authentication check."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Unexpected error")
            
            with pytest.raises(APIError, match="Error checking GitHub CLI authentication"):
                client.is_authenticated()
    
    def test_is_authenticated_dry_run_mode(self, client):
        """Test authentication check in dry-run mode."""
        # Override client to be in dry run mode
        client.dry_run = True
        
        result = client.is_authenticated()
        
        # In dry run mode, should always return True
        assert result is True
        
        # Should not make any subprocess calls
        with patch('subprocess.run') as mock_run:
            result = client.is_authenticated()
            assert result is True
            mock_run.assert_not_called()
    
    def test_authenticate_success(self, client):
        """Test successful authentication."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = client.authenticate()
            
            assert result is True
            mock_run.assert_called_once()
            
            # Check that authentication was called with correct parameters
            call_args = mock_run.call_args
            assert call_args[0][0] == ['gh', 'auth', 'login', '--with-token']
            assert call_args[1]['input'] == "test-token"
            assert call_args[1]['text'] is True
            assert call_args[1]['timeout'] == 10
    
    def test_authenticate_with_custom_token(self, client):
        """Test authentication with custom token."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = client.authenticate(token="custom-token")
            
            assert result is True
            # Check that custom token was used
            call_args = mock_run.call_args
            assert call_args[1]['input'] == "custom-token"
    
    def test_authenticate_empty_custom_token_raises_error(self, client):
        """Test that empty custom token raises ValidationError."""
        with pytest.raises(ValidationError, match="GitHub token cannot be empty"):
            client.authenticate(token="")
    
    def test_authenticate_timeout(self, client):
        """Test authentication timeout."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('gh', 10)
            
            result = client.authenticate()
            
            assert result is False
            mock_run.assert_called_once()
    
    def test_authenticate_unexpected_error(self, client):
        """Test unexpected error during authentication."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Authentication failed")
            
            with pytest.raises(APIError, match="Error authenticating GitHub CLI"):
                client.authenticate()
    
    def test_authenticate_dry_run_mode(self, client):
        """Test authentication in dry-run mode."""
        # Override client to be in dry run mode
        client.dry_run = True
        
        result = client.authenticate()
        
        # In dry run mode, should always return True
        assert result is True
        
        # Should not make any subprocess calls
        with patch('subprocess.run') as mock_run:
            result = client.authenticate()
            assert result is True
            mock_run.assert_not_called()


class TestGitHubCliClientFileUpload:
    """Test file upload functionality."""
    
    @pytest.fixture
    def client(self):
        """Create GitHubCliClient for testing."""
        return GitHubCliClient(
            token="test-token",
            dry_run=False
        )
    
    @pytest.fixture
    def test_file(self):
        """Create a test file for upload testing."""
        file_path = Path("/tmp/test-attachment.txt")
        file_path.write_text("test content")
        yield file_path
        # Cleanup
        if file_path.exists():
            file_path.unlink()
    
    def test_upload_attachment_success(self, client, test_file):
        """Test successful file upload."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Successfully uploaded file"
            mock_run.return_value = mock_result
            
            result = client.upload_attachment(
                filepath=test_file,
                issue_number=1,
                owner="test-owner",
                repo="test-repo"
            )
            
            assert result == "Uploaded via gh CLI"
            mock_run.assert_called_once()
            
            # Verify correct command was called
            call_args = mock_run.call_args
            expected_command = [
                'gh', 'issue', 'comment', '1',
                '--repo', 'test-owner/test-repo',
                '--body', f'📎 **Attachment from Bitbucket**: `{test_file.name}` (0.00 MB)',
                '--attach', str(test_file)
            ]
            assert call_args[0][0] == expected_command
            assert call_args[1]['text'] is True
            assert call_args[1]['timeout'] == 60
    
    def test_upload_attachment_dry_run_mode(self, client, test_file):
        """Test file upload in dry-run mode."""
        # Override client to be in dry run mode
        client.dry_run = True
        
        result = client.upload_attachment(
            filepath=test_file,
            issue_number=1,
            owner="test-owner",
            repo="test-repo"
        )
        
        assert result == "Simulated upload via gh CLI"
        
        # Should not make any subprocess calls
        with patch('subprocess.run') as mock_run:
            result = client.upload_attachment(
                filepath=test_file,
                issue_number=1,
                owner="test-owner",
                repo="test-repo"
            )
            assert result == "Simulated upload via gh CLI"
            mock_run.assert_not_called()
    
    def test_upload_attachment_none_filepath_raises_error(self, client):
        """Test that None filepath raises ValidationError."""
        with pytest.raises(ValidationError, match="Attachment filepath must exist"):
            client.upload_attachment(
                filepath=None,
                issue_number=1,
                owner="test-owner",
                repo="test-repo"
            )
    
    def test_upload_attachment_missing_file_raises_error(self, client):
        """Test that missing file raises ValidationError."""
        nonexistent_file = Path("/tmp/nonexistent-file.txt")
        
        with pytest.raises(ValidationError, match="Attachment filepath must exist"):
            client.upload_attachment(
                filepath=nonexistent_file,
                issue_number=1,
                owner="test-owner",
                repo="test-repo"
            )
    
    def test_upload_attachment_invalid_issue_number(self, client, test_file):
        """Test that invalid issue number raises ValidationError."""
        with pytest.raises(ValidationError, match="Issue number must be a positive integer"):
            client.upload_attachment(
                filepath=test_file,
                issue_number=0,
                owner="test-owner",
                repo="test-repo"
            )
        
        with pytest.raises(ValidationError, match="Issue number must be a positive integer"):
            client.upload_attachment(
                filepath=test_file,
                issue_number=-1,
                owner="test-owner",
                repo="test-repo"
            )
    
    def test_upload_attachment_empty_owner_raises_error(self, client, test_file):
        """Test that empty owner raises ValidationError."""
        with pytest.raises(ValidationError, match="Repository owner cannot be empty"):
            client.upload_attachment(
                filepath=test_file,
                issue_number=1,
                owner="",
                repo="test-repo"
            )
    
    def test_upload_attachment_empty_repo_raises_error(self, client, test_file):
        """Test that empty repo raises ValidationError."""
        with pytest.raises(ValidationError, match="Repository name cannot be empty"):
            client.upload_attachment(
                filepath=test_file,
                issue_number=1,
                owner="test-owner",
                repo=""
            )
    
    def test_upload_attachment_timeout(self, client, test_file):
        """Test file upload timeout."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('gh', 60)
            
            result = client.upload_attachment(
                filepath=test_file,
                issue_number=1,
                owner="test-owner",
                repo="test-repo"
            )
            
            assert result is None
            mock_run.assert_called_once()
    
    def test_upload_attachment_failure(self, client, test_file):
        """Test file upload failure."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = "Upload failed: file not found"
            mock_run.return_value = mock_result
            
            result = client.upload_attachment(
                filepath=test_file,
                issue_number=1,
                owner="test-owner",
                repo="test-repo"
            )
            
            assert result is None
            mock_run.assert_called_once()
    
    def test_upload_attachment_unexpected_error(self, client, test_file):
        """Test unexpected error during file upload."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Unexpected error")
            
            with pytest.raises(APIError, match="Error uploading attachment via GitHub CLI"):
                client.upload_attachment(
                    filepath=test_file,
                    issue_number=1,
                    owner="test-owner",
                    repo="test-repo"
                )
    
    def test_upload_attachment_file_size_calculation(self, client):
        """Test that file size is correctly calculated."""
        # Create a larger test file
        file_path = Path("/tmp/test-large-attachment.txt")
        # Create a 1MB file
        file_path.write_text("x" * (1024 * 1024))
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_run.return_value = mock_result
                
                result = client.upload_attachment(
                    filepath=file_path,
                    issue_number=1,
                    owner="test-owner",
                    repo="test-repo"
                )
                
                assert result == "Uploaded via gh CLI"
                
                # Verify size was calculated and included in body
                call_args = mock_run.call_args
                body = call_args[0][0][7]  # --body parameter is at index 7
                assert "1.00 MB" in body
        finally:
            # Cleanup
            if file_path.exists():
                file_path.unlink()


class TestGitHubCliClientVersion:
    """Test version detection."""
    
    @pytest.fixture
    def client(self):
        """Create GitHubCliClient for testing."""
        return GitHubCliClient(
            token="test-token",
            dry_run=False
        )
    
    def test_get_version_success(self, client):
        """Test successful version detection."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "gh version 2.25.0 (2023-01-15)"
            mock_run.return_value = mock_result
            
            result = client.get_version()
            
            assert result == "2.25.0"
            mock_run.assert_called_once_with(
                ['gh', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
    
    def test_get_version_different_format(self, client):
        """Test version detection with different output format."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "2.40.0"
            mock_run.return_value = mock_result
            
            result = client.get_version()
            
            assert result == "2.40.0"
    
    def test_get_version_short_output(self, client):
        """Test version detection with short output."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "gh"  # Too short
            mock_run.return_value = mock_result
            
            result = client.get_version()
            
            assert result == "unknown"
    
    def test_get_version_failure(self, client):
        """Test version detection failure."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result
            
            result = client.get_version()
            
            assert result is None
            mock_run.assert_called_once()
    
    def test_get_version_unexpected_error(self, client):
        """Test unexpected error during version detection."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Version check failed")
            
            with pytest.raises(APIError, match="Error getting GitHub CLI version"):
                client.get_version()
    
    def test_get_version_dry_run_mode(self, client):
        """Test version detection in dry-run mode."""
        # Override client to be in dry run mode
        client.dry_run = True
        
        result = client.get_version()
        
        # In dry run mode, should return simulated version
        assert result == "2.40.0"
        
        # Should not make any subprocess calls
        with patch('subprocess.run') as mock_run:
            result = client.get_version()
            assert result == "2.40.0"
            mock_run.assert_not_called()


class TestGitHubCliClientLogging:
    """Test logging functionality."""
    
    def test_logger_configuration(self):
        """Test that logger is properly configured."""
        client = GitHubCliClient(
            token="test-token",
            dry_run=False
        )
        
        # Check that logger is set up
        assert client.logger is not None
        assert client.logger.name == 'bitbucket_migration'
    
    def test_logging_in_upload(self):
        """Test that logging works during upload operations."""
        client = GitHubCliClient(
            token="test-token",
            dry_run=False
        )
        
        # Create a test file
        file_path = Path("/tmp/test-logging.txt")
        file_path.write_text("test content")
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_result = Mock()
                mock_result.returncode = 1
                mock_result.stderr = "Upload failed"
                mock_run.return_value = mock_result
                
                # This should log the error
                result = client.upload_attachment(
                    filepath=file_path,
                    issue_number=1,
                    owner="test-owner",
                    repo="test-repo"
                )
                
                assert result is None
        finally:
            if file_path.exists():
                file_path.unlink()


class TestGitHubCliClientEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def client(self):
        """Create GitHubCliClient for testing."""
        return GitHubCliClient(
            token="test-token",
            dry_run=False
        )
    
    def test_multiple_authentication_calls(self, client):
        """Test multiple authentication calls with different tokens."""
        # First authentication
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result1 = client.authenticate(token="token1")
            assert result1 is True
            
            # Second authentication with different token
            result2 = client.authenticate(token="token2")
            assert result2 is True
            
            # Verify both calls were made
            assert mock_run.call_count == 2
            
            # Check that second call used different token
            second_call = mock_run.call_args
            assert second_call[1]['input'] == "token2"
    
    def test_availability_check_after_upload_failure(self, client):
        """Test availability check after previous upload failure."""
        # First, simulate upload failure
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('gh', 60)
            
            result1 = client.is_available()
            assert result1 is False
            
            # Now test availability - should still work
            mock_run.side_effect = None
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result2 = client.is_available()
            assert result2 is True
    
    def test_version_check_after_auth_failure(self, client):
        """Test version check after authentication failure."""
        # First, simulate auth failure
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Auth failed")
            
            with pytest.raises(APIError):
                client.authenticate()
            
            # Now test version check - should still work
            mock_run.side_effect = None
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "gh version 2.25.0 (2023-01-15)"
            mock_run.return_value = mock_result
            
            version = client.get_version()
            assert version == "2.25.0"