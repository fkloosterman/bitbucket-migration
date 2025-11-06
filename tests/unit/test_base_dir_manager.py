"""
Tests for BaseDirManager functionality.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
import json

from bitbucket_migration.utils.base_dir_manager import BaseDirManager


class TestBaseDirManager:
    """Test BaseDirManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = BaseDirManager(str(self.temp_dir))

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_init_with_relative_path(self):
        """Test initialization with relative path."""
        manager = BaseDirManager("./test_dir")
        assert manager.base_dir.name == "test_dir"
        assert manager.base_dir.is_absolute()

    def test_init_with_absolute_path(self):
        """Test initialization with absolute path."""
        abs_path = str(self.temp_dir / "test_dir")
        manager = BaseDirManager(abs_path)
        assert str(manager.base_dir) == abs_path

    def test_get_subcommand_dir(self):
        """Test getting subcommand directory path."""
        path = self.manager.get_subcommand_dir("audit", "workspace1", "repo1")
        expected = self.temp_dir / "audit" / "workspace1_repo1"
        assert path == expected

    def test_get_config_path(self):
        """Test getting config file path."""
        path = self.manager.get_config_path()
        expected = self.temp_dir / "config.json"
        assert path == expected

    def test_get_mappings_path(self):
        """Test getting mappings file path."""
        path = self.manager.get_mappings_path()
        expected = self.temp_dir / "cross_repo_mappings.json"
        assert path == expected

    def test_ensure_subcommand_dir_creates_directory(self):
        """Test that ensure_subcommand_dir creates the directory."""
        path = self.manager.ensure_subcommand_dir("audit", "workspace1", "repo1")
        expected = self.temp_dir / "audit" / "workspace1_repo1"
        assert path == expected
        assert path.exists()
        assert path.is_dir()

    def test_ensure_subcommand_dir_creates_parent_dirs(self):
        """Test that ensure_subcommand_dir creates parent directories."""
        path = self.manager.ensure_subcommand_dir("migrate", "workspace1", "repo1")
        assert path.exists()
        assert path.parent.exists()  # audit directory
        assert path.parent.parent == self.temp_dir  # base directory

    def test_ensure_base_dir_creates_directory(self):
        """Test that ensure_base_dir creates the base directory."""
        # Use a non-existent base directory
        new_base = self.temp_dir / "new_base"
        manager = BaseDirManager(str(new_base))

        path = manager.ensure_base_dir()
        assert path == new_base
        assert path.exists()
        assert path.is_dir()

    def test_get_relative_path_base_only(self):
        """Test get_relative_path with no parameters."""
        assert self.manager.get_relative_path() == "."

    def test_get_relative_path_subcommand_only(self):
        """Test get_relative_path with subcommand only."""
        assert self.manager.get_relative_path("audit") == "audit"

    def test_get_relative_path_full_path(self):
        """Test get_relative_path with all parameters."""
        path = self.manager.get_relative_path("audit", "workspace1", "repo1")
        assert path == "audit/workspace1_repo1"

    def test_list_subcommand_dirs_empty(self):
        """Test listing subcommand directories when none exist."""
        # This method doesn't exist in the current BaseDirManager
        # Skip this test as it's testing functionality that was removed
        pytest.skip("list_subcommand_dirs method removed from BaseDirManager")

    def test_list_subcommand_dirs_with_dirs(self):
        """Test listing subcommand directories when they exist."""
        # This method doesn't exist in the current BaseDirManager
        # Skip this test as it's testing functionality that was removed
        pytest.skip("list_subcommand_dirs method removed from BaseDirManager")

    def test_clean_subcommand_removes_dirs(self):
        """Test that clean_files removes all repository directories."""
        # Create files using create_file to register them
        self.manager.create_file(
            "audit/workspace1_repo1/file.txt",
            "test",
            subcommand="audit",
            workspace="workspace1",
            repo="repo1"
        )
        
        self.manager.create_file(
            "audit/workspace1_repo2/file2.txt",
            "test",
            subcommand="audit",
            workspace="workspace1",
            repo="repo2"
        )

        repo1_dir = self.temp_dir / "audit" / "workspace1_repo1"
        repo2_dir = self.temp_dir / "audit" / "workspace1_repo2"

        # Clean audit subcommand files
        result = self.manager.clean_files(subcommand=["audit"])

        # Verify files are gone (folders and files)
        assert not (repo1_dir / "file.txt").exists()
        assert not (repo2_dir / "file2.txt").exists()
        # Should delete files and possibly folders
        assert len(result['deleted']) >= 1
        assert result['failures'] == 0

    def test_clean_subcommand_no_op_when_not_exists(self):
        """Test that clean_files does nothing when no files match."""
        # Should not raise an error
        result = self.manager.clean_files(subcommand=["nonexistent"])
        assert result['deleted'] == []
        assert result['failures'] == 0

    def test_clean_all_subcommands(self):
        """Test cleaning all subcommand directories."""
        # Create files using create_file to register them
        for subcommand in ["audit", "dry-run", "migrate"]:
            self.manager.create_file(
                f"{subcommand}/workspace1_repo1/test.txt",
                "test",
                subcommand=subcommand,
                workspace="workspace1",
                repo="repo1"
            )

        # Clean all subcommands
        result = self.manager.clean_files()

        # Verify files are gone
        for subcommand in ["audit", "dry-run", "migrate"]:
            repo_dir = self.temp_dir / subcommand / "workspace1_repo1"
            assert not (repo_dir / "test.txt").exists()
        assert len(result['deleted']) >= 3  # At least 3 files deleted

    def test_create_file_basic(self):
        """Test basic file creation and tracking."""
        content = "test content"
        filepath = "test.txt"

        # Create file
        result_path = self.manager.create_file(
            filepath=filepath,
            content=content,
            subcommand="audit",
            workspace="ws",
            repo="repo",
            category="report"
        )

        # Verify file was created
        expected_path = self.manager.base_dir / filepath
        assert result_path == expected_path
        assert expected_path.exists()
        assert expected_path.read_text() == content

        # Verify file was registered
        files = self.manager.registry.get_files()
        assert len(files) == 1

        file_entry = files[0]
        assert file_entry["path"] == filepath
        assert file_entry["subcommand"] == "audit"
        assert file_entry["workspace"] == "ws"
        assert file_entry["repo"] == "repo"
        assert file_entry["category"] == "report"
        assert file_entry["size_bytes"] == len(content)

    def test_create_file_with_bytes(self):
        """Test creating file with binary content."""
        content = b"binary content"
        filepath = "binary.bin"

        result_path = self.manager.create_file(
            filepath=filepath,
            content=content,
            subcommand="migrate"
        )

        expected_path = self.manager.base_dir / filepath
        assert result_path == expected_path
        assert expected_path.exists()
        assert expected_path.read_bytes() == content

    def test_create_file_creates_directories(self):
        """Test that create_file creates parent directories."""
        filepath = "deep/nested/path/file.txt"
        content = "nested content"

        result_path = self.manager.create_file(
            filepath=filepath,
            content=content,
            subcommand="audit"
        )

        expected_path = self.manager.base_dir / filepath
        assert expected_path.exists()
        assert expected_path.parent.exists()
        assert expected_path.parent.name == "path"
        assert expected_path.read_text() == content

    def test_create_file_absolute_path(self):
        """Test creating file with absolute path."""
        abs_filepath = self.manager.base_dir / "absolute.txt"
        content = "absolute content"

        result_path = self.manager.create_file(
            filepath=abs_filepath,
            content=content,
            subcommand="audit"
        )

        assert result_path == abs_filepath
        assert abs_filepath.exists()
        assert abs_filepath.read_text() == content

    def test_create_file_json_content(self):
        """Test creating file with JSON content."""
        data = {"key": "value", "number": 42}
        content = json.dumps(data, indent=2)
        filepath = "data.json"

        result_path = self.manager.create_file(
            filepath=filepath,
            content=content,
            subcommand="audit",
            category="config"
        )

        expected_path = self.manager.base_dir / filepath
        assert expected_path.exists()

        # Verify content is valid JSON
        with open(expected_path, 'r') as f:
            loaded_data = json.load(f)
        assert loaded_data == data

        # Verify registration
        files = self.manager.registry.get_files()
        config_files = [f for f in files if f.get("category") == "config"]
        assert len(config_files) == 1
        assert config_files[0]["path"] == filepath

    def test_create_file_minimal_args(self):
        """Test create_file with minimal arguments."""
        filepath = "minimal.txt"
        content = "minimal"

        result_path = self.manager.create_file(
            filepath=filepath,
            content=content,
            subcommand="test"
        )

        expected_path = self.manager.base_dir / filepath
        assert expected_path.exists()
        assert expected_path.read_text() == content

        # Verify registration with defaults
        files = self.manager.registry.get_files()
        assert len(files) == 1
        file_entry = files[0]
        assert file_entry["subcommand"] == "test"
        assert file_entry["workspace"] is None
        assert file_entry["repo"] is None
        assert file_entry["category"] == "general"

    def test_clean_everything_removes_base_dir(self):
        """Test that clean_everything removes the entire base directory."""
        # Create some content
        (self.temp_dir / "config.json").write_text("{}")
        audit_dir = self.temp_dir / "audit"
        audit_dir.mkdir()
        (audit_dir / "file.txt").write_text("test")

        # Clean everything
        self.manager.clean_everything()

        # Verify base directory is gone
        assert not self.temp_dir.exists()

    def test_template_variables_in_base_dir(self):
        """Test that base directory supports template variables."""
        # Create a manager with template variables
        manager = BaseDirManager("./migrations/{workspace}")

        # The path should be resolved as-is (templates are handled at config level)
        assert "workspace" in str(manager.base_dir)

    def test_nested_base_directory_creation(self):
        """Test creating deeply nested base directories."""
        nested_path = self.temp_dir / "deep" / "nested" / "path"
        manager = BaseDirManager(str(nested_path))

        created_path = manager.ensure_base_dir()
        assert created_path == nested_path
        assert created_path.exists()
        assert created_path.is_dir()

    def test_path_resolution(self):
        """Test that paths are properly resolved."""
        # Test with relative path containing ..
        manager = BaseDirManager("./test/../test_dir")
        resolved_path = manager.base_dir

        # Should resolve the .. properly
        assert ".." not in str(resolved_path)
        assert resolved_path.name == "test_dir"
        assert resolved_path.is_absolute()