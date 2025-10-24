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
from ..exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    ValidationError
)
from .audit_utils import AuditUtils


class AuditOrchestrator:
    """
    High-level coordinator for the Bitbucket audit process.

    This class orchestrates the audit workflow, including data fetching,
    analysis, and report generation. It leverages shared components from
    the migration system while providing audit-specific functionality.
    """

    def __init__(self, workspace: str, repo: str, email: str, token: str):
        """
        Initialize the AuditOrchestrator.

        Args:
            workspace: Bitbucket workspace name
            repo: Repository name
            email: User email for API authentication
            token: Bitbucket API token

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

        # Initialize shared components
        self.bb_client = BitbucketClient(workspace, repo, email, token)
        self.user_mapper = UserMapper({}, self.bb_client)
        self.audit_utils = AuditUtils()

        # Data storage
        self.issues: List[Dict[str, Any]] = []
        self.pull_requests: List[Dict[str, Any]] = []
        self.users: set = set()
        self.milestones: set = set()
        self.attachments: List[Dict[str, Any]] = []

        # Analysis results
        self.gaps: Dict[str, Any] = {}
        self.pr_analysis: Dict[str, Any] = {}
        self.migration_estimates: Dict[str, Any] = {}

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
        print("🔍 Starting Bitbucket repository audit...")
        print(f"   Repository: {self.workspace}/{self.repo}")

        try:
            # Step 1: Fetch data
            self._fetch_data()

            # Step 2: Build user mappings
            self._build_user_mappings()

            # Step 3: Analyze structure and gaps
            self._analyze_structure()

            # Step 4: Generate comprehensive report
            report = self._generate_report()

            print("✅ Audit completed successfully")
            return report

        except (APIError, AuthenticationError, NetworkError) as e:
            print(f"❌ Audit failed: {e}")
            raise
        except Exception as e:
            print(f"❌ Unexpected error during audit: {e}")
            raise

    def _fetch_data(self) -> None:
        """Fetch all repository data using BitbucketClient."""
        print("📥 Fetching repository data...")

        # Fetch issues
        print("   Fetching issues...")
        self.issues = self.bb_client.get_issues()
        print(f"   ✓ Found {len(self.issues)} issues")

        # Fetch pull requests
        print("   Fetching pull requests...")
        self.pull_requests = self.bb_client.get_pull_requests()
        print(f"   ✓ Found {len(self.pull_requests)} pull requests")

        # Fetch milestones
        print("   Fetching milestones...")
        try:
            milestones = self.bb_client.get_milestones()
            self.milestones = {m.get('name') for m in milestones if m.get('name')}
            print(f"   ✓ Found {len(self.milestones)} milestones")
        except Exception as e:
            print(f"   ⚠️  Could not fetch milestones: {e}")
            self.milestones = set()

        # Collect users from issues and PRs
        self._collect_users()

        # Fetch attachments
        self._fetch_attachments()

    def _collect_users(self) -> None:
        """Collect all users from issues and PRs."""
        print("   Collecting users...")

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

        print(f"   ✓ Found {len(self.users)} unique users")

    def _fetch_attachments(self) -> None:
        """Fetch all attachments from issues."""
        print("   Fetching attachments...")

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

        print(f"   ✓ Found {len(self.attachments)} attachments")

    def _build_user_mappings(self) -> None:
        """Build user mappings using UserMapper."""
        print("   Building user mappings...")

        # Build account ID mappings from fetched data
        self.user_mapper.build_account_id_mappings(self.issues, self.pull_requests)

        # Scan comments for additional account IDs
        self.user_mapper.scan_comments_for_account_ids(self.issues, self.pull_requests)

        print(f"   ✓ Built mappings for {len(self.user_mapper.account_id_to_username)} account IDs")

    def _analyze_structure(self) -> None:
        """Analyze repository structure and perform audit calculations."""
        print("   Analyzing repository structure...")

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

        print("   ✓ Analysis complete")
    def _generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive audit report."""
        print("   Generating audit report...")
        print("   Note: Currently generating JSON report only. Markdown report generation is not implemented yet.")

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

    def _get_current_iso_date(self) -> str:
        """Get current date in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()

    def save_reports(self, report: Dict[str, Any], output_dir: str = '.') -> None:
        """
        Save audit reports to files.

        Args:
            report: Complete audit report dictionary
            output_dir: Directory to save reports in
        """
        import json
        from pathlib import Path

        output_path = Path(output_dir)

        # Save JSON report
        json_file = output_path / 'bitbucket_audit_report.json'
        with open(json_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"📄 JSON report saved: {json_file}")
        print("   Note: Only JSON report is being saved. Markdown report generation is not implemented yet.")

        # Save detailed data
        issues_file = output_path / 'bitbucket_issues_detail.json'
        with open(issues_file, 'w') as f:
            json.dump(self.issues, f, indent=2, default=str)

        prs_file = output_path / 'bitbucket_prs_detail.json'
        with open(prs_file, 'w') as f:
            json.dump(self.pull_requests, f, indent=2, default=str)

        print(f"📄 Detailed data saved: {issues_file}, {prs_file}")

    def generate_migration_config(self, gh_owner: str = "", gh_repo: str = "") -> Dict[str, Any]:
        """
        Generate migration configuration template.

        Args:
            gh_owner: GitHub owner/organization name
            gh_repo: GitHub repository name

        Returns:
            Configuration dictionary
        """
        if not gh_owner:
            gh_owner = "YOUR_GITHUB_USERNAME"
        if not gh_repo:
            gh_repo = self.repo

        # Create user mapping template
        user_mapping = {}
        for user in sorted(self.users):
            if user.lower() == 'unknown':
                user_mapping[user] = None
            else:
                user_mapping[user] = ""  # Empty string to be filled in

        config = {
            "_comment": "Bitbucket to GitHub Migration Configuration",
            "_instructions": {
                "step_1": "Fill in your GitHub personal access token (needs 'repo' scope)",
                "step_2": "Set github.owner to your GitHub username or organization",
                "step_3": "Set github.repo to your target repository name",
                "step_4": "For each user in user_mapping - set to their GitHub username if they have an account, or set to null/empty if they don't",
                "step_5": "Bitbucket credentials are pre-filled from audit",
                "step_6": "Run dry-run first - migrate_bitbucket_to_github dry-run --config migration_config.json",
                "step_7": "After dry-run succeeds, use migrate subcommand to perform actual migration"
            },
            "bitbucket": {
                "workspace": self.workspace,
                "repo": self.repo,
                "email": self.email,
                "token": self.token
            },
            "github": {
                "owner": gh_owner,
                "repo": gh_repo,
                "token": "YOUR_GITHUB_TOKEN_HERE"
            },
            "user_mapping": user_mapping
        }

        return config

    def save_migration_config(self, config: Dict[str, Any], filename: str = 'migration_config.json') -> None:
        """
        Save migration configuration to file.

        Args:
            config: Configuration dictionary
            filename: Output filename
        """
        import json

        with open(filename, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"\n{'='*80}")
        print(f"📋 Migration configuration template saved: {filename}")
        print(f"{'='*80}")
        print("\nNext steps:")
        print("1. Edit migration_config.json:")
        print("   - Add your GitHub token")
        print("   - Set github.owner to your GitHub username")
        print("   - Map Bitbucket users to GitHub usernames")
        print("     (use null for users without GitHub accounts)")
        print("\n2. Test with dry run:")
        print(f"   migrate_bitbucket_to_github dry-run --config {filename}")
        print("\n3. Run actual migration:")
        print(f"   migrate_bitbucket_to_github migrate --config {filename}")
        print(f"{'='*80}")