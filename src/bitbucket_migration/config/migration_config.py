"""
Type-safe configuration management for Bitbucket to GitHub migration.

This module provides structured configuration classes and validation
to ensure all required settings are present and properly formatted.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from pathlib import Path

from ..exceptions import ConfigurationError, ValidationError


@dataclass
class BitbucketConfig:
    """
    Configuration for Bitbucket API access.

    Attributes:
        workspace: Bitbucket workspace name
        repo: Bitbucket repository name
        email: User email for API authentication
        token: Bitbucket API token
    """
    workspace: str
    repo: str
    email: str
    token: str

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.workspace or not self.workspace.strip():
            raise ValidationError("Bitbucket workspace cannot be empty")
        if not self.repo or not self.repo.strip():
            raise ValidationError("Bitbucket repository cannot be empty")
        if not self.email or not self.email.strip():
            raise ValidationError("Bitbucket email cannot be empty")
        if not self.token or not self.token.strip():
            raise ValidationError("Bitbucket token cannot be empty")


@dataclass
class GitHubConfig:
    """
    Configuration for GitHub API access.

    Attributes:
        owner: GitHub repository owner (user or organization)
        repo: GitHub repository name
        token: GitHub personal access token
    """
    owner: str
    repo: str
    token: str

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.owner or not self.owner.strip():
            raise ValidationError("GitHub owner cannot be empty")
        if not self.repo or not self.repo.strip():
            raise ValidationError("GitHub repository cannot be empty")
        if not self.token or not self.token.strip():
            raise ValidationError("GitHub token cannot be empty")


@dataclass
class MigrationConfig:
    """
    Complete migration configuration.

    Attributes:
        bitbucket: Bitbucket API configuration
        github: GitHub API configuration
        user_mapping: Mapping of Bitbucket users to GitHub users
        repository_mapping: Cross-repository link mappings
        dry_run: Whether to simulate migration without making changes
        skip_issues: Whether to skip issue migration
        skip_prs: Whether to skip PR migration
        skip_pr_as_issue: Whether to skip migrating closed PRs as issues
        use_gh_cli: Whether to use GitHub CLI for attachment uploads
    """
    bitbucket: BitbucketConfig
    github: GitHubConfig
    user_mapping: Dict[str, Any]
    repository_mapping: Optional[Dict[str, str]] = field(default_factory=dict)
    dry_run: bool = field(default=False)
    skip_issues: bool = field(default=False)
    skip_prs: bool = field(default=False)
    skip_pr_as_issue: bool = field(default=False)
    use_gh_cli: bool = field(default=False)

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.user_mapping:
            raise ValidationError("User mapping cannot be empty")

        # Validate repository mapping format if provided
        if self.repository_mapping:
            for key, value in self.repository_mapping.items():
                if not key or not value:
                    raise ValidationError(f"Invalid repository mapping: '{key}' -> '{value}'")


class ConfigValidator:
    """
    Validates configuration data before creating config objects.
    """

    @staticmethod
    def validate_bitbucket_data(data: Dict[str, Any]) -> None:
        """Validate Bitbucket configuration data."""
        required_fields = ['workspace', 'repo', 'email', 'token']
        for field in required_fields:
            if field not in data:
                raise ConfigurationError(f"Missing required Bitbucket field: '{field}'")
            if not data[field] or not str(data[field]).strip():
                raise ValidationError(f"Bitbucket field '{field}' cannot be empty")

    @staticmethod
    def validate_github_data(data: Dict[str, Any]) -> None:
        """Validate GitHub configuration data."""
        required_fields = ['owner', 'repo', 'token']
        for field in required_fields:
            if field not in data:
                raise ConfigurationError(f"Missing required GitHub field: '{field}'")
            if not data[field] or not str(data[field]).strip():
                raise ValidationError(f"GitHub field '{field}' cannot be empty")

    @staticmethod
    def validate_user_mapping(data: Dict[str, Any]) -> None:
        """Validate user mapping data."""
        if not data:
            raise ValidationError("User mapping cannot be empty")

        # Validate each mapping entry
        for key, value in data.items():
            if not key or not str(key).strip():
                raise ValidationError(f"Invalid user mapping key: '{key}'")

            # Handle different mapping formats
            if value is None:
                # null value means user has no GitHub account - this is valid
                continue
            elif isinstance(value, str):
                # Simple format: "Display Name": "github-username"
                # Empty string means user has no GitHub account - this is valid
                if value.strip() == "":
                    # This is valid - user has no GitHub account
                    pass
            elif isinstance(value, dict):
                # Enhanced format: "Display Name": {"github": "username", "bitbucket_username": "bbuser"}
                if 'github' not in value:
                    raise ValidationError(f"Missing 'github' field in user mapping for '{key}'")
                if not value['github'] or not str(value['github']).strip():
                    raise ValidationError(f"Empty GitHub username for user '{key}'")
            else:
                raise ValidationError(f"Invalid user mapping format for '{key}': {type(value)}")


class ConfigLoader:
    """
    Loads and validates configuration from JSON files.
    """

    @staticmethod
    def load_from_file(config_path: str) -> MigrationConfig:
        """
        Load and validate configuration from JSON file.

        Args:
            config_path: Path to the configuration JSON file

        Returns:
            Validated MigrationConfig object

        Raises:
            ConfigurationError: If configuration file is invalid or missing required keys
            ValidationError: If configuration data is invalid
            FileNotFoundError: If configuration file doesn't exist
            json.JSONDecodeError: If configuration file contains invalid JSON
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        if not config_path.is_file():
            raise ConfigurationError(f"Configuration path is not a file: {config_path}")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except PermissionError:
            raise ConfigurationError(f"Permission denied reading configuration file: {config_path}")
        except UnicodeDecodeError as e:
            raise ConfigurationError(f"Configuration file encoding error: {e}")

        # Validate required sections
        required_keys = ['bitbucket', 'github', 'user_mapping']
        for key in required_keys:
            if key not in data:
                raise ConfigurationError(f"Missing required section '{key}' in configuration file")

        # Validate each section
        ConfigValidator.validate_bitbucket_data(data['bitbucket'])
        ConfigValidator.validate_github_data(data['github'])
        ConfigValidator.validate_user_mapping(data['user_mapping'])

        # Create configuration objects
        try:
            bitbucket_config = BitbucketConfig(**data['bitbucket'])
            github_config = GitHubConfig(**data['github'])

            return MigrationConfig(
                bitbucket=bitbucket_config,
                github=github_config,
                user_mapping=data['user_mapping'],
                repository_mapping=data.get('repository_mapping', {}),
                dry_run=bool(data.get('dry_run', False)),
                skip_issues=bool(data.get('skip_issues', False)),
                skip_prs=bool(data.get('skip_prs', False)),
                skip_pr_as_issue=bool(data.get('skip_pr_as_issue', False)),
                use_gh_cli=bool(data.get('use_gh_cli', False))
            )

        except TypeError as e:
            raise ValidationError(f"Invalid configuration format: {e}")

    @staticmethod
    def load_from_dict(data: Dict[str, Any]) -> MigrationConfig:
        """
        Load and validate configuration from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Validated MigrationConfig object

        Raises:
            ConfigurationError: If configuration data is missing required keys
            ValidationError: If configuration data is invalid
        """
        # Validate required sections
        required_keys = ['bitbucket', 'github', 'user_mapping']
        for key in required_keys:
            if key not in data:
                raise ConfigurationError(f"Missing required section '{key}' in configuration data")

        # Validate each section
        ConfigValidator.validate_bitbucket_data(data['bitbucket'])
        ConfigValidator.validate_github_data(data['github'])
        ConfigValidator.validate_user_mapping(data['user_mapping'])

        # Create configuration objects
        try:
            bitbucket_config = BitbucketConfig(**data['bitbucket'])
            github_config = GitHubConfig(**data['github'])

            return MigrationConfig(
                bitbucket=bitbucket_config,
                github=github_config,
                user_mapping=data['user_mapping'],
                repository_mapping=data.get('repository_mapping', {}),
                dry_run=bool(data.get('dry_run', False)),
                skip_issues=bool(data.get('skip_issues', False)),
                skip_prs=bool(data.get('skip_prs', False)),
                skip_pr_as_issue=bool(data.get('skip_pr_as_issue', False)),
                use_gh_cli=bool(data.get('use_gh_cli', False))
            )

        except TypeError as e:
            raise ValidationError(f"Invalid configuration format: {e}")

    @staticmethod
    def save_to_file(config: MigrationConfig, config_path: str) -> None:
        """
        Save configuration to JSON file.

        Args:
            config: MigrationConfig object to save
            config_path: Path where to save the configuration
        """
        config_path = Path(config_path)

        # Convert config objects to dictionaries
        data = {
            'bitbucket': {
                'workspace': config.bitbucket.workspace,
                'repo': config.bitbucket.repo,
                'email': config.bitbucket.email,
                'token': config.bitbucket.token
            },
            'github': {
                'owner': config.github.owner,
                'repo': config.github.repo,
                'token': config.github.token
            },
            'user_mapping': config.user_mapping,
            'repository_mapping': config.repository_mapping,
            'dry_run': bool(config.dry_run),
            'skip_issues': bool(config.skip_issues),
            'skip_prs': bool(config.skip_prs),
            'skip_pr_as_issue': bool(config.skip_pr_as_issue),
            'use_gh_cli': bool(config.use_gh_cli)
        }

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except PermissionError:
            raise ConfigurationError(f"Permission denied writing configuration file: {config_path}")
        except Exception as e:
            raise ConfigurationError(f"Error saving configuration file: {e}")