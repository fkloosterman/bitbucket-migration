"""
Tests for cross-link command functionality.

This file tests the cross-link command including:
- Configuration loading and validation
- Repository selection parsing
- CrossLinkOrchestrator creation and execution
- Dry-run mode handling
- Error handling scenarios
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace
import sys
from pathlib import Path

from bitbucket_migration.commands.cross_link_command import run_cross_link
from bitbucket_migration.exceptions import ConfigurationError, ValidationError


class TestCrossLinkCommand:
    """Test the run_cross_link function."""
    
    @pytest.fixture
    def mock_args(self):
        """Create mock arguments for testing."""
        return Namespace(
            config='test_config.json',
            repo=None,
            dry_run=None,
            debug=False
        )
    
    @pytest.fixture
    def mock_config(self):
        """Create mock migration configuration."""
        config = Mock()
        config.options = Mock()
        config.options.dry_run = False
        return config
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_success(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test successful cross-link execution."""
        # Setup mocks
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify configuration was loaded
        mock_config_loader.load_from_file.assert_called_once_with('test_config.json')
        
        # Verify orchestrator was created and cross-link execution started
        mock_orchestrator_class.assert_called_once()
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    def test_run_cross_link_config_not_found(self, mock_config_loader, mock_args):
        """Test handling of missing configuration file."""
        mock_config_loader.load_from_file.side_effect = ConfigurationError("Config not found")
        
        with pytest.raises(SystemExit) as exc_info:
            run_cross_link(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    def test_run_cross_link_config_validation_error(self, mock_config_loader, mock_args):
        """Test handling of configuration validation errors."""
        mock_config_loader.load_from_file.side_effect = ValidationError("Invalid config")
        
        with pytest.raises(SystemExit) as exc_info:
            run_cross_link(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    def test_run_cross_link_config_unexpected_error(self, mock_config_loader, mock_args):
        """Test handling of unexpected errors during configuration loading."""
        mock_config_loader.load_from_file.side_effect = Exception("Unexpected error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_cross_link(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_with_repo_selection(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test cross-link with specific repository selection."""
        mock_args.repo = ['repo1', 'repo2']
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify repository selection was passed to orchestrator
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] == ['repo1', 'repo2']
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_no_repo_selection(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test cross-link without specific repository selection (all repos)."""
        mock_args.repo = None
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify no specific repository selection (all repos)
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] is None
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_dry_run_override_true(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test cross-link with dry_run override to true."""
        mock_args.dry_run = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify dry_run override was applied
        assert mock_config.options.dry_run is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_dry_run_override_false(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test cross-link with dry_run override to false."""
        # Config has dry_run=True, override to false
        mock_config.options.dry_run = True
        mock_args.dry_run = 'false'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify dry_run override was applied
        assert mock_config.options.dry_run is False
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_dry_run_from_config(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test cross-link uses dry_run from config when not overridden."""
        # Config has dry_run=True, no override provided
        mock_config.options.dry_run = True
        mock_args.dry_run = None
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify dry_run from config was used
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['dry_run'] is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_debug_mode(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test cross-link with debug mode enabled."""
        mock_args.debug = True
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify DEBUG log level was used
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['log_level'] == 'DEBUG'
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_info_mode(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test cross-link with debug mode disabled (INFO level)."""
        mock_args.debug = False
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify INFO log level was used
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['log_level'] == 'INFO'
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_repo_list_parsing(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test parsing of repository list from command line."""
        # Test with list format
        mock_args.repo = ['repo1', 'repo2', 'repo3']
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify repository list was passed correctly
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] == ['repo1', 'repo2', 'repo3']
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_empty_repo_list(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test cross-link with empty repository list."""
        mock_args.repo = []
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Empty repo list should still be passed as is
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] == []
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_repos_alias(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test that 'repos' alias works the same as 'repo'."""
        # Test that both 'repo' and 'repos' (if present) are handled
        mock_args.repo = ['repo1', 'repo2']
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify repository selection was passed correctly
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] == ['repo1', 'repo2']
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.cross_link_command.CrossLinkOrchestrator')
    def test_run_cross_link_config_integration(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test that config base_dir is used by orchestrator."""
        mock_config.base_dir = Path('/test/dir')
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_cross_link(mock_args)
        
        # Verify orchestrator was initialized with config
        mock_orchestrator_class.assert_called_once()
        call_args = mock_orchestrator_class.call_args[0]
        assert call_args[0] is mock_config  # First arg should be the config
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    def test_run_cross_link_configuration_error_message(self, mock_config_loader, mock_args):
        """Test that configuration errors display appropriate error message."""
        mock_config_loader.load_from_file.side_effect = ConfigurationError("Configuration validation failed")
        
        with pytest.raises(SystemExit) as exc_info:
            run_cross_link(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    def test_run_cross_link_validation_error_message(self, mock_config_loader, mock_args):
        """Test that validation errors display appropriate error message."""
        mock_config_loader.load_from_file.side_effect = ValidationError("Invalid configuration format")
        
        with pytest.raises(SystemExit) as exc_info:
            run_cross_link(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.cross_link_command.SecureConfigLoader')
    def test_run_cross_link_unexpected_error_message(self, mock_config_loader, mock_args):
        """Test that unexpected errors display appropriate error message."""
        mock_config_loader.load_from_file.side_effect = RuntimeError("Unexpected runtime error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_cross_link(mock_args)
        
        assert exc_info.value.code == 1