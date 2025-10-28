"""
Type-safe configuration management for Bitbucket to GitHub migration.

This module provides structured configuration classes and validation
to ensure all required settings are present and properly formatted.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Union
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
        issue_type_mapping: Mapping of Bitbucket issue types to GitHub issue types
        skip_issues: Whether to skip issue migration
        skip_prs: Whether to skip PR migration
        skip_pr_as_issue: Whether to skip migrating closed PRs as issues
        use_gh_cli: Whether to use GitHub CLI for attachment uploads
        link_rewriting_config: Configuration for link rewriting and note templates
        output_dir: Output directory for migration files (default: '.')
        cross_repo_mappings_file: Path to cross-repository mappings file (optional)
    """
    bitbucket: BitbucketConfig
    github: GitHubConfig
    user_mapping: Dict[str, Any]
    issue_type_mapping: Dict[str, str] = field(default_factory=dict)
    skip_issues: bool = field(default=False)
    skip_prs: bool = field(default=False)
    skip_pr_as_issue: bool = field(default=False)
    use_gh_cli: bool = field(default=False)
    link_rewriting_config: 'LinkRewritingConfig' = field(default_factory=lambda: LinkRewritingConfig())
    output_dir: str = field(default_factory=lambda: '.')
    cross_repo_mappings_file: Optional[str] = field(default=None)

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.user_mapping:
            raise ValidationError("User mapping cannot be empty")

        # Repository mapping is now handled by CrossRepoMappingStore

        # Validate issue type mapping format if provided
        if self.issue_type_mapping:
            for bb_type, gh_type in self.issue_type_mapping.items():
                if not bb_type or not bb_type.strip():
                    raise ValidationError(f"Invalid Bitbucket issue type in mapping: '{bb_type}'")
                if not gh_type or not gh_type.strip():
                    raise ValidationError(f"Invalid GitHub issue type in mapping: '{bb_type}' -> '{gh_type}'")

        # Set default output directory based on workspace and repo if not specified
        if self.output_dir == '.':
            self.output_dir = f"{self.bitbucket.workspace}_{self.bitbucket.repo}"

        # Ensure output directory exists
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Validate cross_repo_mappings_file if provided
        if self.cross_repo_mappings_file:
            mapping_path = Path(self.cross_repo_mappings_file)
            if mapping_path.exists() and not mapping_path.is_file():
                raise ValidationError(
                    f"Cross-repo mappings path is not a file: {self.cross_repo_mappings_file}"
                )


class LinkRewritingConfig:
   """
   Configuration for link rewriting and note templates.

   Manages templates for different types of Bitbucket links when migrating to GitHub,
   with support for enabling/disabling notes and markdown context awareness.
   """

   def __init__(self, config_dict: Optional[Dict] = None):
       """
       Initialize link rewriting configuration.

       Args:
           config_dict: Configuration dictionary containing link rewriting settings
       """
       config = config_dict or {}
       self.enabled = config.get('enabled', True)
       self.note_templates = config.get('note_templates', self._default_templates())
       self.enable_notes = config.get('enable_notes', True)
       self.enable_markdown_awareness = config.get('enable_markdown_context_awareness', True)

   @staticmethod
   def _default_templates() -> Dict[str, str]:
       """Default note templates for different link types."""
       return {
           'issue_link': ' *(was [BB #{bb_num}]({bb_url}))*',
           'pr_link': ' *(was [BB PR #{bb_num}]({bb_url}))*',
           'commit_link': ' *(was [Bitbucket]({bb_url}))*',
           'branch_link': ' *(was [Bitbucket]({bb_url}))*',
           'compare_link': ' *(was [Bitbucket]({bb_url}))*',
           'repo_home_link': '',
           'cross_repo_link': ' *(was [Bitbucket]({bb_url}))*',
           'short_issue_ref': ' *(was BB `#{bb_num}`)*',
           'pr_ref': ' *(was BB PR `#{bb_num}`)*',
           'mention': '',
           'default': ' *(migrated link)*'
       }

   def get_template(self, link_type: str) -> str:
       """
       Get template for link type, falling back to default.

       Args:
           link_type: Type of link (e.g., 'issue_link', 'pr_link')

       Returns:
           Template string for the link type, or default template if not found
       """
       return self.note_templates.get(link_type, self.note_templates.get('default', ''))


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
                issue_type_mapping=data.get('issue_type_mapping', {}),
                skip_issues=bool(data.get('skip_issues', False)),
                skip_prs=bool(data.get('skip_prs', False)),
                skip_pr_as_issue=bool(data.get('skip_pr_as_issue', False)),
                use_gh_cli=bool(data.get('use_gh_cli', False)),
                link_rewriting_config=LinkRewritingConfig(data.get('link_rewriting_config')),
                output_dir=data.get('output_dir', '.'),
                cross_repo_mappings_file=data.get('cross_repo_mappings_file')
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
                issue_type_mapping=data.get('issue_type_mapping', {}),
                skip_issues=bool(data.get('skip_issues', False)),
                skip_prs=bool(data.get('skip_prs', False)),
                skip_pr_as_issue=bool(data.get('skip_pr_as_issue', False)),
                use_gh_cli=bool(data.get('use_gh_cli', False)),
                link_rewriting_config=LinkRewritingConfig(data.get('link_rewriting_config')),
                output_dir=data.get('output_dir', '.'),
                cross_repo_mappings_file=data.get('cross_repo_mappings_file')
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
            'issue_type_mapping': config.issue_type_mapping,
            'skip_issues': bool(config.skip_issues),
            'skip_prs': bool(config.skip_prs),
            'skip_pr_as_issue': bool(config.skip_pr_as_issue),
            'use_gh_cli': bool(config.use_gh_cli),
            'link_rewriting_config': {
                'enabled': config.link_rewriting_config.enabled,
                'enable_notes': config.link_rewriting_config.enable_notes,
                'enable_markdown_awareness': config.link_rewriting_config.enable_markdown_awareness,
                'note_templates': config.link_rewriting_config.note_templates
            },
            'output_dir': config.output_dir,
            'cross_repo_mappings_file': config.cross_repo_mappings_file
        }

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except PermissionError:
            raise ConfigurationError(f"Permission denied writing configuration file: {config_path}")
        except Exception as e:
            raise ConfigurationError(f"Error saving configuration file: {e}")