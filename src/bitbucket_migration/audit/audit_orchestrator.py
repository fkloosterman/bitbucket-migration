"""
Multi-repository audit orchestrator for Bitbucket to GitHub migration analysis.

This module contains the MultiRepoAuditOrchestrator class that coordinates auditing
of multiple repositories in a workspace, generating unified configuration files.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import asdict

from ..clients.bitbucket_client import BitbucketClient
from ..utils.logging_config import MigrationLogger
from ..exceptions import ValidationError
from .auditor import Auditor
from ..utils.base_dir_manager import BaseDirManager
from ..config.migration_config import OptionsConfig

class AuditOrchestrator:
    """
    Orchestrate auditing of multiple repositories in a workspace.

    This class provides functionality to discover repositories, audit them,
    and generate unified configuration files for multi-repository migrations.
    """

    def __init__(self, workspace: str, email: str, token: str, log_level: str = "INFO", base_dir_manager: Optional[BaseDirManager] = None):
        """
        Initialize the MultiRepoAuditOrchestrator.

        Args:
            workspace: Bitbucket workspace name
            email: User email for API authentication
            token: Bitbucket API token
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            base_dir_manager: Base Directory Manager

        Raises:
            ValidationError: If any required parameter is empty
        """
        if not workspace or not workspace.strip():
            raise ValidationError("Bitbucket workspace cannot be empty")
        if not email or not email.strip():
            raise ValidationError("Bitbucket email cannot be empty")
        if not token or not token.strip():
            raise ValidationError("Bitbucket token cannot be empty")

        self.workspace = workspace
        self.email = email
        self.token = token

        # Store BaseDirManager (create default if not provided)
        self.base_dir_manager = base_dir_manager or BaseDirManager(".")

        # Initialize logger
        self.logger = MigrationLogger(log_level=log_level)

        # Initialize BitbucketClient for workspace-level operations
        # We need a dummy repo name for client initialization, but won't use repo-specific methods
        self.bb_client = BitbucketClient(workspace, "dummy", email, token)

    def discover_repositories(self) -> List[str]:
        """
        Discover all repositories in the workspace.

        Returns:
            List of repository slugs

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        self.logger.info(f"🔍 Discovering repositories in workspace: {self.workspace}")

        repos = self.bb_client.list_repositories()
        repo_slugs = [repo['slug'] for repo in repos]

        self.logger.info(f"✓ Found {len(repo_slugs)} repositories")
        for slug in repo_slugs:
            self.logger.info(f"  - {slug}")

        return repo_slugs

    def audit_repositories(
        self,
        repo_names: Optional[List[str]] = None,
        discover: bool = False,
        save_reports: bool = True
    ) -> Dict[str, Any]:
        """
        Audit multiple repositories.

        Args:
            repo_names: List of repository names to audit (if None and discover=True, discovers all)
            discover: Whether to auto-discover repositories if repo_names is None

        Returns:
            Dictionary mapping repository names to their audit reports

        Raises:
            ValidationError: If repo_names is None and discover is False
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        # Discover repositories if requested
        if repo_names is None:
            if discover:
                repo_names = self.discover_repositories()
            else:
                raise ValidationError("Either provide repo_names or set discover=True")

        if not repo_names:
            self.logger.warning("⚠️  No repositories to audit")
            return {}

        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"🔍 Starting multi-repository audit")
        self.logger.info(f"   Workspace: {self.workspace}")
        self.logger.info(f"   Repositories: {len(repo_names)}")
        self.logger.info(f"{'='*80}\n")

        reports = {}
        for i, repo_name in enumerate(repo_names, 1):
            self.logger.info(f"\n[{i}/{len(repo_names)}] Auditing {repo_name}...")
            self.logger.info(f"{'-'*80}")

            try:
                # Create AuditOrchestrator for this repository
                auditor = Auditor(
                    workspace=self.workspace,
                    repo=repo_name,
                    email=self.email,
                    token=self.token,
                    log_level=self.logger.log_level,
                    base_dir_manager=self.base_dir_manager
                )

                # Run audit
                report = auditor.run_audit()
                reports[repo_name] = report

                self.logger.info(f"✅ Completed audit for {repo_name}")

                if save_reports:
                    if 'error' in report:
                        self.logger.warning(f"⚠️  Skip saving audit reports b/c failed audit for {repo_name}")
                    else:
                        auditor.save_reports()

            except Exception as e:
                self.logger.error(f"❌ Failed to audit {repo_name}: {e}")
                reports[repo_name] = {
                    'error': str(e),
                    'status': 'failed'
                }

        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"✅ Multi-repository audit completed")
        self.logger.info(f"   Successful: {sum(1 for r in reports.values() if 'error' not in r)}/{len(repo_names)}")
        self.logger.info(f"   Failed: {sum(1 for r in reports.values() if 'error' in r)}/{len(repo_names)}")
        self.logger.info(f"{'='*80}\n")

        return reports

    def generate_config(
        self,
        reports: Dict[str, Any],
        gh_owner: str = "",
        external_repos: List[str] = None,
        existing_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate unified configuration from audit reports, merging with existing config if present.

        Args:
            reports: Dictionary mapping repository names to their audit reports
            gh_owner: GitHub owner/organization name
            external_repos: List of external repository names for reference

        Returns:
            Unified configuration dictionary
        """
        self.logger.info("📋 Generating unified configuration...")

        # Use provided existing config, or load from file if not provided
        if existing_config is None:
            existing_config = self._load_existing_config()

        if existing_config:
            self.logger.info("✓ Merging with existing configuration")
            is_merge = True
        else:
            self.logger.info("✓ Creating new configuration")
            is_merge = False

        # Use existing gh_owner if not provided and we have existing config
        if not gh_owner and existing_config and 'github' in existing_config and 'owner' in existing_config['github']:
            gh_owner = existing_config['github']['owner']
        elif not gh_owner:
            gh_owner = "YOUR_GITHUB_USERNAME"

        # Build new repository list from current reports
        new_repositories = []
        for repo_name in reports.keys():
            # Skip failed audits
            if 'error' in reports[repo_name]:
                continue

            new_repositories.append({
                "bitbucket_repo": repo_name,
                "github_repo": repo_name,  # Default: same name
                # "output_dir": f"{self.workspace}_{repo_name}"
            })

        # Build new external repositories list
        new_external_repositories = []
        if external_repos:
            for repo_name in external_repos:
                new_external_repositories.append({
                    "bitbucket_repo": repo_name,
                    "github_repo": repo_name,  # Default: same name (will be overridden in config)
                    # "output_dir": f"{self.workspace}_{repo_name}"
                })

        # Merge repositories
        if is_merge:
            existing_repos = existing_config.get('repositories', [])
            repositories = self._merge_repositories(existing_repos, new_repositories)

            existing_external_repos = existing_config.get('external_repositories', [])
            external_repositories = self._merge_repositories(existing_external_repos, new_external_repositories)
        else:
            repositories = new_repositories
            external_repositories = new_external_repositories

        # Merge user mappings
        existing_user_mapping = existing_config.get('user_mapping') if existing_config else None
        merged_user_mapping = self._merge_user_mappings(reports, existing_user_mapping)

        # Use existing options if available, otherwise create default
        if is_merge and 'options' in existing_config:
            options = existing_config['options']
        else:
            options = asdict(OptionsConfig())

        # Build final config
        config = {
            "_comment": "Bitbucket to GitHub Multi-Repository Migration Configuration",
            "_instructions": {
                "step_1": "Set BITBUCKET_TOKEN or BITBUCKET_API_TOKEN environment variable (or in .env file) with your Bitbucket API token",
                "step_2": "Set GITHUB_TOKEN or GITHUB_API_TOKEN environment variable (or in .env file) with your GitHub personal access token (needs 'repo' scope)",
                "step_3": "Set github.owner to your GitHub username or organization",
                "step_4": "Review and adjust repository mappings (bitbucket_repo -> github_repo)",
                "step_5": "For each user in user_mapping - set to their GitHub username if they have an account, or set to null/empty if they don't",
                "step_6": "Run dry-run first to validate configuration",
                "step_7": "After dry-run succeeds, run actual migration"
            },
            "options": options,
            "bitbucket": {
                "workspace": self.workspace,
                "email": self.email
            },
            "github": {
                "owner": gh_owner
            },
            "base_dir": str(self.base_dir_manager.base_dir.absolute()),
            "repositories": repositories,
            "external_repositories": external_repositories,
            "user_mapping": merged_user_mapping
        }

        # Log results
        action = "Merged" if is_merge else "Generated"
        self.logger.info(f"✓ {action} configuration for {len(repositories)} repositories")
        if external_repositories:
            self.logger.info(f"✓ Added {len(external_repositories)} external reference repositories")
        self.logger.info(f"✓ Merged user mappings: {len(merged_user_mapping)} unique users")

        return config

    def _load_existing_config(self) -> Optional[Dict[str, Any]]:
        """
        Load existing configuration file if it exists.

        Returns:
            Existing configuration dictionary, or None if file doesn't exist or is invalid
        """
        config_path = self.base_dir_manager.get_config_path()

        if not config_path.exists():
            return None

        try:
            with open(config_path, 'r') as f:
                existing_config = json.load(f)

            # Validate that it's a dict and has required structure
            if not isinstance(existing_config, dict):
                self.logger.warning(f"⚠️  Existing config file is not a valid JSON object: {config_path}")
                return None

            # Check if workspace matches
            if 'bitbucket' in existing_config and 'workspace' in existing_config['bitbucket']:
                existing_workspace = existing_config['bitbucket']['workspace']
                if existing_workspace != self.workspace:
                    self.logger.warning(f"⚠️  Existing config is for different workspace '{existing_workspace}', creating new config")
                    return None

            self.logger.info(f"✓ Loaded existing configuration from {config_path}")
            return existing_config

        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"⚠️  Failed to load existing config file {config_path}: {e}")
            return None

    def _merge_repositories(self, existing_repos: List[Dict[str, str]], new_repos: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Merge repository lists, avoiding duplicates based on bitbucket_repo name.

        Args:
            existing_repos: Repositories from existing config
            new_repos: New repositories to add

        Returns:
            Merged repository list
        """
        # Create a dict keyed by bitbucket_repo for easy lookup
        merged = {repo['bitbucket_repo']: repo for repo in existing_repos}

        # Add new repos, overwriting if they already exist (new audit takes precedence)
        for repo in new_repos:
            merged[repo['bitbucket_repo']] = repo

        return list(merged.values())

    def _merge_user_mappings(self, reports: Dict[str, Any], existing_mapping: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Merge user mappings from all repository reports and existing config.

        Args:
            reports: Dictionary mapping repository names to their audit reports
            existing_mapping: Existing user mapping from config file

        Returns:
            Merged user mapping dictionary
        """
        all_users = set()

        # Collect users from existing mapping
        if existing_mapping:
            all_users.update(existing_mapping.keys())

        # Collect users from new reports
        for repo_name, report in reports.items():
            # Skip failed audits
            if 'error' in report:
                continue

            # Extract users from report
            if 'users' in report and 'list' in report['users']:
                all_users.update(report['users']['list'])

        # Create mapping template, preserving existing mappings
        user_mapping = {}
        for user in sorted(all_users):
            if user.lower() in ('unknown', 'unknown (deleted user)'):
                user_mapping[user] = None
            elif existing_mapping and user in existing_mapping:
                # Preserve existing mapping
                user_mapping[user] = existing_mapping[user]
            else:
                user_mapping[user] = ""  # Empty string to be filled in

        return user_mapping

    def save_config(
        self,
        config: Dict[str, Any],
        filename: str = None
    ) -> None:
        """
        Save unified configuration to file.

        Args:
            config: Configuration dictionary
            filename: Output filename (auto-generated if None)
            output_dir: Directory to save config in
        """
        import json
        
        self.base_dir_manager.ensure_base_dir()
        config_file = self.base_dir_manager.get_config_path(filename)

        # Use create_file to register the config file with 'system' subcommand
        self.base_dir_manager.create_file(
            config_file,
            config,
            subcommand='system',
            category='config'
        )

        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"📋 Unified migration configuration saved: {config_file}")
        self.logger.info(f"{'='*80}")
        self.logger.info("Next steps:")
        self.logger.info("1. Review and edit the configuration file:")
        self.logger.info("   - Set BITBUCKET_TOKEN environment variable")
        self.logger.info("   - Set GITHUB_TOKEN environment variable")
        self.logger.info("   - Set github.owner to your GitHub username/organization")
        self.logger.info("   - Review repository mappings (adjust github_repo names if needed)")
        self.logger.info("   - Map Bitbucket users to GitHub usernames")
        self.logger.info("     (use null for users without GitHub accounts)")
        self.logger.info("2. Test with dry run:")
        self.logger.info(f"   migrate_bitbucket_to_github dry-run --config {config_file}")
        self.logger.info("3. Run actual migration:")
        self.logger.info(f"   migrate_bitbucket_to_github migrate --config {config_file}")
        self.logger.info(f"{'='*80}\n")
