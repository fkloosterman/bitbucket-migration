"""
Tests for Auditor.

Tests the individual repository audit orchestrator including:
- Initialization and validation
- Data fetching and processing
- User mapping and analysis
- Report generation
- File saving functionality
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from bitbucket_migration.audit.auditor import Auditor
from bitbucket_migration.exceptions import ValidationError, APIError, AuthenticationError, NetworkError


class TestAuditorInitialization:
    """Test Auditor initialization and configuration."""
    
    def test_init_with_valid_params(self):
        """Test successful initialization with valid parameters."""
        auditor = Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
        
        assert auditor.workspace == "test-workspace"
        assert auditor.repo == "test-repo"
        assert auditor.email == "test@example.com"
        assert auditor.token == "test-token"
        assert auditor.environment is not None
        assert auditor.base_dir_manager is not None
        assert auditor.audit_utils is not None
    
    def test_init_empty_workspace_raises_error(self):
        """Test that empty workspace raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket workspace cannot be empty"):
            Auditor(workspace="", repo="test-repo", email="test@example.com", token="test-token")
    
    def test_init_whitespace_only_workspace_raises_error(self):
        """Test that whitespace-only workspace raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket workspace cannot be empty"):
            Auditor(workspace="   ", repo="test-repo", email="test@example.com", token="test-token")
    
    def test_init_empty_repo_raises_error(self):
        """Test that empty repo raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket repository cannot be empty"):
            Auditor(workspace="test-workspace", repo="", email="test@example.com", token="test-token")
    
    def test_init_empty_email_raises_error(self):
        """Test that empty email raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket email cannot be empty"):
            Auditor(workspace="test-workspace", repo="test-repo", email="", token="test-token")
    
    def test_init_empty_token_raises_error(self):
        """Test that empty token raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket token cannot be empty"):
            Auditor(workspace="test-workspace", repo="test-repo", email="test@example.com", token="")
    
    def test_init_with_custom_base_dir_manager(self):
        """Test initialization with custom BaseDirManager."""
        mock_base_dir_manager = MagicMock()
        
        auditor = Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token",
            base_dir_manager=mock_base_dir_manager
        )
        
        assert auditor.base_dir_manager == mock_base_dir_manager


class TestDataFetching:
    """Test data fetching functionality."""
    
    @pytest.fixture
    def auditor(self):
        """Create Auditor for testing."""
        return Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('bitbucket_migration.audit.auditor.BitbucketClient')
    def test_fetch_data_complete_flow(self, mock_bb_client_class, auditor):
        """Test complete data fetching flow."""
        # Mock Bitbucket client
        mock_client = Mock()
        mock_bb_client_class.return_value = mock_client
        
        # Mock data
        mock_client.get_issues.return_value = [
            {'id': 1, 'title': 'Issue 1', 'state': 'new', 'kind': 'bug', 'reporter': {'display_name': 'User 1'}},
            {'id': 2, 'title': 'Issue 2', 'state': 'resolved', 'kind': 'enhancement', 'reporter': {'display_name': 'User 2'}}
        ]
        
        mock_client.get_pull_requests.return_value = [
            {'id': 1, 'title': 'PR 1', 'state': 'OPEN', 'author': {'display_name': 'User 1'}},
            {'id': 2, 'title': 'PR 2', 'state': 'MERGED', 'author': {'display_name': 'User 3'}}
        ]
        
        mock_client.get_milestones.return_value = [
            {'name': 'Milestone 1'},
            {'name': 'Milestone 2'}
        ]
        
        # Mock attachments
        mock_client.get_attachments.side_effect = [
            [{'name': 'file1.txt', 'size': 1024}],
            [{'name': 'file2.txt', 'size': 2048}]
        ]
        
        # Re-initialize with mocked client
        auditor.bb_client = mock_client
        auditor.environment.clients.bb = mock_client
        
        # Test fetching
        auditor._fetch_data()
        
        # Verify data was fetched
        assert len(auditor.issues) == 2
        assert len(auditor.pull_requests) == 2
        assert len(auditor.milestones) == 2
        assert len(auditor.attachments) == 2
        assert len(auditor.issue_types) == 2
        
        # Verify users were collected
        assert 'User 1' in auditor.users
        assert 'User 2' in auditor.users
        assert 'User 3' in auditor.users
    
    @patch('bitbucket_migration.audit.auditor.BitbucketClient')
    def test_fetch_data_milestones_error_handling(self, mock_bb_client_class, auditor):
        """Test milestone fetching error handling."""
        # Mock Bitbucket client
        mock_client = Mock()
        mock_bb_client_class.return_value = mock_client
        
        # Mock successful data
        mock_client.get_issues.return_value = []
        mock_client.get_pull_requests.return_value = []
        mock_client.get_milestones.side_effect = Exception("API Error")
        
        # Re-initialize with mocked client
        auditor.bb_client = mock_client
        auditor.environment.clients.bb = mock_client
        
        # Test fetching
        auditor._fetch_data()
        
        # Milestones should be empty set due to error
        assert auditor.milestones == set()
    
    def test_collect_users_with_all_fields(self, auditor):
        """Test user collection with all user fields."""
        issues = [
            {
                'id': 1,
                'reporter': {'display_name': 'Reporter User'},
                'assignee': {'display_name': 'Assignee User'}
            }
        ]
        
        pull_requests = [
            {
                'id': 1,
                'author': {'display_name': 'Author User'},
                'participants': [
                    {'user': {'display_name': 'Participant User'}}
                ],
                'reviewers': [
                    {'display_name': 'Reviewer User'}
                ]
            }
        ]
        
        auditor.issues = issues
        auditor.pull_requests = pull_requests
        
        auditor._collect_users()
        
        expected_users = {'Reporter User', 'Assignee User', 'Author User', 'Participant User', 'Reviewer User'}
        assert auditor.users == expected_users
    
    def test_collect_users_missing_fields(self, auditor):
        """Test user collection with missing fields."""
        issues = [
            {
                'id': 1
                # No reporter or assignee
            }
        ]
        
        pull_requests = [
            {
                'id': 1
                # No author, participants, or reviewers
            }
        ]
        
        auditor.issues = issues
        auditor.pull_requests = pull_requests
        
        auditor._collect_users()
        
        # Should only have the default "Unknown (deleted user)"
        assert auditor.users == {'Unknown (deleted user)'}


class TestUserMapping:
    """Test user mapping functionality."""
    
    @pytest.fixture
    def auditor(self):
        """Create Auditor for testing."""
        return Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    def test_build_user_mappings(self, auditor):
        """Test building user mappings."""
        issues = [
            {
                'id': 1,
                'reporter': {'account_id': 'acc1', 'username': 'user1', 'display_name': 'User 1'}
            }
        ]
        
        pull_requests = []
        
        # Set up the auditor with the test data
        auditor.issues = issues
        auditor.pull_requests = pull_requests
        
        # Mock user mapper
        mock_user_mapper = MagicMock()
        auditor.user_mapper = mock_user_mapper
        
        auditor._build_user_mappings()
        
        # Verify user mapper methods were called with auditor's data
        mock_user_mapper.build_account_id_mappings.assert_called_once_with(issues, pull_requests)
        mock_user_mapper.scan_comments_for_account_ids.assert_called_once_with(issues, pull_requests)
    
    def test_build_user_mappings_empty_data(self, auditor):
        """Test building user mappings with empty data."""
        issues = []
        pull_requests = []
        
        # Mock user mapper
        mock_user_mapper = MagicMock()
        auditor.user_mapper = mock_user_mapper
        
        auditor._build_user_mappings()
        
        # Verify user mapper methods were called with empty data
        mock_user_mapper.build_account_id_mappings.assert_called_once_with(issues, pull_requests)
        mock_user_mapper.scan_comments_for_account_ids.assert_called_once_with(issues, pull_requests)


class TestStructureAnalysis:
    """Test repository structure analysis."""
    
    @pytest.fixture
    def auditor(self):
        """Create Auditor for testing."""
        return Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    def test_analyze_structure_with_data(self, auditor):
        """Test structure analysis with sample data."""
        # Setup test data
        auditor.issues = [
            {'id': 1, 'state': 'new'},
            {'id': 2, 'state': 'resolved'},
            {'id': 3, 'state': 'new'}
        ]
        
        auditor.pull_requests = [
            {'id': 1, 'state': 'OPEN'},
            {'id': 2, 'state': 'MERGED'}
        ]
        
        auditor.attachments = [
            {'size': 1024, 'type': 'issue'},
            {'size': 2048, 'type': 'issue'}
        ]
        
        auditor.issue_types = {'bug', 'enhancement'}
        auditor.milestones = {'Milestone 1', 'Milestone 2'}
        
        # Mock user mapper
        mock_user_mapper = MagicMock()
        mock_user_mapper.data.account_id_to_username = {'acc1': 'user1'}
        auditor.user_mapper = mock_user_mapper
        
        # Mock audit utils
        with patch.object(auditor, 'audit_utils') as mock_audit_utils:
            mock_audit_utils.analyze_gaps.side_effect = [
                ([1, 3], 2),  # Issue gaps
                ([], 0)       # PR gaps (no gaps)
            ]
            mock_audit_utils.analyze_pr_migratability.return_value = {
                'fully_migratable': {'count': 1},
                'partially_migratable': {'count': 1},
                'migration_challenges': {'count': 0}
            }
            mock_audit_utils.calculate_migration_estimates.return_value = {
                'estimated_time_minutes': 15.0,
                'placeholder_issues_needed': 2,
                'total_api_calls_estimate': 10,
                'issues_count': 3,
                'prs_count': 2,
                'attachments_count': 2,
                'total_items': 7
            }
            mock_audit_utils.analyze_repository_structure.return_value = {
                'issue_states': {'new': 2, 'resolved': 1},
                'pr_states': {'OPEN': 1, 'MERGED': 1},
                'issue_date_range': {'first': '2024-01-01', 'last': '2024-01-10'},
                'pr_date_range': {'first': '2024-01-02', 'last': '2024-01-08'},
                'total_issues': 3,
                'total_prs': 2,
                'has_issues': True,
                'has_prs': True
            }
            mock_audit_utils.generate_migration_strategy.return_value = {
                'recommended_approach': 'hybrid',
                'steps': [
                    {'action': 'migrate_open_prs', 'count': 1},
                    {'action': 'migrate_closed_prs_as_issues', 'count': 1}
                ]
            }
            
            auditor._analyze_structure()
        
        # Verify analysis was performed
        assert auditor.gaps is not None
        assert auditor.pr_analysis is not None
        assert auditor.migration_estimates is not None
    
    def test_analyze_structure_empty_data(self, auditor):
        """Test structure analysis with empty data."""
        # Mock audit utils
        with patch.object(auditor, 'audit_utils') as mock_audit_utils:
            mock_audit_utils.analyze_gaps.side_effect = [
                ([], 0),  # No issue gaps
                ([], 0)   # No PR gaps
            ]
            mock_audit_utils.analyze_pr_migratability.return_value = {
                'fully_migratable': {'count': 0},
                'partially_migratable': {'count': 0},
                'migration_challenges': {'count': 0}
            }
            mock_audit_utils.calculate_migration_estimates.return_value = {
                'estimated_time_minutes': 0.0,
                'placeholder_issues_needed': 0,
                'total_api_calls_estimate': 0,
                'issues_count': 0,
                'prs_count': 0,
                'attachments_count': 0,
                'total_items': 0
            }
            mock_audit_utils.analyze_repository_structure.return_value = {
                'issue_states': {},
                'pr_states': {},
                'issue_date_range': {'first': None, 'last': None},
                'pr_date_range': {'first': None, 'last': None},
                'total_issues': 0,
                'total_prs': 0,
                'has_issues': False,
                'has_prs': False
            }
            mock_audit_utils.generate_migration_strategy.return_value = {
                'recommended_approach': 'issues_only',
                'steps': []
            }
            
            auditor._analyze_structure()
        
        # Verify analysis was performed even with empty data
        assert auditor.gaps is not None
        assert auditor.pr_analysis is not None
        assert auditor.migration_estimates is not None


class TestReportGeneration:
    """Test report generation functionality."""
    
    @pytest.fixture
    def auditor(self):
        """Create Auditor for testing."""
        return Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    def test_generate_report_complete(self, auditor):
        """Test complete report generation."""
        # Setup test data
        auditor.issues = [
            {'id': 1, 'title': 'Issue 1', 'state': 'new', 'kind': 'bug', 'reporter': {'display_name': 'User 1'}}
        ]
        
        auditor.pull_requests = [
            {'id': 1, 'title': 'PR 1', 'state': 'OPEN', 'author': {'display_name': 'User 1'}}
        ]
        
        auditor.attachments = [
            {'name': 'file1.txt', 'size': 1024, 'type': 'issue', 'issue_number': 1}
        ]
        
        auditor.issue_types = {'bug'}
        auditor.milestones = {'Milestone 1'}
        auditor.users = {'User 1', 'User 2'}
        
        auditor.gaps = {'issues': {'gaps': [2], 'count': 1}, 'pull_requests': {'gaps': [], 'count': 0}}
        auditor.pr_analysis = {
            'fully_migratable': {'count': 1, 'prs': []},
            'partially_migratable': {'count': 0, 'prs': []},
            'migration_challenges': {'count': 0, 'prs': []}
        }
        auditor.migration_estimates = {
            'estimated_time_minutes': 5.0,
            'placeholder_issues_needed': 1,
            'total_api_calls_estimate': 5,
            'issues_count': 1,
            'prs_count': 1,
            'attachments_count': 1,
            'total_items': 3
        }
        
        # Mock user mapper
        mock_user_mapper = MagicMock()
        mock_user_mapper.data.account_id_to_username = {'acc1': 'user1'}
        auditor.user_mapper = mock_user_mapper
        
        # Mock audit utils
        with patch.object(auditor, 'audit_utils') as mock_audit_utils:
            mock_audit_utils.analyze_repository_structure.return_value = {
                'issue_states': {'new': 1},
                'pr_states': {'OPEN': 1},
                'issue_date_range': {'first': None, 'last': None},
                'pr_date_range': {'first': None, 'last': None},
                'total_issues': 1,
                'total_prs': 1,
                'has_issues': True,
                'has_prs': True
            }
            mock_audit_utils.generate_migration_strategy.return_value = {
                'recommended_approach': 'hybrid',
                'steps': [
                    {'action': 'migrate_open_prs', 'count': 1}
                ]
            }
            
            report = auditor._generate_report()
        
        # Verify report structure
        assert 'repository' in report
        assert 'summary' in report
        assert 'issues' in report
        assert 'pull_requests' in report
        assert 'attachments' in report
        assert 'users' in report
        assert 'milestones' in report
        assert 'migration_analysis' in report
        
        # Verify report content
        assert report['repository']['workspace'] == 'test-workspace'
        assert report['repository']['repo'] == 'test-repo'
        assert report['summary']['total_issues'] == 1
        assert report['summary']['total_prs'] == 1
        assert report['summary']['total_users'] == 2
        assert report['summary']['total_attachments'] == 1
        assert report['summary']['estimated_migration_time_minutes'] == 5.0
    
    def test_generate_report_empty_data(self, auditor):
        """Test report generation with empty data."""
        # Setup empty data
        auditor.issues = []
        auditor.pull_requests = []
        auditor.attachments = []
        auditor.issue_types = set()
        auditor.milestones = set()
        auditor.users = set()
        auditor.gaps = {'issues': {'gaps': [], 'count': 0}, 'pull_requests': {'gaps': [], 'count': 0}}
        auditor.pr_analysis = {
            'fully_migratable': {'count': 0, 'prs': []},
            'partially_migratable': {'count': 0, 'prs': []},
            'migration_challenges': {'count': 0, 'prs': []}
        }
        auditor.migration_estimates = {
            'estimated_time_minutes': 0.0,
            'placeholder_issues_needed': 0,
            'total_api_calls_estimate': 0,
            'issues_count': 0,
            'prs_count': 0,
            'attachments_count': 0,
            'total_items': 0
        }
        
        # Mock user mapper
        mock_user_mapper = MagicMock()
        mock_user_mapper.data.account_id_to_username = {}
        auditor.user_mapper = mock_user_mapper
        
        # Mock audit utils
        with patch.object(auditor, 'audit_utils') as mock_audit_utils:
            mock_audit_utils.analyze_repository_structure.return_value = {
                'issue_states': {},
                'pr_states': {},
                'issue_date_range': {'first': None, 'last': None},
                'pr_date_range': {'first': None, 'last': None},
                'total_issues': 0,
                'total_prs': 0,
                'has_issues': False,
                'has_prs': False
            }
            mock_audit_utils.generate_migration_strategy.return_value = {
                'recommended_approach': 'issues_only',
                'steps': []
            }
            
            report = auditor._generate_report()
        
        # Verify report structure
        assert 'repository' in report
        assert 'summary' in report
        assert 'issues' in report
        assert 'pull_requests' in report
        assert 'attachments' in report
        assert 'users' in report
        assert 'milestones' in report
        assert 'migration_analysis' in report
        
        # Verify empty report content
        assert report['summary']['total_issues'] == 0
        assert report['summary']['total_prs'] == 0
        assert report['summary']['total_users'] == 0
        assert report['summary']['total_attachments'] == 0


class TestRunAudit:
    """Test the main audit execution flow."""
    
    @pytest.fixture
    def auditor(self):
        """Create Auditor for testing."""
        return Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    def test_run_audit_success(self, auditor):
        """Test successful audit execution."""
        # Mock the internal methods
        with patch.object(auditor, '_fetch_data') as mock_fetch, \
             patch.object(auditor, '_build_user_mappings') as mock_build, \
             patch.object(auditor, '_analyze_structure') as mock_analyze, \
             patch.object(auditor, '_generate_report') as mock_generate:
            
            mock_generate.return_value = {'status': 'success', 'issues': 10}
            
            # Run audit
            report = auditor.run_audit()
        
        # Verify all methods were called
        mock_fetch.assert_called_once()
        mock_build.assert_called_once()
        mock_analyze.assert_called_once()
        mock_generate.assert_called_once()
        
        # Verify report
        assert report == {'status': 'success', 'issues': 10}
    
    def test_run_audit_api_error(self, auditor):
        """Test audit execution with API error."""
        with patch.object(auditor, '_fetch_data', side_effect=APIError("API Error")):
            with pytest.raises(APIError):
                auditor.run_audit()
    
    def test_run_audit_auth_error(self, auditor):
        """Test audit execution with authentication error."""
        with patch.object(auditor, '_fetch_data', side_effect=AuthenticationError("Auth Error")):
            with pytest.raises(AuthenticationError):
                auditor.run_audit()
    
    def test_run_audit_network_error(self, auditor):
        """Test audit execution with network error."""
        with patch.object(auditor, '_fetch_data', side_effect=NetworkError("Network Error")):
            with pytest.raises(NetworkError):
                auditor.run_audit()
    
    def test_run_audit_generic_error(self, auditor):
        """Test audit execution with generic error."""
        with patch.object(auditor, '_fetch_data', side_effect=Exception("Generic Error")):
            with pytest.raises(Exception):
                auditor.run_audit()


class TestReportSaving:
    """Test report saving functionality."""
    
    @pytest.fixture
    def auditor(self):
        """Create Auditor for testing."""
        return Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    def test_save_reports_success(self, auditor):
        """Test successful report saving."""
        # Setup test data
        auditor.report = {
            'repository': {'workspace': 'test-workspace', 'repo': 'test-repo'},
            'summary': {'total_issues': 5}
        }
        
        auditor.issues = [
            {'id': 1, 'title': 'Issue 1'},
            {'id': 2, 'title': 'Issue 2'}
        ]
        
        auditor.pull_requests = [
            {'id': 1, 'title': 'PR 1'},
            {'id': 2, 'title': 'PR 2'}
        ]
        
        # Mock base_dir_manager
        mock_base_dir_manager = MagicMock()
        mock_output_path = MagicMock()
        mock_output_path.__truediv__ = Mock(return_value=mock_output_path)
        
        mock_base_dir_manager.ensure_subcommand_dir.return_value = mock_output_path
        mock_base_dir_manager.create_file = Mock()
        
        auditor.base_dir_manager = mock_base_dir_manager
        
        # Mock markdown generation
        with patch.object(auditor, '_generate_markdown_report', return_value="# Test Report\n"):
            auditor.save_reports()
        
        # Verify base_dir_manager methods were called
        mock_base_dir_manager.ensure_subcommand_dir.assert_called_once_with(
            'audit', 'test-workspace', 'test-repo'
        )
        
        # Verify create_file calls
        assert mock_base_dir_manager.create_file.call_count == 4  # JSON report, MD report, issues, PRs
    
    def test_save_reports_no_report_data(self, auditor):
        """Test saving with no report data."""
        auditor.report = None
        auditor.issues = []
        auditor.pull_requests = []
        
        # Mock base_dir_manager
        mock_base_dir_manager = MagicMock()
        auditor.base_dir_manager = mock_base_dir_manager
        
        auditor.save_reports()
        
        # No files should be saved
        mock_base_dir_manager.create_file.assert_not_called()
    
    def test_save_reports_empty_data(self, auditor):
        """Test saving with empty data."""
        # Setup a proper report structure
        auditor.report = {
            'repository': {
                'workspace': 'test-workspace',
                'repo': 'test-repo',
                'audit_date': '2024-01-01T10:00:00Z'
            },
            'summary': {
                'total_issues': 0,
                'total_prs': 0,
                'total_users': 0,
                'total_attachments': 0,
                'total_attachment_size_mb': 0,
                'estimated_migration_time_minutes': 0
            }
        }
        auditor.issues = []
        auditor.pull_requests = []
        
        # Mock base_dir_manager
        mock_base_dir_manager = MagicMock()
        mock_output_path = MagicMock()
        mock_output_path.__truediv__ = Mock(return_value=mock_output_path)
        
        mock_base_dir_manager.ensure_subcommand_dir.return_value = mock_output_path
        mock_base_dir_manager.create_file = Mock()
        
        auditor.base_dir_manager = mock_base_dir_manager
        
        # Mock markdown generation
        with patch.object(auditor, '_generate_markdown_report', return_value="# Test Report\n"):
            auditor.save_reports()
        
        # Only report files should be saved (not empty data files)
        assert mock_base_dir_manager.create_file.call_count == 2  # JSON and MD reports only


class TestMarkdownReportGeneration:
    """Test markdown report generation."""
    
    @pytest.fixture
    def auditor(self):
        """Create Auditor for testing."""
        return Auditor(
            workspace="test-workspace",
            repo="test-repo",
            email="test@example.com",
            token="test-token"
        )
    
    def test_generate_markdown_report_complete(self, auditor):
        """Test complete markdown report generation."""
        report = {
            'repository': {
                'audit_date': '2024-01-01T10:00:00Z',
                'workspace': 'test-workspace',
                'repo': 'test-repo'
            },
            'summary': {
                'total_issues': 5,
                'total_prs': 3,
                'total_users': 4,
                'total_attachments': 2,
                'total_attachment_size_mb': 1.5,
                'estimated_migration_time_minutes': 10.0
            },
            'issues': {
                'total': 5,
                'by_state': {'new': 2, 'resolved': 3},
                'number_range': {'min': 1, 'max': 10},
                'gaps': {'gaps': [6, 8], 'count': 2},
                'date_range': {'first': '2024-01-01', 'last': '2024-01-10'},
                'total_comments': 8,
                'with_attachments': 2,
                'types': {
                    'total': 2,
                    'list': ['bug', 'enhancement']
                }
            },
            'pull_requests': {
                'total': 3,
                'by_state': {'OPEN': 1, 'MERGED': 2},
                'number_range': {'min': 1, 'max': 5},
                'gaps': {'gaps': [3], 'count': 1},
                'date_range': {'first': '2024-01-05', 'last': '2024-01-15'},
                'total_comments': 5
            },
            'attachments': {
                'total': 2,
                'total_size_bytes': 1572864,
                'total_size_mb': 1.5,
                'by_issue': 2
            },
            'users': {
                'total_unique': 4,
                'list': ['User 1', 'User 2', 'User 3', 'User 4'],
                'mappings': {
                    'account_id_to_username': {'acc1': 'user1'},
                    'username_to_account_id': {'user1': 'acc1'}
                }
            },
            'milestones': {
                'total': 2,
                'list': ['Milestone 1', 'Milestone 2']
            },
            'migration_analysis': {
                'gaps': {'issues': {'count': 2}, 'pull_requests': {'count': 1}},
                'pr_migration_analysis': {
                    'fully_migratable': {'count': 1},
                    'partially_migratable': {'count': 1},
                    'migration_challenges': {'count': 0}
                },
                'migration_strategy': {
                    'recommended_approach': 'hybrid',
                    'steps': [
                        {'action': 'migrate_open_prs', 'count': 1}
                    ]
                },
                'estimates': {
                    'estimated_time_minutes': 10.0
                }
            }
        }
        
        markdown = auditor._generate_markdown_report(report)
        
        # Verify markdown content
        assert '# Bitbucket Repository Audit Report' in markdown
        assert '**Audit Date:** 2024-01-01T10:00:00Z' in markdown
        assert '**Repository:** test-workspace/test-repo' in markdown
        assert '**Total Issues:** 5' in markdown
        assert '**Total Pull Requests:** 3' in markdown
        assert '**Total Users:** 4' in markdown
        assert '**Total Attachments:** 2 (1.5 MB)' in markdown
        assert '**Estimated Migration Time:** 10.0 minutes' in markdown
        
        # Verify section headers
        assert '## Table of Contents' in markdown
        assert '## Issues Analysis' in markdown
        assert '## Pull Requests Analysis' in markdown
        assert '## Attachments' in markdown
        assert '## Users' in markdown
        assert '## Milestones' in markdown
        assert '## Migration Analysis' in markdown
    
    def test_generate_markdown_report_empty(self, auditor):
        """Test markdown report generation with empty data."""
        report = {
            'repository': {
                'audit_date': '2024-01-01T10:00:00Z',
                'workspace': 'test-workspace',
                'repo': 'test-repo'
            },
            'summary': {
                'total_issues': 0,
                'total_prs': 0,
                'total_users': 0,
                'total_attachments': 0,
                'total_attachment_size_mb': 0,
                'estimated_migration_time_minutes': 0
            },
            'issues': {
                'total': 0,
                'by_state': {},
                'number_range': {'min': 0, 'max': 0},
                'gaps': {'gaps': [], 'count': 0},
                'date_range': {'first': None, 'last': None},
                'total_comments': 0,
                'with_attachments': 0,
                'types': {
                    'total': 0,
                    'list': []
                }
            },
            'pull_requests': {
                'total': 0,
                'by_state': {},
                'number_range': {'min': 0, 'max': 0},
                'gaps': {'gaps': [], 'count': 0},
                'date_range': {'first': None, 'last': None},
                'total_comments': 0
            },
            'attachments': {
                'total': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'by_issue': 0
            },
            'users': {
                'total_unique': 0,
                'list': [],
                'mappings': {
                    'account_id_to_username': {},
                    'username_to_account_id': {}
                }
            },
            'milestones': {
                'total': 0,
                'list': []
            },
            'migration_analysis': {
                'gaps': {'issues': {'count': 0}, 'pull_requests': {'count': 0}},
                'pr_migration_analysis': {
                    'fully_migratable': {'count': 0},
                    'partially_migratable': {'count': 0},
                    'migration_challenges': {'count': 0}
                },
                'migration_strategy': {
                    'recommended_approach': 'issues_only',
                    'steps': []
                },
                'estimates': {
                    'estimated_time_minutes': 0
                }
            }
        }
        
        markdown = auditor._generate_markdown_report(report)
        
        # Verify basic structure
        assert '# Bitbucket Repository Audit Report' in markdown
        assert '**Total Issues:** 0' in markdown
        assert '**Total Pull Requests:** 0' in markdown