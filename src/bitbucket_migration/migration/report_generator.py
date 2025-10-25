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
                                    report_filename: str = 'migration_report.md',
                                    user_mapping_data: Optional[List[Dict[str, Any]]] = None,
                                    attachment_data: Optional[List[Dict[str, Any]]] = None,
                                    link_data: Optional[Dict[str, Any]] = None,
                                    type_mapping_data: Optional[Dict[str, Any]] = None) -> str:
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
            user_mapping_data: Optional list of user mapping records with keys: bb_user, gh_user, success, timestamp, reason
            attachment_data: Optional list of attachment records with keys: file_path, size, type, uploaded, url, error, instructions
            link_data: Optional dict with link rewriting data including total_processed, successful, failed, and details list
            type_mapping_data: Optional dict with issue type mapping data including type_stats and type_fallbacks

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
            report.append("**Note:** Issue and PR numbers in this report are simulated sequentially and do not reflect actual GitHub numbers.")
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

        report.append(f"- **Total Attachments:** {len([r for r in issue_records if r.get('attachments', 0) > 0]) + len([r for r in pr_records if r.get('attachments', 0) > 0])}")
        report.append("")

        # Table of Contents
        report.append("## Table of Contents")
        report.append("")
        report.append("1. [Issues Migration](#issues-migration)")
        report.append("   - [Issue Types](#issue-types)")
        report.append("2. [Pull Requests Migration](#pull-requests-migration)")
        report.append("3. [User Mapping](#user-mapping)")
        report.append("4. [Attachment Handling](#attachment-handling)")
        report.append("5. [Link Rewriting](#link-rewriting)")
        report.append("6. [Migration Statistics](#migration-statistics)")
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
        report.append("### Issue Types")
        report.append("")

        # Collect unique issue types from records
        issue_types = set()
        for record in issue_records:
            if record.get('kind') and record['kind'] != 'N/A':
                issue_types.add(record['kind'])

        if issue_types:
            report.append(f"**Unique Issue Types Found:** {len(issue_types)}")
            report.append("")
            report.append("**Issue Types:**")
            report.append("")
            for issue_type in sorted(issue_types):
                count = len([r for r in issue_records if r.get('kind') == issue_type])
                report.append(f"- **{issue_type}**: {count} issues")
            report.append("")

            # Add type mapping details if available
            if type_mapping_data:
                type_stats = type_mapping_data.get('type_stats', {})
                type_fallbacks = type_mapping_data.get('type_fallbacks', [])

                report.append("**Issue Type Mapping Summary:**")
                report.append("")
                report.append(f"- **Using native GitHub issue types:** {type_stats.get('using_native', 0)} issues")
                report.append(f"- **Using labels (fallback):** {type_stats.get('using_labels', 0)} issues")
                report.append(f"- **No type specified:** {type_stats.get('no_type', 0)} issues")
                report.append("")

                # Separate native types from label fallbacks
                native_types = [(bb_type, gh_type) for bb_type, gh_type in type_fallbacks if gh_type is not None]
                label_fallbacks = [(bb_type, gh_type) for bb_type, gh_type in type_fallbacks if gh_type is None]

                if native_types:
                    report.append("**Successfully mapped to native GitHub types:**")
                    report.append("")
                    native_summary = {}
                    for bb_type, gh_type in native_types:
                        if bb_type not in native_summary:
                            native_summary[bb_type] = (gh_type, 0)
                        native_summary[bb_type] = (gh_type, native_summary[bb_type][1] + 1)
                    for bb_type, (gh_type, count) in native_summary.items():
                        report.append(f"- **{bb_type}** ({count} issues) → GitHub type **{gh_type}**")
                    report.append("")

                if label_fallbacks:
                    report.append("**Types that fell back to labels:**")
                    report.append("")
                    fallback_summary = {}
                    for bb_type, gh_type in label_fallbacks:
                        fallback_summary[bb_type] = fallback_summary.get(bb_type, 0) + 1
                    for bb_type, count in fallback_summary.items():
                        report.append(f"- **{bb_type}** ({count} issues) → Label **type: {bb_type}**")
                    report.append("")

            report.append("**Note:** Use these types in your `issue_type_mapping` configuration to map to GitHub issue types.")
        else:
            report.append("**No issue types found** (all issues have no 'kind' specified)")
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

        # User Mapping
        report.append("---")
        report.append("")
        report.append("## User Mapping")
        report.append("")

        if user_mapping_data:
            total_users = len(user_mapping_data)
            successful_mappings = len([u for u in user_mapping_data if u.get('success', False)])
            failed_mappings = total_users - successful_mappings

            report.append(f"**Total Users Processed:** {total_users}")
            report.append(f"  - Successfully Mapped: {successful_mappings}")
            report.append(f"  - Failed Mappings: {failed_mappings}")
            report.append("")

            # User mapping table
            report.append("| Bitbucket User | GitHub User | Success | Timestamp | Reason |")
            report.append("|----------------|-------------|---------|-----------|--------|")

            for user in user_mapping_data:
                bb_user = user.get('bb_user', 'N/A')
                gh_user = user.get('gh_user', 'N/A')
                success = '✅' if user.get('success', False) else '❌'
                timestamp = user.get('timestamp', 'N/A')
                reason = user.get('reason', '-')

                report.append(f"| {bb_user} | {gh_user} | {success} | {timestamp} | {reason} |")

            report.append("")

            # Recommendations
            if failed_mappings > 0:
                report.append("### Recommendations for Failed Mappings")
                report.append("")
                report.append("For users that failed to map:")
                report.append("- Verify that the GitHub user exists and is spelled correctly in the mapping configuration.")
                report.append("- Check if the user has a GitHub account and update the mapping accordingly.")
                report.append("- For account IDs, ensure they are resolved to usernames via API lookup.")
                report.append("- Consider manual intervention: Create GitHub accounts or update mappings in the configuration file.")
                report.append("")
        else:
            report.append("No user mapping data available.")
            report.append("")

        # Attachment Handling
        report.append("---")
        report.append("")
        report.append("## Attachment Handling")
        report.append("")

        if attachment_data:
            total_attachments = len(attachment_data)
            successful_uploads = len([a for a in attachment_data if a.get('uploaded', False)])
            manual_uploads = total_attachments - successful_uploads

            report.append(f"**Total Attachments Processed:** {total_attachments}")
            report.append(f"  - Successfully Uploaded: {successful_uploads}")
            report.append(f"  - Require Manual Upload: {manual_uploads}")
            report.append("")

            # Attachment table
            report.append("| File Path | Size | Type | Uploaded | Target URL | Error/Instructions |")
            report.append("|-----------|------|------|----------|------------|---------------------|")

            for attachment in attachment_data:
                file_path = attachment.get('file_path', 'N/A')
                size = attachment.get('size', 'N/A')
                file_type = attachment.get('type', 'N/A')
                uploaded = '✅' if attachment.get('uploaded', False) else '❌'
                url = attachment.get('url', '-')
                error_or_instructions = attachment.get('error', attachment.get('instructions', '-'))

                report.append(f"| {file_path} | {size} | {file_type} | {uploaded} | {url} | {error_or_instructions} |")

            report.append("")

            # Errors and instructions
            if manual_uploads > 0 or any(a.get('error') for a in attachment_data):
                report.append("### Manual Upload Instructions")
                report.append("")
                report.append("For attachments requiring manual upload:")
                report.append("1. Locate the file in the attachments directory (e.g., `attachments_temp/`).")
                report.append("2. Navigate to the corresponding GitHub issue.")
                report.append("3. Drag and drop the file into the comment box to upload and embed it.")
                report.append("4. If size limits are encountered, consider compressing the file or splitting large attachments.")
                report.append("")

                errors = [a for a in attachment_data if a.get('error')]
                if errors:
                    report.append("### Errors Encountered")
                    report.append("")
                    for error in errors:
                        report.append(f"- **{error.get('file_path', 'Unknown')}**: {error.get('error', 'Unknown error')}")
                        if error.get('instructions'):
                            report.append(f"  - Suggested Resolution: {error.get('instructions')}")
                    report.append("")
        else:
            report.append("No attachment data available.")
            report.append("")

        # Link Rewriting
        report.append("---")
        report.append("")
        report.append("## Link Rewriting")
        report.append("")

        if link_data:
            total_processed = link_data.get('total_processed', 0)
            successful = link_data.get('successful', 0)
            failed = link_data.get('failed', 0)

            report.append(f"**Total Links and Mentions Processed:** {total_processed}")
            report.append(f"  - Successfully Rewritten: {successful}")
            report.append(f"  - Failed Rewrites: {failed}")
            report.append("")

            # Link rewriting table
            report.append("| Original | Rewritten | Type | Reason |")
            report.append("|----------|-----------|------|--------|")

            details = link_data.get('details', [])
            for detail in details:
                original = detail.get('original', 'N/A')
                rewritten = detail.get('rewritten', 'N/A')
                link_type = detail.get('type', 'N/A')
                reason = detail.get('reason', '-')

                # Enclose commit references in backticks for proper rendering
                if link_type == 'commit_ref':
                    if not original.startswith('`'):
                        original = f"`{original}`"
                    if not rewritten.startswith('`'):
                        rewritten = f"`{rewritten}`"

                report.append(f"| {original} | {rewritten} | {link_type} | {reason} |")

            report.append("")

            # Instructions for failed rewrites
            if failed > 0:
                report.append("### Manual Update Instructions")
                report.append("")
                report.append("For links that failed to rewrite:")
                report.append("- **Internal Links**: Search for the original Bitbucket issue/PR number in the GitHub repository and replace with the new GitHub link.")
                report.append("- **External Links**: Verify if the external resource still exists and update the URL if necessary.")
                report.append("- **User Mentions**: Ensure the user mapping is correct; update mentions to the corresponding GitHub usernames.")
                report.append("- Use search and replace tools in GitHub or scripts to bulk update failed rewrites.")
                report.append("")
        else:
            report.append("No link rewriting data available.")
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