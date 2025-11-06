"""
Tests for migration command functionality.

This file tests the migration command including:
- Configuration loading and validation
- Repository selection parsing
- Configuration option overrides
- Migration orchestrator creation and execution
- Error handling scenarios
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace
import sys
from pathlib import Path

from bitbucket_migration.commands.migration_command import run_migration
from bitbucket_migration.exceptions import ConfigurationError, ValidationError


class TestMigrationCommand:
    """Test the run_migration function."""
    
    @pytest.fixture
    def mock_args(self):
        """Create mock arguments for testing."""
        return Namespace(
            config='test_config.json',
            repo=None,
            skip_issues='false',
            open_issues_only='false',
            skip_prs='false',
            open_prs_only='false',
            skip_pr_as_issue='false',
            skip_milestones='false',
            open_milestones_only='false',
            use_gh_cli='false',
            dry_run='true',
            debug=False
        )
    
    @pytest.fixture
    def mock_config(self):
        """Create mock migration configuration."""
        config = Mock()
        config.options = Mock()
        config.options.dry_run = False
        config.options.skip_issues = False
        config.options.open_issues_only = False
        config.options.skip_prs = False
        config.options.open_prs_only = False
        config.options.skip_pr_as_issue = False
        config.options.skip_milestones = False
        config.options.open_milestones_only = False
        config.options.use_gh_cli = False
        return config
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_success(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test successful migration execution."""
        # Setup mocks
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify configuration was loaded
        mock_config_loader.load_from_file.assert_called_once_with('test_config.json')
        
        # Verify orchestrator was created and migration executed
        mock_orchestrator_class.assert_called_once()
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    def test_run_migration_config_not_found(self, mock_config_loader, mock_args):
        """Test handling of missing configuration file."""
        mock_config_loader.load_from_file.side_effect = ConfigurationError("Config not found")
        
        with pytest.raises(SystemExit) as exc_info:
            run_migration(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    def test_run_migration_config_validation_error(self, mock_config_loader, mock_args):
        """Test handling of configuration validation errors."""
        mock_config_loader.load_from_file.side_effect = ValidationError("Invalid config")
        
        with pytest.raises(SystemExit) as exc_info:
            run_migration(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    def test_run_migration_config_unexpected_error(self, mock_config_loader, mock_args):
        """Test handling of unexpected errors during configuration loading."""
        mock_config_loader.load_from_file.side_effect = Exception("Unexpected error")
        
        with pytest.raises(SystemExit) as exc_info:
            run_migration(mock_args)
        
        assert exc_info.value.code == 1
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_with_repo_selection(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with specific repository selection."""
        mock_args.repo = ['repo1', 'repo2']
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify repository selection was passed to orchestrator
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] == ['repo1', 'repo2']
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_no_repo_selection(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration without specific repository selection (all repos)."""
        mock_args.repo = None
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify no specific repository selection (all repos)
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] is None
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_skip_issues_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with skip_issues override."""
        mock_args.skip_issues = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.skip_issues is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_open_issues_only_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with open_issues_only override."""
        mock_args.open_issues_only = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.open_issues_only is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_skip_prs_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with skip_prs override."""
        mock_args.skip_prs = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.skip_prs is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_open_prs_only_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with open_prs_only override."""
        mock_args.open_prs_only = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.open_prs_only is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_skip_pr_as_issue_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with skip_pr_as_issue override."""
        mock_args.skip_pr_as_issue = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.skip_pr_as_issue is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_skip_milestones_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with skip_milestones override."""
        mock_args.skip_milestones = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.skip_milestones is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_open_milestones_only_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with open_milestones_only override."""
        mock_args.open_milestones_only = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.open_milestones_only is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_use_gh_cli_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with use_gh_cli override."""
        mock_args.use_gh_cli = 'true'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.use_gh_cli is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_dry_run_override(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with dry_run override."""
        mock_args.dry_run = 'false'  # Change to false
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify override was applied
        assert mock_config.options.dry_run is False
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_debug_mode(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with debug mode enabled."""
        mock_args.debug = True
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify DEBUG log level was used
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['log_level'] == 'DEBUG'
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_info_mode(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with debug mode disabled (INFO level)."""
        mock_args.debug = False
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify INFO log level was used
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['log_level'] == 'INFO'
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_dry_run_from_config(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration uses dry_run from config when not overridden."""
        # Config has dry_run=True, no override provided
        mock_config.options.dry_run = True
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify dry_run from config was used
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['dry_run'] is True
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_multiple_overrides(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with multiple configuration overrides."""
        mock_args.skip_issues = 'true'
        mock_args.skip_prs = 'true'
        mock_args.dry_run = 'false'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify all overrides were applied
        assert mock_config.options.skip_issues is True
        assert mock_config.options.skip_prs is True
        assert mock_config.options.dry_run is False
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_repo_list_parsing(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test parsing of repository list from command line."""
        # Test with comma-separated list
        mock_args.repo = 'repo1, repo2, repo3'
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify repository list was parsed correctly
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] == ['repo1', 'repo2', 'repo3']
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_empty_repo_list(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test migration with empty repository list."""
        mock_args.repo = ''
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Empty repo list should be treated as None (all repos)
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] is None
        mock_orchestrator.run_migration.assert_called_once()
    
    @patch('bitbucket_migration.commands.migration_command.SecureConfigLoader')
    @patch('bitbucket_migration.commands.migration_command.MigrationOrchestrator')
    def test_run_migration_repos_alias(self, mock_orchestrator_class, mock_config_loader, mock_args, mock_config):
        """Test that 'repos' alias works the same as 'repo'."""
        # Test that both 'repo' and 'repos' (if present) are handled
        mock_args.repo = ['repo1', 'repo2']
        mock_config_loader.load_from_file.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_migration(mock_args)
        
        # Verify repository selection was passed correctly
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['selected_repos'] == ['repo1', 'repo2']
        mock_orchestrator.run_migration.assert_called_once()