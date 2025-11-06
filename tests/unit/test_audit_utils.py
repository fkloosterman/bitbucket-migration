"""
Tests for AuditUtils.

Tests the audit utility functions including:
- Gap analysis for issues and PRs
- PR migratability analysis
- Migration time and API estimates
- Repository structure analysis
- Migration strategy generation
"""

import pytest
from datetime import datetime
from unittest.mock import Mock

from bitbucket_migration.audit.audit_utils import AuditUtils


class TestAuditUtilsInitialization:
    """Test AuditUtils initialization."""
    
    def test_init(self):
        """Test that AuditUtils initializes properly."""
        utils = AuditUtils()
        assert utils is not None


class TestGapAnalysis:
    """Test gap analysis functionality."""
    
    @pytest.fixture
    def audit_utils(self):
        """Create AuditUtils for testing."""
        return AuditUtils()
    
    def test_analyze_gaps_empty_list(self, audit_utils):
        """Test gap analysis with empty list."""
        gaps, count = audit_utils.analyze_gaps([])
        
        assert gaps == []
        assert count == 0
    
    def test_analyze_gaps_no_gaps(self, audit_utils):
        """Test gap analysis with continuous sequence."""
        items = [
            {'id': 1}, {'id': 2}, {'id': 3}, {'id': 4}, {'id': 5}
        ]
        
        gaps, count = audit_utils.analyze_gaps(items)
        
        assert gaps == []
        assert count == 0
    
    def test_analyze_gaps_with_gaps(self, audit_utils):
        """Test gap analysis with missing numbers."""
        items = [
            {'id': 1}, {'id': 2}, {'id': 4}, {'id': 5}, {'id': 7}
        ]
        
        gaps, count = audit_utils.analyze_gaps(items)
        
        assert gaps == [3, 6]
        assert count == 2
    
    def test_analyze_gaps_only_gaps(self, audit_utils):
        """Test gap analysis with only gaps (no items)."""
        items = []
        
        gaps, count = audit_utils.analyze_gaps(items)
        
        assert gaps == []
        assert count == 0
    
    def test_analyze_gaps_single_item(self, audit_utils):
        """Test gap analysis with single item."""
        items = [{'id': 5}]
        
        gaps, count = audit_utils.analyze_gaps(items)
        
        # Should have gaps 1, 2, 3, 4 before item 5
        assert gaps == [1, 2, 3, 4]
        assert count == 4
    
    def test_analyze_gaps_unsorted_items(self, audit_utils):
        """Test gap analysis with unsorted items (should handle gracefully)."""
        items = [
            {'id': 5}, {'id': 2}, {'id': 8}, {'id': 3}
        ]
        
        gaps, count = audit_utils.analyze_gaps(items)
        
        # Should have gaps 1, 4, 6, 7
        assert gaps == [1, 4, 6, 7]
        assert count == 4
    
    def test_analyze_gaps_negative_ids(self, audit_utils):
        """Test gap analysis with negative IDs."""
        items = [
            {'id': 1}, {'id': 2}, {'id': 5}
        ]
        
        gaps, count = audit_utils.analyze_gaps(items)
        
        # Should have gaps 3, 4
        assert gaps == [3, 4]
        assert count == 2


class TestPRMigratabilityAnalysis:
    """Test PR migratability analysis functionality."""
    
    @pytest.fixture
    def audit_utils(self):
        """Create AuditUtils for testing."""
        return AuditUtils()
    
    def test_analyze_pr_migratability_empty_list(self, audit_utils):
        """Test PR analysis with empty list."""
        result = audit_utils.analyze_pr_migratability([])
        
        assert result['fully_migratable']['count'] == 0
        assert result['partially_migratable']['count'] == 0
        assert result['migration_challenges']['count'] == 0
        assert result['fully_migratable']['prs'] == []
        assert result['partially_migratable']['prs'] == []
        assert result['migration_challenges']['prs'] == []
    
    def test_analyze_pr_migratability_fully_migratable(self, audit_utils):
        """Test analysis with fully migratable open PRs."""
        prs = [
            {
                'id': 1,
                'title': 'Feature A',
                'state': 'OPEN',
                'source_branch': 'feature-a',
                'migratable': True
            },
            {
                'id': 2,
                'title': 'Feature B', 
                'state': 'OPEN',
                'source_branch': 'feature-b',
                'migratable': True,
                'comment_count': 5,
                'commit_count': 3,
                'reviewers': 2
            }
        ]
        
        result = audit_utils.analyze_pr_migratability(prs)
        
        assert result['fully_migratable']['count'] == 2
        assert result['partially_migratable']['count'] == 0
        assert result['migration_challenges']['count'] == 0
        
        # Check first PR details
        pr1 = result['fully_migratable']['prs'][0]
        assert pr1['number'] == 1
        assert pr1['title'] == 'Feature A'
        assert pr1['state'] == 'OPEN'
        assert pr1['source_branch'] == 'feature-a'
        assert pr1['can_migrate_as_pr'] is True
        
        # Check data preservation
        assert pr1['data_preserved']['description'] is True
        assert pr1['data_preserved']['comments'] is False  # No comments
        assert pr1['data_preserved']['commits'] is False  # No commits
        assert pr1['data_preserved']['reviewers'] is False  # No reviewers
        assert pr1['data_preserved']['diff'] is True  # Migratable = True
        
        # Check second PR with data
        pr2 = result['fully_migratable']['prs'][1]
        assert pr2['data_preserved']['comments'] is True
        assert pr2['data_preserved']['commits'] is True
        assert pr2['data_preserved']['reviewers'] is True
    
    def test_analyze_pr_migratability_partially_migratable(self, audit_utils):
        """Test analysis with closed PRs that can be migrated as issues."""
        prs = [
            {
                'id': 3,
                'title': 'Merged Feature',
                'state': 'MERGED',
                'source_branch': 'merged-branch'
            },
            {
                'id': 4,
                'title': 'Declined Feature',
                'state': 'DECLINED',
                'source_branch': 'declined-branch'
            }
        ]
        
        result = audit_utils.analyze_pr_migratability(prs)
        
        assert result['fully_migratable']['count'] == 0
        assert result['partially_migratable']['count'] == 2
        assert result['migration_challenges']['count'] == 0
        
        # Both should be in partially migratable
        assert len(result['partially_migratable']['prs']) == 2
        assert result['partially_migratable']['prs'][0]['state'] == 'MERGED'
        assert result['partially_migratable']['prs'][1]['state'] == 'DECLINED'
    
    def test_analyze_pr_migratability_migration_challenges(self, audit_utils):
        """Test analysis with PRs that have migration challenges."""
        prs = [
            {
                'id': 5,
                'title': 'Complex PR',
                'state': 'OPEN',
                'source_branch': 'complex-branch',
                'migratable': False,
                'migration_issues': ['Missing source branch']
            }
        ]
        
        result = audit_utils.analyze_pr_migratability(prs)
        
        assert result['fully_migratable']['count'] == 0
        assert result['partially_migratable']['count'] == 0
        assert result['migration_challenges']['count'] == 1
        
        # Check challenges details
        pr = result['migration_challenges']['prs'][0]
        assert pr['can_migrate_as_pr'] is False
        assert 'Missing source branch' in pr['issues']
    
    def test_analyze_pr_migratability_mixed_states(self, audit_utils):
        """Test analysis with mixed PR states."""
        prs = [
            {
                'id': 1,
                'title': 'Open PR',
                'state': 'OPEN',
                'source_branch': 'open-branch',
                'migratable': True
            },
            {
                'id': 2,
                'title': 'Merged PR',
                'state': 'MERGED',
                'source_branch': 'merged-branch'
            },
            {
                'id': 3,
                'title': 'Superseded PR',
                'state': 'SUPERSEDED',
                'source_branch': 'superseded-branch'
            }
        ]
        
        result = audit_utils.analyze_pr_migratability(prs)
        
        assert result['fully_migratable']['count'] == 1
        assert result['partially_migratable']['count'] == 2  # MERGED + SUPERSEDED
        assert result['migration_challenges']['count'] == 0


class TestMigrationEstimates:
    """Test migration time and API call estimates."""
    
    @pytest.fixture
    def audit_utils(self):
        """Create AuditUtils for testing."""
        return AuditUtils()
    
    def test_calculate_migration_estimates_empty(self, audit_utils):
        """Test estimates with no data."""
        estimates = audit_utils.calculate_migration_estimates(
            issues=[],
            pull_requests=[],
            attachments=[],
            issue_gaps=0
        )
        
        assert estimates['placeholder_issues_needed'] == 0
        assert estimates['total_api_calls_estimate'] == 0
        assert estimates['estimated_time_minutes'] == 0
        assert estimates['issues_count'] == 0
        assert estimates['prs_count'] == 0
        assert estimates['attachments_count'] == 0
        assert estimates['total_items'] == 0
    
    def test_calculate_migration_estimates_with_data(self, audit_utils):
        """Test estimates with sample data."""
        issues = [{'id': i} for i in range(1, 11)]  # 10 issues
        pull_requests = [{'id': i} for i in range(1, 6)]  # 5 PRs
        attachments = [{'name': f'attachment{i}'} for i in range(1, 4)]  # 3 attachments
        issue_gaps = 3  # 3 missing issue numbers
        
        estimates = audit_utils.calculate_migration_estimates(
            issues, pull_requests, attachments, issue_gaps
        )
        
        # Verify calculations
        assert estimates['placeholder_issues_needed'] == 3
        
        # API calls: 10 issues * 3 = 30, 5 PRs * 2 = 10, 3 placeholders, 3 attachments = 46
        assert estimates['total_api_calls_estimate'] == 46
        
        # Time: (10 + 5 + 3) * 0.5 = 9.0 minutes
        assert estimates['estimated_time_minutes'] == 9.0
        
        # Counts
        assert estimates['issues_count'] == 10
        assert estimates['prs_count'] == 5
        assert estimates['attachments_count'] == 3
        assert estimates['total_items'] == 18  # 10 + 5 + 3
    
    def test_calculate_migration_estimates_large_numbers(self, audit_utils):
        """Test estimates with large numbers."""
        issues = [{'id': i} for i in range(1, 101)]  # 100 issues
        pull_requests = [{'id': i} for i in range(1, 51)]  # 50 PRs
        attachments = [{'name': f'attachment{i}'} for i in range(1, 21)]  # 20 attachments
        issue_gaps = 10
        
        estimates = audit_utils.calculate_migration_estimates(
            issues, pull_requests, attachments, issue_gaps
        )
        
        # Time should be rounded to 1 decimal
        assert estimates['estimated_time_minutes'] == 80.0  # (100 + 50 + 10) * 0.5


class TestRepositoryStructureAnalysis:
    """Test repository structure analysis functionality."""
    
    @pytest.fixture
    def audit_utils(self):
        """Create AuditUtils for testing."""
        return AuditUtils()
    
    def test_analyze_repository_structure_empty(self, audit_utils):
        """Test structure analysis with no data."""
        result = audit_utils.analyze_repository_structure([], [])
        
        assert result['issue_states'] == {}
        assert result['pr_states'] == {}
        assert result['issue_date_range']['first'] is None
        assert result['issue_date_range']['last'] is None
        assert result['pr_date_range']['first'] is None
        assert result['pr_date_range']['last'] is None
        assert result['total_issues'] == 0
        assert result['total_prs'] == 0
        assert result['has_issues'] is False
        assert result['has_prs'] is False
    
    def test_analyze_repository_structure_with_issues_and_prs(self, audit_utils):
        """Test structure analysis with sample issues and PRs."""
        issues = [
            {
                'id': 1,
                'state': 'new',
                'created_on': '2024-01-01T10:00:00Z'
            },
            {
                'id': 2,
                'state': 'resolved',
                'created_on': '2024-01-05T14:30:00Z'
            },
            {
                'id': 3,
                'state': 'new',
                'created_on': '2024-01-10T09:15:00Z'
            }
        ]
        
        pull_requests = [
            {
                'id': 1,
                'state': 'OPEN',
                'created_on': '2024-01-02T11:00:00Z'
            },
            {
                'id': 2,
                'state': 'MERGED',
                'created_on': '2024-01-08T16:45:00Z'
            }
        ]
        
        result = audit_utils.analyze_repository_structure(issues, pull_requests)
        
        # Issue states
        assert result['issue_states'] == {'new': 2, 'resolved': 1}
        
        # PR states
        assert result['pr_states'] == {'OPEN': 1, 'MERGED': 1}
        
        # Issue date range (with timezone formatting)
        assert '2024-01-01T10:00:00' in result['issue_date_range']['first']
        assert '2024-01-10T09:15:00' in result['issue_date_range']['last']
        
        # PR date range (with timezone formatting)
        assert '2024-01-02T11:00:00' in result['pr_date_range']['first']
        assert '2024-01-08T16:45:00' in result['pr_date_range']['last']
        
        # Totals
        assert result['total_issues'] == 3
        assert result['total_prs'] == 2
        assert result['has_issues'] is True
        assert result['has_prs'] is True
    
    def test_analyze_repository_structure_missing_dates(self, audit_utils):
        """Test structure analysis with missing date fields."""
        issues = [
            {
                'id': 1,
                'state': 'new'
                # No created_on field
            }
        ]
        
        result = audit_utils.analyze_repository_structure(issues, [])
        
        assert result['issue_date_range']['first'] is None
        assert result['issue_date_range']['last'] is None
        assert result['total_issues'] == 1
        assert result['has_issues'] is True
    
    def test_analyze_repository_structure_invalid_dates(self, audit_utils):
        """Test structure analysis with invalid date formats."""
        issues = [
            {
                'id': 1,
                'state': 'new',
                'created_on': 'invalid-date-format'
            },
            {
                'id': 2,
                'state': 'resolved',
                'created_on': '2024-01-15T10:00:00Z'
            }
        ]
        
        result = audit_utils.analyze_repository_structure(issues, [])
        
        # Should handle invalid date gracefully (skip it)
        assert '2024-01-15T10:00:00' in result['issue_date_range']['first']
        assert '2024-01-15T10:00:00' in result['issue_date_range']['last']
    
    def test_analyze_repository_structure_different_date_formats(self, audit_utils):
        """Test structure analysis with different date formats."""
        issues = [
            {
                'id': 1,
                'state': 'new',
                'created_on': '2024-01-01T10:00:00+00:00'  # With timezone
            },
            {
                'id': 2,
                'state': 'resolved',
                'created_on': '2024-01-05T14:30:00+00:00'  # Same timezone
            }
        ]
        
        result = audit_utils.analyze_repository_structure(issues, [])
        
        # Should handle both formats
        assert result['issue_date_range']['first'] is not None
        assert result['issue_date_range']['last'] is not None
        assert result['total_issues'] == 2


class TestMigrationStrategy:
    """Test migration strategy generation."""
    
    @pytest.fixture
    def audit_utils(self):
        """Create AuditUtils for testing."""
        return AuditUtils()
    
    def test_generate_migration_strategy_only_issues(self, audit_utils):
        """Test strategy generation when only issues can be migrated."""
        pr_analysis = {
            'fully_migratable': {'count': 0},
            'partially_migratable': {'count': 0},
            'migration_challenges': {'count': 0}
        }
        
        strategy = audit_utils.generate_migration_strategy(pr_analysis)
        
        assert strategy['recommended_approach'] == 'issues_only'
        assert len(strategy['steps']) == 1  # Only preserve history step
        assert strategy['steps'][0]['action'] == 'preserve_history'
    
    def test_generate_migration_strategy_hybrid_approach(self, audit_utils):
        """Test strategy generation with hybrid approach."""
        pr_analysis = {
            'fully_migratable': {'count': 5},
            'partially_migratable': {'count': 3},
            'migration_challenges': {'count': 2}
        }
        
        strategy = audit_utils.generate_migration_strategy(pr_analysis)
        
        assert strategy['recommended_approach'] == 'hybrid'
        assert len(strategy['steps']) == 4  # 3 migration steps + preserve history
        
        # Step 1: Migrate open PRs
        step1 = strategy['steps'][0]
        assert step1['step'] == 1
        assert step1['action'] == 'migrate_open_prs'
        assert step1['count'] == 5
        
        # Step 2: Migrate closed PRs as issues
        step2 = strategy['steps'][1]
        assert step2['step'] == 2
        assert step2['action'] == 'migrate_closed_prs_as_issues'
        assert step2['count'] == 3
        assert step2['note'] is not None
        
        # Step 3: Review challenges
        step3 = strategy['steps'][2]
        assert step3['step'] == 3
        assert step3['action'] == 'review_challenges'
        assert step3['count'] == 2
        assert step3['note'] is not None
        
        # Step 4: Preserve history
        step4 = strategy['steps'][3]
        assert step4['step'] == 4
        assert step4['action'] == 'preserve_history'
        assert step4['count'] is None
    
    def test_generate_migration_strategy_all_prs_migratable(self, audit_utils):
        """Test strategy when all PRs are fully migratable."""
        pr_analysis = {
            'fully_migratable': {'count': 8},
            'partially_migratable': {'count': 0},
            'migration_challenges': {'count': 0}
        }
        
        strategy = audit_utils.generate_migration_strategy(pr_analysis)
        
        # Should be 'issues_only' since no partially migratable PRs
        assert strategy['recommended_approach'] == 'issues_only'
        assert len(strategy['steps']) == 2  # Migrate PRs + preserve history
        
        step1 = strategy['steps'][0]
        assert step1['action'] == 'migrate_open_prs'
        assert step1['count'] == 8
        
        step2 = strategy['steps'][1]
        assert step2['action'] == 'preserve_history'
        assert step2['count'] is None
    
    def test_generate_migration_strategy_only_challenges(self, audit_utils):
        """Test strategy when only PRs with challenges exist."""
        pr_analysis = {
            'fully_migratable': {'count': 0},
            'partially_migratable': {'count': 0},
            'migration_challenges': {'count': 1}
        }
        
        strategy = audit_utils.generate_migration_strategy(pr_analysis)
        
        assert strategy['recommended_approach'] == 'issues_only'  # No fully migratable PRs
        assert len(strategy['steps']) == 2  # Review challenges + preserve history
        
        step1 = strategy['steps'][0]
        assert step1['action'] == 'review_challenges'
        assert step1['count'] == 1
    
    def test_generate_migration_strategy_large_numbers(self, audit_utils):
        """Test strategy with large numbers of PRs."""
        pr_analysis = {
            'fully_migratable': {'count': 150},
            'partially_migratable': {'count': 75},
            'migration_challenges': {'count': 25}
        }
        
        strategy = audit_utils.generate_migration_strategy(pr_analysis)
        
        # All counts should be preserved
        assert strategy['steps'][0]['count'] == 150
        assert strategy['steps'][1]['count'] == 75
        assert strategy['steps'][2]['count'] == 25