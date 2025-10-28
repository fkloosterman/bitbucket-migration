import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

logger = logging.getLogger('bitbucket_migration')

class PrLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket pull request links.
    """

    def __init__(self, pr_mapping: Dict[int, int], bb_workspace: str, bb_repo: str,
                   gh_owner: str, gh_repo: str, template_config=None):
        # Pre-compile pattern at initialization
        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(bb_workspace)}/{re.escape(bb_repo)}/pull-requests/(\d+)(?:/[^/\s\)\"\'>]*)?'
        )
        super().__init__(priority=2, template_config=template_config)  # High priority, after issues

        self.pr_mapping = pr_mapping
        self.bb_workspace = bb_workspace
        self.bb_repo = bb_repo
        self.gh_owner = gh_owner
        self.gh_repo = gh_repo

        logger.debug(
            "PrLinkHandler initialized for %s/%s -> %s/%s",
            bb_workspace, bb_repo, gh_owner, gh_repo
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            logger.debug("URL did not match PR pattern: %s", url)
            return None

        bb_num = int(match.group(1))
        gh_num = self.pr_mapping.get(bb_num)

        if gh_num:
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"

            markdown_context = context.get('markdown_context')

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

        # Update context with link details if needed
        if 'link_details' in context:
            context['link_details'].append({
                'original': url,
                'rewritten': rewritten,
                'type': 'pr_link',
                'reason': 'mapped' if gh_num else 'unmapped',
                'item_type': context.get('item_type'),
                'item_number': context.get('item_number'),
                'comment_seq': context.get('comment_seq'),
                'markdown_context': context.get('markdown_context')
            })

        return rewritten