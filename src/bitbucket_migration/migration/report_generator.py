"""
Report generator for Bitbucket to GitHub migration.

This module contains the ReportGenerator class that handles the generation
of comprehensive migration reports, including statistics, mappings, and
troubleshooting information.
"""

from typing import Dict, List, Any
from datetime import datetime
from ..services.services_data import LinkWriterData
from ..core.migration_context import MigrationEnvironment, MigrationState

class ReportGenerator:
    """
    Handles generation of migration reports and statistics.

    This class encapsulates all logic related to report generation, including
    migration summaries, detailed tables, and troubleshooting information.
    """

    def __init__(self, environment:MigrationEnvironment, state:MigrationState):
        """
        Initialize the ReportGenerator.

        Args:
            environment: Migration environment containing all services and configuration
            state: Migration state containing mappings and records
        """
        
        self.environment = environment
        self.state = state

        self.logger = environment.logger
        self.base_dir_manager = environment.base_dir_manager

    def _format_found_in(self, item_type: str = None, item_number: int = None, comment_seq: int = None) -> str:
        """
        Format "Found In" information similar to link rewriting.

        Args:
            item_type: 'issue' or 'pr'
            item_number: The issue or PR number
            comment_seq: Comment sequence number if attachment is from a comment

        Returns:
            Formatted string like "Issue #123" or "PR #456 Comment #2"
        """
        if not item_type or item_number is None:
            return 'N/A'

        if item_type == 'issue':
            location = f"Issue #{item_number}"
        elif item_type == 'pr':
            location = f"PR #{item_number}"
        else:
            return 'N/A'

        if comment_seq is not None:
            location += f" Comment #{comment_seq}"

        return location
    
    def _collect_user_mapping_data(self) -> List[Dict[str, Any]]:
        """Collect user mapping data for the report."""
        from datetime import datetime
        data = []
        for bb_user, gh_user in self.environment.config.user_mapping.items():
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
        for attachment in self.state.services['AttachmentHandler'].attachments:
            file_path = attachment.get('filepath', 'N/A')
            filename = attachment.get('filename', 'N/A')
            # Assume size and type need to be calculated or added
            size = "Unknown"  # Placeholder
            file_type = "Unknown"  # Placeholder
            uploaded = False  # Placeholder, need to track in attachment_handler
            url = "-"  # Placeholder
            error = "-"  # Placeholder
            instructions = "Drag and drop to GitHub issue" if not uploaded else "-"

            # Format "Found In" information similar to link rewriting
            item_type = attachment.get('item_type')
            item_number = attachment.get('item_number')
            comment_seq = attachment.get('comment_seq')

            found_in = self._format_found_in(item_type, item_number, comment_seq)

            data.append({
                'file_path': file_path,
                'size': size,
                'type': file_type,
                'uploaded': uploaded,
                'url': url,
                'error': error,
                'instructions': instructions,
                'found_in': found_in
            })
        return data

    # Link data is now collected from LinkWriterData service
    
    def _link_report(self, link_data: LinkWriterData):
        
        report = []

        if link_data:
            total_processed = link_data.total_processed
            successful = link_data.successful
            failed = link_data.failed

            report.append(f"**Total Links and Mentions Processed:** {total_processed}")
            report.append(f"  - Successfully Rewritten: {successful}")
            report.append(f"  - Failed Rewrites: {failed}")
            report.append("")

            # Link rewriting table
            report.append("| Original | Rewritten | Type | Reason | Found In |")
            report.append("|----------|-----------|------|--------|----------|")

            details = link_data.details
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

                # Determine location
                item_type = detail.get('item_type', 'N/A')
                item_number = detail.get('item_number', 'N/A')
                comment_seq = detail.get('comment_seq', None)

                if item_type == 'issue' and item_number != 'N/A':
                    location = f"Issue #{item_number}"
                    if comment_seq:
                        location += f" Comment #{comment_seq}"
                elif item_type == 'pr' and item_number != 'N/A':
                    location = f"PR #{item_number}"
                    if comment_seq:
                        location += f" Comment #{comment_seq}"
                else:
                    location = item_type or 'N/A'

                report.append(f"| {original} | {rewritten} | {link_type} | {reason} | {location} |")

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
        
        return report


    def generate_cross_link_report(self, report_filename: str = 'cross_link_report.md'):

        link_data : LinkWriterData = self.state.services['LinkRewriter']

        report = self._link_report(link_data)

        # Add deferred links section to the report
        deferred_by_repo = self._extract_deferred_links()
        if deferred_by_repo:
            deferred_section = self._generate_deferred_links_section(deferred_by_repo)
            report.extend(deferred_section)

        # Write report to file using create_file for tracking
        report_content = '\n'.join(report)
        
        # Determine subcommand based on dry_run flag
        subcommand = 'cross-link_dry-run' if self.environment.dry_run else 'cross-link'
        
        output_path = self.base_dir_manager.get_subcommand_dir(subcommand, self.environment.config.bitbucket.workspace, self.environment.config.bitbucket.repo)
        
        # Use create_file to write and track the report
        self.base_dir_manager.create_file(
            output_path / report_filename,
            report_content,
            subcommand=subcommand,
            workspace=self.environment.config.bitbucket.workspace,
            repo=self.environment.config.bitbucket.repo,
            category='report'
        )

        self.logger.info(f"Cross-link report saved to {report_filename}")

        return report_content

    def generate_migration_report(self,
                                    report_filename: str = 'migration_report.md',
                                    ) -> str:
        """
        Generate a comprehensive markdown migration report.

        Args:
            report_filename: Output filename for the report

        Returns:
            The filename where the report was saved
        """

        user_mapping_data = self._collect_user_mapping_data()
        attachment_data = self._collect_attachment_data()
        link_data : LinkWriterData = self.state.services['LinkRewriter']
        

        report = []
        report.append("# Bitbucket to GitHub Migration Report")
        report.append("")
        report.append(f"**Migration Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Source:** Bitbucket `{self.environment.config.bitbucket.workspace}/{self.environment.config.bitbucket.repo}`")
        report.append(f"**Destination:** GitHub `{self.environment.config.github.owner}/{self.environment.config.github.repo}`")
        report.append("")

        if self.environment.dry_run:
            report.append("**⚠️ DRY RUN MODE** - This is a simulation report")
            report.append("**Note:** Issue and PR numbers in this report are simulated sequentially and do not reflect actual GitHub numbers.")
            report.append("")

        # Executive Summary
        report.append("## Executive Summary")
        report.append("")
        report.append(f"- **Total Issues Migrated:** {len(self.state.issue_records)}")
        report.append(f"  - Real Issues: {len([r for r in self.state.issue_records if r['state'] != 'deleted'])}")
        report.append(f"  - Placeholders: {len([r for r in self.state.issue_records if r['state'] == 'deleted'])}")

        # Calculate PR statistics
        total_prs = len(self.state.pr_records)
        skipped_prs = len([r for r in self.state.pr_records if r['gh_type'] == 'Skipped'])
        migrated_prs = total_prs - skipped_prs

        report.append(f"- **Total Pull Requests Processed:** {total_prs}")
        report.append(f"  - Migrated: {migrated_prs}")
        report.append(f"  - As GitHub PRs: {self.state.pr_migration_stats.get('prs_as_prs', 0)}")
        report.append(f"  - As GitHub Issues: {self.state.pr_migration_stats.get('prs_as_issues', 0)}")
        if skipped_prs > 0:
            report.append(f"  - Skipped (not migrated): {skipped_prs}")

        report.append(f"- **Total Attachments:** {len([r for r in self.state.issue_records if r.get('attachments', 0) > 0]) + len([r for r in self.state.pr_records if r.get('attachments', 0) > 0])}")
        report.append("")

        # Table of Contents
        report.append("## Table of Contents")
        report.append("")
        report.append("1. [Issues Migration](#issues-migration)")
        report.append("   - [Issue Types](#issue-types)")
        report.append("2. [Pull Requests Migration](#pull-requests-migration)")
        report.append("3. [Milestones](#milestones)")
        report.append("4. [User Mapping](#user-mapping)")
        report.append("5. [Attachment Handling](#attachment-handling)")
        report.append("6. [Link Rewriting](#link-rewriting)")
        report.append("7. [Migration Statistics](#migration-statistics)")
        report.append("")

        # Issues Migration
        report.append("---")
        report.append("")
        report.append("## Issues Migration")
        report.append("")
        report.append(f"**Total Issues:** {len(self.state.issue_records)}")
        report.append("")

        # Issues table
        report.append("| BB # | GH # | Title | Reporter | State | Kind | Comments | Attachments | Links | Remarks |")
        report.append("|------|------|-------|----------|-------|------|----------|-------------|-------|---------|")

        for record in sorted(self.state.issue_records, key=lambda x: x['bb_number']):
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
        for record in self.state.issue_records:
            if record.get('kind') and record['kind'] != 'N/A':
                issue_types.add(record['kind'])

        if issue_types:
            report.append(f"**Unique Issue Types Found:** {len(issue_types)}")
            report.append("")
            report.append("**Issue Types:**")
            report.append("")
            for issue_type in sorted(issue_types):
                count = len([r for r in self.state.issue_records if r.get('kind') == issue_type])
                report.append(f"- **{issue_type}**: {count} issues")
            report.append("")

            # Add type mapping details if available

            report.append("**Issue Type Mapping Summary:**")
            report.append("")
            report.append(f"- **Using native GitHub issue types:** {self.state.type_stats.get('using_native', 0)} issues")
            report.append(f"- **Using labels (fallback):** {self.state.type_stats.get('using_labels', 0)} issues")
            report.append(f"- **No type specified:** {self.state.type_stats.get('no_type', 0)} issues")
            report.append("")

            # Separate native types from label fallbacks
            native_types = [(bb_type, gh_type) for bb_type, gh_type in self.state.type_fallbacks if gh_type is not None]
            label_fallbacks = [(bb_type, gh_type) for bb_type, gh_type in self.state.type_fallbacks if gh_type is None]

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
        report.append(f"**Total Pull Requests:** {len(self.state.pr_records)}")
        report.append("")

        # PRs table
        report.append("| BB PR # | GH # | Type | Title | Author | State | Source → Dest | Comments | Links | Remarks |")
        report.append("|---------|------|------|-------|--------|-------|---------------|----------|-------|---------|")

        for record in sorted(self.state.pr_records, key=lambda x: x['bb_number']):
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

        # Milestones Migration
        report.append("---")
        report.append("")
        report.append("## Milestones")
        report.append("")

        if self.state.milestone_records:
            total_milestones = len(self.state.milestone_records)
            duplicates = len([m for m in self.state.milestone_records if m.get('is_duplicate', False)])
            created = total_milestones - duplicates

            report.append(f"**Total Milestones Processed:** {total_milestones}")
            report.append(f"  - Created on GitHub: {created}")
            report.append(f"  - Already Existed (Duplicates): {duplicates}")
            report.append("")

            # Milestones table
            report.append("| Name | GitHub # | State | Due Date | Description | Remarks |")
            report.append("|------|----------|-------|----------|-------------|---------|")

            for milestone in sorted(self.state.milestone_records, key=lambda x: x.get('bb_name', '')):
                name = milestone.get('bb_name', 'N/A')
                gh_number = milestone.get('gh_number', 'N/A')
                state = milestone.get('state', 'N/A')
                due_date = milestone.get('due_date', '-')
                
                # Truncate description if too long
                description = milestone.get('description', '-')
                if description and description != '-' and len(description) > 50:
                    description = description[:47] + '...'
                
                # Format remarks
                remarks_list = milestone.get('remarks', [])
                if remarks_list:
                    remarks = '<br>'.join(remarks_list)
                else:
                    remarks = '-'

                report.append(f"| {name} | #{gh_number} | {state} | {due_date} | {description} | {remarks} |")

            report.append("")
        else:
            report.append("No milestone data available.")
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
            report.append("| File Path | Size | Type | Uploaded | Target URL | Found In | Error/Instructions |")
            report.append("|-----------|------|------|----------|------------|----------|---------------------|")

            for attachment in attachment_data:
                file_path = attachment.get('file_path', 'N/A')
                size = attachment.get('size', 'N/A')
                file_type = attachment.get('type', 'N/A')
                uploaded = '✅' if attachment.get('uploaded', False) else '❌'
                url = attachment.get('url', '-')
                found_in = attachment.get('found_in', 'N/A')
                error_or_instructions = attachment.get('error', attachment.get('instructions', '-'))

                report.append(f"| {file_path} | {size} | {file_type} | {uploaded} | {url} | {found_in} | {error_or_instructions} |")

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

        report.extend(self._link_report(link_data))

        # Migration Statistics
        report.append("---")
        report.append("")
        report.append("## Migration Statistics")
        report.append("")

        report.append("### Issues")
        report.append("")
        report.append(f"- Total issues processed: {len(self.state.issue_records)}")
        report.append(f"- Real issues: {len([r for r in self.state.issue_records if r['state'] != 'deleted'])}")
        report.append(f"- Placeholder issues: {len([r for r in self.state.issue_records if r['state'] == 'deleted'])}")
        report.append(f"- Open issues: {len([r for r in self.state.issue_records if r['state'] in ['new', 'open']])}")
        report.append(f"- Closed issues: {len([r for r in self.state.issue_records if r['state'] not in ['new', 'open', 'deleted']])}")
        report.append(f"- Total comments: {sum(r['comments'] for r in self.state.issue_records)}")
        report.append(f"- Total attachments: {sum(r['attachments'] for r in self.state.issue_records)}")
        report.append("")

        report.append("### Pull Requests")
        report.append("")
        report.append(f"- Total PRs processed: {len(self.state.pr_records)}")
        report.append(f"- Migrated as GitHub PRs: {self.state.pr_migration_stats.get('prs_as_prs', 0)}")
        report.append(f"- Migrated as GitHub Issues: {self.state.pr_migration_stats.get('prs_as_issues', 0)}")
        report.append(f"  - Due to merged/closed state: {self.state.pr_migration_stats.get('pr_merged_as_issue', 0)}")
        report.append(f"  - Due to missing branches: {self.state.pr_migration_stats.get('pr_branch_missing', 0)}")
        report.append(f"- Total PR comments: {sum(r['comments'] for r in self.state.pr_records)}")
        report.append("")

        # State breakdown for PRs
        pr_states = {}
        for record in self.state.pr_records:
            state = record['state']
            pr_states[state] = pr_states.get(state, 0) + 1

        report.append("### Pull Request States")
        report.append("")
        for state, count in sorted(pr_states.items()):
            report.append(f"- {state}: {count}")
        report.append("")

        # Add deferred links section to the report
        deferred_by_repo = self._extract_deferred_links()
        if deferred_by_repo:
            deferred_section = self._generate_deferred_links_section(deferred_by_repo)
            report.extend(deferred_section)

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

        # Write report to file using create_file for tracking
        report_content = '\n'.join(report)
        
        # Determine subcommand based on dry_run flag
        subcommand = 'dry-run' if self.environment.dry_run else 'migrate'
        
        output_path = self.base_dir_manager.get_subcommand_dir(subcommand, self.environment.config.bitbucket.workspace, self.environment.config.bitbucket.repo)
        
        # Use create_file to write and track the report
        self.base_dir_manager.create_file(
            output_path / report_filename,
            report_content,
            subcommand=subcommand,
            workspace=self.environment.config.bitbucket.workspace,
            repo=self.environment.config.bitbucket.repo,
            category='report'
        )

        self.logger.info(f"Migration report saved to {report_filename}")

        return report_content

    def save_mapping(self, filename: str = 'migration_mapping.json'):
        """
        Save issue/PR mapping to file.

        Args:
            filename: Output filename for the mapping JSON
        """
        mapping = {
            'bitbucket': {
                'workspace': self.environment.config.bitbucket.workspace,
                'repo': self.environment.config.bitbucket.repo
            },
            'github': {
                'owner': self.environment.config.github.owner,
                'repo': self.environment.config.github.repo
            },
            'issue_mapping': self.state.mappings.issues,
            'pr_mapping': self.state.mappings.prs,
            'statistics': self.state.pr_migration_stats,
            'migration_date': datetime.now().isoformat()
        }

        # Also save to cross-repo store if provided
        cross_repo_store = self.environment.services.get('cross_repo_mapping_store')

        if cross_repo_store:
            try:
                cross_repo_store.save(
                    self.environment.config.bitbucket.workspace,
                    self.environment.config.bitbucket.repo,
                    self.environment.config.github.owner,
                    self.environment.config.github.repo,
                    self.state.mappings.issues,
                    self.state.mappings.prs,
                    self.state.mappings.issue_comments,
                    self.state.mappings.pr_comments
                )
                self.logger.info(f"Saved consolidated cross-repository mappings")
            except Exception as e:
                self.logger.warning(f"Could not save to cross-repo store: {e}")

        subcommand = 'dry-run' if self.environment.dry_run else 'migrate'
        output_path = self.base_dir_manager.get_subcommand_dir(
            subcommand, self.environment.config.bitbucket.workspace, self.environment.config.bitbucket.repo
            )

        # Use create_file to write and track the mapping
        self.base_dir_manager.create_file(
            output_path / filename,
            mapping,
            subcommand=subcommand,
            workspace=self.environment.config.bitbucket.workspace,
            repo=self.environment.config.bitbucket.repo,
            category='mapping'
        )

        self.logger.info(f"Mapping saved to {filename}")

    def _extract_deferred_links(self) -> Dict[str, List[Dict]]:
        """
        Extract deferred cross-repository links from reports.

        Returns dict mapping repo_key to list of deferred link info.
        Example: {'workspace/repo-b': [{'url': '...', 'found_in': 'issue #5'}, ...]}
        """
        deferred_by_repo = {}

        # Process issues
        for report in self.state.issue_records:
            issue_num = report.get('gh_number', 'unknown')
            link_details = report.get('link_details', [])

            for link in link_details:
                if link.get('type') == 'cross_repo_deferred':
                    repo_key = link.get('repo_key', 'unknown')
                    if repo_key not in deferred_by_repo:
                        deferred_by_repo[repo_key] = []

                    deferred_by_repo[repo_key].append({
                        'url': link.get('original', ''),
                        'found_in': f'issue #{issue_num}',
                        'resource_type': link.get('resource_type', 'unknown')
                    })

        # Process PRs (same logic)
        for report in self.state.pr_records:
            pr_num = report.get('gh_number', 'unknown')
            link_details = report.get('link_details', [])

            for link in link_details:
                if link.get('type') == 'cross_repo_deferred':
                    repo_key = link.get('repo_key', 'unknown')
                    if repo_key not in deferred_by_repo:
                        deferred_by_repo[repo_key] = []

                    deferred_by_repo[repo_key].append({
                        'url': link.get('original', ''),
                        'found_in': f'PR #{pr_num}',
                        'resource_type': link.get('resource_type', 'unknown')
                    })

        return deferred_by_repo

    def _generate_deferred_links_section(self, deferred_by_repo: Dict[str, List[Dict]]) -> str:
        """Generate markdown section for deferred cross-repository links."""
        if not deferred_by_repo:
            return []

        section = []
        section.append("\n## ⏳ Deferred Cross-Repository Links\n")
        section.append("The following cross-repository links could not be rewritten because the target repositories have not been migrated yet. ")
        section.append("After migrating all repositories, run Phase 2 with `migrate_bitbucket_to_github cross-link` to rewrite these links.\n")

        total_deferred = sum(len(links) for links in deferred_by_repo.values())
        section.append(f"**Total deferred links**: {total_deferred}\n")

        for repo_key, links in sorted(deferred_by_repo.items()):
            section.append(f"### Repository: `{repo_key}` ({len(links)} links)\n")

            # Group by resource type
            by_type = {}
            for link in links:
                res_type = link['resource_type']
                if res_type not in by_type:
                    by_type[res_type] = []
                by_type[res_type].append(link)

            for res_type, type_links in sorted(by_type.items()):
                section.append(f"**{res_type.capitalize()}s** ({len(type_links)}):")
                for link in type_links[:10]:  # Limit to first 10
                    section.append(f"- `{link['url']}` in {link['found_in']}")

                if len(type_links) > 10:
                    section.append(f"- ... and {len(type_links) - 10} more")
                section.append("\n")

        section.append("**Next steps**:")
        section.append("1. Complete Phase 1 migration for all referenced repositories")
        section.append("2. Run Phase 2 for this repository:")
        section.append("   ```bash")
        section.append("   migrate_bitbucket_to_github cross-link --config <config>")
        section.append("   ```\n")

        return section

    def print_summary(self) -> None:
        """
        Print migration summary statistics.
        """
        self.logger.info("="*80)
        self.logger.info("MIGRATION SUMMARY")
        self.logger.info("="*80)

        self.logger.info(f"Issues:")
        self.logger.info(f"  Total migrated: {len(self.state.mappings.issues)}")

        self.logger.info(f"Pull Requests:")
        self.logger.info(f"  Total processed: {len(self.state.mappings.prs)}")
        self.logger.info(f"  Migrated as GitHub PRs: {self.state.pr_migration_stats.get('prs_as_prs', 0)}")
        self.logger.info(f"  Migrated as GitHub Issues: {self.state.pr_migration_stats.get('prs_as_issues', 0)}")
        self.logger.info(f"    - Due to merged/closed state: {self.state.pr_migration_stats.get('pr_merged_as_issue', 0)}")
        self.logger.info(f"    - Due to missing branches: {self.state.pr_migration_stats.get('pr_branch_missing', 0)}")

        skipped_prs = len([r for r in self.state.mappings.prs.values() if r is None])  # Assuming None means skipped
        if skipped_prs > 0:
            self.logger.info(f"  Skipped (not migrated as issues): {skipped_prs}")

        self.logger.info(f"Attachments:")
        self.logger.info(f"  Total downloaded: {len(self.state.services['AttachmentHandler'].attachments)}")
        self.logger.info(f"  Location: {self.state.services['AttachmentHandler'].attachment_dir}/")

        self.logger.info(f"Reports Generated:")
        self.logger.info(f"  ✓ migration_mapping.json - Machine-readable mapping")
        if self.environment.dry_run:
            self.logger.info(f"  ✓ migration_report_dry_run.md - Comprehensive migration report")
        else:
            self.logger.info(f"  ✓ migration_report.md - Comprehensive migration report")

        self.logger.info("="*80)