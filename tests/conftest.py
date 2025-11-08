"""
Shared pytest fixtures for unit tests.

Provides mock objects and helper factories for testing migration components.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock
from dataclasses import dataclass
from typing import Dict, Any

import pytest


@dataclass
class MockMigrationConfig:
    """Mock migration configuration for testing."""
    
    @dataclass
    class MockBitbucketConfig:
        workspace: str = "test_workspace"
        repo: str = "test_repo"
        email: str = "test@example.com"
        token: str = "test_token"
    
    @dataclass
    class MockGitHubConfig:
        owner: str = "test_owner"
        repo: str = "test_repo"
        token: str = "test_token"
    
    @dataclass
    class MockLinkRewritingConfig:
        enabled: bool = True
        enable_notes: bool = True
        enable_markdown_awareness: bool = True
        note_templates: Dict[str, str] = None
        
        def __post_init__(self):
            if self.note_templates is None:
                self.note_templates = {
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
        
        def get_template(self, link_type: str) -> str:
            return self.note_templates.get(link_type, self.note_templates.get('default', ''))
    
    bitbucket: MockBitbucketConfig = None
    github: MockGitHubConfig = None
    link_rewriting_config: MockLinkRewritingConfig = None
    
    def __post_init__(self):
        if self.bitbucket is None:
            self.bitbucket = self.MockBitbucketConfig()
        if self.github is None:
            self.github = self.MockGitHubConfig()
        if self.link_rewriting_config is None:
            self.link_rewriting_config = self.MockLinkRewritingConfig()


@pytest.fixture
def mock_environment():
    """Create a mock MigrationEnvironment for testing."""
    env = MagicMock()
    env.config = MockMigrationConfig()
    env.logger = MagicMock()
    env.logger.debug = MagicMock()
    env.logger.info = MagicMock()
    env.logger.error = MagicMock()
    env.logger.warning = MagicMock()
    
    # Mock dry_run default
    env.dry_run = False
    
    # Mock services
    env.services = MagicMock()
    
    # Mock base_dir_manager
    env.base_dir_manager = MagicMock()
    env.base_dir_manager.get_subcommand_dir = MagicMock()
    mock_subcommand_dir = MagicMock()
    mock_subcommand_dir.__truediv__ = MagicMock(return_value=mock_subcommand_dir)
    env.base_dir_manager.get_subcommand_dir.return_value = mock_subcommand_dir
    
    # Mock clients
    env.clients = MagicMock()
    env.clients.gh = MagicMock()
    env.clients.bitbucket = MagicMock()
    
    # Mock cross repo mapping store
    mock_mapping_store = MagicMock()
    mock_mapping_store.get_mapped_repository = MagicMock(return_value=(None, None))
    mock_mapping_store.get_issue_mapping = MagicMock(return_value={})
    mock_mapping_store.get_pr_mapping = MagicMock(return_value={})
    mock_mapping_store.has_repository = MagicMock(return_value=False)
    
    env.services.get = MagicMock(return_value=mock_mapping_store)
    
    return env


@pytest.fixture
def mock_state():
    """Create a mock MigrationState for testing."""
    state = MagicMock()
    
    # Mock mappings
    state.mappings = MagicMock()
    state.mappings.issues = {}
    state.mappings.prs = {}
    
    # Mock services
    state.services = {}
    
    return state


@pytest.fixture
def mock_cross_repo_store(mock_environment, mock_state):
    """Create a mock CrossRepoMappingStore for testing."""
    from bitbucket_migration.services.cross_repo_mapping_store import CrossRepoMappingStore
    
    store = MagicMock(spec=CrossRepoMappingStore)
    store._repositories = {}
    store._mappings = {}
    store._loaded = False
    
    def mock_get_mapped_repository(bb_workspace: str, bb_repo: str):
        key = f"{bb_workspace}/{bb_repo}"
        mapped = store._repositories.get(key, "")
        if not mapped:
            return None, None
        if '/' in mapped:
            return mapped.split('/', 1)
        return None, mapped
    
    store.get_mapped_repository = mock_get_mapped_repository
    store.get_issue_mapping = MagicMock(return_value={})
    store.get_pr_mapping = MagicMock(return_value={})
    store.set_repository_mapping = MagicMock()
    store.load = MagicMock(return_value=({}, {}))
    
    return store