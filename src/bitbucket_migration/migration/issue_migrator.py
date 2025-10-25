"""
Issue migrator for Bitbucket to GitHub migration.

This module contains the IssueMigrator class that handles the migration
of Bitbucket issues to GitHub issues, including comments, attachments,
and metadata preservation.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path

from ..clients.bitbucket_client import BitbucketClient
from ..clients.github_client import GitHubClient
from ..services.user_mapper import UserMapper
from ..services.link_rewriter import LinkRewriter
from ..services.attachment_handler import AttachmentHandler
from ..formatters.formatter_factory import FormatterFactory
from ..exceptions import MigrationError, APIError, AuthenticationError, NetworkError, ValidationError
from ..utils.logging_config import MigrationLogger


class IssueMigrator:
    """
    Handles migration of Bitbucket issues to GitHub.

    This class encapsulates all logic related to issue migration, including
    fetching, creating, and updating issues, as well as handling attachments
    and comments.
    """

    def __init__(self, bb_client: BitbucketClient, gh_client: GitHubClient,
                   user_mapper: UserMapper, link_rewriter: LinkRewriter,
                   attachment_handler: AttachmentHandler, formatter_factory: FormatterFactory,
                   logger: MigrationLogger, type_mapping: Optional[Dict[str, Dict[str, Any]]] = None):
        """
        Initialize the IssueMigrator.

        Args:
            bb_client: Bitbucket API client
            gh_client: GitHub API client
            user_mapper: User mapping service
            link_rewriter: Link rewriting service
            attachment_handler: Attachment handling service
            formatter_factory: Formatter factory
            logger: Logger instance
            type_mapping: Optional mapping of Bitbucket issue types to GitHub type data (id and name)
        """
        self.bb_client = bb_client
        self.gh_client = gh_client
        self.user_mapper = user_mapper
        self.link_rewriter = link_rewriter
        self.attachment_handler = attachment_handler
        self.formatter_factory = formatter_factory
        self.logger = logger
        self.type_mapping = type_mapping or {}  # GitHub issue type mapping

        # Track migration progress
        self.issue_mapping = {}  # BB issue # -> GH issue #
        self.issue_records = []  # Detailed migration records
        self.comment_mapping = {}  # BB comment ID -> GH comment ID

    def migrate_issues(self, bb_issues: List[Dict[str, Any]],
                        milestone_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
                        skip_link_rewriting: bool = False) -> List[Dict[str, Any]]:
        """
        Migrate all Bitbucket issues to GitHub.

        Args:
            bb_issues: List of Bitbucket issues to migrate
            milestone_lookup: Optional mapping of milestone names to GitHub milestone data
            skip_link_rewriting: If True, skip link rewriting (for two-pass migration)

        Returns:
            List of migration records
        """
        milestone_lookup = milestone_lookup or {}

        self.logger.info("="*80)
        self.logger.info("PHASE 1: Migrating Issues")
        self.logger.info("="*80)

        if not bb_issues:
            self.logger.info("No issues to migrate")
            return []

        # Determine range and gaps
        issue_numbers = [issue['id'] for issue in bb_issues]
        min_num = min(issue_numbers)
        max_num = max(issue_numbers)

        self.logger.info(f"Issue range: #{min_num} to #{max_num}")

        # Track issue type usage for reporting
        type_stats = {'using_native': 0, 'using_labels': 0, 'no_type': 0}
        type_fallbacks = []  # Track types that fell back to labels

        # Create placeholder issues for gaps
        expected_num = 1
        for bb_issue in bb_issues:
            issue_num = bb_issue['id']

            # Fill gaps with placeholders
            while expected_num < issue_num:
                self.logger.info(f"Creating placeholder issue #{expected_num}")
                placeholder = self._create_gh_issue(
                    title=f"[Placeholder] Issue #{expected_num} was deleted in Bitbucket",
                    body="This issue number was skipped or deleted in the original Bitbucket repository.",
                    labels=['migration-placeholder'],
                    state='closed'
                )
                self.issue_mapping[expected_num] = placeholder['number']

                # Record placeholder for report
                self.issue_records.append({
                    'bb_number': expected_num,
                    'gh_number': placeholder['number'],
                    'title': '[Placeholder - Deleted Issue]',
                    'reporter': 'N/A',
                    'gh_reporter': None,
                    'state': 'deleted',
                    'kind': 'N/A',
                    'priority': 'N/A',
                    'comments': 0,
                    'attachments': 0,
                    'links_rewritten': 0,
                    'bb_url': '',
                    'gh_url': f"https://github.com/{self.gh_client.owner}/{self.gh_client.repo}/issues/{placeholder['number']}",
                    'remarks': ['Placeholder for deleted/missing issue']
                })

                expected_num += 1

            # Migrate actual issue
            self.logger.info(f"Migrating issue #{issue_num}: {bb_issue.get('title', 'No title')}")

            # Extract reporter info
            reporter = bb_issue.get('reporter', {}).get('display_name', 'Unknown') if bb_issue.get('reporter') else 'Unknown (deleted user)'
            gh_reporter = self.user_mapper.map_user(reporter) if reporter != 'Unknown (deleted user)' else None

            # Use minimal body in first pass to avoid duplication
            body = f"Migrating issue #{issue_num} from Bitbucket. Content will be updated in second pass."

            # Note: Inline images will be handled in second pass when formatting occurs

            # Map assignee
            assignees = []
            if bb_issue.get('assignee'):
                assignee_name = bb_issue['assignee'].get('display_name', '')
                gh_user = self.user_mapper.map_user(assignee_name)
                if gh_user:
                    assignees = [gh_user]
                else:
                    self.logger.info(f"  Note: Assignee '{assignee_name}' has no GitHub account, mentioned in body instead")

            # Map milestone
            milestone_number = None
            if bb_issue.get('milestone'):
                milestone_name = bb_issue['milestone'].get('name')
                if milestone_name and milestone_name in milestone_lookup:
                    milestone_number = milestone_lookup[milestone_name].get('number')

            # Map issue kind/type
            labels = ['migrated-from-bitbucket']
            issue_type_id = None
            issue_type_name = None

            kind = bb_issue.get('kind')
            if kind:
                # Check if we have a native GitHub issue type for this kind
                kind_lower = kind.lower()
                if kind_lower in self.type_mapping:
                    mapping = self.type_mapping[kind_lower]
                    issue_type_id = mapping['id']
                    issue_type_name = mapping['name']
                    configured_name = mapping.get('configured_name')
                    display_name = configured_name if configured_name else issue_type_name
                    type_stats['using_native'] += 1
                    type_fallbacks.append((kind, display_name))
                    self.logger.info(f"  Using native issue type: {kind} -> {display_name} (ID: {issue_type_id})")
                else:
                    # Fall back to labels
                    labels.append(f'type: {kind}')
                    type_stats['using_labels'] += 1
                    type_fallbacks.append((kind, None))
                    self.logger.info(f"  Using label fallback for type: {kind}")
            else:
                type_stats['no_type'] += 1

            priority = bb_issue.get('priority')
            if priority:
                labels.append(f'priority: {priority}')

            # Create issue
            gh_issue = self._create_gh_issue(
                title=bb_issue.get('title', f'Issue #{issue_num}'),
                body=body,
                labels=labels,
                state='open' if bb_issue.get('state') in ['new', 'open'] else 'closed',
                assignees=assignees,
                milestone=milestone_number,
                type=issue_type_name
            )

            self.issue_mapping[issue_num] = gh_issue['number']

            # Migrate attachments
            attachments = self._fetch_bb_issue_attachments(issue_num)
            if attachments:
                self.logger.info(f"  Migrating {len(attachments)} attachments...")
                for attachment in attachments:
                    att_name = attachment.get('name', 'unknown')
                    att_url = attachment.get('links', {}).get('self', {}).get('href')

                    if att_url:
                        self.logger.info(f"    Downloading {att_name}...")
                        filepath = self.attachment_handler.download_attachment(att_url, att_name)
                        if filepath:
                            self.logger.info(f"    Creating attachment note on GitHub...")
                            self.attachment_handler.upload_to_github(filepath, gh_issue['number'], self.gh_client, self.gh_client.owner, self.gh_client.repo)

            # Comments will be created in the second pass to avoid duplication

            # Record migration details (comments and links will be updated in second pass)
            self.issue_records.append({
                'bb_number': issue_num,
                'gh_number': gh_issue['number'],
                'title': bb_issue.get('title', f'Issue #{issue_num}'),
                'reporter': reporter,
                'gh_reporter': gh_reporter,
                'state': bb_issue.get('state', 'unknown'),
                'kind': bb_issue.get('kind', None),
                'priority': bb_issue.get('priority', None),
                'comments': 0,  # Will be updated in second pass
                'attachments': len(attachments),
                'links_rewritten': 0,  # Will be updated in second pass
                'bb_url': bb_issue.get('links', {}).get('html', {}).get('href', ''),
                'gh_url': f"https://github.com/{self.gh_client.owner}/{self.gh_client.repo}/issues/{gh_issue['number']}",
                'remarks': []
            })

            self.logger.info(f"  ✓ Created issue #{issue_num} -> #{gh_issue['number']} (content and comments will be added in second pass)")
            expected_num += 1

        # Report type usage statistics
        self.logger.info(f"Issue Type Migration Summary:")
        self.logger.info(f"  Using native issue types: {type_stats['using_native']}")
        self.logger.info(f"  Using labels (fallback): {type_stats['using_labels']}")
        self.logger.info(f"  No type specified: {type_stats['no_type']}")

        if type_fallbacks:
            # Separate native types from label fallbacks
            native_types = [(bb_type, gh_type) for bb_type, gh_type in type_fallbacks if gh_type is not None]
            label_fallbacks = [(bb_type, gh_type) for bb_type, gh_type in type_fallbacks if gh_type is None]

            if native_types:
                self.logger.info(f"  ✓ Successfully mapped to native types:")
                native_summary = {}
                for bb_type, gh_type in native_types:
                    if bb_type not in native_summary:
                        native_summary[bb_type] = (gh_type, 0)
                    native_summary[bb_type] = (gh_type, native_summary[bb_type][1] + 1)
                for bb_type, (gh_type, count) in native_summary.items():
                    self.logger.info(f"    - '{bb_type}' ({count} issues) → GitHub type '{gh_type}'")

            if label_fallbacks:
                self.logger.info(f"\n  ℹ Types that fell back to labels:")
                fallback_summary = {}
                for bb_type, gh_type in label_fallbacks:
                    fallback_summary[bb_type] = fallback_summary.get(bb_type, 0) + 1
                for bb_type, count in fallback_summary.items():
                    self.logger.info(f"    - '{bb_type}' ({count} issues) → Label 'type: {bb_type}'")

        return self.issue_records, type_stats, type_fallbacks

    def _create_gh_issue(self, title: str, body: str, labels: Optional[List[str]] = None,
                          state: str = 'open', assignees: Optional[List[str]] = None,
                          milestone: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """
        Create a GitHub issue.

        Args:
            title: Issue title
            body: Issue body content
            labels: Optional list of label names
            state: Issue state ('open' or 'closed')
            assignees: Optional list of GitHub usernames to assign
            milestone: Optional milestone number
            **kwargs: Additional issue parameters (e.g., issue_type)

        Returns:
            Created GitHub issue data
        """
        try:
            issue = self.gh_client.create_issue(
                title=title,
                body=body,
                labels=labels,
                state=state,
                assignees=assignees,
                milestone=milestone,
                **kwargs
            )

            # Close if needed
            if state == 'closed':
                self.gh_client.update_issue(issue['number'], state='closed')

            return issue

        except (APIError, AuthenticationError, NetworkError, ValidationError):
            raise  # Re-raise client exceptions
        except Exception as e:
            self.logger.error(f"  ERROR: Unexpected error creating issue: {e}")
            raise MigrationError(f"Unexpected error creating GitHub issue: {e}")

    def _create_gh_comment(self, issue_number: int, body: str) -> Dict[str, Any]:
        """
        Create a comment on a GitHub issue.

        Args:
            issue_number: The issue number
            body: Comment text

        Returns:
            Created comment data
        """
        try:
            return self.gh_client.create_comment(issue_number, body)
        except (APIError, AuthenticationError, NetworkError, ValidationError):
            raise  # Re-raise client exceptions
        except Exception as e:
            self.logger.error(f"  ERROR: Unexpected error creating comment: {e}")
            raise MigrationError(f"Unexpected error creating GitHub comment: {e}")

    def _fetch_bb_issue_attachments(self, issue_id: int) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a Bitbucket issue.

        Args:
            issue_id: The Bitbucket issue ID

        Returns:
            List of attachment dictionaries
        """
        try:
            return self.bb_client.get_attachments("issue", issue_id)
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"    Warning: Could not fetch issue attachments: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"    Warning: Unexpected error fetching issue attachments: {e}")
            return []

    def _fetch_bb_issue_comments(self, issue_id: int) -> List[Dict[str, Any]]:
        """
        Fetch comments for a Bitbucket issue.

        Args:
            issue_id: The Bitbucket issue ID

        Returns:
            List of comment dictionaries
        """
        try:
            return self.bb_client.get_comments("issue", issue_id)
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"    Warning: Could not fetch issue comments: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"    Warning: Unexpected error fetching issue comments: {e}")
            return []

    def _fetch_bb_issue_changes(self, issue_id: int) -> List[Dict[str, Any]]:
        """
        Fetch changes for a Bitbucket issue.

        Changes represent modifications to the issue (e.g., status, assignee)
        that are associated with comments. This is used to enhance comment
        bodies with the underlying change details.

        Args:
            issue_id: The Bitbucket issue ID

        Returns:
            List of change dictionaries
        """
        try:
            return self.bb_client.get_changes(issue_id)
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"    Warning: Could not fetch issue changes: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"    Warning: Unexpected error fetching issue changes: {e}")
            return []

    def _get_next_gh_number(self) -> int:
        """
        Get the next expected GitHub issue number.

        Returns:
            Next GitHub issue number
        """
        # This is a simplified implementation; in practice, you'd track this more carefully
        return len(self.issue_mapping) + 1

    def _sort_comments_topologically(self, comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort comments topologically based on parent relationships (parents before children).

        Args:
            comments: List of Bitbucket comment dictionaries

        Returns:
            Sorted list of comments
        """
        # Build graph: comment_id -> list of children
        graph = {}
        in_degree = {}
        comment_map = {comment['id']: comment for comment in comments}

        for comment in comments:
            comment_id = comment['id']
            parent_id = comment.get('parent', {}).get('id') if comment.get('parent') else None
            graph[comment_id] = []
            in_degree[comment_id] = 0

        for comment in comments:
            comment_id = comment['id']
            parent_id = comment.get('parent', {}).get('id') if comment.get('parent') else None
            if parent_id and parent_id in comment_map:
                graph[parent_id].append(comment_id)
                in_degree[comment_id] += 1

        # Topological sort using Kahn's algorithm
        queue = [cid for cid in in_degree if in_degree[cid] == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(comment_map[current])
            for child in graph[current]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        # If there are cycles or missing parents, append remaining comments
        remaining = [comment_map[cid] for cid in in_degree if in_degree[cid] > 0]
        result.extend(remaining)

        return result

    def update_issue_content(self, bb_issue: Dict[str, Any], gh_issue_number: int) -> None:
        """
        Update the content of a GitHub issue with rewritten links and create comments after mappings are established.

        Args:
            bb_issue: The original Bitbucket issue data
            gh_issue_number: The GitHub issue number
        """
        issue_num = bb_issue['id']

        # Format and update issue body
        formatter = self.formatter_factory.get_issue_formatter()
        body, links_in_body, inline_images_body = formatter.format(bb_issue, skip_link_rewriting=False, use_gh_cli=self.attachment_handler.use_gh_cli)

        # Track inline images as attachments
        for img in inline_images_body:
            self.attachment_handler.attachments.append({
                'issue_number': issue_num,
                'github_issue': gh_issue_number,
                'filename': img['filename'],
                'filepath': img['filepath'],
                'type': 'inline_image'
            })

        # Update the issue body
        try:
            self.gh_client.update_issue(gh_issue_number, body=body)
            self.logger.info(f"  Updated issue #{gh_issue_number} with rewritten links")
        except Exception as e:
            self.logger.warning(f"  Warning: Could not update issue #{gh_issue_number}: {e}")

        # Create comments
        comments = self._fetch_bb_issue_comments(issue_num)
        # Fetch changes for the issue to enhance comments with change details
        changes = self._fetch_bb_issue_changes(issue_num)

        # Create mapping from comment ID to associated changes
        from collections import defaultdict
        comment_changes = defaultdict(list)
        for change in changes:
            comment_id = change.get('id')
            if comment_id:
                comment_changes[comment_id].append(change)

        # Sort comments topologically (parents before children)
        sorted_comments = self._sort_comments_topologically(comments)
        links_in_comments = 0
        migrated_comments_count = 0
        for comment in sorted_comments:
            # Check for deleted field
            if comment.get('deleted', False):
                self.logger.info(f"  Skipping deleted comment on issue #{issue_num}")
                continue

            # Check for pending field and annotate if true
            is_pending = comment.get('pending', False)
            if is_pending:
                self.logger.info(f"  Annotating pending comment on issue #{issue_num}")

            # Format comment
            formatter = self.formatter_factory.get_comment_formatter()
            comment_body, comment_links, inline_images_comment = formatter.format(comment, item_type='issue', item_number=issue_num, skip_link_rewriting=False, use_gh_cli=self.attachment_handler.use_gh_cli, changes=comment_changes[comment['id']])
            links_in_comments += comment_links

            # Add annotation for pending
            if is_pending:
                comment_body = f"**[PENDING APPROVAL]**\n\n{comment_body}"

            # Track inline images from comments
            for img in inline_images_comment:
                self.attachment_handler.attachments.append({
                    'issue_number': issue_num,
                    'github_issue': gh_issue_number,
                    'filename': img['filename'],
                    'filepath': img['filepath'],
                    'type': 'inline_image_comment'
                })

            parent_id = comment.get('parent', {}).get('id') if comment.get('parent') else None
            if parent_id:
                # Add note for reply since GitHub issue comments don't support threading
                comment_body = f"**[Reply to Bitbucket Comment {parent_id}]**\n\n{comment_body}"
            gh_comment = self._create_gh_comment(gh_issue_number, comment_body)
            self.comment_mapping[comment['id']] = gh_comment['id']
            migrated_comments_count += 1

        # Update the record with actual counts
        for record in self.issue_records:
            if record['gh_number'] == gh_issue_number:
                record['comments'] = migrated_comments_count
                record['links_rewritten'] = links_in_body + links_in_comments
                # record['remarks'].append('Content and comments updated')
                break

        self.logger.info(f"  ✓ Updated issue #{gh_issue_number} with {migrated_comments_count} comments and {links_in_body + links_in_comments} links rewritten")

    def update_issue_comments(self, bb_issue: Dict[str, Any], gh_issue_number: int) -> None:
        """
        Comments are now created in update_issue_content to avoid duplication.
        This method is kept for compatibility but does nothing.

        Args:
            bb_issue: The original Bitbucket issue data
            gh_issue_number: The GitHub issue number
        """
        # Comments are handled in update_issue_content
        pass