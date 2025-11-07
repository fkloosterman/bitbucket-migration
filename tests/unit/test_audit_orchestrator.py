"""
Tests for AuditOrchestrator.

Tests the multi-repository audit orchestrator including:
- Initialization and validation
- Repository discovery
- Multi-repository auditing
- Configuration generation and merging
- Error handling
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from bitbucket_migration.audit.audit_orchestrator import AuditOrchestrator
from bitbucket_migration.exceptions import ValidationError


class TestAuditOrchestratorInitialization:
    """Test AuditOrchestrator initialization and configuration."""
    
    def test_init_with_valid_params(self):
        """Test successful initialization with valid parameters."""
        orchestrator = AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token"
        )
        
        assert orchestrator.workspace == "test-workspace"
        assert orchestrator.email == "test@example.com"
        assert orchestrator.token == "test-token"
        assert orchestrator.logger is not None
        assert orchestrator.bb_client is not None
    
    def test_init_empty_workspace_raises_error(self):
        """Test that empty workspace raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket workspace cannot be empty"):
            AuditOrchestrator(workspace="", email="test@example.com", token="test-token")
    
    def test_init_whitespace_only_workspace_raises_error(self):
        """Test that whitespace-only workspace raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket workspace cannot be empty"):
            AuditOrchestrator(workspace="   ", email="test@example.com", token="test-token")
    
    def test_init_empty_email_raises_error(self):
        """Test that empty email raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket email cannot be empty"):
            AuditOrchestrator(workspace="test-workspace", email="", token="test-token")
    
    def test_init_empty_token_raises_error(self):
        """Test that empty token raises ValidationError."""
        with pytest.raises(ValidationError, match="Bitbucket token cannot be empty"):
            AuditOrchestrator(workspace="test-workspace", email="test@example.com", token="")
    
    def test_init_with_custom_base_dir_manager(self):
        """Test initialization with custom BaseDirManager."""
        mock_base_dir_manager = MagicMock()
        
        orchestrator = AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token",
            base_dir_manager=mock_base_dir_manager
        )
        
        assert orchestrator.base_dir_manager == mock_base_dir_manager
    
    def test_init_with_default_base_dir_manager(self):
        """Test initialization creates default BaseDirManager when not provided."""
        orchestrator = AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token"
        )
        
        # Should create a BaseDirManager with current directory
        assert orchestrator.base_dir_manager is not None


class TestRepositoryDiscovery:
    """Test repository discovery functionality."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create AuditOrchestrator for testing."""
        return AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('bitbucket_migration.audit.audit_orchestrator.BitbucketClient')
    def test_discover_repositories_success(self, mock_bb_client, orchestrator):
        """Test successful repository discovery."""
        # Mock Bitbucket client
        mock_client = Mock()
        mock_client.list_repositories.return_value = [
            {'slug': 'repo1', 'name': 'Repository 1'},
            {'slug': 'repo2', 'name': 'Repository 2'},
            {'slug': 'repo3', 'name': 'Repository 3'}
        ]
        mock_bb_client.return_value = mock_client
        
        # Re-initialize to use mocked client
        orchestrator.bb_client = mock_client
        
        repositories = orchestrator.discover_repositories()
        
        assert len(repositories) == 3
        assert 'repo1' in repositories
        assert 'repo2' in repositories
        assert 'repo3' in repositories
    
    @patch('bitbucket_migration.audit.audit_orchestrator.BitbucketClient')
    def test_discover_repositories_empty(self, mock_bb_client, orchestrator):
        """Test repository discovery with no repositories."""
        # Mock Bitbucket client
        mock_client = Mock()
        mock_client.list_repositories.return_value = []
        mock_bb_client.return_value = mock_client
        
        # Re-initialize to use mocked client
        orchestrator.bb_client = mock_client
        
        repositories = orchestrator.discover_repositories()
        
        assert repositories == []


class TestMultiRepositoryAuditing:
    """Test multi-repository auditing functionality."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create AuditOrchestrator for testing."""
        return AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token"
        )
    
    @patch('bitbucket_migration.audit.audit_orchestrator.Auditor')
    def test_audit_repositories_with_provided_names(self, mock_auditor_class, orchestrator):
        """Test auditing with explicitly provided repository names."""
        # Mock Bitbucket client
        mock_client = Mock()
        mock_client.list_repositories.return_value = []
        orchestrator.bb_client = mock_client
        
        # Mock auditor instances
        mock_auditor1 = Mock()
        mock_auditor1.run_audit.return_value = {'status': 'success', 'issues': 10, 'prs': 5}
        
        mock_auditor2 = Mock()
        mock_auditor2.run_audit.return_value = {'status': 'success', 'issues': 15, 'prs': 8}
        
        # Configure mock to return different auditors
        mock_auditor_class.side_effect = [mock_auditor1, mock_auditor2]
        
        repo_names = ['repo1', 'repo2']
        reports = orchestrator.audit_repositories(repo_names=repo_names, discover=False)
        
        assert len(reports) == 2
        assert 'repo1' in reports
        assert 'repo2' in reports
        assert reports['repo1']['status'] == 'success'
        assert reports['repo2']['status'] == 'success'
    
    @patch('bitbucket_migration.audit.audit_orchestrator.Auditor')
    def test_audit_repositories_with_discovery(self, mock_auditor_class, orchestrator):
        """Test auditing with auto-discovery of repositories."""
        # Mock Bitbucket client
        mock_client = Mock()
        mock_client.list_repositories.return_value = [
            {'slug': 'discovered-repo1'},
            {'slug': 'discovered-repo2'}
        ]
        orchestrator.bb_client = mock_client
        
        # Mock auditor instances
        mock_auditor1 = Mock()
        mock_auditor1.run_audit.return_value = {'status': 'success', 'issues': 5}
        
        mock_auditor2 = Mock()
        mock_auditor2.run_audit.return_value = {'status': 'success', 'issues': 8}
        
        mock_auditor_class.side_effect = [mock_auditor1, mock_auditor2]
        
        reports = orchestrator.audit_repositories(discover=True)
        
        assert len(reports) == 2
        assert 'discovered-repo1' in reports
        assert 'discovered-repo2' in reports
    
    def test_audit_repositories_no_names_no_discovery_raises_error(self, orchestrator):
        """Test that no repository names and no discovery raises ValidationError."""
        with pytest.raises(ValidationError, match="Either provide repo_names or set discover=True"):
            orchestrator.audit_repositories()
    
    def test_audit_repositories_empty_list(self, orchestrator):
        """Test auditing with empty repository list."""
        reports = orchestrator.audit_repositories(repo_names=[], discover=False)
        
        assert reports == {}
    
    @patch('bitbucket_migration.audit.audit_orchestrator.Auditor')
    def test_audit_repositories_with_failures(self, mock_auditor_class, orchestrator):
        """Test auditing with some repository failures."""
        # Mock successful auditor
        mock_auditor_success = Mock()
        mock_auditor_success.run_audit.return_value = {'status': 'success', 'issues': 10}
        
        # Mock failed auditor
        mock_auditor_fail = Mock()
        mock_auditor_fail.run_audit.side_effect = Exception("API Error")
        
        mock_auditor_class.side_effect = [mock_auditor_success, mock_auditor_fail]
        
        repo_names = ['good-repo', 'bad-repo']
        reports = orchestrator.audit_repositories(repo_names=repo_names, discover=False)
        
        assert len(reports) == 2
        assert 'good-repo' in reports
        assert 'bad-repo' in reports
        assert 'error' in reports['bad-repo']
        assert 'status' in reports['bad-repo']


class TestConfigGeneration:
    """Test unified configuration generation."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create AuditOrchestrator for testing."""
        return AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token"
        )
    
    def test_generate_config_new_config(self, orchestrator):
        """Test generating new configuration from reports."""
        reports = {
            'repo1': {'issues': {'total': 10}, 'users': {'list': ['user1', 'user2']}},
            'repo2': {'issues': {'total': 5}, 'users': {'list': ['user2', 'user3']}}
        }
        
        config = orchestrator.generate_config(reports, gh_owner="test-owner")
        
        assert config['bitbucket']['workspace'] == 'test-workspace'
        assert config['bitbucket']['email'] == 'test@example.com'
        assert config['github']['owner'] == 'test-owner'
        assert len(config['repositories']) == 2
        
        # Check repository mappings
        repo_names = [repo['bitbucket_repo'] for repo in config['repositories']]
        assert 'repo1' in repo_names
        assert 'repo2' in repo_names
        
        # Check user mapping aggregation
        assert len(config['user_mapping']) == 3  # user1, user2, user3
        assert 'user1' in config['user_mapping']
        assert 'user2' in config['user_mapping']
        assert 'user3' in config['user_mapping']
    
    def test_generate_config_with_external_repos(self, orchestrator):
        """Test generating config with external repositories."""
        reports = {
            'repo1': {'issues': {'total': 10}}
        }
        external_repos = ['external-repo1', 'external-repo2']
        
        config = orchestrator.generate_config(
            reports, 
            gh_owner="test-owner", 
            external_repos=external_repos
        )
        
        assert len(config['external_repositories']) == 2
        ext_repo_names = [repo['bitbucket_repo'] for repo in config['external_repositories']]
        assert 'external-repo1' in ext_repo_names
        assert 'external-repo2' in ext_repo_names
    
    def test_generate_config_skips_failed_audits(self, orchestrator):
        """Test that failed audits are skipped in config generation."""
        reports = {
            'good-repo': {'issues': {'total': 10}},
            'bad-repo': {'error': 'API Error', 'status': 'failed'}
        }
        
        config = orchestrator.generate_config(reports, gh_owner="test-owner")
        
        # Should only include successful repo
        repo_names = [repo['bitbucket_repo'] for repo in config['repositories']]
        assert 'good-repo' in repo_names
        assert 'bad-repo' not in repo_names
    
    def test_generate_config_merges_with_existing(self, orchestrator):
        """Test merging new config with existing configuration."""
        # Mock existing config file
        existing_config = {
            'repositories': [
                {
                    'bitbucket_repo': 'existing-repo',
                    'github_repo': 'existing-repo-renamed'
                }
            ],
            'user_mapping': {
                'existing-user': 'existing-gh-user'
            }
        }
        
        with patch.object(orchestrator, '_load_existing_config', return_value=existing_config):
            reports = {
                'new-repo': {'issues': {'total': 5}, 'users': {'list': ['new-user']}}
            }
            
            config = orchestrator.generate_config(reports, gh_owner="test-owner")
            
            # Should have both existing and new repositories
            assert len(config['repositories']) == 2
            repo_names = [repo['bitbucket_repo'] for repo in config['repositories']]
            assert 'existing-repo' in repo_names
            assert 'new-repo' in repo_names
            
            # Should have both existing and new users
            assert 'existing-user' in config['user_mapping']
            assert 'new-user' in config['user_mapping']
    
    def test_generate_config_uses_existing_gh_owner(self, orchestrator):
        """Test using GitHub owner from existing config when not provided."""
        existing_config = {
            'github': {'owner': 'existing-owner'}
        }
        
        with patch.object(orchestrator, '_load_existing_config', return_value=existing_config):
            reports = {'repo1': {'issues': {'total': 5}}}
            
            config = orchestrator.generate_config(reports)  # No gh_owner provided
            
            assert config['github']['owner'] == 'existing-owner'
    
    def test_generate_config_default_gh_owner(self, orchestrator):
        """Test default GitHub owner when not provided and no existing config."""
        reports = {'repo1': {'issues': {'total': 5}}}
        
        config = orchestrator.generate_config(reports)
        
        assert config['github']['owner'] == 'YOUR_GITHUB_USERNAME'


class TestConfigMerging:
    """Test configuration merging logic."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create AuditOrchestrator for testing."""
        return AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token"
        )
    
    def test_merge_repositories_avoid_duplicates(self, orchestrator):
        """Test that duplicate repositories are handled correctly."""
        existing_repos = [
            {'bitbucket_repo': 'repo1', 'github_repo': 'repo1'},
            {'bitbucket_repo': 'repo2', 'github_repo': 'repo2'}
        ]
        new_repos = [
            {'bitbucket_repo': 'repo2', 'github_repo': 'repo2-updated'},  # Duplicate, should update
            {'bitbucket_repo': 'repo3', 'github_repo': 'repo3'}  # New
        ]
        
        merged = orchestrator._merge_repositories(existing_repos, new_repos)
        
        assert len(merged) == 3
        repo_map = {repo['bitbucket_repo']: repo for repo in merged}
        
        # repo1 unchanged
        assert repo_map['repo1']['github_repo'] == 'repo1'
        
        # repo2 updated (new takes precedence)
        assert repo_map['repo2']['github_repo'] == 'repo2-updated'
        
        # repo3 added
        assert repo_map['repo3']['github_repo'] == 'repo3'
    
    def test_merge_user_mappings_preserve_existing(self, orchestrator):
        """Test that existing user mappings are preserved."""
        existing_mapping = {
            'user1': 'gh_user1',
            'user2': 'gh_user2'
        }
        
        reports = {
            'repo1': {'users': {'list': ['user2', 'user3']}}
        }
        
        merged = orchestrator._merge_user_mappings(reports, existing_mapping)
        
        # Should have all users
        assert len(merged) == 3
        assert merged['user1'] == 'gh_user1'  # Preserved
        assert merged['user2'] == 'gh_user2'  # Preserved
        assert merged['user3'] == ''  # New user, empty for filling
    
    def test_merge_user_mappings_unknown_users_as_none(self, orchestrator):
        """Test that unknown/deleted users are mapped to None."""
        existing_mapping = {
            'user1': 'gh_user1'
        }
        
        reports = {
            'repo1': {'users': {'list': ['Unknown', 'user2', 'Unknown (deleted user)']}}
        }
        
        merged = orchestrator._merge_user_mappings(reports, existing_mapping)
        
        assert merged['Unknown'] is None
        assert merged['Unknown (deleted user)'] is None
        assert merged['user2'] == ''  # New regular user


class TestConfigLoading:
    """Test existing configuration loading."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create AuditOrchestrator for testing."""
        return AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token"
        )
    
    def test_load_existing_config_file_not_exists(self, orchestrator):
        """Test loading when config file doesn't exist."""
        with patch.object(orchestrator.base_dir_manager, 'get_config_path') as mock_get_path:
            mock_path = Mock()
            mock_path.exists.return_value = False
            mock_get_path.return_value = mock_path
            
            config = orchestrator._load_existing_config()
            
            assert config is None
    
    def test_load_existing_config_invalid_json(self, orchestrator):
        """Test loading with invalid JSON."""
        with patch.object(orchestrator.base_dir_manager, 'get_config_path') as mock_get_path:
            mock_path = Mock()
            mock_path.exists.return_value = True
            mock_get_path.return_value = mock_path
            
            mock_file = MagicMock()
            mock_file.read.return_value = 'invalid json'
            
            with patch('builtins.open', return_value=mock_file):
                with patch('json.load', side_effect=json.JSONDecodeError("Invalid JSON", "doc", 0)):
                    config = orchestrator._load_existing_config()
                    
                    assert config is None
    
    def test_load_existing_config_different_workspace(self, orchestrator):
        """Test loading config for different workspace."""
        existing_config = {
            'bitbucket': {'workspace': 'different-workspace'}
        }
        
        with patch.object(orchestrator.base_dir_manager, 'get_config_path') as mock_get_path:
            mock_path = Mock()
            mock_path.exists.return_value = True
            mock_get_path.return_value = mock_path
            
            mock_file = MagicMock()
            mock_file.read.return_value = '{}'
            
            with patch('builtins.open', return_value=mock_file):
                with patch('json.load', return_value=existing_config):
                    config = orchestrator._load_existing_config()
                    
                    assert config is None
    
    def test_load_existing_config_success(self, orchestrator):
        """Test successful loading of existing config."""
        existing_config = {
            'bitbucket': {'workspace': 'test-workspace'},
            'repositories': []
        }
        
        with patch.object(orchestrator.base_dir_manager, 'get_config_path') as mock_get_path:
            mock_path = Mock()
            mock_path.exists.return_value = True
            mock_get_path.return_value = mock_path
            
            mock_file = MagicMock()
            mock_file.read.return_value = '{}'
            
            with patch('builtins.open', return_value=mock_file):
                with patch('json.load', return_value=existing_config):
                    config = orchestrator._load_existing_config()
                    
                    assert config == existing_config


class TestConfigSaving:
    """Test configuration file saving."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create AuditOrchestrator for testing."""
        return AuditOrchestrator(
            workspace="test-workspace",
            email="test@example.com",
            token="test-token"
        )
    
    def test_save_config_custom_filename(self, orchestrator):
        """Test saving config with custom filename."""
        config = {'test': 'config'}
        
        with patch.object(orchestrator.base_dir_manager, 'ensure_base_dir'), \
             patch.object(orchestrator.base_dir_manager, 'get_config_path') as mock_get_path, \
             patch.object(orchestrator.base_dir_manager, 'create_file') as mock_create_file:
            
            mock_path = Path('/fake/path/config.json')
            mock_get_path.return_value = mock_path
            
            orchestrator.save_config(config, filename="custom-config.json")
            
            mock_get_path.assert_called_once_with("custom-config.json")
            mock_create_file.assert_called_once_with(
                mock_path,
                config,
                subcommand='system',
                category='config'
            )
    
    def test_save_config_auto_generated_filename(self, orchestrator):
        """Test saving config with auto-generated filename."""
        config = {'test': 'config'}
        
        with patch.object(orchestrator.base_dir_manager, 'ensure_base_dir'), \
             patch.object(orchestrator.base_dir_manager, 'get_config_path') as mock_get_path, \
             patch.object(orchestrator.base_dir_manager, 'create_file') as mock_create_file:
            
            mock_path = Path('/fake/path/config.json')
            mock_get_path.return_value = mock_path
            
            orchestrator.save_config(config)  # No filename provided
            
            mock_get_path.assert_called_once_with(None)  # Should pass None for auto-generation
            mock_create_file.assert_called_once_with(
                mock_path,
                config,
                subcommand='system',
                category='config'
            )