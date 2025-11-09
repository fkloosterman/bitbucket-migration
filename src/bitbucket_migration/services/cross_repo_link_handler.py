import re
import logging
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler
from .issue_link_handler import IssueLinkHandler
from .pr_link_handler import PrLinkHandler
from .commit_link_handler import CommitLinkHandler

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData


class CrossRepoLinkHandler(BaseLinkHandler):
    """
    Handler for cross-repository links (issues, src, commits, pull-requests, repository home).

    Handles links that reference other Bitbucket repositories, delegating to
    appropriate handlers with mapped GitHub repositories. Supports deferred
    processing for repositories that haven't been migrated yet. Also handles
    repository home URLs for cross-repository links.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the CrossRepoLinkHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
        """
        super().__init__(environment, state, priority=6)  # After specific repo handlers
        
        # Pre-compile pattern at initialization
        self.PATTERN = re.compile(
            r'https://bitbucket\.org/([^/]+)/([^/]+)(?:/(issues|src|raw|commits|pull-requests)(/[^\s\)"\'>]+)?)?'
        )
        
        # Read detection_only mode from config
        options = getattr(self.environment.config, 'options', None)

        # Determine detection mode based on operation type
        if self.environment.mode == "cross-link":
            # Cross-link operations: always rewrite detected links
            self.detection_only = False
        else:
            # Initial migration: respect user config setting
            self.detection_only = not getattr(options, 'rewrite_cross_repo_links', False) if options else False

        self.logger.debug(
                "CrossRepoLinkHandler initialized for {0}/{1} -> {2}/{3} (detection_only={4})".format(
                self.environment.config.bitbucket.workspace,
                self.environment.config.bitbucket.repo,
                self.environment.config.github.owner,
                self.environment.config.github.repo,
                self.detection_only
                )
        )

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Handle cross-repository link rewriting.

        Args:
            url: The Bitbucket cross-repo URL to rewrite
            context: Context information including item details and markdown context

        Returns:
            Rewritten GitHub URL or None if URL doesn't match
        """
        match = self.PATTERN.match(url)  # Use pre-compiled pattern
        if not match:
            self.logger.debug(f"URL did not match cross-repo pattern: {url}")
            return None
        # Check if this is a same-repository link - if so, let higher priority handlers handle it
        workspace = match.group(1)
        repo = match.group(2)
        if workspace == self.environment.config.bitbucket.workspace and repo == self.environment.config.bitbucket.repo:
            self.logger.debug(f"Same-repository link, letting higher priority handlers handle: {url}")
            return None

        resource_type = match.group(3)
        resource_path = match.group(4)[1:] if match.group(4) else ""

        # Check if URL is an image/attachment that should be ignored
        if self._should_ignore_url(url):
            self.logger.debug(f"URL is an image/attachment, ignoring: {url}")
            return None

        workspace = match.group(1)
        repo = match.group(2)
        resource_type = match.group(3)
        resource_path = match.group(4)[1:] if match.group(4) else ""

        # In detection-only mode, track the link but keep URL unchanged
        if self.detection_only:
            rewritten = url
            repo_key = f"{workspace}/{repo}"
            
            # Determine resource type for tracking
            if resource_type == 'issues':
                resource_type_key = 'issue'
            elif resource_type == 'pull-requests':
                resource_type_key = 'pr'
            elif resource_type == 'commits':
                resource_type_key = 'commit'
            elif resource_type == 'src':
                resource_type_key = 'src'
            elif resource_type == 'raw':
                resource_type_key = 'raw'
            else:
                resource_type_key = 'repo_home'
            
            # Track as detected cross-repo link
            self._add_to_details(context, url, rewritten, 'cross_repo_link', 'detected')
            
            # Add metadata for reporting
            context['details'][-1]['repo_key'] = repo_key
            context['details'][-1]['resource_type'] = resource_type_key
            context['details'][-1]['detection_only'] = True
            
            self.logger.debug(f"Detected cross-repo {resource_type_key} link to {repo_key} (detection-only mode)")
            return rewritten

        # Normal rewriting mode (not detection-only)
        # Initialize with default values
        gh_owner = self.environment.config.github.owner
        gh_repo = self.environment.config.github.repo

        # Determine mapped repos
        if workspace == self.environment.config.bitbucket.workspace and repo == self.environment.config.bitbucket.repo:
            # Already set to self.environment.config.github.owner, self.environment.config.github.repo
            pass
        else:
            mapped_owner, mapped_repo = self.environment.services.get('cross_repo_mapping_store').get_mapped_repository(workspace, repo)
            if not mapped_repo:
                rewritten = url
                self._add_to_details(context, url, rewritten, 'cross_repo_link', 'unmapped')
                return rewritten
            gh_repo = mapped_repo
            if mapped_owner:
                gh_owner = mapped_owner
            else:
                gh_owner = self.environment.config.github.owner

        # Handle repository home URLs (no resource_type)
        if resource_type is None:
            rewritten = self._rewrite_repo_home(url, workspace, repo, gh_owner, gh_repo, context)
        # Delegate to appropriate handler or handle directly
        elif resource_type == 'issues':
            
            handler = None
            # Determine which mapping to use
            if workspace == self.environment.config.bitbucket.workspace and repo == self.environment.config.bitbucket.repo:
                # Same repository - use current mapping
                # external_issue_mapping = self.state.mappings.issues
                handler = IssueLinkHandler(self.environment, self.state)
            elif self.environment.services.get('cross_repo_mapping_store').has_repository(workspace, repo):
                # Cross-repo with available mapping
                # external_issue_mapping = self.environment.services.get('cross_repo_mapping_store').get_issue_mapping(workspace, repo)
                handler = IssueLinkHandler(self.environment, self.state, workspace, repo)
            else:
                # Cross-repo without mapping - keep as Bitbucket URL and track
                # external_issue_mapping = {}
                rewritten = url
                repo_key = f"{workspace}/{repo}"
                self._track_deferred_link(url, repo_key, 'issue', context)

            if handler:
                delegate_context = {
                    'details': context['details'],
                    'item_type': context.get('item_type'),
                    'item_number': context.get('item_number'),
                    'comment_seq': context.get('comment_seq'),
                    'markdown_context': context.get('markdown_context')
                }
                rewritten = handler.handle(url, delegate_context)
        elif resource_type == 'pull-requests':
            repo_key = f"{workspace}/{repo}"

            # Determine which mapping to use
            if workspace == self.environment.config.bitbucket.workspace and repo == self.environment.config.bitbucket.repo:
                # Same repository - use current mapping
                external_pr_mapping = self.state.mappings.prs
            elif self.environment.services.get('cross_repo_mapping_store').has_repository(workspace, repo):
                # Cross-repo with available mapping
                external_pr_mapping = self.environment.services.get('cross_repo_mapping_store').get_pr_mapping(workspace, repo)
            else:
                # Cross-repo without mapping - keep as Bitbucket URL and track
                external_pr_mapping = {}
                self._track_deferred_link(url, repo_key, 'pr', context)

            rewritten = self._rewrite_pr(url, workspace, repo, resource_path, gh_owner, gh_repo, context, external_pr_mapping)
        elif resource_type == 'commits':
            handler = CommitLinkHandler(self.environment, self.state)
            delegate_context = {
                'details': context['details'],
                'item_type': context.get('item_type'),
                'item_number': context.get('item_number'),
                'comment_seq': context.get('comment_seq'),
                'markdown_context': context.get('markdown_context', None)
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

    def _rewrite_repo_home(self, url: str, workspace: str, repo: str, gh_owner: str, gh_repo: str, context: Dict[str, Any]) -> str:
        """
        Rewrite Bitbucket repository home URLs to GitHub repository URLs.

        Args:
            url: Original Bitbucket repository home URL
            workspace: Bitbucket workspace
            repo: Bitbucket repository
            gh_owner: GitHub owner
            gh_repo: GitHub repository
            context: Context information

        Returns:
            Rewritten GitHub repository URL
        """
        gh_url = f"https://github.com/{gh_owner}/{gh_repo}"

        markdown_context = context.get('markdown_context', None)

        # If in markdown target context, return URL only (no note)
        if markdown_context == 'target':
            rewritten = gh_url  # Just the URL
        else:
            # Normal context - return formatted link with note
            note = self.format_note(
                'cross_repo_link',
                bb_url=url,
                gh_url=gh_url,
                gh_repo=gh_repo
            )
            if note:
                rewritten = f"[{gh_repo}]({gh_url}){note}"
            else:
                rewritten = f"[{gh_repo}]({gh_url})"

        self._add_to_details(context, url, rewritten, 'cross_repo_link', 'mapped')
        return rewritten

    def _rewrite_src(self, url: str, workspace: str, repo: str, resource_path: str, gh_owner: str, gh_repo: str, context: Dict[str, Any]) -> str:
        """
        Rewrite Bitbucket src URLs to GitHub blob URLs.

        Args:
            url: Original Bitbucket URL
            workspace: Bitbucket workspace
            repo: Bitbucket repository
            resource_path: Path part of the URL (ref/file_path)
            gh_owner: GitHub owner
            gh_repo: GitHub repository
            context: Context information

        Returns:
            Rewritten GitHub URL
        """
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

            markdown_context = context.get('markdown_context', None)

            if workspace == self.environment.config.bitbucket.workspace and repo == self.environment.config.bitbucket.repo:
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
        """
        Rewrite Bitbucket PR URLs to GitHub PR/issue URLs.

        Args:
            url: Original Bitbucket URL
            workspace: Bitbucket workspace
            repo: Bitbucket repository
            resource_path: Path part containing PR number
            gh_owner: GitHub owner
            gh_repo: GitHub repository
            context: Context information
            pr_mapping: Optional mapping from Bitbucket PR numbers to GitHub numbers

        Returns:
            Rewritten GitHub URL
        """
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

        markdown_context = context.get('markdown_context', None)

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
        """
        Rewrite Bitbucket raw file URLs to GitHub raw URLs.

        Args:
            url: Original Bitbucket URL
            workspace: Bitbucket workspace
            repo: Bitbucket repository
            resource_path: Path part of the URL (ref/file_path)
            gh_owner: GitHub owner
            gh_repo: GitHub repository
            context: Context information

        Returns:
            Rewritten GitHub raw URL
        """
        parts = resource_path.split('/', 1)
        if len(parts) == 2:
            ref, file_path = parts

            # URL-encode the ref (branch/tag) but keep slashes in file path
            encoded_ref = self.encode_url_component(ref, safe='')

            # URL-encode the file path as well
            encoded_file_path = self.encode_url_component(file_path, safe='/')

            # GitHub raw URL
            gh_url = f"https://github.com/{gh_owner}/{gh_repo}/raw/{encoded_ref}/{encoded_file_path}"

            filename = file_path.split('/')[-1]
            markdown_context = context.get('markdown_context', None)

            if workspace == self.environment.config.bitbucket.workspace and repo == self.environment.config.bitbucket.repo:
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

    def _track_deferred_link(self, url: str, repo_key: str, resource_type: str, context: Dict[str, Any]) -> None:
        """
        Track a cross-repo link that cannot be rewritten yet.

        These links are deferred until Phase 2 when all repository mappings are available.

        Args:
            url: The original Bitbucket URL
            repo_key: Repository key (workspace/repo)
            resource_type: Type of resource (issue, pr, etc.)
            context: Context information for tracking
        """
        self._add_to_details(context, url, url, 'cross_repo_deferred', 'mapping_not_available')

        # Add metadata for reporting
        context['details'][-1]['repo_key'] = repo_key
        context['details'][-1]['resource_type'] = resource_type

        self.logger.info(
            f"Deferred cross-repo {resource_type} link to {repo_key} "
            f"(will be rewritten in Phase 2 after that repository is migrated)"
        )

    def _add_to_details(self, context: Dict[str, Any], original: str, rewritten: str, link_type: str, reason: str):
        """
        Add link processing details to the context.

        Args:
            context: Context dictionary containing details list
            original: Original URL
            rewritten: Rewritten URL
            link_type: Type of link (cross_repo_link, etc.)
            reason: Reason for the result (mapped, unmapped, etc.)
        """
        context['details'].append({
            'original': original,
            'rewritten': rewritten,
            'type': link_type,
            'reason': reason,
            'item_type': context.get('item_type'),
            'item_number': context.get('item_number'),
            'comment_seq': context.get('comment_seq'),
            'comment_id': context.get('comment_id'),
        })

    def _should_ignore_url(self, url: str) -> bool:
        """
        Check if URL should be ignored (contains image/attachment paths).
        
        These URLs should be preserved as-is since they don't represent
        repository content that needs to be migrated to GitHub.
        
        Args:
            url: The URL to check
            
        Returns:
            True if URL should be ignored, False otherwise
        """
        ignored_patterns = [
            r'/images/',
            r'/attachments/',
            r'/thumbnails/',
            r'/avatars/',
        ]
        
        for pattern in ignored_patterns:
            if re.search(pattern, url):
                return True
        return False