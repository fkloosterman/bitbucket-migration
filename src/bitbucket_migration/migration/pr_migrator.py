"""
Pull request migrator for Bitbucket to GitHub migration.

This module contains the PullRequestMigrator class that handles the migration
of Bitbucket pull requests to GitHub, with intelligent branch checking and
strategy for handling different PR states.
"""

from typing import List, Dict, Any, Optional

from ..clients.bitbucket_client import BitbucketClient
from ..clients.github_client import GitHubClient
from ..services.user_mapper import UserMapper
from ..services.link_rewriter import LinkRewriter
from ..services.attachment_handler import AttachmentHandler
from ..formatters.formatter_factory import FormatterFactory
from ..exceptions import MigrationError, APIError, AuthenticationError, NetworkError, ValidationError
from ..utils.logging_config import MigrationLogger


class PullRequestMigrator:
    """
    Handles migration of Bitbucket pull requests to GitHub.

    This class encapsulates all logic related to PR migration, including
    branch existence checking, state-based migration strategies, and
    handling attachments and comments.
    """

    def __init__(self, bb_client: BitbucketClient, gh_client: GitHubClient,
                  user_mapper: UserMapper, link_rewriter: LinkRewriter,
                  attachment_handler: AttachmentHandler, formatter_factory: FormatterFactory,
                  logger: MigrationLogger):
        """
        Initialize the PullRequestMigrator.

        Args:
            bb_client: Bitbucket API client
            gh_client: GitHub API client
            user_mapper: User mapping service
            link_rewriter: Link rewriting service
            attachment_handler: Attachment handling service
            formatter_factory: Formatter factory
            logger: Logger instance
        """
        self.bb_client = bb_client
        self.gh_client = gh_client
        self.user_mapper = user_mapper
        self.link_rewriter = link_rewriter
        self.attachment_handler = attachment_handler
        self.formatter_factory = formatter_factory
        self.logger = logger

        # Track migration progress
        self.pr_mapping = {}  # BB PR # -> GH issue/PR #
        self.pr_records = []  # Detailed migration records
        self.comment_mapping = {}  # BB comment ID -> GH comment ID

        # Migration statistics
        self.stats = {
            'prs_as_prs': 0,  # Open PRs that became GitHub PRs
            'prs_as_issues': 0,  # PRs that became GitHub issues
            'pr_branch_missing': 0,  # PRs that couldn't be migrated due to missing branches
            'pr_merged_as_issue': 0,  # Merged PRs migrated as issues (safest approach)
        }

    def migrate_pull_requests(self, bb_prs: List[Dict[str, Any]],
                               milestone_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
                               skip_pr_as_issue: bool = False,
                               skip_link_rewriting: bool = False) -> List[Dict[str, Any]]:
        """
        Migrate Bitbucket PRs to GitHub with intelligent branch checking.

        Strategy:
        - OPEN PRs: Try to create as GitHub PRs (if branches exist)
        - MERGED/DECLINED/SUPERSEDED PRs: Always migrate as issues (safest approach)

        Args:
            bb_prs: List of Bitbucket pull requests to migrate
            milestone_lookup: Optional mapping of milestone names to GitHub milestone data
            skip_pr_as_issue: Whether to skip migrating closed PRs as issues
            skip_link_rewriting: If True, skip link rewriting (for two-pass migration)

        Returns:
            List of migration records
        """
        milestone_lookup = milestone_lookup or {}

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
                    source_exists = self.gh_client.check_branch_exists(source_branch)
                    dest_exists = self.gh_client.check_branch_exists(dest_branch)

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
                                self.gh_client.update_issue(gh_pr['number'], milestone=milestone_number)
                                self.logger.info(f"    Applied milestone to PR #{gh_pr['number']}")
                            except (APIError, AuthenticationError, NetworkError, ValidationError):
                                self.logger.warning(f"    Warning: Could not apply milestone to PR")
                            except Exception as e:
                                self.logger.warning(f"    Warning: Unexpected error applying milestone to PR: {e}")

                        if gh_pr:
                            self.pr_mapping[pr_num] = gh_pr['number']
                            self.stats['prs_as_prs'] += 1

                            # Apply labels to the migrated PR
                            labels = ['migrated-from-bitbucket']
                            try:
                                self.gh_client.update_issue(gh_pr['number'], labels=labels)
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

                            self.pr_records.append({
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
                                'links_rewritten': 0,  # Will be updated in second pass
                                'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                                'gh_url': f"https://github.com/{self.gh_client.owner}/{self.gh_client.repo}/pull/{gh_pr['number']}",
                                'remarks': ['Migrated as GitHub PR', 'Branches exist on GitHub', 'Content updated in second pass']
                            })

                            # Migrate PR attachments
                            pr_attachments = self._fetch_bb_pr_attachments(pr_num)
                            if pr_attachments:
                                self.logger.info(f"  Migrating {len(pr_attachments)} PR attachments...")
                                for attachment in pr_attachments:
                                    att_name = attachment.get('name', 'unknown')
                                    att_url = attachment.get('links', {}).get('self', {}).get('href')

                                    if att_url:
                                        self.logger.info(f"    Processing {att_name}...")
                                        filepath = self.attachment_handler.download_attachment(att_url, att_name)
                                        if filepath:
                                            self.attachment_handler.upload_to_github(filepath, gh_pr['number'], self.gh_client, self.gh_client.owner, self.gh_client.repo)

                            self.logger.info(f"  ✓ Created PR #{gh_pr['number']} (content and comments will be added in second pass)")
                            continue
                        else:
                            self.logger.info(f"  ✗ Failed to create GitHub PR, falling back to issue migration")
                    else:
                        # Branches don't exist
                        self.logger.info(f"  ✗ Cannot create as PR - branches missing on GitHub")
                        self.stats['pr_branch_missing'] += 1
                else:
                    self.logger.info(f"  ✗ Missing branch information in Bitbucket data")
            else:
                # MERGED, DECLINED, or SUPERSEDED - always migrate as issue
                if skip_pr_as_issue:
                    self.logger.info(f"  → Skipping migration as issue (PR was {pr_state}, --skip-pr-as-issue enabled)")
                else:
                    self.logger.info(f"  → Migrating as issue (PR was {pr_state} - safest approach)")

                if pr_state in ['MERGED', 'SUPERSEDED']:
                    self.stats['pr_merged_as_issue'] += 1

            # Skip or migrate as issue based on flag
            if skip_pr_as_issue:
                self.logger.info(f"  ✓ Skipped PR #{pr_num} (not migrated as issue due to --skip-pr-as-issue flag)")

                # Still record PR details for report
                author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
                gh_author = self.user_mapper.map_user(author) if author != 'Unknown (deleted user)' else None

                # Determine remarks
                remarks = ['Not migrated (--skip-pr-as-issue flag)']
                if pr_state in ['MERGED', 'SUPERSEDED']:
                    remarks.append('Original PR was merged')
                elif pr_state == 'DECLINED':
                    remarks.append('Original PR was declined')
                if not source_branch or not dest_branch:
                    remarks.append('Branch information missing')
                elif not self.gh_client.check_branch_exists(source_branch) or not self.gh_client.check_branch_exists(dest_branch):
                    remarks.append('One or both branches do not exist on GitHub')

                self.pr_records.append({
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

            self.pr_mapping[pr_num] = gh_issue['number']
            self.stats['prs_as_issues'] += 1

            # Get commit_id for inline comments
            commit_id = None
            if source_branch:
                try:
                    response = self.gh_client.session.get(f"{self.gh_client.base_url}/branches/{source_branch}")
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
            elif not self.gh_client.check_branch_exists(source_branch) or not self.gh_client.check_branch_exists(dest_branch):
                remarks.append('One or both branches do not exist on GitHub')

            self.pr_records.append({
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
                'links_rewritten': 0,  # Will be updated in second pass
                'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                'gh_url': f"https://github.com/{self.gh_client.owner}/{self.gh_client.repo}/issues/{gh_issue['number']}",
                'remarks': remarks + ['Content updated in second pass']
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
                        self.logger.info(f"    Downloading {att_name}...")
                        filepath = self.attachment_handler.download_attachment(att_url, att_name)
                        if filepath:
                            self.logger.info(f"    Creating attachment note...")
                            self.attachment_handler.upload_to_github(filepath, gh_issue['number'], self.gh_client, self.gh_client.owner, self.gh_client.repo)

        return self.pr_records

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
            pr = self.gh_client.create_pull_request(title, body, head, base)
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
            issue = self.gh_client.create_issue(
                title=title,
                body=body,
                labels=labels,
                state=state,
                milestone=milestone
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
            return self.gh_client.create_comment(issue_number, body)
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
            return self.bb_client.get_attachments("pr", pr_id)
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
            return self.bb_client.get_comments("pr", pr_id)
        except (APIError, AuthenticationError, NetworkError) as e:
            self.logger.warning(f"    Warning: Could not fetch PR comments: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"    Warning: Unexpected error fetching PR comments: {e}")
            return []

    def _get_next_gh_number(self) -> int:
        """
        Get the next expected GitHub issue/PR number.

        Returns:
            Next GitHub issue/PR number
        """
        # This is a simplified implementation; in practice, you'd track this more carefully
        return len(self.pr_mapping) + len(self.pr_records) + 1

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
        body, links_in_body, inline_images_body = formatter.format(bb_pr, as_issue=not as_pr, skip_link_rewriting=False, use_gh_cli=self.attachment_handler.use_gh_cli)

        # Track inline images as attachments
        for img in inline_images_body:
            self.attachment_handler.attachments.append({
                'pr_number': pr_num,
                'github_pr': gh_number,
                'filename': img['filename'],
                'filepath': img['filepath'],
                'type': 'inline_image'
            })

        # Update the PR or issue body
        try:
            self.gh_client.update_issue(gh_number, body=body)
            if as_pr:
                self.logger.info(f"  Updated PR #{gh_number} with rewritten links")
            else:
                self.logger.info(f"  Updated issue #{gh_number} with rewritten links")
        except Exception as e:
            self.logger.warning(f"  Warning: Could not update PR/issue #{gh_number}: {e}")

        # Create comments
        comments = self._fetch_bb_pr_comments(pr_num)
        # Sort comments topologically (parents before children)
        sorted_comments = self._sort_comments_topologically(comments)
        links_in_comments = 0
        migrated_comments_count = 0

        # Get commit_id for inline comments
        commit_id = None
        if as_pr:
            # For PRs, get commit_id from the PR
            try:
                pr_data = self.gh_client.get_pull_request(gh_number)
                commit_id = pr_data.get('head', {}).get('sha')
            except Exception:
                commit_id = None

        for comment in sorted_comments:
            # Check for deleted field
            if comment.get('deleted', False):
                self.logger.info(f"  Skipping deleted comment on PR #{pr_num}")
                continue

            # Check for pending field and annotate if true
            is_pending = comment.get('pending', False)
            if is_pending:
                self.logger.info(f"  Annotating pending comment on PR #{pr_num}")

            # Format comment
            formatter = self.formatter_factory.get_comment_formatter()
            comment_body, comment_links, inline_images_comment = formatter.format(comment, item_type='pr', item_number=pr_num, commit_id=commit_id, skip_link_rewriting=False, use_gh_cli=self.attachment_handler.use_gh_cli)
            links_in_comments += comment_links

            # Add annotation for pending
            if is_pending:
                comment_body = f"**[PENDING APPROVAL]**\n\n{comment_body}"

            # Track inline images from PR comments
            for img in inline_images_comment:
                self.attachment_handler.attachments.append({
                    'pr_number': pr_num,
                    'github_pr': gh_number,
                    'filename': img['filename'],
                    'filepath': img['filepath'],
                    'type': 'inline_image_comment'
                })

            # Check if this is an inline comment
            inline_data = comment.get('inline')
            parent_id = comment.get('parent', {}).get('id') if comment.get('parent') else None
            in_reply_to = self.comment_mapping.get(parent_id) if parent_id else None

            if inline_data and commit_id:
                # Attempt to create as inline review comment
                try:
                    path = inline_data.get('path')
                    line = inline_data.get('to')
                    start_line = inline_data.get('from')
                    if path and line:
                        gh_comment = self.gh_client.create_pr_review_comment(
                            pull_number=gh_number,
                            body=comment_body,
                            path=path,
                            line=line,
                            side='RIGHT',  # Default to new file side
                            start_line=start_line if start_line and start_line != line else None,
                            start_side='LEFT' if start_line and start_line != line else None,  # Use 'LEFT' for start if multi-line
                            commit_id=commit_id,
                            in_reply_to=in_reply_to
                        )
                        self.comment_mapping[comment['id']] = gh_comment['id']
                        self.logger.info(f"  Created inline comment on {path} (line {line}) for PR #{gh_number}")
                    else:
                        # Fallback if required fields missing
                        gh_comment = self._create_gh_comment(gh_number, comment_body, is_pr=True)
                        self.comment_mapping[comment['id']] = gh_comment['id']
                        self.logger.warning(f"  Missing path or line for inline comment, using regular comment")
                except (APIError, AuthenticationError, NetworkError, ValidationError) as e:
                    # Fallback to regular comment on failure
                    self.logger.warning(f"  Failed to create inline comment: {e}. Using regular comment.")
                    gh_comment = self._create_gh_comment(gh_number, comment_body, is_pr=True)
                    self.comment_mapping[comment['id']] = gh_comment['id']
                except Exception as e:
                    # Unexpected error, fallback
                    self.logger.error(f"  Unexpected error creating inline comment: {e}. Using regular comment.")
                    gh_comment = self._create_gh_comment(gh_number, comment_body, is_pr=True)
                    self.comment_mapping[comment['id']] = gh_comment['id']
            else:
                # Regular comment
                if parent_id and not in_reply_to:
                    # Add note for reply since GitHub doesn't support threading for PR comments
                    comment_body = f"**[Reply to Bitbucket Comment {parent_id}]**\n\n{comment_body}"
                gh_comment = self._create_gh_comment(gh_number, comment_body, is_pr=True)
                self.comment_mapping[comment['id']] = gh_comment['id']

            migrated_comments_count += 1

        # Update the record with actual counts
        for record in self.pr_records:
            if record['gh_number'] == gh_number:
                record['comments'] = migrated_comments_count
                record['links_rewritten'] = links_in_body + links_in_comments
                record['remarks'].append('Content and comments updated in second pass')
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