"""
Base Directory Management for Migration Operations.

This module provides utilities for managing the base directory structure
used in unified configuration format (v2.0). It handles the creation and
resolution of subcommand-specific directories within a base directory.
"""

import shutil
from pathlib import Path
from typing import Optional, Union, Any, List, Dict
import json
from .file_registry import FileRegistry


class BaseDirManager:
    """
    Manages base directory structure for migrations.

    Provides utilities for:
    - Creating subcommand-specific directories (audit/, dry-run/, migrate/)
    - Resolving paths within the base directory structure
    - Ensuring directory existence
    - Tracking created files
    """

    def __init__(self, base_dir: str = "."):
        """
        Initialize base directory manager.

        Args:
            base_dir: Base directory path (relative or absolute)
        """
        self.base_dir = Path(base_dir).resolve()
        self.registry = FileRegistry(self.base_dir)

    def get_subcommand_dir(self, subcommand: str, workspace: str, repo: str) -> Path:
        """
        Get output directory for a specific subcommand and repository.

        Args:
            subcommand: Subcommand name ('audit', 'dry-run', or 'migrate')
            workspace: Bitbucket workspace name
            repo: Repository name

        Returns:
            Path to the subcommand-specific directory for this repo

        Example:
            get_subcommand_dir('audit', 'myworkspace', 'repo1')
            -> Path('./myproject/audit/myworkspace_repo1')
        """
        return self.base_dir / subcommand / f"{workspace}_{repo}"

    def get_config_path(self, filename: Optional[str] = None) -> Path:
        """
        Get path to the configuration file.

        Returns:
            Path to config.json in the base directory
        """

        filename = filename or "config.json"

        return self.base_dir / filename

    def get_mappings_path(self, dry_run: bool = False) -> Path:
        """
        Get path to the cross-repository mappings file.

        Args:
            dry_run: If True, return dry-run specific mappings file path.
                    If False, return the main mappings file path.

        Returns:
            Path to cross_repo_mappings.json (or cross_repo_mappings_dry_run.json if dry_run=True)
        """
        if dry_run:
            return self.base_dir / "cross_repo_mappings_dry_run.json"
        else:
            return self.base_dir / "cross_repo_mappings.json"

    def ensure_subcommand_dir(self, subcommand: str, workspace: str, repo: str) -> Path:
        """
        Create and return the subcommand directory for a repository.

        Args:
            subcommand: Subcommand name ('audit', 'dry-run', or 'migrate')
            workspace: Bitbucket workspace name
            repo: Repository name

        Returns:
            Path to the created directory

        Raises:
            OSError: If directory creation fails
        """
        dir_path = self.get_subcommand_dir(subcommand, workspace, repo)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def ensure_base_dir(self) -> Path:
        """
        Ensure the base directory exists.

        Returns:
            Path to the base directory
        """
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def get_relative_path(self, subcommand: Optional[str] = None,
                         workspace: Optional[str] = None,
                         repo: Optional[str] = None) -> str:
        """
        Get relative path string for a subcommand directory.

        Args:
            subcommand: Optional subcommand name
            workspace: Optional workspace name
            repo: Optional repository name

        Returns:
            Relative path string from base directory
        """
        if not subcommand:
            return "."

        if not workspace or not repo:
            return subcommand

        return f"{subcommand}/{workspace}_{repo}"


    def create_file(
        self,
        filepath: Union[str, Path],
        content: Union[str, bytes, dict, list],
        subcommand: str,
        workspace: Optional[str] = None,
        repo: Optional[str] = None,
        category: str = "general"
    ) -> Path:
        """
        Create a file and register it in the tracking system.

        Args:
            filepath: Absolute or relative path to file
            content: File content (str for text, bytes for binary, dict/list for JSON)
            subcommand: The subcommand creating the file
            workspace: Optional workspace name
            repo: Optional repository name
            category: File category for filtering

        Returns:
            Absolute path to created file

        Example:
            >>> manager = BaseDirManager("./project")
            >>> # JSON content (dict/list) - automatically serialized
            >>> path = manager.create_file(
            ...     "audit/ws_repo/report.json",
            ...     {"data": "value"},
            ...     subcommand="audit",
            ...     workspace="ws",
            ...     repo="repo",
            ...     category="report"
            ... )
            >>> # String content
            >>> path = manager.create_file(
            ...     "audit/ws_repo/report.md",
            ...     "# Report\\nContent here",
            ...     subcommand="audit",
            ...     workspace="ws",
            ...     repo="repo",
            ...     category="report"
            ... )
        """
        filepath = Path(filepath)

        # Resolve path relative to base_dir if needed
        if not filepath.is_absolute():
            filepath = self.base_dir / filepath

        # Create parent directories
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Handle different content types
        if isinstance(content, bytes):
            # Binary content
            mode = 'wb'
            encoding = None
            write_content = content
        elif isinstance(content, (dict, list)):
            # JSON content - serialize it
            mode = 'w'
            encoding = 'utf-8'
            write_content = json.dumps(content, indent=2, ensure_ascii=False, default=str)
        else:
            # String content
            mode = 'w'
            encoding = 'utf-8'
            write_content = content

        # Write content
        with open(filepath, mode, encoding=encoding) as f:
            f.write(write_content)

        # Track file
        self.registry.register_file(
            filepath, subcommand, workspace, repo, category
        )

        return filepath

    def register_log_file(
        self,
        log_file_path: Union[str, Path],
        subcommand: str,
        workspace: Optional[str] = None,
        repo: Optional[str] = None
    ) -> None:
        """
        Register an existing log file in the file tracking system.
        
        This method is used to track log files that were created by MigrationLogger
        directly (without using create_file()) so they can be included in cleanup
        operations.
        
        Args:
            log_file_path: Path to the log file (absolute or relative to base_dir)
            subcommand: The subcommand that created the log file ('audit', 'dry-run', 'migrate')
            workspace: Optional workspace name
            repo: Optional repository name
        
        Example:
            >>> manager = BaseDirManager("./project")
            >>> log_file = manager.base_dir / "migration_log.txt"
            >>> logger = MigrationLogger(log_file=str(log_file))
            >>> manager.register_log_file(log_file, subcommand="migrate", workspace="ws", repo="repo")
        """
        log_file_path = Path(log_file_path)
        
        # Resolve path relative to base_dir if needed
        if not log_file_path.is_absolute():
            log_file_path = self.base_dir / log_file_path
               
        # Register the log file with category='log'
        self.registry.register_file(
            log_file_path,
            subcommand=subcommand,
            workspace=workspace,
            repo=repo,
            category='log'
        )

    def get_folders_and_files(self, **filters) -> List[Dict[str, Any]]:
        """
        Get files matching filters by delegating to registry.
        
        Args:
            **filters: Filters to apply (subcommand, workspace, repo, exists_only)
            
        Returns:
            List of file metadata dictionaries
        """
        return self.registry.get_folders_and_files(**filters)

    def clean_files(self, dry_run: bool = False, **filters):

        folders, files = self.get_folders_and_files(**filters)

        deleted = []
        failed = []
        errors = []

        for f in folders:
            if f.exists():
                try:
                    if not dry_run:
                        shutil.rmtree(f)
                    deleted.append(str(f))
                except Exception as e:
                    failed.append(str(f))
                    errors.append({'path': str(f), 'error': str(e)})

        for f in files:
            file_path = Path(f["absolute_path"])
            if file_path.exists():
                try:
                    if not dry_run:
                        file_path.unlink()
                    deleted.append(str(file_path))
                except Exception as e:
                    failed.append(str(file_path))
                    errors.append({'path': str(file_path), 'error': str(e)})

        if not dry_run:
            self.registry.unregister_files_by_filter(**filters)

        return {
            'deleted': deleted,
            'failures': len(failed),
            'errors': errors
        }

    def clean_everything(self) -> None:
        """
        Remove the entire base directory and all contents.
        """
        import shutil

        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)