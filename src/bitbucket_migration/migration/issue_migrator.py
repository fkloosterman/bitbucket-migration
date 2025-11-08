"""
Issue migrator for Bitbucket to GitHub migration.

This module contains the IssueMigrator class that handles the migration
of Bitbucket issues to GitHub issues, including comments, attachments,
and metadata preservation.
"""

from typing import List, Dict, Any, Optional
import time

from ..exceptions import MigrationError, APIError, AuthenticationError, NetworkError, ValidationError

from ..core.migration_context import MigrationEnvironment, MigrationState

class IssueMigrator:
    """
    Handles migration of Bitbucket issues to GitHub.

    This class encapsulates all logic related to issue migration, including
    fetching, creating, and updating issues, as well as handling attachments
    and comments.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the IssueMigrator.

        Args:
            environment: Migration environment containing all services and configuration
            state: Migration state containing mappings and records
        """

        self.environment = environment
        self.state = state

        self.logger = self.environment.logger

        self.user_mapper = self.environment.services.get('user_mapper')
        self.link_rewriter = self.environment.services.get('link_rewriter')
        self.attachment_handler = self.environment.services.get('attachment_handler')
        self.formatter_factory = self.environment.services.get('formatter_factory')
        self.type_mapping = self.state.mappings.issue_types

    def migrate_issues(self, bb_issues: List[Dict[str, Any]],
                        open_issues_only: bool = False) -> List[Dict[str, Any]]:
        """
        Migrate all Bitbucket issues to GitHub.

        Args:
            bb_issues: List of Bitbucket issues to migrate
            open_issues_only: If True, only migrate open issues

        Returns:
            List of migration records
        """
        milestone_lookup = self.state.mappings.milestones

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
                self.state.mappings.issues[expected_num] = placeholder['number']

                # Record placeholder for report
                self.state.issue_records.append({
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
                    'gh_url': f"https://github.com/{self.environment.clients.gh.owner}/{self.environment.clients.gh.repo}/issues/{placeholder['number']}",
                    'remarks': ['Placeholder for deleted/missing issue']
                })

                expected_num += 1

            if open_issues_only and bb_issue.get('state', 'open') not in ['open', 'new']:
                self.logger.info(f"Skipping migration of closed issue #{issue_num}: {bb_issue.get('title', 'No title')}")
                continue

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
                    self.logger.info(f"  Assigning to milestone: {milestone_name} (#{milestone_number})")
                elif milestone_name:
                    self.logger.warning(f"  Milestone '{milestone_name}' not found in lookup - issue will not be assigned to a milestone")

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

            self.state.mappings.issues[issue_num] = gh_issue['number']

            # Migrate attachments
            attachments = self._fetch_bb_issue_attachments(issue_num)
            if attachments:
                self.logger.info(f"  Migrating {len(attachments)} attachments...")
                for attachment in attachments:
                    att_name = attachment.get('name', 'unknown')
                    att_url = attachment.get('links', {}).get('self', {}).get('href')

                    if att_url:
                        self.logger.info(f"    Downloading {att_name}...")
                        # Handle cases where href might be a list or string - with intelligent URL selection
                        original_att_url = att_url
                        if isinstance(att_url, list):
                            if not att_url:
                                att_url = None
                                self.logger.warning(f"    Warning: Empty URL list for attachment {att_name}")
                            elif len(att_url) == 1:
                                att_url = att_url[0]
                                self.logger.info(f"    Selected URL from single-item list for {att_name}")
                            else:
                                # Multiple URLs - choose the best one
                                self.logger.info(f"    Found {len(att_url)} URLs for {att_name}, selecting best...")
                                for url in att_url:
                                    if 'api.bitbucket.org' in url:
                                        att_url = url
                                        self.logger.info(f"    Selected primary API URL for {att_name}")
                                        break
                                else:
                                    # Fall back to first URL if no preferred pattern found
                                    att_url = att_url[0]
                                    self.logger.info(f"    Selected first URL from {len(att_url)} options for {att_name}")
                        
                        if att_url:
                            filepath = self.attachment_handler.download_attachment(att_url, att_name, item_type='issue', item_number=issue_num)
                            if filepath:
                                self.logger.info(f"    Creating attachment note on GitHub...")
                                self.attachment_handler.upload_to_github(filepath, gh_issue['number'])
                        else:
                            self.logger.warning(f"    Warning: No valid URL found for attachment {att_name}")

            # Comments will be created in the second pass to avoid duplication

            # Record migration details (comments and links will be updated in second pass)
            self.state.issue_records.append({
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
                'gh_url': f"https://github.com/{self.environment.clients.gh.owner}/{self.environment.clients.gh.repo}/issues/{gh_issue['number']}",
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

        return self.state.issue_records, type_stats, type_fallbacks

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
            issue = self.environment.clients.gh.create_issue(
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
                self.environment.clients.gh.update_issue(issue['number'], state='closed')

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
            return self.environment.clients.gh.create_comment(issue_number, body)
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
            return self.environment.clients.bb.get_attachments("issue", issue_id)
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
            return self.environment.clients.bb.get_comments("issue", issue_id)
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
            return self.environment.clients.bb.get_changes(issue_id)
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"    Warning: Could not fetch issue changes: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"    Warning: Unexpected error fetching issue changes: {e}")
            return []

    def _format_date(self, date_str: str) -> str:
        """
        Format a date string to a more readable format with UTC timezone.

        Args:
            date_str: ISO 8601 date string

        Returns:
            Formatted date string like "March 5, 2020 at 12:44 PM UTC"
        """
        if not date_str:
            return ''
        try:
            from datetime import datetime
            # Parse the ISO format
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Format to readable string with UTC
            return dt.strftime('%B %d, %Y at %I:%M %p UTC')
        except ValueError:
            # If parsing fails, return as is
            return date_str

    def _get_next_gh_number(self) -> int:
        """
        Get the next expected GitHub issue number.

        Returns:
            Next GitHub issue number
        """
        # This is a simplified implementation; in practice, you'd track this more carefully
        return len(self.state.mappings.issues) + 1

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
        body, links_in_body, inline_images_body = formatter.format(bb_issue, skip_link_rewriting=False)

        # Inline images are already tracked by the formatter, no need to duplicate

        # Update the issue body
        try:
            self.environment.clients.gh.update_issue(gh_issue_number, body=body)
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
        description_changes = []  # Track changes to issue description
        other_changes = []  # Track other issue-level changes (status, assignee, etc.)

        self.logger.info(f"Processing {len(changes)} changes for issue #{issue_num}")
        for change in changes:
            comment_id = change.get('id')
            change_data = change.get('changes', {})

            # Classify the change based on the logic provided
            if 'content' in change_data:
                # This is a content change - could be issue description or comment edit
                if comment_id:
                    # Has comment_id - check if corresponding comment has content
                    # We'll handle this during comment processing
                    comment_changes[comment_id].append(change)
                    self.logger.info(f"  Content change with comment_id {comment_id} - will check comment content")
                else:
                    # No comment_id - this is definitely an issue description change
                    self.logger.info(f"  Issue description change detected: {change}")
                    description_changes.append(change)
            elif comment_id:
                # Has comment_id but no content change - regular comment change
                comment_changes[comment_id].append(change)
                self.logger.info(f"  Regular comment change for comment_id {comment_id}")
            else:
                # No comment_id and no content change - other issue-level change
                self.logger.info(f"  Other issue change detected: {change}")
                other_changes.append(change)

        # Sort comments topologically (parents before children)
        sorted_comments = self._sort_comments_topologically(comments)
        self.logger.info(f"Processing {len(sorted_comments)} comments for issue #{issue_num}")
        links_in_comments = 0
        migrated_comments_count = 0
        comment_seq = 0
        for comment in sorted_comments:
            # Check for deleted field
            if comment.get('deleted', False):
                self.logger.info(f"  Skipping deleted comment on issue #{issue_num}")
                continue

            # Check for pending field and annotate if true
            is_pending = comment.get('pending', False)
            if is_pending:
                self.logger.info(f"  Annotating pending comment on issue #{issue_num}")

            # Debug logging for comment content
            comment_id = comment.get('id')
            content = comment.get('content', {}).get('raw', '')
            content_length = len(content) if content else 0
            self.logger.info(f"  Processing comment ID {comment_id}: content length = {content_length}")

            # Check if this comment corresponds to a description change
            associated_changes = comment_changes.get(comment_id, [])
            has_content_change = any('content' in change.get('changes', {}) for change in associated_changes)

            if not content and has_content_change:
                # This is a description change comment (empty content + content change = description edit)
                self.logger.info(f"  Empty comment {comment_id} corresponds to a description change - moving to description_changes")
                
                # Move the associated changes from comment_changes to description_changes
                for change in associated_changes:
                    if 'content' in change.get('changes', {}):
                        description_changes.append(change)
                
                # Skip creating a comment for this empty comment entry
                continue
            elif not content:
                # Empty comment with no associated changes - skip it
                self.logger.info(f"  Skipping empty comment {comment_id} with no changes")
                continue
            elif content and has_content_change:
                # This is a comment edit - the formatter will handle showing the change history
                self.logger.info(f"  Processing comment edit for comment_id {comment_id}")
            else:
                # Regular comment with no changes
                self.logger.info(f"  Processing regular comment {comment_id}")

            # Increment comment sequence
            comment_seq += 1

            # Format comment
            formatter = self.formatter_factory.get_comment_formatter()
            comment_body, comment_links, inline_images_comment = formatter.format(comment, item_type='issue', item_number=issue_num, comment_seq=comment_seq, skip_link_rewriting=False, changes=comment_changes[comment['id']])
            links_in_comments += comment_links

            # Add annotation for pending
            if is_pending:
                comment_body = f"**[PENDING APPROVAL]**\n\n{comment_body}"

            # Inline images from comments are already tracked by the formatter, no need to duplicate

            parent_id = comment.get('parent', {}).get('id') if comment.get('parent') else None
            if parent_id:
                # Check if parent was successfully migrated
                parent_comment = self.state.mappings.issue_comments.get(parent_id)
                if parent_comment:
                    # Create link to parent comment on GitHub
                    # Format: https://github.com/owner/repo/issues/123#issuecomment-456
                    parent_url = f"https://github.com/{self.environment.clients.gh.owner}/{self.environment.clients.gh.repo}/issues/{gh_issue_number}#issuecomment-{parent_comment['gh_id']}"
                    
                    # Optionally get parent comment body for quoting
                    # parent_comment_data = self.state.mappings.issue_comments.get(f"{parent_id}_data")
                    if 'body' in parent_comment:
                        # Extract first line or first 100 chars of parent for quote
                        parent_body = parent_comment['body']
                        parent_preview = parent_body.split('\n')[0][:100]
                        if len(parent_body.split('\n')[0]) > 100:
                            parent_preview += "..."
                        
                        reply_note = f"**[In reply to [this comment]({parent_url})]**\n> {parent_preview}\n\n"
                    else:
                        reply_note = f"**[In reply to [this comment]({parent_url})]**\n\n"
                    
                    comment_body = reply_note + comment_body
                else:
                    # Parent not migrated yet or not found
                    self.logger.warning(f"  Parent comment {parent_id} not found in mapping for reply")
                    comment_body = f"**[In reply to Bitbucket comment {parent_id}]**\n\n{comment_body}"
            
            try:
                gh_comment = self._create_gh_comment(gh_issue_number, comment_body)
                self.state.mappings.issue_comments[comment['id']] = {
                    'gh_id': gh_comment['id'],
                    # Store comment data for potential child replies
                    'body': comment_body
                    }
            except ValidationError as e:
                if 'locked' in str(e).lower():
                    self.logger.warning(f"  Skipping comment on locked issue #{gh_issue_number}: {e}")
                else:
                    raise
            migrated_comments_count += 1

            # Add rate limiting delay between comments to avoid secondary rate limits
            # GitHub recommends at least 1 second between mutative requests (POST/PATCH/PUT/DELETE)
            time.sleep(self.environment.config.options.request_delay_seconds)

        # Create comments for issue description changes
        self.logger.info(f"Creating {len(description_changes)} description change comments for issue #{issue_num}")
        for change in description_changes:
            # Check if this is a content change (description edit)
            if 'content' in change.get('changes', {}):
                change_date = change.get('created_on', '')
                formatted_date = self._format_date(change_date) if hasattr(self, '_format_date') else change_date

                # Get author if available
                author = change.get('user', {})
                if author:
                    author_name = author.get('display_name', 'Unknown')
                    gh_author = self.user_mapper.map_user(author_name)
                    author_mention = f"@{gh_author}" if gh_author else f"**{author_name}**"
                else:
                    author_mention = "**Unknown**"

                change_comment = f"**Description edited by {author_mention} on {formatted_date}**"
                self.logger.info(f"  Creating description change comment: {change_comment}")
                try:
                    self._create_gh_comment(gh_issue_number, change_comment)
                    migrated_comments_count += 1
                except ValidationError as e:
                    if 'locked' in str(e).lower():
                        self.logger.warning(f"  Skipping description change comment on locked issue #{gh_issue_number}: {e}")
                    else:
                        raise

                # Add rate limiting delay between comments to avoid secondary rate limits
                # GitHub recommends at least 1 second between mutative requests (POST/PATCH/PUT/DELETE)
                time.sleep(self.environment.config.options.request_delay_seconds)

        # Create comments for other issue-level changes (status, assignee, etc.)
        self.logger.info(f"Creating {len(other_changes)} other issue change comments for issue #{issue_num}")
        for change in other_changes:
            change_data = change.get('changes', {})
            self.logger.info(f"  Processing other change: {change}")

            change_date = change.get('created_on', '')
            formatted_date = self._format_date(change_date) if hasattr(self, '_format_date') else change_date

            # Get author if available
            author = change.get('user', {})
            if author:
                author_name = author.get('display_name', 'Unknown')
                gh_author = self.user_mapper.map_user(author_name)
                author_mention = f"@{gh_author}" if gh_author else f"**{author_name}**"
            else:
                author_mention = "**Unknown**"

            # Build change description
            change_parts = []
            for field, field_change in change_data.items():
                old_val = field_change.get('old')
                new_val = field_change.get('new')
                if old_val != new_val:
                    if field == 'assignee':
                        old_name = old_val.get('display_name', 'None') if old_val else 'None'
                        new_name = new_val.get('display_name', 'None') if new_val else 'None'
                        change_parts.append(f"Assignee changed from '{old_name}' to '{new_name}'")
                    elif field == 'state':
                        change_parts.append(f"Status changed from '{old_val}' to '{new_val}'")
                    elif field == 'kind':
                        change_parts.append(f"Type changed from '{old_val}' to '{new_val}'")
                    elif field == 'priority':
                        change_parts.append(f"Priority changed from '{old_val}' to '{new_val}'")
                    elif field == 'title':
                        change_parts.append(f"Title changed from '{old_val}' to '{new_val}'")
                    elif field == 'milestone':
                        old_name = old_val.get('name', 'None') if old_val else 'None'
                        new_name = new_val.get('name', 'None') if new_val else 'None'
                        change_parts.append(f"Milestone changed from '{old_name}' to '{new_name}'")
                    else:
                        change_parts.append(f"{field.capitalize()} changed from '{old_val}' to '{new_val}'")

            if change_parts:
                change_comment = f"**Issue updated by {author_mention} on {formatted_date}:**\n- " + "\n- ".join(change_parts)
                self.logger.info(f"  Creating issue change comment: {change_comment}")
                try:
                    self._create_gh_comment(gh_issue_number, change_comment)
                    migrated_comments_count += 1
                except ValidationError as e:
                    if 'locked' in str(e).lower():
                        self.logger.warning(f"  Skipping issue change comment on locked issue #{gh_issue_number}: {e}")
                    else:
                        raise

                # Add rate limiting delay between comments to avoid secondary rate limits
                # GitHub recommends at least 1 second between mutative requests (POST/PATCH/PUT/DELETE)
                time.sleep(self.environment.config.options.request_delay_seconds)

        # Update the record with actual counts
        for record in self.state.issue_records:
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