import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class RepoHomeLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket repository home links.

    Handles repository root URLs that don't match more specific patterns
    like issues, PRs, commits, etc. Has lowest priority to avoid interfering
    with more specific link handlers.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the RepoHomeLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
        """
        # Pre-compile pattern at initialization
        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(environment.config.bitbucket.workspace)}/{re.escape(environment.config.bitbucket.repo)}(?=\s|\)|"|\'|>|$|$)'
        )
        super().__init__(environment, state, priority=10)  # Low priority

        self.logger.debug(
            "RepoHomeLinkHandler initialized for {0}/{1} -> {2}/{3}".format(
                self.environment.config.bitbucket.workspace,
                self.environment.config.bitbucket.repo,
                self.environment.config.github.owner,
                self.environment.config.github.repo
            )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle Bitbucket repository home link rewriting.

        Args:
            url: The Bitbucket repository home URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub repository URL or None if URL doesn't match
        """
        # Initialize with default values
        gh_owner = self.environment.config.github.owner
        gh_repo = self.environment.config.github.repo

        workspace, repo = self.environment.config.bitbucket.workspace, self.environment.config.bitbucket.repo
        if workspace == self.environment.config.bitbucket.workspace and repo == self.environment.config.bitbucket.repo:
            gh_url = f"https://github.com/{gh_owner}/{gh_repo}"

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
                    gh_repo=gh_repo
                )
                if note:
                    rewritten = f"[repository]({gh_url}){note}"
                else:
                    rewritten = f"[repository]({gh_url})"
        else:
            repo_key = f"{workspace}/{repo}"
            repo_mapping = self.environment.services.get('cross_repo_mapping_store').get_repository_mapping()
            if repo_key in repo_mapping:
                gh_repo_full = repo_mapping[repo_key]
                if '/' in gh_repo_full:
                    gh_owner, gh_repo = gh_repo_full.split('/', 1)
                else:
                    gh_owner = self.environment.config.github.owner
                    gh_repo = gh_repo_full
                gh_url = f"https://github.com/{gh_owner}/{gh_repo}"

                markdown_context = context.get('markdown_context')

                # If in markdown target context, return URL only (no note)
                if markdown_context == 'target':
                    rewritten = gh_url  # Just the URL
                else:
                    # Normal context - return formatted link with note
                    note = self.format_note(
                        'repo_home_link',
                        bb_url=url,
                        gh_url=gh_url,
                        gh_repo=gh_repo
                    )
                    if note:
                        rewritten = f"[{gh_repo}]({gh_url}){note}"
                    else:
                        rewritten = f"[{gh_repo}]({gh_url})"
            else:
                rewritten = url

        context['details'].append({
            'original': url,
            'rewritten': rewritten,
            'type': 'repo_home_link',
            'reason': 'mapped' if rewritten != url else 'unmapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context', None)
        })

        return rewritten