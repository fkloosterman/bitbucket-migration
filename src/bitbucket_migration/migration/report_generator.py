"""
Report generator for Bitbucket to GitHub migration.

This module contains the ReportGenerator class that handles the generation
of comprehensive migration reports, including statistics, mappings, and
troubleshooting information.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from ..utils.logging_config import MigrationLogger


class ReportGenerator:
    """
    Handles generation of migration reports and statistics.

    This class encapsulates all logic related to report generation, including
    migration summaries, detailed tables, and troubleshooting information.
    """

    def __init__(self, logger: MigrationLogger):
        """
        Initialize the ReportGenerator.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def generate_migration_report(self, issue_records: List[Dict[str, Any]],
                                  pr_records: List[Dict[str, Any]],
                                  stats: Dict[str, Any],
                                  bb_workspace: str, bb_repo: str,
                                  gh_owner: str, gh_repo: str,
                                  dry_run: bool = False,
                                  report_filename: str = 'migration_report.md') -> str:
        """
        Generate a comprehensive markdown migration report.

        Args:
            issue_records: List of issue migration records
            pr_records: List of PR migration records
            stats: Migration statistics
            bb_workspace: Bitbucket workspace name
            bb_repo: Bitbucket repository name
            gh_owner: GitHub owner name
            gh_repo: GitHub repository name
            dry_run: Whether this is a dry run
            report_filename: Output filename for the report

        Returns:
            The filename where the report was saved
        """
        report = []
        report.append("# Bitbucket to GitHub Migration Report")
        report.append("")
        report.append(f"**Migration Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Source:** Bitbucket `{bb_workspace}/{bb_repo}`")
        report.append(f"**Destination:** GitHub `{gh_owner}/{gh_repo}`")
        report.append("")

        if dry_run:
            report.append("**⚠️ DRY RUN MODE** - This is a simulation report")
            report.append("")

        # Executive Summary
        report.append("## Executive Summary")
        report.append("")
        report.append(f"- **Total Issues Migrated:** {len(issue_records)}")
        report.append(f"  - Real Issues: {len([r for r in issue_records if r['state'] != 'deleted'])}")
        report.append(f"  - Placeholders: {len([r for r in issue_records if r['state'] == 'deleted'])}")

        # Calculate PR statistics
        total_prs = len(pr_records)
        skipped_prs = len([r for r in pr_records if r['gh_type'] == 'Skipped'])
        migrated_prs = total_prs - skipped_prs

        report.append(f"- **Total Pull Requests Processed:** {total_prs}")
        report.append(f"  - Migrated: {migrated_prs}")
        report.append(f"  - As GitHub PRs: {stats.get('prs_as_prs', 0)}")
        report.append(f"  - As GitHub Issues: {stats.get('prs_as_issues', 0)}")
        if skipped_prs > 0:
            report.append(f"  - Skipped (not migrated): {skipped_prs}")

        report.append(f"- **Total Attachments:** {len([r for r in issue_records if r.get('attachments', 0) > 0]) + len([r for r in pr_records if r.get('comments', 0) > 0])}")
        report.append("")

        # Table of Contents
        report.append("## Table of Contents")
        report.append("")
        report.append("1. [Issues Migration](#issues-migration)")
        report.append("2. [Pull Requests Migration](#pull-requests-migration)")
        report.append("3. [Migration Statistics](#migration-statistics)")
        report.append("")

        # Issues Migration
        report.append("---")
        report.append("")
        report.append("## Issues Migration")
        report.append("")
        report.append(f"**Total Issues:** {len(issue_records)}")
        report.append("")

        # Issues table
        report.append("| BB # | GH # | Title | Reporter | State | Kind | Comments | Attachments | Links | Remarks |")
        report.append("|------|------|-------|----------|-------|------|----------|-------------|-------|---------|")

        for record in sorted(issue_records, key=lambda x: x['bb_number']):
            bb_num = record['bb_number']
            gh_num = record['gh_number']
            title = record['title'][:50] + ('...' if len(record['title']) > 50 else '')
            reporter = record['reporter'][:20] if record['reporter'] != 'N/A' else 'N/A'
            state = record['state']
            kind = record['kind']
            comments = record['comments']
            attachments = record['attachments']
            links = record.get('links_rewritten', 0)
            remarks = ', '.join(record['remarks']) if record['remarks'] else '-'

            # Create links
            bb_link = f"[#{bb_num}]({record['bb_url']})" if record['bb_url'] else f"#{bb_num}"
            gh_link = f"[#{gh_num}]({record['gh_url']})" if record['gh_url'] else f"#{gh_num}"

            report.append(f"| {bb_link} | {gh_link} | {title} | {reporter} | {state} | {kind} | {comments} | {attachments} | {links} | {remarks} |")

        report.append("")

        # Pull Requests Migration
        report.append("---")
        report.append("")
        report.append("## Pull Requests Migration")
        report.append("")
        report.append(f"**Total Pull Requests:** {len(pr_records)}")
        report.append("")

        # PRs table
        report.append("| BB PR # | GH # | Type | Title | Author | State | Source → Dest | Comments | Links | Remarks |")
        report.append("|---------|------|------|-------|--------|-------|---------------|----------|-------|---------|")

        for record in sorted(pr_records, key=lambda x: x['bb_number']):
            bb_num = record['bb_number']
            gh_num = record['gh_number']
            gh_type = record['gh_type']
            title = record['title'][:40] + ('...' if len(record['title']) > 40 else '')
            author = record['author'][:20]
            state = record['state']
            branches = f"`{record['source_branch'][:15]}` → `{record['dest_branch'][:15]}`"
            comments = record['comments']
            links = record.get('links_rewritten', 0)
            remarks = '<br>'.join(record['remarks'])

            # Create links
            bb_link = f"[PR #{bb_num}]({record['bb_url']})" if record['bb_url'] else f"PR #{bb_num}"

            if gh_num is None:
                gh_link = "Not migrated"
            elif gh_type == 'PR':
                gh_link = f"[PR #{gh_num}]({record['gh_url']})"
            else:
                gh_link = f"[Issue #{gh_num}]({record['gh_url']})"

            report.append(f"| {bb_link} | {gh_link} | {gh_type} | {title} | {author} | {state} | {branches} | {comments} | {links} | {remarks} |")

        report.append("")

        # Migration Statistics
        report.append("---")
        report.append("")
        report.append("## Migration Statistics")
        report.append("")

        report.append("### Issues")
        report.append("")
        report.append(f"- Total issues processed: {len(issue_records)}")
        report.append(f"- Real issues: {len([r for r in issue_records if r['state'] != 'deleted'])}")
        report.append(f"- Placeholder issues: {len([r for r in issue_records if r['state'] == 'deleted'])}")
        report.append(f"- Open issues: {len([r for r in issue_records if r['state'] in ['new', 'open']])}")
        report.append(f"- Closed issues: {len([r for r in issue_records if r['state'] not in ['new', 'open', 'deleted']])}")
        report.append(f"- Total comments: {sum(r['comments'] for r in issue_records)}")
        report.append(f"- Total attachments: {sum(r['attachments'] for r in issue_records)}")
        report.append("")

        report.append("### Pull Requests")
        report.append("")
        report.append(f"- Total PRs processed: {len(pr_records)}")
        report.append(f"- Migrated as GitHub PRs: {stats.get('prs_as_prs', 0)}")
        report.append(f"- Migrated as GitHub Issues: {stats.get('prs_as_issues', 0)}")
        report.append(f"  - Due to merged/closed state: {stats.get('pr_merged_as_issue', 0)}")
        report.append(f"  - Due to missing branches: {stats.get('pr_branch_missing', 0)}")
        report.append(f"- Total PR comments: {sum(r['comments'] for r in pr_records)}")
        report.append("")

        # State breakdown for PRs
        pr_states = {}
        for record in pr_records:
            state = record['state']
            pr_states[state] = pr_states.get(state, 0) + 1

        report.append("### Pull Request States")
        report.append("")
        for state, count in sorted(pr_states.items()):
            report.append(f"- {state}: {count}")
        report.append("")

        # Footer
        report.append("---")
        report.append("")
        report.append("## Notes")
        report.append("")
        report.append("- All issues maintain their original numbering from Bitbucket (with placeholders for gaps)")
        report.append("- Pull requests share the same numbering sequence as issues on GitHub")
        report.append("- Merged/closed PRs were migrated as issues to avoid re-merging code")
        report.append("- Original metadata (dates, authors, URLs) are preserved in issue/PR descriptions")
        report.append("- All comments include original author and timestamp information")
        report.append(f"**Migration completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        report.append("---")
        report.append("")
        report.append("*This report was automatically generated by the Bitbucket to GitHub migration script.*")

        # Write report to file
        report_content = '\n'.join(report)
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(report_content)

        self.logger.info(f"Migration report saved to {report_filename}")

        return report_filename

    def save_mapping(self, issue_mapping: Dict[int, int], pr_mapping: Dict[int, int],
                     bb_workspace: str, bb_repo: str, gh_owner: str, gh_repo: str,
                     stats: Dict[str, Any], filename: str = 'migration_mapping.json') -> None:
        """
        Save issue/PR mapping to file.

        Args:
            issue_mapping: BB issue # -> GH issue # mapping
            pr_mapping: BB PR # -> GH issue/PR # mapping
            bb_workspace: Bitbucket workspace name
            bb_repo: Bitbucket repository name
            gh_owner: GitHub owner name
            gh_repo: GitHub repository name
            stats: Migration statistics
            filename: Output filename for the mapping JSON
        """
        mapping = {
            'bitbucket': {
                'workspace': bb_workspace,
                'repo': bb_repo
            },
            'github': {
                'owner': gh_owner,
                'repo': gh_repo
            },
            'issue_mapping': issue_mapping,
            'pr_mapping': pr_mapping,
            'statistics': stats,
            'migration_date': datetime.now().isoformat()
        }

        with open(filename, 'w') as f:
            json.dump(mapping, f, indent=2)

        self.logger.info(f"Mapping saved to {filename}")

    def print_summary(self, issue_mapping: Dict[int, int], pr_mapping: Dict[int, int],
                      stats: Dict[str, Any], attachments: List[Dict[str, Any]],
                      attachment_handler, dry_run: bool = False) -> None:
        """
        Print migration summary statistics.

        Args:
            issue_mapping: BB issue # -> GH issue # mapping
            pr_mapping: BB PR # -> GH issue/PR # mapping
            stats: Migration statistics
            attachments: List of attachment records
            attachment_handler: Attachment handler instance
            dry_run: Whether this is a dry run
        """
        self.logger.info("="*80)
        self.logger.info("MIGRATION SUMMARY")
        self.logger.info("="*80)

        self.logger.info(f"Issues:")
        self.logger.info(f"  Total migrated: {len(issue_mapping)}")

        self.logger.info(f"Pull Requests:")
        self.logger.info(f"  Total processed: {len(pr_mapping)}")
        self.logger.info(f"  Migrated as GitHub PRs: {stats.get('prs_as_prs', 0)}")
        self.logger.info(f"  Migrated as GitHub Issues: {stats.get('prs_as_issues', 0)}")
        self.logger.info(f"    - Due to merged/closed state: {stats.get('pr_merged_as_issue', 0)}")
        self.logger.info(f"    - Due to missing branches: {stats.get('pr_branch_missing', 0)}")

        skipped_prs = len([r for r in pr_mapping.values() if r is None])  # Assuming None means skipped
        if skipped_prs > 0:
            self.logger.info(f"  Skipped (not migrated as issues): {skipped_prs}")

        self.logger.info(f"Attachments:")
        self.logger.info(f"  Total downloaded: {len(attachments)}")
        self.logger.info(f"  Location: {attachment_handler.attachment_dir}/")

        self.logger.info(f"Reports Generated:")
        self.logger.info(f"  ✓ migration_mapping.json - Machine-readable mapping")
        if dry_run:
            self.logger.info(f"  ✓ migration_report_dry_run.md - Comprehensive migration report")
        else:
            self.logger.info(f"  ✓ migration_report.md - Comprehensive migration report")

        self.logger.info("="*80)