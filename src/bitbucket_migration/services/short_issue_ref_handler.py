import re
from typing import Optional, Dict, Any
from .base_link_handler import BaseLinkHandler

class ShortIssueRefHandler(BaseLinkHandler):
    """
    Handler for short issue references like #123.
    """

    def __init__(self, issue_mapping: Dict[int, int], gh_owner: str, gh_repo: str, template_config=None):
        super().__init__(priority=20, template_config=template_config)  # Lower priority for shorthand
        self.issue_mapping = issue_mapping
        self.gh_owner = gh_owner
        self.gh_repo = gh_repo

    def can_handle(self, url: str) -> bool:
        # This is for shorthand, not URLs, but we'll handle it separately
        return False  # Not for URLs

    def handle(self, url: str, context: Dict[str, Any]) -> Optional[str]:
        return None