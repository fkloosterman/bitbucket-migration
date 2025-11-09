from typing import Dict, Optional, List, Tuple, Any

from ..clients.bitbucket_client import BitbucketClient
from ..clients.github_client import GitHubClient
from ..utils.logging_config import MigrationLogger
from ..utils.base_dir_manager import BaseDirManager

from dataclasses import dataclass, field
   

class ServiceLocator:
    """Registry for services with attribute-like access."""
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
    
    def register(self, name: str, service: Any):
        self._services[name] = service
    
    def get(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(f"Service '{name}' not registered")
        return self._services[name]
    
    def __getattr__(self, name: str) -> Any:
        """Allow attribute access like locator.user_mapper."""
        return self.get(name)
    
    def __contains__(self, name: str) -> bool:
        return name in self._services
    
    def list_services(self) -> List[str]:
        return list(self._services.keys())


@dataclass
class ClientContext:
    bb: Optional[BitbucketClient] = None
    gh: Optional[GitHubClient] = None

@dataclass
class MigrationEnvironment:
    clients: ClientContext = field(default_factory=ClientContext)
    services: ServiceLocator = field(default_factory=ServiceLocator)
    config: Dict = field(default_factory=dict)
    dry_run: bool = False
    base_dir_manager: Optional[BaseDirManager] = None
    logger: Optional[MigrationLogger] = None
    mode: str = "migrate"  # "migrate" or "cross-link"

@dataclass
class MigrationMappings:
    issues: Dict = field(default_factory=dict)
    issue_types: Dict = field(default_factory=dict)
    prs: Dict = field(default_factory=dict)
    milestones: Dict = field(default_factory=dict)
    # cross_repo: Optional[Tuple[Dict[str, str], Dict[str, Dict[str, Dict[int, int]]]]] = None
    issue_comments: Dict[int,dict] = field(default_factory=dict)
    pr_comments: Dict[int,dict] = field(default_factory=dict)

@dataclass
class MigrationState:
    """Centralized migration state."""
    mappings: MigrationMappings = field(default_factory=MigrationMappings)
    milestone_records: List = field(default_factory=list)
    pr_migration_stats: Dict = field(default_factory=dict)
    services: Dict = field(default_factory=dict)
    issue_records: List[Any] = field(default_factory=list)  # Detailed migration records
    pr_records: List[Any] = field(default_factory=list)  # Detailed migration records
    type_stats: Dict = field(default_factory=dict)
    type_fallbacks: List = field(default_factory=list)
    