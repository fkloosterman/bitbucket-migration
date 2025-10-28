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

logger = logging.getLogger('bitbucket_migration')


class CrossRepoMappingStore:
    """
    Manages cross-repository mappings for multi-repo migrations.

    The store uses a shared JSON file containing both repository mappings
    and issue/PR number mappings, consolidating all cross-repository data
    in a single source of truth.
    """

    def __init__(self, mapping_file: Optional[str] = None):
        """
        Initialize the cross-repo mapping store.

        Args:
            mapping_file: Path to mapping file. Defaults to cross_repo_mappings.json
        """
        self.mapping_file = Path(mapping_file) if mapping_file else Path('cross_repo_mappings.json')
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
            logger.info(f"No cross-repository mapping file found at: {self.mapping_file}")
            return {}, {}

        try:
            with open(self.mapping_file, 'r') as f:
                data = json.load(f)

            # Check if this is the new consolidated format
            if 'repositories' in data and 'mappings' in data:
                # New format
                repositories = data['repositories']
                mappings_data = data['mappings']

                # Convert string keys to integers for issue/PR numbers
                mappings = {}
                for repo_key, repo_mappings in mappings_data.items():
                    mappings[repo_key] = {
                        'issues': {int(k): v for k, v in repo_mappings.get('issues', {}).items()},
                        'prs': {int(k): v for k, v in repo_mappings.get('prs', {}).items()},
                        'github_repo': repo_mappings.get('github_repo'),
                        'migrated_at': repo_mappings.get('migrated_at')
                    }

                self._repositories = repositories
                self._mappings = mappings
                self._loaded = True
                logger.info(f"Loaded consolidated cross-repository mappings for {len(mappings)} repositories from {self.mapping_file}")
                return repositories, mappings

            else:
                # Old format - convert to new format
                logger.warning(f"Detected old cross_repo_mappings.json format. Converting to new consolidated format.")

                repositories = {}
                mappings = {}

                # Convert old format to new format
                for repo_key, repo_mappings in data.items():
                    mappings[repo_key] = {
                        'issues': {int(k): v for k, v in repo_mappings.get('issues', {}).items()},
                        'prs': {int(k): v for k, v in repo_mappings.get('prs', {}).items()},
                        'github_repo': repo_mappings.get('github_repo'),
                        'migrated_at': repo_mappings.get('migrated_at')
                    }

                self._repositories = repositories  # Empty for old format
                self._mappings = mappings
                self._loaded = True

                # Save in new format
                self._save_consolidated_format(repositories, mappings)
                logger.info(f"Converted and saved mappings in new consolidated format")

                return repositories, mappings

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in cross-repo mappings file: {e}")
            return {}, {}
        except Exception as e:
            logger.warning(f"Failed to load cross-repository mappings: {e}")
            return {}, {}

    def save(self, bb_workspace: str, bb_repo: str, gh_owner: str, gh_repo: str,
              issue_mapping: Dict[int, int], pr_mapping: Dict[int, int]) -> None:
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
            'github_repo': f"{gh_owner}/{gh_repo}",
            'migrated_at': datetime.now().isoformat()
        }

        # Save in consolidated format
        self._save_consolidated_format(repositories, mappings)

        logger.info(f"Saved cross-repository mapping to {self.mapping_file}")
        logger.info(f"  Repository: {repo_key} ({len(issue_mapping)} issues, {len(pr_mapping)} PRs)")

    def _save_consolidated_format(self, repositories: Dict[str, str],
                                  mappings: Dict[str, Dict[str, Dict[int, int]]]) -> None:
        """Save data in the new consolidated format."""
        data = {
            'repositories': repositories,
            'mappings': mappings
        }

        with open(self.mapping_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_repository_mapping(self) -> Dict[str, str]:
        """Get the repository mapping (repo_key -> github_repo)."""
        if not self._loaded:
            self.load()
        return self._repositories.copy()

    def set_repository_mapping(self, repo_mapping: Dict[str, str]) -> None:
        """Set the repository mapping."""
        self._repositories = repo_mapping.copy()

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