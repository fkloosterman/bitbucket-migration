import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class RepoHomeLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket repository home links.

    Rewrites Bitbucket repository home URLs to their corresponding GitHub repository URLs.
    This handler should have higher priority than CrossRepoLinkHandler to ensure
    same-repository home links are handled correctly.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the RepoHomeLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
        """
        super().__init__(environment, state, priority=5)  # Higher than CrossRepoLinkHandler (6)

        self.bb_workspace = self.environment.config.bitbucket.workspace
        self.bb_repo = self.environment.config.bitbucket.repo
        self.gh_owner = self.environment.config.github.owner
        self.gh_repo = self.environment.config.github.repo

        # Pre-compile pattern for same-repository home links only
        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(self.bb_workspace)}/{re.escape(self.bb_repo)}/?$'
        )

        self.logger.debug(
            "RepoHomeLinkHandler initialized for {0}/{1} -> {2}/{3}".format(
                self.bb_workspace, self.bb_repo,
                self.gh_owner, self.gh_repo
            )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle Bitbucket repository home link rewriting.

        Args:
            url: The Bitbucket repository home URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub URL or None if URL doesn't match
        """
        match = self.PATTERN.match(url)
        if not match:
            self.logger.debug(f"URL did not match repository home pattern: {url}")
            return None

        gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}"

        markdown_context = context.get('markdown_context', None)

        # If in markdown target context, return URL only (no note)
        if markdown_context == 'target':
            rewritten = gh_url  # Just the URL
        else:
            # Normal context - return formatted link with note
            note = self.format_note(
                'repo_home_link',
                bb_url=url,
                gh_url=gh_url,
                gh_repo=self.gh_repo
            )
            if note:
                rewritten = f"[{self.gh_repo}]({gh_url}){note}"
            else:
                rewritten = f"[{self.gh_repo}]({gh_url})"

        context['details'].append({
            'original': url,
            'rewritten': rewritten,
            'type': 'repo_home_link',
            'reason': 'mapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context', None)
        })

        return rewritten