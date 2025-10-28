import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

logger = logging.getLogger('bitbucket_migration')

class CommitLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket commit links.
    """

    def __init__(self, bb_workspace: str, bb_repo: str, gh_owner: str, gh_repo: str, template_config=None):
        # Pre-compile pattern at initialization
        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(bb_workspace)}/{re.escape(bb_repo)}/commits/([0-9a-f]{{7,40}})'
        )
        super().__init__(priority=3, template_config=template_config)

        self.bb_workspace = bb_workspace
        self.bb_repo = bb_repo
        self.gh_owner = gh_owner
        self.gh_repo = gh_repo

        logger.debug(
            "CommitLinkHandler initialized for %s/%s -> %s/%s",
            bb_workspace, bb_repo, gh_owner, gh_repo
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            logger.debug("URL did not match commit pattern: %s", url)
            return None

        commit_sha = match.group(1)
        gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/commit/{commit_sha}"

        markdown_context = context.get('markdown_context')

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

        if 'link_details' in context:
            context['link_details'].append({
                'original': url,
                'rewritten': rewritten,
                'type': 'commit_link',
                'reason': 'mapped',
                'item_type': context.get('item_type'),
                'item_number': context.get('item_number'),
                'comment_seq': context.get('comment_seq'),
                'markdown_context': context.get('markdown_context')
            })

        return rewritten