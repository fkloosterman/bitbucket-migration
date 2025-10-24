"""
API client modules for Bitbucket and GitHub integration.

This package provides separate, focused clients for interacting with
Bitbucket and GitHub APIs, encapsulating all API-specific logic
and error handling.
"""

from .bitbucket_client import BitbucketClient
from .github_client import GitHubClient

__all__ = [
    'BitbucketClient',
    'GitHubClient'
]