"""
Configuration management for Bitbucket to GitHub migration.

This module provides type-safe configuration loading and validation
for the migration process, ensuring all required settings are present
and properly formatted.
"""

from .migration_config import (
    BitbucketConfig,
    GitHubConfig,
    MigrationConfig,
    RepositoryConfig,
    ExternalRepositoryConfig,
    OptionsConfig,
    LinkRewritingConfig,
    ConfigLoader,
    ConfigValidator
)

__all__ = [
    'BitbucketConfig',
    'GitHubConfig',
    'MigrationConfig',
    'RepositoryConfig',
    'ExternalRepositoryConfig',
    'OptionsConfig',
    'LinkRewritingConfig',
    'ConfigLoader',
    'ConfigValidator'
]