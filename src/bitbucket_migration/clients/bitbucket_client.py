"""
Bitbucket API client for the migration tool.

This module provides a focused, reusable client for interacting with
the Bitbucket API, encapsulating all Bitbucket-specific API logic,
authentication, and error handling.
"""

import requests
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from ..exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    ValidationError
)


class BitbucketClient:
    """
    Client for interacting with the Bitbucket API.

    This class handles all Bitbucket API operations including authentication,
    pagination, and error handling. It provides a clean interface for fetching
    issues, pull requests, comments, attachments, and other repository data.

    Attributes:
        workspace (str): Bitbucket workspace name
        repo (str): Bitbucket repository name
        email (str): User email for API authentication
        token (str): Bitbucket API token
        session (requests.Session): Authenticated session for API calls
        base_url (str): Base URL for repository API endpoints
        dry_run (bool): Whether to simulate API calls without making changes
    """

    def __init__(self, workspace: str, repo: str, email: str, token: str, dry_run: bool = False) -> None:
        """
        Initialize the Bitbucket API client.

        Args:
            workspace: Bitbucket workspace name
            repo: Bitbucket repository name
            email: User email for API authentication
            token: Bitbucket API token

        Raises:
            ValidationError: If any required parameter is empty
        """
        if not workspace or not workspace.strip():
            raise ValidationError("Bitbucket workspace cannot be empty")
        if not repo or not repo.strip():
            raise ValidationError("Bitbucket repository cannot be empty")
        if not email or not email.strip():
            raise ValidationError("Bitbucket email cannot be empty")
        if not token or not token.strip():
            raise ValidationError("Bitbucket token cannot be empty")

        self.workspace = workspace
        self.repo = repo
        self.email = email
        self.token = token
        self.dry_run = dry_run

        # Setup authenticated session
        self.session = requests.Session()
        self.session.auth = (email, token)

        # Base URL for repository API endpoints
        self.base_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}"

    def list_repositories(self) -> List[Dict[str, Any]]:
        """
        List all repositories in the workspace.

        Returns:
            List of repository dictionaries

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        url = f"https://api.bitbucket.org/2.0/repositories/{self.workspace}"
        repos = []
        
        while url:
            try:
                response = self.session.get(url)
                response.raise_for_status()
                data = response.json()
                
                repos.extend(data.get('values', []))
                url = data.get('next')
                
            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    raise AuthenticationError("Bitbucket API authentication failed. Please check your credentials.")
                elif response.status_code == 403:
                    raise AuthenticationError("Bitbucket API access forbidden. Please check your token permissions.")
                elif response.status_code == 404:
                    raise APIError(f"Workspace not found: {self.workspace}", status_code=404)
                else:
                    raise APIError(f"Bitbucket API error: {e}", status_code=response.status_code)
            except requests.exceptions.RequestException as e:
                raise NetworkError(f"Network error communicating with Bitbucket API: {e}")
            except Exception as e:
                raise APIError(f"Unexpected error fetching repositories: {e}")
        
        return repos

    def get_issues(self) -> List[Dict[str, Any]]:
        """
        Fetch all issues from the Bitbucket repository.

        Returns:
            List of issue dictionaries sorted by ID

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        url = f"{self.base_url}/issues"
        params = {'pagelen': 100, 'sort': 'id'}

        issues = []
        next_url = url

        while next_url:
            try:
                response = self.session.get(next_url, params=params if next_url == url else None)
                response.raise_for_status()
                data = response.json()

                issues.extend(data.get('values', []))
                next_url = data.get('next')
                params = None

            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    raise AuthenticationError("Bitbucket API authentication failed. Please check your credentials.")
                elif response.status_code == 403:
                    raise AuthenticationError("Bitbucket API access forbidden. Please check your token permissions.")
                elif response.status_code == 404:
                    raise APIError(f"Repository not found: {self.workspace}/{self.repo}", status_code=404)
                else:
                    raise APIError(f"Bitbucket API error: {e}", status_code=response.status_code)
            except requests.exceptions.RequestException as e:
                raise NetworkError(f"Network error communicating with Bitbucket API: {e}")
            except Exception as e:
                raise APIError(f"Unexpected error fetching Bitbucket issues: {e}")

        return sorted(issues, key=lambda x: x['id'])

    def get_pull_requests(self) -> List[Dict[str, Any]]:
        """
        Fetch all pull requests from the Bitbucket repository.

        Returns:
            List of pull request dictionaries sorted by ID

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        url = f"{self.base_url}/pullrequests"
        params = {'state': 'MERGED,SUPERSEDED,OPEN,DECLINED', 'pagelen': 50, 'sort': 'id'}

        prs = []
        next_url = url

        while next_url:
            try:
                response = self.session.get(next_url, params=params if next_url == url else None)
                response.raise_for_status()
                data = response.json()

                prs.extend(data.get('values', []))
                next_url = data.get('next')
                params = None

            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    raise AuthenticationError("Bitbucket API authentication failed. Please check your credentials.")
                elif response.status_code == 403:
                    raise AuthenticationError("Bitbucket API access forbidden. Please check your token permissions.")
                elif response.status_code == 404:
                    raise APIError(f"Repository not found: {self.workspace}/{self.repo}", status_code=404)
                else:
                    raise APIError(f"Bitbucket API error: {e}", status_code=response.status_code)
            except requests.exceptions.RequestException as e:
                raise NetworkError(f"Network error communicating with Bitbucket API: {e}")
            except Exception as e:
                raise APIError(f"Unexpected error fetching Bitbucket pull requests: {e}")

        return sorted(prs, key=lambda x: x['id'])

    def get_milestones(self) -> List[Dict[str, Any]]:
        """
        Fetch all milestones from the Bitbucket repository.

        Returns:
            List of milestone dictionaries

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        url = f"{self.base_url}/milestones"
        params = {'pagelen': 100}

        try:
            return self._paginate(url, params)
        except (APIError, AuthenticationError, NetworkError):
            raise  # Re-raise API-related errors
        except Exception as e:
            raise APIError(f"Unexpected error fetching Bitbucket milestones: {e}")

    def get_comments(self, item_type: str, item_id: int) -> List[Dict[str, Any]]:
        """
        Fetch comments for a Bitbucket issue or pull request.

        Args:
            item_type: Either 'issue' or 'pr'
            item_id: The issue or PR ID

        Returns:
            List of comment dictionaries

        Raises:
            ValidationError: If item_type is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        import logging
        logger = logging.getLogger(__name__)

        if item_type not in ['issue', 'pr']:
            raise ValidationError(f"Invalid item type: {item_type}. Must be 'issue' or 'pr'")

        endpoint = "issues" if item_type == "issue" else "pullrequests"
        url = f"{self.base_url}/{endpoint}/{item_id}/comments"

        logger.debug(f"Fetching comments for {item_type} #{item_id}")

        try:
            comments = self._paginate(url)
            logger.debug(f"Total comments fetched for {item_type} #{item_id}: {len(comments)}")
            return comments
        except (APIError, AuthenticationError, NetworkError):
            raise  # Re-raise API-related errors
        except Exception as e:
            raise APIError(f"Unexpected error fetching Bitbucket comments: {e}")

    def get_activity(self, pr_id: int) -> List[Dict[str, Any]]:
        """
        Fetch activity log for a Bitbucket pull request.

        Args:
            pr_id: The pull request ID

        Returns:
            List of activity dictionaries

        Raises:
            ValidationError: If pr_id is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(pr_id, int) or pr_id <= 0:
            raise ValidationError("Pull request ID must be a positive integer")

        url = f"{self.base_url}/pullrequests/{pr_id}/activity"

        try:
            return self._paginate(url)
        except (APIError, AuthenticationError, NetworkError):
            raise  # Re-raise API-related errors
        except Exception as e:
            raise APIError(f"Unexpected error fetching Bitbucket PR activity: {e}")

    def get_attachments(self, item_type: str, item_id: int) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a Bitbucket issue or pull request.

        Args:
            item_type: Either 'issue' or 'pr'
            item_id: The issue or PR ID

        Returns:
            List of attachment dictionaries

        Raises:
            ValidationError: If item_type is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if item_type not in ['issue', 'pr']:
            raise ValidationError(f"Invalid item type: {item_type}. Must be 'issue' or 'pr'")

        endpoint = "issues" if item_type == "issue" else "pullrequests"
        url = f"{self.base_url}/{endpoint}/{item_id}/attachments"

        try:
            return self._paginate(url)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # No attachments found - this is normal, especially for PRs where attachments API may not exist
                return []
            elif e.response.status_code == 401:
                raise AuthenticationError("Bitbucket API authentication failed. Please check your credentials.")
            elif e.response.status_code == 403:
                raise AuthenticationError("Bitbucket API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"Bitbucket API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with Bitbucket API: {e}")
        except (APIError, AuthenticationError, NetworkError):
            raise  # Re-raise API-related errors
        except Exception as e:
            raise APIError(f"Unexpected error fetching Bitbucket attachments: {e}")

    def get_changes(self, issue_id: int) -> List[Dict[str, Any]]:
        """
        Fetch changes for a Bitbucket issue.

        This method retrieves the change history for an issue, which includes
        modifications like status changes, assignee updates, etc., that are
        associated with comments.

        Args:
            issue_id: The Bitbucket issue ID

        Returns:
            List of change dictionaries

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        url = f"{self.base_url}/issues/{issue_id}/changes"

        try:
            return self._paginate(url)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # No changes found - this is normal for issues without changes
                return []
            elif e.response.status_code == 401:
                raise AuthenticationError("Bitbucket API authentication failed. Please check your credentials.")
            elif e.response.status_code == 403:
                raise AuthenticationError("Bitbucket API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"Bitbucket API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with Bitbucket API: {e}")
        except (APIError, AuthenticationError, NetworkError):
            raise  # Re-raise API-related errors
        except Exception as e:
            raise APIError(f"Unexpected error fetching Bitbucket issue changes: {e}")

    def get_user_info(self, account_id: str) -> Optional[Dict[str, str]]:
        """
        Look up user information by account ID.

        Args:
            account_id: The Bitbucket account ID to look up

        Returns:
            User information dictionary with username and display_name, or None if not found

        Raises:
            APIError: If the API request fails (except 404)
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        url = f"https://api.bitbucket.org/2.0/users/{account_id}"

        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                user_data = response.json()
                return {
                    'username': user_data.get('username'),
                    'nickname': user_data.get('nickname'),
                    'display_name': user_data.get('display_name'),
                    'account_id': user_data.get('account_id')
                }
            elif response.status_code == 404:
                # User not found (deleted account, etc.) - this is expected
                return None
            else:
                response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Bitbucket API authentication failed. Please check your credentials.")
            elif e.response.status_code == 403:
                raise AuthenticationError("Bitbucket API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"Bitbucket API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with Bitbucket API: {e}")
        except Exception as e:
            raise APIError(f"Unexpected error looking up Bitbucket user: {e}")

        return None

    def _paginate(self, url: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Fetch all pages of results from a Bitbucket API endpoint.

        Args:
            url: The API endpoint URL to paginate
            params: Optional query parameters for the first request

        Returns:
            List of all items from all pages

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        results = []
        next_url = url
        first_request = True

        while next_url:
            try:
                if first_request and params:
                    response = self.session.get(next_url, params=params)
                    first_request = False
                else:
                    response = self.session.get(next_url)

                response.raise_for_status()
                data = response.json()

                if 'values' in data:
                    values = data['values']
                    results.extend(values)
                else:
                    results.append(data)

                next_url = data.get('next')

            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    raise AuthenticationError("Bitbucket API authentication failed. Please check your credentials.")
                elif response.status_code == 403:
                    raise AuthenticationError("Bitbucket API access forbidden. Please check your token permissions.")
                elif response.status_code == 404:
                    # API endpoint not found - this can happen for PR attachments or other optional endpoints
                    # Return empty results instead of raising an error
                    return []
                elif response.status_code == 502:
                    # Bad Gateway - API instability, but we already have results from previous pages
                    if len(results) > 0:
                        # Return what we have so far instead of failing completely
                        return results
                    else:
                        raise APIError(f"Bitbucket API error: {e}", status_code=response.status_code)
                else:
                    raise APIError(f"Bitbucket API error: {e}", status_code=response.status_code)
            except requests.exceptions.RequestException as e:
                raise NetworkError(f"Network error communicating with Bitbucket API: {e}")
            except Exception as e:
                raise APIError(f"Unexpected error during Bitbucket API pagination: {e}")

        return results

    def test_connection(self, detailed: bool = False) -> bool:
        """
        Test the Bitbucket API connection.

        Args:
            detailed: If True, also test issues and pull requests endpoints for comprehensive auth validation

        Returns:
            True if connection is successful, False otherwise

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        # In dry-run mode, skip API calls
        if self.dry_run:
            return True
            
        try:
            # Try to fetch repository info as a basic connection test
            url = f"{self.base_url}"
            response = self.session.get(url)
            response.raise_for_status()

            if detailed:
                # Test issues endpoint
                issues_url = f"{self.base_url}/issues"
                issues_response = self.session.get(issues_url)
                issues_response.raise_for_status()

                # Test pull requests endpoint
                prs_url = f"{self.base_url}/pullrequests"
                prs_response = self.session.get(prs_url)
                prs_response.raise_for_status()

            return True

        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise AuthenticationError("Bitbucket API authentication failed. Please check your credentials.")
            elif response.status_code == 403:
                raise AuthenticationError("Bitbucket API access forbidden. Please check your token permissions.")
            elif response.status_code == 404:
                raise APIError(f"Repository not found: {self.workspace}/{self.repo}", status_code=404)
            else:
                raise APIError(f"Bitbucket API error: {e}", status_code=response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error testing Bitbucket connection: {e}")
        except Exception as e:
            raise APIError(f"Unexpected error testing Bitbucket connection: {e}")