from typing import Dict, Any, Optional
from .content_formatter import ContentFormatter, IssueContentFormatter, PullRequestContentFormatter, CommentContentFormatter
from ..services.user_mapper import UserMapper
from ..services.link_rewriter import LinkRewriter
from ..services.attachment_handler import AttachmentHandler

from ..core.migration_context import MigrationEnvironment, MigrationState

class FormatterFactory:
    """
    Factory for creating content formatters.

    This factory creates the appropriate formatter based on the content type
    and provides a centralized way to manage formatter creation.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the factory with required services.

        Args:
            environment: Migration environment containing services
            state: Migration state (unused but kept for compatibility)
        """

        self.user_mapper = environment.services.get('user_mapper')
        self.link_rewriter = environment.services.get('link_rewriter')
        self.attachment_handler = environment.services.get('attachment_handler')

    def get_issue_formatter(self) -> IssueContentFormatter:
        """
        Get formatter for issues.

        Returns:
            IssueContentFormatter instance
        """
        return IssueContentFormatter(self.user_mapper, self.link_rewriter, self.attachment_handler)

    def get_pull_request_formatter(self) -> PullRequestContentFormatter:
        """
        Get formatter for pull requests.

        Returns:
            PullRequestContentFormatter instance
        """
        return PullRequestContentFormatter(self.user_mapper, self.link_rewriter, self.attachment_handler)

    def get_comment_formatter(self) -> CommentContentFormatter:
        """
        Get formatter for comments.

        Returns:
            CommentContentFormatter instance
        """
        return CommentContentFormatter(self.user_mapper, self.link_rewriter, self.attachment_handler)

    def get_formatter(self, content_type: str) -> ContentFormatter:
        """
        Get formatter based on content type.

        Args:
            content_type: Type of content ('issue', 'pr', 'comment')

        Returns:
            Appropriate ContentFormatter instance

        Raises:
            ValueError: If content_type is not supported
        """
        if content_type == 'issue':
            return self.get_issue_formatter()
        elif content_type == 'pr':
            return self.get_pull_request_formatter()
        elif content_type == 'comment':
            return self.get_comment_formatter()
        else:
            raise ValueError(f"Unsupported content type: {content_type}")