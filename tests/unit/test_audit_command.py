"""
Tests for audit command functionality.

This file tests the audit command including:
- Repository auditing flow
- Multi-repository discovery and selection
- Configuration generation
- Error handling and validation
- Interactive prompting
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace
import sys
from pathlib import Path

from bitbucket_migration.commands.audit_command import run_audit, prompt_for_missing_args
from bitbucket_migration.exceptions import APIError, AuthenticationError, NetworkError, ValidationError


class TestAuditCommandPromptForMissingArgs:
    """Test the prompt_for_missing_args function."""
    
    def test_prompt_for_missing_args_with_empty_values(self):
        """Test prompting for empty required fields."""
        args = Namespace()
        args.workspace = ""
        args.repo = "test-repo"
        args.email = ""
        args.token = ""
        
        with patch('builtins.input', side_effect=['test-workspace', 'test@example.com']):
            with patch('bitbucket_migration.commands.audit_command.getpass.getpass', return_value='test-token'):
                with patch('os.getenv', return_value=None):
                    result = prompt_for_missing_args(args, ['workspace', 'email', 'token'])
                    
                    assert result.workspace == 'test-workspace'
                    assert result.email == 'test@example.com'
                    assert result.token == 'test-token'
                    assert result.repo == 'test-repo'  # Unchanged
    
    def test_prompt_for_missing_args_skips_existing_values(self):
        """Test that existing values are not prompted for."""
        args = Namespace()
        args.workspace = 'existing-workspace'
        args.repo = 'existing-repo'
        args.email = 'existing@example.com'
        args.token = 'existing-token'
        
        with patch('builtins.input', side_effect=['']) as mock_input:
            with patch('bitbucket_migration.commands.audit_command.getpass.getpass', return_value='') as mock_getpass:
                result = prompt_for_missing_args(args, ['workspace', 'email', 'token'])
                
                # Should not prompt for existing values
                mock_input.assert_not_called()
                mock_getpass.assert_not_called()
                
                assert result.workspace == 'existing-workspace'
                assert result.email == 'existing@example.com'
                assert result.token == 'existing-token'
    
    def test_prompt_for_missing_args_uses_environment_variables(self):
        """Test that environment variables are used when available."""
        args = Namespace()
        args.workspace = ""
        args.repo = "test-repo"
        args.email = ""
        args.token = ""
        
        with patch('os.getenv', side_effect=lambda key: {
            'BITBUCKET_TOKEN': 'env-token',
            'BITBUCKET_API_TOKEN': None
        }.get(key)):
            with patch('builtins.input', side_effect=['test-workspace', 'test@example.com']) as mock_input:
                result = prompt_for_missing_args(args, ['workspace', 'email', 'token'])
                
                # Should not prompt for token (found in env)
                assert mock_input.call_count == 2  # Only workspace and email
                assert result.token == 'env-token'


class TestAuditCommandRunAudit:
    """Test the run_audit function."""
    
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
            discover=False,
            debug=False,
            base_dir='.'
        )
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    @patch('bitbucket_migration.commands.audit_command.BaseDirManager')
    @patch('bitbucket_migration.commands.audit_command.SecureConfigLoader')
    def test_run_audit_single_repo_success(self, mock_config_loader, mock_base_dir_manager, mock_auditor, mock_args):
        """Test successful audit of a single repository."""
        # Setup mocks
        mock_config = Mock()
        mock_config.bitbucket.workspace = 'existing-workspace'
        mock_config.bitbucket.email = 'existing@example.com'
        mock_config.github.owner = 'existing-owner'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_base_dir = Mock()
        mock_base_dir_manager.return_value = mock_base_dir
        mock_base_dir.get_config_path.return_value = Path('config.json')
        mock_base_dir.base_dir = Path('.')
        
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.audit_repositories.return_value = []
        mock_audit_orchestrator.generate_config.return_value = {}
        mock_audit_orchestrator.save_config.return_value = None
        
        with patch('builtins.input', side_effect=['test-owner']):
            run_audit(mock_args)
        
        # Verify audit was called
        mock_audit_orchestrator.audit_repositories.assert_called_once_with(
            repo_names=['test-repo'], save_reports=True
        )
        mock_audit_orchestrator.generate_config.assert_called_once()
        mock_audit_orchestrator.save_config.assert_called_once()
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    @patch('bitbucket_migration.commands.audit_command.BaseDirManager')
    @patch('bitbucket_migration.commands.audit_command.SecureConfigLoader')
    def test_run_audit_explicit_repos_success(self, mock_config_loader, mock_base_dir_manager, mock_auditor, mock_args):
        """Test successful audit with explicit repository list."""
        mock_args.repo = ['repo1', 'repo2', 'repo3']
        mock_args.discover = False
        
        # Setup mocks
        mock_config_loader.load_from_file.side_effect = Exception("Config not found")
        
        mock_base_dir = Mock()
        mock_base_dir_manager.return_value = mock_base_dir
        mock_base_dir.get_config_path.return_value = Path('config.json')
        mock_base_dir.base_dir = Path('.')
        
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.audit_repositories.return_value = []
        mock_audit_orchestrator.generate_config.return_value = {}
        mock_audit_orchestrator.save_config.return_value = None
        
        with patch('builtins.input', side_effect=['test-owner']):
            run_audit(mock_args)
        
        # Verify audit was called for all repos
        mock_audit_orchestrator.audit_repositories.assert_called_once_with(
            repo_names=['repo1', 'repo2', 'repo3'], save_reports=True
        )
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    @patch('bitbucket_migration.commands.audit_command.BaseDirManager')
    @patch('bitbucket_migration.commands.audit_command.SecureConfigLoader')
    def test_run_audit_discovery_mode_success(self, mock_config_loader, mock_base_dir_manager, mock_auditor, mock_args):
        """Test successful audit in discovery mode."""
        mock_args.discover = True
        
        # Setup mocks
        mock_config_loader.load_from_file.side_effect = Exception("Config not found")
        
        mock_base_dir = Mock()
        mock_base_dir_manager.return_value = mock_base_dir
        mock_base_dir.get_config_path.return_value = Path('config.json')
        mock_base_dir.base_dir = Path('.')
        
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.discover_repositories.return_value = ['repo1', 'repo2', 'repo3']
        mock_audit_orchestrator.audit_repositories.return_value = []
        mock_audit_orchestrator.generate_config.return_value = {}
        mock_audit_orchestrator.save_config.return_value = None
        
        with patch('builtins.input', side_effect=['1', '', 'test-owner']):  # Select repo1, no external repos, then gh_owner
            run_audit(mock_args)
        
        # Verify discovery and audit were called
        mock_audit_orchestrator.discover_repositories.assert_called_once()
        mock_audit_orchestrator.audit_repositories.assert_called_once_with(
            repo_names=['repo1'], save_reports=True
        )
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    @patch('bitbucket_migration.commands.audit_command.BaseDirManager')
    @patch('bitbucket_migration.commands.audit_command.SecureConfigLoader')
    def test_run_audit_discovery_mode_all_repos(self, mock_config_loader, mock_base_dir_manager, mock_auditor, mock_args):
        """Test discovery mode with all repositories selected."""
        mock_args.discover = True
        
        # Setup mocks
        mock_config_loader.load_from_file.side_effect = Exception("Config not found")
        
        mock_base_dir = Mock()
        mock_base_dir_manager.return_value = mock_base_dir
        mock_base_dir.get_config_path.return_value = Path('config.json')
        mock_base_dir.base_dir = Path('.')
        
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.discover_repositories.return_value = ['repo1', 'repo2', 'repo3']
        mock_audit_orchestrator.audit_repositories.return_value = []
        mock_audit_orchestrator.generate_config.return_value = {}
        mock_audit_orchestrator.save_config.return_value = None
        
        with patch('builtins.input', side_effect=['all', '', 'test-owner']):  # Select all repos, no external repos, then gh_owner
            run_audit(mock_args)
        
        # Verify all repos were selected and audited
        mock_audit_orchestrator.audit_repositories.assert_called_once_with(
            repo_names=['repo1', 'repo2', 'repo3'], save_reports=True
        )
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_keyboard_interrupt(self, mock_auditor, mock_args):
        """Test handling of keyboard interrupt during audit."""
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.audit_repositories.side_effect = KeyboardInterrupt()
        
        with pytest.raises(SystemExit) as exc_info:
            run_audit(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_api_error(self, mock_auditor, mock_args):
        """Test handling of API errors during audit."""
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.audit_repositories.side_effect = APIError("API test error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_audit(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_authentication_error(self, mock_auditor, mock_args):
        """Test handling of authentication errors during audit."""
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.audit_repositories.side_effect = AuthenticationError("Auth test error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_audit(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_network_error(self, mock_auditor, mock_args):
        """Test handling of network errors during audit."""
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.audit_repositories.side_effect = NetworkError("Network test error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_audit(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_validation_error(self, mock_auditor, mock_args):
        """Test handling of validation errors during audit."""
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.audit_repositories.side_effect = ValidationError("Validation test error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_audit(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_unexpected_error(self, mock_auditor, mock_args):
        """Test handling of unexpected errors during audit."""
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.audit_repositories.side_effect = Exception("Unexpected test error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_audit(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_discovery_no_repositories(self, mock_auditor, mock_args):
        """Test discovery mode when no repositories are found."""
        mock_args.discover = True
        
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.discover_repositories.return_value = []
        
        with patch('builtins.print'):  # Suppress output
            run_audit(mock_args)
        
        # Should not proceed to audit if no repos found
        mock_audit_orchestrator.audit_repositories.assert_not_called()
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_discovery_keyboard_interrupt(self, mock_auditor, mock_args):
        """Test handling of keyboard interrupt during discovery."""
        mock_args.discover = True
        
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.discover_repositories.side_effect = KeyboardInterrupt()
        
        with pytest.raises(SystemExit) as exc_info:
            run_audit(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.audit_command.AuditOrchestrator')
    def test_run_audit_discovery_api_error(self, mock_auditor, mock_args):
        """Test handling of API errors during discovery."""
        mock_args.discover = True
        
        mock_audit_orchestrator = Mock()
        mock_auditor.return_value = mock_audit_orchestrator
        mock_audit_orchestrator.discover_repositories.side_effect = APIError("Discovery API error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_audit(mock_args)
        
        assert exc_info.value.code == 1
    
    def test_run_audit_discovery_invalid_repo_selection(self, mock_args):
        """Test handling of invalid repository selection in discovery mode."""
        mock_args.discover = True
        
        with patch('bitbucket_migration.commands.audit_command.AuditOrchestrator') as mock_auditor_class:
            mock_audit_orchestrator = Mock()
            mock_auditor_class.return_value = mock_audit_orchestrator
            mock_audit_orchestrator.discover_repositories.return_value = ['repo1', 'repo2', 'repo3']
            
            with patch('builtins.input', side_effect=['999', 'test-owner']):  # Invalid repo number
                with patch('builtins.print'):  # Suppress output
                    run_audit(mock_args)
            
            # Should not proceed to audit if invalid selection
            mock_audit_orchestrator.audit_repositories.assert_not_called()
    
    def test_run_audit_discovery_overlapping_repos(self, mock_args):
        """Test handling of overlapping repository selection in discovery mode."""
        mock_args.discover = True
        
        with patch('bitbucket_migration.commands.audit_command.AuditOrchestrator') as mock_auditor_class:
            mock_audit_orchestrator = Mock()
            mock_auditor_class.return_value = mock_audit_orchestrator
            mock_audit_orchestrator.discover_repositories.return_value = ['repo1', 'repo2', 'repo3']
            
            with patch('builtins.input', side_effect=['1,2', '1', 'test-owner']):  # repo1 in both migrate and external
                with patch('builtins.print'):  # Suppress output
                    run_audit(mock_args)
            
            # Should not proceed to audit if overlapping repos
            mock_audit_orchestrator.audit_repositories.assert_not_called()
    
    def test_run_audit_discovery_empty_selection(self, mock_args):
        """Test handling of empty repository selection in discovery mode."""
        mock_args.discover = True
        
        with patch('bitbucket_migration.commands.audit_command.AuditOrchestrator') as mock_auditor_class:
            mock_audit_orchestrator = Mock()
            mock_auditor_class.return_value = mock_audit_orchestrator
            mock_audit_orchestrator.discover_repositories.return_value = ['repo1', 'repo2', 'repo3']
            
            with patch('builtins.input', side_effect=['', 'test-owner']):  # Empty selection
                with patch('builtins.print'):  # Suppress output
                    run_audit(mock_args)
            
            # Should not proceed to audit if no selection
            mock_audit_orchestrator.audit_repositories.assert_not_called()
    
    def test_run_audit_debug_mode(self, mock_args):
        """Test that debug mode sets appropriate log level."""
        mock_args.debug = True
        
        with patch('bitbucket_migration.commands.audit_command.AuditOrchestrator') as mock_auditor_class:
            with patch('bitbucket_migration.commands.audit_command.BaseDirManager'):
                with patch('bitbucket_migration.commands.audit_command.SecureConfigLoader.load_from_file', side_effect=Exception("Config not found")):
                    mock_audit_orchestrator = Mock()
                    mock_auditor_class.return_value = mock_audit_orchestrator
                    mock_audit_orchestrator.audit_repositories.return_value = []
                    mock_audit_orchestrator.generate_config.return_value = {}
                    mock_audit_orchestrator.save_config.return_value = None
                    
                    with patch('builtins.input', side_effect=['test-owner']):
                        run_audit(mock_args)
                    
                    # Verify DEBUG log level was used
                    mock_auditor_class.assert_called_once()
                    call_kwargs = mock_auditor_class.call_args[1]
                    assert call_kwargs['log_level'] == 'DEBUG'
    
    def test_run_audit_info_mode(self, mock_args):
        """Test that non-debug mode uses INFO log level."""
        mock_args.debug = False
        
        with patch('bitbucket_migration.commands.audit_command.AuditOrchestrator') as mock_auditor_class:
            with patch('bitbucket_migration.commands.audit_command.BaseDirManager'):
                with patch('bitbucket_migration.commands.audit_command.SecureConfigLoader.load_from_file', side_effect=Exception("Config not found")):
                    mock_audit_orchestrator = Mock()
                    mock_auditor_class.return_value = mock_audit_orchestrator
                    mock_audit_orchestrator.audit_repositories.return_value = []
                    mock_audit_orchestrator.generate_config.return_value = {}
                    mock_audit_orchestrator.save_config.return_value = None
                    
                    with patch('builtins.input', side_effect=['test-owner']):
                        run_audit(mock_args)
                    
                    # Verify INFO log level was used
                    mock_auditor_class.assert_called_once()
                    call_kwargs = mock_auditor_class.call_args[1]
                    assert call_kwargs['log_level'] == 'INFO'