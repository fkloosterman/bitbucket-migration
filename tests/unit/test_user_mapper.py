"""
Tests for UserMapper.

Tests the user mapping functionality including:
- Direct username mappings
- Enhanced format mappings with account IDs
- @mention resolution
- Account ID to username resolution
- Comment scanning for account IDs
- API lookups for unknown account IDs
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from bitbucket_migration.services.user_mapper import UserMapper


class TestUserMapper:
    """Test UserMapper initialization and basic setup."""

    @pytest.fixture
    def mock_user_mapper(self, mock_environment, mock_state):
        """Create a UserMapper for testing."""
        return UserMapper(mock_environment, mock_state)

    def test_init_with_user_mapping(self, mock_environment, mock_state):
        """Test UserMapper initialization with user mapping."""
        # Setup user mapping in environment
        mock_environment.config.user_mapping = {
            'bb_user1': 'gh_user1',
            'bb_user2': {'github': 'gh_user2', 'display_name': 'Display Name 2'}
        }
        
        mapper = UserMapper(mock_environment, mock_state)
        
        assert mapper.user_mapping == mock_environment.config.user_mapping
        assert hasattr(mapper, 'data')
        assert hasattr(mapper.data, 'account_id_to_username')
        assert hasattr(mapper.data, 'account_id_to_display_name')

    def test_init_without_user_mapping(self, mock_environment, mock_state):
        """Test UserMapper initialization without user mapping."""
        # Simply test that when config has no user_mapping, it defaults to empty
        mock_environment.config.user_mapping = {}
        
        mapper = UserMapper(mock_environment, mock_state)
        
        # Should be empty dict
        assert mapper.user_mapping == {}

    def test_creates_data_storage(self, mock_user_mapper):
        """Test that user mapper creates proper data storage."""
        assert hasattr(mock_user_mapper, 'data')
        assert mock_user_mapper.data is not None
        assert hasattr(mock_user_mapper.data, 'account_id_to_username')
        assert hasattr(mock_user_mapper.data, 'account_id_to_display_name')
        assert isinstance(mock_user_mapper.data.account_id_to_username, dict)
        assert isinstance(mock_user_mapper.data.account_id_to_display_name, dict)

    def test_stores_self_in_state(self, mock_environment, mock_state):
        """Test that user mapper stores itself in state services."""
        mapper = UserMapper(mock_environment, mock_state)
        
        # Should be stored in state services
        assert UserMapper.__name__ in mock_state.services
        assert mock_state.services[UserMapper.__name__] == mapper.data


class TestUserMapping:
    """Test basic user mapping functionality."""

    @pytest.fixture
    def mock_user_mapper(self, mock_environment, mock_state):
        """Create a UserMapper for testing."""
        mock_environment.config.user_mapping = {
            'bb_user1': 'gh_user1',
            'bb_user2': {'github': 'gh_user2', 'display_name': 'Display Name 2'},
            'bb_user3': None,  # No GitHub account
            'bb_user4': ''     # Empty mapping
        }
        return UserMapper(mock_environment, mock_state)

    def test_map_user_direct_mapping(self, mock_user_mapper):
        """Test mapping with direct string format."""
        result = mock_user_mapper.map_user('bb_user1')
        
        assert result == 'gh_user1'

    def test_map_user_enhanced_format(self, mock_user_mapper):
        """Test mapping with enhanced dict format."""
        result = mock_user_mapper.map_user('bb_user2')
        
        assert result == 'gh_user2'

    def test_map_user_display_name_fallback(self, mock_user_mapper):
        """Test mapping display name to GitHub user."""
        # Setup display name mapping
        mock_user_mapper.user_mapping = {
            'some_key': {
                'github': 'gh_user2',
                'display_name': 'Display Name 2'
            }
        }
        
        result = mock_user_mapper.map_user('Display Name 2')
        
        assert result == 'gh_user2'

    def test_map_user_no_mapping_returns_none(self, mock_user_mapper):
        """Test mapping non-existent user returns None."""
        result = mock_user_mapper.map_user('nonexistent_user')
        
        assert result is None

    def test_map_user_none_input(self, mock_user_mapper):
        """Test mapping None input returns None."""
        result = mock_user_mapper.map_user(None)
        
        assert result is None

    def test_map_user_empty_string(self, mock_user_mapper):
        """Test mapping empty string returns None."""
        result = mock_user_mapper.map_user('')
        
        assert result is None

    def test_map_user_no_github_account(self, mock_user_mapper):
        """Test mapping user with no GitHub account (None value)."""
        result = mock_user_mapper.map_user('bb_user3')
        
        assert result is None

    def test_map_user_empty_mapping(self, mock_user_mapper):
        """Test mapping user with empty string mapping."""
        result = mock_user_mapper.map_user('bb_user4')
        
        # Empty string should be treated as no mapping
        assert result is None

    def test_map_user_enhanced_format_no_github(self, mock_user_mapper):
        """Test enhanced format with no GitHub account specified."""
        mock_user_mapper.user_mapping = {
            'user_key': {
                'github': None,
                'display_name': 'Some Display Name'
            }
        }
        
        result = mock_user_mapper.map_user('user_key')
        
        assert result is None


class TestMentionMapping:
    """Test @mention mapping with account ID resolution."""

    @pytest.fixture
    def mock_user_mapper(self, mock_environment, mock_state):
        """Create a UserMapper for testing."""
        mock_environment.config.user_mapping = {
            'bb_user1': 'gh_user1',
            'account_user': {
                'github': 'gh_account_user',
                'bitbucket_username': 'bb_account_user'
            }
        }
        return UserMapper(mock_environment, mock_state)

    def test_map_mention_with_username(self, mock_user_mapper):
        """Test mapping @mention with username."""
        result = mock_user_mapper.map_mention('bb_user1')
        
        assert result == 'gh_user1'

    def test_map_mention_with_account_id(self, mock_user_mapper):
        """Test mapping @mention with account ID."""
        # Setup account ID mapping
        mock_user_mapper.data.account_id_to_username['account-123'] = 'bb_account_user'
        
        result = mock_user_mapper.map_mention('account-123')
        
        assert result == 'gh_account_user'

    def test_map_mention_account_id_resolved_to_username(self, mock_user_mapper):
        """Test account ID resolution to username."""
        # Setup account ID to username mapping
        mock_user_mapper.data.account_id_to_username['account-456'] = 'bb_user1'
        
        result = mock_user_mapper.map_mention('account-456')
        
        # Should resolve account ID to username, then map to GitHub
        assert result == 'gh_user1'

    def test_map_mention_account_id_resolved_to_display_name(self, mock_user_mapper):
        """Test account ID resolution when only display name available."""
        # Setup account ID to display name mapping (no username)
        mock_user_mapper.data.account_id_to_display_name['account-789'] = 'Display Name Only'
        
        # Map display name to GitHub user
        mock_user_mapper.user_mapping['Display Name Only'] = 'gh_display_user'
        
        result = mock_user_mapper.map_mention('account-789')
        
        # Should resolve account ID to display name, then map
        assert result == 'gh_display_user'

    def test_map_mention_fallback_to_alternative_mapping(self, mock_user_mapper):
        """Test fallback when direct mapping doesn't work."""
        # Setup account ID to both username and display name
        mock_user_mapper.data.account_id_to_username['account-abc'] = 'bb_user1'
        mock_user_mapper.data.account_id_to_display_name['account-abc'] = 'bb_user1_display'
    
        # Only username has mapping (not display name)
        mock_user_mapper.user_mapping['bb_user1'] = 'gh_user1'
    
        result = mock_user_mapper.map_mention('account-abc')
    
        # Should use username mapping (preferred)
        assert result == 'gh_user1'

    def test_map_mention_no_mapping(self, mock_user_mapper):
        """Test mapping @mention with no available mapping."""
        result = mock_user_mapper.map_mention('unknown_user')
        
        assert result is None

    def test_map_mention_none_input(self, mock_user_mapper):
        """Test mapping None @mention."""
        result = mock_user_mapper.map_mention(None)
        
        assert result is None

    def test_map_mention_empty_string(self, mock_user_mapper):
        """Test mapping empty @mention."""
        result = mock_user_mapper.map_mention('')
        
        assert result is None

    def test_map_mention_enhanced_format_direct(self, mock_user_mapper):
        """Test mapping @mention in enhanced format directly."""
        result = mock_user_mapper.map_mention('account_user')
        
        # Should match bitbucket_username in enhanced format
        assert result == 'gh_account_user'

    def test_map_mention_enhanced_format_with_null_github(self, mock_user_mapper):
        """Test enhanced format with null GitHub account."""
        mock_user_mapper.user_mapping = {
            'no_gh_user': {
                'github': None,
                'display_name': 'No GitHub'
            }
        }
        
        result = mock_user_mapper.map_mention('no_gh_user')
        
        # Should return None for null GitHub account
        assert result is None

    def test_map_mention_enhanced_format_with_empty_github(self, mock_user_mapper):
        """Test enhanced format with empty GitHub account."""
        mock_user_mapper.user_mapping = {
            'empty_gh_user': {
                'bitbucket_username': 'empty_bb_user',
                'github': ''
            }
        }
        
        result = mock_user_mapper.map_mention('empty_bb_user')
        
        # Should return None for empty GitHub account
        assert result is None


class TestAccountIDResolution:
    """Test building account ID to username mappings."""

    @pytest.fixture
    def mock_user_mapper(self, mock_environment, mock_state):
        """Create a UserMapper for testing."""
        return UserMapper(mock_environment, mock_state)

    def test_build_account_id_mappings_from_issues(self, mock_user_mapper):
        """Test building mappings from issues."""
        issues = [
            {
                'id': 1,
                'reporter': {
                    'account_id': 'acc1',
                    'username': 'user1',
                    'display_name': 'User One'
                },
                'assignee': {
                    'account_id': 'acc2',
                    'username': 'user2',
                    'display_name': 'User Two'
                }
            },
            {
                'id': 2,
                'reporter': {
                    'account_id': 'acc1',  # Same as above
                    'username': 'user1',
                    'display_name': 'User One Updated'
                }
            }
        ]
        
        prs = []
        
        result = mock_user_mapper.build_account_id_mappings(issues, prs)
        
        # Should find 2 unique account IDs
        assert result == 2
        assert 'acc1' in mock_user_mapper.data.account_id_to_username
        assert 'acc2' in mock_user_mapper.data.account_id_to_username
        
        # Should have usernames
        assert mock_user_mapper.data.account_id_to_username['acc1'] == 'user1'
        assert mock_user_mapper.data.account_id_to_username['acc2'] == 'user2'
        
        # Should have display names
        assert mock_user_mapper.data.account_id_to_display_name['acc1'] == 'User One Updated'
        assert mock_user_mapper.data.account_id_to_display_name['acc2'] == 'User Two'

    def test_build_account_id_mappings_from_prs(self, mock_user_mapper):
        """Test building mappings from pull requests."""
        issues = []
        prs = [
            {
                'id': 1,
                'author': {
                    'account_id': 'acc1',
                    'username': 'author1',
                    'display_name': 'Author One'
                },
                'participants': [
                    {
                        'user': {
                            'account_id': 'acc2',
                            'username': 'participant1',
                            'display_name': 'Participant One'
                        }
                    }
                ],
                'reviewers': [
                    {
                        'account_id': 'acc3',
                        'username': 'reviewer1',
                        'display_name': 'Reviewer One'
                    }
                ]
            }
        ]
        
        result = mock_user_mapper.build_account_id_mappings(issues, prs)
        
        # Should find 3 unique account IDs
        assert result == 3
        assert 'acc1' in mock_user_mapper.data.account_id_to_username
        assert 'acc2' in mock_user_mapper.data.account_id_to_username
        assert 'acc3' in mock_user_mapper.data.account_id_to_username

    def test_build_account_id_mappings_duplicate_handling(self, mock_user_mapper):
        """Test handling duplicate account IDs."""
        issues = [
            {
                'id': 1,
                'reporter': {
                    'account_id': 'acc1',
                    'username': 'user1',
                    'display_name': 'Display 1'
                }
            },
            {
                'id': 2,
                'reporter': {
                    'account_id': 'acc1',  # Duplicate
                    'username': 'user1',
                    'display_name': 'Display 1 Updated'
                }
            }
        ]
        
        prs = []
        
        result = mock_user_mapper.build_account_id_mappings(issues, prs)
        
        # Should only count once
        assert result == 1
        assert len(mock_user_mapper.data.account_id_to_username) == 1

    def test_build_account_id_mappings_missing_fields(self, mock_user_mapper):
        """Test handling issues/PRs with missing user fields."""
        issues = [
            {
                'id': 1,
                'reporter': {
                    'account_id': 'acc1',
                    # Missing username
                    'display_name': 'Display Name'
                }
            }
        ]
        
        prs = [
            {
                'id': 1,
                'author': {
                    # Missing account_id
                    'username': 'author1',
                    'display_name': 'Author Display'
                }
            }
        ]
        
        result = mock_user_mapper.build_account_id_mappings(issues, prs)
        
        # Should only add the one with account_id
        assert result == 1
        # Username might be None, but account ID should still be tracked
        assert 'acc1' in mock_user_mapper.data.account_id_to_display_name
        # Display name should be recorded
        assert mock_user_mapper.data.account_id_to_display_name['acc1'] == 'Display Name'

    def test_add_account_mapping(self, mock_user_mapper):
        """Test adding account ID mappings manually."""
        mock_user_mapper.add_account_mapping('acc123', 'username', 'Display Name')
        
        assert mock_user_mapper.data.account_id_to_username['acc123'] == 'username'
        assert mock_user_mapper.data.account_id_to_display_name['acc123'] == 'Display Name'

    def test_add_account_mapping_no_display_name(self, mock_user_mapper):
        """Test adding account ID mapping without display name."""
        mock_user_mapper.add_account_mapping('acc456', 'username_only', None)
        
        assert mock_user_mapper.data.account_id_to_username['acc456'] == 'username_only'
        assert 'acc456' not in mock_user_mapper.data.account_id_to_display_name

    def test_scan_comments_for_account_ids(self, mock_user_mapper):
        """Test scanning comments for account IDs."""
        # Mock Bitbucket client
        mock_bb = MagicMock()
        mock_bb.get_comments.side_effect = [
            [  # Issue 1 comments
                {
                    'id': 1,
                    'content': {'raw': 'Check this out @{557058:account123}'},
                    'created_on': '2024-01-01'
                }
            ],
            [  # PR 1 comments
                {
                    'id': 2,
                    'content': {'raw': 'See also @{557058:account456}'},
                    'created_on': '2024-01-02'
                }
            ]
        ]
        mock_user_mapper.bb_client = mock_bb
        
        issues = [{'id': 1}]
        prs = [{'id': 1}]
        
        with patch.object(mock_user_mapper, 'lookup_account_id_via_api') as mock_lookup:
            mock_lookup.return_value = {
                'username': 'found_user',
                'display_name': 'Found User Display'
            }
            
            mock_user_mapper.scan_comments_for_account_ids(issues, prs)
        
        # Should look up both account IDs (full format with prefix)
        assert mock_lookup.call_count == 2
        call_args = [call[0][0] for call in mock_lookup.call_args_list]
        assert '557058:account123' in call_args
        assert '557058:account456' in call_args
        
        # Should add resolved mappings (full account ID format)
        assert '557058:account123' in mock_user_mapper.data.account_id_to_username
        assert '557058:account456' in mock_user_mapper.data.account_id_to_username

    def test_scan_comments_no_mentions(self, mock_user_mapper):
        """Test scanning comments with no @mentions."""
        mock_bb = MagicMock()
        mock_bb.get_comments.return_value = [
            {
                'id': 1,
                'content': {'raw': 'This is a comment with no mentions.'},
                'created_on': '2024-01-01'
            }
        ]
        mock_user_mapper.bb_client = mock_bb
        
        issues = [{'id': 1}]
        prs = []
        
        with patch.object(mock_user_mapper, 'lookup_account_id_via_api') as mock_lookup:
            mock_user_mapper.scan_comments_for_account_ids(issues, prs)
        
        # Should not look up any account IDs
        mock_lookup.assert_not_called()

    def test_scan_comments_no_at_symbol(self, mock_user_mapper):
        """Test scanning comments without @ symbol."""
        mock_bb = MagicMock()
        mock_bb.get_comments.return_value = [
            {
                'id': 1,
                'content': {'raw': 'Just regular text content.'},
                'created_on': '2024-01-01'
            }
        ]
        mock_user_mapper.bb_client = mock_bb
        
        issues = [{'id': 1}]
        prs = []
        
        with patch.object(mock_user_mapper, 'lookup_account_id_via_api') as mock_lookup:
            mock_user_mapper.scan_comments_for_account_ids(issues, prs)
        
        # Should not look up any account IDs
        mock_lookup.assert_not_called()

    def test_lookup_account_id_via_api_success(self, mock_user_mapper):
        """Test successful API lookup of account ID."""
        mock_bb = MagicMock()
        mock_bb.get_user_info.return_value = {
            'username': 'api_user',
            'display_name': 'API User Display'
        }
        mock_user_mapper.bb_client = mock_bb
        
        result = mock_user_mapper.lookup_account_id_via_api('acc123')
        
        assert result is not None
        assert result['username'] == 'api_user'
        assert result['display_name'] == 'API User Display'
        mock_bb.get_user_info.assert_called_once_with('acc123')

    def test_lookup_account_id_via_api_api_error(self, mock_user_mapper):
        """Test API lookup with API error."""
        from bitbucket_migration.exceptions import APIError
        
        mock_bb = MagicMock()
        mock_bb.get_user_info.side_effect = APIError("API Error")
        mock_user_mapper.bb_client = mock_bb
        
        result = mock_user_mapper.lookup_account_id_via_api('acc123')
        
        assert result is None

    def test_lookup_account_id_via_api_auth_error(self, mock_user_mapper):
        """Test API lookup with authentication error."""
        from bitbucket_migration.exceptions import AuthenticationError
        
        mock_bb = MagicMock()
        mock_bb.get_user_info.side_effect = AuthenticationError("Auth Error")
        mock_user_mapper.bb_client = mock_bb
        
        result = mock_user_mapper.lookup_account_id_via_api('acc123')
        
        assert result is None

    def test_lookup_account_id_via_api_network_error(self, mock_user_mapper):
        """Test API lookup with network error."""
        from bitbucket_migration.exceptions import NetworkError
        
        mock_bb = MagicMock()
        mock_bb.get_user_info.side_effect = NetworkError("Network Error")
        mock_user_mapper.bb_client = mock_bb
        
        result = mock_user_mapper.lookup_account_id_via_api('acc123')
        
        assert result is None

    def test_lookup_account_id_via_api_generic_exception(self, mock_user_mapper):
        """Test API lookup with generic exception."""
        mock_bb = MagicMock()
        mock_bb.get_user_info.side_effect = Exception("Generic Error")
        mock_user_mapper.bb_client = mock_bb
        
        result = mock_user_mapper.lookup_account_id_via_api('acc123')
        
        assert result is None

    def test_scan_comments_known_account_ids_skipped(self, mock_user_mapper):
        """Test that known account IDs are not looked up again."""
        # Pre-populate known account ID with colon format
        mock_user_mapper.data.account_id_to_username['557058:known123'] = 'known_user'
        
        mock_bb = MagicMock()
        # Comments reference both known and unknown account IDs
        mock_bb.get_comments.side_effect = [
            [
                {
                    'id': 1,
                    'content': {'raw': 'Check @{557058:known123} and @{557058:unknown456}'},
                    'created_on': '2024-01-01'
                }
            ]
        ]
        mock_user_mapper.bb_client = mock_bb
        
        issues = [{'id': 1}]
        prs = []
        
        with patch.object(mock_user_mapper, 'lookup_account_id_via_api') as mock_lookup:
            mock_lookup.return_value = {
                'username': 'unknown_user',
                'display_name': 'Unknown User'
            }
            
            mock_user_mapper.scan_comments_for_account_ids(issues, prs)
        
        # Should only look up unknown account ID
        mock_lookup.assert_called_once_with('557058:unknown456')

    def test_scan_comments_account_id_formats(self, mock_user_mapper):
        """Test various account ID formats in comments."""
        # Test with just one format to ensure it works
        content = '@{557058:account123}'  # Curly braces format
        
        with patch.object(mock_user_mapper, 'lookup_account_id_via_api') as mock_lookup:
            mock_lookup.return_value = {'username': 'test_user', 'display_name': 'Test User'}
            
            mock_bb = MagicMock()
            mock_bb.get_comments.return_value = [
                {
                    'id': 1,
                    'content': {'raw': f'Mention: {content}'},
                    'created_on': '2024-01-01'
                }
            ]
            mock_user_mapper.bb_client = mock_bb
            
            issues = [{'id': 1}]
            prs = []
            
            mock_user_mapper.scan_comments_for_account_ids(issues, prs)
            
            # Account ID should be detected and looked up
            assert mock_lookup.call_count == 1
            mock_lookup.assert_called_with('557058:account123')