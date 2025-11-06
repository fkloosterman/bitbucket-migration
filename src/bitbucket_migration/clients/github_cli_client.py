"""
GitHub CLI client for the migration tool.

This module provides a focused, reusable client for interacting with
the GitHub CLI tool, encapsulating all CLI-specific logic,
authentication, and error handling.
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from ..exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    ValidationError
)


class GitHubCliClient:
    """
    Client for interacting with the GitHub CLI tool.

    This class handles all GitHub CLI operations including availability checks,
    authentication, and attachment uploads. It provides a clean interface for
    CLI-based operations during migration.

    Attributes:
        token (str): GitHub personal access token for authentication
        dry_run (bool): Whether to simulate CLI calls without making changes
        logger (logging.Logger): Logger instance for this client
    """

    def __init__(self, token: str, dry_run: bool = False) -> None:
        """
        Initialize the GitHub CLI client.

        Args:
            token: GitHub personal access token
            dry_run: Whether to simulate CLI calls without making changes

        Raises:
            ValidationError: If token is empty
        """
        if not token or not token.strip():
            raise ValidationError("GitHub token cannot be empty")

        self.token = token
        self.dry_run = dry_run
        self.logger = logging.getLogger('bitbucket_migration')

    def is_available(self) -> bool:
        """
        Check if GitHub CLI is installed and available.

        Returns:
            True if CLI is available, False otherwise

        Raises:
            APIError: If there's an unexpected error checking availability
        """
        if self.dry_run:
            return True  # Assume available in dry run

        try:
            result = subprocess.run(['gh', '--version'],
                                  capture_output=True,
                                  text=True,
                                  timeout=5)
            return result.returncode == 0
        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            raise APIError(f"Error checking GitHub CLI availability: {e}")

    def is_authenticated(self) -> bool:
        """
        Check if GitHub CLI is authenticated.

        Returns:
            True if authenticated, False otherwise

        Raises:
            APIError: If there's an unexpected error checking authentication
        """
        if self.dry_run:
            return True  # Assume authenticated in dry run

        try:
            result = subprocess.run(['gh', 'auth', 'status'],
                                  capture_output=True,
                                  text=True,
                                  timeout=5)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            raise APIError(f"Error checking GitHub CLI authentication: {e}")

    def authenticate(self, token: Optional[str] = None) -> bool:
        """
        Authenticate GitHub CLI using the provided token.

        Args:
            token: Token to use for authentication (uses self.token if None)

        Returns:
            True if authentication successful, False otherwise

        Raises:
            ValidationError: If token is empty
            APIError: If there's an unexpected error during authentication
        """
        # Validate custom token if provided
        if token is not None and (not token or not token.strip()):
            raise ValidationError("GitHub token cannot be empty")
        
        auth_token = token or self.token
        if not auth_token or not auth_token.strip():
            raise ValidationError("GitHub token cannot be empty")

        if self.dry_run:
            return True  # Simulate success in dry run

        try:
            result = subprocess.run([
                'gh', 'auth', 'login',
                '--with-token'
            ], input=auth_token, text=True, capture_output=True, timeout=10)

            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            raise APIError(f"Error authenticating GitHub CLI: {e}")

    def upload_attachment(self, filepath: Path, issue_number: int, owner: str, repo: str) -> Optional[str]:
        """
        Upload an attachment to a GitHub issue using CLI.

        Args:
            filepath: Path to the file to upload
            issue_number: GitHub issue number
            owner: Repository owner
            repo: Repository name

        Returns:
            Success message if uploaded, None if failed

        Raises:
            ValidationError: If parameters are invalid
            APIError: If there's an unexpected error during upload
        """
        self.logger.debug(f"upload_attachment called with filepath={filepath}, exists={filepath.exists() if filepath else 'None'}, dry_run={self.dry_run}")
        if not filepath:
            raise ValidationError("Attachment filepath must exist")
        if not self.dry_run and not filepath.exists():
            raise ValidationError("Attachment filepath must exist")
        if not isinstance(issue_number, int) or issue_number <= 0:
            raise ValidationError("Issue number must be a positive integer")
        if not owner or not owner.strip():
            raise ValidationError("Repository owner cannot be empty")
        if not repo or not repo.strip():
            raise ValidationError("Repository name cannot be empty")

        if self.dry_run:
            return "Simulated upload via gh CLI"

        try:
            file_size = filepath.stat().st_size
            size_mb = file_size / (1024 * 1024)

            # Create a comment with the attached file
            result = subprocess.run([
                'gh', 'issue', 'comment', str(issue_number),
                '--repo', f'{owner}/{repo}',
                '--body', f'📎 **Attachment from Bitbucket**: `{filepath.name}` ({size_mb:.2f} MB)',
                '--attach', str(filepath)
            ], capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                return "Uploaded via gh CLI"
            else:
                self.logger.error(f"ERROR uploading via CLI: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            self.logger.error(f"ERROR: gh CLI command timed out for {filepath.name}")
            return None
        except Exception as e:
            raise APIError(f"Error uploading attachment via GitHub CLI: {e}")

    def get_version(self) -> Optional[str]:
        """
        Get the GitHub CLI version.

        Returns:
            Version string if available, None otherwise

        Raises:
            APIError: If there's an unexpected error getting version
        """
        if self.dry_run:
            return "2.40.0"  # Simulated version

        try:
            result = subprocess.run(['gh', '--version'],
                                  capture_output=True,
                                  text=True,
                                  timeout=5)
            if result.returncode == 0:
                output = result.stdout.strip()
                parts = output.split()
                
                # Try to extract version from different formats
                # Format 1: "gh version 2.25.0 (2023-01-15)"
                # Format 2: "2.40.0"
                if len(parts) >= 3 and parts[0] == 'gh' and parts[1] == 'version':
                    return parts[2]
                elif len(parts) == 1 and '.' in parts[0]:
                    # Single version number (must contain dot to be valid version)
                    return parts[0]
                else:
                    return 'unknown'
            return None
        except Exception as e:
            raise APIError(f"Error getting GitHub CLI version: {e}")