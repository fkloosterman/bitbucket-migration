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
from ..clients.github_cli_client import GitHubCliClient
from ..services.user_mapper import UserMapper
from ..services.link_rewriter import LinkRewriter
from ..services.attachment_handler import AttachmentHandler
from ..formatters.formatter_factory import FormatterFactory
from ..config.migration_config import MigrationConfig
from ..migration.issue_migrator import IssueMigrator
from ..migration.pr_migrator import PullRequestMigrator
from ..migration.report_generator import ReportGenerator
from ..exceptions import MigrationError, APIError, AuthenticationError, NetworkError, ConfigurationError, ValidationError
from ..utils.logging_config import MigrationLogger


class MigrationOrchestrator:
    """
    High-level coordinator for the Bitbucket to GitHub migration process.

    This class orchestrates the entire migration workflow, including setup,
    data fetching, migration execution, and report generation. It delegates
    specific tasks to specialized migrators while maintaining overall control.
    """

    def __init__(self, config: MigrationConfig, logger: Optional[MigrationLogger] = None):
        """
        Initialize the MigrationOrchestrator.

        Args:
            config: Complete migration configuration
            logger: Optional logger instance
        """
        self.config = config

        # Setup logger
        if logger:
            self.logger = logger
        else:
            log_file = f"migration_{'dry_run_' if self.config.dry_run else ''}log.txt"
            self.logger = MigrationLogger(log_level="INFO", log_file=log_file, dry_run=self.config.dry_run)

        # Track overall progress
        self.issue_mapping = {}
        self.pr_mapping = {}
        self.stats = {
            'prs_as_prs': 0,
            'prs_as_issues': 0,
            'pr_branch_missing': 0,
            'pr_merged_as_issue': 0,
        }

        # Initialize components
        self._setup_components()

    def _setup_components(self) -> None:
        """Set up all migration components."""
        # Setup API clients
        self.bb_client = BitbucketClient(
            workspace=self.config.bitbucket.workspace,
            repo=self.config.bitbucket.repo,
            email=self.config.bitbucket.email,
            token=self.config.bitbucket.token,
            dry_run=self.config.dry_run
        )

        self.gh_client = GitHubClient(
            owner=self.config.github.owner,
            repo=self.config.github.repo,
            token=self.config.github.token,
            dry_run=self.config.dry_run
        )

        # Setup GitHub CLI client if needed
        self.gh_cli_client = None
        if self.config.use_gh_cli:
            self.gh_cli_client = GitHubCliClient(
                token=self.config.github.token,
                dry_run=self.config.dry_run
            )

        # Fetch issue type mapping for organization repositories
        type_mapping = {}
        try:
            repo_info = self.gh_client.get_repository_info()
            owner_type = repo_info.get('owner', {}).get('type', 'User')

            if owner_type == 'Organization':
                self.logger.info(f"Fetching issue types for organization: {self.config.github.owner}")
                type_mapping = self.gh_client.get_issue_types(self.config.github.owner)
                if type_mapping:
                    self.logger.info(f"Found {len(type_mapping)} issue types: {', '.join(type_mapping.keys())}")
                else:
                    self.logger.info("No issue types configured for this organization")
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"Could not fetch issue types: {e}")
        except Exception as e:
            self.logger.warning(f"Unexpected error fetching issue types: {e}")

        # Setup services
        self.user_mapper = UserMapper(self.config.user_mapping, self.bb_client)
        self.link_rewriter = LinkRewriter(
            self.issue_mapping, self.pr_mapping, self.config.repository_mapping or {},
            self.config.bitbucket.workspace, self.config.bitbucket.repo,
            self.config.github.owner, self.config.github.repo, self.user_mapper
        )
        self.attachment_handler = AttachmentHandler(
            Path('attachments_temp'), self.gh_cli_client, self.config.dry_run
        )
        self.formatter_factory = FormatterFactory(
            self.user_mapper, self.link_rewriter, self.attachment_handler
        )

        # Setup migrators
        self.issue_migrator = IssueMigrator(
            self.bb_client, self.gh_client, self.user_mapper, self.link_rewriter,
            self.attachment_handler, self.formatter_factory, self.logger, type_mapping
        )
        self.pr_migrator = PullRequestMigrator(
            self.bb_client, self.gh_client, self.user_mapper, self.link_rewriter,
            self.attachment_handler, self.formatter_factory, self.logger
        )
        self.report_generator = ReportGenerator(self.logger)

    async def run_migration_async(self) -> None:
        """
        Run the complete migration process asynchronously.

        Note: This is a placeholder for async implementation.
        For now, it runs synchronously but can be extended for concurrency.
        """
        await self._run_migration()

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

            if self.config.dry_run:
                self.logger.info("🔍 DRY RUN MODE ENABLED")
                self.logger.info("This is a simulation - NO changes will be made to GitHub")
                self.logger.info("")

            # Step 1: Setup and validation
            self._setup_and_validate()

            # Step 2: Fetch data
            bb_issues = self._fetch_issues() if not self.config.skip_issues else []
            bb_prs = self._fetch_prs() if not self.config.skip_prs else []

            # Step 3: Build user mappings
            self._build_user_mappings(bb_issues, bb_prs)

            # Step 4: Create milestones
            milestone_lookup = self._create_milestones()

            # Step 5: Test connections
            self._test_connections()

            # Step 6: Perform migration
            if not self.config.skip_issues:
                issue_records = self.issue_migrator.migrate_issues(bb_issues, milestone_lookup)
                self.issue_mapping = self.issue_migrator.issue_mapping

            if not self.config.skip_prs:
                pr_records = self.pr_migrator.migrate_pull_requests(
                    bb_prs, milestone_lookup, self.config.skip_pr_as_issue
                )
                self.pr_mapping = self.pr_migrator.pr_mapping
                self.stats.update(self.pr_migrator.stats)

            # Step 7: Generate reports
            self._generate_reports()

            # Step 8: Print summary
            self._print_summary()

            # Step 9: Post-migration instructions
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

        # Check and setup GitHub CLI if requested
        if self.config.use_gh_cli and not self.config.dry_run:
            if not self.gh_cli_client.is_available():
                self.logger.error("--use-gh-cli specified but GitHub CLI is not available")
                self.logger.error("Please install gh CLI: https://cli.github.com/")
                raise ConfigurationError("GitHub CLI not available. Please install from https://cli.github.com/")

            if not self.gh_cli_client.is_authenticated():
                self.logger.info("GitHub CLI is not authenticated. Attempting automatic authentication...")
                if not self.gh_cli_client.authenticate():
                    self.logger.error("Failed to authenticate GitHub CLI automatically")
                    self.logger.error("Please run 'gh auth login' manually or use test-auth command")
                    raise ConfigurationError("GitHub CLI authentication failed. Please authenticate manually.")
                else:
                    self.logger.info("GitHub CLI authenticated successfully")

        # Check repository type and fetch issue types
        self.logger.info("Checking repository type and issue type support...")
        self._check_repository_type()

    def _check_repository_type(self) -> None:
        """Check if repository is organization or personal and fetch issue types."""
        try:
            repo_info = self.gh_client.get_repository_info()
            owner_type = repo_info.get('owner', {}).get('type', 'User')

            if owner_type == 'Organization':
                self.logger.info(f"  ✓ Repository belongs to organization: {self.config.github.owner}")
                # Fetch organization issue types
                type_mapping = self.gh_client.get_issue_types(self.config.github.owner)
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
            issues = self.bb_client.get_issues()
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
            prs = self.bb_client.get_pull_requests()
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

        # Build account ID mappings from the fetched data
        self.user_mapper.build_account_id_mappings(bb_issues, bb_prs)

        # Scan comments for additional account IDs
        self.user_mapper.scan_comments_for_account_ids(bb_issues, bb_prs)

        # Lookup any unresolved account IDs via API
        if self.user_mapper.account_id_to_display_name:
            self.logger.info("Checking for unresolved account IDs...")

            unresolved_ids = []
            for account_id in self.user_mapper.account_id_to_display_name.keys():
                if account_id not in self.user_mapper.account_id_to_username or self.user_mapper.account_id_to_username[account_id] is None:
                    unresolved_ids.append(account_id)

            if unresolved_ids:
                self.logger.info(f"  Found {len(unresolved_ids)} account ID(s) without usernames")
                self.logger.info(f"  Attempting API lookup to resolve usernames...")

                resolved_count = 0
                for account_id in unresolved_ids[:10]:  # Limit to first 10
                    user_info = self.user_mapper.lookup_account_id_via_api(account_id)
                    if user_info:
                        username = user_info.get('username') or user_info.get('nickname')
                        display_name = user_info.get('display_name')

                        if username:
                            self.user_mapper.account_id_to_username[account_id] = username
                            resolved_count += 1
                            self.logger.info(f"    ✓ Resolved {account_id[:40]}... → {username}")
                        if display_name and account_id not in self.user_mapper.account_id_to_display_name:
                            self.user_mapper.account_id_to_display_name[account_id] = display_name

                if resolved_count > 0:
                    self.logger.info(f"  ✓ Resolved {resolved_count} account ID(s) to usernames")

    def _create_milestones(self) -> Dict[str, Dict[str, Any]]:
        """Fetch and create milestones on GitHub."""
        self.logger.info("Creating milestones on GitHub...")

        bb_milestones = self.bb_client.get_milestones()
        milestone_lookup = {}

        if bb_milestones:
            for milestone in bb_milestones:
                name = milestone.get('name')
                if name:
                    milestone_lookup[name] = milestone
                    # Pre-create milestone (simplified - in real implementation, use a MilestoneMigrator)
                    try:
                        # This would be handled by a separate MilestoneMigrator in full implementation
                        self.logger.info(f"  Would create milestone: {name}")
                    except Exception as e:
                        self.logger.warning(f"  Warning: Could not create milestone {name}: {e}")

        return milestone_lookup

    def _test_connections(self) -> None:
        """Test both Bitbucket and GitHub connections."""
        self.logger.info("Testing API connections...")

        # Test Bitbucket connection
        try:
            self.bb_client.test_connection(detailed=True)
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
            self.gh_client.test_connection(detailed=True)
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

    def _collect_user_mapping_data(self) -> List[Dict[str, Any]]:
        """Collect user mapping data for the report."""
        from datetime import datetime
        data = []
        for bb_user, gh_user in self.config.user_mapping.items():
            success = gh_user is not None and gh_user != ""
            if isinstance(gh_user, dict):
                gh_user = gh_user.get('github', 'N/A')
            reason = "Mapped successfully" if success else "No GitHub user found or invalid mapping"
            data.append({
                'bb_user': bb_user,
                'gh_user': gh_user or 'N/A',
                'success': success,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'reason': reason
            })
        return data

    def _collect_attachment_data(self) -> List[Dict[str, Any]]:
        """Collect attachment data for the report."""
        data = []
        for attachment in self.attachment_handler.attachments:
            file_path = attachment.get('filepath', 'N/A')
            filename = attachment.get('filename', 'N/A')
            # Assume size and type need to be calculated or added
            size = "Unknown"  # Placeholder
            file_type = "Unknown"  # Placeholder
            uploaded = False  # Placeholder, need to track in attachment_handler
            url = "-"  # Placeholder
            error = "-"  # Placeholder
            instructions = "Drag and drop to GitHub issue" if not uploaded else "-"
            data.append({
                'file_path': file_path,
                'size': size,
                'type': file_type,
                'uploaded': uploaded,
                'url': url,
                'error': error,
                'instructions': instructions
            })
        return data

    def _collect_link_data(self) -> Dict[str, Any]:
        """Collect link rewriting data for the report."""
        # Placeholder: Need to collect from link_rewriter
        total_processed = 0  # Placeholder
        successful = 0  # Placeholder
        failed = 0  # Placeholder
        details = []  # Placeholder
        return {
            'total_processed': total_processed,
            'successful': successful,
            'failed': failed,
            'details': details
        }

    def _generate_reports(self) -> None:
        """Generate migration reports."""
        self.logger.info("Generating migration reports...")

        # Combine records from migrators
        issue_records = self.issue_migrator.issue_records
        pr_records = self.pr_migrator.pr_records

        # Collect data from services
        user_mapping_data = self._collect_user_mapping_data()
        attachment_data = self._collect_attachment_data()
        link_data = self._collect_link_data()

        # Save mapping
        self.report_generator.save_mapping(
            self.issue_mapping, self.pr_mapping,
            self.config.bitbucket.workspace, self.config.bitbucket.repo,
            self.config.github.owner, self.config.github.repo,
            self.stats
        )

        # Generate comprehensive migration report
        if self.config.dry_run:
            self.report_generator.generate_migration_report(
                issue_records, pr_records, self.stats,
                self.config.bitbucket.workspace, self.config.bitbucket.repo,
                self.config.github.owner, self.config.github.repo,
                dry_run=True, report_filename="migration_report_dry_run.md",
                user_mapping_data=user_mapping_data,
                attachment_data=attachment_data,
                link_data=link_data
            )
        else:
            self.report_generator.generate_migration_report(
                issue_records, pr_records, self.stats,
                self.config.bitbucket.workspace, self.config.bitbucket.repo,
                self.config.github.owner, self.config.github.repo,
                dry_run=False,
                user_mapping_data=user_mapping_data,
                attachment_data=attachment_data,
                link_data=link_data
            )

    def _print_summary(self) -> None:
        """Print migration summary."""
        self.report_generator.print_summary(
            self.issue_mapping, self.pr_mapping, self.stats,
            self.attachment_handler.attachments, self.attachment_handler,
            self.config.dry_run
        )

    def _print_post_migration_instructions(self) -> None:
        """Print post-migration instructions."""
        if not self.config.dry_run and len(self.attachment_handler.attachments) > 0:
            self.logger.info("="*80)
            self.logger.info("POST-MIGRATION: Attachment Handling")
            self.logger.info("="*80)
            self.logger.info(f"{len(self.attachment_handler.attachments)} attachments were downloaded to: {self.attachment_handler.attachment_dir}")

            if self.config.use_gh_cli:
                uploaded_count = len([a for a in self.attachment_handler.attachments if a.get('uploaded', False)])
                self.logger.info(f"✓ Attachments were automatically uploaded using GitHub CLI")
                self.logger.info(f"  Successfully uploaded: {uploaded_count}/{len(self.attachment_handler.attachments)}")

                failed_count = len(self.attachment_handler.attachments) - uploaded_count
                if failed_count > 0:
                    self.logger.warning(f"⚠️  {failed_count} attachment(s) failed to upload")
                    self.logger.warning("  These need manual upload via drag-and-drop")
                    self.logger.warning("  Check migration.log for details")

                self.logger.info(f"Note: Inline images in comments still need manual upload")
                self.logger.info("      (gh CLI limitation - can't attach to comment edits)")
            else:
                self.logger.info("To upload attachments to GitHub issues:")
                self.logger.info("1. Navigate to the issue on GitHub")
                self.logger.info("2. Click the comment box")
                self.logger.info(f"3. Drag and drop the file from {self.attachment_handler.attachment_dir}/")
                self.logger.info("4. The file will be uploaded and embedded")
                self.logger.info("Example:")
                self.logger.info(f"  - Open: https://github.com/{self.config.github.owner}/{self.config.github.repo}/issues/1")
                self.logger.info(f"  - Drag: {self.attachment_handler.attachment_dir}/screenshot.png")
                self.logger.info("  - File will appear in comment with URL")
                self.logger.info("Note: Comments already note which attachments belonged to each issue.")
                self.logger.info("Tip: Use --use-gh-cli flag to automatically upload attachments")

            self.logger.info(f"Keep {self.attachment_handler.attachment_dir}/ folder as backup until verified.")
            self.logger.info("="*80)

        # Print PR migration explanation
        if not self.config.dry_run and not self.config.skip_prs:
            self.logger.info("="*80)
            self.logger.info("ABOUT PR MIGRATION")
            self.logger.info("="*80)
            self.logger.info("PR Migration Strategy:")
            self.logger.info(f"  - OPEN PRs with existing branches → GitHub PRs ({self.stats['prs_as_prs']} migrated)")
            self.logger.info(f"  - All other PRs → GitHub Issues ({self.stats['prs_as_issues']} migrated)")
            self.logger.info("Why merged PRs become issues:")
            self.logger.info("  - Prevents re-merging already-merged code")
            self.logger.info("  - Git history already contains all merged changes")
            self.logger.info("  - Full metadata preserved in issue description")
            self.logger.info("  - Safer approach - no risk of repository corruption")
            self.logger.info("Merged PRs are labeled 'pr-merged' so you can easily identify them.")
            self.logger.info("="*80)


    def _save_partial_mapping(self) -> None:
        """Save partial mapping in case of interruption."""
        try:
            self.report_generator.save_mapping(
                self.issue_mapping, self.pr_mapping,
                self.config.bitbucket.workspace, self.config.bitbucket.repo,
                self.config.github.owner, self.config.github.repo,
                self.stats, 'migration_mapping_partial.json'
            )
        except Exception as e:
            self.logger.warning(f"Could not save partial mapping: {e}")