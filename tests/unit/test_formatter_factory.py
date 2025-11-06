"""
Tests for FormatterFactory.

Tests the factory pattern for creating formatters:
- Issue formatter creation
- PR formatter creation
- Comment formatter creation
- Formatter reuse and dependency injection
"""

import pytest
from unittest.mock import MagicMock, patch

from bitbucket_migration.formatters.formatter_factory import FormatterFactory
from bitbucket_migration.formatters.content_formatter import (
    IssueContentFormatter,
    PullRequestContentFormatter,
    CommentContentFormatter
)


class TestFormatterFactory:
    """Test FormatterFactory functionality."""

    def test_init(self, mock_environment, mock_state):
        """Test FormatterFactory initialization."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        # Factory gets services from environment, not storing environment itself
        assert hasattr(factory, 'user_mapper')
        assert hasattr(factory, 'link_rewriter')
        assert hasattr(factory, 'attachment_handler')

    def test_get_issue_formatter(self, mock_environment, mock_state):
        """Test creating issue formatter."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        formatter = factory.get_issue_formatter()
        
        assert isinstance(formatter, IssueContentFormatter)
        assert formatter.user_mapper is not None
        assert formatter.link_rewriter is not None
        assert formatter.attachment_handler is not None

    def test_get_pull_request_formatter(self, mock_environment, mock_state):
        """Test creating PR formatter."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        formatter = factory.get_pull_request_formatter()
        
        assert isinstance(formatter, PullRequestContentFormatter)
        assert formatter.user_mapper is not None
        assert formatter.link_rewriter is not None
        assert formatter.attachment_handler is not None

    def test_get_comment_formatter(self, mock_environment, mock_state):
        """Test creating comment formatter."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        formatter = factory.get_comment_formatter()
        
        assert isinstance(formatter, CommentContentFormatter)
        assert formatter.user_mapper is not None
        assert formatter.link_rewriter is not None
        assert formatter.attachment_handler is not None

    def test_formatter_instances_not_reused(self, mock_environment, mock_state):
        """Test that formatter instances are created fresh each time."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        # Get formatters multiple times
        issue_formatter1 = factory.get_issue_formatter()
        issue_formatter2 = factory.get_issue_formatter()
        
        pr_formatter1 = factory.get_pull_request_formatter()
        pr_formatter2 = factory.get_pull_request_formatter()
        
        comment_formatter1 = factory.get_comment_formatter()
        comment_formatter2 = factory.get_comment_formatter()
        
        # Issue formatters should be different instances (not cached)
        assert issue_formatter1 is not issue_formatter2
        
        # PR formatters should be different instances
        assert pr_formatter1 is not pr_formatter2
        
        # Comment formatters should be different instances
        assert comment_formatter1 is not comment_formatter2
        
        # Different types should be different instances
        assert issue_formatter1 is not pr_formatter1
        assert issue_formatter1 is not comment_formatter1
        assert pr_formatter1 is not comment_formatter1

    def test_formatters_have_required_dependencies(self, mock_environment, mock_state):
        """Test that all formatters have required dependencies."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        # Test issue formatter
        issue_formatter = factory.get_issue_formatter()
        assert hasattr(issue_formatter, 'user_mapper')
        assert hasattr(issue_formatter, 'link_rewriter')
        assert hasattr(issue_formatter, 'attachment_handler')
        assert issue_formatter.user_mapper is not None
        assert issue_formatter.link_rewriter is not None
        assert issue_formatter.attachment_handler is not None
        
        # Test PR formatter
        pr_formatter = factory.get_pull_request_formatter()
        assert hasattr(pr_formatter, 'user_mapper')
        assert hasattr(pr_formatter, 'link_rewriter')
        assert hasattr(pr_formatter, 'attachment_handler')
        assert pr_formatter.user_mapper is not None
        assert pr_formatter.link_rewriter is not None
        assert pr_formatter.attachment_handler is not None
        
        # Test comment formatter
        comment_formatter = factory.get_comment_formatter()
        assert hasattr(comment_formatter, 'user_mapper')
        assert hasattr(comment_formatter, 'link_rewriter')
        assert hasattr(comment_formatter, 'attachment_handler')
        assert comment_formatter.user_mapper is not None
        assert comment_formatter.link_rewriter is not None
        assert comment_formatter.attachment_handler is not None

    def test_formatter_dependencies_are_mock_objects(self, mock_environment, mock_state):
        """Test that formatters receive mock dependencies."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        issue_formatter = factory.get_issue_formatter()
        
        # Dependencies should be MagicMock objects from conftest
        assert isinstance(issue_formatter.user_mapper, MagicMock)
        assert isinstance(issue_formatter.link_rewriter, MagicMock)
        assert isinstance(issue_formatter.attachment_handler, MagicMock)

    def test_all_formatters_use_same_dependencies(self, mock_environment, mock_state):
        """Test that all formatters use the same dependency instances."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        issue_formatter = factory.get_issue_formatter()
        pr_formatter = factory.get_pull_request_formatter()
        comment_formatter = factory.get_comment_formatter()
        
        # All formatters should share the same user_mapper
        assert issue_formatter.user_mapper is pr_formatter.user_mapper
        assert issue_formatter.user_mapper is comment_formatter.user_mapper
        
        # All formatters should share the same link_rewriter
        assert issue_formatter.link_rewriter is pr_formatter.link_rewriter
        assert issue_formatter.link_rewriter is comment_formatter.link_rewriter
        
        # All formatters should share the same attachment_handler
        assert issue_formatter.attachment_handler is pr_formatter.attachment_handler
        assert issue_formatter.attachment_handler is comment_formatter.attachment_handler

    @patch('bitbucket_migration.formatters.formatter_factory.IssueContentFormatter')
    @patch('bitbucket_migration.formatters.formatter_factory.PullRequestContentFormatter')
    @patch('bitbucket_migration.formatters.formatter_factory.CommentContentFormatter')
    def test_formatter_creation_with_patches(self, mock_comment_class, mock_pr_class,
                                            mock_issue_class, mock_environment, mock_state):
        """Test formatter creation using mocked classes."""
        # Setup mock instances
        mock_issue_instance = MagicMock()
        mock_pr_instance = MagicMock()
        mock_comment_instance = MagicMock()
        
        mock_issue_class.return_value = mock_issue_instance
        mock_pr_class.return_value = mock_pr_instance
        mock_comment_class.return_value = mock_comment_instance
        
        factory = FormatterFactory(mock_environment, mock_state)
        
        # Get formatters
        issue_formatter = factory.get_issue_formatter()
        pr_formatter = factory.get_pull_request_formatter()
        comment_formatter = factory.get_comment_formatter()
        
        # Verify class instantiation with correct arguments
        mock_issue_class.assert_called_once()
        mock_pr_class.assert_called_once()
        mock_comment_class.assert_called_once()
        
        # Verify formatters are the mock instances
        assert issue_formatter is mock_issue_instance
        assert pr_formatter is mock_pr_instance
        assert comment_formatter is mock_comment_instance

    def test_factory_with_different_environment_states(self, mock_state):
        """Test factory behavior with different environment states."""
        # Test with different mock environment
        env1 = MagicMock()
        env1.services = MagicMock()
        env1.services.get = MagicMock(return_value=MagicMock())
        
        factory1 = FormatterFactory(env1, mock_state)
        formatter1 = factory1.get_issue_formatter()
        
        # Test with another environment
        env2 = MagicMock()
        env2.services = MagicMock()
        env2.services.get = MagicMock(return_value=MagicMock())
        
        factory2 = FormatterFactory(env2, mock_state)
        formatter2 = factory2.get_issue_formatter()
        
        # Formatters should be created with their respective dependencies
        # (cannot check environment attribute since formatters don't store it)
        assert formatter1 is not None
        assert formatter2 is not None

    def test_get_all_formatters_at_once(self, mock_environment, mock_state):
        """Test getting all formatters in sequence."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        # Get all formatters
        issue_formatter = factory.get_issue_formatter()
        pr_formatter = factory.get_pull_request_formatter()
        comment_formatter = factory.get_comment_formatter()
        
        # All should be created successfully
        assert issue_formatter is not None
        assert pr_formatter is not None
        assert comment_formatter is not None
        
        # All should be different types
        assert type(issue_formatter).__name__ == 'IssueContentFormatter'
        assert type(pr_formatter).__name__ == 'PullRequestContentFormatter'
        assert type(comment_formatter).__name__ == 'CommentContentFormatter'

    def test_multiple_factory_instances(self, mock_environment, mock_state):
        """Test creating multiple factory instances."""
        factory1 = FormatterFactory(mock_environment, mock_state)
        factory2 = FormatterFactory(mock_environment, mock_state)
        
        # Get formatters from both factories
        formatter1a = factory1.get_issue_formatter()
        formatter2a = factory2.get_issue_formatter()
        
        # Each factory should create its own instances
        assert formatter1a is not formatter2a

    def test_get_formatter_with_content_type(self, mock_environment, mock_state):
        """Test getting formatters by content type."""
        factory = FormatterFactory(mock_environment, mock_state)
        
        # Test getting issue formatter
        issue_formatter = factory.get_formatter('issue')
        assert isinstance(issue_formatter, IssueContentFormatter)
        
        # Test getting PR formatter
        pr_formatter = factory.get_formatter('pr')
        assert isinstance(pr_formatter, PullRequestContentFormatter)
        
        # Test getting comment formatter
        comment_formatter = factory.get_formatter('comment')
        assert isinstance(comment_formatter, CommentContentFormatter)
        
        # Test invalid content type
        with pytest.raises(ValueError, match="Unsupported content type: invalid"):
            factory.get_formatter('invalid')