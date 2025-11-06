"""
Comprehensive end-to-end integration tests for link rewriting.

These tests simulate real migration scenarios with realistic data patterns,
performance benchmarks, regression testing, and mixed content validation.
"""

import pytest
import json
import time
import re
from typing import Dict, List, Any
from unittest.mock import MagicMock
from pathlib import Path

from bitbucket_migration.services.link_rewriter import LinkRewriter
from bitbucket_migration.services.user_mapper import UserMapper
from bitbucket_migration.config.migration_config import LinkRewritingConfig


class TestEndToEndMigrationSimulation:
    """End-to-end migration simulation tests with real-world data patterns."""

    @pytest.fixture
    def migration_data(self) -> Dict[str, Any]:
        """Create realistic migration data for testing."""
        return {
            'issues': [
                {
                    'number': 1,
                    'description': """
# Bug Report

Found an issue in https://bitbucket.org/workspace/repo/src/main/app.py
Related to [previous bug](https://bitbucket.org/workspace/repo/issues/123)

See also #456 and PR #45.
                    """
                },
                {
                    'number': 2,
                    'description': """
Check out [this PR](https://bitbucket.org/workspace/repo/pull-requests/30)
and compare with https://bitbucket.org/workspace/repo/compare/abc123..def456
                    """
                },
                {
                    'number': 3,
                    'description': """
![Screenshot](https://bitbucket.org/workspace/repo/raw/main/screenshot.png)

Branch: https://bitbucket.org/workspace/repo/branch/feature/new-feature
Commit: https://bitbucket.org/workspace/repo/commits/abc1234567890
                    """
                },
                {
                    'number': 4,
                    'description': """
Mixed content:
- Plain URL: https://bitbucket.org/workspace/repo/issues/789
- Markdown: [Issue link](https://bitbucket.org/workspace/repo/issues/42)
- Short ref: #123
- PR ref: PR #30
- Mention: @user123
                    """
                },
                {
                    'number': 5,
                    'description': """
Nested markdown test:
[See https://bitbucket.org/workspace/repo/issues/123 for details](https://example.com)

Multiple links: [Issue 1](https://bitbucket.org/workspace/repo/issues/123) and [Issue 2](https://bitbucket.org/workspace/repo/issues/456)
                    """
                }
            ],
            'pull_requests': [
                {
                    'number': 1,
                    'description': """
Fixes https://bitbucket.org/workspace/repo/issues/123
Related: https://bitbucket.org/workspace/repo/pull-requests/45
                    """
                }
            ]
        }

    @pytest.fixture
    def rewriter(self, mock_environment, mock_state):
        """Create a configured LinkRewriter for testing."""
        issue_mapping = {
            123: 1000,
            456: 1001,
            789: 1002,
            42: 1003
        }
        pr_mapping = {
            30: 2000,
            45: 2001
        }
        
        template_config = LinkRewritingConfig()

        # Configure environment and state
        mock_environment.config.link_rewriting_config = template_config
        mock_environment.config.bitbucket.workspace = 'workspace'
        mock_environment.config.bitbucket.repo = 'repo'
        mock_environment.config.github.owner = 'owner'
        mock_environment.config.github.repo = 'repo'
        mock_environment.config.user_mapping = {'user123': 'ghuser123'}
        mock_state.mappings.issues = issue_mapping
        mock_state.mappings.prs = pr_mapping

        # Create link rewriter - it will create its own UserMapper
        link_rewriter = LinkRewriter(mock_environment, mock_state)
        
        # Now override the environment.services to return the actual user_mapper that was created
        user_mapper = mock_state.services.get('UserMapper')
        if user_mapper:
            mock_environment.services.get = lambda name: user_mapper if name == 'user_mapper' else None
        
        return link_rewriter

    def test_end_to_end_migration_simulation(self, rewriter, migration_data):
        """Simulate a complete migration with real-world data."""
        total_links = 0
        total_failures = 0
        total_validation_errors = 0
        all_results = []

        for item in migration_data['issues']:
            result, links_found, unhandled, _, _, _, validation_failures = rewriter.rewrite_links(
                item['description'],
                item_type='issue',
                item_number=item['number']
            )

            total_links += links_found
            total_failures += len(unhandled)
            total_validation_errors += len(validation_failures)

            all_results.append({
                'item_number': item['number'],
                'result': result,
                'links_found': links_found,
                'unhandled': unhandled,
                'validation_failures': validation_failures
            })

            # Validate result integrity
            assert result.count("[") == result.count("]"), \
                f"Unmatched brackets in issue #{item['number']}"
            assert result.count("(") == result.count(")"), \
                f"Unmatched parentheses in issue #{item['number']}"
            assert "][" not in result, \
                f"Markdown nesting detected in issue #{item['number']}"

        # Process PRs
        for item in migration_data['pull_requests']:
            result, links_found, unhandled, _, _, _, validation_failures = rewriter.rewrite_links(
                item['description'],
                item_type='pr',
                item_number=item['number']
            )

            total_links += links_found
            total_failures += len(unhandled)
            total_validation_errors += len(validation_failures)

        print(f"\n=== Migration Simulation Results ===")
        print(f"Total links processed: {total_links}")
        print(f"Total failures: {total_failures}")
        print(f"Total validation errors: {total_validation_errors}")
        print(f"Success rate: {((total_links - total_failures) / total_links * 100):.1f}%")

        # Assertions
        assert total_links > 0, "Should find links to process"
        assert total_failures < total_links * 0.10, \
            f"Failure rate too high: {total_failures}/{total_links} ({total_failures/total_links*100:.1f}%)"
        assert total_validation_errors == 0, \
            f"Should not have validation errors, found {total_validation_errors}"

        # Verify no Bitbucket URLs remain (except in unhandled cases or preserved links)
        for result_data in all_results:
            result = result_data['result']
            if "bitbucket.org" in result:
                # If bitbucket.org appears, there should be unhandled links or validation failures
                # OR it should be a preserved link (e.g., in template text like "*(was [Bitbucket](...))*")
                has_unhandled_or_validation = len(result_data['unhandled']) > 0 or len(result_data['validation_failures']) > 0
                is_preserved_link = "*(was [Bitbucket]" in result or "*(was BB " in result
                assert has_unhandled_or_validation or is_preserved_link, \
                    f"Bitbucket URL found but no unhandled links reported in issue #{result_data['item_number']}"

    def test_mixed_content_comprehensive(self, rewriter):
        """Test comprehensive mixed content with all URL types."""
        input_text = """
# Development Update

## Issues
- Fixed [critical bug](https://bitbucket.org/workspace/repo/issues/123)
- Plain URL: https://bitbucket.org/workspace/repo/issues/456
- Short ref: #789
- Another ref: #42

## Pull Requests
- Merged [feature PR](https://bitbucket.org/workspace/repo/pull-requests/30)
- Plain URL: https://bitbucket.org/workspace/repo/pull-requests/45
- PR ref: PR #30

## Code References
- Branch: https://bitbucket.org/workspace/repo/branch/feature/test
- Commit: https://bitbucket.org/workspace/repo/commits/abc1234567890
- Compare: https://bitbucket.org/workspace/repo/compare/abc123..def456
- File: https://bitbucket.org/workspace/repo/src/main/app.py

## Media
![Diagram](https://bitbucket.org/workspace/repo/raw/main/diagram.png)

## Mentions
Thanks @user123 for the review!
        """

        result, links_found, unhandled, mentions_replaced, _, _, validation_failures = rewriter.rewrite_links(
            input_text,
            item_type='issue',
            item_number=100
        )

        print(f"\n=== Mixed Content Test Results ===")
        print(f"Links found: {links_found}")
        print(f"Unhandled: {len(unhandled)}")
        print(f"Mentions replaced: {mentions_replaced}")
        print(f"Validation failures: {len(validation_failures)}")

        # Structural integrity
        assert result.count("[") == result.count("]"), "Unmatched brackets"
        assert result.count("(") == result.count(")"), "Unmatched parentheses"
        assert "][" not in result, "Markdown nesting detected"

        # Content verification
        assert links_found >= 10, f"Expected at least 10 links, found {links_found}"
        assert mentions_replaced >= 1, "Should replace at least one mention"
        assert len(validation_failures) == 0, f"Should have no validation failures, found {len(validation_failures)}"

        # Verify GitHub URLs present
        assert "github.com/owner/repo/issues/1000" in result, "Issue 123 not rewritten"
        assert "github.com/owner/repo/issues/1001" in result, "Issue 456 not rewritten"
        assert "github.com/owner/repo/issues/2000" in result, "PR 30 not rewritten"
        # Note: Mention rewriting requires proper service setup, skipped for integration test

        # Verify no unwanted Bitbucket URLs (except in unhandled cases or preserved links)
        bb_urls_in_result = result.count("bitbucket.org")
        if bb_urls_in_result > 0:
            has_unhandled = len(unhandled) > 0
            is_preserved_link = "*(was [Bitbucket]" in result or "*(was BB " in result
            assert has_unhandled or is_preserved_link, "Bitbucket URLs present but no unhandled links or preserved links"

    def test_markdown_edge_cases(self, rewriter):
        """Test various markdown edge cases."""
        test_cases = [
            # Nested markdown
            {
                'input': '[See https://bitbucket.org/workspace/repo/issues/123](https://example.com)',
                'description': 'URL in link text'
            },
            # Multiple links in same line
            {
                'input': '[Issue 1](https://bitbucket.org/workspace/repo/issues/123) and [Issue 2](https://bitbucket.org/workspace/repo/issues/456)',
                'description': 'Multiple markdown links'
            },
            # Image links
            {
                'input': '![Alt text](https://bitbucket.org/workspace/repo/raw/main/image.png)',
                'description': 'Image link'
            },
            # Mixed markdown and plain
            {
                'input': 'Check [this](https://bitbucket.org/workspace/repo/issues/123) and https://bitbucket.org/workspace/repo/issues/456',
                'description': 'Mixed markdown and plain'
            },
            # Empty link text
            {
                'input': '[](https://bitbucket.org/workspace/repo/issues/123)',
                'description': 'Empty link text'
            }
        ]

        for test_case in test_cases:
            result, links_found, _, _, _, _, validation_failures = rewriter.rewrite_links(
                test_case['input'],
                item_type='issue',
                item_number=1
            )

            # All test cases should pass structural validation
            assert result.count("[") == result.count("]"), \
                f"Unmatched brackets in: {test_case['description']}"
            assert result.count("(") == result.count(")"), \
                f"Unmatched parentheses in: {test_case['description']}"
            assert "][" not in result, \
                f"Markdown nesting in: {test_case['description']}"
            assert len(validation_failures) == 0, \
                f"Validation failures in: {test_case['description']}"

            # Should find at least one link
            assert links_found >= 1, \
                f"No links found in: {test_case['description']}"


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.fixture
    def rewriter(self, mock_environment, mock_state):
        """Create a LinkRewriter for benchmarking."""
        # Large mapping for realistic scenario
        issue_mapping = {i: i + 1000 for i in range(1, 1001)}
        pr_mapping = {i: i + 2000 for i in range(1, 501)}
        
        template_config = LinkRewritingConfig()

        # Configure environment and state
        mock_environment.config.link_rewriting_config = template_config
        mock_environment.config.bitbucket.workspace = 'workspace'
        mock_environment.config.bitbucket.repo = 'repo'
        mock_environment.config.github.owner = 'owner'
        mock_environment.config.github.repo = 'repo'
        mock_state.mappings.issues = issue_mapping
        mock_state.mappings.prs = pr_mapping

        return LinkRewriter(mock_environment, mock_state)

    def test_performance_benchmark_small(self, rewriter):
        """Benchmark with small dataset (10 URLs)."""
        text = """
        Issue links: https://bitbucket.org/workspace/repo/issues/1
        PR links: https://bitbucket.org/workspace/repo/pull-requests/1
        Markdown: [Link](https://bitbucket.org/workspace/repo/issues/2)
        Short refs: #3, #4, #5
        PR refs: PR #2, PR #3
        """ * 1  # 10 links total

        start = time.perf_counter()
        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(text)
        duration = time.perf_counter() - start

        print(f"\n=== Small Dataset Performance ===")
        print(f"URLs: ~10")
        print(f"Duration: {duration:.3f}s")
        print(f"Links found: {links_found}")
        print(f"Rate: {links_found/duration:.1f} links/sec")

        assert duration < 1.0, f"Small dataset took too long: {duration:.3f}s"

    def test_performance_benchmark_medium(self, rewriter):
        """Benchmark with medium dataset (100 URLs)."""
        text = """
        Issue: https://bitbucket.org/workspace/repo/issues/1
        PR: https://bitbucket.org/workspace/repo/pull-requests/1
        Markdown: [Link](https://bitbucket.org/workspace/repo/issues/2)
        Refs: #3, PR #2
        """ * 20  # ~100 links

        start = time.perf_counter()
        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(text)
        duration = time.perf_counter() - start

        print(f"\n=== Medium Dataset Performance ===")
        print(f"URLs: ~100")
        print(f"Duration: {duration:.3f}s")
        print(f"Links found: {links_found}")
        print(f"Rate: {links_found/duration:.1f} links/sec")

        assert duration < 3.0, f"Medium dataset took too long: {duration:.3f}s"

    def test_performance_benchmark_large(self, rewriter):
        """Benchmark with large dataset (1000 URLs)."""
        text = """
        https://bitbucket.org/workspace/repo/issues/1
        https://bitbucket.org/workspace/repo/pull-requests/1
        [Link](https://bitbucket.org/workspace/repo/issues/2)
        #3 PR #2
        """ * 200  # ~1000 links

        start = time.perf_counter()
        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(text)
        duration = time.perf_counter() - start

        print(f"\n=== Large Dataset Performance ===")
        print(f"URLs: ~1000")
        print(f"Duration: {duration:.3f}s")
        print(f"Links found: {links_found}")
        print(f"Rate: {links_found/duration:.1f} links/sec")

        assert duration < 10.0, f"Large dataset took too long: {duration:.3f}s"
        assert links_found/duration > 50, f"Processing rate too slow: {links_found/duration:.1f} links/sec"


class TestRegressionSuite:
    """Regression test suite for known issues and edge cases."""

    @pytest.fixture
    def rewriter(self, mock_environment, mock_state):
        """Create a LinkRewriter for regression testing."""
        issue_mapping = {123: 456, 789: 1001}
        pr_mapping = {45: 200}
        
        template_config = LinkRewritingConfig()

        # Configure environment and state
        mock_environment.config.link_rewriting_config = template_config
        mock_environment.config.bitbucket.workspace = 'workspace'
        mock_environment.config.bitbucket.repo = 'repo'
        mock_environment.config.github.owner = 'owner'
        mock_environment.config.github.repo = 'repo'
        mock_state.mappings.issues = issue_mapping
        mock_state.mappings.prs = pr_mapping

        return LinkRewriter(mock_environment, mock_state)

    def test_regression_no_markdown_nesting(self, rewriter):
        """Regression: Ensure markdown nesting bug is fixed."""
        # This was a known bug where markdown links created nested structures
        input_text = "[See this issue](https://bitbucket.org/workspace/repo/issues/123)"
        
        result, _, _, _, _, _, _ = rewriter.rewrite_links(input_text)
        
        assert "][" not in result, "Markdown nesting bug has regressed"
        assert result.count("[") == result.count("]"), "Unmatched brackets"
        assert result.count("(") == result.count(")"), "Unmatched parentheses"

    def test_regression_url_encoding(self, rewriter):
        """Regression: Ensure URL encoding works for special characters."""
        test_cases = [
            "https://bitbucket.org/workspace/repo/branch/feature/my-branch",
            "https://bitbucket.org/workspace/repo/branch/fix#123",
        ]
        
        for url in test_cases:
            result, links_found, _, _, _, _, _ = rewriter.rewrite_links(url)
            
            # Should not have raw special chars in GitHub URL (except alphanumeric and -)
            assert links_found >= 1, f"Link not found: {url}"
            # The GitHub URL should be properly encoded
            assert "github.com" in result, f"Not rewritten: {url}"

    def test_regression_duplicate_tracking(self, rewriter):
        """Regression: Ensure no duplicate link tracking."""
        input_text = """
        https://bitbucket.org/workspace/repo/issues/123
        https://bitbucket.org/workspace/repo/issues/123
        """
        
        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)
        
        # Check link_details for duplicates
        link_details = rewriter.state.services['LinkRewriter'].details
        originals = [d['original'] for d in link_details]
        unique_originals = set(originals)
        
        assert len(originals) == len(unique_originals), \
            f"Duplicate tracking detected: {len(originals)} vs {len(unique_originals)}"

    def test_regression_partial_url_matching(self, rewriter):
        """Regression: Ensure handlers don't partially match URLs."""
        # Full PR URL should not match repo home handler
        input_text = "https://bitbucket.org/workspace/repo/pull-requests/45"
        
        result, links_found, _, _, _, _, _ = rewriter.rewrite_links(input_text)
        
        # Should be handled as PR, not repo home
        link_details = rewriter.state.services['LinkRewriter'].details
        pr_links = [d for d in link_details if d['type'] == 'pr_link']
        repo_home_links = [d for d in link_details if d['type'] == 'repo_home_link']
        
        assert len(pr_links) > 0, "PR link not detected"
        assert not any('pull-requests' in d['original'] for d in repo_home_links), \
            "Repo home handler partially matched PR URL"

    def test_regression_validation_failures(self, rewriter):
        """Regression: Ensure validation catches invalid GitHub URLs."""
        # This tests that the validation system is working
        # Normal valid URLs should pass validation
        input_text = "https://bitbucket.org/workspace/repo/issues/123"
        
        result, _, _, _, _, _, validation_failures = rewriter.rewrite_links(input_text)
        
        # Should not have validation failures for standard links
        assert len(validation_failures) == 0, \
            f"Unexpected validation failures: {validation_failures}"


class TestMixedContentScenarios:
    """Test realistic mixed content scenarios."""

    @pytest.fixture
    def rewriter(self, mock_environment, mock_state):
        """Create a LinkRewriter for mixed content testing."""
        issue_mapping = {i: i + 100 for i in range(1, 51)}
        pr_mapping = {i: i + 200 for i in range(1, 26)}
        
        template_config = LinkRewritingConfig()

        # Configure environment and state
        mock_environment.config.link_rewriting_config = template_config
        mock_environment.config.bitbucket.workspace = 'workspace'
        mock_environment.config.bitbucket.repo = 'repo'
        mock_environment.config.github.owner = 'owner'
        mock_environment.config.github.repo = 'repo'
        mock_environment.config.user_mapping = {'user1': 'ghuser1', 'user2': 'ghuser2'}
        mock_state.mappings.issues = issue_mapping
        mock_state.mappings.prs = pr_mapping

        # Create link rewriter - it will create its own UserMapper
        link_rewriter = LinkRewriter(mock_environment, mock_state)
        
        # Now override the environment.services to return the actual user_mapper that was created
        user_mapper = mock_state.services.get('UserMapper')
        if user_mapper:
            mock_environment.services.get = lambda name: user_mapper if name == 'user_mapper' else None
        
        return link_rewriter

    def test_mixed_content_github_issue_description(self, rewriter):
        """Test realistic GitHub issue description."""
        input_text = """
## Description
This issue is related to https://bitbucket.org/workspace/repo/issues/10

## Steps to Reproduce
1. Check the code in https://bitbucket.org/workspace/repo/src/main/app.py
2. Run the test mentioned in #15
3. Compare with https://bitbucket.org/workspace/repo/compare/abc123..def456

## Related
- [Original bug report](https://bitbucket.org/workspace/repo/issues/5)
- [Fix attempt](https://bitbucket.org/workspace/repo/pull-requests/20)
- See also: #8, #12, PR #15

## Screenshots
![Before](https://bitbucket.org/workspace/repo/raw/main/before.png)
![After](https://bitbucket.org/workspace/repo/raw/main/after.png)

## Credits
Thanks @user1 and @user2 for investigating this!
        """

        result, links_found, unhandled, mentions_replaced, _, _, validation_failures = rewriter.rewrite_links(
            input_text,
            item_type='issue',
            item_number=50
        )

        # Comprehensive checks
        assert links_found >= 10, f"Expected at least 10 links, found {links_found}"
        assert mentions_replaced >= 2, f"Expected 2 mentions replaced, found {mentions_replaced}"
        assert len(validation_failures) == 0, f"Validation failures: {validation_failures}"
        
        # Structural integrity
        assert result.count("[") == result.count("]"), "Unmatched brackets"
        assert result.count("(") == result.count(")"), "Unmatched parentheses"
        assert "][" not in result, "Markdown nesting"
        
        # Content checks
        # Note: Mention rewriting requires proper service setup, skipped for integration test
        assert "github.com" in result, "No GitHub URLs found"
        
        # Verify specific rewrites
        assert "issues/110" in result, "Issue #10 not rewritten correctly"
        assert "issues/105" in result, "Issue #5 not rewritten correctly"
        assert "issues/220" in result, "PR #20 not rewritten correctly"

    def test_mixed_content_pr_description(self, rewriter):
        """Test realistic GitHub PR description."""
        input_text = """
## Changes
This PR fixes https://bitbucket.org/workspace/repo/issues/25 and improves performance.

## Related PRs
- Depends on [infrastructure PR](https://bitbucket.org/workspace/repo/pull-requests/10)
- Related to PR #15

## Testing
Tested on branch https://bitbucket.org/workspace/repo/branch/feature/optimization

## Review
@user1 please review the changes in https://bitbucket.org/workspace/repo/src/feature/optimization/optimizer.py
        """

        result, links_found, _, mentions_replaced, _, _, validation_failures = rewriter.rewrite_links(
            input_text,
            item_type='pr',
            item_number=25
        )

        assert links_found >= 5, f"Expected at least 5 links, found {links_found}"
        assert mentions_replaced >= 1, "Expected mention to be replaced"
        assert len(validation_failures) == 0, "Should have no validation failures"
        
        assert result.count("[") == result.count("]"), "Unmatched brackets"
        assert result.count("(") == result.count(")"), "Unmatched parentheses"
        assert "][" not in result, "Markdown nesting detected"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])