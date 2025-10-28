import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

logger = logging.getLogger('bitbucket_migration')

class RepoHomeLinkHandler(BaseLinkHandler):
    """
    Handler for Bitbucket repository home links.
    Lowest priority to avoid matching specific links.
    """

    def __init__(self, repo_mapping: Dict[str, str], bb_workspace: str, bb_repo: str,
                   gh_owner: str, gh_repo: str, template_config=None):
        # Pre-compile pattern at initialization
        self.PATTERN = re.compile(
            rf'https://bitbucket\.org/{re.escape(bb_workspace)}/{re.escape(bb_repo)}(?=\s|\)|"|\'|>|$|$)'
        )
        super().__init__(priority=10, template_config=template_config)  # Low priority

        self.repo_mapping = repo_mapping
        self.bb_workspace = bb_workspace
        self.bb_repo = bb_repo
        self.gh_owner = gh_owner
        self.gh_repo = gh_repo

        logger.debug(
            "RepoHomeLinkHandler initialized for %s/%s -> %s/%s",
            bb_workspace, bb_repo, gh_owner, gh_repo
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        workspace, repo = self.bb_workspace, self.bb_repo
        if workspace == self.bb_workspace and repo == self.bb_repo:
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}"

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
                    rewritten = f"[repository]({gh_url}){note}"
                else:
                    rewritten = f"[repository]({gh_url})"
        else:
            repo_key = f"{workspace}/{repo}"
            if repo_key in self.repo_mapping:
                gh_repo_full = self.repo_mapping[repo_key]
                if '/' in gh_repo_full:
                    gh_owner, gh_repo = gh_repo_full.split('/', 1)
                else:
                    gh_owner = self.gh_owner
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

        if 'link_details' in context:
            context['link_details'].append({
                'original': url,
                'rewritten': rewritten,
                'type': 'repo_home_link',
                'reason': 'mapped' if rewritten != url else 'unmapped',
                'item_type': context.get('item_type'),
                'item_number': context.get('item_number'),
                'comment_seq': context.get('comment_seq'),
                'markdown_context': context.get('markdown_context')
            })

        return rewritten