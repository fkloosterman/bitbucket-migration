import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class SourceFileLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket source file links (src, raw).

    Rewrites Bitbucket source file URLs to their corresponding GitHub blob/raw URLs.
    This handler should have higher priority than CrossRepoLinkHandler to ensure
    same-repository source files are handled correctly.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the SourceFileLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
        """
        super().__init__(environment, state, priority=4)  # Higher than CrossRepoLinkHandler (6)

        self.bb_workspace = self.environment.config.bitbucket.workspace
        self.bb_repo = self.environment.config.bitbucket.repo
        self.gh_owner = self.environment.config.github.owner
        self.gh_repo = self.environment.config.github.repo

        # Pre-compile pattern for same-repository source files only
        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(self.bb_workspace)}/{re.escape(self.bb_repo)}/(src|raw)/([^\s\)"\'>]+)'
        )

        self.logger.debug(
            "SourceFileLinkHandler initialized for {0}/{1} -> {2}/{3}".format(
                self.bb_workspace, self.bb_repo,
                self.gh_owner, self.gh_repo
            )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle Bitbucket source file link rewriting.

        Args:
            url: The Bitbucket source file URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub URL or None if URL doesn't match
        """
        match = self.PATTERN.match(url)
        if not match:
            self.logger.debug(f"URL did not match source file pattern: {url}")
            return None

        resource_type = match.group(1)  # 'src' or 'raw'
        resource_path = match.group(2)  # ref/file_path

        # Parse the resource path (ref/file_path or ref/file_path#lines-N)
        if '#lines-' in resource_path:
            file_path_part, line_ref = resource_path.split('#lines-', 1)
            parts = file_path_part.split('/', 1)
            if len(parts) == 2:
                ref, file_path = parts
                encoded_ref = self.encode_url_component(ref, safe='')
                encoded_file_path = self.encode_url_component(file_path, safe='/')
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/blob/{encoded_ref}/{encoded_file_path}#L{line_ref}"
            else:
                # Invalid format, return original
                return url
        else:
            parts = resource_path.split('/', 1)
            if len(parts) == 2:
                ref, file_path = parts

                # URL-encode the ref (branch/tag) but keep slashes in file path
                encoded_ref = self.encode_url_component(ref, safe='')
                encoded_file_path = self.encode_url_component(file_path, safe='/')

                if resource_type == 'src':
                    gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/blob/{encoded_ref}/{encoded_file_path}"
                else:  # 'raw'
                    gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/raw/{encoded_ref}/{encoded_file_path}"
            else:
                # Invalid format, return original
                return url

        filename = file_path.split('/')[-1] if '/' in file_path else file_path
        markdown_context = context.get('markdown_context', None)

        # If in markdown target context, return URL only (no note)
        if markdown_context == 'target':
            rewritten = gh_url  # Just the URL
        else:
            # Normal context - return formatted link with note
            note = self.format_note(
                'source_file_link',
                bb_url=url,
                gh_url=gh_url,
                filename=filename
            )
            if note:
                rewritten = f"[{filename}]({gh_url}){note}"
            else:
                rewritten = f"[{filename}]({gh_url})"

        context['details'].append({
            'original': url,
            'rewritten': rewritten,
            'type': 'source_file_link',
            'reason': 'mapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context', None)
        })

        return rewritten