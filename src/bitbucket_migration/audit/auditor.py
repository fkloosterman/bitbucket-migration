"""
Audit orchestrator for Bitbucket to GitHub migration analysis.

This module contains the AuditOrchestrator class that coordinates the audit process,
leveraging shared components from the migration system while providing audit-specific
functionality.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path

from ..clients.bitbucket_client import BitbucketClient
from ..services.user_mapper import UserMapper
from ..utils.logging_config import MigrationLogger
from ..exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    ValidationError
)
from .audit_utils import AuditUtils

from ..utils.base_dir_manager import BaseDirManager

from ..core.migration_context import MigrationState, MigrationEnvironment

class Auditor:
    """
    High-level coordinator for the Bitbucket audit process.

    This class orchestrates the audit workflow, including data fetching,
    analysis, and report generation. It leverages shared components from
    the migration system while providing audit-specific functionality.
    """

    def __init__(self, workspace: str, repo: str, email: str, token: str, log_level: str = "INFO", base_dir_manager: Optional[BaseDirManager] = None):
        """
        Initialize the AuditOrchestrator.

        Args:
            workspace: Bitbucket workspace name
            repo: Repository name
            email: User email for API authentication
            token: Bitbucket API token
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)

        Raises:
            ValidationError: If any required parameter is empty
        """


        if not workspace or not workspace.strip():
            raise ValidationError("Bitbucket workspace cannot be empty")
        if not repo or not repo.strip():
            raise ValidationError("Bitbucket repository cannot be empty")
        if not email or not email.strip():
            raise ValidationError("Bitbucket email cannot be empty")
        if not token or not token.strip():
            raise ValidationError("Bitbucket token cannot be empty")

        self.workspace = workspace
        self.repo = repo
        self.email = email
        self.token = token

        self.environment = MigrationEnvironment(
            base_dir_manager=base_dir_manager or BaseDirManager("."),
            logger=MigrationLogger(log_level=log_level),
            mode="audit"
        )

        # self.services = ServiceLocator()
        self.state = MigrationState()

        # Store BaseDirManager (create default if not provided)
        self.base_dir_manager = self.environment.base_dir_manager

        # Initialize logger
        self.logger = self.environment.logger
        
        self.logger.info("Init Auditor started")

        # Initialize shared components
        self.environment.clients.bb = BitbucketClient(workspace, repo, email, token)
        self.bb_client = self.environment.clients.bb

        self.environment.services.register(
            'user_mapper',
            UserMapper(self.environment, self.state) 
            # UserMapper(self.config.user_mapping, self.environment.clients.bb)
        )

        self.logger.info("Init Auditor user mapper")

        self.user_mapper = self.environment.services.get('user_mapper')
        self.audit_utils = AuditUtils()

        # Data storage
        self.issues: List[Dict[str, Any]] = []
        self.pull_requests: List[Dict[str, Any]] = []
        self.users: set = set()
        self.milestones: set = set()
        self.attachments: List[Dict[str, Any]] = []
        self.issue_types: set = set()

        # Analysis results
        self.gaps: Dict[str, Any] = {}
        self.pr_analysis: Dict[str, Any] = {}
        self.migration_estimates: Dict[str, Any] = {}

        # Report
        self.report = {}

        self.logger.info("Init Auditor complete")

    def run_audit(self) -> Dict[str, Any]:
        """
        Run the complete audit process.

        Returns:
            Complete audit report dictionary

        Raises:
            APIError: If API requests fail
            AuthenticationError: If authentication fails
            NetworkError: If network issues occur
        """
        self.logger.info("🔍 Starting Bitbucket repository audit...")
        self.logger.info(f"   Repository: {self.workspace}/{self.repo}")

        try:
            # Step 1: Fetch data
            self._fetch_data()

            # Step 2: Build user mappings
            self._build_user_mappings()

            # Step 3: Analyze structure and gaps
            self._analyze_structure()

            # Step 4: Generate comprehensive report
            self.report = self._generate_report()

            self.logger.info("✅ Audit completed successfully")
            return self.report

        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.error(f"❌ Audit failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected error during audit: {e}")
            raise

    def _fetch_data(self) -> None:
        """Fetch all repository data using BitbucketClient."""
        self.logger.info("📥 Fetching repository data...")

        # Fetch issues
        self.logger.info("   Fetching issues...")
        self.issues = self.bb_client.get_issues()
        self.logger.info(f"   ✓ Found {len(self.issues)} issues")

        # Collect unique issue types (kinds)
        self.logger.info("   Collecting issue types...")
        for issue in self.issues:
            if issue.get('kind'):
                self.issue_types.add(issue['kind'])
        self.logger.info(f"   ✓ Found {len(self.issue_types)} unique issue types")

        # Fetch pull requests
        self.logger.info("   Fetching pull requests...")
        self.pull_requests = self.bb_client.get_pull_requests()
        self.logger.info(f"   ✓ Found {len(self.pull_requests)} pull requests")

        # Fetch milestones
        self.logger.info("   Fetching milestones...")
        try:
            milestones = self.bb_client.get_milestones()
            self.milestones = {m.get('name') for m in milestones if m.get('name')}
            self.logger.info(f"   ✓ Found {len(self.milestones)} milestones")
        except Exception as e:
            self.logger.warning(f"   ⚠️  Could not fetch milestones: {e}")
            self.milestones = set()

        # Collect users from issues and PRs
        self._collect_users()

        # Fetch attachments
        self._fetch_attachments()

    def _collect_users(self) -> None:
        """Collect all users from issues and PRs."""
        self.logger.info("   Collecting users...")

        for issue in self.issues:
            # Reporter
            if issue.get('reporter') and issue.get('reporter', {}).get('display_name'):
                self.users.add(issue['reporter']['display_name'])
            else:
                self.users.add('Unknown (deleted user)')

            # Assignee
            if issue.get('assignee') and issue.get('assignee', {}).get('display_name'):
                self.users.add(issue['assignee']['display_name'])

        for pr in self.pull_requests:
            # Author
            if pr.get('author') and pr.get('author', {}).get('display_name'):
                self.users.add(pr['author']['display_name'])

            # Participants
            for participant in pr.get('participants', []):
                if participant.get('user') and participant['user'].get('display_name'):
                    self.users.add(participant['user']['display_name'])

            # Reviewers
            for reviewer in pr.get('reviewers', []):
                if reviewer.get('display_name'):
                    self.users.add(reviewer['display_name'])

        self.logger.info(f"   ✓ Found {len(self.users)} unique users")

    def _fetch_attachments(self) -> None:
        """Fetch all attachments from issues."""
        self.logger.info("   Fetching attachments...")

        for issue in self.issues:
            try:
                attachments = self.bb_client.get_attachments('issue', issue['id'])
                for attachment in attachments:
                    self.attachments.append({
                        'issue_number': issue['id'],
                        'type': 'issue',
                        'name': attachment.get('name'),
                        'size': attachment.get('size', 0),
                    })
            except Exception as e:
                # Attachments might not be available for some issues
                continue

        self.logger.info(f"   ✓ Found {len(self.attachments)} attachments")

    def _build_user_mappings(self) -> None:
        """Build user mappings using UserMapper."""
        self.logger.info("   Building user mappings...")

        # Build account ID mappings from fetched data
        self.user_mapper.build_account_id_mappings(self.issues, self.pull_requests)

        # Scan comments for additional account IDs
        self.user_mapper.scan_comments_for_account_ids(self.issues, self.pull_requests)

        self.logger.info(f"   ✓ Built mappings for {len(self.user_mapper.data.account_id_to_username)} account IDs")

    def _analyze_structure(self) -> None:
        """Analyze repository structure and perform audit calculations."""
        self.logger.info("   Analyzing repository structure...")

        # Analyze gaps
        issue_gaps, issue_gap_count = self.audit_utils.analyze_gaps(self.issues)
        pr_gaps, pr_gap_count = self.audit_utils.analyze_gaps(self.pull_requests)

        self.gaps = {
            'issues': {'gaps': issue_gaps, 'count': issue_gap_count},
            'pull_requests': {'gaps': pr_gaps, 'count': pr_gap_count}
        }

        # Analyze PR migratability
        self.pr_analysis = self.audit_utils.analyze_pr_migratability(self.pull_requests)

        # Calculate migration estimates
        self.migration_estimates = self.audit_utils.calculate_migration_estimates(
            self.issues, self.pull_requests, self.attachments, issue_gap_count
        )

        self.logger.info("   ✓ Analysis complete")

    def _generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive audit report."""
        self.logger.info("   Generating audit report...")

        # Get structural analysis
        structure_analysis = self.audit_utils.analyze_repository_structure(
            self.issues, self.pull_requests
        )

        # Generate migration strategy
        migration_strategy = self.audit_utils.generate_migration_strategy(self.pr_analysis)

        # Calculate attachment statistics
        total_attachment_size = sum(a['size'] for a in self.attachments)

        report = {
            'repository': {
                'workspace': self.workspace,
                'repo': self.repo,
                'audit_date': self._get_current_iso_date(),
            },
            'summary': {
                'total_issues': len(self.issues),
                'total_prs': len(self.pull_requests),
                'total_users': len(self.users),
                'total_attachments': len(self.attachments),
                'total_attachment_size_mb': round(total_attachment_size / (1024 * 1024), 2),
                'estimated_migration_time_minutes': self.migration_estimates['estimated_time_minutes']
            },
            'issues': {
                'total': len(self.issues),
                'by_state': structure_analysis['issue_states'],
                'number_range': {
                    'min': min([i['id'] for i in self.issues]) if self.issues else 0,
                    'max': max([i['id'] for i in self.issues]) if self.issues else 0,
                },
                'gaps': self.gaps['issues'],
                'date_range': structure_analysis['issue_date_range'],
                'total_comments': sum(i.get('comment_count', 0) for i in self.issues),
                'with_attachments': sum(1 for i in self.issues if i.get('attachment_count', 0) > 0),
                'types': {
                    'total': len(self.issue_types),
                    'list': sorted(list(self.issue_types)),
                },
            },
            'pull_requests': {
                'total': len(self.pull_requests),
                'by_state': structure_analysis['pr_states'],
                'number_range': {
                    'min': min([p['id'] for p in self.pull_requests]) if self.pull_requests else 0,
                    'max': max([p['id'] for p in self.pull_requests]) if self.pull_requests else 0,
                },
                'gaps': self.gaps['pull_requests'],
                'date_range': structure_analysis['pr_date_range'],
                'total_comments': sum(p.get('comment_count', 0) for p in self.pull_requests),
            },
            'attachments': {
                'total': len(self.attachments),
                'total_size_bytes': total_attachment_size,
                'total_size_mb': round(total_attachment_size / (1024 * 1024), 2),
                'by_issue': sum(1 for a in self.attachments if a['type'] == 'issue'),
            },
            'users': {
                'total_unique': len(self.users),
                'list': sorted(list(self.users)),
                'mappings': {
                    'account_id_to_username': self.user_mapper.data.account_id_to_username,
                    'username_to_account_id': {v: k for k, v in self.user_mapper.data.account_id_to_username.items()},
                },
            },
            'milestones': {
                'total': len(self.milestones),
                'list': sorted(list(self.milestones)),
            },
            'migration_analysis': {
                'gaps': self.gaps,
                'pr_migration_analysis': self.pr_analysis,
                'migration_strategy': migration_strategy,
                'estimates': self.migration_estimates
            }
        }

        return report

    def _generate_markdown_report(self, report: Dict[str, Any]) -> str:
        """Generate markdown audit report."""
        from datetime import datetime

        md = []
        md.append("# Bitbucket Repository Audit Report")
        md.append("")
        md.append(f"**Audit Date:** {report['repository']['audit_date']}")
        md.append(f"**Repository:** {report['repository']['workspace']}/{report['repository']['repo']}")
        md.append("")

        # Executive Summary
        md.append("## Executive Summary")
        md.append("")
        summary = report['summary']
        md.append(f"- **Total Issues:** {summary['total_issues']}")
        md.append(f"- **Total Pull Requests:** {summary['total_prs']}")
        md.append(f"- **Total Users:** {summary['total_users']}")
        md.append(f"- **Total Attachments:** {summary['total_attachments']} ({summary['total_attachment_size_mb']} MB)")
        md.append(f"- **Estimated Migration Time:** {summary['estimated_migration_time_minutes']} minutes")
        md.append("")

        # Table of Contents
        md.append("## Table of Contents")
        md.append("")
        md.append("1. [Issues Analysis](#issues-analysis)")
        md.append("   - [Issue Types](#issue-types)")
        md.append("2. [Pull Requests Analysis](#pull-requests-analysis)")
        md.append("3. [Attachments](#attachments)")
        md.append("4. [Users](#users)")
        md.append("5. [Milestones](#milestones)")
        md.append("6. [Migration Analysis](#migration-analysis)")
        md.append("")

        # Issues Analysis
        md.append("---")
        md.append("")
        md.append("## Issues Analysis")
        md.append("")
        issues = report['issues']
        md.extend(self._format_dict_as_markdown(issues, ''))
        md.append("")
        md.append("### Issue Types")
        md.append("")
        if issues['types']['total'] > 0:
            md.append(f"**Total Unique Issue Types:** {issues['types']['total']}")
            md.append("")
            md.append("**Issue Types Found:**")
            md.append("")
            for issue_type in issues['types']['list']:
                md.append(f"- {issue_type}")
        else:
            md.append("**No issue types found (all issues have no 'kind' specified)**")
        md.append("")

        # Pull Requests Analysis
        md.append("---")
        md.append("")
        md.append("## Pull Requests Analysis")
        md.append("")
        prs = report['pull_requests']
        md.extend(self._format_dict_as_markdown(prs, ''))
        md.append("")

        # Attachments
        md.append("---")
        md.append("")
        md.append("## Attachments")
        md.append("")
        attachments = report['attachments']
        md.extend(self._format_dict_as_markdown(attachments, ''))
        md.append("")

        # Users
        md.append("---")
        md.append("")
        md.append("## Users")
        md.append("")
        users = report['users']
        md.append(f"**Total Unique Users:** {users['total_unique']}")
        md.append("")
        md.append("### User List")
        md.append("")
        for user in users['list']:
            md.append(f"- {user}")
        md.append("")
        md.append("### User Mappings")
        md.append("")
        mappings = users['mappings']
        md.append("#### Account ID to Username")
        md.append("")
        md.extend(self._format_dict_as_markdown(mappings['account_id_to_username'], '  '))
        md.append("")
        md.append("#### Username to Account ID")
        md.append("")
        md.extend(self._format_dict_as_markdown(mappings['username_to_account_id'], '  '))
        md.append("")

        # Milestones
        md.append("---")
        md.append("")
        md.append("## Milestones")
        md.append("")
        milestones = report['milestones']
        md.append(f"**Total Milestones:** {milestones['total']}")
        md.append("")
        md.append("### Milestone List")
        md.append("")
        for milestone in milestones['list']:
            md.append(f"- {milestone}")
        md.append("")

        # Migration Analysis
        md.append("---")
        md.append("")
        md.append("## Migration Analysis")
        md.append("")
        migration = report['migration_analysis']
        md.extend(self._format_dict_as_markdown(migration, ''))
        md.append("")

        # Footer
        md.append("---")
        md.append("")
        md.append("## Notes")
        md.append("")
        md.append("- This audit report provides a comprehensive overview of the repository structure.")
        md.append("- All data is based on the current state of the Bitbucket repository.")
        md.append("- User mappings and migration estimates are included for planning purposes.")
        md.append(f"**Audit completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        md.append("")
        md.append("---")
        md.append("")
        md.append("*This report was automatically generated by the Bitbucket Audit Orchestrator.*")

        return '\n'.join(md)

    def _prettify_key(self, key: str) -> str:
        """Prettify dictionary keys by replacing underscores and capitalizing."""
        words = key.replace('_', ' ').split()
        return ' '.join(word.capitalize() for word in words)

    def _format_dict_as_markdown(self, data, prefix='') -> List[str]:
        """Convert a dict or list to nested bulleted markdown list."""
        lines = []
        if isinstance(data, dict):
            for k, v in data.items():
                pretty_k = self._prettify_key(k)
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}- {pretty_k}:")
                    lines.extend(self._format_dict_as_markdown(v, prefix + '  '))
                else:
                    lines.append(f"{prefix}- {pretty_k}: {v}")
        elif isinstance(data, (list, tuple)):
            for item in data:
                if isinstance(item, (dict, list)):
                    lines.extend(self._format_dict_as_markdown(item, prefix + '  '))
                else:
                    lines.append(f"{prefix}- {item}")
        else:
            lines.append(f"{prefix}{data}")
        return lines

    def _get_current_iso_date(self) -> str:
        """Get current date in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()

    def save_reports(self) -> None:
        """
        Save audit reports to files.

        Args:
            report: Complete audit report dictionary
            output_dir: Directory to save reports in (defaults to audit/<workspace>_<repo>)
        """
        import json

        # Use BaseDirManager to get the proper audit subdirectory
        output_path = self.base_dir_manager.ensure_subcommand_dir(
            'audit', 
            self.workspace, 
            self.repo
        )

        if self.report:
            # Save JSON report using create_file for tracking
            self.base_dir_manager.create_file(
                output_path / 'bitbucket_audit_report.json',
                self.report,
                subcommand='audit',
                workspace=self.workspace,
                repo=self.repo,
                category='report'
            )
            self.logger.info(f"📄 JSON report saved: {output_path / 'bitbucket_audit_report.json'}")

            # Save Markdown report using create_file for tracking
            markdown_content = self._generate_markdown_report(self.report)
            self.base_dir_manager.create_file(
                output_path / 'bitbucket_audit_report.md',
                markdown_content,
                subcommand='audit',
                workspace=self.workspace,
                repo=self.repo,
                category='report'
            )
            self.logger.info(f"📄 Markdown report saved: {output_path / 'bitbucket_audit_report.md'}")

        # Save detailed data using create_file for tracking
        if self.issues:
            self.base_dir_manager.create_file(
                output_path / 'bitbucket_issues_detail.json',
                self.issues,
                subcommand='audit',
                workspace=self.workspace,
                repo=self.repo,
                category='data'
            )
            self.logger.info(f"📄 Detailed issue data saved: {output_path / 'bitbucket_issues_detail.json'}")

        if self.pull_requests:
            self.base_dir_manager.create_file(
                output_path / 'bitbucket_prs_detail.json',
                self.pull_requests,
                subcommand='audit',
                workspace=self.workspace,
                repo=self.repo,
                category='data'
            )
            self.logger.info(f"📄 Detailed PR data saved: {output_path / 'bitbucket_prs_detail.json'}")

    # def generate_migration_config(self, gh_owner: str = "", gh_repo: str = "") -> Dict[str, Any]:
    #     """
    #     Generate migration configuration template.

    #     Args:
    #         gh_owner: GitHub owner/organization name
    #         gh_repo: GitHub repository name

    #     Returns:
    #         Configuration dictionary
    #     """
    #     if not gh_owner:
    #         gh_owner = "YOUR_GITHUB_USERNAME"
    #     if not gh_repo:
    #         gh_repo = self.repo

    #     # Create user mapping template
    #     user_mapping = {}
    #     for user in sorted(self.users):
    #         if user.lower() == 'unknown':
    #             user_mapping[user] = None
    #         else:
    #             user_mapping[user] = ""  # Empty string to be filled in

    #     config = {
    #         "_comment": "Bitbucket to GitHub Migration Configuration",
    #         "_instructions": {
    #             "step_1": "Set BITBUCKET_TOKEN or BITBUCKET_API_TOKEN environment variable (or in .env file) with your Bitbucket API token",
    #             "step_2": "Set GITHUB_TOKEN or GITHUB_API_TOKEN environment variable (or in .env file) with your GitHub personal access token (needs 'repo' scope)",
    #             "step_3": "Set github.owner to your GitHub username or organization",
    #             "step_4": "Set github.repo to your target repository name",
    #             "step_5": "For each user in user_mapping - set to their GitHub username if they have an account, or set to null/empty if they don't",
    #             "step_6": "Bitbucket credentials (except token) are pre-filled from audit",
    #             "step_7": "Secure or remove bitbucket_api_token.txt file to prevent token exposure",
    #             "step_8": "Run dry-run first - migrate_bitbucket_to_github dry-run --config migration_config.json",
    #             "step_9": "After dry-run succeeds, use migrate subcommand to perform actual migration"
    #         },
    #         "bitbucket": {
    #             "workspace": self.workspace,
    #             "repo": self.repo,
    #             "email": self.email
    #         },
    #         "github": {
    #             "owner": gh_owner,
    #             "repo": gh_repo
    #         },
    #         "user_mapping": user_mapping
    #     }

    #     return config

    # def save_migration_config(self, config: Dict[str, Any], filename: str = None) -> None:
    #     """
    #     Save migration configuration to file.

    #     Args:
    #         config: Configuration dictionary
    #         filename: Output filename (auto-generated if None)
    #         output_dir: Directory to save config in
    #     """
    #     import json
    #     from pathlib import Path

    #     # Auto-generate filename if not provided
    #     if filename is None:
    #         workspace = config.get('bitbucket', {}).get('workspace', 'unknown')
    #         repo = config.get('bitbucket', {}).get('repo', 'unknown')
    #         filename = f"config-{workspace}-{repo}.json"

    #     config_file = self.base_dir_manager.get_config_path(filename)
        
    #     with open(config_file, 'w') as f:
    #         json.dump(config, f, indent=2)

    #     self.logger.info(f"\n{'='*80}")
    #     self.logger.info(f"📋 Migration configuration template saved: {config_file}")
    #     self.logger.info(f"{'='*80}")
    #     self.logger.info("\nNext steps:")
    #     self.logger.info("1. Set environment variables (recommended) or edit the config file:")
    #     self.logger.info("   - Set BITBUCKET_TOKEN or BITBUCKET_API_TOKEN (env var or .env file)")
    #     self.logger.info("   - Set GITHUB_TOKEN or GITHUB_API_TOKEN (env var or .env file)")
    #     self.logger.info("   - Set github.owner to your GitHub username")
    #     self.logger.info("   - Map Bitbucket users to GitHub usernames")
    #     self.logger.info("     (use null for users without GitHub accounts)")
    #     self.logger.info("   - Secure or remove bitbucket_api_token.txt file")
    #     self.logger.info("\n2. Test with dry run:")
    #     self.logger.info(f"   migrate_bitbucket_to_github dry-run --config {config_file}")
    #     self.logger.info("\n3. Run actual migration:")
    #     self.logger.info(f"   migrate_bitbucket_to_github migrate --config {config_file}")
    #     self.logger.info(f"{'='*80}")