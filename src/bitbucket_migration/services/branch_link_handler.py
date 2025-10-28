import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

logger = logging.getLogger('bitbucket_migration')

class BranchLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket branch links.
    """

    def __init__(self, bb_workspace: str, bb_repo: str, gh_owner: str, gh_repo: str, template_config=None):
        # Support both /branch/ and /commits/branch/ patterns
        # Capture everything after /branch/ or /commits/branch/ until end of string or query params
        pattern1 = rf'https://bitbucket\.org/{re.escape(bb_workspace)}/{re.escape(bb_repo)}/branch/(.+)'
        pattern2 = rf'https://bitbucket\.org/{re.escape(bb_workspace)}/{re.escape(bb_repo)}/commits/branch/(.+)'

        # Combine patterns with OR
        self.PATTERN = re.compile(f'(?:{pattern1})|(?:{pattern2})')
        super().__init__(priority=4, template_config=template_config)

        self.bb_workspace = bb_workspace
        self.bb_repo = bb_repo
        self.gh_owner = gh_owner
        self.gh_repo = gh_repo

        logger.debug(
            "BranchLinkHandler initialized for %s/%s -> %s/%s",
            bb_workspace, bb_repo, gh_owner, gh_repo
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            logger.debug("URL did not match branch pattern: %s", url)
            return None

        # Extract branch name (from either pattern group)
        branch_name = match.group(1) or match.group(2)

        # URL-encode branch name (encode slashes and special chars)
        encoded_branch = self.encode_url_component(branch_name, safe='')

        gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/tree/{encoded_branch}"

        markdown_context = context.get('markdown_context')

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

        if 'link_details' not in context:
            context['link_details'] = []
        context['link_details'].append({
            'original': url,
            'rewritten': rewritten,
            'type': 'branch_link',
            'reason': 'mapped',
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'markdown_context': context.get('markdown_context')
        })

        return rewritten