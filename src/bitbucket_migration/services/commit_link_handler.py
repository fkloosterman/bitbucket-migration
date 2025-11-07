import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class CommitLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket commit links.

    Rewrites Bitbucket commit URLs to their corresponding GitHub commit URLs.
    Supports both same-repo and cross-repo commit links.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState, workspace: str = None, repo: str = None):
        """
        Initialize the CommitLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
            workspace: Optional workspace override for cross-repo handling
            repo: Optional repo override for cross-repo handling
        """
        super().__init__(environment, state, priority=3)

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

        else:
            self.bb_workspace = self.environment.config.bitbucket.workspace
            self.bb_repo = self.environment.config.bitbucket.repo
            self.gh_owner = self.environment.config.github.owner
            self.gh_repo = self.environment.config.github.repo


        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(environment.config.bitbucket.workspace)}/{re.escape(environment.config.bitbucket.repo)}/commits/([0-9a-f]{{7,40}})'
        )

        self.logger.debug(
                "CommitLinkHandler initialized for {0}/{1} -> {2}/{3}".format(
                self.bb_workspace, self.bb_repo,
                self.gh_owner, self.gh_repo
                )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle Bitbucket commit link rewriting.

        Args:
            url: The Bitbucket commit URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub commit URL or None if URL doesn't match
        """
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            self.logger.debug(f"URL did not match commit pattern: {url}")
            return None

        commit_sha = match.group(1)
        gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/commit/{commit_sha}"

        markdown_context = context.get('markdown_context', None)

        # If in markdown target context, return URL only (no note)
        if markdown_context == 'target':
            rewritten = gh_url  # Just the URL
        else:
            # Normal context - return formatted link with note
            note = self.format_note(
                'commit_link',
                bb_url=url,
                gh_url=gh_url,
                commit_sha=commit_sha
            )
            if note:
                rewritten = f"[`{commit_sha[:7]}`]({gh_url}){note}"
            else:
                rewritten = f"[`{commit_sha[:7]}`]({gh_url})"

        context['details'].append({
            'original': url,
            'rewritten': rewritten,
            'type': 'commit_link',
            'reason': 'mapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context', None)
        })

        return rewritten