import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class CompareLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket compare links.

    Rewrites Bitbucket compare URLs (both legacy SHA-only and modern branch/tag
    comparison URLs) to their corresponding GitHub compare URLs.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the CompareLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
        """
        # Pattern 1: /compare/{sha1}..{sha2} (legacy, SHA-only)
        pattern1 = rf'https://bitbucket\.org/{re.escape(environment.config.bitbucket.workspace)}/{re.escape(environment.config.bitbucket.repo)}/compare/([0-9a-f]{{6,40}})\.\.([0-9a-f]{{6,40}})$'

        # Pattern 2: /branches/compare/{comparison} (supports both SHAs and branch names)
        pattern2 = rf'https://bitbucket\.org/{re.escape(environment.config.bitbucket.workspace)}/{re.escape(environment.config.bitbucket.repo)}/branches/compare/([^.]+)\.\.([^/\s\)]+)$'

        # Combine with OR
        self.PATTERN = re.compile(f'(?:{pattern1})|(?:{pattern2})')
        super().__init__(environment, state, priority=5)

        self.logger.debug(
            "CompareLinkHandler initialized for {0}/{1} -> {2}/{3}".format(
                self.environment.config.bitbucket.workspace,
                self.environment.config.bitbucket.repo,
                self.environment.config.github.owner,
                self.environment.config.github.repo
            )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle Bitbucket compare link rewriting.

        Args:
            url: The Bitbucket compare URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub compare URL or None if URL doesn't match
        """
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            self.logger.debug(f"URL did not match compare pattern: {url}")
            return None

        # Extract from either pattern (group 1&2 OR group 3&4)
        ref1 = match.group(1) or match.group(3)
        ref2 = match.group(2) or match.group(4)

        if not ref1 or not ref2:
            return None

        # URL-encode the refs for GitHub
        encoded_ref1 = self.encode_url_component(ref1, safe='')
        encoded_ref2 = self.encode_url_component(ref2, safe='')

        # GitHub uses three dots for compare
        gh_url = f"https://github.com/{self.environment.config.github.owner}/{self.environment.config.github.repo}/compare/{encoded_ref1}...{encoded_ref2}"

        markdown_context = context.get('markdown_context', None)

        # If in markdown target context, return URL only (no note)
        if markdown_context == 'target':
            rewritten = gh_url  # Just the URL
        else:
            # Normal context - return formatted link with note
            note = self.format_note(
                'compare_link',
                bb_url=url,
                gh_url=gh_url,
                ref1=ref1,
                ref2=ref2
            )
            if note:
                rewritten = f"[compare `{ref1[:7] if len(ref1) > 7 else ref1}`...`{ref2[:7] if len(ref2) > 7 else ref2}`]({gh_url}){note}"
            else:
                rewritten = f"[compare `{ref1[:7] if len(ref1) > 7 else ref1}`...`{ref2[:7] if len(ref2) > 7 else ref2}`]({gh_url})"

        context['details'].append({
            'original': url,
            'rewritten': rewritten,
            'type': 'compare_link',
            'reason': 'mapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context', None)
        })

        return rewritten