import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class IssueLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket issue links.

    Rewrites Bitbucket issue URLs to their corresponding GitHub issue URLs.
    Supports both same-repo and cross-repo issue links.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState, workspace: str = None, repo: str = None):
        """
        Initialize the IssueLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
            workspace: Optional workspace override for cross-repo handling
            repo: Optional repo override for cross-repo handling
        """
        super().__init__(environment, state, priority=1)

        if repo:
            self.bb_repo = repo
            self.bb_workspace = environment.config.bitbucket.workspace if not workspace else workspace

            self.gh_owner, self.gh_repo = self.environment.services.get('cross_repo_mapping_store').get_mapped_repository(
                self.bb_workspace, self.bb_repo
            )

            if not self.gh_repo:
                # no mapping found
                self.logger.error(f"Could not find mapped GitHub repository for {workspace}/{repo}")

            if not self.gh_owner:
                self.gh_owner = self.environment.config.github.owner

            self.issue_mapping = self.environment.services.get('cross_repo_mapping_store').get_issue_mapping(
                self.bb_workspace, self.bb_repo
            )
        else:
            self.bb_workspace = self.environment.config.bitbucket.workspace
            self.bb_repo = self.environment.config.bitbucket.repo
            self.gh_owner = self.environment.config.github.owner
            self.gh_repo = self.environment.config.github.repo
            self.issue_mapping = self.state.mappings.issues


        # Pre-compile pattern at initialization
        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(self.bb_workspace)}/{re.escape(self.bb_repo)}/issues/(\d+)(?:/[^/\s\)\"\'>]*)?'
        )

        self.logger.debug(
            "IssueLinkHandler initialized for {0}/{1} -> {2}/{3}".format(
                self.bb_workspace, self.bb_repo,
                self.gh_owner, self.gh_repo
            )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle Bitbucket issue link rewriting.

        Args:
            url: The Bitbucket issue URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub issue URL or None if URL doesn't match
        """
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            self.logger.debug(f"URL did not match issue pattern: {url}")
            return None

        bb_num = int(match.group(1))
        gh_num = self.issue_mapping.get(bb_num)

        if gh_num:
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"

            markdown_context = context.get('markdown_context', None)

            # If in markdown context (target or text), return URL only (no note)
            if markdown_context in ('target', 'text'):
                rewritten = gh_url  # Just the URL
            else:
                # Normal context - return formatted link with note
                note = self.format_note(
                    'issue_link',
                    bb_num=bb_num,
                    bb_url=url,
                    gh_num=gh_num,
                    gh_url=gh_url
                )
                if note:
                    rewritten = f"[#{gh_num}]({gh_url}){note}"
                else:
                    rewritten = f"[#{gh_num}]({gh_url})"
        else:
            rewritten = url

        context['details'].append({
            'original': url,
            'rewritten': rewritten,
            'type': 'issue_link',
            'reason': 'mapped' if gh_num else 'unmapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context', None)
        })

        return rewritten