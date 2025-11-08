from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Pattern
import re
import logging
from urllib.parse import quote

from ..core.migration_context import MigrationEnvironment, MigrationState

class BaseLinkHandler(ABC):
    """
    Abstract base class for link handlers in the link rewriting system.

    Each handler is responsible for detecting and processing specific types of links.
    Handlers are invoked in order of priority (lower number = higher priority).
    
    Attributes:
        PATTERN: Optional pre-compiled regex pattern for URL matching.
                 If set, can_handle() will use this instead of dynamic compilation.
    """
    
    PATTERN: Optional[Pattern] = None

    def __init__(self, environment: MigrationEnvironment, state: MigrationState, priority: int = 100):
        """
        Initialize the BaseLinkHandler.

        Args:
            priority: Priority for handler ordering (lower = higher priority)
            template_config: Configuration for link rewriting templates
        """
        
        self.environment = environment
        self.state = state

        self.logger = environment.logger
        
        self.priority = priority
        self.template_config = self.environment.config.link_rewriting_config

    def can_handle(self, url: str) -> bool:
        """
        Check if this handler can process the given URL.
        
        Uses pre-compiled PATTERN attribute if available for better performance.
        Subclasses can override this method for custom matching logic.

        Args:
            url: The URL to check

        Returns:
            True if this handler can process the URL, False otherwise
        """
        if self.PATTERN is None:
            return False
        return bool(self.PATTERN.match(url))

    @abstractmethod
    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Process the URL and return the rewritten version.

        Args:
            url: The original URL
            context: Additional context (e.g., mappings, item_type)

        Returns:
            Rewritten URL if handled, None otherwise
        """
        pass

    def get_priority(self) -> int:
        """
        Get the priority of this handler.

        Returns:
            Priority value (lower = higher priority)
        """
        return self.priority

    def format_note(self, link_type: str, **kwargs) -> str:
        """
        Format note template with provided variables.

        Args:
            link_type: Type of link (issue_link, pr_link, etc.)
            **kwargs: Variables to interpolate (bb_num, bb_url, etc.)

        Returns:
            Formatted note string
        """
        if not self.template_config or not self.template_config.enable_notes:
            return ''

        template = self.template_config.get_template(link_type)

        try:
            return template.format(**kwargs)
        except (KeyError, ValueError) as e:
            self.logger.warning(f"Template formatting error: {e}")
            return self.template_config.get_template('default') if self.template_config else ''

    @staticmethod
    def encode_url_component(component: str, safe: str = '') -> str:
        """
        URL-encode a path component (branch name, filename, etc.).

        Args:
            component: The string to encode
            safe: Characters that should not be encoded (default: none)

        Returns:
            URL-encoded string

        Examples:
            >>> BaseLinkHandler.encode_url_component("feature/my-branch")
            'feature%2Fmy-branch'
            >>> BaseLinkHandler.encode_url_component("path/to/file.py", safe='/')
            'path/to/file.py'
            >>> BaseLinkHandler.encode_url_component("fix#123")
            'fix%23123'
        """
        return quote(component, safe=safe)