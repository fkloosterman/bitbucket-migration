"""
Audit utilities for Bitbucket to GitHub migration analysis.

This module contains audit-specific functionality extracted from the original
audit_bitbucket.py script, including gap analysis, PR migratability analysis,
and migration estimates.
"""

from typing import Dict, List, Tuple, Any
from collections import Counter


class AuditUtils:
    """
    Utility class for audit-specific calculations and analysis.

    This class contains methods that are unique to the audit functionality
    and not part of the core migration system.
    """

    def analyze_gaps(self, items: List[Dict[str, Any]]) -> Tuple[List[int], int]:
        """
        Analyze number gaps in issues or PRs.

        Args:
            items: List of issue or PR dictionaries with 'number' field

        Returns:
            Tuple of (gap_numbers_list, total_gap_count)
        """
        if not items:
            return [], 0

        numbers = sorted([item['id'] for item in items])
        gaps = []

        if numbers:
            expected = 1
            for num in numbers:
                while expected < num:
                    gaps.append(expected)
                    expected += 1
                expected = num + 1

        return gaps, len(gaps)

    def analyze_pr_migratability(self, pull_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze which PRs can be migrated completely vs partially.

        Args:
            pull_requests: List of PR dictionaries

        Returns:
            Dictionary with migration analysis results
        """
        fully_migratable = []  # Open PRs with branches intact
        partially_migratable = []  # Closed PRs - can migrate as issues
        migration_challenges = []  # PRs with specific issues

        for pr in pull_requests:
            pr_analysis = {
                'number': pr['id'],
                'title': pr['title'],
                'state': pr['state'],
                'source_branch': pr.get('source_branch'),
                'can_migrate_as_pr': pr.get('migratable', True),
                'issues': pr.get('migration_issues', []),
                'data_preserved': {
                    'description': True,
                    'comments': pr.get('comment_count', 0) > 0,
                    'commits': pr.get('commit_count', 0) > 0,
                    'reviewers': pr.get('reviewers', 0) > 0,
                    'diff': pr.get('migratable', True),  # Only if branches exist
                }
            }

            if pr.get('state') == 'OPEN' and pr.get('migratable', True):
                fully_migratable.append(pr_analysis)
            elif pr.get('state') in ['MERGED', 'DECLINED', 'SUPERSEDED']:
                partially_migratable.append(pr_analysis)
            else:
                migration_challenges.append(pr_analysis)

        return {
            'fully_migratable': {
                'count': len(fully_migratable),
                'prs': fully_migratable
            },
            'partially_migratable': {
                'count': len(partially_migratable),
                'prs': partially_migratable,
                'note': 'These PRs can be migrated as issues with PR metadata in description'
            },
            'migration_challenges': {
                'count': len(migration_challenges),
                'prs': migration_challenges
            }
        }

    def calculate_migration_estimates(self, issues: List[Dict[str, Any]],
                                    pull_requests: List[Dict[str, Any]],
                                    attachments: List[Dict[str, Any]],
                                    issue_gaps: int) -> Dict[str, Any]:
        """
        Calculate migration time and API call estimates.

        Args:
            issues: List of issue dictionaries
            pull_requests: List of PR dictionaries
            attachments: List of attachment dictionaries
            issue_gaps: Number of missing issue numbers

        Returns:
            Dictionary with migration estimates
        """
        return {
            'placeholder_issues_needed': issue_gaps,
            'total_api_calls_estimate': (
                len(issues) * 3 +  # Create issue, comments, close if needed
                len(pull_requests) * 2 +  # Create PR, comments
                issue_gaps +  # Placeholder issues
                len(attachments)  # Attachment uploads
            ),
            'estimated_time_minutes': round(
                (len(issues) + len(pull_requests) + issue_gaps) * 0.5,  # ~0.5 min per item
                1
            ),
            'issues_count': len(issues),
            'prs_count': len(pull_requests),
            'attachments_count': len(attachments),
            'total_items': len(issues) + len(pull_requests) + issue_gaps
        }

    def analyze_repository_structure(self, issues: List[Dict[str, Any]],
                                    pull_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze overall repository structure and content.

        Args:
            issues: List of issue dictionaries
            pull_requests: List of PR dictionaries

        Returns:
            Dictionary with structural analysis
        """
        # Analyze issue states
        issue_states = Counter(i.get('state', 'unknown') for i in issues)
        pr_states = Counter(p.get('state', 'unknown') for p in pull_requests)

        # Calculate date ranges
        def get_date_range(items, date_field='created_on'):
            if not items:
                return None, None
            dates = []
            for item in items:
                date_str = item.get(date_field)
                if date_str:
                    # Handle ISO format dates
                    from datetime import datetime
                    try:
                        # Try to parse as ISO format (with or without Z)
                        if 'Z' in date_str:
                            dates.append(datetime.fromisoformat(date_str.replace('Z', '+00:00')))
                        else:
                            dates.append(datetime.fromisoformat(date_str))
                    except ValueError:
                        # If parsing fails, skip this date
                        continue

            if dates:
                return min(dates), max(dates)
            return None, None

        issue_first, issue_last = get_date_range(issues)
        pr_first, pr_last = get_date_range(pull_requests)

        return {
            'issue_states': dict(issue_states),
            'pr_states': dict(pr_states),
            'issue_date_range': {
                'first': issue_first.isoformat() if issue_first else None,
                'last': issue_last.isoformat() if issue_last else None,
            },
            'pr_date_range': {
                'first': pr_first.isoformat() if pr_first else None,
                'last': pr_last.isoformat() if pr_last else None,
            },
            'total_issues': len(issues),
            'total_prs': len(pull_requests),
            'has_issues': len(issues) > 0,
            'has_prs': len(pull_requests) > 0
        }

    def generate_migration_strategy(self, pr_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate recommended migration strategy based on PR analysis.

        Args:
            pr_analysis: Results from analyze_pr_migratability()

        Returns:
            Dictionary with migration strategy recommendations
        """
        fully_migratable = pr_analysis['fully_migratable']['count']
        partially_migratable = pr_analysis['partially_migratable']['count']
        challenges = pr_analysis['migration_challenges']['count']

        strategy = {
            'recommended_approach': 'hybrid' if fully_migratable > 0 and partially_migratable > 0 else 'issues_only',
            'steps': []
        }

        if fully_migratable > 0:
            strategy['steps'].append({
                'step': 1,
                'action': 'migrate_open_prs',
                'description': f'Migrate {fully_migratable} open PRs as actual GitHub PRs',
                'count': fully_migratable
            })

        if partially_migratable > 0:
            strategy['steps'].append({
                'step': 2,
                'action': 'migrate_closed_prs_as_issues',
                'description': f'Migrate {partially_migratable} closed PRs as GitHub issues',
                'count': partially_migratable,
                'note': 'Include original PR metadata, state, and links in description'
            })

        if challenges > 0:
            strategy['steps'].append({
                'step': 3,
                'action': 'review_challenges',
                'description': f'Review {challenges} PRs with migration challenges',
                'count': challenges,
                'note': 'May have missing branches or other issues requiring manual handling'
            })

        strategy['steps'].append({
            'step': len(strategy['steps']) + 1,
            'action': 'preserve_history',
            'description': 'All PR comments, commits, and history will be preserved in descriptions',
            'count': None
        })

        return strategy