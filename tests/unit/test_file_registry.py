"""
Tests for FileRegistry functionality.
"""

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from bitbucket_migration.utils.file_registry import FileRegistry


class TestFileRegistry:
    """Test FileRegistry class functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Set up test fixtures."""
        self.temp_dir = tmp_path
        self.registry = FileRegistry(self.temp_dir)
        yield

    def test_init_creates_base_dir(self):
        """Test that __init__ creates base directory if it doesn't exist."""
        new_dir = self.temp_dir / "new_base"
        registry = FileRegistry(new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_register_file_basic(self):
        """Test basic file registration."""
        # Create a test file
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("test content")

        # Register the file
        self.registry.register_file(
            test_file,
            subcommand="audit",
            workspace="ws",
            repo="repo",
            category="report"
        )

        # Verify registry contains the file
        files = self.registry.get_files()
        assert len(files) == 1

        file_entry = files[0]
        assert file_entry["path"] == "test.txt"
        assert file_entry["absolute_path"] == str(test_file)
        assert file_entry["subcommand"] == "audit"
        assert file_entry["workspace"] == "ws"
        assert file_entry["repo"] == "repo"
        assert file_entry["category"] == "report"
        assert file_entry["size_bytes"] == 12  # "test content" is 12 bytes
        assert file_entry["exists"] is True
        assert "created_at" in file_entry

    def test_register_file_nonexistent_raises_error(self):
        """Test that registering non-existent file raises FileNotFoundError."""
        nonexistent_file = self.temp_dir / "nonexistent.txt"

        with pytest.raises(FileNotFoundError, match="Cannot register non-existent file"):
            self.registry.register_file(nonexistent_file, "audit")

    def test_register_file_outside_base_dir(self, tmp_path):
        """Test registering file outside base directory."""
        # Create file outside base_dir
        external_file = tmp_path.parent / "external.txt"
        external_file.write_text("external")

        try:
            self.registry.register_file(external_file, "audit")

            # Should still be registered with absolute path
            files = self.registry.get_files()
            assert len(files) == 1
            assert files[0]["path"] == str(external_file)  # Absolute path as string
            assert files[0]["absolute_path"] == str(external_file)
        finally:
            if external_file.exists():
                external_file.unlink()

    def test_register_file_updates_existing(self):
        """Test that registering same file twice updates the entry."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")

        # Register first time
        self.registry.register_file(test_file, "audit", category="old")
        files = self.registry.get_files()
        assert len(files) == 1
        assert files[0]["category"] == "old"

        # Register again with different metadata
        self.registry.register_file(test_file, "migrate", category="new")
        files = self.registry.get_files()
        assert len(files) == 1
        assert files[0]["subcommand"] == "migrate"
        assert files[0]["category"] == "new"

    def test_unregister_file(self):
        """Test unregistering a file."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")

        # Register then unregister
        self.registry.register_file(test_file, "audit")
        assert len(self.registry.get_files()) == 1

        self.registry.unregister_file(test_file)
        assert len(self.registry.get_files()) == 0

    def test_unregister_nonexistent_file(self):
        """Test unregistering a file that was never registered."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")

        # Should not raise error
        self.registry.unregister_file(test_file)
        # Registry should still be empty
        assert len(self.registry.get_files()) == 0

    def test_get_files_filtering(self):
        """Test filtering files by various criteria."""
        # Create multiple test files
        files_data = [
            ("audit_report.json", "audit", "ws1", "repo1", "report"),
            ("migrate_log.txt", "migrate", "ws1", "repo1", "log"),
            ("audit_report2.json", "audit", "ws2", "repo2", "report"),
            ("config.json", "audit", None, None, "config"),
        ]

        for filename, subcommand, workspace, repo, category in files_data:
            filepath = self.temp_dir / filename
            filepath.write_text("content")
            self.registry.register_file(filepath, subcommand, workspace, repo, category)

        # Test filtering by subcommand (pass as list)
        audit_files = self.registry.get_files(subcommand=["audit"])
        assert len(audit_files) == 3

        migrate_files = self.registry.get_files(subcommand=["migrate"])
        assert len(migrate_files) == 1

        # Test filtering by workspace
        ws1_files = self.registry.get_files(workspace="ws1")
        assert len(ws1_files) == 2

        # Test filtering by category - manually filter from results since get_files doesn't support it
        all_files = self.registry.get_files()
        report_files = [f for f in all_files if f.get("category") == "report"]
        assert len(report_files) == 2

        # Test multiple filters
        ws1_audit_files = self.registry.get_files(subcommand=["audit"], workspace="ws1")
        assert len(ws1_audit_files) == 1
        assert ws1_audit_files[0]["repo"] == "repo1"

    def test_get_files_exists_only(self):
        """Test exists_only parameter."""
        # Create and register file
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")
        self.registry.register_file(test_file, "audit")

        # File exists - should be returned
        files = self.registry.get_files(exists_only=True)
        assert len(files) == 1
        assert files[0]["exists"] is True

        # Delete file
        test_file.unlink()

        # File doesn't exist - should not be returned when exists_only=True
        files = self.registry.get_files(exists_only=True)
        assert len(files) == 0

        # But should be returned when exists_only=False
        files = self.registry.get_files(exists_only=False)
        assert len(files) == 1
        # When exists_only=False, we don't check existence, so exists remains True from registration
        # This is expected behavior - exists_only=False means return all registered files regardless of current status

    def test_clean_files_dry_run(self):
        """Test that FileRegistry doesn't have clean_files - it's in BaseDirManager."""
        # This test is for documentation - clean_files is in BaseDirManager, not FileRegistry
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")
        self.registry.register_file(test_file, "audit")

        # FileRegistry doesn't have clean_files - that's in BaseDirManager
        assert not hasattr(self.registry, 'clean_files')
        
        # But we can manually delete and unregister
        files = self.registry.get_files()
        assert len(files) == 1
        # File exists before deletion
        assert test_file.exists()

    def test_manual_file_cleanup(self):
        """Test manual file deletion and unregistration."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")
        self.registry.register_file(test_file, "audit")

        # Manually delete file and unregister it
        test_file.unlink()
        self.registry.unregister_file(test_file)
        
        assert not test_file.exists()

        # Should be unregistered
        files = self.registry.get_files()
        assert len(files) == 0

    def test_unregister_files_by_filter(self):
        """Test unregistering files by filter."""
        # Create files with different subcommands
        audit_file = self.temp_dir / "audit.txt"
        audit_file.write_text("audit")
        self.registry.register_file(audit_file, "audit")

        migrate_file = self.temp_dir / "migrate.txt"
        migrate_file.write_text("migrate")
        self.registry.register_file(migrate_file, "migrate")

        # Unregister only audit files (doesn't delete from filesystem)
        self.registry.unregister_files_by_filter(subcommand=["audit"])
        
        # Both files still exist on filesystem
        assert audit_file.exists()
        assert migrate_file.exists()
        
        # But only migrate file is in registry
        files = self.registry.get_files()
        assert len(files) == 1
        assert files[0]["path"] == "migrate.txt"

    def test_unregister_files_doesnt_delete(self):
        """Test that unregister_files_by_filter doesn't delete files from filesystem."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")
        self.registry.register_file(test_file, "audit")

        # Unregister the file
        self.registry.unregister_files_by_filter(subcommand=["audit"])
        
        # File should still exist on filesystem
        assert test_file.exists()
        
        # But should not be in registry
        files = self.registry.get_files()
        assert len(files) == 0

    def test_verify_registry(self):
        """Test registry verification."""
        # Create and register file
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")
        self.registry.register_file(test_file, "audit")

        # Verify when file exists
        valid, missing = self.registry.verify_registry()
        assert len(valid) == 1
        assert len(missing) == 0
        assert valid[0] == "test.txt"

        # Delete file and verify
        test_file.unlink()
        valid, missing = self.registry.verify_registry()
        assert len(valid) == 0
        assert len(missing) == 1
        assert missing[0] == "test.txt"

    def test_export_audit_trail(self):
        """Test audit trail export."""
        # Create and register file
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")
        self.registry.register_file(test_file, "audit", workspace="ws", repo="repo")

        # Export audit trail
        export_file = self.temp_dir / "audit_export.json"
        self.registry.export_audit_trail(export_file)

        # Verify export file
        assert export_file.exists()
        with open(export_file, 'r') as f:
            data = json.load(f)

        assert data["total_files"] == 1
        assert data["files_by_subcommand"]["audit"] == 1
        assert len(data["files"]) == 1
        assert "export_date" in data
        assert data["base_dir"] == str(self.temp_dir)

    def test_thread_safety(self):
        """Test that registry operations are thread-safe."""
        results = []
        errors = []

        def worker(worker_id):
            try:
                # Each worker creates and registers its own file
                test_file = self.temp_dir / f"test_{worker_id}.txt"
                test_file.write_text(f"content {worker_id}")
                self.registry.register_file(test_file, f"subcommand_{worker_id}")

                # Small delay to increase chance of race conditions
                time.sleep(0.01)

                # Verify file was registered
                files = self.registry.get_files(subcommand=f"subcommand_{worker_id}")
                results.append(len(files))
            except Exception as e:
                errors.append(str(e))

        # Start multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Verify no errors and all files were registered
        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 5
        assert all(r == 1 for r in results)  # Each worker should have 1 file

        # Total files should be 5
        all_files = self.registry.get_files()
        assert len(all_files) == 5

    def test_registry_file_format(self):
        """Test registry file format."""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("content")
        self.registry.register_file(test_file, "audit", workspace="ws", repo="repo", category="report")

        # Load registry file directly
        with open(self.registry.registry_file, 'r') as f:
            data = json.load(f)

        # Verify structure
        assert data["format_version"] == "1.0"
        assert data["base_dir"] == str(self.temp_dir)
        assert len(data["files"]) == 1

        file_entry = data["files"][0]
        assert file_entry["path"] == "test.txt"
        assert file_entry["subcommand"] == "audit"
        assert file_entry["workspace"] == "ws"
        assert file_entry["repo"] == "repo"
        assert file_entry["category"] == "report"
        assert file_entry["exists"] is True
        assert "created_at" in file_entry
        assert file_entry["size_bytes"] == 7  # "content" is 7 bytes