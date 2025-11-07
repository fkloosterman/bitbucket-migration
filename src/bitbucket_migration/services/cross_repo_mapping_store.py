"""
Cross-repository mapping store for multi-repository migrations.

This module manages the shared cross_repo_mappings.json file that coordinates
both repository mappings and issue/PR number mappings across multiple repository migrations.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime

from ..core.migration_context import MigrationEnvironment, MigrationState

class CrossRepoMappingStore:
    """
    Manages cross-repository mappings for multi-repo migrations.

    The store uses a shared JSON file containing both repository mappings
    and issue/PR number mappings, consolidating all cross-repository data
    in a single source of truth.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the cross-repo mapping store.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing mapping data
        """
        self.environment = environment
        self.state = state
        
        # Get dry_run from environment (with backward compatibility)
        self.dry_run = getattr(environment, 'dry_run', False)
        
        self.base_dir_manager = environment.base_dir_manager
        self.mapping_file = self.base_dir_manager.get_mappings_path(dry_run=self.dry_run)
        self.logger = environment.logger
        
        self._repositories: Dict[str, str] = {}
        self._mappings: Dict[str, Dict[str, Dict[int, int]]] = {}
        self._loaded = False

    def load(self) -> Tuple[Dict[str, str], Dict[str, Dict[str, Dict[int, int]]]]:
        """
        Load cross-repository mappings from file.

        Returns:
            Tuple of (repositories, mappings) where:
            - repositories: Dict[repo_key, github_repo]
            - mappings: Dict[repo_key, {issues: {bb: gh}, prs: {bb: gh}}]
        """
        if not self.mapping_file.exists():
            self.logger.info(f"No cross-repository mapping file found at: {self.mapping_file}")
            return {}, {}

        try:
            with open(self.mapping_file, 'r') as f:
                data = json.load(f)

            # New format
            repositories = data['repositories']
            mappings_data = data['mappings']

            # Convert string keys to integers for issue/PR numbers
            mappings = {}
            for repo_key, repo_mappings in mappings_data.items():
                mappings[repo_key] = {
                    'issues': {int(k): v for k, v in repo_mappings.get('issues', {}).items()},
                    'prs': {int(k): v for k, v in repo_mappings.get('prs', {}).items()},
                    'issue_comments': {int(k): v for k, v in repo_mappings.get('issue_comments', {}).items()},
                    'pr_comments': {int(k): v for k, v in repo_mappings.get('pr_comments', {}).items()},
                    'cross_repo_links': {
                        'issues': repo_mappings.get('cross_repo_links', {}).get('issues', []),
                        'issue_comments': {int(k): v for k, v in repo_mappings.get('cross_repo_links', {}).get('issue_comments', {}).items()},
                        'prs': repo_mappings.get('cross_repo_links', {}).get('prs', []),
                        'pr_comments': {int(k): v for k, v in repo_mappings.get('cross_repo_links', {}).get('pr_comments', {}).items()}
                    },
                    'github_repo': repo_mappings.get('github_repo'),
                    'migrated_at': repo_mappings.get('migrated_at')
                }

            self._repositories = repositories
            self._mappings = mappings
            self._loaded = True
            self.logger.info(f"Loaded cross-repository mappings for {len(mappings)} repositories from {self.mapping_file}")
            
            return repositories, mappings

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in cross-repo mappings file: {e}")
            return {}, {}
        except Exception as e:
            self.logger.warning(f"Failed to load cross-repository mappings: {e}")
            return {}, {}

    def save(self, bb_workspace: str, bb_repo: str, gh_owner: str, gh_repo: str,
              issue_mapping: Dict[int, int], pr_mapping: Dict[int, int],
              issue_comment_mapping: Dict[int, dict], pr_comment_mapping: Dict[int, dict]) -> None:
        """
        Save mappings for a repository to the shared file.

        This APPENDS to existing mappings, building up the file incrementally.

        Args:
            bb_workspace: Bitbucket workspace name
            bb_repo: Bitbucket repository name
            gh_owner: GitHub owner name
            gh_repo: GitHub repository name
            issue_mapping: Bitbucket issue # -> GitHub issue # mapping
            pr_mapping: Bitbucket PR # -> GitHub issue/PR # mapping
        """
        repo_key = f"{bb_workspace}/{bb_repo}"

        # Load existing data (handles both old and new formats)
        repositories, mappings = self.load()

        # Add/update current repository mapping
        repositories[repo_key] = f"{gh_owner}/{gh_repo}"
        mappings[repo_key] = {
            'issues': issue_mapping,
            'prs': pr_mapping,
            'issue_comments': {key:c['gh_id'] for key,c in issue_comment_mapping.items()},
            'pr_comments': {key:c['gh_id'] for key,c in pr_comment_mapping.items()},
            'cross_repo_links': self._collect_cross_repo_links(),
            'github_repo': f"{gh_owner}/{gh_repo}",
            'migrated_at': datetime.now().isoformat()
        }

        # Save in consolidated format
        self._save_consolidated_format(repositories, mappings)

        self.logger.info(f"Saved cross-repository mapping to {self.mapping_file}")
        self.logger.info(f"  Repository: {repo_key} ({len(issue_mapping)} issues, {len(pr_mapping)} PRs)")

    def _collect_cross_repo_links(self):

        issues = []
        issue_comments = {}
        prs = []
        pr_comments = {}
        
        for r in self.state.services['LinkRewriter'].details:
            if not r['type']=='cross_repo_link':
                continue
            if r['item_type'] == 'issue':
                if r['comment_id'] is None:
                    issues.append(r['item_number'])
                else:
                    if not r['item_number'] in issue_comments: issue_comments[r['item_number']] = []
                    issue_comments[r['item_number']].append(r['comment_id'])
            elif r['item_type'] == 'pr':
                if r['comment_id'] is None:
                    prs.append(r['item_number'])
                else:
                    if not r['item_number'] in pr_comments: pr_comments[r['item_number']] = []
                    pr_comments[r['item_number']].append(r['comment_id'])
        
        return {'issues': issues, 'issue_comments': issue_comments, 'prs': prs, 'prs_comments': pr_comments}

    def _save_consolidated_format(self, repositories: Dict[str, str],
                                  mappings: Dict[str, Dict[str, Dict[int, int]]]) -> None:
        """Save data in the new consolidated format."""
        data = {
            'repositories': repositories,
            'mappings': mappings
        }

        # Extract workspace and repo from first mapping for tracking
        # (cross-repo files are shared across all repos)
        self.base_dir_manager.create_file(
            self.mapping_file.name,
            data,
            subcommand='system',
            category='cross-repo-mapping'
        )
        
    def get_repository_mapping(self) -> Dict[str, str]:
        """Get the repository mapping (repo_key -> github_repo)."""
        if not self._loaded:
            self.load()
        return self._repositories.copy()

    def set_repository_mapping(self, repo_mapping: Dict[str, str]) -> None:
        """Set the repository mapping."""
        self._repositories = repo_mapping.copy()

    def get_mapped_repository(self, bb_workspace: str, bb_repo:str) -> Tuple[str, str]:
        if not self._loaded:
            self.load()
        
        mapped_repo = self._repositories.get(f"{bb_workspace}/{bb_repo}")
        
        if not mapped_repo:
            return None, None
        elif '/' in mapped_repo:
            return mapped_repo.split('/', 1)
        else:
            return None, mapped_repo

    def get_mapping(self, bb_workspace: str, bb_repo: str, mapping: Optional[str] = None):
        if not self._loaded:
            self.load()

        repo_key = f"{bb_workspace}/{bb_repo}"

        if mapping:
            return self._mappings.get(repo_key, {}).get(mapping, {})
        else:
            return self._mappings.get(repo_key)

    def get_issue_mapping(self, bb_workspace: str, bb_repo: str) -> Dict[int, int]:
        """Get issue mapping for a specific repository."""
        if not self._loaded:
            self.load()

        repo_key = f"{bb_workspace}/{bb_repo}"
        return self._mappings.get(repo_key, {}).get('issues', {})

    def get_pr_mapping(self, bb_workspace: str, bb_repo: str) -> Dict[int, int]:
        """Get PR mapping for a specific repository."""
        if not self._loaded:
            self.load()

        repo_key = f"{bb_workspace}/{bb_repo}"
        return self._mappings.get(repo_key, {}).get('prs', {})

    def has_repository(self, bb_workspace: str, bb_repo: str) -> bool:
        """Check if repository has been migrated and is in mappings."""
        if not self._loaded:
            self.load()

        repo_key = f"{bb_workspace}/{bb_repo}"
        return repo_key in self._mappings


class CrossLinkMappingStore(CrossRepoMappingStore):
    """
    Specialized mapping store for cross-link processing that prioritizes
    real migration mappings but falls back to dry-run mappings only when
    cross-link processing is run in dry-run mode.
    """
    
    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the cross-link mapping store with fallback logic.
        
        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing mapping data
        """
        # Call parent constructor to initialize environment, state, logger, etc.
        super().__init__(environment, state)
        
        # Override the mapping file selection with fallback logic
        self.mapping_file, self._fallback_used = self._select_mapping_file()
    
    def _select_mapping_file(self) -> Tuple[Path, bool]:
        """
        Select the appropriate mapping file with conditional fallback logic.
        
        Real mode (dry_run=False):
        - Only use real migration mappings (cross_repo_mappings.json)
        - Error if not available
        
        Dry-run mode (dry_run=True):
        - Priority 1: Real migration mappings (cross_repo_mappings.json)
        - Priority 2: Dry-run mappings (cross_repo_mappings_dry_run.json) with warning
        
        Returns:
            Tuple of (selected_file_path, fallback_used)
        """
        real_mappings = self.base_dir_manager.get_mappings_path(dry_run=False)
        dry_run_mappings = self.base_dir_manager.get_mappings_path(dry_run=True)
        
        if real_mappings.exists():
            self.logger.info(f"Using real migration mappings: {real_mappings}")
            return real_mappings, False
        elif self.dry_run and dry_run_mappings.exists():
            # Only fallback to dry-run mappings if cross-link is also in dry-run mode
            self.logger.warning(f"Real migration mappings not found at {real_mappings}")
            self.logger.warning(f"Falling back to dry-run mappings: {dry_run_mappings}")
            self.logger.warning("Cross-link processing will use dry-run data. Consider running real migration first.")
            return dry_run_mappings, True
        else:
            # No fallback - either not in dry-run mode or no dry-run mappings available
            self.logger.error(f"No cross-repository mappings found!")
            self.logger.error(f"  Real migration: {real_mappings}")
            if self.dry_run:
                self.logger.error(f"  Dry-run: {dry_run_mappings}")
                self.logger.error("For dry-run cross-link processing, ensure at least one migration (real or dry-run) has been completed.")
            else:
                self.logger.error("For real cross-link processing, ensure real migration has been completed first.")
                self.logger.error("Run 'migrate' command before 'cross-link' command.")
            # Return the real mappings path even if it doesn't exist, for error reporting
            return real_mappings, False
