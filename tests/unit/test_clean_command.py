"""
Tests for clean command functionality.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bitbucket_migration.migrate_bitbucket_to_github import run_clean


class TestCleanCommand:
    """Test clean command functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        """Set up test fixtures."""
        self.temp_dir = tmp_path
        monkeypatch.chdir(self.temp_dir)
        yield

    def create_test_structure(self):
        """Create a test directory structure with various migration outputs."""
        from bitbucket_migration.utils.base_dir_manager import BaseDirManager
        
        # Use BaseDirManager to create files with proper tracking
        manager = BaseDirManager(str(self.temp_dir))
        
        # Create audit files
        manager.create_file(
            "audit/workspace1_repo1/report.json",
            {"test": "data"},
            subcommand="audit",
            workspace="workspace1",
            repo="repo1",
            category="report"
        )
        
        # Create dry-run files
        manager.create_file(
            "dry-run/workspace1_repo1/dry_run_log.txt",
            "dry run log",
            subcommand="dry-run",
            workspace="workspace1",
            repo="repo1",
            category="log"
        )
        
        # Create migrate files
        manager.create_file(
            "migrate/workspace1_repo1/migration_report.md",
            "# Migration Report",
            subcommand="migrate",
            workspace="workspace1",
            repo="repo1",
            category="report"
        )
        
        # Create config file (not tracked)
        config_file = self.temp_dir / "config.json"
        config_file.write_text('{"format_version": "2.0", "base_dir": "."}')
        
        return {
            'audit_dir': self.temp_dir / "audit",
            'dry_run_dir': self.temp_dir / "dry-run",
            'migrate_dir': self.temp_dir / "migrate",
            'config_file': config_file
        }

    def test_clean_audit_only(self):
        """Test cleaning only audit directory."""
        structure = self.create_test_structure()

        # Create args for cleaning audit only
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.subcommand = ['audit']
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        # Run clean command
        with patch('builtins.input', return_value='y'):
            run_clean(args)

        # Verify only audit directory was removed
        assert not structure['audit_dir'].exists()
        assert structure['dry_run_dir'].exists()
        assert structure['migrate_dir'].exists()
        assert structure['config_file'].exists()

    def test_clean_dry_run_only(self):
        """Test cleaning only dry-run directory."""
        structure = self.create_test_structure()

        # Create args for cleaning dry-run only
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.subcommand = ['dry-run']
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        # Run clean command
        with patch('builtins.input', return_value='y'):
            run_clean(args)

        # Verify only dry-run directory was removed
        assert structure['audit_dir'].exists()
        assert not structure['dry_run_dir'].exists()
        assert structure['migrate_dir'].exists()
        assert structure['config_file'].exists()

    def test_clean_migrate_only(self):
        """Test cleaning only migrate directory."""
        structure = self.create_test_structure()

        # Create args for cleaning migrate only
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.subcommand = ['migrate']
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        # Run clean command
        with patch('builtins.input', return_value='y'):
            run_clean(args)

        # Verify only migrate directory was removed
        assert structure['audit_dir'].exists()
        assert structure['dry_run_dir'].exists()
        assert not structure['migrate_dir'].exists()
        assert structure['config_file'].exists()

    def test_clean_all(self):
        """Test cleaning all output directories."""
        structure = self.create_test_structure()

        # Create args for cleaning all (no filters = clean everything)
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.subcommand = None
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        # Run clean command
        with patch('builtins.input', return_value='y'):
            run_clean(args)

        # Verify all output directories were removed
        assert not structure['audit_dir'].exists()
        assert not structure['dry_run_dir'].exists()
        assert not structure['migrate_dir'].exists()
        assert structure['config_file'].exists()

    def test_clean_reset(self):
        """Test reset mode that removes everything."""
        structure = self.create_test_structure()

        # Create args for reset
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.audit = False
        args.dry_run = False
        args.migrate = False
        args.all = False
        args.reset = True

        # Run clean command
        with patch('builtins.input', return_value='yes'):
            run_clean(args)

        # Verify everything was removed
        assert not structure['audit_dir'].exists()
        assert not structure['dry_run_dir'].exists()
        assert not structure['migrate_dir'].exists()
        assert not structure['config_file'].exists()

    def test_clean_cancelled(self):
        """Test that cleaning can be cancelled."""
        structure = self.create_test_structure()

        # Create args for cleaning all
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.subcommand = None
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        # Run clean command
        with patch('builtins.input', return_value='n'):
            run_clean(args)

        # Verify nothing was removed
        assert structure['audit_dir'].exists()
        assert structure['dry_run_dir'].exists()
        assert structure['migrate_dir'].exists()
        assert structure['config_file'].exists()

    def test_clean_no_filters_specified(self, capsys):
        """Test that no filters means clean everything (with confirmation)."""
        # Create args with no filters
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.subcommand = None
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        # Run clean command with 'no' to cancel
        with patch('builtins.input', return_value='n'):
            run_clean(args)

        # Check message - should prompt for cleaning all outputs
        captured = capsys.readouterr()
        assert "Cleaning all outputs from base directory" in captured.out

    @patch('bitbucket_migration.config.secure_config.SecureConfigLoader.load_from_file')
    def test_clean_with_config_file(self, mock_loader):
        """Test cleaning using base directory from config file."""
        # Mock config loader
        mock_config = MagicMock()
        mock_config.base_dir = str(self.temp_dir)
        mock_loader.return_value = mock_config

        # Create structure
        structure = self.create_test_structure()

        # Create args with config file
        args = MagicMock()
        args.config = 'config.json'
        args.base_dir = None
        args.subcommand = ['audit']
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        with patch('builtins.input', return_value='y'):
            run_clean(args)

        # Verify audit directory was removed
        assert not structure['audit_dir'].exists()
        assert structure['dry_run_dir'].exists()
        assert structure['migrate_dir'].exists()
        assert structure['config_file'].exists()

        # Verify the mock was called
        mock_loader.assert_called_once_with('config.json')

    @patch('bitbucket_migration.config.secure_config.SecureConfigLoader.load_from_file')
    def test_clean_config_load_error(self, mock_loader, capsys):
        """Test error handling when config file cannot be loaded."""
        mock_loader.side_effect = Exception("Config load error")

        # Create args with config file
        args = MagicMock()
        args.config = 'config.json'
        args.base_dir = None
        args.subcommand = ['audit']
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        # Run clean command - should exit with error
        with pytest.raises(SystemExit):
            run_clean(args)

        # Check error message
        captured = capsys.readouterr()
        assert "Error loading config" in captured.out

    def test_clean_nonexistent_directories(self, capsys):
        """Test cleaning when directories don't exist."""
        # Create args for cleaning all
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.subcommand = None
        args.workspace = None
        args.repo = None
        args.dry_run = False
        args.reset = False

        with patch('builtins.input', return_value='y'):
            run_clean(args)

        # Should complete successfully even if directories don't exist
        captured = capsys.readouterr()
        assert "Clean completed!" in captured.out or "No folders or files found" in captured.out

    def test_clean_reset_cancelled(self):
        """Test that reset can be cancelled."""
        structure = self.create_test_structure()

        # Create args for reset
        args = MagicMock()
        args.config = None
        args.base_dir = '.'
        args.audit = False
        args.dry_run = False
        args.migrate = False
        args.all = False
        args.reset = True

        # Run clean command
        with patch('builtins.input', return_value='no'):
            run_clean(args)

        # Verify nothing was removed
        assert structure['audit_dir'].exists()
        assert structure['dry_run_dir'].exists()
        assert structure['migrate_dir'].exists()
        assert structure['config_file'].exists()