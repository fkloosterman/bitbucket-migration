import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler
from .issue_link_handler import IssueLinkHandler
from .pr_link_handler import PrLinkHandler
from .commit_link_handler import CommitLinkHandler

logger = logging.getLogger('bitbucket_migration')

class CrossRepoLinkHandler(BaseLinkHandler):
    """
    Handler for cross-repository links (issues, src, commits).
    Delegates to specific handlers with mapped repositories.
    """

    def __init__(self, cross_repo_store, bb_workspace: str, bb_repo: str,
                    gh_owner: str, gh_repo: str, issue_mapping: Dict[int, int], pr_mapping: Dict[int, int],
                    template_config=None):
        # Pre-compile pattern at initialization
        self.PATTERN = re.compile(
            r'https://bitbucket\.org/([^/]+)/([^/]+)/(issues|src|raw|commits|pull-requests)(/[^\s\)"\'>]+)'
        )
        super().__init__(priority=6, template_config=template_config)  # After specific repo handlers

        self.cross_repo_store = cross_repo_store
        self.bb_workspace = bb_workspace
        self.bb_repo = bb_repo
        self.gh_owner = gh_owner
        self.gh_repo = gh_repo
        self.issue_mapping = issue_mapping
        self.pr_mapping = pr_mapping

        logger.debug(
            "CrossRepoLinkHandler initialized for %s/%s -> %s/%s",
            bb_workspace, bb_repo, gh_owner, gh_repo
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            logger.debug("URL did not match cross-repo pattern: %s", url)
            return None

        workspace = match.group(1)
        repo = match.group(2)
        resource_type = match.group(3)
        resource_path = match.group(4)[1:]

        # Determine mapped repos
        if workspace == self.bb_workspace and repo == self.bb_repo:
            gh_owner = self.gh_owner
            gh_repo = self.gh_repo
            mapped = True
        else:
            repo_key = f"{workspace}/{repo}"
            repo_mapping = self.cross_repo_store.get_repository_mapping()
            if repo_key not in repo_mapping:
                rewritten = url
                self._add_to_details(context, url, rewritten, 'cross_repo_link', 'unmapped')
                return rewritten
            gh_repo_full = repo_mapping[repo_key]
            if '/' in gh_repo_full:
                gh_owner, gh_repo = gh_repo_full.split('/', 1)
            else:
                gh_owner = self.gh_owner
                gh_repo = gh_repo_full
            mapped = True

        # Delegate to appropriate handler or handle directly
        if resource_type == 'issues':
            repo_key = f"{workspace}/{repo}"

            # Determine which mapping to use
            if workspace == self.bb_workspace and repo == self.bb_repo:
                # Same repository - use current mapping
                external_issue_mapping = self.issue_mapping
            elif self.cross_repo_store.has_repository(workspace, repo):
                # Cross-repo with available mapping
                external_issue_mapping = self.cross_repo_store.get_issue_mapping(workspace, repo)
            else:
                # Cross-repo without mapping - keep as Bitbucket URL and track
                external_issue_mapping = {}
                self._track_deferred_link(url, repo_key, 'issue', context)

            handler = IssueLinkHandler(external_issue_mapping, workspace, repo, gh_owner, gh_repo, self.template_config)
            delegate_context = {
                'link_details': context['link_details'],
                'item_type': context.get('item_type'),
                'item_number': context.get('item_number'),
                'comment_seq': context.get('comment_seq'),
                'markdown_context': context.get('markdown_context')
            }
            rewritten = handler.handle(url, delegate_context)
        elif resource_type == 'pull-requests':
            repo_key = f"{workspace}/{repo}"

            # Determine which mapping to use
            if workspace == self.bb_workspace and repo == self.bb_repo:
                # Same repository - use current mapping
                external_pr_mapping = self.pr_mapping
            elif self.cross_repo_store.has_repository(workspace, repo):
                # Cross-repo with available mapping
                external_pr_mapping = self.cross_repo_store.get_pr_mapping(workspace, repo)
            else:
                # Cross-repo without mapping - keep as Bitbucket URL and track
                external_pr_mapping = {}
                self._track_deferred_link(url, repo_key, 'pr', context)

            rewritten = self._rewrite_pr(url, workspace, repo, resource_path, gh_owner, gh_repo, context, external_pr_mapping)
        elif resource_type == 'commits':
            handler = CommitLinkHandler(workspace, repo, gh_owner, gh_repo, self.template_config)
            delegate_context = {
                'link_details': context['link_details'],
                'item_type': context.get('item_type'),
                'item_number': context.get('item_number'),
                'comment_seq': context.get('comment_seq'),
                'markdown_context': context.get('markdown_context')
            }
            rewritten = handler.handle(url, delegate_context)
        elif resource_type == 'src':
            rewritten = self._rewrite_src(url, workspace, repo, resource_path, gh_owner, gh_repo, context)
        elif resource_type == 'raw':
            rewritten = self._rewrite_raw(url, workspace, repo, resource_path, gh_owner, gh_repo, context)
        else:
            rewritten = url
            self._add_to_details(context, url, rewritten, 'cross_repo_link', 'unmapped')

        return rewritten

    def _rewrite_src(self, url: str, workspace: str, repo: str, resource_path: str, gh_owner: str, gh_repo: str, context: Dict[str, Any]) -> str:
        parts = resource_path.split('/', 1)
        if len(parts) == 2:
            ref, file_path = parts

            # URL-encode the ref (branch/tag) but keep slashes in file path
            encoded_ref = self.encode_url_component(ref, safe='')

            # URL-encode the file path as well
            encoded_file_path = self.encode_url_component(file_path, safe='/')

            if '#lines-' in file_path:
                file_path_part, line_ref = file_path.split('#lines-', 1)
                encoded_file_path = self.encode_url_component(file_path_part, safe='/')
                gh_url = f"https://github.com/{gh_owner}/{gh_repo}/blob/{encoded_ref}/{encoded_file_path}#L{line_ref}"
            else:
                gh_url = f"https://github.com/{gh_owner}/{gh_repo}/blob/{encoded_ref}/{encoded_file_path}"
            filename = file_path.split('/')[-1]

            markdown_context = context.get('markdown_context')

            if workspace == self.bb_workspace and repo == self.bb_repo:
                # If in markdown target context, return URL only (no note)
                if markdown_context == 'target':
                    rewritten = gh_url  # Just the URL
                else:
                    # Normal context - return formatted link with note
                    note = self.format_note(
                        'cross_repo_link',
                        bb_url=url,
                        gh_url=gh_url,
                        gh_repo=gh_repo,
                        filename=filename
                    )
                    if note:
                        rewritten = f"[{filename}]({gh_url}){note}"
                    else:
                        rewritten = f"[{filename}]({gh_url})"
            else:
                # If in markdown target context, return URL only (no note)
                if markdown_context == 'target':
                    rewritten = gh_url  # Just the URL
                else:
                    # Normal context - return formatted link with note
                    note = self.format_note(
                        'cross_repo_link',
                        bb_url=url,
                        gh_url=gh_url,
                        gh_repo=gh_repo,
                        filename=filename
                    )
                    if note:
                        rewritten = f"[{gh_repo}/{filename}]({gh_url}){note}"
                    else:
                        rewritten = f"[{gh_repo}/{filename}]({gh_url})"
        else:
            rewritten = url

        self._add_to_details(context, url, rewritten, 'cross_repo_link', 'mapped')
        return rewritten

    def _rewrite_pr(self, url: str, workspace: str, repo: str, resource_path: str, gh_owner: str, gh_repo: str, context: Dict[str, Any], pr_mapping: Optional[Dict[int, int]] = None) -> str:
        pr_number_str = resource_path.split('/')[0]
        try:
            pr_number = int(pr_number_str)
        except ValueError:
            # Invalid PR number, keep as-is
            rewritten = url
            self._add_to_details(context, url, rewritten, 'cross_repo_link', 'invalid_pr_number')
            return rewritten

        # Use mapping if available
        if pr_mapping and pr_number in pr_mapping:
            gh_number = pr_mapping[pr_number]
            gh_url = f"https://github.com/{gh_owner}/{gh_repo}/pull/{gh_number}"
        else:
            # No mapping available, keep as issues URL (fallback)
            gh_url = f"https://github.com/{gh_owner}/{gh_repo}/issues/{pr_number}"

        markdown_context = context.get('markdown_context')

        # If in markdown target context, return URL only (no note)
        if markdown_context == 'target':
            rewritten = gh_url  # Just the URL
        else:
            # Normal context - return formatted link with note
            note = self.format_note(
                'cross_repo_link',
                bb_url=url,
                gh_url=gh_url,
                gh_repo=gh_repo,
                pr_number=pr_number
            )
            if note:
                rewritten = f"[{gh_repo} PR #{pr_number}]({gh_url}){note}"
            else:
                rewritten = f"[{gh_repo} PR #{pr_number}]({gh_url})"

        self._add_to_details(context, url, rewritten, 'cross_repo_link', 'mapped')
        return rewritten

    def _rewrite_raw(self, url: str, workspace: str, repo: str, resource_path: str, gh_owner: str, gh_repo: str, context: Dict[str, Any]) -> str:
        """Rewrite raw file URLs to GitHub raw URLs."""
        parts = resource_path.split('/', 1)
        if len(parts) == 2:
            ref, file_path = parts

            # URL-encode the ref (branch/tag) but keep slashes in file path
            encoded_ref = self.encode_url_component(ref, safe='')

            # URL-encode the file path as well
            encoded_file_path = self.encode_url_component(file_path, safe='/')

            # GitHub raw URL
            gh_url = f"https://github.com/{gh_owner}/{gh_repo}/raw/{encoded_ref}/{encoded_file_path}"

            markdown_context = context.get('markdown_context')

            if workspace == self.bb_workspace and repo == self.bb_repo:
                # If in markdown target context, return URL only (no note)
                if markdown_context == 'target':
                    rewritten = gh_url  # Just the URL
                else:
                    # Normal context - return formatted link with note
                    filename = file_path.split('/')[-1]
                    note = self.format_note(
                        'cross_repo_link',
                        bb_url=url,
                        gh_url=gh_url,
                        gh_repo=gh_repo,
                        filename=filename
                    )
                    if note:
                        rewritten = f"[{filename}]({gh_url}){note}"
                    else:
                        rewritten = f"[{filename}]({gh_url})"
            else:
                # If in markdown target context, return URL only (no note)
                if markdown_context == 'target':
                    rewritten = gh_url  # Just the URL
                else:
                    # Normal context - return formatted link with note
                    filename = file_path.split('/')[-1]
                    note = self.format_note(
                        'cross_repo_link',
                        bb_url=url,
                        gh_url=gh_url,
                        gh_repo=gh_repo,
                        filename=filename
                    )
                    if note:
                        rewritten = f"[{gh_repo}/{filename}]({gh_url}){note}"
                    else:
                        rewritten = f"[{gh_repo}/{filename}]({gh_url})"
        else:
            rewritten = url

        self._add_to_details(context, url, rewritten, 'cross_repo_link', 'mapped')
        return rewritten

    def _track_deferred_link(self, url: str, repo_key: str, resource_type: str, context: Dict[str, Any]) -> None:
        """
        Track a cross-repo link that cannot be rewritten yet.

        These links are deferred until Phase 2 when all repository mappings are available.
        """
        self._add_to_details(context, url, url, 'cross_repo_deferred', 'mapping_not_available')

        # Add metadata for reporting
        if context.get('link_details') and context['link_details']:
            context['link_details'][-1]['repo_key'] = repo_key
            context['link_details'][-1]['resource_type'] = resource_type

        logger.info(
            f"Deferred cross-repo {resource_type} link to {repo_key} "
            f"(will be rewritten in Phase 2 after that repository is migrated)"
        )

    def _add_to_details(self, context: Dict[str, Any], original: str, rewritten: str, link_type: str, reason: str):
        if 'link_details' in context:
            context['link_details'].append({
                'original': original,
                'rewritten': rewritten,
                'type': link_type,
                'reason': reason,
                'item_type': context.get('item_type'),
                'item_number': context.get('item_number'),
                'comment_seq': context.get('comment_seq')
            })