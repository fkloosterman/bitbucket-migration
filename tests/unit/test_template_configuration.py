"""
Unit tests for template configuration system.

Tests the LinkRewritingConfig and template functionality used by the link rewriting system.
Covers custom templates, disabling notes, per-type templates, missing variables, and fallback behavior.
"""

from unittest.mock import Mock

import pytest

from bitbucket_migration.config.migration_config import LinkRewritingConfig
from bitbucket_migration.services.link_rewriter import LinkRewriter
from bitbucket_migration.services.user_mapper import UserMapper


class TestLinkRewritingConfig:
    """Test the LinkRewritingConfig class functionality."""

    def test_default_templates(self):
        """Test default templates are properly initialized."""
        config = LinkRewritingConfig()

        expected_templates = {
            'issue_link': ' *(was [BB #{bb_num}]({bb_url}))*',
            'pr_link': ' *(was [BB PR #{bb_num}]({bb_url}))*',
            'commit_link': ' *(was [Bitbucket]({bb_url}))*',
            'branch_link': ' *(was [Bitbucket]({bb_url}))*',
            'compare_link': ' *(was [Bitbucket]({bb_url}))*',
            'repo_home_link': '',
            'cross_repo_link': ' *(was [Bitbucket]({bb_url}))*',
            'short_issue_ref': ' *(was BB `#{bb_num}`)*',
            'pr_ref': ' *(was BB PR `#{bb_num}`)*',
            'mention': '',
            'default': ' *(migrated link)*'
        }

        assert config.note_templates == expected_templates
        assert config.enabled is True
        assert config.enable_notes is True
        assert config.enable_markdown_awareness is True

    def test_custom_config_initialization(self):
        """Test initialization with custom configuration."""
        config_dict = {
            'enabled': False,
            'enable_notes': False,
            'enable_markdown_context_awareness': False,
            'note_templates': {
                'issue_link': ' *(custom issue template #{bb_num})*',
                'default': ' *(custom default)*'
            }
        }

        config = LinkRewritingConfig(config_dict)

        assert config.enabled is False
        assert config.enable_notes is False
        assert config.enable_markdown_awareness is False
        assert config.note_templates['issue_link'] == ' *(custom issue template #{bb_num})*'
        assert config.note_templates['default'] == ' *(custom default)*'

    def test_get_template_existing(self):
        """Test get_template returns correct template for existing type."""
        config = LinkRewritingConfig({
            'note_templates': {
                'issue_link': ' *(custom issue #{bb_num})*',
                'default': ' *(default template)*'
            }
        })

        assert config.get_template('issue_link') == ' *(custom issue #{bb_num})*'
        assert config.get_template('pr_link') == ' *(default template)*'  # Falls back to default

    def test_get_template_fallback_to_default(self):
        """Test get_template falls back to default for unknown types."""
        config = LinkRewritingConfig({
            'note_templates': {
                'default': ' *(fallback template)*'
            }
        })

        assert config.get_template('unknown_type') == ' *(fallback template)*'

    def test_get_template_no_default(self):
        """Test get_template returns empty string when no default exists."""
        config = LinkRewritingConfig({
            'note_templates': {}
        })

        assert config.get_template('unknown_type') == ''


class TestTemplateIntegrationWithLinkHandlers:
    """Test template integration with link handlers."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_environment, mock_state):
        """Set up test fixtures."""
        self.issue_mapping = {123: 456, 789: 101}
        self.pr_mapping = {50: 75}
        self.repo_mapping = {}
        self.bb_workspace = 'test_workspace'
        self.bb_repo = 'test_repo'
        self.gh_owner = 'test_owner'
        self.gh_repo = 'test_repo'
        # Create UserMapper with proper mock environment and state
        self.user_mapper = UserMapper(mock_environment, mock_state)
        yield

    def test_custom_note_templates(self, mock_environment, mock_state):
        """Test custom note templates work with LinkRewriter."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'issue_link': ' *(migrated from BB #{bb_num})*',
                'default': ' *(migrated)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        assert "*(migrated from BB #123)*" in result
        assert "[#456]" in result  # GitHub issue link

    def test_disable_notes(self, mock_environment, mock_state):
        """Test disabling notes entirely."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': False
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        # Should not contain any notes
        assert "was BB" not in result
        assert "*(was" not in result
        assert "migrated" not in result
        # But should still contain the GitHub link
        assert "[#456]" in result

    def test_per_type_templates(self, mock_environment, mock_state):
        """Test per-type templates for different link types."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'issue_link': ' *(Issue migrated from BB #{bb_num})*',
                'pr_link': ' *(PR migrated from BB #{bb_num})*',
                'commit_link': ' *(Commit from Bitbucket)*',
                'branch_link': ' *(Branch from Bitbucket)*',
                'default': ' *(Generic migration note)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        # Test issue link
        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )
        assert "*(Issue migrated from BB #123)*" in result

        # Test PR link
        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/pull-requests/50"
        )
        assert "*(PR migrated from BB #50)*" in result

    def test_missing_template_variables(self, mock_environment, mock_state):
        """Test handling of missing template variables."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'issue_link': 'Issue #{bb_num} from {bb_url} at {missing_var}',
                'default': ' *(fallback template)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        # Should fall back to default template when variables are missing
        assert "*(fallback template)*" in result
        assert "Issue #123 from" not in result  # Original template should not be used

    def test_template_fallback_to_default(self, mock_environment, mock_state):
        """Test template fallback to default for unknown link types."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'default': ' *(fallback note)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        # Should use default template since issue_link template is not defined
        assert "*(fallback note)*" in result

    def test_short_issue_references_with_custom_templates(self, mock_environment, mock_state):
        """Test short issue references with custom templates."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'short_issue_ref': ' *(short ref BB #{bb_num})*',
                'default': ' *(default)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "This is issue #123 and #789"
        )

        assert "*(short ref BB #123)*" in result
        assert "*(short ref BB #789)*" in result

    def test_pr_references_with_custom_templates(self, mock_environment, mock_state):
        """Test PR references with custom templates."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'pr_ref': ' *(PR ref BB #{bb_num})*',
                'default': ' *(default)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "Check PR #50 and pull request #50"
        )

        assert "*(PR ref BB #50)*" in result

    def test_empty_template(self, mock_environment, mock_state):
        """Test behavior with empty template."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'issue_link': '',
                'default': ' *(default)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        # Should not have any note since template is empty
        assert "*(default)*" not in result
        assert "*(was" not in result
        # But should still have the GitHub link
        assert "[#456]" in result

    def test_complex_template_variables(self, mock_environment, mock_state):
        """Test templates with multiple variables."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'issue_link': ' *(BB #{bb_num} -> GH #{gh_num} | {bb_url})*',
                'default': ' *(complex fallback)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        assert "*(BB #123 -> GH #456 |" in result
        assert "bitbucket.org/test_workspace/test_repo/issues/123" in result

    def test_template_with_special_characters(self, mock_environment, mock_state):
        """Test templates with special regex characters."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'issue_link': ' *(BB #{bb_num} -> GH #{gh_num} [link]({bb_url}))*',
                'default': ' *(special chars)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        assert "*(BB #123 -> GH #456" in result
        assert "[link]" in result


class TestTemplateErrorHandling:
    """Test error handling in template system."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_environment, mock_state):
        """Set up test fixtures."""
        self.issue_mapping = {123: 456}
        self.pr_mapping = {}
        self.repo_mapping = {}
        self.bb_workspace = 'ws'
        self.bb_repo = 'repo'
        self.gh_owner = 'owner'
        self.gh_repo = 'repo'
        self.user_mapper = UserMapper(mock_environment, mock_state)
        yield

    def test_malformed_template_variables(self, mock_environment, mock_state):
        """Test handling of malformed template variables."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'issue_link': 'Issue #{bb_num from {bb_url}',  # Missing closing brace
                'default': ' *(malformed fallback)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        # Should fall back to default template on format error
        assert "*(malformed fallback)*" in result

    def test_template_with_undefined_variables(self, mock_environment, mock_state):
        """Test template with variables not provided by handler."""
        config = LinkRewritingConfig({
            'enabled': True,
            'enable_notes': True,
            'note_templates': {
                'issue_link': 'Issue #{bb_num} - {undefined_var}',
                'default': ' *(undefined fallback)*'
            }
        })

        # Configure environment
        mock_environment.config.link_rewriting_config = config
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        # Should fall back to default template when variables are undefined
        assert "*(undefined fallback)*" in result

    def test_handler_without_template_config(self, mock_environment, mock_state):
        """Test handler behavior when no template config is provided."""
        # Configure environment with no template config
        mock_environment.config.link_rewriting_config = None
        mock_state.mappings.issues = self.issue_mapping
        mock_state.mappings.prs = self.pr_mapping

        rewriter = LinkRewriter(mock_environment, mock_state)

        result, _, _, _, _, _, _ = rewriter.rewrite_links(
            "https://bitbucket.org/test_workspace/test_repo/issues/123"
        )

        # Should not have any notes when no template config
        assert "was BB" not in result
        assert "migrated" not in result
        # But should still have the GitHub link (without notes)
        assert "[#456](https://github.com/test_owner/test_repo/issues/456)" in result
        # Should not have the original Bitbucket URL
        assert "bitbucket.org" not in result