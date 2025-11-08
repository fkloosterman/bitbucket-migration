"""
Type-safe configuration management for Bitbucket to GitHub migration.

This module provides structured configuration classes and validation
to ensure all required settings are present and properly formatted.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Union, List
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
class RepositoryConfig:
    """Configuration for a single repository in multi-repo migration."""
    bitbucket_repo: str
    github_repo: str
    # output_dir removed - now derived from base_dir + subcommand structure


@dataclass
class ExternalRepositoryConfig:
    """External repository referenced but not migrated here."""
    bitbucket_repo: str
    github_repo: Optional[str]  # None if not being migrated
    github_owner: Optional[str] = None


@dataclass
class OptionsConfig:
    """Migration options configuration."""
    skip_issues: bool = False
    open_issues_only: bool = False
    skip_prs: bool = False
    open_prs_only: bool = False
    skip_pr_as_issue: bool = False
    skip_milestones: bool = False
    open_milestones_only: bool = False
    dry_run: bool = False
    rewrite_cross_repo_links: bool = False
    request_delay_seconds: float = 1.5  # Delay between mutative API requests (GitHub recommends >= 1.0)


@dataclass
class MigrationConfig:
    """Unified configuration for multi-repository migrations (v2.0)."""
    format_version: str  # Required: "2.0"
    bitbucket: BitbucketConfig  # No repo field
    github: GitHubConfig        # No repo field
    repositories: List[RepositoryConfig]
    user_mapping: Dict[str, Any]
    base_dir: str = "."  # Optional: defaults to current directory
    external_repositories: List[ExternalRepositoryConfig] = field(default_factory=list)
    issue_type_mapping: Dict[str, str] = field(default_factory=dict)
    options: OptionsConfig = field(default_factory=lambda: OptionsConfig())
    # cross_repo_mappings_file: str = "cross_repo_mappings.json"
    link_rewriting_config: 'LinkRewritingConfig' = field(default_factory=lambda: LinkRewritingConfig())
    # dry_run: bool = False  # For compatibility with existing code


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
    Loads and validates unified configuration from JSON files (v2.0 format only).
    """

    @staticmethod
    def load_from_file(config_path: str) -> MigrationConfig:
        """
        Load and validate unified configuration from JSON file (v2.0 format only).

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

        # Validate format version (required for v2.0)
        format_version = data.get('format_version')
        if format_version != '2.0':
            raise ConfigurationError(
                f"Unsupported config format. Expected version 2.0, got {format_version}. "
                f"See docs/reference/migration_config.md for current format."
            )

        # Validate required fields for v2.0
        if 'repositories' not in data or not isinstance(data['repositories'], list):
            raise ConfigurationError(
                "Config must have 'repositories' array. "
                "See docs/reference/migration_config.md for format."
            )

        if 'repo' in data.get('bitbucket', {}):
            raise ConfigurationError(
                "Invalid config: 'bitbucket.repo' field not allowed in v2.0 format. "
                "Use 'repositories' array instead."
            )

        if 'repo' in data.get('github', {}):
            raise ConfigurationError(
                "Invalid config: 'github.repo' field not allowed in v2.0 format. "
                "Use 'repositories' array instead."
            )

        return ConfigLoader._load_unified_config(data)

    @staticmethod
    def load_from_dict(data: Dict[str, Any]) -> MigrationConfig:
        """
        Load and validate unified configuration from dictionary (v2.0 format).

        Args:
            data: Configuration dictionary in v2.0 format

        Returns:
            Validated MigrationConfig object

        Raises:
            ConfigurationError: If configuration data is missing required keys
            ValidationError: If configuration data is invalid
        """
        # Validate format version
        format_version = data.get('format_version')
        if format_version != '2.0':
            raise ConfigurationError(
                f"Unsupported config format. Expected version 2.0, got {format_version}."
            )

        # Validate required sections
        required_keys = ['bitbucket', 'github', 'user_mapping', 'repositories']
        for key in required_keys:
            if key not in data:
                raise ConfigurationError(f"Missing required section '{key}' in configuration data")

        # Validate repositories array
        if not isinstance(data['repositories'], list) or len(data['repositories']) == 0:
            raise ValidationError("'repositories' must be a non-empty list")

        # Validate no repo fields in bitbucket/github sections
        if 'repo' in data.get('bitbucket', {}):
            raise ValidationError("bitbucket section should not have 'repo' field in v2.0 format")
        if 'repo' in data.get('github', {}):
            raise ValidationError("github section should not have 'repo' field in v2.0 format")

        # Validate each section
        ConfigValidator.validate_user_mapping(data['user_mapping'])

        # Create configuration objects
        try:
            # Parse bitbucket/github configs (with placeholder repo values for validation)
            bitbucket_data = data['bitbucket'].copy()
            bitbucket_data['repo'] = '__unified_config__'  # Placeholder for validation
            bitbucket_config = BitbucketConfig(**bitbucket_data)

            github_data = data['github'].copy()
            github_data['repo'] = '__unified_config__'  # Placeholder for validation
            github_config = GitHubConfig(**github_data)

            # Parse repositories
            repositories = []
            for idx, repo_data in enumerate(data['repositories']):
                if not isinstance(repo_data, dict):
                    raise ValidationError(f"Repository entry {idx} must be a dictionary")
                if 'bitbucket_repo' not in repo_data:
                    raise ValidationError(f"Repository entry {idx}: missing 'bitbucket_repo' field")
                if 'github_repo' not in repo_data:
                    raise ValidationError(f"Repository entry {idx}: missing 'github_repo' field")
                repositories.append(RepositoryConfig(**repo_data))

            # Parse external repositories
            external_repositories = []
            for idx, ext_repo_data in enumerate(data.get('external_repositories', [])):
                if not isinstance(ext_repo_data, dict):
                    raise ValidationError(f"External repository entry {idx} must be a dictionary")
                if 'bitbucket_repo' not in ext_repo_data:
                    raise ValidationError(f"External repository entry {idx}: missing 'bitbucket_repo' field")
                external_repositories.append(ExternalRepositoryConfig(**ext_repo_data))

            # Parse options
            options_data = data.get('options', {})
            options = OptionsConfig(**options_data)

            return MigrationConfig(
                format_version='2.0',
                bitbucket=bitbucket_config,
                github=github_config,
                repositories=repositories,
                user_mapping=data['user_mapping'],
                base_dir=data.get('base_dir', '.'),
                external_repositories=external_repositories,
                issue_type_mapping=data.get('issue_type_mapping', {}),
                options=options,
                # cross_repo_mappings_file=data.get('cross_repo_mappings_file', 'cross_repo_mappings.json'),
                link_rewriting_config=LinkRewritingConfig(data.get('link_rewriting_config'))
            )

        except TypeError as e:
            raise ValidationError(f"Invalid configuration format: {e}")

    @staticmethod
    def _load_unified_config(data: Dict[str, Any]) -> MigrationConfig:
        """
        Load unified configuration format (v2.0) for multi-repository migrations.

        Args:
            data: Configuration dictionary in v2.0 format

        Returns:
            Validated MigrationConfig object

        Raises:
            ConfigurationError: If configuration is invalid
            ValidationError: If configuration data is invalid
        """
        # Validate user mapping
        ConfigValidator.validate_user_mapping(data['user_mapping'])

        # Parse bitbucket and github configs (with placeholder repo values for validation)
        try:
            bitbucket_data = data['bitbucket'].copy()
            bitbucket_data['repo'] = '__unified_config__'  # Placeholder for validation
            bitbucket_config = BitbucketConfig(**bitbucket_data)

            github_data = data['github'].copy()
            github_data['repo'] = '__unified_config__'  # Placeholder for validation
            github_config = GitHubConfig(**github_data)
        except (TypeError, ValidationError) as e:
            raise ValidationError(f"Invalid bitbucket/github configuration: {e}")

        # Parse repositories
        try:
            repositories = []
            for idx, repo_data in enumerate(data['repositories']):
                if not isinstance(repo_data, dict):
                    raise ValidationError(f"Repository entry {idx} must be a dictionary")

                # Validate required fields
                if 'bitbucket_repo' not in repo_data:
                    raise ValidationError(f"Repository entry {idx}: missing 'bitbucket_repo' field")
                if 'github_repo' not in repo_data:
                    raise ValidationError(f"Repository entry {idx}: missing 'github_repo' field")

                repositories.append(RepositoryConfig(**repo_data))
        except TypeError as e:
            raise ValidationError(f"Invalid repository configuration: {e}")

        # Parse external repositories
        try:
            external_repositories = []
            for idx, ext_repo_data in enumerate(data.get('external_repositories', [])):
                if not isinstance(ext_repo_data, dict):
                    raise ValidationError(f"External repository entry {idx} must be a dictionary")

                # Validate required fields
                if 'bitbucket_repo' not in ext_repo_data:
                    raise ValidationError(f"External repository entry {idx}: missing 'bitbucket_repo' field")

                external_repositories.append(ExternalRepositoryConfig(**ext_repo_data))
        except TypeError as e:
            raise ValidationError(f"Invalid external repository configuration: {e}")

        # Parse options
        try:
            options_data = data.get('options', {})
            options = OptionsConfig(**options_data)
        except TypeError as e:
            raise ValidationError(f"Invalid options configuration: {e}")

        # Create unified config
        try:
            return MigrationConfig(
                format_version='2.0',
                bitbucket=bitbucket_config,
                github=github_config,
                repositories=repositories,
                user_mapping=data['user_mapping'],
                base_dir=data.get('base_dir', '.'),
                external_repositories=external_repositories,
                issue_type_mapping=data.get('issue_type_mapping', {}),
                options=options,
                # cross_repo_mappings_file=data.get('cross_repo_mappings_file', 'cross_repo_mappings.json'),
                link_rewriting_config=LinkRewritingConfig(data.get('link_rewriting_config'))
            )
        except TypeError as e:
            raise ValidationError(f"Invalid unified configuration format: {e}")

    @staticmethod
    def save_to_file(config: MigrationConfig, config_path: str) -> None:
        """
        Save unified configuration to JSON file (v2.0 format).

        Args:
            config: MigrationConfig object to save
            config_path: Path where to save the configuration
        """
        config_path = Path(config_path)

        # Convert config objects to dictionaries
        data = {
            'format_version': '2.0',
            'bitbucket': {
                'workspace': config.bitbucket.workspace,
                'email': config.bitbucket.email,
                'token': config.bitbucket.token
            },
            'github': {
                'owner': config.github.owner,
                'token': config.github.token
            },
            'repositories': [
                {
                    'bitbucket_repo': repo.bitbucket_repo,
                    'github_repo': repo.github_repo
                }
                for repo in config.repositories
            ],
            'user_mapping': config.user_mapping,
            'base_dir': config.base_dir,
            'external_repositories': [
                {
                    'bitbucket_repo': ext_repo.bitbucket_repo,
                    'github_repo': ext_repo.github_repo,
                    'github_owner': ext_repo.github_owner
                }
                for ext_repo in config.external_repositories
            ],
            'issue_type_mapping': config.issue_type_mapping,
            'options': {
                            'skip_issues': config.options.skip_issues,
                            'open_issues_only': config.options.open_issues_only,
                            'skip_prs': config.options.skip_prs,
                            'open_prs_only': config.options.open_prs_only,
                            'skip_pr_as_issue': config.options.skip_pr_as_issue,
                            'skip_milestones': config.options.skip_milestones,
                            'open_milestones_only': config.options.open_milestones_only,
                            'rewrite_cross_repo_links': config.options.rewrite_cross_repo_links,
                            'request_delay_seconds': config.options.request_delay_seconds
                        },
            # 'cross_repo_mappings_file': config.cross_repo_mappings_file,
            'link_rewriting_config': {
                'enabled': config.link_rewriting_config.enabled,
                'enable_notes': config.link_rewriting_config.enable_notes,
                'enable_markdown_awareness': config.link_rewriting_config.enable_markdown_awareness,
                'note_templates': config.link_rewriting_config.note_templates
            }
        }

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except PermissionError:
            raise ConfigurationError(f"Permission denied writing configuration file: {config_path}")
        except Exception as e:
            raise ConfigurationError(f"Error saving configuration file: {e}")