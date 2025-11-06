import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class PrLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket pull request links.

    Rewrites Bitbucket pull request URLs to their corresponding GitHub issue URLs.
    Pull requests in GitHub are represented as issues with additional pull request data.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the PrLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
        """
        # Pre-compile pattern at initialization
        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(environment.config.bitbucket.workspace)}/{re.escape(environment.config.bitbucket.repo)}/pull-requests/(\d+)(?:/[^/\s\)\"\'>]*)?'
        )
        super().__init__(environment, state, priority=2)  # High priority, after issues

        self.logger.debug(
            "PrLinkHandler initialized for {0}/{1} -> {2}/{3}".format(
                self.environment.config.bitbucket.workspace,
                self.environment.config.bitbucket.repo,
                self.environment.config.github.owner,
                self.environment.config.github.repo
            )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle Bitbucket pull request link rewriting.

        Args:
            url: The Bitbucket pull request URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub issue URL or None if URL doesn't match
        """
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            self.logger.debug(f"URL did not match PR pattern: {url}")
            return None

        bb_num = int(match.group(1))
        gh_num = self.state.mappings.prs.get(bb_num)

        if gh_num:
            gh_url = f"https://github.com/{self.environment.config.github.owner}/{self.environment.config.github.repo}/issues/{gh_num}"

            markdown_context = context.get('markdown_context', None)

            # If in markdown context (target or text), return URL only (no note)
            if markdown_context in ('target', 'text'):
                rewritten = gh_url  # Just the URL
            else:
                # Normal context - return formatted link with note
                note = self.format_note(
                    'pr_link',
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
            'type': 'pr_link',
            'reason': 'mapped' if gh_num else 'unmapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context', None)
        })

        return rewritten