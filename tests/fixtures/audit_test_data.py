"""
Test fixtures for audit module tests.

Provides shared fixtures and mock data for testing audit functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock
from typing import Dict, Any, List


# Sample repository data for testing
SAMPLE_REPOSITORY_DATA = {
    'workspace': 'test-workspace',
    'repo': 'test-repo',
    'email': 'test@example.com',
    'token': 'test-token'
}


# Sample issues data for testing
SAMPLE_ISSUES = [
    {
        'id': 1,
        'title': 'First Issue',
        'state': 'new',
        'kind': 'bug',
        'reporter': {
            'account_id': 'acc1',
            'username': 'user1',
            'display_name': 'User One'
        },
        'assignee': {
            'account_id': 'acc2',
            'username': 'user2',
            'display_name': 'User Two'
        },
        'created_on': '2024-01-01T10:00:00Z',
        'updated_on': '2024-01-05T14:30:00Z',
        'comment_count': 3,
        'attachment_count': 1
    },
    {
        'id': 2,
        'title': 'Second Issue',
        'state': 'resolved',
        'kind': 'enhancement',
        'reporter': {
            'account_id': 'acc3',
            'username': 'user3',
            'display_name': 'User Three'
        },
        'assignee': {
            'account_id': 'acc1',
            'username': 'user1',
            'display_name': 'User One Updated'
        },
        'created_on': '2024-01-10T09:15:00Z',
        'updated_on': '2024-01-15T16:45:00Z',
        'comment_count': 5,
        'attachment_count': 0
    },
    {
        'id': 3,
        'title': 'Third Issue',
        'state': 'on_hold',
        'kind': 'task',
        'reporter': {
            'account_id': 'acc2',
            'username': 'user2',
            'display_name': 'User Two'
        },
        'created_on': '2024-02-01T11:30:00Z',
        'updated_on': '2024-02-10T13:20:00Z',
        'comment_count': 1,
        'attachment_count': 2
    },
    {
        'id': 4,
        'title': 'Fourth Issue',
        'state': 'closed',
        'reporter': {
            'account_id': 'acc4',
            'username': 'user4',
            'display_name': 'User Four'
        },
        'created_on': '2024-02-15T08:00:00Z',
        'updated_on': '2024-02-20T17:00:00Z',
        'comment_count': 0,
        'attachment_count': 0
    },
    {
        'id': 5,
        'title': 'Fifth Issue',
        'state': 'new',
        'reporter': {
            'display_name': 'Unknown (deleted user)'
        },
        'created_on': '2024-03-01T12:00:00Z',
        'comment_count': 2,
        'attachment_count': 0
    }
]


# Sample pull requests data for testing
SAMPLE_PULL_REQUESTS = [
    {
        'id': 1,
        'title': 'Add new feature',
        'state': 'OPEN',
        'author': {
            'account_id': 'acc1',
            'username': 'user1',
            'display_name': 'User One'
        },
        'source_branch': 'feature/new-feature',
        'destination_branch': 'main',
        'created_on': '2024-01-05T10:00:00Z',
        'updated_on': '2024-01-10T14:30:00Z',
        'comment_count': 2,
        'commit_count': 5,
        'reviewers': [
            {
                'account_id': 'acc2',
                'username': 'user2',
                'display_name': 'User Two'
            }
        ],
        'participants': [
            {
                'user': {
                    'account_id': 'acc3',
                    'username': 'user3',
                    'display_name': 'User Three'
                }
            }
        ],
        'migratable': True,
        'migration_issues': []
    },
    {
        'id': 2,
        'title': 'Fix bug in module',
        'state': 'MERGED',
        'author': {
            'account_id': 'acc2',
            'username': 'user2',
            'display_name': 'User Two'
        },
        'source_branch': 'bugfix/critical-bug',
        'destination_branch': 'main',
        'created_on': '2024-01-15T09:00:00Z',
        'updated_on': '2024-01-20T16:45:00Z',
        'comment_count': 4,
        'commit_count': 3,
        'reviewers': [
            {
                'account_id': 'acc1',
                'username': 'user1',
                'display_name': 'User One'
            },
            {
                'account_id': 'acc3',
                'username': 'user3',
                'display_name': 'User Three'
            }
        ]
    },
    {
        'id': 3,
        'title': 'Update documentation',
        'state': 'DECLINED',
        'author': {
            'account_id': 'acc3',
            'username': 'user3',
            'display_name': 'User Three'
        },
        'source_branch': 'docs/update-readme',
        'destination_branch': 'main',
        'created_on': '2024-02-01T11:30:00Z',
        'updated_on': '2024-02-05T13:20:00Z',
        'comment_count': 1,
        'commit_count': 1,
        'reviewers': [
            {
                'account_id': 'acc1',
                'username': 'user1',
                'display_name': 'User One'
            }
        ]
    },
    {
        'id': 4,
        'title': 'Refactor codebase',
        'state': 'SUPERSEDED',
        'author': {
            'account_id': 'acc4',
            'username': 'user4',
            'display_name': 'User Four'
        },
        'source_branch': 'refactor/architecture',
        'destination_branch': 'main',
        'created_on': '2024-02-10T08:00:00Z',
        'updated_on': '2024-02-15T17:00:00Z',
        'comment_count': 3,
        'commit_count': 8,
        'reviewers': [
            {
                'account_id': 'acc1',
                'username': 'user1',
                'display_name': 'User One'
            },
            {
                'account_id': 'acc2',
                'username': 'user2',
                'display_name': 'User Two'
            }
        ]
    },
    {
        'id': 5,
        'title': 'Complex migration',
        'state': 'OPEN',
        'author': {
            'account_id': 'acc1',
            'username': 'user1',
            'display_name': 'User One'
        },
        'source_branch': 'complex/branch-with-issues',
        'destination_branch': 'main',
        'created_on': '2024-03-01T12:00:00Z',
        'comment_count': 0,
        'commit_count': 0,
        'migratable': False,
        'migration_issues': ['Missing source branch', 'Conflicting changes']
    }
]


# Sample attachments data for testing
SAMPLE_ATTACHMENTS = [
    {
        'issue_number': 1,
        'type': 'issue',
        'name': 'screenshot.png',
        'size': 1024 * 1024 * 2  # 2MB
    },
    {
        'issue_number': 1,
        'type': 'issue',
        'name': 'logfile.txt',
        'size': 512 * 1024  # 512KB
    },
    {
        'issue_number': 3,
        'type': 'issue',
        'name': 'document.pdf',
        'size': 1024 * 1024  # 1MB
    },
    {
        'issue_number': 3,
        'type': 'issue',
        'name': 'code_snippet.py',
        'size': 10 * 1024  # 10KB
    }
]


# Sample milestones data for testing
SAMPLE_MILESTONES = [
    'v1.0 Release',
    'v1.1 Release',
    'v2.0 Planning',
    'Bug Fix Sprint',
    'Feature Complete'
]


# Sample user list for testing
SAMPLE_USERS = [
    'User One',
    'User Two', 
    'User Three',
    'User Four',
    'Unknown (deleted user)'
]


# Sample gap data for testing
SAMPLE_GAPS = {
    'issues': {
        'gaps': [6, 7, 9, 10, 15, 16, 17, 18, 19, 20],
        'count': 10
    },
    'pull_requests': {
        'gaps': [6, 7, 8, 12, 13, 14],
        'count': 6
    }
}


# Sample PR migratability analysis for testing
SAMPLE_PR_ANALYSIS = {
    'fully_migratable': {
        'count': 1,
        'prs': [
            {
                'number': 1,
                'title': 'Add new feature',
                'state': 'OPEN',
                'source_branch': 'feature/new-feature',
                'can_migrate_as_pr': True,
                'issues': [],
                'data_preserved': {
                    'description': True,
                    'comments': True,
                    'commits': True,
                    'reviewers': True,
                    'diff': True
                }
            }
        ]
    },
    'partially_migratable': {
        'count': 3,
        'prs': [
            {
                'number': 2,
                'title': 'Fix bug in module',
                'state': 'MERGED',
                'source_branch': 'bugfix/critical-bug',
                'can_migrate_as_pr': True,
                'issues': [],
                'data_preserved': {
                    'description': True,
                    'comments': True,
                    'commits': True,
                    'reviewers': True,
                    'diff': True
                }
            },
            {
                'number': 3,
                'title': 'Update documentation',
                'state': 'DECLINED',
                'source_branch': 'docs/update-readme',
                'can_migrate_as_pr': True,
                'issues': [],
                'data_preserved': {
                    'description': True,
                    'comments': True,
                    'commits': True,
                    'reviewers': True,
                    'diff': True
                }
            },
            {
                'number': 4,
                'title': 'Refactor codebase',
                'state': 'SUPERSEDED',
                'source_branch': 'refactor/architecture',
                'can_migrate_as_pr': True,
                'issues': [],
                'data_preserved': {
                    'description': True,
                    'comments': True,
                    'commits': True,
                    'reviewers': True,
                    'diff': True
                }
            }
        ],
        'note': 'These PRs can be migrated as issues with PR metadata in description'
    },
    'migration_challenges': {
        'count': 1,
        'prs': [
            {
                'number': 5,
                'title': 'Complex migration',
                'state': 'OPEN',
                'source_branch': 'complex/branch-with-issues',
                'can_migrate_as_pr': False,
                'issues': ['Missing source branch', 'Conflicting changes'],
                'data_preserved': {
                    'description': True,
                    'comments': False,
                    'commits': False,
                    'reviewers': False,
                    'diff': False
                }
            }
        ]
    }
}


# Sample migration estimates for testing
SAMPLE_MIGRATION_ESTIMATES = {
    'placeholder_issues_needed': 10,
    'total_api_calls_estimate': 95,  # 5*3 + 5*2 + 10 + 4 = 39 + 10 + 10 + 4 = 63? Let's recalculate
    'estimated_time_minutes': 10.0,  # (5 issues + 5 PRs + 10 gaps) * 0.5 = 10
    'issues_count': 5,
    'prs_count': 5,
    'attachments_count': 4,
    'total_items': 14  # 5 + 5 + 4
}


# Sample repository structure analysis for testing
SAMPLE_STRUCTURE_ANALYSIS = {
    'issue_states': {'new': 2, 'resolved': 1, 'on_hold': 1, 'closed': 1},
    'pr_states': {'OPEN': 2, 'MERGED': 1, 'DECLINED': 1, 'SUPERSEDED': 1},
    'issue_date_range': {
        'first': '2024-01-01T10:00:00Z',
        'last': '2024-03-01T12:00:00Z'
    },
    'pr_date_range': {
        'first': '2024-01-05T10:00:00Z',
        'last': '2024-03-01T12:00:00Z'
    },
    'total_issues': 5,
    'total_prs': 5,
    'has_issues': True,
    'has_prs': True
}


# Sample migration strategy for testing
SAMPLE_MIGRATION_STRATEGY = {
    'recommended_approach': 'hybrid',
    'steps': [
        {
            'step': 1,
            'action': 'migrate_open_prs',
            'description': 'Migrate 1 open PRs as actual GitHub PRs',
            'count': 1
        },
        {
            'step': 2,
            'action': 'migrate_closed_prs_as_issues',
            'description': 'Migrate 3 closed PRs as GitHub issues',
            'count': 3,
            'note': 'Include original PR metadata, state, and links in description'
        },
        {
            'step': 3,
            'action': 'review_challenges',
            'description': 'Review 1 PRs with migration challenges',
            'count': 1,
            'note': 'May have missing branches or other issues requiring manual handling'
        },
        {
            'step': 4,
            'action': 'preserve_history',
            'description': 'All PR comments, commits, and history will be preserved in descriptions',
            'count': None
        }
    ]
}


# Sample complete audit report for testing
SAMPLE_AUDIT_REPORT = {
    'repository': {
        'workspace': 'test-workspace',
        'repo': 'test-repo',
        'audit_date': '2024-03-15T10:30:00'
    },
    'summary': {
        'total_issues': 5,
        'total_prs': 5,
        'total_users': 5,
        'total_attachments': 4,
        'total_attachment_size_mb': 3.54,
        'estimated_migration_time_minutes': 10.0
    },
    'issues': {
        'total': 5,
        'by_state': SAMPLE_STRUCTURE_ANALYSIS['issue_states'],
        'number_range': {'min': 1, 'max': 5},
        'gaps': SAMPLE_GAPS['issues'],
        'date_range': SAMPLE_STRUCTURE_ANALYSIS['issue_date_range'],
        'total_comments': 11,
        'with_attachments': 2,
        'types': {
            'total': 3,
            'list': ['bug', 'enhancement', 'task']
        }
    },
    'pull_requests': {
        'total': 5,
        'by_state': SAMPLE_STRUCTURE_ANALYSIS['pr_states'],
        'number_range': {'min': 1, 'max': 5},
        'gaps': SAMPLE_GAPS['pull_requests'],
        'date_range': SAMPLE_STRUCTURE_ANALYSIS['pr_date_range'],
        'total_comments': 10
    },
    'attachments': {
        'total': 4,
        'total_size_bytes': 3710976,  # 3.54 MB in bytes
        'total_size_mb': 3.54,
        'by_issue': 4
    },
    'users': {
        'total_unique': 5,
        'list': SAMPLE_USERS,
        'mappings': {
            'account_id_to_username': {
                'acc1': 'user1',
                'acc2': 'user2',
                'acc3': 'user3',
                'acc4': 'user4'
            },
            'username_to_account_id': {
                'user1': 'acc1',
                'user2': 'acc2',
                'user3': 'acc3',
                'user4': 'acc4'
            }
        }
    },
    'milestones': {
        'total': 5,
        'list': SAMPLE_MILESTONES
    },
    'migration_analysis': {
        'gaps': SAMPLE_GAPS,
        'pr_migration_analysis': SAMPLE_PR_ANALYSIS,
        'migration_strategy': SAMPLE_MIGRATION_STRATEGY,
        'estimates': SAMPLE_MIGRATION_ESTIMATES
    }
}


# Sample configuration data for testing
SAMPLE_CONFIG = {
    '_comment': 'Bitbucket to GitHub Multi-Repository Migration Configuration',
    '_instructions': {
        'step_1': 'Set BITBUCKET_TOKEN or BITBUCKET_API_TOKEN environment variable',
        'step_2': 'Set GITHUB_TOKEN environment variable',
        'step_3': 'Set github.owner to your GitHub username or organization',
        'step_4': 'Review and adjust repository mappings',
        'step_5': 'For each user in user_mapping set to their GitHub username',
        'step_6': 'Run dry-run first to validate configuration',
        'step_7': 'After dry-run succeeds, run actual migration'
    },
    'options': {
        'dry_run': False,
        'preserve_timestamps': True,
        'link_rewriting': {
            'enabled': True,
            'enable_notes': True,
            'enable_markdown_awareness': True
        }
    },
    'bitbucket': {
        'workspace': 'test-workspace',
        'email': 'test@example.com'
    },
    'github': {
        'owner': 'test-owner'
    },
    'base_dir': '/path/to/base',
    'repositories': [
        {
            'bitbucket_repo': 'repo1',
            'github_repo': 'repo1'
        },
        {
            'bitbucket_repo': 'repo2',
            'github_repo': 'repo2-renamed'
        }
    ],
    'external_repositories': [
        {
            'bitbucket_repo': 'external-repo',
            'github_repo': 'external-repo'
        }
    ],
    'user_mapping': {
        'User One': 'user1',
        'User Two': 'user2',
        'User Three': 'user3',
        'User Four': 'user4',
        'Unknown (deleted user)': None
    }
}


# Sample comments data for testing
SAMPLE_COMMENTS = [
    {
        'id': 1,
        'content': {'raw': 'This looks good @{557058:acc1}'},
        'created_on': '2024-01-01T10:00:00Z',
        'user': {
            'account_id': 'acc2',
            'username': 'user2',
            'display_name': 'User Two'
        }
    },
    {
        'id': 2,
        'content': {'raw': 'I disagree with this approach @{557058:acc3}'},
        'created_on': '2024-01-02T11:00:00Z',
        'user': {
            'account_id': 'acc1',
            'username': 'user1',
            'display_name': 'User One'
        }
    },
    {
        'id': 3,
        'content': {'raw': 'This needs more work.'},
        'created_on': '2024-01-03T12:00:00Z',
        'user': {
            'account_id': 'acc3',
            'username': 'user3',
            'display_name': 'User Three'
        }
    }
]


@pytest.fixture
def sample_repository_data():
    """Fixture providing sample repository data."""
    return SAMPLE_REPOSITORY_DATA.copy()


@pytest.fixture
def sample_issues():
    """Fixture providing sample issues data."""
    return SAMPLE_ISSUES.copy()


@pytest.fixture
def sample_pull_requests():
    """Fixture providing sample pull requests data."""
    return SAMPLE_PULL_REQUESTS.copy()


@pytest.fixture
def sample_attachments():
    """Fixture providing sample attachments data."""
    return SAMPLE_ATTACHMENTS.copy()


@pytest.fixture
def sample_milestones():
    """Fixture providing sample milestones data."""
    return SAMPLE_MILESTONES.copy()


@pytest.fixture
def sample_users():
    """Fixture providing sample users data."""
    return SAMPLE_USERS.copy()


@pytest.fixture
def sample_gaps():
    """Fixture providing sample gaps data."""
    return SAMPLE_GAPS.copy()


@pytest.fixture
def sample_pr_analysis():
    """Fixture providing sample PR analysis data."""
    return SAMPLE_PR_ANALYSIS.copy()


@pytest.fixture
def sample_migration_estimates():
    """Fixture providing sample migration estimates."""
    return SAMPLE_MIGRATION_ESTIMATES.copy()


@pytest.fixture
def sample_structure_analysis():
    """Fixture providing sample structure analysis."""
    return SAMPLE_STRUCTURE_ANALYSIS.copy()


@pytest.fixture
def sample_migration_strategy():
    """Fixture providing sample migration strategy."""
    return SAMPLE_MIGRATION_STRATEGY.copy()


@pytest.fixture
def sample_audit_report():
    """Fixture providing complete sample audit report."""
    return SAMPLE_AUDIT_REPORT.copy()


@pytest.fixture
def sample_config():
    """Fixture providing sample configuration data."""
    return SAMPLE_CONFIG.copy()


@pytest.fixture
def sample_comments():
    """Fixture providing sample comments data."""
    return SAMPLE_COMMENTS.copy()


@pytest.fixture
def mock_bitbucket_client():
    """Fixture providing mock Bitbucket client."""
    mock_client = Mock()
    
    # Setup default return values
    mock_client.get_issues.return_value = SAMPLE_ISSUES.copy()
    mock_client.get_pull_requests.return_value = SAMPLE_PULL_REQUESTS.copy()
    mock_client.get_milestones.return_value = [
        {'name': milestone} for milestone in SAMPLE_MILESTONES
    ]
    mock_client.get_comments.side_effect = lambda item_type, item_id: SAMPLE_COMMENTS.copy()
    mock_client.get_attachments.side_effect = lambda item_type, item_id: SAMPLE_ATTACHMENTS.copy()
    mock_client.get_user_info.return_value = {
        'username': 'api_user',
        'display_name': 'API User Display'
    }
    mock_client.list_repositories.return_value = [
        {'slug': 'repo1', 'name': 'Repository 1'},
        {'slug': 'repo2', 'name': 'Repository 2'}
    ]
    
    return mock_client


@pytest.fixture
def mock_user_mapper():
    """Fixture providing mock user mapper."""
    mock_mapper = Mock()
    mock_mapper.data.account_id_to_username = {
        'acc1': 'user1',
        'acc2': 'user2',
        'acc3': 'user3',
        'acc4': 'user4'
    }
    mock_mapper.data.account_id_to_display_name = {
        'acc1': 'User One',
        'acc2': 'User Two',
        'acc3': 'User Three',
        'acc4': 'User Four'
    }
    mock_mapper.build_account_id_mappings.return_value = 4
    mock_mapper.scan_comments_for_account_ids.return_value = None
    
    return mock_mapper


@pytest.fixture
def mock_base_dir_manager():
    """Fixture providing mock base directory manager."""
    mock_manager = Mock()
    mock_output_path = Mock()
    mock_output_path.__truediv__ = Mock(return_value=mock_output_path)
    
    mock_manager.ensure_subcommand_dir.return_value = mock_output_path
    mock_manager.get_config_path.return_value = Mock()
    mock_manager.create_file = Mock()
    
    return mock_manager


@pytest.fixture
def populated_auditor(sample_issues, sample_pull_requests, sample_attachments, 
                     sample_milestones, sample_users, mock_user_mapper, mock_base_dir_manager):
    """Fixture providing an Auditor instance with populated test data."""
    from bitbucket_migration.audit.auditor import Auditor
    
    auditor = Auditor(
        workspace='test-workspace',
        repo='test-repo',
        email='test@example.com',
        token='test-token',
        base_dir_manager=mock_base_dir_manager
    )
    
    # Populate with test data
    auditor.issues = sample_issues.copy()
    auditor.pull_requests = sample_pull_requests.copy()
    auditor.attachments = sample_attachments.copy()
    auditor.milestones = set(sample_milestones.copy())
    auditor.users = set(sample_users.copy())
    auditor.issue_types = {'bug', 'enhancement', 'task'}
    auditor.gaps = SAMPLE_GAPS.copy()
    auditor.pr_analysis = SAMPLE_PR_ANALYSIS.copy()
    auditor.migration_estimates = SAMPLE_MIGRATION_ESTIMATES.copy()
    auditor.report = SAMPLE_AUDIT_REPORT.copy()
    auditor.user_mapper = mock_user_mapper
    
    return auditor


@pytest.fixture
def empty_auditor(mock_base_dir_manager):
    """Fixture providing an empty Auditor instance."""
    from bitbucket_migration.audit.auditor import Auditor
    
    return Auditor(
        workspace='test-workspace',
        repo='test-repo',
        email='test@example.com',
        token='test-token',
        base_dir_manager=mock_base_dir_manager
    )