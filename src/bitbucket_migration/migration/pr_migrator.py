"""
Pull request migrator for Bitbucket to GitHub migration.

This module contains the PullRequestMigrator class that handles the migration
of Bitbucket pull requests to GitHub, with intelligent branch checking and
strategy for handling different PR states.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import time

from ..exceptions import MigrationError, APIError, AuthenticationError, NetworkError, ValidationError

from ..core.migration_context import MigrationEnvironment, MigrationState

class PullRequestMigrator:
    """
    Handles migration of Bitbucket pull requests to GitHub.

    This class encapsulates all logic related to PR migration, including
    branch existence checking, state-based migration strategies, and
    handling attachments and comments.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the PullRequestMigrator.

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
        
        # Migration statistics
        self.state.pr_migration_stats = {
            'prs_as_prs': 0,  # Open PRs that became GitHub PRs
            'prs_as_issues': 0,  # PRs that became GitHub issues
            'pr_branch_missing': 0,  # PRs that couldn't be migrated due to missing branches
            'pr_merged_as_issue': 0,  # Merged PRs migrated as issues (safest approach)
        }

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
            # Parse the ISO format
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Format to readable string with UTC
            return dt.strftime('%B %d, %Y at %I:%M %p UTC')
        except ValueError:
            # If parsing fails, return as is
            return date_str

    def migrate_pull_requests(self, bb_prs: List[Dict[str, Any]],
                                skip_pr_as_issue: bool = False,
                                open_prs_only: bool = False) -> List[Dict[str, Any]]:
        """
        Migrate Bitbucket PRs to GitHub with intelligent branch checking.

        Strategy:
        - OPEN PRs: Try to create as GitHub PRs (if branches exist)
        - MERGED/DECLINED/SUPERSEDED PRs: Always migrate as issues (safest approach)

        Args:
            bb_prs: List of Bitbucket pull requests to migrate
            skip_pr_as_issue: Whether to skip migrating closed PRs as issues
            open_prs_only: If True, only migrate open PRs

        Returns:
            List of migration records
        """
        milestone_lookup = self.state.mappings.milestones

        self.logger.info("="*80)
        self.logger.info("PHASE 2: Migrating Pull Requests")
        self.logger.info("="*80)

        if not bb_prs:
            self.logger.info("No pull requests to migrate")
            return []

        for bb_pr in bb_prs:
            pr_num = bb_pr['id']
            pr_state = bb_pr.get('state', 'UNKNOWN')
            title = bb_pr.get('title', f'PR #{pr_num}')
            source_branch = bb_pr.get('source', {}).get('branch', {}).get('name')
            dest_branch = bb_pr.get('destination', {}).get('branch', {}).get('name', 'main')

            self.logger.info(f"Migrating PR #{pr_num} ({pr_state}): {title}")
            self.logger.info(f"  Source: {source_branch} -> Destination: {dest_branch}")

            # Strategy: Only OPEN PRs become GitHub PRs (safest approach)
            if pr_state == 'OPEN':
                if source_branch and dest_branch:
                    # Check if both branches exist on GitHub
                    self.logger.info(f"  Checking branch existence on GitHub...")
                    source_exists = self.environment.clients.gh.check_branch_exists(source_branch)
                    dest_exists = self.environment.clients.gh.check_branch_exists(dest_branch)

                    if source_exists and dest_exists:
                        # Try to create as actual GitHub PR
                        self.logger.info(f"  ✓ Both branches exist, creating as GitHub PR")

                        # Use minimal body in first pass to avoid duplication
                        body = f"Migrating PR #{pr_num} from Bitbucket. Content will be updated in second pass."

                        # Map milestone for PRs
                        milestone_number = None
                        if bb_pr.get('milestone'):
                            milestone_name = bb_pr['milestone'].get('name')
                            if milestone_name and milestone_name in milestone_lookup:
                                milestone_number = milestone_lookup[milestone_name].get('number')
                                self.logger.info(f"  Assigning to milestone: {milestone_name} (#{milestone_number})")
                            elif milestone_name:
                                self.logger.warning(f"  Milestone '{milestone_name}' not found in lookup - PR will not be assigned to a milestone")

                        # Note: Inline images will be handled in second pass

                        try:
                            gh_pr = self._create_gh_pr(
                                title=title,
                                body=body,
                                head=source_branch,
                                base=dest_branch
                            )
                        except ValidationError as e:
                            self.logger.warning(f"  ✗ Failed to create GitHub PR: {e}. Falling back to issue migration.")
                            gh_pr = None

                        # Apply milestone to PR (must be done after creation)
                        if milestone_number and gh_pr:
                            try:
                                self.environment.clients.gh.update_issue(gh_pr['number'], milestone=milestone_number)
                                self.logger.info(f"  ✓ Applied milestone to PR #{gh_pr['number']}")
                            except (APIError, AuthenticationError, NetworkError, ValidationError) as e:
                                self.logger.warning(f"  ⚠️  Warning: Could not apply milestone to PR #{gh_pr['number']}: {e}")
                            except Exception as e:
                                self.logger.warning(f"  ⚠️  Warning: Unexpected error applying milestone to PR #{gh_pr['number']}: {e}")

                        if gh_pr:
                            self.state.mappings.prs[pr_num] = gh_pr['number']
                            self.state.pr_migration_stats['prs_as_prs'] += 1

                            # Apply labels to the migrated PR
                            labels = ['migrated-from-bitbucket']
                            try:
                                self.environment.clients.gh.update_issue(gh_pr['number'], labels=labels)
                                self.logger.info(f"    Applied labels to PR #{gh_pr['number']}")
                            except (APIError, AuthenticationError, NetworkError, ValidationError):
                                self.logger.warning(f"    Warning: Could not apply labels to PR")
                            except Exception as e:
                                self.logger.warning(f"    Warning: Unexpected error applying labels to PR: {e}")

                            # Get commit_id for inline comments
                            commit_id = gh_pr.get('head', {}).get('sha')

                            # Record PR migration details
                            author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
                            gh_author = self.user_mapper.map_user(author) if author != 'Unknown (deleted user)' else None

                            # Comments will be created in the second pass to avoid duplication

                            self.state.pr_records.append({
                                'bb_number': pr_num,
                                'gh_number': gh_pr['number'],
                                'gh_type': 'PR',
                                'title': title,
                                'author': author,
                                'gh_author': gh_author,
                                'state': pr_state,
                                'source_branch': source_branch,
                                'dest_branch': dest_branch,
                                'comments': 0,  # Will be updated in second pass
                                'attachments': 0,  # Will be updated after fetching
                                'links_rewritten': 0,  # Will be updated in second pass
                                'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                                'gh_url': f"https://github.com/{self.environment.clients.gh.owner}/{self.environment.clients.gh.repo}/pull/{gh_pr['number']}",
                                'remarks': ['Migrated as GitHub PR', 'Branches exist on GitHub']
                            })

                            # Migrate PR attachments
                            pr_attachments = self._fetch_bb_pr_attachments(pr_num)
                            if pr_attachments:
                                self.logger.info(f"  Migrating {len(pr_attachments)} PR attachments...")
                                for attachment in pr_attachments:
                                    att_name = attachment.get('name', 'unknown')
                                    att_url = attachment.get('links', {}).get('self', {}).get('href')

                                    if att_url:
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
                                            self.logger.info(f"    Processing {att_name}...")
                                            filepath = self.attachment_handler.download_attachment(att_url, att_name, item_type='pr', item_number=pr_num)
                                            if filepath:
                                                self.attachment_handler.upload_to_github(filepath, gh_pr['number'])
                                        else:
                                            self.logger.warning(f"    Warning: No valid URL found for attachment {att_name}")

                            # Update the record with attachments count
                            for record in self.state.pr_records:
                                if record['gh_number'] == gh_pr['number']:
                                    record['attachments'] = len(pr_attachments)
                                    break

                            self.logger.info(f"  ✓ Created PR #{gh_pr['number']} (content and comments will be added in second pass)")
                            continue
                        else:
                            self.logger.info(f"  ✗ Failed to create GitHub PR, falling back to issue migration")
                    else:
                        # Branches don't exist
                        self.logger.info(f"  ✗ Cannot create as PR - branches missing on GitHub")
                        self.state.pr_migration_stats['pr_branch_missing'] += 1
                else:
                    self.logger.info(f"  ✗ Missing branch information in Bitbucket data")
            else:
                # MERGED, DECLINED, or SUPERSEDED - always migrate as issue
                if open_prs_only:
                    self.logger.info(f"  → Skipping migration of {pr_state} PR")
                elif skip_pr_as_issue:
                    self.logger.info(f"  → Skipping migration as issue (PR was {pr_state}, --skip-pr-as-issue enabled)")
                else:
                    self.logger.info(f"  → Migrating as issue (PR was {pr_state} - safest approach)")

                if pr_state in ['MERGED', 'SUPERSEDED']:
                    self.state.pr_migration_stats['pr_merged_as_issue'] += 1

            # Skip or migrate as issue based on flag
            if skip_pr_as_issue or (open_prs_only and pr_state != 'OPEN'):
                self.logger.info(f"  ✓ Skipped PR #{pr_num}")

                # Still record PR details for report
                author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
                gh_author = self.user_mapper.map_user(author) if author != 'Unknown (deleted user)' else None

                # Determine remarks
                remarks = ['Not migrated']
                if pr_state in ['MERGED', 'SUPERSEDED']:
                    remarks.append('Original PR was merged')
                elif pr_state == 'DECLINED':
                    remarks.append('Original PR was declined')
                if not source_branch or not dest_branch:
                    remarks.append('Branch information missing')
                elif not self.environment.clients.gh.check_branch_exists(source_branch) or not self.environment.clients.gh.check_branch_exists(dest_branch):
                    remarks.append('One or both branches do not exist on GitHub')

                self.state.pr_records.append({
                    'bb_number': pr_num,
                    'gh_number': None,  # Not migrated
                    'gh_type': 'Skipped',
                    'title': title,
                    'author': author,
                    'gh_author': gh_author,
                    'state': pr_state,
                    'source_branch': source_branch or 'unknown',
                    'dest_branch': dest_branch or 'unknown',
                    'comments': 0,  # Not migrated, so no comments counted
                    'attachments': 0,  # Not migrated, so no attachments counted
                    'links_rewritten': 0,
                    'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                    'gh_url': '',  # No GitHub URL since not migrated
                    'remarks': remarks
                })

                continue  # Skip to next PR

            # Migrate as issue (for all non-open PRs or failed PR creation)
            self.logger.info(f"  Creating as GitHub issue...")

            # Use minimal body in first pass to avoid duplication
            body = f"Migrating PR #{pr_num} as issue from Bitbucket. Content will be updated in second pass."

            # Map milestone for PRs migrated as issues
            milestone_number = None
            if bb_pr.get('milestone'):
                milestone_name = bb_pr['milestone'].get('name')
                if milestone_name and milestone_name in milestone_lookup:
                    milestone_number = milestone_lookup[milestone_name].get('number')
                    self.logger.info(f"  Assigning to milestone: {milestone_name} (#{milestone_number})")
                elif milestone_name:
                    self.logger.warning(f"  Milestone '{milestone_name}' not found in lookup - PR-as-issue will not be assigned to a milestone")

            # Note: Inline images will be handled in second pass

            # Determine labels based on original state
            labels = ['migrated-from-bitbucket', 'original-pr']
            if pr_state == 'MERGED':
                labels.append('pr-merged')
            elif pr_state == 'DECLINED':
                labels.append('pr-declined')
            elif pr_state == 'SUPERSEDED':
                labels.append('pr-superseded')

            gh_issue = self._create_gh_issue(
                title=f"[PR #{pr_num}] {title}",
                body=body,
                labels=labels,
                state='closed',  # Always close migrated PRs that are now issues
                milestone=milestone_number
            )

            self.state.mappings.prs[pr_num] = gh_issue['number']
            self.state.pr_migration_stats['prs_as_issues'] += 1

            # Get commit_id for inline comments
            commit_id = None
            if source_branch:
                try:
                    response = self.environment.clients.gh.session.get(f"{self.environment.clients.gh.base_url}/branches/{source_branch}")
                    response.raise_for_status()
                    commit_id = response.json()['commit']['sha']
                    self.logger.info(f"  Commit ID fetched for branch {source_branch}: {commit_id}")
                except Exception:
                    # Expected for PRs migrated as issues if branch doesn't exist
                    commit_id = None

            # Comments will be created in the second pass to avoid duplication

            # Record PR-as-issue migration details
            author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
            gh_author = self.user_mapper.map_user(author) if author != 'Unknown (deleted user)' else None

            # Determine remarks
            remarks = ['Migrated as GitHub Issue']
            if pr_state in ['MERGED', 'SUPERSEDED']:
                remarks.append('Original PR was merged - safer as issue to avoid re-merge')
            elif pr_state == 'DECLINED':
                remarks.append('Original PR was declined')
            if not source_branch or not dest_branch:
                remarks.append('Branch information missing')
            elif not self.environment.clients.gh.check_branch_exists(source_branch) or not self.environment.clients.gh.check_branch_exists(dest_branch):
                remarks.append('One or both branches do not exist on GitHub')

            self.state.pr_records.append({
                'bb_number': pr_num,
                'gh_number': gh_issue['number'],
                'gh_type': 'Issue',
                'title': title,
                'author': author,
                'gh_author': gh_author,
                'state': pr_state,
                'source_branch': source_branch or 'unknown',
                'dest_branch': dest_branch or 'unknown',
                'comments': 0,  # Will be updated in second pass
                'attachments': 0,  # Will be updated after fetching
                'links_rewritten': 0,  # Will be updated in second pass
                'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                'gh_url': f"https://github.com/{self.environment.clients.gh.owner}/{self.environment.clients.gh.repo}/issues/{gh_issue['number']}",
                'remarks': remarks
            })

            self.logger.info(f"  ✓ Created Issue #{gh_issue['number']} (content and comments will be added in second pass)")

            # Migrate PR attachments
            pr_attachments = self._fetch_bb_pr_attachments(pr_num)
            if pr_attachments:
                self.logger.info(f"  Migrating {len(pr_attachments)} PR attachments...")
                for attachment in pr_attachments:
                    att_name = attachment.get('name', 'unknown')
                    att_url = attachment.get('links', {}).get('self', {}).get('href')

                    if att_url:
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
                            self.logger.info(f"    Downloading {att_name}...")
                            filepath = self.attachment_handler.download_attachment(att_url, att_name, item_type='pr', item_number=pr_num)
                            if filepath:
                                self.logger.info(f"    Creating attachment note...")
                                self.attachment_handler.upload_to_github(filepath, gh_issue['number'])
                        else:
                            self.logger.warning(f"    Warning: No valid URL found for attachment {att_name}")

            # Update the record with attachments count
            for record in self.state.pr_records:
                if record['gh_number'] == gh_issue['number']:
                    record['attachments'] = len(pr_attachments)
                    break

        return self.state.pr_records

    def _create_gh_pr(self, title: str, body: str, head: str, base: str) -> Optional[Dict[str, Any]]:
        """
        Create a GitHub pull request.

        Args:
            title: PR title
            body: PR body content
            head: Source branch name
            base: Target branch name

        Returns:
            Created GitHub PR data, or None if creation failed
        """
        try:
            pr = self.environment.clients.gh.create_pull_request(title, body, head, base)
            return pr

        except (APIError, AuthenticationError, NetworkError, ValidationError):
            raise  # Re-raise client exceptions
        except Exception as e:
            self.logger.error(f"  ERROR: Unexpected error creating PR: {e}")
            raise MigrationError(f"Unexpected error creating GitHub PR: {e}")

    def _create_gh_issue(self, title: str, body: str, labels: Optional[List[str]] = None,
                          state: str = 'open', milestone: Optional[int] = None) -> Dict[str, Any]:
        """
        Create a GitHub issue.

        Args:
            title: Issue title
            body: Issue body content
            labels: Optional list of label names
            state: Issue state ('open' or 'closed')
            milestone: Optional milestone number

        Returns:
            Created GitHub issue data
        """
        try:
            issue = self.environment.clients.gh.create_issue(
                title=title,
                body=body,
                labels=labels,
                state=state,
                milestone=milestone
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

    def _create_gh_comment(self, issue_number: int, body: str, is_pr: bool = False) -> Dict[str, Any]:
        """
        Create a comment on a GitHub issue or PR.

        Args:
            issue_number: The issue or PR number
            body: Comment text
            is_pr: Whether this is a PR (for better logging)

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

    def _fetch_bb_pr_attachments(self, pr_id: int) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a Bitbucket PR.

        Args:
            pr_id: The Bitbucket pull request ID

        Returns:
            List of attachment dictionaries
        """
        try:
            return self.environment.clients.bb.get_attachments("pr", pr_id)
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"    Warning: Could not fetch PR attachments: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"    Warning: Unexpected error fetching PR attachments: {e}")
            return []

    def _fetch_bb_pr_comments(self, pr_id: int) -> List[Dict[str, Any]]:
        """
        Fetch comments for a Bitbucket PR.

        Args:
            pr_id: The Bitbucket pull request ID

        Returns:
            List of comment dictionaries
        """
        try:
            return self.environment.clients.bb.get_comments("pr", pr_id)
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"    Warning: Could not fetch PR comments: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"    Warning: Unexpected error fetching PR comments: {e}")
            return []

    def _fetch_bb_pr_activity(self, pr_id: int) -> List[Dict[str, Any]]:
        """
        Fetch activity log for a Bitbucket PR.

        Args:
            pr_id: The Bitbucket pull request ID

        Returns:
            List of activity dictionaries
        """
        try:
            return self.environment.clients.bb.get_activity(pr_id)
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"    Warning: Could not fetch PR activity: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"    Warning: Unexpected error fetching PR activity: {e}")
            return []

    def _generate_update_comment(self, update: Dict[str, Any], author: str, date: str, is_first: bool = False) -> Optional[str]:
        """
        Generate a comment body for a PR update.

        Args:
            update: The update data from activity
            author: The author of the update
            date: The date of the update
            is_first: Whether this is the first activity (likely PR opening)

        Returns:
            Comment body string or None if no meaningful content
        """
        changes = update.get('changes', {})
        if changes:
            # Summarize changes
            change_parts = []
            for field, change in changes.items():
                old = change.get('old')
                new = change.get('new')
                if old != new:
                    if field == 'title':
                        change_parts.append(f"Title updated from '{old}' to '{new}'")
                    elif field == 'description':
                        change_parts.append(f"Description updated")
                    elif field == 'reviewers':
                        added = change.get('added', [])
                        removed = change.get('removed', [])
                        if added:
                            change_parts.append(f"Reviewers added: {', '.join(r.get('display_name', 'Unknown') for r in added)}")
                        if removed:
                            change_parts.append(f"Reviewers removed: {', '.join(r.get('display_name', 'Unknown') for r in removed)}")
                    elif field == 'status':
                        formatted_date = self._format_date(date)
                        if new == 'fulfilled':
                            change_parts.append(f"PR merged by {author} on {formatted_date}")
                        elif new == 'rejected':
                            change_parts.append(f"PR declined by {author} on {formatted_date}")
                        else:
                            change_parts.append(f"Status updated from '{old}' to '{new}' by {author} on {formatted_date}")
                    else:
                        change_parts.append(f"{field.capitalize()} updated")
                else:
                    self.logger.info(f"  No change: old and new {field} values are the same")
            if change_parts:
                formatted_date = self._format_date(date)
                return f"PR updated by {author} on {formatted_date}:\n- " + "\n- ".join(change_parts)
        else:
            # If it's the first activity, likely PR opening
            if is_first:
                formatted_date = self._format_date(date)
                return f"{author} opened the pull request on {formatted_date}"
            else:
                # Check for new commit
                source_commit = update.get('source', {}).get('commit', {}).get('hash')
                if source_commit:
                    formatted_date = self._format_date(date)
                    return f"New commit added to PR: {source_commit} by {author} on {formatted_date}"
                else:
                    # Fallback
                    formatted_date = self._format_date(date)
                    return f"PR updated by {author} on {formatted_date}"

        return None

    def _get_next_gh_number(self) -> int:
        """
        Get the next expected GitHub issue/PR number.

        Returns:
            Next GitHub issue/PR number
        """
        # This is a simplified implementation; in practice, you'd track this more carefully
        return len(self.state.mappings.prs) + len(self.state.pr_records) + 1

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

    def update_pr_content(self, bb_pr: Dict[str, Any], gh_number: int, as_pr: bool = True) -> None:
        """
        Update the content of a GitHub PR or issue with rewritten links and create comments after mappings are established.

        Args:
            bb_pr: The original Bitbucket PR data
            gh_number: The GitHub PR or issue number
            as_pr: If True, update as PR; else as issue
        """
        pr_num = bb_pr['id']

        # Format and update PR or issue body
        formatter = self.formatter_factory.get_pull_request_formatter()
        body, links_in_body, inline_images_body = formatter.format(bb_pr, as_issue=not as_pr, skip_link_rewriting=False)

        # Inline images are already tracked by the formatter, no need to duplicate

        # Update the PR or issue body
        try:
            self.environment.clients.gh.update_issue(gh_number, body=body)
            if as_pr:
                self.logger.info(f"  Updated PR #{gh_number} with rewritten links")
            else:
                self.logger.info(f"  Updated issue #{gh_number} with rewritten links")
        except Exception as e:
            self.logger.warning(f"  Warning: Could not update PR/issue #{gh_number}: {e}")

        # Create comments from activity log
        activities = self._fetch_bb_pr_activity(pr_num)
        # Sort activities by date to maintain timeline
        def get_activity_date(activity):
            if 'update' in activity:
                return activity['update'].get('date', '')
            elif 'comment' in activity:
                return activity['comment'].get('created_on', '')
            elif 'approval' in activity:
                return activity['approval'].get('date', '')
            else:
                return ''
        sorted_activities = sorted(activities, key=get_activity_date)
        links_in_comments = 0
        migrated_comments_count = 0

        # Get commit_id for inline comments
        commit_id = None
        if as_pr:
            # For PRs, get commit_id from the PR
            try:
                pr_data = self.environment.clients.gh.get_pull_request(gh_number)
                commit_id = pr_data.get('head', {}).get('sha')
            except Exception:
                commit_id = None

        # Fetch all PR comments once to avoid repeated API calls
        all_comments = self._fetch_bb_pr_comments(pr_num)
        
        # Sort comments topologically (parents before children)
        sorted_comments = self._sort_comments_topologically(all_comments)
        self.logger.info(f"Processing {len(sorted_comments)} comments for PR #{pr_num}")
        
        # Create a mapping from comment ID to activities for chronological ordering
        # Use defaultdict(list) to handle multiple activities per comment
        from collections import defaultdict
        comment_activities = defaultdict(list)
        for activity in sorted_activities:
            if 'comment' in activity:
                comment_id = activity['comment']['id']
                comment_activities[comment_id].append(activity)
        
        comment_seq = 0
        for comment in sorted_comments:
            # Find the corresponding activities for this comment
            comment_id = comment.get('id')
            activities = comment_activities.get(comment_id, [])
            if not activities:
                # Skip if no corresponding activities found
                continue
                
            comment = comment  # Use the sorted comment directly
            activity_id = comment.get('id', 'unknown')
            
            # Process the comment (typically one activity per comment, but handle multiple)
            for activity in activities:
                # Add logging to verify comment ID mapping
                parent_id = comment.get('parent', {}).get('id') if comment.get('parent') else None
                if parent_id:
                    self.logger.info(f"  Comment {activity_id} is a reply to comment {parent_id}")
                    parent_gh_id = self.state.mappings.pr_comments.get(parent_id)
                    if parent_gh_id:
                        self.logger.info(f"    Parent {parent_id} maps to GitHub comment {parent_gh_id['gh_id']}")
                    else:
                        self.logger.warning(f"    Parent {parent_id} not found in comment_mapping yet")

                # Check for deleted field
                if comment.get('deleted', False):
                    self.logger.info(f"  Skipping deleted comment on PR #{pr_num}")
                    continue

                # Check for pending field and annotate if true
                is_pending = comment.get('pending', False)
                if is_pending:
                    self.logger.info(f"  Annotating pending comment on PR #{pr_num}")

                # Increment comment sequence
                comment_seq += 1

                # Format comment
                formatter = self.formatter_factory.get_comment_formatter()
                comment_body, comment_links, inline_images_comment = formatter.format(comment, item_type='pr', item_number=pr_num, commit_id=commit_id, comment_seq=comment_seq, skip_link_rewriting=False)
                links_in_comments += comment_links

                # Add annotation for pending
                if is_pending:
                    comment_body = f"**[PENDING APPROVAL]**\n\n{comment_body}"

                # Inline images from comments are already tracked by the formatter, no need to duplicate

                # Check if this is an inline comment
                inline_data = comment.get('inline')
                parent_id = comment.get('parent', {}).get('id') if comment.get('parent') else None
                in_reply_to = self.state.mappings.pr_comments.get(parent_id) if parent_id else None

                if inline_data and commit_id:
                    # Attempt to create as inline review comment
                    try:
                        # Log detailed info for debugging
                        self.logger.debug(f"  DEBUG: Creating inline comment for comment ID {comment.get('id')}")
                        self.logger.debug(f"  DEBUG: inline_data = {inline_data}")
                        self.logger.debug(f"  DEBUG: commit_id = {commit_id[:7] if commit_id else 'None'}")
                        self.logger.debug(f"  DEBUG: in_reply_to = {in_reply_to}")
                        self.logger.debug(f"  DEBUG: parent_id = {parent_id}")
                        
                        path = inline_data.get('path')
                        line = inline_data.get('to')          # Anchor line in new version (ending line if multi-line)
                        from_line = inline_data.get('from')   # Anchor line in old version (ending line if multi-line)
                        start_from = inline_data.get('start_from')  # Starting line in old version (null for single-line)
                        start_to = inline_data.get('start_to')      # Starting line in new version (null for single-line)

                        # Log attempt details with proper None handling
                        in_reply_to_id = in_reply_to['gh_id'] if in_reply_to and isinstance(in_reply_to, dict) else 'None'
                        self.logger.info(f"  Attempting inline comment: path={path}, line={line}, from={from_line}, start_from={start_from}, start_to={start_to}, commit={commit_id[:7] if commit_id else 'None'}, in_reply_to={in_reply_to_id}")

                        if path and line:
                            # Strategy: Use in_reply_to when available to simplify parameter handling
                            # GitHub allows omitting start_line/start_side for multi-line comments when using in_reply_to
                            has_parent = in_reply_to and isinstance(in_reply_to, dict)
                            
                            if has_parent:
                                # When using in_reply_to, we can omit start_line/start_side even for multi-line
                                actual_start_line = None
                                actual_start_side = None
                                reply_id = in_reply_to['gh_id']
                                self.logger.info(f"  Using in_reply_to approach: reply_to={reply_id}, omitting start_line/start_side")
                            else:
                                # Fall back to explicit start_line/start_side for multi-line comments
                                # For single-line: start_from and start_to are null
                                # For multi-line: start_from and start_to are set
                                actual_start_line = start_to if start_to else None  # Use start_to for multi-line comments
                                actual_start_side = 'LEFT' if actual_start_line else None
                                reply_id = None
                            
                            gh_comment = self.environment.clients.gh.create_pr_review_comment(
                                pull_number=gh_number,
                                body=comment_body,
                                path=path,
                                line=line,
                                side='RIGHT',  # Always 'RIGHT' for target (new) version
                                start_line=actual_start_line,
                                start_side=actual_start_side,
                                commit_id=commit_id,
                                in_reply_to=reply_id
                            )
                            if not activity_id=='unknown':
                                self.state.mappings.pr_comments[activity_id] = {
                                    'gh_id': gh_comment['id'],
                                    # Store comment data for potential child replies
                                    'body': comment_body
                                    }
                            self.logger.info(f"  ✓ Created inline comment on {path}:{line} for PR #{gh_number}")
                        else:
                            # Fallback if required fields missing
                            self.logger.warning(f"  Missing path ({path}) or line ({line}) for inline comment, using regular comment")
                            gh_comment = self._create_gh_comment(gh_number, comment_body, is_pr=True)
                            if not activity_id=='unknown':
                                self.state.mappings.pr_comments[activity_id] = {
                                    'gh_id': gh_comment['id'],
                                    'body': comment_body
                                }
                    except (APIError, AuthenticationError, NetworkError, ValidationError) as e:
                        # Fallback to regular comment on failure
                        self.logger.warning(f"  Failed to create inline comment: {e}")
                        self.logger.warning(f"    Details - Path: {path}, Line: {line}, Commit: {commit_id[:7] if commit_id else 'None'}")
                        # Use the same logic as above for consistency
                        actual_start_line = start_to if start_to else None
                        actual_start_side = 'LEFT' if actual_start_line else None
                        self.logger.warning(f"    Start line: {actual_start_line}, Side: RIGHT, Start side: {actual_start_side}")
                        self.logger.warning(f"    Raw BB params: from={from_line}, to={line}, start_from={start_from}, start_to={start_to}")

                        # Add detailed context to the fallback comment
                        context_note = f"> 💬 **Code comment on `{path}` (line {line})**"
                        if commit_id:
                            context_note += f" (commit: `{commit_id[:7]}`)"
                        context_note += f"\n> ⚠️ *Could not attach to code diff: {str(e)}*\n\n"
                        comment_body = context_note + comment_body

                        gh_comment = self._create_gh_comment(gh_number, comment_body, is_pr=True)
                        if not activity_id=='unknown':
                            self.state.mappings.pr_comments[activity_id] = {
                                'gh_id': gh_comment['id'],
                                'body': comment_body
                            }
                    except Exception as e:
                        # Unexpected error, fallback
                        self.logger.error(f"  Unexpected error creating inline comment: {e}")
                        self.logger.error(f"    Details - Path: {path}, Line: {line}, Commit: {commit_id[:7] if commit_id else 'None'}")

                        # Add detailed context to the fallback comment
                        context_note = f"> 💬 **Code comment on `{path}` (line {line})**"
                        if commit_id:
                            context_note += f" (commit: `{commit_id[:7]}`)"
                        context_note += f"\n> ⚠️ *Unexpected error attaching to code diff: {str(e)}*\n\n"
                        comment_body = context_note + comment_body

                        gh_comment = self._create_gh_comment(gh_number, comment_body, is_pr=True)
                        if not activity_id=='unknown':
                            self.state.mappings.pr_comments[activity_id] = {
                                'gh_id': gh_comment['id'],
                                'body': comment_body
                            }
                else:
                    # Regular comment
                    if parent_id:
                        # Check if parent was successfully migrated
                        parent_gh_id = self.state.mappings.pr_comments.get(parent_id)
                        if parent_gh_id:
                            # Create link to parent comment on GitHub
                            # Format: https://github.com/owner/repo/pull/123#issuecomment-456
                            parent_url = f"https://github.com/{self.environment.clients.gh.owner}/{self.environment.clients.gh.repo}/pull/{gh_number}#issuecomment-{parent_gh_id['gh_id']}"

                            # Optionally get parent comment body for quoting
                            # parent_comment_data = self.state.mappings.pr_comments.get(f"{parent_id}_data")
                            if 'body' in parent_gh_id:
                                # Extract first line or first 100 chars of parent for quote
                                parent_body = parent_gh_id['body']
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
                        gh_comment = self._create_gh_comment(gh_number, comment_body, is_pr=True)
                        if not activity_id=='unknown':
                            self.state.mappings.pr_comments[activity_id] = {
                                'gh_id': gh_comment['id'],
                                # Store comment data for potential child replies
                                'body': comment_body
                            }
                    except ValidationError as e:
                        if 'locked' in str(e).lower():
                            self.logger.warning(f"  Skipping comment on locked PR #{gh_number}: {e}")
                            # Add note to record that PR was locked (this is actual repository locking)
                            for record in self.state.pr_records:
                                if record.get('gh_number') == gh_number:
                                    if 'locked' not in ' '.join(record.get('remarks', [])):
                                        record['remarks'].append('PR was locked - comments skipped')
                                    break
                        else:
                            raise

                migrated_comments_count += 1
                # Only process the first activity for this comment to avoid duplicate processing
                break

        # Process non-comment activities (updates and approvals) separately to maintain chronological order
        for activity in sorted_activities:
            if 'comment' in activity:
                continue  # Skip comments as they're already processed
            
            if 'update' in activity:
                # Process as update
                update = activity['update']
                activity_id = 'unknown'  # Updates do not have IDs
                author = update.get('author', {}).get('display_name', 'Unknown')
                date = update.get('date', '')

                # Generate comment body for update
                is_first = (activity is sorted_activities[0])
                update_body = self._generate_update_comment(update, author, date, is_first)
                if update_body:
                    try:
                        gh_comment = self._create_gh_comment(gh_number, update_body, is_pr=True)
                        # self.state.mappings.pr_comments[activity_id] = {'gh_id': gh_comment['id']} # no mapping for generated update comments
                        migrated_comments_count += 1
                        self.logger.info(f"  Created update comment for PR #{gh_number}")
                    except ValidationError as e:
                        if 'locked' in str(e).lower():
                            self.logger.warning(f"  Skipping comment on locked PR #{gh_number}: {e}")
                            # Add note to record that PR was locked (this is actual repository locking)
                            for record in self.state.pr_records:
                                if record.get('gh_number') == gh_number:
                                    if 'locked' not in ' '.join(record.get('remarks', [])):
                                        record['remarks'].append('PR was locked - comments skipped')
                                    break
                        else:
                            raise
                else:
                    self.logger.info(f"  Skipping update without meaningful content on PR #{pr_num}")

            elif 'approval' in activity:
                # Process as approval
                approval = activity['approval']
                activity_id = 'unknown'  # Approvals do not have IDs
                user = approval.get('user', {}).get('display_name', 'Unknown')
                date = approval.get('date', '')

                # Generate comment body for approval
                formatted_date = self._format_date(date)
                approval_body = f"{user} approved the pull request on {formatted_date}"
                try:
                    gh_comment = self._create_gh_comment(gh_number, approval_body, is_pr=True)
                    # self.state.mappings.pr_comments[activity_id] = {'gh_id':gh_comment['id']} # no mapping for generated approval comment
                    migrated_comments_count += 1
                    self.logger.info(f"  Created approval comment for PR #{gh_number}")
                except ValidationError as e:
                    if 'locked' in str(e).lower():
                        self.logger.warning(f"  Skipping comment on locked PR #{gh_number}: {e}")
                    else:
                        raise

            else:
                self.logger.info(f"  Skipping unknown activity type on PR #{pr_num}")

            # Add rate limiting delay between comments to avoid secondary rate limits and abuse detection
            # GitHub recommends at least 1 second between mutative requests (POST/PATCH/PUT/DELETE)
            time.sleep(self.environment.config.options.request_delay_seconds)

        # Update the record with actual counts
        for record in self.state.pr_records:
            if record['gh_number'] == gh_number:
                record['comments'] = migrated_comments_count
                record['links_rewritten'] = links_in_body + links_in_comments
                break

        self.logger.info(f"  ✓ Updated PR/issue #{gh_number} with {migrated_comments_count} comments and {links_in_body + links_in_comments} links rewritten")

    def update_pr_comments(self, bb_pr: Dict[str, Any], gh_number: int, as_pr: bool = True) -> None:
        """
        Comments are now created in update_pr_content to avoid duplication.
        This method is kept for compatibility but does nothing.

        Args:
            bb_pr: The original Bitbucket PR data
            gh_number: The GitHub PR or issue number
            as_pr: If True, update as PR comments; else as issue comments
        """
        # Comments are handled in update_pr_content
        pass