import re
import logging
from typing import Dict, Tuple, Optional, List, Any
from urllib.parse import urlparse

from .user_mapper import UserMapper
from .base_link_handler import BaseLinkHandler
from .link_detector import LinkDetector
from .issue_link_handler import IssueLinkHandler
from .pr_link_handler import PrLinkHandler
from .commit_link_handler import CommitLinkHandler
from .branch_link_handler import BranchLinkHandler
from .compare_link_handler import CompareLinkHandler
from .cross_repo_link_handler import CrossRepoLinkHandler
from .cross_repo_mapping_store import CrossRepoMappingStore

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import LinkWriterData

class LinkRewriter:
    """
    Rewrites Bitbucket links in text to GitHub equivalents.

    This class handles the rewriting of various types of Bitbucket links (issues, PRs, commits, etc.)
    to their GitHub counterparts. It prioritizes full URL matches to avoid partial rewrites and
    deduplicates link details to prevent multiple entries in reports.

    Key improvements:
    - Prioritizes specific patterns (e.g., full PR/issue links) over general ones (e.g., repo home).
    - Ensures only full URLs are matched and rewritten to maintain link validity.
    - Deduplicates link details based on original URL and context to avoid report duplicates.
    - Handlers are pre-sorted by priority during initialization for optimal performance.
    - Preserves content inside code blocks (fenced and inline) to prevent rewriting literal content.
    """
    # Class-level compiled patterns for markdown link detection
    MARKDOWN_LINK_PATTERN = re.compile(
        r'(?<!\!)\[(?P<text>[^\]]*(?:\[[^\]]*\][^\]]*)*)\]\((?P<url>https?://[^\s)]+)\)'
    )

    # Also add image link pattern
    IMAGE_LINK_PATTERN = re.compile(
        r'!\[(?P<alt>[^\]]*(?:\[[^\]]*\][^\]]*)*)\]\((?P<url>https?://[^\s)]+)\)'
    )

    # Code block detection pattern - matches both fenced and inline code
    CODE_BLOCK_PATTERN = re.compile(
        r'(```+[a-zA-Z0-9]*\n.*?\n```+|~~~+[a-zA-Z0-9]*\n.*?\n~~~+|```[^`\n]*```|`[^`]+`)',
        re.DOTALL
    )

    # Valid GitHub URL patterns for validation
    GITHUB_URL_PATTERNS = {
        'issue': re.compile(r'https://github\.com/[\w-]+/[\w.-]+/issues/\d+'),
        'pr': re.compile(r'https://github\.com/[\w-]+/[\w.-]+/pull/\d+'),
        'commit': re.compile(r'https://github\.com/[\w-]+/[\w.-]+/commit/[0-9a-f]{7,40}'),
        'compare': re.compile(r'https://github\.com/[\w-]+/[\w.-]+/compare/[^/]+\.\.\.[^/]+'),
        'tree': re.compile(r'https://github\.com/[\w-]+/[\w.-]+/tree/.+'),
        'blob': re.compile(r'https://github\.com/[\w-]+/[\w.-]+/blob/.+'),
        'raw': re.compile(r'https://github\.com/[\w-]+/[\w.-]+/raw/.+'),
        'repo': re.compile(r'https://github\.com/[\w-]+/[\w.-]+/?$'),
    }
    
    def __init__(self, environment: MigrationEnvironment, state: MigrationState, handlers: Optional[List[BaseLinkHandler]] = None):
        """
        Initialize the LinkRewriter.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing link data
            handlers: Optional list of link handler classes to use
        """
        self.environment = environment
        self.state = state

        self.logger = self.environment.logger

        self.data = LinkWriterData()
        self.state.services[self.__class__.__name__] = self.data

        self.unhandled_bb_links = []
        # Validation failure tracking
        self.validation_failures: List[Dict[str, Any]] = []
        self.validation_errors: int = 0
        # Context for current item being processed
        self.current_item_type = None
        self.current_item_number = None
        self.current_comment_seq = None
        self.current_comment_id = None
        # Track processed URLs to avoid duplicates
        self.processed_urls = set()

        # Build repository lookup including external repos
        self.repo_lookup = self._build_repo_lookup(getattr(self.environment.config, 'external_repositories', []))

        # Initialize handlers
        if handlers is None:
            from .source_file_link_handler import SourceFileLinkHandler
            from .repo_home_link_handler import RepoHomeLinkHandler
            handlers = [IssueLinkHandler, PrLinkHandler, CommitLinkHandler, SourceFileLinkHandler, RepoHomeLinkHandler, BranchLinkHandler, CompareLinkHandler, CrossRepoLinkHandler]

        handlers = set(handlers)

        if not all([issubclass(h, BaseLinkHandler) for h in handlers]):
            raise ValueError("Expect handlers to be a subclass of `BaseLinkHandler`")

        self.handlers: List[BaseLinkHandler] = [
            h(self.environment, self.state) for h in handlers
        ]

        # Sort once at initialization instead of per URL
        self.handlers = sorted(self.handlers, key=lambda h: h.get_priority())
        self.logger.info(f"Initialized {len(self.handlers)} link handlers (sorted by priority)")
        self.logger.info(f"Built repository lookup with {len(self.repo_lookup)} external repositories")

    def _build_repo_lookup(self, external_repos: List[Any]) -> Dict[str, Dict[str, Any]]:
        """
        Build repository lookup dictionary including external repositories.

        Args:
            external_repos: List of ExternalRepositoryConfig objects

        Returns:
            Dictionary mapping "{workspace}/{repo}" to repository info
        """
        repo_lookup = {}

        # Add external repositories to lookup
        for ext_repo in external_repos:
            key = f"{self.environment.config.bitbucket.workspace}/{ext_repo.bitbucket_repo}"

            if ext_repo.github_repo:
                # Repository is being migrated (either here or elsewhere)
                gh_owner = ext_repo.github_owner or self.environment.config.github.owner
                repo_lookup[key] = {
                    'github_repo': f"{gh_owner}/{ext_repo.github_repo}",
                    'github_owner': gh_owner,
                    'github_repo_name': ext_repo.github_repo,
                    'type': 'external'
                }
                self.logger.debug(
                    "Added external repo to lookup: {0} -> {1}".format(
                        key, repo_lookup[key]['github_repo']
                    )
                )
            else:
                # Repository is not being migrated
                repo_lookup[key] = {
                    'github_repo': None,
                    'type': 'not_migrating'
                }
                self.logger.debug(
                    "Added non-migrating repo to lookup: {0} (will preserve Bitbucket links)".format(key)
                )

        return repo_lookup

    def _extract_code_blocks(self, text: str) -> List[Tuple[str, str]]:
        """
        Extract code blocks and text segments from the text.
        
        Args:
            text: The text to process
            
        Returns:
            List of tuples (content_type, content) where content_type is 'text' or 'code'
        """
        if not text:
            return [('text', '')]
        
        blocks = []
        last_end = 0
        
        for match in self.CODE_BLOCK_PATTERN.finditer(text):
            if match.start() > last_end:
                # Add the text before this code block
                blocks.append(('text', text[last_end:match.start()]))
            
            # Add the code block
            blocks.append(('code', match.group(0)))
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(text):
            blocks.append(('text', text[last_end:]))
        
        return blocks

    def validate_github_url(self, url: str, expected_type: Optional[str] = None) -> bool:
        """
        Validate that a GitHub URL is well-formed.

        Args:
            url: The GitHub URL to validate
            expected_type: Expected type (issue, pr, commit, etc.) or None for any

        Returns:
            True if valid, False otherwise
        """
        parsed = urlparse(url)

        # Must be GitHub
        if parsed.netloc != 'github.com':
            return False

        # Check against patterns
        if expected_type:
            pattern = self.GITHUB_URL_PATTERNS.get(expected_type)
            if not pattern:
                self.logger.warning(f"Unknown GitHub URL type: {expected_type}")
                return True  # Don't block unknown types
            return bool(pattern.match(url))
        else:
            # Match any valid GitHub pattern
            return any(pattern.match(url) for pattern in self.GITHUB_URL_PATTERNS.values())

    def rewrite_links(self, text: str, item_type: str = 'issue',
                          item_number: Optional[int] = None,
                          comment_seq: Optional[int] = None, comment_id: Optional[int] = None) -> Tuple[str, int, List[Dict], int, int, List[str], List[Dict]]:
        """
        Rewrite Bitbucket links in text to GitHub equivalents.

        Uses a handler-based system to process URLs sequentially, avoiding partial matches.
        Processes shorthand references separately.

        Args:
            text: The text containing Bitbucket links
            item_type: Type of item ('issue' or 'pr')
            item_number: The issue/PR number
            comment_id: Optional comment sequence number

        Returns:
            Tuple of (rewritten_text, links_found, unhandled_links, mentions_replaced, mentions_unmapped, unmapped_list, validation_failures)
        """
        if not text:
            self.logger.debug("Empty text provided to rewrite_links, returning early with empty results")
            return text, 0, [], 0, 0, [], []

        # PHASE 0: Extract and preserve code blocks
        blocks = self._extract_code_blocks(text)
        
        # Set current context
        self.current_item_type = item_type
        self.current_item_number = item_number
        self.current_comment_seq = comment_seq
        self.current_comment_id = comment_id

        links_found = 0
        total_mentions_replaced = 0
        total_mentions_unmapped = 0
        total_unmapped_list = []

        self.processed_urls = set()
        # Clear validation failures for this processing session
        self.validation_failures = []
        self.validation_errors = 0

        # Process each text block separately for deterministic behavior
        processed_blocks = []
        for block_type, content in blocks:
            if block_type == 'code':
                # Preserve code blocks as-is
                processed_blocks.append(('code', content))
            else:
                # Process text blocks independently
                processed_content = content

                # PHASE 1: Process markdown links FIRST to prevent nesting
                processed_content, md_links = self._rewrite_markdown_links(processed_content)
                links_found += md_links

                # PHASE 1b: Process image links
                processed_content, img_links = self._rewrite_image_links(processed_content)
                links_found += img_links

                # PHASE 2: Process remaining plain URLs
                processed_content, url_links = self._rewrite_urls_with_handlers(processed_content)
                links_found += url_links

                # Skip cosmetic phases during cross-link operations (already done during migration)
                if not hasattr(self.environment, 'mode') or self.environment.mode != "cross-link":
                    # PHASE 2.5: Escape non-URL angle brackets to prevent GitHub markdown misinterpretation
                    processed_content = self._escape_non_url_angle_brackets(processed_content)

                    # PHASE 3: Rewrite mentions
                    processed_content, mention_replaced, mention_unmapped, unmapped_list = self._rewrite_mentions(processed_content)
                    total_mentions_replaced += mention_replaced
                    total_mentions_unmapped += mention_unmapped
                    total_unmapped_list.extend(unmapped_list)

                    # PHASE 4: Rewrite short issue references
                    processed_content, short_issue_links = self._rewrite_short_issue_refs(processed_content)
                    links_found += short_issue_links

                    # PHASE 5: Rewrite PR references
                    processed_content, pr_ref_links = self._rewrite_pr_refs(processed_content)
                    links_found += pr_ref_links

                processed_blocks.append(('text', processed_content))
        
        # Reassemble all processed blocks
        final_text = ''.join(content for block_type, content in processed_blocks)
        mention_replaced = total_mentions_replaced
        mention_unmapped = total_mentions_unmapped
        unmapped_list = total_unmapped_list

        # Deduplicate link details
        self._deduplicate_link_details()

        # Clear context
        self.current_item_type = None
        self.current_item_number = None
        self.current_comment_seq = None
        self.current_comment_id = None

        self.logger.info(f"Total links rewritten: {links_found}")
        self.logger.info(f"Validation errors: {self.validation_errors}")
        return final_text, links_found, self.unhandled_bb_links, mention_replaced, mention_unmapped, unmapped_list, self.validation_failures

    def _rewrite_markdown_links(self, text: str) -> Tuple[str, int]:
        """
        Rewrite markdown-formatted links [text](url).

        This must be called BEFORE _rewrite_urls_with_handlers to prevent
        nesting issues where the URL gets replaced within the markdown structure.

        Returns:
            Tuple of (rewritten_text, links_found)
        """
        links_found = 0

        def replace_markdown_link(match: re.Match) -> str:
            nonlocal links_found

            text_part = match.group('text')
            url = match.group('url')
            original_match = match.group(0)

            # Skip if already processed
            if original_match in self.processed_urls:
                return original_match

            self.logger.debug(f"Processing markdown link: text='{text_part}', url='{url}'")

            # Rewrite URLs in text portion if present
            new_text_part = text_part
            text_urls_found = 0

            # Find and rewrite URLs in the text part
            text_urls = LinkDetector.extract_urls(text_part)
            for text_url in text_urls:
                for handler in self.handlers:
                    if handler.can_handle(text_url):
                        context = {
                            'details': self.data.details,
                            'item_type': self.current_item_type,
                            'item_number': self.current_item_number,
                            'comment_seq': self.current_comment_seq,
                            'comment_id': self.current_comment_id,
                            'markdown_context': 'text'  # URL in link text
                        }
                        rewritten = handler.handle(text_url, context)

                        if rewritten and rewritten != text_url:
                            # Extract just URL from handler output
                            if rewritten.startswith('[') and '](' in rewritten:
                                url_match = re.search(r'\(([^)]+)\)', rewritten)
                                if url_match:
                                    new_text_url = url_match.group(1)
                                else:
                                    new_text_url = rewritten
                            else:
                                new_text_url = rewritten

                            new_text_part = new_text_part.replace(text_url, new_text_url)
                            text_urls_found += 1
                            links_found += 1
                            self.logger.debug(f"URL in markdown text rewritten: {text_url} -> {new_text_url}")
                            
                            # Mark the rewritten URL as processed to prevent double processing in Phase 2
                            self.processed_urls.add(new_text_url)

                            # Validate the rewritten GitHub URL in text
                            if new_text_url.startswith('https://github.com'):
                                if not self.validate_github_url(new_text_url):
                                    self.logger.error(f"Invalid GitHub URL generated in markdown text: {new_text_url}")
                                    self.validation_failures.append({
                                        'original_url': text_url,
                                        'invalid_url': new_text_url,
                                        'item_type': self.current_item_type,
                                        'item_number': self.current_item_number,
                                        'comment_seq': self.current_comment_seq,
                                        'comment_id': self.current_comment_id,
                                        'context': 'markdown_text'
                                    })
                                    self.validation_errors += 1
                        break

            # Rewrite the URL portion
            new_url = url
            url_changed = False

            for handler in self.handlers:
                if handler.can_handle(url):
                    context = {
                        'details': self.data.details,
                        'item_type': self.current_item_type,
                        'item_number': self.current_item_number,
                        'comment_seq': self.current_comment_seq,
                        'comment_id': self.current_comment_id,
                        'markdown_context': 'target'  # Track context
                    }
                    rewritten = handler.handle(url, context)

                    if rewritten and rewritten != url:
                        # Handle different return formats from handlers
                        # In markdown context, handlers return just the URL
                        # In other contexts, handlers return formatted markdown links
                        if rewritten.startswith('[') and '](' in rewritten:
                            # Handler returned formatted markdown link, extract URL
                            url_match = re.search(r'\(([^)]+)\)', rewritten)
                            if url_match:
                                new_url = url_match.group(1)
                            else:
                                new_url = rewritten  # fallback
                        else:
                            # Handler returned just the URL (markdown context)
                            new_url = rewritten

                        url_changed = True
                        links_found += 1
                        self.logger.debug(f"Markdown URL rewritten: {url} -> {new_url}")

                        # Validate the rewritten GitHub URL
                        if new_url.startswith('https://github.com'):
                            if not self.validate_github_url(new_url):
                                self.logger.error(f"Invalid GitHub URL generated: {new_url}")
                                self.validation_failures.append({
                                    'original_url': url,
                                    'invalid_url': new_url,
                                    'item_type': self.current_item_type,
                                    'item_number': self.current_item_number,
                                    'comment_seq': self.current_comment_seq,
                                    'comment_id': self.current_comment_id,
                                    'context': 'markdown_target'
                                })
                                self.validation_errors += 1
                    break

            # Mark as processed
            self.processed_urls.add(original_match)
            self.processed_urls.add(url)

            # Return markdown link with potentially updated URL and text
            if url_changed or text_urls_found > 0:
                # Also mark the new URL as processed to prevent double processing
                self.processed_urls.add(new_url)
                # Mark the entire rewritten markdown link as processed to prevent LinkDetector from extracting parts of it
                rewritten_markdown = f"[{new_text_part}]({new_url})"
                self.processed_urls.add(rewritten_markdown)
                return rewritten_markdown
            else:
                return original_match

        rewritten_text = self.MARKDOWN_LINK_PATTERN.sub(replace_markdown_link, text)
        return rewritten_text, links_found

    def _rewrite_image_links(self, text: str) -> Tuple[str, int]:
        """
        Rewrite markdown-formatted image links ![alt](url).

        Similar to _rewrite_markdown_links but for image links.

        Returns:
            Tuple of (rewritten_text, links_found)
        """
        links_found = 0

        def replace_image_link(match: re.Match) -> str:
            nonlocal links_found

            alt_text = match.group('alt')
            url = match.group('url')
            original_match = match.group(0)

            # Skip if already processed
            if original_match in self.processed_urls:
                return original_match

            self.logger.debug(f"Processing image link: alt='{alt_text}', url='{url}'")

            # Rewrite the URL portion
            new_url = url
            url_changed = False

            for handler in self.handlers:
                if handler.can_handle(url):
                    context = {
                        'details': self.data.details,
                        'item_type': self.current_item_type,
                        'item_number': self.current_item_number,
                        'comment_seq': self.current_comment_seq,
                        'comment_id': self.current_comment_id,
                        'markdown_context': 'target'  # Track context
                    }
                    rewritten = handler.handle(url, context)

                    if rewritten and rewritten != url:
                        # Handle different return formats from handlers
                        # In markdown context, handlers return just the URL
                        # In other contexts, handlers return formatted markdown links
                        if rewritten.startswith('[') and '](' in rewritten:
                            # Handler returned formatted markdown link, extract URL
                            url_match = re.search(r'\(([^)]+)\)', rewritten)
                            if url_match:
                                new_url = url_match.group(1)
                            else:
                                new_url = rewritten  # fallback
                        else:
                            # Handler returned just the URL (markdown context)
                            new_url = rewritten

                        url_changed = True
                        links_found += 1
                        self.logger.debug(f"Image URL rewritten: {url} -> {new_url}")

                        # Validate the rewritten GitHub URL
                        if new_url.startswith('https://github.com'):
                            if not self.validate_github_url(new_url):
                                self.logger.error(f"Invalid GitHub URL generated in image: {new_url}")
                                self.validation_failures.append({
                                    'original_url': url,
                                    'invalid_url': new_url,
                                    'item_type': self.current_item_type,
                                    'item_number': self.current_item_number,
                                    'comment_seq': self.current_comment_seq,
                                    'comment_id': self.current_comment_id,
                                    'context': 'image_target'
                                })
                                self.validation_errors += 1
                    break

            # Mark as processed
            self.processed_urls.add(original_match)
            self.processed_urls.add(url)

            # Return image link with potentially updated URL
            if url_changed:
                # Also mark the new URL as processed to prevent double processing
                self.processed_urls.add(new_url)
                return f"![{alt_text}]({new_url})"
            else:
                return original_match

        rewritten_text = self.IMAGE_LINK_PATTERN.sub(replace_image_link, text)
        return rewritten_text, links_found

    def _rewrite_urls_with_handlers(self, text: str) -> Tuple[str, int]:
        """
        Rewrite URLs using the handler system.
        """
        urls = LinkDetector.extract_urls(text)
        links_found = 0

        for url in urls:
            if url in self.processed_urls:
                continue
            
            # Skip malformed URLs that contain markdown syntax (indicates LinkDetector extracted across markdown boundaries)
            if '](' in url or '[' in url or '(' in url and url.count('(') > 1:
                self.logger.debug(f"Skipping malformed URL containing markdown syntax: {url}")
                self.processed_urls.add(url)
                continue
            
            # Skip URLs that are inside markdown link structures [text](url)
            # This prevents processing URLs that are already part of markdown links
            url_pos = text.find(url)
            if url_pos > 0:
                # Check if this URL is part of a markdown link structure
                before = text[max(0, url_pos-2):url_pos]
                after = text[url_pos+len(url):min(len(text), url_pos+len(url)+1)]
                
                # Pattern: ](url) - URL is in markdown target position
                if before == '](' and after == ')':
                    self.logger.debug(f"Skipping URL inside markdown target: {url}")
                    self.processed_urls.add(url)
                    continue
            
            self.processed_urls.add(url)

            self.logger.debug(f"Processing URL: {url}")
            handled = False
            # No need to sort - handlers already sorted by priority in __init__
            for handler in self.handlers:
                if handler.can_handle(url):
                    self.logger.debug(f"Handler {handler.__class__.__name__} can handle URL: {url}")
                    context = {
                        'details': self.data.details,
                        'item_type': self.current_item_type,
                        'item_number': self.current_item_number,
                        'comment_seq': self.current_comment_seq,
                        'comment_id': self.current_comment_id,
                        # No markdown_context for plain URLs - they should return formatted markdown
                    }
                    rewritten = handler.handle(url, context)
                    if rewritten and rewritten != url:
                        # Extract GitHub URL from rewritten text
                        gh_url_match = re.search(r'https://github\.com/[^\s)]+', rewritten)
                        if gh_url_match:
                            gh_url = gh_url_match.group(0)
                            
                            # Validate GitHub URL
                            if not self.validate_github_url(gh_url):
                                self.logger.error(
                                    f"Invalid GitHub URL generated: {gh_url} from {url}"
                                )
                                # Add to failed links for reporting
                                self.data.details.append({
                                    'original': url,
                                    'rewritten': gh_url,
                                    'type': 'invalid_github_url',
                                    'reason': 'validation_failed',
                                    'item_type': self.current_item_type,
                                    'item_number': self.current_item_number,
                                    'comment_seq': self.current_comment_seq,
                                    'comment_id': self.current_comment_id,
                                })
                                self.validation_failures.append({
                                    'original_url': url,
                                    'invalid_url': gh_url,
                                    'item_type': self.current_item_type,
                                    'item_number': self.current_item_number,
                                    'comment_seq': self.current_comment_seq,
                                    'comment_id': self.current_comment_id,
                                    'context': 'plain_url'
                                })
                                self.validation_errors += 1
                                self.data.failed += 1
                                self.data.total_processed += 1
                                handled = True
                                # Don't replace - keep original
                                break
                        
                        text = text.replace(url, rewritten)
                        links_found += 1
                        self.data.successful += 1
                        self.logger.debug(f"URL rewritten: {url} -> {rewritten}")
                    else:
                        self.data.failed += 1
                        self.logger.debug(f"URL not rewritten: {url}")
                    self.data.total_processed += 1
                    handled = True
                    break
                else:
                    self.logger.debug(f"Handler {handler.__class__.__name__} cannot handle URL: {url}")

            if not handled:
                self.logger.warning(f"URL not handled by any handler: {url}")
                # Add as unhandled
                self.unhandled_bb_links.append({
                    'url': url,
                    'item_type': self.current_item_type,
                    'item_number': self.current_item_number,
                    'context': text[max(0, text.find(url)-50):min(len(text), text.find(url)+len(url)+50)]
                })
                self.data.details.append({
                    'original': url,
                    'rewritten': url,
                    'type': 'unhandled',
                    'reason': 'unhandled',
                    'item_type': self.current_item_type,
                    'item_number': self.current_item_number,
                    'comment_seq': self.current_comment_seq,
                    'comment_id': self.current_comment_id,
                })
                self.data.failed += 1
                self.data.total_processed += 1

        return text, links_found
    
    def _escape_non_url_angle_brackets(self, text: str) -> str:
        """
        Escape angle-bracketed expressions that are NOT valid autolinks.
        
        This prevents GitHub from misinterpreting expressions like <std::uint16_t>
        as autolinks or HTML, which causes underscore escaping issues.
        
        Valid autolinks in markdown/GitHub:
        - <https://example.com>
        - <http://example.com>
        - <mailto:user@example.com>
        - <ftp://example.com>
        - <user@example.com>
        
        Everything else gets wrapped in backticks to preserve display.
        
        Returns:
            Text with non-URL angle brackets escaped
        """
        # Match the outermost angle bracket pair, including nested brackets
        # Pattern: <(content that may include nested <>)>
        pattern = re.compile(r'<((?:[^<>]|<[^>]*>)*?)>')
        
        def maybe_escape(match):
            content = match.group(1)
            full_match = match.group(0)
            
            # Check if it's a valid autolink
            # GitHub autolinks must start with: http://, https://, mailto:, or ftp://
            # Also handle email addresses directly: user@example.com
            is_http_url = re.match(r'^https?://', content)
            is_ftp_url = re.match(r'^ftp://', content)
            is_mailto = re.match(r'^mailto:', content)
            is_email = re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', content)
            
            if is_http_url or is_ftp_url or is_mailto or is_email:
                return full_match  # Keep autolinks as-is
            
            # Not a URL/email, escape it
            return f'`{full_match}`'
        
        return pattern.sub(maybe_escape, text)
    
    def _rewrite_mentions(self, text: str) -> Tuple[str, int, int, List[str]]:
        """Rewrite @mentions"""
        pattern = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_][a-zA-Z0-9_-]*)'
        mentions_replaced = 0
        mentions_unmapped = 0
        unmapped_list = []
        
        def replace_mention(match):
            nonlocal mentions_replaced, mentions_unmapped, unmapped_list
            original_mention = match.group(0)
            if original_mention in self.processed_urls:
                return original_mention  # Skip if already processed
            self.processed_urls.add(original_mention)
            
            bb_mention = match.group(1)
            
            if bb_mention.startswith('{') and bb_mention.endswith('}'):
                bb_username = bb_mention[1:-1]
                bb_username_normalized = bb_username.replace(' ', '-')
            else:
                bb_username = bb_mention
                bb_username_normalized = bb_username
            
            self.logger.info("call map_mention")
            gh_username = self.environment.services.get('user_mapper').map_mention(bb_username)
            self.logger.info("gh_username obtained")

            if gh_username:
                mentions_replaced += 1
                rewritten = f"@{gh_username}"
                self.data.details.append({
                      'original': original_mention,
                      'rewritten': rewritten,
                      'type': 'mention',
                      'reason': 'mapped',
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'comment_seq': self.current_comment_seq,
                      'comment_id': self.current_comment_id,
                      'markdown_context': 'target'
                  })
                self.data.successful += 1
            else:
                is_account_id = ':' in bb_username or (len(bb_username) == 24 and all(c in '0123456789abcdef' for c in bb_username.lower()))
                
                if is_account_id:
                    self.logger.info("before account_id_to_display_name")

                    display_name = self.state.services['UserMapper'].account_id_to_display_name.get(bb_username)
                    self.logger.info("after account_id_to_display_name")
                    if display_name:
                        mentions_unmapped += 1
                        unmapped_list.append(bb_username)
                        rewritten = f"**{display_name}** *(Bitbucket user, no GitHub account)*"
                    else:
                        mentions_unmapped += 1
                        unmapped_list.append(bb_username)
                        rewritten = f"@{bb_username_normalized} *(Bitbucket user, needs GitHub mapping)*"
                else:
                    mentions_unmapped += 1
                    unmapped_list.append(bb_username)
                    rewritten = f"@{bb_username_normalized} *(Bitbucket user, needs GitHub mapping)*"
                
                self.data.details.append({
                      'original': original_mention,
                      'rewritten': rewritten,
                      'type': 'mention',
                      'reason': 'unmapped',
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'comment_seq': self.current_comment_seq,
                      'comment_id': self.current_comment_id,
                      'markdown_context': 'target'
                  })
                self.data.failed += 1
            self.data.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_mention, text), mentions_replaced, mentions_unmapped, unmapped_list
    
    def _rewrite_short_issue_refs(self, text: str) -> Tuple[str, int]:
        """Rewrite short issue references like #123"""
        pattern = r'(?<!\bPR\s)(?<!\bpull request\s)(?<!\[)(?<!BB )#(\d+)(?!\])'
        links_found = 0

        def replace_short_issue(match):
            nonlocal links_found
            original_ref = match.group(0)
            if original_ref in self.processed_urls:
                return original_ref  # Skip if already processed
            self.processed_urls.add(original_ref)
            
            bb_num = int(match.group(1))
            gh_num = self.state.mappings.issues.get(bb_num)
            if gh_num and bb_num != gh_num:
                links_found += 1
                gh_url = f"https://github.com/{self.environment.config.github.owner}/{self.environment.config.github.repo}/issues/{gh_num}"

                # Validate the generated GitHub URL
                if not self.validate_github_url(gh_url, 'issue'):
                    self.logger.error(f"Invalid GitHub issue URL generated: {gh_url}")
                    self.validation_failures.append({
                        'original_url': original_ref,
                        'invalid_url': gh_url,
                        'item_type': self.current_item_type,
                        'item_number': self.current_item_number,
                        'comment_seq': self.current_comment_seq,
                        'comment_id': self.current_comment_id,
                        'context': 'short_issue_ref'
                    })
                    self.validation_errors += 1

                note = self.environment.config.link_rewriting_config.get_template('short_issue_ref').format(
                    bb_num=bb_num, gh_num=gh_num, bb_url="", gh_url=gh_url
                ) if self.environment.config.link_rewriting_config else f" *(was BB `#{bb_num}`)*"
                rewritten = f"[#{gh_num}]({gh_url}){note}"
                self.data.details.append({
                      'original': original_ref,
                      'rewritten': rewritten,
                      'type': 'short_issue_ref',
                      'reason': 'mapped',
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'comment_seq': self.current_comment_seq,
                      'comment_id': self.current_comment_id,
                      'markdown_context': 'target'
                  })
                self.data.successful += 1
            elif gh_num and bb_num == gh_num:
                links_found += 1
                rewritten = f"#{gh_num}"
                self.data.details.append({
                      'original': original_ref,
                      'rewritten': rewritten,
                      'type': 'short_issue_ref',
                      'reason': 'mapped',
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'comment_seq': self.current_comment_seq,
                      'comment_id': self.current_comment_id,
                      'markdown_context': 'target'
                  })
                self.data.successful += 1
            else:
                rewritten = original_ref
                self.data.details.append({
                      'original': original_ref,
                      'rewritten': rewritten,
                      'type': 'short_issue_ref',
                      'reason': 'unmapped',
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'comment_seq': self.current_comment_seq,
                      'comment_id': self.current_comment_id,
                      'markdown_context': 'target'
                  })
                self.data.failed += 1
            self.data.total_processed += 1
            return rewritten

        return re.sub(pattern, replace_short_issue, text, flags=re.IGNORECASE), links_found
    
    def _rewrite_pr_refs(self, text: str) -> Tuple[str, int]:
        """Rewrite PR references like PR #45"""
        pattern = r'(?<!\[)(?:PR|pull request)\s*#(\d+)(?!\])'
        links_found = 0
        
        def replace_pr_ref(match):
            nonlocal links_found
            original_ref = match.group(0)
            if original_ref in self.processed_urls:
                return original_ref  # Skip if already processed
            self.processed_urls.add(original_ref)
            
            bb_num = int(match.group(1))
            gh_num = self.state.mappings.prs.get(bb_num)
            
            if gh_num:
                links_found += 1
                gh_url = f"https://github.com/{self.environment.config.github.owner}/{self.environment.config.github.repo}/issues/{gh_num}"

                # Validate the generated GitHub URL
                if not self.validate_github_url(gh_url, 'issue'):
                    self.logger.error(f"Invalid GitHub PR URL generated: {gh_url}")
                    self.validation_failures.append({
                        'original_url': original_ref,
                        'invalid_url': gh_url,
                        'item_type': self.current_item_type,
                        'item_number': self.current_item_number,
                        'comment_seq': self.current_comment_seq,
                        'comment_id': self.current_comment_id,
                        'context': 'pr_ref'
                    })
                    self.validation_errors += 1

                note = self.environment.config.link_rewriting_config.get_template('pr_ref').format(
                    bb_num=bb_num, gh_num=gh_num, bb_url="", gh_url=gh_url
                ) if self.environment.config.link_rewriting_config else f" *(was BB PR `#{bb_num}`)*"
                rewritten = f"[#{gh_num}]({gh_url}){note}"
                self.data.details.append({
                      'original': original_ref,
                      'rewritten': rewritten,
                      'type': 'pr_ref',
                      'reason': 'mapped',
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'comment_seq': self.current_comment_seq,
                      'comment_id': self.current_comment_id,
                      'markdown_context': 'target'
                  })
                self.data.successful += 1
            else:
                rewritten = original_ref
                self.data.details.append({
                      'original': original_ref,
                      'rewritten': rewritten,
                      'type': 'pr_ref',
                      'reason': 'unmapped',
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'comment_seq': self.current_comment_seq,
                      'comment_id': self.current_comment_id,
                      'markdown_context': 'target'
                  })
                self.data.failed += 1
            self.data.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_pr_ref, text, flags=re.IGNORECASE), links_found
    
    def _detect_unhandled_links(self, text: str):
        """Detect unhandled Bitbucket links"""
        remaining_bb_pattern = r'https?://(?:www\.)?bitbucket\.org/[^\s\)"\'>]+'
        remaining_matches = re.findall(remaining_bb_pattern, text)
        for unhandled_url in remaining_matches:
            if unhandled_url in self.processed_urls:
                continue  # Skip if already processed
            if '*(was' not in text[max(0, text.find(unhandled_url)-50):text.find(unhandled_url)+len(unhandled_url)+50]:
                self.unhandled_bb_links.append({
                      'url': unhandled_url,
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'context': text[max(0, text.find(unhandled_url)-50):min(len(text), text.find(unhandled_url)+len(unhandled_url)+50)]
                  })
                self.data.details.append({
                      'original': unhandled_url,
                      'rewritten': unhandled_url,
                      'type': 'unhandled',
                      'reason': 'unhandled',
                      'item_type': self.current_item_type,
                      'item_number': self.current_item_number,
                      'comment_seq': self.current_comment_seq,
                      'comment_id': self.current_comment_id,
                  })
                self.data.failed += 1
                self.data.total_processed += 1
    
    def _deduplicate_link_details(self):
        """
        Deduplicate link_details based on original URL and context.

        This prevents multiple entries in the report for the same link, which can occur
        when overlapping regex patterns match the same URL.
        """
        seen = set()
        unique_details = []
        for detail in self.data.details:
            key = (detail['original'], detail['item_type'], detail['item_number'], detail['comment_seq'])
            if key not in seen:
                seen.add(key)
                unique_details.append(detail)
        self.data.details = unique_details