"""
Migration orchestrator for Bitbucket to GitHub migration.

This module contains the MigrationOrchestrator class that coordinates
the entire migration process, delegating to specialized migrators and
handling overall workflow.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path

from ..clients.bitbucket_client import BitbucketClient
from ..clients.github_client import GitHubClient
from ..services.user_mapper import UserMapper
from ..services.link_rewriter import LinkRewriter
from ..services.attachment_handler import AttachmentHandler
from ..services.cross_repo_mapping_store import CrossRepoMappingStore
from ..formatters.formatter_factory import FormatterFactory
from ..config.migration_config import MigrationConfig
from ..migration.issue_migrator import IssueMigrator
from ..migration.pr_migrator import PullRequestMigrator
from ..migration.report_generator import ReportGenerator
from ..exceptions import MigrationError, APIError, AuthenticationError, NetworkError, ConfigurationError, ValidationError
from ..utils.logging_config import MigrationLogger
from ..utils.base_dir_manager import BaseDirManager
from ..services.cross_repo_link_handler import CrossRepoLinkHandler

from .migration_context import MigrationState, MigrationEnvironment
from ..migration.cross_link_updater import CrossLinkUpdater

class BaseMigrator:
    def __init__(self, config: MigrationConfig, dry_run: bool = False, log_level: str = 'INFO'):
        """
        Initialize the base repository handler.
        
        Args:
            config: Complete migration configuration
            dry_run: Run migration in dry-run mode
        """
        
        self.config = config
        self.dry_run = dry_run
        self.log_level = log_level
        
        # Core infrastructure
        self.base_dir_manager = BaseDirManager(config.base_dir)
        self.logger = None

        # Initialize infrastructure
        self._init_logger()

    def _init_logger(self) -> None:
        """
        Initialize stage-specific logger with appropriate files.
        
        Subclasses override _get_subcommand() and _get_log_filename() to control
        where log files are written, ensuring complete isolation between stages.
        """
        subcommand = self._get_subcommand()
        output_dir = self.base_dir_manager.ensure_subcommand_dir(
            subcommand, self.config.bitbucket.workspace, self.config.bitbucket.repo
        )
        log_file = output_dir / self._get_log_filename()
        
        # Create unique logger name for this repository and subcommand
        logger_name = f"bitbucket_migration_{self.config.bitbucket.workspace}_{self.config.bitbucket.repo}_{subcommand}"
        
        self.logger = MigrationLogger(
            log_level=self.log_level,
            log_file=str(log_file),
            dry_run=self.dry_run,
            overwrite=True,
            logger_name=logger_name
        )

        # Register log file for tracking
        self.base_dir_manager.register_log_file(
            log_file,
            subcommand=subcommand,
            workspace=self.config.bitbucket.workspace,
            repo=self.config.bitbucket.repo
        )
        
        self.logger.info(f"Initialized logger for {subcommand} mode")

    def _get_subcommand(self) -> str:
        """
        Get stage-specific subcommand name.
        
        Returns:
            Subcommand name for BaseDirManager directory structure
        """
        raise NotImplementedError("Subclasses must implement _get_subcommand()")
        
    def _get_log_filename(self) -> str:
        """
        Get stage-specific log filename.
        
        Returns:
            Log filename for this stage
        """
        raise NotImplementedError("Subclasses must implement _get_log_filename()")


class RepoMigrator(BaseMigrator):
    """
    High-level coordinator for the Bitbucket to GitHub migration process.

    This class orchestrates the entire migration workflow, including setup,
    data fetching, migration execution, and report generation. It delegates
    specific tasks to specialized migrators while maintaining overall control.
    """

    def _get_subcommand(self) -> str:
        """Return Stage 1 subcommand based on dry-run mode."""
        return "migrate" if not self.dry_run else "dry-run"
        
    def _get_log_filename(self) -> str:
        """Return Stage 1 log filename based on dry-run mode."""
        return "migration_log.txt"
    
    def __init__(self, config: MigrationConfig, dry_run: bool = False, log_level: str = 'INFO'):
        """
        Initialize the MigrationOrchestrator.

        Args:
            config: Complete migration configuration
            dry_run: Run migration in dry-run mode
            logger: Optional logger instance
        """
        super().__init__(config, dry_run, log_level)
        
        self.environment = MigrationEnvironment(
            config = config, dry_run=dry_run,
            base_dir_manager=self.base_dir_manager,
            logger=self.logger,
            mode="migrate"
        )

        self.state = MigrationState()

        # Initialize components
        self._setup_components()

        # Test connections
        self._test_connections()

    def _setup_components(self) -> None:
        """Set up all migration components."""
        # Setup API clients
        self.environment.clients.bb = BitbucketClient(
            workspace=self.config.bitbucket.workspace,
            repo=self.config.bitbucket.repo,
            email=self.config.bitbucket.email,
            token=self.config.bitbucket.token,
            dry_run=self.dry_run
        )

        self.environment.clients.gh = GitHubClient(
            owner=self.config.github.owner,
            repo=self.config.github.repo,
            token=self.config.github.token,
            dry_run=self.dry_run
        )

        # Fetch issue type mapping for organization repositories
        api_type_mapping = {}
        try:
            repo_info = self.environment.clients.gh.get_repository_info()
            owner_type = repo_info.get('owner', {}).get('type', 'User')

            if owner_type == 'Organization':
                self.logger.info(f"Fetching issue types for organization: {self.config.github.owner}")
                api_type_mapping = self.environment.clients.gh.get_issue_types(self.config.github.owner)
                if api_type_mapping:
                    self.logger.info(f"Found {len(api_type_mapping)} issue types: {', '.join(api_type_mapping.keys())}")
                else:
                    self.logger.info("No issue types configured for this organization")
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"Could not fetch issue types: {e}")
        except Exception as e:
            self.logger.warning(f"Unexpected error fetching issue types: {e}")

        # Build combined type mapping using config and API-fetched types
        type_mapping = self.state.mappings.issue_types
        
        # Create case-insensitive lookup for GitHub types
        api_type_mapping_lower = {k.lower(): (k, v) for k, v in api_type_mapping.items()}
        
        # Apply user-configured mappings first
        if self.config.issue_type_mapping:
            self.logger.info(f"Applying configurable issue type mappings: {list(self.config.issue_type_mapping.keys())}")
            for bb_type, gh_type in self.config.issue_type_mapping.items():
                bb_type_lower = bb_type.lower()
                gh_type_lower = gh_type.lower()
                if gh_type_lower in api_type_mapping_lower:
                    original_gh_type, gh_id = api_type_mapping_lower[gh_type_lower]
                    type_mapping[bb_type_lower] = {
                        'id': gh_id,
                        'name': original_gh_type,
                        'configured_name': gh_type
                    }
                    self.logger.info(f"  Mapped '{bb_type}' -> '{gh_type}' (ID: {gh_id})")
                else:
                    self.logger.warning(f"  GitHub issue type '{gh_type}' not found for Bitbucket type '{bb_type}'. Skipping mapping.")
        
        # Auto-map Bitbucket types that exactly match GitHub types (case-insensitive)
        # This covers common types like "bug" -> "Bug", "task" -> "Task", etc.
        configured_bb_types = [k.lower() for k in self.config.issue_type_mapping.keys()]
        for gh_type, gh_id in api_type_mapping.items():
            gh_lower = gh_type.lower()
            if gh_lower not in configured_bb_types:
                # Map Bitbucket type to GitHub type if names match (case-insensitive)
                type_mapping[gh_lower] = {
                    'id': gh_id,
                    'name': gh_type,
                    'configured_name': None
                }
                self.logger.info(f"  Auto-mapped '{gh_lower}' -> '{gh_type}' (ID: {gh_id})")
        
        # Setup services
        self.environment.services.register(
            'user_mapper',
            UserMapper(self.environment, self.state)
            # UserMapper(self.config.user_mapping, self.environment.clients.bb)
        )
        
        # Initialize cross-repo mapping store
        self.environment.services.register(
            'cross_repo_mapping_store',
            CrossRepoMappingStore(self.environment, self.state)
        )
        # self.state.mappings.cross_repo = self.environment.services.get('cross_repo_mapping_store').load()
        

        self.environment.services.register(
            'link_rewriter',
            LinkRewriter(self.environment, self.state)
        )
        
        self.environment.services.register(
            'attachment_handler',
            AttachmentHandler(self.environment, self.state)
        )
        
        self.environment.services.register(
            'formatter_factory',
            FormatterFactory(self.environment, self.state)
        )
        
        # Setup migrators
        self.issue_migrator = IssueMigrator(self.environment, self.state)
        
        self.pr_migrator = PullRequestMigrator(self.environment, self.state)
        
        self.report_generator = ReportGenerator(self.environment, self.state)


    def run_migration(self) -> None:
        """
        Run the complete migration process.

        This method coordinates the entire migration workflow:
        1. Setup and validation
        2. Data fetching
        3. Migration execution
        4. Report generation
        """
        try:
            self.logger.info("="*80)
            self.logger.info("🔄 STARTING BITBUCKET TO GITHUB MIGRATION")
            self.logger.info("="*80)

            if self.dry_run:
                self.logger.info("🔍 DRY RUN MODE ENABLED")
                self.logger.info("This is a simulation - NO changes will be made to GitHub")
                self.logger.info("")

            # Step 1: Setup and validation
            self._setup_and_validate()

            # Step 2: Fetch data
            bb_issues = self._fetch_issues() if not self.config.options.skip_issues else []
            bb_prs = self._fetch_prs() if not self.config.options.skip_prs else []

            # Step 3: Build user mappings
            self._build_user_mappings(bb_issues, bb_prs)

            # Step 4: Create milestones
            if not self.config.options.skip_milestones: self._create_milestones()

            # Step 6: Perform migration (two-pass for link rewriting)
            if not self.config.options.skip_issues:
                # First pass: create issues without link rewriting
                issue_records, self.state.type_stats, self.state.type_fallbacks = self.issue_migrator.migrate_issues(bb_issues, self.config.options.open_issues_only)
            else:
                issue_records = []

            if not self.config.options.skip_prs:
                # First pass: create PRs without link rewriting
                pr_records = self.pr_migrator.migrate_pull_requests(
                    bb_prs, self.config.options.skip_pr_as_issue, self.config.options.open_prs_only
                )


            # Second pass: update issue content with rewritten links (after PR mappings are available)
            if not self.config.options.skip_issues:
                for bb_issue in bb_issues:
                    gh_number = self.state.mappings.issues.get(bb_issue['id'])
                    if gh_number:
                        self.issue_migrator.update_issue_content(bb_issue, gh_number)
                        self.issue_migrator.update_issue_comments(bb_issue, gh_number)

            # Second pass: update PR content with rewritten links
            if not self.config.options.skip_prs:
                for bb_pr in bb_prs:
                    gh_number = self.state.mappings.prs.get(bb_pr['id'])
                    if gh_number:
                        # Find the corresponding pr_record to determine if it's a PR or issue
                        pr_record = next((r for r in pr_records if r['bb_number'] == bb_pr['id']), None)
                        if pr_record:
                            as_pr = pr_record['gh_type'] == 'PR'
                            self.pr_migrator.update_pr_content(bb_pr, gh_number, as_pr)
                            self.pr_migrator.update_pr_comments(bb_pr, gh_number, as_pr)

            # Step 7: Generate reports
            self._generate_reports()

            # Step 8: Print summary
            self._print_summary()

            # Step 9: Save cross-repo mappings for future migrations
            self._save_cross_repo_mappings()

            # Step 10: Post-migration instructions
            self._print_post_migration_instructions()

            self.logger.info("="*80)
            self.logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY")
            self.logger.info("="*80)

        except KeyboardInterrupt:
            self.logger.info("Migration interrupted by user")
            self._save_partial_mapping()
            raise
        except (ConfigurationError, AuthenticationError, NetworkError, ValidationError, MigrationError) as e:
            self.logger.error(f"MIGRATION FAILED: {e}")
            self._save_partial_mapping()
            raise
        except Exception as e:
            self.logger.error(f"UNEXPECTED ERROR: {e}")
            self._save_partial_mapping()
            raise

    def _setup_and_validate(self) -> None:
        """Setup and validate the migration environment."""
        self.logger.info("Setting up migration environment...")

        # Check repository type and fetch issue types
        self.logger.info("Checking repository type and issue type support...")
        self._check_repository_type()

    def _check_repository_type(self) -> None:
        """Check if repository is organization or personal and fetch issue types."""
        try:
            repo_info = self.environment.clients.gh.get_repository_info()
            owner_type = repo_info.get('owner', {}).get('type', 'User')

            if owner_type == 'Organization':
                self.logger.info(f"  ✓ Repository belongs to organization: {self.config.github.owner}")
                # Fetch organization issue types
                type_mapping = self.environment.clients.gh.get_issue_types(self.config.github.owner)
                if type_mapping:
                    self.logger.info(f"  ✓ Found {len(type_mapping)} organization issue types: {', '.join(type_mapping.keys())}")
                else:
                    self.logger.info(f"  ℹ No issue types configured for organization")
            else:
                self.logger.info(f"  ✓ Repository is personal: {self.config.github.owner}")

        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"  Warning: Could not check repository type: {e}")

    def _fetch_issues(self) -> List[Dict[str, Any]]:
        """Fetch issues from Bitbucket."""
        self.logger.info("Fetching Bitbucket issues...")
        try:
            issues = self.environment.clients.bb.get_issues()
            self.logger.info(f"  Found {len(issues)} issues")
            return issues
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"  Warning: Could not fetch Bitbucket issues: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"  Warning: Unexpected error fetching issues: {e}")
            return []

    def _fetch_prs(self) -> List[Dict[str, Any]]:
        """Fetch pull requests from Bitbucket."""
        self.logger.info("Fetching Bitbucket pull requests...")
        try:
            prs = self.environment.clients.bb.get_pull_requests()
            self.logger.info(f"  Found {len(prs)} pull requests")
            return prs
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"  Warning: Could not fetch Bitbucket pull requests: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"  Warning: Unexpected error fetching pull requests: {e}")
            return []

    def _build_user_mappings(self, bb_issues: List[Dict[str, Any]], bb_prs: List[Dict[str, Any]]) -> None:
        """Build user mappings from fetched data."""
        self.logger.info("Building user mappings...")

        user_mapper = self.environment.services.get('user_mapper')
        # Build account ID mappings from the fetched data
        user_mapper.build_account_id_mappings(bb_issues, bb_prs)

        # Scan comments for additional account IDs
        user_mapper.scan_comments_for_account_ids(bb_issues, bb_prs)

        # Lookup any unresolved account IDs via API
        if user_mapper.data.account_id_to_display_name:
            self.logger.info("Checking for unresolved account IDs...")

            unresolved_ids = []
            for account_id in user_mapper.data.account_id_to_display_name.keys():
                if account_id not in user_mapper.data.account_id_to_username or user_mapper.data.account_id_to_username[account_id] is None:
                    unresolved_ids.append(account_id)

            if unresolved_ids:
                self.logger.info(f"  Found {len(unresolved_ids)} account ID(s) without usernames")
                self.logger.info(f"  Attempting API lookup to resolve usernames...")

                resolved_count = 0
                for account_id in unresolved_ids[:10]:  # Limit to first 10
                    user_info = user_mapper.lookup_account_id_via_api(account_id)
                    if user_info:
                        username = user_info.get('username') or user_info.get('nickname')
                        display_name = user_info.get('display_name')

                        if username:
                            user_mapper.data.account_id_to_username[account_id] = username
                            resolved_count += 1
                            self.logger.info(f"    ✓ Resolved {account_id[:40]}... → {username}")
                        if display_name and account_id not in user_mapper.data.account_id_to_display_name:
                            user_mapper.data.account_id_to_display_name[account_id] = display_name

                if resolved_count > 0:
                    self.logger.info(f"  ✓ Resolved {resolved_count} account ID(s) to usernames")

    def _create_milestones(self) -> Dict[str, Dict[str, Any]]:
        """Fetch Bitbucket milestones and create them on GitHub.
        
        Returns:
            milestone_lookup: Dict mapping milestone name to GitHub milestone data
                             including 'number', 'title', 'state', etc.
        """
        self.logger.info("Creating milestones on GitHub...")
        
        # Import MilestoneMigrator
        from ..migration.milestone_migrator import MilestoneMigrator

        # Initialize migrator
        milestone_migrator = MilestoneMigrator(
            self.environment, self.state
        )

        # Perform migration
        milestone_lookup = milestone_migrator.migrate_milestones(self.config.options.open_milestones_only)

        # Log summary
        if milestone_lookup:
            created_count = len([r for r in self.state.milestone_records if not r.get('is_duplicate', False) and r.get('gh_number')])
            duplicate_count = len([r for r in self.state.milestone_records if r.get('is_duplicate', False)])
            failed_count = len([r for r in self.state.milestone_records if not r.get('gh_number')])

            self.logger.info(f"  ✓ Milestone migration complete:")
            self.logger.info(f"    Created: {created_count}")
            if duplicate_count > 0:
                self.logger.info(f"    Reused (duplicates): {duplicate_count}")
            if failed_count > 0:
                self.logger.warning(f"    Failed: {failed_count}")
        else:
            self.logger.info("  No milestones to migrate")

        return milestone_lookup

    def _test_connections(self) -> None:
        """Test both Bitbucket and GitHub connections."""
        self.logger.info("Testing API connections...")

        # Test Bitbucket connection
        try:
            self.environment.clients.bb.test_connection(detailed=True)
            self.logger.info("  ✓ Bitbucket connection successful")
        except (APIError, AuthenticationError, NetworkError) as e:
            if isinstance(e, AuthenticationError):
                self.logger.error("  ✗ ERROR: Bitbucket authentication failed")
                self.logger.error("  Please check your Bitbucket token in configuration file")
            elif isinstance(e, APIError) and e.status_code == 404:
                self.logger.error(f"  ✗ ERROR: Repository not found: {self.config.bitbucket.workspace}/{self.config.bitbucket.repo}")
                self.logger.error("  Please verify the repository exists and you have access")
            else:
                self.logger.error(f"  ✗ ERROR: {e}")
            raise

        # Test GitHub connection
        try:
            self.environment.clients.gh.test_connection(detailed=True)
            self.logger.info("  ✓ GitHub connection successful")
        except (APIError, AuthenticationError, NetworkError) as e:
            if isinstance(e, AuthenticationError):
                self.logger.error("  ✗ ERROR: GitHub authentication failed")
                self.logger.error("  Please check your GitHub token in configuration file")
            elif isinstance(e, APIError) and e.status_code == 404:
                self.logger.error(f"  ✗ ERROR: Repository not found: {self.config.github.owner}/{self.config.github.repo}")
                self.logger.error("  Please verify the repository exists and you have access")
            else:
                self.logger.error(f"  ✗ ERROR: {e}")
            raise

    def _generate_reports(self) -> None:
        """Generate migration reports."""
        self.logger.info("Generating migration reports...")

        # Save mapping
        self.report_generator.save_mapping()

        # Generate comprehensive migration report
        self.report_generator.generate_migration_report(
            report_filename=f"migration_report{'_dry_run' if self.dry_run else ''}.md"
        )

    def _print_summary(self) -> None:
        """Print migration summary."""
        self.report_generator.print_summary()

    def _print_post_migration_instructions(self) -> None:
        """Print post-migration instructions."""
        attachment_handler = self.environment.services.get('attachment_handler')
        if not self.dry_run and len(attachment_handler.data.attachments) > 0:
            self.logger.info("="*80)
            self.logger.info("POST-MIGRATION: Attachment Handling")
            self.logger.info("="*80)
            self.logger.info(f"{len(attachment_handler.data.attachments)} attachments were downloaded to: {attachment_handler.data.attachment_dir}")

            self.logger.info("To upload attachments to GitHub issues:")
            self.logger.info("1. Navigate to the issue on GitHub")
            self.logger.info("2. Click the comment box")
            self.logger.info(f"3. Drag and drop the file from {attachment_handler.data.attachment_dir}/")
            self.logger.info("4. The file will be uploaded and embedded")
            self.logger.info("Example:")
            self.logger.info(f"  - Open: https://github.com/{self.config.github.owner}/{self.config.github.repo}/issues/1")
            self.logger.info(f"  - Drag: {attachment_handler.data.attachment_dir}/screenshot.png")
            self.logger.info("  - File will appear in comment with URL")
            self.logger.info("Note: Comments already note which attachments belonged to each issue.")

            self.logger.info(f"Keep {attachment_handler.data.attachment_dir}/ folder as backup until verified.")
            self.logger.info("="*80)

        # Print PR migration explanation
        if not self.dry_run and not self.config.options.skip_prs:
            self.logger.info("="*80)
            self.logger.info("ABOUT PR MIGRATION")
            self.logger.info("="*80)
            self.logger.info("PR Migration Strategy:")
            self.logger.info(f"  - OPEN PRs with existing branches → GitHub PRs ({self.state.pr_migration_stats['prs_as_prs']} migrated)")
            self.logger.info(f"  - All other PRs → GitHub Issues ({self.state.pr_migration_stats['prs_as_issues']} migrated)")
            self.logger.info("Why merged PRs become issues:")
            self.logger.info("  - Prevents re-merging already-merged code")
            self.logger.info("  - Git history already contains all merged changes")
            self.logger.info("  - Full metadata preserved in issue description")
            self.logger.info("  - Safer approach - no risk of repository corruption")
            self.logger.info("Merged PRs are labeled 'pr-merged' so you can easily identify them.")
            self.logger.info("="*80)

    def _save_cross_repo_mappings(self) -> None:
        """Save cross-repository mappings for future migrations."""
        cross_repo_mappings_file = self.base_dir_manager.get_mappings_path(dry_run=self.dry_run)

        try:
            mapping_store = self.environment.services.get('cross_repo_mapping_store')
            mapping_store.save(
                getattr(self.config.bitbucket, 'workspace', None), getattr(self.config.bitbucket, 'repo', None),
                self.config.github.owner, self.config.github.repo,
                self.state.mappings.issues, self.state.mappings.prs,
                self.state.mappings.issue_comments, self.state.mappings.pr_comments
            )
            self.logger.info(f"Saved cross-repository mappings to {cross_repo_mappings_file}")
        except Exception as e:
            self.logger.warning(f"Could not save cross-repository mappings: {e}")


    def _save_partial_mapping(self) -> None:
        """Save partial mapping in case of interruption."""
        try:
            self.report_generator.save_mapping(filename='migration_mapping_partial.json')
        except Exception as e:
            self.logger.warning(f"Could not save partial mapping: {e}")


class CrossLinkMigrator(BaseMigrator):

    def _get_subcommand(self) -> str:
        """Return Stage 1 subcommand based on dry-run mode."""
        return "cross-link" if not self.dry_run else "cross-link_dry-run"
        
    def _get_log_filename(self) -> str:
        """Return Stage 1 log filename based on dry-run mode."""
        return "migration_log.txt"
    
    def __init__(self, config: MigrationConfig, dry_run: bool = False, log_level: str = 'INFO'):
        super().__init__(config, dry_run, log_level)

        self.environment = MigrationEnvironment(
            config = config, dry_run=dry_run,
            base_dir_manager=self.base_dir_manager,
            logger=self.logger,
            mode="cross-link"
        )

        # self.services = ServiceLocator()
        self.state = MigrationState()

        # Initialize cross-repo mapping store for cross-link processing
        # Use specialized store that automatically gets dry_run from environment
        from ..services.cross_repo_mapping_store import CrossLinkMappingStore
        self.environment.services.register(
            'cross_repo_mapping_store',
            CrossLinkMappingStore(self.environment, self.state)
        )

        self.environment.clients.gh = GitHubClient(
            owner=self.config.github.owner,
            repo=self.config.github.repo,
            token=self.config.github.token,
            dry_run=self.dry_run
        )

        self.environment.services.register(
            'link_rewriter',
            LinkRewriter(self.environment, self.state, handlers=[CrossRepoLinkHandler])
        )

        self.cross_link_updater = CrossLinkUpdater(self.environment, self.state)
        
        self.report_generator = ReportGenerator(self.environment, self.state)

    def run_migration(self):

        try:
            self.logger.info("=" * 80)
            self.logger.info("Updating cross-repository links")
            self.logger.info("=" * 80)

            # Reload mappings to get latest from all migrated repos
            _, repo_mappings = self.environment.services.get('cross_repo_mapping_store').load()
            
            self.logger.info(f"Loaded mappings for {len(repo_mappings)} repositories")

            if not repo_mappings:
                self.logger.warning("No cross-repo mappings available. Nothing to update.")
                return
            else:
                self.logger.info(f"Found cross-repo mappings for {len(repo_mappings)} repositories:")
                for key in repo_mappings.keys():
                    self.logger.info(f"  - {key}")
            
            if not repo_mappings:
                self.logger.warning("No cross-repo mappings available. Nothing to update.")
                return
            
            # Load cross-repo link index for current repository
            repo_key = f"{self.config.bitbucket.workspace}/{self.config.bitbucket.repo}"
            cross_repo_links = repo_mappings.get(repo_key, {}).get('cross_repo_links')

            if not cross_repo_links:
                self.logger.warning(f"No cross-repo links found for {repo_key}. "
                                "This repository may not have been processed in Stage 1, "
                                "or the index was not saved properly.")
                return

            n_issues = len(cross_repo_links.get('issues', []))
            n_issues_with_comments = len(cross_repo_links.get('issue_comments', {}))
            n_issue_comments = sum([len(v) for v in cross_repo_links.get('issue_comments', {}).values()])
            n_prs = len(cross_repo_links.get('prs', []))
            n_prs_with_comments = len(cross_repo_links.get('pr_comments', {}))
            n_pr_comments = sum([len(v) for v in cross_repo_links.get('pr_comments', {}).values()])

            total_items = n_issues + n_issue_comments + n_prs + n_pr_comments
            
            if total_items == 0:
                self.logger.info("No items with cross-repo links found for processing.")
                return

            self.logger.info(f"Found {total_items} items needing cross-repo link updates:")
            self.logger.info(f"  Issue descriptions: {n_issues}")
            self.logger.info(f"  Issue comments: {n_issue_comments} comments in {n_issues_with_comments} issues")
            self.logger.info(f"  PR descriptions: {n_prs}")
            self.logger.info(f"  PR comments: {n_pr_comments} comments in {n_prs_with_comments} PRs")

            self.logger.info(f"  Total cross-repo links: {cross_repo_links.get('total_links', 0)}")

            # Perform the updates
            stats = self.cross_link_updater.update_cross_repo_links()

            # Log completion
            self.logger.info("Updating cross-repo links complete")

            self.report_generator.generate_cross_link_report()

        except KeyboardInterrupt:
            self.logger.info("Migration interrupted by user")
            raise
        except (ConfigurationError, AuthenticationError, NetworkError, ValidationError, MigrationError) as e:
            self.logger.error(f"MIGRATION FAILED: {e}")
            raise
        except Exception as e:
            self.logger.error(f"UNEXPECTED ERROR: {e}")
            raise