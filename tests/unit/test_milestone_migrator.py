"""
Unit tests for MilestoneMigrator.

Tests the milestone migration logic including:
- Milestone creation and duplicate detection
- Date formatting and conversion
- Error handling for API failures
- State management
"""

from unittest.mock import MagicMock, Mock, patch
from typing import Dict, Any, List
import pytest

from bitbucket_migration.migration.milestone_migrator import MilestoneMigrator
from bitbucket_migration.exceptions import APIError, AuthenticationError, NetworkError, ValidationError


@pytest.fixture
def mock_environment():
    """Create a mock MigrationEnvironment for testing."""
    env = MagicMock()
    env.logger = MagicMock()
    
    # Mock clients
    env.clients = MagicMock()
    env.clients.gh = MagicMock()
    env.clients.bb = MagicMock()
    
    return env


@pytest.fixture
def mock_state():
    """Create a mock MigrationState for testing."""
    state = MagicMock()
    state.mappings = MagicMock()
    state.mappings.milestones = {}
    state.milestone_records = []
    
    return state


@pytest.fixture
def milestone_migrator(mock_environment, mock_state):
    """Create a MilestoneMigrator instance for testing."""
    return MilestoneMigrator(mock_environment, mock_state)


class TestMilestoneMigratorInitialization:
    """Test MilestoneMigrator initialization."""
    
    def test_init_success(self, mock_environment, mock_state):
        """Test successful initialization."""
        migrator = MilestoneMigrator(mock_environment, mock_state)
        
        assert migrator.environment == mock_environment
        assert migrator.state == mock_state


class TestMigrateMilestones:
    """Test migrate_milestones method."""
    
    def test_migrate_empty_list(self, milestone_migrator, mock_environment):
        """Test migrating when no milestones exist."""
        mock_environment.clients.bb.get_milestones.return_value = []
        
        result = milestone_migrator.migrate_milestones()
        
        assert result == {}
        milestone_migrator.environment.logger.info.assert_any_call("  No milestones to migrate")
    
    def test_migrate_single_milestone(self, milestone_migrator, mock_environment, mock_state):
        """Test migrating a single milestone."""
        bb_milestones = [
            {
                'name': 'v1.0',
                'description': 'First release',
                'state': 'open',
                'due_on': '2024-12-31T23:59:59Z'
            }
        ]
        
        gh_milestone = {
            'number': 1,
            'title': 'v1.0',
            'state': 'open',
            'description': 'First release',
            'due_on': '2024-12-31T23:59:59Z'
        }
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.return_value = []
        mock_environment.clients.gh.create_milestone.return_value = gh_milestone
        
        result = milestone_migrator.migrate_milestones()
        
        assert 'v1.0' in result
        assert result['v1.0']['number'] == 1
        assert len(mock_state.milestone_records) == 1
        mock_environment.clients.gh.create_milestone.assert_called_once()
    
    def test_migrate_duplicate_milestone(self, milestone_migrator, mock_environment, mock_state):
        """Test detecting and reusing existing milestone."""
        bb_milestones = [
            {'name': 'v1.0', 'state': 'open', 'description': 'Release'}
        ]
        
        existing_gh_milestones = [
            {'number': 1, 'title': 'v1.0', 'state': 'open', 'description': 'Existing'}
        ]
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.return_value = existing_gh_milestones
        
        result = milestone_migrator.migrate_milestones()
        
        # Should reuse existing milestone, not create new one
        assert 'v1.0' in result
        assert result['v1.0']['number'] == 1
        mock_environment.clients.gh.create_milestone.assert_not_called()
        
        # Verify duplicate flag in record
        assert len(mock_state.milestone_records) == 1
        assert mock_state.milestone_records[0]['is_duplicate'] is True
    
    def test_migrate_milestone_no_name(self, milestone_migrator, mock_environment):
        """Test handling milestone with no name."""
        bb_milestones = [
            {'description': 'No name milestone', 'state': 'open'}
        ]
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.return_value = []
        
        result = milestone_migrator.migrate_milestones()
        
        # Should skip milestone without name
        assert result == {}
        mock_environment.clients.gh.create_milestone.assert_not_called()
    
    def test_migrate_with_open_milestones_only(self, milestone_migrator, mock_environment):
        """Test open_milestones_only filter."""
        bb_milestones = [
            {'name': 'v1.0', 'state': 'open'},
            {'name': 'v0.9', 'state': 'closed'}
        ]
        
        gh_milestone = {'number': 1, 'title': 'v1.0', 'state': 'open'}
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.return_value = []
        mock_environment.clients.gh.create_milestone.return_value = gh_milestone
        
        result = milestone_migrator.migrate_milestones(open_milestones_only=True)
        
        # Should only migrate open milestone
        assert 'v1.0' in result
        assert 'v0.9' not in result
        mock_environment.clients.gh.create_milestone.assert_called_once()
    
    def test_migrate_bb_fetch_error(self, milestone_migrator, mock_environment):
        """Test handling error when fetching Bitbucket milestones."""
        mock_environment.clients.bb.get_milestones.side_effect = APIError("API error")
        
        result = milestone_migrator.migrate_milestones()
        
        assert result == {}
        milestone_migrator.environment.logger.warning.assert_called()
    
    def test_migrate_gh_fetch_error(self, milestone_migrator, mock_environment):
        """Test handling error when fetching GitHub milestones."""
        bb_milestones = [{'name': 'v1.0', 'state': 'open'}]
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.side_effect = APIError("API error")
        mock_environment.clients.gh.create_milestone.return_value = {
            'number': 1, 'title': 'v1.0', 'state': 'open'
        }
        
        result = milestone_migrator.migrate_milestones()
        
        # Should continue with creation despite error fetching existing
        assert 'v1.0' in result
        mock_environment.clients.gh.create_milestone.assert_called_once()
    
    def test_migrate_creation_error(self, milestone_migrator, mock_environment, mock_state):
        """Test handling error when creating milestone."""
        bb_milestones = [{'name': 'v1.0', 'state': 'open'}]
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.return_value = []
        mock_environment.clients.gh.create_milestone.side_effect = ValidationError("Invalid data")
        
        result = milestone_migrator.migrate_milestones()
        
        # Should log error and record failure
        assert 'v1.0' not in result
        assert len(mock_state.milestone_records) == 1
        assert mock_state.milestone_records[0]['gh_number'] is None
        assert 'Failed to create' in mock_state.milestone_records[0]['remarks'][0]


class TestCheckDuplicate:
    """Test _check_duplicate method."""
    
    def test_check_duplicate_found(self, milestone_migrator):
        """Test finding a duplicate milestone."""
        existing_milestones = [
            {'number': 1, 'title': 'v1.0', 'state': 'open'},
            {'number': 2, 'title': 'v2.0', 'state': 'open'}
        ]
        
        result = milestone_migrator._check_duplicate('v1.0', existing_milestones)
        
        assert result is not None
        assert result['number'] == 1
    
    def test_check_duplicate_not_found(self, milestone_migrator):
        """Test when no duplicate exists."""
        existing_milestones = [
            {'number': 1, 'title': 'v1.0', 'state': 'open'}
        ]
        
        result = milestone_migrator._check_duplicate('v2.0', existing_milestones)
        
        assert result is None
    
    def test_check_duplicate_empty_list(self, milestone_migrator):
        """Test checking against empty list."""
        result = milestone_migrator._check_duplicate('v1.0', [])
        
        assert result is None


class TestCreateMilestone:
    """Test _create_milestone method."""
    
    def test_create_milestone_success(self, milestone_migrator, mock_environment):
        """Test successful milestone creation."""
        bb_milestone = {
            'name': 'v1.0',
            'description': 'First release',
            'state': 'open',
            'due_on': '2024-12-31T23:59:59Z'
        }
        
        gh_milestone = {
            'number': 1,
            'title': 'v1.0',
            'state': 'open',
            'description': 'First release',
            'due_on': '2024-12-31T23:59:59Z'
        }
        
        mock_environment.clients.gh.create_milestone.return_value = gh_milestone
        
        result = milestone_migrator._create_milestone(bb_milestone)
        
        assert result['number'] == 1
        mock_environment.clients.gh.create_milestone.assert_called_once()
    
    def test_create_milestone_no_description(self, milestone_migrator, mock_environment):
        """Test creating milestone without description."""
        bb_milestone = {
            'name': 'v1.0',
            'state': 'open'
        }
        
        gh_milestone = {'number': 1, 'title': 'v1.0', 'state': 'open'}
        mock_environment.clients.gh.create_milestone.return_value = gh_milestone
        
        result = milestone_migrator._create_milestone(bb_milestone)
        
        call_args = mock_environment.clients.gh.create_milestone.call_args
        assert call_args[1]['description'] is None
    
    def test_create_milestone_no_due_date(self, milestone_migrator, mock_environment):
        """Test creating milestone without due date."""
        bb_milestone = {
            'name': 'v1.0',
            'state': 'open',
            'description': 'Release'
        }
        
        gh_milestone = {'number': 1, 'title': 'v1.0', 'state': 'open'}
        mock_environment.clients.gh.create_milestone.return_value = gh_milestone
        
        result = milestone_migrator._create_milestone(bb_milestone)
        
        call_args = mock_environment.clients.gh.create_milestone.call_args
        assert call_args[1]['due_on'] is None
    
    def test_create_milestone_invalid_state(self, milestone_migrator, mock_environment):
        """Test creating milestone with invalid state."""
        bb_milestone = {
            'name': 'v1.0',
            'state': 'unknown_state'
        }
        
        gh_milestone = {'number': 1, 'title': 'v1.0', 'state': 'open'}
        mock_environment.clients.gh.create_milestone.return_value = gh_milestone
        
        result = milestone_migrator._create_milestone(bb_milestone)
        
        # Should default to 'open'
        call_args = mock_environment.clients.gh.create_milestone.call_args
        assert call_args[1]['state'] == 'open'
    
    def test_create_milestone_invalid_due_date_retry(self, milestone_migrator, mock_environment):
        """Test retry without due date when date is invalid."""
        bb_milestone = {
            'name': 'v1.0',
            'state': 'open',
            'due_on': 'invalid-date'
        }
        
        gh_milestone = {'number': 1, 'title': 'v1.0', 'state': 'open'}
        
        # First call fails due to due_on, second succeeds
        mock_environment.clients.gh.create_milestone.side_effect = [
            ValidationError("Invalid due_on date"),
            gh_milestone
        ]
        
        result = milestone_migrator._create_milestone(bb_milestone)
        
        # Should retry and succeed
        assert result['number'] == 1
        assert mock_environment.clients.gh.create_milestone.call_count == 2
        
        # Second call should have due_on=None
        second_call = mock_environment.clients.gh.create_milestone.call_args_list[1]
        assert second_call[1]['due_on'] is None
    
    def test_create_milestone_non_date_validation_error(self, milestone_migrator, mock_environment):
        """Test that non-date validation errors are not retried."""
        bb_milestone = {
            'name': 'v1.0',
            'state': 'open'
        }
        
        mock_environment.clients.gh.create_milestone.side_effect = ValidationError("Invalid title")
        
        with pytest.raises(ValidationError):
            milestone_migrator._create_milestone(bb_milestone)


class TestFormatDate:
    """Test _format_date method."""
    
    def test_format_date_with_z_suffix(self, milestone_migrator):
        """Test formatting date already ending with Z."""
        date_str = "2024-12-31T23:59:59Z"
        
        result = milestone_migrator._format_date(date_str)
        
        assert result == "2024-12-31T23:59:59Z"
    
    def test_format_date_with_timezone_offset(self, milestone_migrator):
        """Test formatting date with +00:00 offset."""
        date_str = "2024-12-31T23:59:59+00:00"
        
        result = milestone_migrator._format_date(date_str)
        
        # Should convert to Z format
        assert result == "2024-12-31T23:59:59Z"
    
    def test_format_date_without_timezone(self, milestone_migrator):
        """Test formatting date without timezone."""
        date_str = "2024-12-31T23:59:59"
        
        result = milestone_migrator._format_date(date_str)
        
        # Should add Z suffix
        assert result is not None
        assert result.endswith('Z')
    
    def test_format_date_invalid(self, milestone_migrator, mock_environment):
        """Test handling invalid date format."""
        date_str = "not-a-date"
        
        result = milestone_migrator._format_date(date_str)
        
        assert result is None
        milestone_migrator.environment.logger.warning.assert_called()
    
    def test_format_date_empty(self, milestone_migrator):
        """Test formatting empty date string."""
        result = milestone_migrator._format_date("")
        
        assert result is None
    
    def test_format_date_none(self, milestone_migrator):
        """Test formatting None date."""
        result = milestone_migrator._format_date(None)
        
        assert result is None


class TestMilestoneRecords:
    """Test milestone record creation."""
    
    def test_record_successful_creation(self, milestone_migrator, mock_environment, mock_state):
        """Test recording successful milestone creation."""
        bb_milestones = [
            {'name': 'v1.0', 'state': 'open', 'description': 'Release'}
        ]
        
        gh_milestone = {
            'number': 1,
            'title': 'v1.0',
            'state': 'open',
            'description': 'Release'
        }
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.return_value = []
        mock_environment.clients.gh.create_milestone.return_value = gh_milestone
        
        milestone_migrator.migrate_milestones()
        
        assert len(mock_state.milestone_records) == 1
        record = mock_state.milestone_records[0]
        assert record['bb_name'] == 'v1.0'
        assert record['gh_number'] == 1
        assert record['is_duplicate'] is False
        assert 'Created successfully' in record['remarks']
    
    def test_record_duplicate_milestone(self, milestone_migrator, mock_environment, mock_state):
        """Test recording duplicate milestone."""
        bb_milestones = [
            {'name': 'v1.0', 'state': 'open'}
        ]
        
        existing_gh_milestones = [
            {'number': 1, 'title': 'v1.0', 'state': 'open', 'description': ''}
        ]
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.return_value = existing_gh_milestones
        
        milestone_migrator.migrate_milestones()
        
        assert len(mock_state.milestone_records) == 1
        record = mock_state.milestone_records[0]
        assert record['is_duplicate'] is True
        assert 'Already existed on GitHub' in record['remarks']
    
    def test_record_failed_creation(self, milestone_migrator, mock_environment, mock_state):
        """Test recording failed milestone creation."""
        bb_milestones = [
            {'name': 'v1.0', 'state': 'open'}
        ]
        
        mock_environment.clients.bb.get_milestones.return_value = bb_milestones
        mock_environment.clients.gh.get_milestones.return_value = []
        mock_environment.clients.gh.create_milestone.side_effect = APIError("API error")
        
        milestone_migrator.migrate_milestones()
        
        assert len(mock_state.milestone_records) == 1
        record = mock_state.milestone_records[0]
        assert record['gh_number'] is None
        assert 'Failed to create' in record['remarks'][0]