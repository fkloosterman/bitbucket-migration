import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class BranchLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket branch links.

    Rewrites Bitbucket branch URLs (both /branch/ and /commits/branch/ patterns)
    to their corresponding GitHub tree URLs.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the BranchLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
        """
        # Support both /branch/ and /commits/branch/ patterns
        # Capture everything after /branch/ or /commits/branch/ until end of string or query params
        pattern1 = rf'https://bitbucket\.org/{re.escape(environment.config.bitbucket.workspace)}/{re.escape(environment.config.bitbucket.repo)}/branch/(.+)'
        pattern2 = rf'https://bitbucket\.org/{re.escape(environment.config.bitbucket.workspace)}/{re.escape(environment.config.bitbucket.repo)}/commits/branch/(.+)'

        # Combine patterns with OR
        self.PATTERN = re.compile(f'(?:{pattern1})|(?:{pattern2})')
        super().__init__(environment, state, priority=4)

        self.logger.debug(
            "BranchLinkHandler initialized for {0}/{1} -> {2}/{3}".format(
                self.environment.config.bitbucket.workspace,
                self.environment.config.bitbucket.repo,
                self.environment.config.github.owner,
                self.environment.config.github.repo
            )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle Bitbucket branch link rewriting.

        Args:
            url: The Bitbucket branch URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub URL or None if URL doesn't match
        """
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            self.logger.debug(f"URL did not match branch pattern: {url}")
            return None

        # Extract branch name (from either pattern group)
        branch_name = match.group(1) or match.group(2)

        # URL-encode branch name (encode slashes and special chars)
        encoded_branch = self.encode_url_component(branch_name, safe='')

        gh_url = f"https://github.com/{self.environment.config.github.owner}/{self.environment.config.github.repo}/tree/{encoded_branch}"

        markdown_context = context.get('markdown_context', None)

        # If in markdown target context, return URL only (no note)
        if markdown_context == 'target':
            rewritten = gh_url  # Just the URL
        else:
            # Normal context - return formatted link with note
            note = self.format_note(
                'branch_link',
                bb_url=url,
                gh_url=gh_url,
                branch_name=branch_name
            )
            if note:
                rewritten = f"[commits on `{branch_name}`]({gh_url}){note}"
            else:
                rewritten = f"[commits on `{branch_name}`]({gh_url})"

        context['details'].append({
            'original': url,
            'rewritten': rewritten,
            'type': 'branch_link',
            'reason': 'mapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context', None)
        })

        return rewritten