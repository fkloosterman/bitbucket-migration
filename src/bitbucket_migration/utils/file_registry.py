"""
File Registry for tracking created files during migration operations.

This module provides centralized file tracking with metadata for selective
cleanup and audit trail capabilities.
"""

import json
import fcntl
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import os


class FileRegistry:
    """
    Centralized registry for tracking created files.

    Thread-safe file tracking using file locking for concurrent migrations.
    Stores metadata in JSON format for queryability.

    Example:
        >>> registry = FileRegistry(Path("/project"))
        >>> registry.register_file(
        ...     Path("/project/audit/ws_repo/report.json"),
        ...     subcommand="audit",
        ...     workspace="ws",
        ...     repo="repo",
        ...     category="report"
        ... )
        >>> files = registry.get_files(subcommand="audit")
        >>> len(files)
        1
    """

    FORMAT_VERSION = "1.0"

    def __init__(self, base_dir: Path):
        """
        Initialize file registry.

        Args:
            base_dir: Base directory for migration operations
        """
        self.base_dir = Path(base_dir).resolve()
        self.registry_file = self.base_dir / "_file_registry.json"
        self._lock_file = self.base_dir / "_file_registry.lock"

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _acquire_lock(self) -> int:
        """
        Acquire exclusive lock for registry file access.

        Returns:
            File descriptor for lock file
        """
        lock_fd = os.open(str(self._lock_file), os.O_CREAT | os.O_WRONLY)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        return lock_fd

    def _release_lock(self, lock_fd: int) -> None:
        """Release lock and close file descriptor."""
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)

    def _load_registry(self) -> Dict[str, Any]:
        """
        Load registry from disk.

        Returns:
            Registry data dictionary
        """
        if not self.registry_file.exists():
            return {
                "format_version": self.FORMAT_VERSION,
                "base_dir": str(self.base_dir),
                "files": []
            }

        with open(self.registry_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_registry(self, data: Dict[str, Any]) -> None:
        """
        Save registry to disk.

        Args:
            data: Registry data dictionary
        """
        with open(self.registry_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def register_file(
        self,
        filepath: Path,
        subcommand: str,
        workspace: Optional[str] = None,
        repo: Optional[str] = None,
        category: Optional[str] = None
    ) -> None:
        """
        Register a created file with metadata.

        Args:
            filepath: Absolute or relative path to file
            subcommand: The subcommand that created the file
            workspace: Optional workspace name
            repo: Optional repository name
            category: Optional category (report, log, config, attachment, etc.)

        Raises:
            FileNotFoundError: If filepath does not exist
        """
        filepath = Path(filepath).resolve()

        if not filepath.exists():
            raise FileNotFoundError(f"Cannot register non-existent file: {filepath}")

        # Calculate relative path
        try:
            relative_path = filepath.relative_to(self.base_dir)
        except ValueError:
            # File is outside base_dir
            relative_path = filepath

        # Get file stats
        stats = filepath.stat()

        file_entry = {
            "path": str(relative_path),
            "absolute_path": str(filepath),
            "subcommand": subcommand,
            "workspace": workspace,
            "repo": repo,
            "category": category,
            "created_at": datetime.now().isoformat() + "Z",
            "size_bytes": stats.st_size,
            "exists": True
        }

        # Thread-safe registry update
        lock_fd = self._acquire_lock()
        try:
            data = self._load_registry()

            # Remove existing entry for this path (if any)
            data["files"] = [
                f for f in data["files"]
                if f["absolute_path"] != str(filepath)
            ]

            # Add new entry
            data["files"].append(file_entry)

            self._save_registry(data)
        finally:
            self._release_lock(lock_fd)

    def unregister_file(self, filepath: Path) -> None:
        """
        Remove a file from the registry.

        Args:
            filepath: Path to file to unregister
        """
        filepath = Path(filepath).resolve()

        lock_fd = self._acquire_lock()
        try:
            data = self._load_registry()

            # Remove entries matching this path
            original_count = len(data["files"])
            data["files"] = [
                f for f in data["files"]
                if f["absolute_path"] != str(filepath)
            ]

            if len(data["files"]) < original_count:
                self._save_registry(data)
        finally:
            self._release_lock(lock_fd)

    def unregister_files_by_filter(self, **filters) -> None:
        """
        Remove files from registry matching criteria (no filesystem operations).
        
        Args:
            **filters: Same filters as get_files() (subcommand, workspace, repo, category)
        """
        files_to_deregister = self.get_files(**filters, exists_only=False)
        for file_entry in files_to_deregister:
            self.unregister_file(Path(file_entry["absolute_path"]))

    def get_folders_and_files(
        self,
        subcommand: Optional[List] = None,
        workspace: Optional[str] = None,
        repo: Optional[List] = None,
        exists_only: bool = True
    ) -> Tuple[List[Path], List[Dict[str, Any]]]:

        files = self.get_files(
            subcommand=subcommand,
            workspace=workspace,
            repo=repo,
            exists_only=exists_only
        )

        if workspace or repo:
            folders = list({Path(f.get('path')).parent for f in files if f.get('workspace') and f.get('repo')})
        else:
            folders = list({self.base_dir / f.get('subcommand') for f in files})

        return folders, files

    def get_files(
        self,
        subcommand: Optional[List] = None,
        workspace: Optional[str] = None,
        repo: Optional[List] = None,
        exists_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Query registered files by criteria.

        Args:
            subcommand: Filter by subcommand
            workspace: Filter by workspace
            repo: Filter by repository
            exists_only: Only return files that currently exist

        Returns:
            List of file metadata dictionaries
        """
        lock_fd = self._acquire_lock()
        try:
            data = self._load_registry()
            files = data["files"]

            # Apply filters
            if subcommand:
                files = [f for f in files if f.get("subcommand") in subcommand]
            
            if workspace:
                if isinstance(workspace, list):
                    files = [f for f in files if f.get("workspace") in workspace]
                else:
                    files = [f for f in files if f.get("workspace") == workspace]
            
            if repo:
                if isinstance(repo, list):
                    files = [f for f in files if f.get("repo") in repo]
                else:
                    files = [f for f in files if f.get("repo") == repo]

            # Check existence
            if exists_only:
                files = [f for f in files if Path(f["absolute_path"]).exists()]
                # Update exists flag for returned files
                for file_entry in files:
                    file_entry["exists"] = True

            return files
        finally:
            self._release_lock(lock_fd)


    def verify_registry(self) -> Tuple[List[str], List[str]]:
        """
        Verify registry consistency.

        Checks that all registered files exist and updates registry.

        Returns:
            Tuple of (valid_files, missing_files)
        """
        lock_fd = self._acquire_lock()
        try:
            data = self._load_registry()

            valid_files = []
            missing_files = []

            for file_entry in data["files"]:
                filepath = Path(file_entry["absolute_path"])
                if filepath.exists():
                    valid_files.append(file_entry["path"])
                    file_entry["exists"] = True
                else:
                    missing_files.append(file_entry["path"])
                    file_entry["exists"] = False

            self._save_registry(data)

            return valid_files, missing_files
        finally:
            self._release_lock(lock_fd)

    def export_audit_trail(self, output_file: Path) -> None:
        """
        Export audit trail to a separate file.

        Args:
            output_file: Path to export file
        """
        lock_fd = self._acquire_lock()
        try:
            data = self._load_registry()

            # Create human-readable audit trail
            audit_data = {
                "export_date": datetime.now().isoformat() + "Z",
                "base_dir": data["base_dir"],
                "total_files": len(data["files"]),
                "files_by_subcommand": {},
                "files": data["files"]
            }

            # Group by subcommand
            for file_entry in data["files"]:
                subcommand = file_entry.get("subcommand", "unknown")
                if subcommand not in audit_data["files_by_subcommand"]:
                    audit_data["files_by_subcommand"][subcommand] = 0
                audit_data["files_by_subcommand"][subcommand] += 1

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(audit_data, f, indent=2, ensure_ascii=False)
        finally:
            self._release_lock(lock_fd)