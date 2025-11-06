"""
Tests for test-auth command functionality.

This file tests the test-auth command including:
- GitHub CLI availability and authentication checking
- Bitbucket and GitHub API authentication testing
- Interactive prompting for missing arguments
- Error handling and user feedback
- Success and failure scenarios
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace
import sys
from pathlib import Path

from bitbucket_migration.commands.test_auth_command import (
    run_test_auth, 
    _check_gh_cli_available, 
    _authenticate_gh_cli,
    prompt_for_missing_args
)
from bitbucket_migration.exceptions import APIError, AuthenticationError, NetworkError, ValidationError
from bitbucket_migration.clients.bitbucket_client import BitbucketClient
from bitbucket_migration.clients.github_client import GitHubClient


class TestCheckGhCliAvailable:
    """Test the _check_gh_cli_available function."""
    
    @patch('bitbucket_migration.commands.test_auth_command.GitHubCliClient')
    def test_check_gh_cli_available_success(self, mock_cli_client_class):
        """Test successful GitHub CLI availability check."""
        # Setup mocks
        mock_cli_client = Mock()
        mock_cli_client_class.return_value = mock_cli_client
        mock_cli_client.is_available.return_value = True
        mock_cli_client.get_version.return_value = "2.40.0"
        mock_cli_client.is_authenticated.return_value = True
        
        result = _check_gh_cli_available("test-token")
        
        assert result['available'] is True
        assert result['authenticated'] is True
        assert result['version'] == "2.40.0"
        assert "installed" in result['details']
        assert "authenticated" in result['details']
    
    @patch('bitbucket_migration.commands.test_auth_command.GitHubCliClient')
    def test_check_gh_cli_not_available(self, mock_cli_client_class):
        """Test GitHub CLI not available."""
        # Setup mocks
        mock_cli_client = Mock()
        mock_cli_client_class.return_value = mock_cli_client
        mock_cli_client.is_available.return_value = False
        
        result = _check_gh_cli_available("test-token")
        
        assert result['available'] is False
        assert result['authenticated'] is False
        assert result['version'] == ''
        assert result['details'] == "GitHub CLI not installed"
    
    @patch('bitbucket_migration.commands.test_auth_command.GitHubCliClient')
    def test_check_gh_cli_exception(self, mock_cli_client_class):
        """Test handling of exceptions during CLI check."""
        # Setup mocks to raise exception
        mock_cli_client_class.side_effect = Exception("Test exception")
        
        result = _check_gh_cli_available("test-token")
        
        assert result['available'] is False
        assert result['authenticated'] is False
        assert "Error checking GitHub CLI" in result['details']
        assert "Test exception" in result['details']


class TestAuthenticateGhCli:
    """Test the _authenticate_gh_cli function."""
    
    @patch('bitbucket_migration.commands.test_auth_command.GitHubCliClient')
    def test_authenticate_gh_cli_success(self, mock_cli_client_class):
        """Test successful GitHub CLI authentication."""
        # Setup mocks
        mock_cli_client = Mock()
        mock_cli_client_class.return_value = mock_cli_client
        mock_cli_client.authenticate.return_value = True
        
        result = _authenticate_gh_cli("test-token")
        
        assert result['success'] is True
        assert result['error'] == ''
    
    @patch('bitbucket_migration.commands.test_auth_command.GitHubCliClient')
    def test_authenticate_gh_cli_failure(self, mock_cli_client_class):
        """Test failed GitHub CLI authentication."""
        # Setup mocks
        mock_cli_client = Mock()
        mock_cli_client_class.return_value = mock_cli_client
        mock_cli_client.authenticate.return_value = False
        
        result = _authenticate_gh_cli("test-token")
        
        assert result['success'] is False
        assert result['error'] == "Authentication failed"
    
    @patch('bitbucket_migration.commands.test_auth_command.GitHubCliClient')
    def test_authenticate_gh_cli_exception(self, mock_cli_client_class):
        """Test handling of exceptions during CLI authentication."""
        # Setup mocks to raise exception
        mock_cli_client_class.side_effect = Exception("Auth exception")
        
        result = _authenticate_gh_cli("test-token")
        
        assert result['success'] is False
        assert "Authentication error: Auth exception" in result['error']


class TestTestAuthCommand:
    """Test the run_test_auth function."""
    
    @pytest.fixture
    def mock_args(self):
        """Create mock arguments for testing."""
        return Namespace(
            workspace='test-workspace',
            repo='test-repo',
            email='test@example.com',
            token='test-token',
            gh_owner='test-owner',
            gh_repo='test-repo',
            gh_token='test-gh-token'
        )
    
    @patch('bitbucket_migration.commands.test_auth_command.prompt_for_missing_args')
    @patch('bitbucket_migration.commands.test_auth_command.BitbucketClient')
    @patch('bitbucket_migration.commands.test_auth_command.GitHubClient')
    @patch('bitbucket_migration.commands.test_auth_command._check_gh_cli_available')
    def test_run_test_auth_all_success(self, mock_check_cli, mock_github_client_class, 
                                       mock_bitbucket_client_class, mock_prompt, mock_args):
        """Test successful authentication for all services."""
        # Setup mocks
        mock_prompt.return_value = mock_args
        
        # Bitbucket client
        mock_bb_client = Mock()
        mock_bb_client.test_connection.return_value = True
        mock_bitbucket_client_class.return_value = mock_bb_client
        
        # GitHub client
        mock_gh_client = Mock()
        mock_gh_client.test_connection.return_value = True
        mock_github_client_class.return_value = mock_gh_client
        
        # GitHub CLI check
        mock_check_cli.return_value = {
            'available': True,
            'authenticated': True,
            'details': 'GitHub CLI 2.40.0 is installed and authenticated',
            'version': '2.40.0'
        }
        
        with patch('builtins.print'):  # Suppress output
            with patch('builtins.input', side_effect=['test-owner', 'test-repo', 'test-gh-token']):
                run_test_auth(mock_args)
    
    @patch('bitbucket_migration.commands.test_auth_command.prompt_for_missing_args')
    @patch('bitbucket_migration.commands.test_auth_command.BitbucketClient')
    @patch('bitbucket_migration.commands.test_auth_command.GitHubClient')
    @patch('bitbucket_migration.commands.test_auth_command._check_gh_cli_available')
    def test_run_test_auth_bitbucket_auth_failure(self, mock_check_cli, mock_github_client_class, 
                                                 mock_bitbucket_client_class, mock_prompt, mock_args):
        """Test Bitbucket authentication failure."""
        # Setup mocks
        mock_prompt.return_value = mock_args
        
        # Bitbucket client - authentication error
        mock_bb_client = Mock()
        mock_bb_client.test_connection.side_effect = AuthenticationError("Invalid credentials")
        mock_bitbucket_client_class.return_value = mock_bb_client
        
        # GitHub client
        mock_gh_client = Mock()
        mock_gh_client.test_connection.return_value = True
        mock_github_client_class.return_value = mock_gh_client
        
        # GitHub CLI check
        mock_check_cli.return_value = {
            'available': True,
            'authenticated': True,
            'details': 'GitHub CLI 2.40.0 is installed and authenticated',
            'version': '2.40.0'
        }
        
        with pytest.raises(SystemExit) as exc_info:
            with patch('builtins.print'):
                with patch('builtins.input', side_effect=['test-owner', 'test-repo', 'test-gh-token']):
                    run_test_auth(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.test_auth_command.prompt_for_missing_args')
    @patch('bitbucket_migration.commands.test_auth_command.BitbucketClient')
    @patch('bitbucket_migration.commands.test_auth_command.GitHubClient')
    @patch('bitbucket_migration.commands.test_auth_command._check_gh_cli_available')
    def test_run_test_auth_github_auth_failure(self, mock_check_cli, mock_github_client_class, 
                                             mock_bitbucket_client_class, mock_prompt, mock_args):
        """Test GitHub authentication failure."""
        # Setup mocks
        mock_prompt.return_value = mock_args
        
        # Bitbucket client
        mock_bb_client = Mock()
        mock_bb_client.test_connection.return_value = True
        mock_bitbucket_client_class.return_value = mock_bb_client
        
        # GitHub client - authentication error
        mock_gh_client = Mock()
        mock_gh_client.test_connection.side_effect = AuthenticationError("Invalid GitHub token")
        mock_github_client_class.return_value = mock_gh_client
        
        # GitHub CLI check
        mock_check_cli.return_value = {
            'available': True,
            'authenticated': True,
            'details': 'GitHub CLI 2.40.0 is installed and authenticated',
            'version': '2.40.0'
        }
        
        with pytest.raises(SystemExit) as exc_info:
            with patch('builtins.print'):
                with patch('builtins.input', side_effect=['test-owner', 'test-repo', 'test-gh-token']):
                    run_test_auth(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.test_auth_command.prompt_for_missing_args')
    @patch('bitbucket_migration.commands.test_auth_command.BitbucketClient')
    @patch('bitbucket_migration.commands.test_auth_command.GitHubClient')
    @patch('bitbucket_migration.commands.test_auth_command._check_gh_cli_available')
    def test_run_test_auth_api_error_404(self, mock_check_cli, mock_github_client_class, 
                                       mock_bitbucket_client_class, mock_prompt, mock_args):
        """Test API 404 error handling."""
        # Setup mocks
        mock_prompt.return_value = mock_args
        
        # Bitbucket client - API error with 404
        mock_bb_client = Mock()
        mock_bb_client.test_connection.side_effect = APIError("Repository not found", status_code=404)
        mock_bitbucket_client_class.return_value = mock_bb_client
        
        with pytest.raises(SystemExit) as exc_info:
            with patch('builtins.print'):
                with patch('builtins.input', side_effect=['test-owner', 'test-repo', 'test-gh-token']):
                    run_test_auth(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.test_auth_command.prompt_for_missing_args')
    @patch('bitbucket_migration.commands.test_auth_command.BitbucketClient')
    def test_run_test_auth_network_error(self, mock_bitbucket_client_class, mock_prompt, mock_args):
        """Test network error handling."""
        # Setup mocks
        mock_prompt.return_value = mock_args
        
        # Bitbucket client - network error
        mock_bb_client = Mock()
        mock_bb_client.test_connection.side_effect = NetworkError("Connection failed")
        mock_bitbucket_client_class.return_value = mock_bb_client
        
        with pytest.raises(SystemExit) as exc_info:
            with patch('builtins.print'):
                with patch('builtins.input', side_effect=['test-owner', 'test-repo', 'test-gh-token']):
                    run_test_auth(mock_args)
        
        assert exc_info.value.code == 1


class TestTestAuthCommandPromptForMissingArgs:
    """Test the prompt_for_missing_args function for test-auth command."""
    
    def test_prompt_for_missing_args_with_empty_values(self):
        """Test prompting for empty required fields."""
        args = Namespace()
        args.workspace = ""
        args.repo = ""
        args.email = ""
        args.token = ""
        args.gh_owner = ""
        args.gh_repo = ""
        args.gh_token = ""
        
        with patch('builtins.input', side_effect=[
            'test-workspace', 'test-repo', 'test@example.com', 'test-gh-owner', 'test-gh-repo'
        ]):
            with patch('bitbucket_migration.commands.test_auth_command.getpass.getpass', side_effect=['test-token', 'test-gh-token']):
                with patch('os.getenv', return_value=None):
                    result = prompt_for_missing_args(args, [
                        'workspace', 'repo', 'email', 'token', 'gh_owner', 'gh_repo', 'gh_token'
                    ])
                    
                    assert result.workspace == 'test-workspace'
                    assert result.repo == 'test-repo'
                    assert result.email == 'test@example.com'
                    assert result.token == 'test-token'
                    assert result.gh_owner == 'test-gh-owner'
                    assert result.gh_repo == 'test-gh-repo'
                    assert result.gh_token == 'test-gh-token'
    
    def test_prompt_for_missing_args_skips_existing_values(self):
        """Test that existing values are not prompted for."""
        args = Namespace()
        args.workspace = 'existing-workspace'
        args.repo = 'existing-repo'
        args.email = 'existing@example.com'
        args.token = 'existing-token'
        args.gh_owner = 'existing-gh-owner'
        args.gh_repo = 'existing-gh-repo'
        args.gh_token = 'existing-gh-token'
        
        with patch('builtins.input', side_effect=['']) as mock_input:
            with patch('bitbucket_migration.commands.test_auth_command.getpass.getpass', return_value='') as mock_getpass:
                result = prompt_for_missing_args(args, [
                    'workspace', 'repo', 'email', 'token', 'gh_owner', 'gh_repo', 'gh_token'
                ])
                
                # Should not prompt for existing values
                mock_input.assert_not_called()
                mock_getpass.assert_not_called()
                
                assert result.workspace == 'existing-workspace'
                assert result.repo == 'existing-repo'
                assert result.email == 'existing@example.com'
                assert result.token == 'existing-token'
                assert result.gh_owner == 'existing-gh-owner'
                assert result.gh_repo == 'existing-gh-repo'
                assert result.gh_token == 'existing-gh-token'
    
    def test_prompt_for_missing_args_uses_environment_variables(self):
        """Test that environment variables are used when available."""
        args = Namespace()
        args.workspace = ""
        args.repo = "test-repo"
        args.email = ""
        args.token = ""
        args.gh_owner = ""
        args.gh_repo = "test-gh-repo"
        args.gh_token = ""
        
        def mock_getenv(key):
            return {
                'BITBUCKET_TOKEN': 'env-bb-token',
                'BITBUCKET_API_TOKEN': None,
                'GITHUB_TOKEN': 'env-gh-token',
                'GITHUB_API_TOKEN': None
            }.get(key)
        
        with patch('os.getenv', side_effect=mock_getenv):
            with patch('builtins.input', side_effect=['test-workspace', 'test@example.com', 'test-gh-owner']) as mock_input:
                result = prompt_for_missing_args(args, [
                    'workspace', 'email', 'token', 'gh_owner', 'gh_token'
                ])
                
                # Should not prompt for tokens (found in env)
                assert mock_input.call_count == 3  # Only workspace, email, and gh_owner
                assert result.token == 'env-bb-token'
                assert result.gh_token == 'env-gh-token'