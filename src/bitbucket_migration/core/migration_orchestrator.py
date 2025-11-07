"""
Migration orchestrator for Bitbucket to GitHub migration.

This module contains the MigrationOrchestrator class that coordinates
migration of multiple repositories using a unified configuration.
"""

from typing import List, Optional
from pathlib import Path

from ..config.migration_config import (
    MigrationConfig,
    BitbucketConfig,
    GitHubConfig,
    RepositoryConfig,
    OptionsConfig
)
from ..utils.base_dir_manager import BaseDirManager
from ..core.repo_migrator import RepoMigrator, CrossLinkMigrator
from ..utils.logging_config import MigrationLogger


class BaseOrchestrator:

    def __init__(
        self,
        config: MigrationConfig,
        selected_repos: Optional[List[str]] = None,
        dry_run: bool = False,
        logger: Optional[MigrationLogger] = None,
        log_level: str = 'INFO'
    ):
        
        self.config = config
        self.selected_repos = selected_repos or [
            r.bitbucket_repo for r in config.repositories
        ]
        self.base_dir_manager = BaseDirManager(config.base_dir)
        self.dry_run = dry_run
        self.log_level = log_level

        # Setup logger
        if logger:
            self.logger = logger
        else:
            # Create a logger for multi-repo orchestration
            log_file = self.base_dir_manager.base_dir / self._get_log_file()
            self.logger = MigrationLogger(
                log_level=self.log_level,
                log_file=str(log_file),
                dry_run=self.dry_run,
                overwrite=False,
                logger_name='bitbucket_migration_orchestrator'
            )

            # Register the orchestrator log file for tracking
            self.base_dir_manager.register_log_file(
                log_file,
                subcommand=self._get_subcommand(),
                workspace=self.config.bitbucket.workspace,
                repo=None  # This is the orchestrator log, not repo-specific
            )

        # Track overall migration progress
        self.migration_results = {}

    def _get_subcommand(self):
        raise NotImplementedError
    
    def _get_log_file(self):
        raise NotImplementedError

    def _get_selected_repositories(self) -> List[RepositoryConfig]:
        """
        Get list of repositories to migrate based on selection.

        Returns:
            List of RepositoryConfig objects for selected repositories
        """
        return [
            repo for repo in self.config.repositories
            if repo.bitbucket_repo in self.selected_repos
        ]
    
    def _build_per_repo_config(self, repo: RepositoryConfig, subcommand: str) -> MigrationConfig:
        """
        Build per-repository MigrationConfig from unified config.

        This method creates a MigrationConfig for a single repository by
        combining the unified configuration settings with repository-specific
        overrides.

        Args:
            repo: Repository configuration from unified config
            subcommand: Subcommand being executed ('migrate' or 'dry-run')

        Returns:
            MigrationConfig for the specific repository
        """

        # Build per-repo config with fallback logic for options
        per_repo_config = MigrationConfig(
            format_version='2.0',
            bitbucket=BitbucketConfig(
                workspace=self.config.bitbucket.workspace,
                email=self.config.bitbucket.email,
                token=self.config.bitbucket.token,
                repo=repo.bitbucket_repo
            ),
            github=GitHubConfig(
                owner=self.config.github.owner,
                token=self.config.github.token,
                repo=repo.github_repo
            ),
            repositories=[],  # Not needed for single repo orchestrator
            user_mapping=self.config.user_mapping,
            base_dir=self.config.base_dir,
            external_repositories=self.config.external_repositories,
            issue_type_mapping=self.config.issue_type_mapping,
            options=self.config.options,
            link_rewriting_config=self.config.link_rewriting_config,
        )


        return per_repo_config
    
    def _print_migration_summary(self) -> None:
        """Print summary of multi-repository migration."""

        subcommand = self._get_subcommand().replace('_',' ')
        
        self.logger.info("=" * 80)
        self.logger.info(f"📊 MULTI-REPOSITORY {subcommand.upper()} SUMMARY")
        self.logger.info("=" * 80)

        successful = [r for r, result in self.migration_results.items() if result['status'] == 'success']
        failed = [r for r, result in self.migration_results.items() if result['status'] == 'failed']

        self.logger.info(f"Total repositories: {len(self.migration_results)}")
        self.logger.info(f"✅ Successful: {len(successful)}")
        self.logger.info(f"❌ Failed: {len(failed)}")
        self.logger.info("")

        if successful:
            self.logger.info(f"Successfully performed {subcommand} for repositories:")
            for repo in successful:
                result = self.migration_results[repo]
                self.logger.info(f"  ✅ {repo} → {result['github_repo']}")
                self.logger.info(f"     Output: {result['output_dir']}")

        if failed:
            self.logger.info("")
            self.logger.info(f"Failed repositories:")
            for repo in failed:
                result = self.migration_results[repo]
                self.logger.info(f"  ❌ {repo} → {result['github_repo']}")
                self.logger.info(f"     Error: {result['error']}")

        self.logger.info("")
        self.logger.info("=" * 80)

        if failed:
            self.logger.warning(f"⚠️  Some repositories failed to {subcommand}. Check logs for details.")
        else:
            self.logger.info(f"✅ ALL REPOSITORIES PROCESSED SUCCESSFULLY")

        self.logger.info("=" * 80)


class MigrationOrchestrator(BaseOrchestrator):
    """
    Orchestrate migration of multiple repositories.

    This class manages the migration of multiple repositories defined in a
    MigrationConfig (v2.0), delegating to individual MigrationOrchestrator
    instances for each repository.
    """

    def __init__(
        self,
        config: MigrationConfig,
        selected_repos: Optional[List[str]] = None,
        dry_run: bool = False,
        logger: Optional[MigrationLogger] = None, 
        log_level: str = 'INFO'
    ):
        """
        Initialize the MigrationOrchestrator.

        Args:
            config: Unified configuration for multi-repository migration (v2.0)
            selected_repos: Optional list of repository names to migrate.
                            If None, all repositories in config will be migrated.
            dry_run: Run migration in dry-run mode
            logger: Optional logger instance. If not provided, a new one will be created.
        """
        
        super().__init__(config, selected_repos, dry_run, logger, log_level)
    
    def _get_log_file(self):
        return "repo_migration_log.txt"

    def _get_subcommand(self):
        return "dry-run" if self.dry_run else "migrate"

    def run_migration(self) -> None:
        """
        Run migration/dry-run for all selected repositories.

        This method iterates through each selected repository, builds a
        per-repository configuration, and runs the migration using the
        single-repository orchestrator.

        Args:
            subcommand: Subcommand to execute ('migrate' or 'dry-run')
        """

        subcommand = "dry-run" if self.dry_run else "migrate"

        self.logger.info("=" * 80)
        self.logger.info(f"🚀 STARTING MULTI-REPOSITORY {subcommand.upper()}")
        self.logger.info("=" * 80)

        if self.dry_run:
            self.logger.info("🔍 DRY RUN MODE ENABLED - No changes will be made")
            self.logger.info("")

        selected_repositories = self._get_selected_repositories()
        total_repos = len(selected_repositories)

        self.logger.info(f"Found {total_repos} repository(ies) to {subcommand}:")
        for repo in selected_repositories:
            self.logger.info(f"  - {repo.bitbucket_repo} → {repo.github_repo}")
        self.logger.info("")

        # Run subcommand for each repository
        for idx, repo_config in enumerate(selected_repositories, 1):
            self.logger.info("=" * 80)
            self.logger.info(f"📦 MIGRATING REPOSITORY {idx}/{total_repos}")
            self.logger.info(f"Bitbucket: {self.config.bitbucket.workspace}/{repo_config.bitbucket_repo}")
            self.logger.info(f"GitHub: {self.config.github.owner}/{repo_config.github_repo}")
            self.logger.info(f"Output: {self.base_dir_manager.get_relative_path(subcommand, self.config.bitbucket.workspace, repo_config.bitbucket_repo)}")
            self.logger.info("=" * 80)

            try:
                # Build per-repo config from unified config
                per_repo_config = self._build_per_repo_config(repo_config, subcommand)
                
                # Create and run single-repo orchestrator
                migrator = RepoMigrator(per_repo_config, dry_run=self.dry_run, log_level=self.log_level)
                migrator.run_migration()

                # Track success
                output_dir = self.base_dir_manager.get_subcommand_dir(
                    subcommand, self.config.bitbucket.workspace, repo_config.bitbucket_repo
                )
                self.migration_results[repo_config.bitbucket_repo] = {
                    'status': 'success',
                    'github_repo': repo_config.github_repo,
                    'output_dir': str(output_dir)
                }

                self.logger.info(f"✅ Successfully performed {subcommand} for {repo_config.bitbucket_repo}")
                self.logger.info("")

            except Exception as e:
                # Track failure
                self.migration_results[repo_config.bitbucket_repo] = {
                    'status': 'failed',
                    'github_repo': repo_config.github_repo,
                    'error': str(e)
                }

                self.logger.error(f"❌ Failed to perform {subcommand} for {repo_config.bitbucket_repo}: {e}")
                self.logger.error("Continuing with next repository...")
                self.logger.info("")
        
        # Print summary
        self._print_migration_summary()
    

class CrossLinkOrchestrator(BaseOrchestrator):

    def __init__(
        self,
        config: MigrationConfig,
        selected_repos: Optional[List[str]] = None,
        dry_run: bool = False,
        logger: Optional[MigrationLogger] = None,
        log_level: str = 'INFO'
    ):
        
        super().__init__(config, selected_repos, dry_run, logger, log_level)

    def _get_log_file(self):
        return "repo_cross_link_log.txt"
    
    def _get_subcommand(self):
        return "cross-link_dry-run" if self.dry_run else "cross-link"

    def run_migration(self) -> None:
        
        subcommand = "cross-link_dry-run" if self.dry_run else "cross-link"

        self.logger.info("=" * 80)
        self.logger.info(f"🚀 STARTING MULTI-REPOSITORY {subcommand.upper().replace('_', ' ')}")
        self.logger.info("=" * 80)

        if self.dry_run:
            self.logger.info("🔍 DRY RUN MODE ENABLED - No changes will be made")
            self.logger.info("")

        selected_repositories = self._get_selected_repositories()
        total_repos = len(selected_repositories)

        self.logger.info(f"Found {total_repos} repository(ies) to {subcommand.replace('_',' ')}:")
        for repo in selected_repositories:
            self.logger.info(f"  - {repo.bitbucket_repo} → {repo.github_repo}")
        self.logger.info("")

        # Run subcommand for each repository
        for idx, repo_config in enumerate(selected_repositories, 1):
            self.logger.info("=" * 80)
            self.logger.info(f"📦 MIGRATING REPOSITORY {idx}/{total_repos}")
            self.logger.info(f"Bitbucket: {self.config.bitbucket.workspace}/{repo_config.bitbucket_repo}")
            self.logger.info(f"GitHub: {self.config.github.owner}/{repo_config.github_repo}")
            self.logger.info(f"Output: {self.base_dir_manager.get_relative_path(subcommand, self.config.bitbucket.workspace, repo_config.bitbucket_repo)}")
            self.logger.info("=" * 80)

            try:
                # Build per-repo config from unified config
                per_repo_config = self._build_per_repo_config(repo_config, subcommand)
                
                # Create and run single-repo orchestrator
                migrator = CrossLinkMigrator(per_repo_config, dry_run=self.dry_run, log_level=self.log_level)
                migrator.run_migration()

                # Track success
                output_dir = self.base_dir_manager.get_subcommand_dir(
                    subcommand, self.config.bitbucket.workspace, repo_config.bitbucket_repo
                )
                self.migration_results[repo_config.bitbucket_repo] = {
                    'status': 'success',
                    'github_repo': repo_config.github_repo,
                    'output_dir': str(output_dir)
                }

                self.logger.info(f"✅ Successfully performed {subcommand.replace('_',' ')} for {repo_config.bitbucket_repo}")
                self.logger.info("")

            except Exception as e:
                # Track failure
                self.migration_results[repo_config.bitbucket_repo] = {
                    'status': 'failed',
                    'github_repo': repo_config.github_repo,
                    'error': str(e)
                }

                self.logger.error(f"❌ Failed to perform {subcommand.replace('_',' ')} for {repo_config.bitbucket_repo}: {e}")
                self.logger.error("Continuing with next repository...")
                self.logger.info("")
        
        # Print summary
        self._print_migration_summary()
