"""
Secure configuration management for Bitbucket to GitHub migration.

This module enhances the configuration loading with security best practices,
including token validation and support for environment variables to avoid
storing sensitive data in configuration files.
"""

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from .migration_config import MigrationConfig, ConfigLoader, ConfigValidator, BitbucketConfig, GitHubConfig
from ..exceptions import ConfigurationError, ValidationError


class SecureConfigLoader(ConfigLoader):
    """
    Secure configuration loader with enhanced security features.

    Supports loading tokens from environment variables and validates token formats.
    Provides options for encrypted storage of sensitive data.
    """

    @staticmethod
    def load_from_file(config_path: str) -> MigrationConfig:
        """
        Load configuration from file with security enhancements.

        Args:
            config_path: Path to the configuration JSON file

        Returns:
            Validated MigrationConfig object

        Raises:
            ConfigurationError: If configuration file is invalid or missing required keys
            ValidationError: If configuration data is invalid
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except PermissionError:
            raise ConfigurationError(f"Permission denied reading configuration file: {config_path}")
        except UnicodeDecodeError as e:
            raise ConfigurationError(f"Configuration file encoding error: {e}")

        # Load tokens from environment variables if available
        data = SecureConfigLoader._load_tokens_from_env(data)

        # Validate tokens
        SecureConfigLoader._validate_tokens(data)

        # Detect format and load appropriately with our modified data
        if 'repositories' in data and isinstance(data['repositories'], list):
            # New unified format
            return ConfigLoader._load_unified_config(data)
        else:
            # Old per-repo format no longer supported - only v2.0 unified format
            raise ConfigurationError(
                "Unsupported config format. Only v2.0 unified format is supported. "
                "See docs/reference/migration_config.md for current format."
            )

    @staticmethod
    def _load_tokens_from_env(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load tokens from environment variables or .env file if not present in config.

        This allows users to store sensitive tokens in environment variables
        or a .env file instead of configuration files, improving security.

        Args:
            data: Configuration dictionary

        Returns:
            Updated configuration dictionary
        """
        # Load from .env file if it exists
        load_dotenv()

        # Bitbucket token
        if not data.get('bitbucket', {}).get('token'):
            bb_token = os.getenv('BITBUCKET_TOKEN') or os.getenv('BITBUCKET_API_TOKEN')
            if bb_token:
                data.setdefault('bitbucket', {})['token'] = bb_token

        # GitHub token
        if not data.get('github', {}).get('token'):
            gh_token = os.getenv('GITHUB_TOKEN') or os.getenv('GITHUB_API_TOKEN')
            if gh_token:
                data.setdefault('github', {})['token'] = gh_token

        return data

    @staticmethod
    def _validate_tokens(data: Dict[str, Any]) -> None:
        """
        Validate token formats and presence.

        Args:
            data: Configuration dictionary

        Raises:
            ValidationError: If tokens are invalid or missing
        """
        # Validate Bitbucket token
        bb_token = data.get('bitbucket', {}).get('token')
        if not bb_token:
            raise ValidationError("Bitbucket token is required. Set BITBUCKET_TOKEN or BITBUCKET_API_TOKEN in environment variables, .env file, or add to config file.")
        if not SecureConfigLoader._is_valid_bitbucket_token(bb_token):
            raise ValidationError("Invalid Bitbucket token format. Expected app password or API token.")

        # Validate GitHub token
        gh_token = data.get('github', {}).get('token')
        if not gh_token:
            raise ValidationError("GitHub token is required. Set GITHUB_TOKEN or GITHUB_API_TOKEN in environment variables, .env file, or add to config file.")
        if not SecureConfigLoader._is_valid_github_token(gh_token):
            raise ValidationError("Invalid GitHub token format. Expected personal access token (ghp_ or github_pat_).")

    @staticmethod
    def _is_valid_bitbucket_token(token: str) -> bool:
        """
        Validate Bitbucket API token format.

        Bitbucket API tokens start with "ATATT", contain alphanumeric characters,
        hyphens (-), underscores (_), and equals (=), and are machine-generated
        with variable length (typically 100+ characters).

        Args:
            token: The token to validate

        Returns:
            True if valid, False otherwise
        """
        import re

        # Check if starts with ATATT
        if not token.startswith('ATATT'):
            return False

        # Check length (minimum 50 characters based on examples)
        if len(token) < 50:
            return False

        # Check for allowed characters: alphanumeric, -, _, =
        if not re.match(r'^ATATT[A-Za-z0-9\-_]*=[A-Za-z0-9]+$', token):
            return False

        return True

    @staticmethod
    def _is_valid_github_token(token: str) -> bool:
        """
        Validate GitHub token format.

        GitHub personal access tokens start with 'ghp_' or 'github_pat_'.

        Args:
            token: The token to validate

        Returns:
            True if valid, False otherwise
        """
        return token.startswith('ghp_') or token.startswith('github_pat_')




def load_config_secure(config_path: str) -> MigrationConfig:
    """
    Convenience function to load configuration securely.

    Args:
        config_path: Path to configuration file

    Returns:
        MigrationConfig object
    """
    return SecureConfigLoader.load_from_file(config_path)