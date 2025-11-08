"""
GitHub API client for the migration tool.

This module provides a focused, reusable client for interacting with
the GitHub API, encapsulating all GitHub-specific API logic,
authentication, and error handling.
"""

import requests
import time
from typing import List, Dict, Any, Optional

from ..exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    ValidationError
)


class GitHubClient:
    """
    Client for interacting with the GitHub API.

    This class handles all GitHub API operations including authentication,
    rate limiting, and error handling. It provides a clean interface for
    creating issues, pull requests, comments, and managing repository data.

    Attributes:
        owner (str): GitHub repository owner (user or organization)
        repo (str): GitHub repository name
        token (str): GitHub personal access token
        session (requests.Session): Authenticated session for API calls
        base_url (str): Base URL for repository API endpoints
    """

    def __init__(self, owner: str, repo: str, token: str, dry_run: bool = False) -> None:
        """
        Initialize the GitHub API client.

        Args:
            owner: GitHub repository owner (user or organization)
            repo: GitHub repository name
            token: GitHub personal access token
            dry_run: Whether to simulate API calls without making changes

        Raises:
            ValidationError: If any required parameter is empty
        """
        if not owner or not owner.strip():
            raise ValidationError("GitHub owner cannot be empty")
        if not repo or not repo.strip():
            raise ValidationError("GitHub repository cannot be empty")
        if not token or not token.strip():
            raise ValidationError("GitHub token cannot be empty")

        self.owner = owner
        self.repo = repo
        self.token = token
        self.dry_run = dry_run

        # Separate simulated counters for different types of GitHub objects in dry-run mode
        # GitHub issues and PRs share the same numbering space, milestones have their own
        self.simulated_issue_pr_counter = 1
        self.simulated_milestone_counter = 1

        # Rate limiting state - track per resource type
        self.rate_limits = {
            'core': {'limit': 5000, 'remaining': 5000, 'reset': 0, 'used': 0},
            'search': {'limit': 30, 'remaining': 30, 'reset': 0, 'used': 0},
            'graphql': {'limit': 5000, 'remaining': 5000, 'reset': 0, 'used': 0}
        }

        # Setup authenticated session
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Bitbucket-Migration-Tool/1.0'
        })

        # Base URL for repository API endpoints
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"

    def _update_rate_limits_from_headers(self, headers: dict) -> None:
        """
        Update rate limit tracking from response headers (free, no extra API call).

        Args:
            headers: Response headers from any GitHub API call
        """
        resource = headers.get('X-RateLimit-Resource', 'core')

        # Only track known resources
        if resource not in self.rate_limits:
            return

        try:
            self.rate_limits[resource].update({
                'limit': int(headers.get('X-RateLimit-Limit', self.rate_limits[resource]['limit'])),
                'remaining': int(headers.get('X-RateLimit-Remaining', self.rate_limits[resource]['remaining'])),
                'reset': int(headers.get('X-RateLimit-Reset', self.rate_limits[resource]['reset'])),
                'used': int(headers.get('X-RateLimit-Used', self.rate_limits[resource]['used']))
            })
        except (ValueError, TypeError):
            # If header parsing fails, keep existing values
            pass

    def _calculate_wait_time(self, headers: dict, status_code: int, response_body: dict = None) -> float:
        """
        Calculate optimal wait time based on GitHub's rate limit signals.

        Args:
            headers: Response headers
            status_code: HTTP status code
            response_body: Optional response body (for checking error messages)

        Returns:
            Seconds to wait before retry (0 = no wait needed)
        """
        # Priority 1: Retry-After header (most accurate)
        if 'Retry-After' in headers:
            try:
                wait_time = float(headers['Retry-After'])
                return wait_time
            except (ValueError, TypeError):
                # Invalid Retry-After header, continue to other methods
                pass

        # Priority 2: Rate limit reset for 403 errors
        if status_code == 403:
            reset_time = int(headers.get('X-RateLimit-Reset', 0))
            remaining = int(headers.get('X-RateLimit-Remaining', 1))

            if remaining == 0:
                # We have no remaining quota - this is a primary rate limit
                if reset_time > 0:
                    # Calculate exact wait time from reset
                    wait_time = max(0, reset_time - time.time() + 1)
                    # Cap at 5 minutes for safety (in case of edge cases)
                    wait_time = min(wait_time, 300)
                    return wait_time
                else:
                    # No reset time available, use conservative default
                    return 60
            else:
                # This 403 has remaining quota - check if it's abuse detection/secondary limit
                # by examining the error message
                if response_body and isinstance(response_body, dict):
                    error_msg = response_body.get('message', '').lower()
                    if any(keyword in error_msg for keyword in ['abuse', 'secondary', 'too many requests', 'rate limit']):
                        # This is abuse detection/secondary rate limiting
                        # GitHub recommends waiting "a few minutes" - start with 3 minutes
                        wait_time = 180  # 3 minutes base wait time for secondary limits
                        return wait_time
                
                # Otherwise, it's likely a permission/policy issue - don't retry
                return 0

        # Priority 3: Progressive backoff for 429 (secondary limits)
        if status_code == 429:
            wait_time = 180  # Start with 3 minutes for 429 secondary limits
            return wait_time

        # Priority 4: Calculated wait based on remaining quota
        remaining = int(headers.get('X-RateLimit-Remaining', 100))
        if remaining < 10:
            # We're running low, slow down
            wait_time = 30
            return wait_time
        elif remaining < 50:
            wait_time = 10
            return wait_time

        return 0  # No wait needed

    def _make_request_with_retry(self, method: str, url: str, max_retries: int = 5, **kwargs) -> requests.Response:
        """
        Make an HTTP request with intelligent retry on rate limiting and transient errors.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            max_retries: Maximum number of retries (increased from 3)
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            The original exception after all retries are exhausted
        """
        # Outer loop allows user to restart retries after waiting
        while True:
            last_exception = None
            user_requested_retry = False

            for attempt in range(max_retries + 1):
                try:
                    # Make the request
                    response = self.session.request(method, url, **kwargs)

                    # Update rate limit tracking from headers (free!)
                    self._update_rate_limits_from_headers(response.headers)

                    # Success case
                    if response.status_code < 400:
                        return response

                    # Rate limit error cases
                    if response.status_code in [403, 429]:
                        # Try to get response body for error message checking
                        response_body = None
                        try:
                            response_body = response.json()
                        except (ValueError, AttributeError):
                            pass  # Not JSON or empty body
                        
                        # Detect rate limit type for better user messaging
                        is_secondary = False
                        if response_body and isinstance(response_body, dict):
                            error_msg = response_body.get('message', '').lower()
                            is_secondary = any(keyword in error_msg for keyword in ['abuse', 'secondary'])
                        
                        wait_time = self._calculate_wait_time(response.headers, response.status_code, response_body)
    
                        if attempt < max_retries and wait_time > 0:
                            # Apply exponential backoff multiplier for retries
                            # First retry: base wait time, subsequent retries increase exponentially
                            if attempt > 0:
                                exponential_multiplier = min(2 ** attempt, 8)  # Cap at 8x
                                actual_wait = wait_time * exponential_multiplier
                            else:
                                actual_wait = wait_time
                            
                            # User-friendly message
                            limit_type = "Secondary rate limit" if is_secondary else "Rate limit"
                            print(f"⏳ {limit_type} hit. Waiting {actual_wait:.0f}s before retry {attempt+1}/{max_retries}")
                            time.sleep(actual_wait)
                            continue
                        elif wait_time == 0:
                            # No wait needed, likely a permission issue rather than rate limit
                            # Return response so raise_for_status() can be called
                            return response
                        else:
                            # Cannot retry (either exhausted retries or no wait time needed)
                            # Create the error message with secondary/primary distinction
                            if is_secondary:
                                error_msg = "GitHub API secondary rate limit (abuse detection) exceeded. Please wait before retrying."
                            else:
                                error_msg = "GitHub API rate limit exceeded. Please wait before retrying."
                            api_error = APIError(error_msg)
                            
                            # Call retry exhaustion handler which may prompt user
                            try:
                                self._handle_retry_exhaustion(api_error, url, max_retries, is_secondary)
                                # If we reach here, user chose to continue/skip - re-raise to let caller handle
                                raise api_error
                            except APIError as e:
                                # Check if this is the same error (user wants to retry after waiting)
                                if str(e) == str(api_error):
                                    # User waited and wants to retry - break out of inner loop and restart
                                    user_requested_retry = True
                                    break
                                else:
                                    # Different error, re-raise
                                    raise

                    # For other errors, retry on server errors (5xx) and some client errors
                    if response.status_code >= 500 or response.status_code in [408]:
                        if attempt < max_retries:
                            wait_time = min(2 ** attempt, 30)  # Exponential backoff, max 30 seconds
                            time.sleep(wait_time)
                            continue

                    # If we get here, it's a non-retryable error
                    return response

                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = min(2 ** attempt, 30)
                        time.sleep(wait_time)
                        continue
                    break
            
                except APIError as e:
                    # Check if this is a rate limit error
                    if any(keyword in str(e).lower() for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                        if attempt < max_retries:
                            # Use calculated wait time or exponential backoff for rate limit APIErrors
                            wait_time = min(2 ** attempt, 300)  # Cap at 5 minutes
                            print(f"Rate limit APIError detected. Waiting {wait_time:.0f}s before retry {attempt+1}/{max_retries}")
                            time.sleep(wait_time)
                            continue
                        else:
                            # All retries exhausted - ask user what to do
                            try:
                                # Detect if it's secondary rate limit
                                is_secondary_error = 'secondary' in str(e).lower() or 'abuse' in str(e).lower()
                                self._handle_retry_exhaustion(e, url, max_retries, is_secondary_error)
                                raise  # Re-raise the original APIError
                            except APIError as retry_error:
                                # Check if user wants to retry after waiting
                                if str(retry_error) == str(e):
                                    user_requested_retry = True
                                    break
                                else:
                                    raise
                    else:
                        # Not a rate limit error, don't retry
                        raise

            # Check if user requested retry - if so, restart the outer loop
            if user_requested_retry:
                print(f"🔄 Restarting retry attempts for {url}...")
                continue  # Restart the outer while loop
            
            # All retries exhausted for non-APIError exceptions
            if last_exception:
                raise NetworkError(f"Network error after {max_retries} retries: {last_exception}")
            else:
                raise APIError(f"Request failed after {max_retries} retries")

    def _handle_retry_exhaustion(self, original_error: APIError, url: str, max_retries: int, is_secondary: bool = False) -> None:
        """
        Handle the case when all retries have been exhausted for rate limiting.
        
        Args:
            original_error: The original APIError that triggered the retry exhaustion
            url: The URL that was being accessed
            max_retries: Maximum number of retries that were attempted
            is_secondary: Whether this is a secondary (abuse) rate limit
        """
        import sys
        
        # Check if running in test environment (pytest captures stdin/stdout)
        # or if stdin is not a TTY (non-interactive environment)
        is_tty = sys.stdin.isatty()
        has_pytest = 'pytest' in sys.modules
        
        if not is_tty or has_pytest:
            # In test or non-interactive mode, just re-raise the error without prompting
            raise original_error
        
        print(f"\n{'='*60}")
        print("⚠️  GITHUB API RATE LIMIT - ALL RETRIES EXHAUSTED")
        print(f"{'='*60}")
        print(f"Error: {original_error}")
        print(f"URL: {url}")
        print(f"Max retries: {max_retries}")
        print()
        
        # Check if this is abuse detection (secondary) or primary rate limit
        if is_secondary or 'abuse' in str(original_error).lower() or 'secondary' in str(original_error).lower():
            print("This appears to be GitHub's abuse detection (secondary rate limit).")
            print("Unlike primary rate limits, secondary limits don't have specific reset times.")
            print()
            print("Recommended actions:")
            print("  1. Wait 5-10 minutes before retrying (allows abuse detection to clear)")
            print("  2. Increase config.options.request_delay_seconds (currently controls delays)")
            print("  3. Continue with migration (may hit limit again if pattern persists)")
        else:
            print("This appears to be a primary rate limit (quota exhausted).")
            print("Primary rate limits typically reset at the top of the hour.")
            print()
            print("Recommended actions:")
            print("  1. Wait for rate limit to reset (check GitHub's rate limit status)")
            print("  2. Try again later when limits have reset")
            print("  3. Continue with other repositories and retry this one separately")
        print()
        
        while True:
            try:
                choice = input("What would you like to do? (t)ry again, (w)ait longer, (c)ontinue, or (q)uit: ").strip().lower()
                if choice in ['t', 'try again']:
                    print("🔄 Retrying immediately...")
                    # Reset the attempt counter by re-raising to let the caller handle it
                    raise original_error
                elif choice in ['w', 'wait longer']:
                    # Suggest different defaults based on error type
                    if is_secondary:
                        default_wait = "10"  # Secondary limits typically clear faster
                        print("Note: For secondary rate limits, 10-15 minutes is usually sufficient.")
                    else:
                        default_wait = "60"  # Primary limits reset hourly
                    
                    wait_minutes = int(input(f"How many minutes to wait? (default {default_wait}): ") or default_wait)
                    print(f"⏳ Waiting {wait_minutes} minutes before retrying...")
                    time.sleep(wait_minutes * 60)
                    # After waiting, re-raise to retry
                    raise original_error
                elif choice in ['c', 'continue']:
                    print("⏭️  Skipping current operation and continuing with migration...")
                    # Return without raising - this will cause the caller to continue
                    return
                elif choice in ['q', 'quit']:
                    print("👋 Exiting migration as requested.")
                    raise original_error  # Re-raise to exit gracefully
                else:
                    print("❌ Please enter t, w, c, or q")
            except KeyboardInterrupt:
                print("\n🛑 Migration interrupted by user.")
                raise original_error

    def create_issue(self, title: str, body: str, **kwargs) -> Dict[str, Any]:
        """
        Create a GitHub issue.

        Args:
            title: Issue title
            body: Issue body content
            **kwargs: Additional issue parameters (labels, assignees, milestone, state, issue_type)

        Returns:
            Created GitHub issue data (or simulated data in dry-run mode)

        Raises:
            ValidationError: If title or body is empty
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not title or not title.strip():
            raise ValidationError("Issue title cannot be empty")
        if not body:
            body = ""  # Body can be empty

        # In dry-run mode, return simulated data
        if self.dry_run:
            number = self.simulated_issue_pr_counter
            self.simulated_issue_pr_counter += 1
            return {
                'number': number,
                'title': title.strip(),
                'body': body,
                'state': kwargs.get('state', 'open'),
                'html_url': f"https://github.com/{self.owner}/{self.repo}/issues/{number}"
            }

        payload = {
            'title': title.strip(),
            'body': body,
        }

        # Add optional parameters
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        try:
            response = self._make_request_with_retry('POST', f"{self.base_url}/issues", json=payload)
            response.raise_for_status()
            return response.json()

        except NetworkError:
            # Re-raise NetworkError from _make_request_with_retry
            raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Repository not found: {self.owner}/{self.repo}", status_code=404)
            elif e.response.status_code == 422:
                raise ValidationError(f"Invalid issue data: {e}")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error creating GitHub issue: {e}")

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> Dict[str, Any]:
        """
        Create a GitHub pull request.

        Args:
            title: PR title
            body: PR body content
            head: Source branch name
            base: Target branch name

        Returns:
            Created GitHub PR data (or simulated data in dry-run mode)

        Raises:
            ValidationError: If required parameters are empty
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not title or not title.strip():
            raise ValidationError("PR title cannot be empty")
        if not head or not head.strip():
            raise ValidationError("Head branch cannot be empty")
        if not base or not base.strip():
            raise ValidationError("Base branch cannot be empty")

        # In dry-run mode, return simulated data
        if self.dry_run:
            number = self.simulated_issue_pr_counter
            self.simulated_issue_pr_counter += 1
            return {
                'number': number,
                'title': title.strip(),
                'body': body or "",
                'head': {
                    'sha': 'abc123def456',  # Simulated commit SHA
                    'ref': head.strip()
                },
                'base': {
                    'ref': base.strip()
                },
                'state': 'open',
                'html_url': f"https://github.com/{self.owner}/{self.repo}/pull/{number}"
            }

        payload = {
            'title': title.strip(),
            'body': body or "",
            'head': head.strip(),
            'base': base.strip(),
        }

        try:
            response = self._make_request_with_retry('POST', f"{self.base_url}/pulls", json=payload)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Repository or branches not found: {self.owner}/{self.repo}", status_code=404)
            elif e.response.status_code == 422:
                raise ValidationError(f"Invalid PR data or branch doesn't exist: {e}")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error creating GitHub PR: {e}")

    def get_pull_request(self, pull_number: int) -> Dict[str, Any]:
        """
        Get details of a GitHub pull request.

        Args:
            pull_number: The pull request number

        Returns:
            Pull request data

        Raises:
            ValidationError: If pull_number is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(pull_number, int) or pull_number <= 0:
            raise ValidationError("Pull request number must be a positive integer")

        # Read operations are allowed in dry-run mode
        try:
            response = self._make_request_with_retry('GET', f"{self.base_url}/pulls/{pull_number}")
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Pull request not found: {pull_number}", status_code=404)
            elif e.response.status_code == 403:
                # For PR review comments, 403 might be rate limiting even without proper headers
                # Check if this looks like a rate limit error by examining the response
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('message', '').lower()
                    if any(keyword in error_message for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                        raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                    else:
                        raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
                except (ValueError, AttributeError):
                    # If we can't parse the error message, assume it's rate limiting for PR comments
                    raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except Exception as e:
            raise APIError(f"Unexpected error fetching GitHub pull request: {e}")
    
    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """
        Get details of a GitHub issue.

        Args:
            issue_number: The issue number

        Returns:
            Issue data

        Raises:
            ValidationError: If issue_number is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(issue_number, int) or issue_number <= 0:
            raise ValidationError("Issue number must be a positive integer")

        # Read operations are allowed in dry-run mode
        try:
            response = self._make_request_with_retry('GET', f"{self.base_url}/issues/{issue_number}")
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Issue not found: {issue_number}", status_code=404)
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error fetching GitHub issue: {e}")

    def get_comments(self, issue_number: int) -> List[Dict[str, Any]]:
        """
        Get all comments for a GitHub issue or PR.

        Args:
            issue_number: The issue or PR number

        Returns:
            List of comment dictionaries

        Raises:
            ValidationError: If issue_number is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(issue_number, int) or issue_number <= 0:
            raise ValidationError("Issue number must be a positive integer")

        # Read operations are allowed in dry-run mode
        comments = []
        params = {'per_page': 100}
        url = f"{self.base_url}/issues/{issue_number}/comments"

        try:
            # Paginate through all comments
            while url:
                response = self._make_request_with_retry('GET', url, params=params)
                response.raise_for_status()

                page_data = response.json()
                comments.extend(page_data)

                # Get next page URL from Link header
                link_header = response.headers.get('Link', '')
                url = None
                params = None  # Only use params on first request

                if link_header:
                    # Parse Link header for next page
                    for link in link_header.split(','):
                        if 'rel="next"' in link:
                            url = link[link.index('<')+1:link.index('>')]
                            break

            return comments

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Issue/PR not found: {issue_number}", status_code=404)
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error fetching GitHub comments: {e}")

    def create_comment(self, issue_number: int, body: str) -> Dict[str, Any]:
        """
        Create a comment on a GitHub issue or PR.

        Args:
            issue_number: The issue or PR number
            body: Comment text

        Returns:
            Created comment data (or simulated data in dry-run mode)

        Raises:
            ValidationError: If body is empty or issue_number is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(issue_number, int) or issue_number <= 0:
            raise ValidationError("Issue number must be a positive integer")
        if not body or not body.strip():
            raise ValidationError("Comment body cannot be empty")

        # In dry-run mode, return simulated data
        if self.dry_run:
            return {
                'id': 1,  # Simulated comment ID
                'body': body.strip(),
                'issue_url': f"https://api.github.com/repos/{self.owner}/{self.repo}/issues/{issue_number}",
                'html_url': f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}#issuecomment-1"
            }

        try:
            response = self._make_request_with_retry(
                'POST',
                f"{self.base_url}/issues/{issue_number}/comments",
                json={'body': body.strip()}
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Issue/PR not found: {issue_number}", status_code=404)
            elif e.response.status_code == 422:
                raise ValidationError(f"Invalid comment data: {e}")
            elif e.response.status_code == 403:
                # Check if this is a rate limit, abuse detection, or actually locked issue/PR
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting first
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                        # Check for actual locking
                        elif 'locked' in error_msg:
                            raise ValidationError(f"Issue/PR #{issue_number} is locked and cannot accept new comments")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error creating GitHub comment: {e}")

    def update_comment(self, comment_id: int, body: str) -> Dict[str, Any]:
        """
        Update a GitHub comment.

        Args:
            comment_id: The comment ID to update
            body: New comment text

        Returns:
            Updated comment data (or simulated data in dry-run mode)

        Raises:
            ValidationError: If comment_id is invalid or body is empty
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(comment_id, int) or comment_id <= 0:
            raise ValidationError("Comment ID must be a positive integer")
        if not body or not body.strip():
            raise ValidationError("Comment body cannot be empty")

        # In dry-run mode, return simulated data
        if self.dry_run:
            return {
                'id': comment_id,
                'body': body.strip(),
                'html_url': f"https://github.com/{self.owner}/{self.repo}/issues/1#issuecomment-{comment_id}"
            }

        try:
            response = self._make_request_with_retry(
                'PATCH',
                f"https://api.github.com/repos/{self.owner}/{self.repo}/issues/comments/{comment_id}",
                json={'body': body.strip()}
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Comment not found: {comment_id}", status_code=404)
            elif e.response.status_code == 422:
                raise ValidationError(f"Invalid comment update data: {e}")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error updating GitHub comment: {e}")

    def create_pr_review_comment(self, pull_number: int, body: str, path: str, line: int,
                                   side: str = 'RIGHT', start_line: Optional[int] = None,
                                   start_side: Optional[str] = None, commit_id: Optional[str] = None,
                                   in_reply_to: Optional[int] = None) -> Dict[str, Any]:
        """
        Create an inline comment on a GitHub pull request review.

        Args:
            pull_number: The pull request number
            body: Comment text
            path: File path in the repository
            line: Line number for the comment
            side: 'LEFT' for old file, 'RIGHT' for new file (default: 'RIGHT')
            start_line: Start line for multi-line comments (optional)
            start_side: Side for start line (optional, default: 'RIGHT')
            commit_id: SHA of the commit (optional, but recommended for accuracy)
            in_reply_to: ID of the comment to reply to (optional, for threading)

        Returns:
            Created review comment data (or simulated data in dry-run mode)

        Raises:
            ValidationError: If required parameters are invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(pull_number, int) or pull_number <= 0:
            raise ValidationError("Pull request number must be a positive integer")
        if not body or not body.strip():
            raise ValidationError("Comment body cannot be empty")
        if not path or not path.strip():
            raise ValidationError("File path cannot be empty")
        if not isinstance(line, int) or line <= 0:
            raise ValidationError("Line number must be a positive integer")
        if side not in ['LEFT', 'RIGHT']:
            raise ValidationError("Side must be 'LEFT' or 'RIGHT'")

        # Validate commit_id format if provided
        if commit_id is not None:
            if not isinstance(commit_id, str) or len(commit_id.strip()) == 0:
                raise ValidationError("Commit ID must be a non-empty string")
            commit_id = commit_id.strip()
            # Basic SHA validation (40 hex chars or short SHA)
            if not (len(commit_id) >= 4 and len(commit_id) <= 40 and all(c in '0123456789abcdefABCDEF' for c in commit_id)):
                raise ValidationError("Commit ID must be a valid SHA hash")

        # Validate in_reply_to if provided
        if in_reply_to is not None:
            if not isinstance(in_reply_to, int) or in_reply_to <= 0:
                raise ValidationError("in_reply_to must be a positive integer")

        # In dry-run mode, return simulated data
        if self.dry_run:
            return {
                'id': 1,  # Simulated comment ID
                'body': body.strip(),
                'path': path.strip(),
                'line': line,
                'side': side,
                'html_url': f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}/files#diff-{path}R{line}"
            }

        payload = {
            'body': body.strip(),
            'path': path.strip(),
            'line': line,
            'side': side
        }

        if start_line is not None:
            payload['start_line'] = start_line
        if start_side is not None:
            payload['start_side'] = start_side
        if commit_id is not None:
            payload['commit_id'] = commit_id
        if in_reply_to is not None:
            payload['in_reply_to'] = in_reply_to

        try:
            response = self._make_request_with_retry(
                'POST',
                f"{self.base_url}/pulls/{pull_number}/comments",
                json=payload
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:

            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Pull request or file not found: {pull_number}", status_code=404)
            elif e.response.status_code == 422:
                # Enhanced error handling for 422 errors with detailed diagnostics
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('message', str(e))

                    # Log detailed field-level errors if available
                    errors = error_data.get('errors', [])
                    if errors:
                        print(f"GitHub API Validation Errors:")
                        for error in errors:
                            field = error.get('field', 'unknown')
                            code = error.get('code', 'unknown')
                            msg = error.get('message', 'Unknown error')
                            print(f"  • {field} ({code}): {msg}")

                    # Check for specific validation errors
                    if 'commit_id' in error_message.lower():
                        raise ValidationError(f"Invalid commit_id parameter: {error_message}")
                    elif 'line' in error_message.lower() or 'position' in error_message.lower():
                        raise ValidationError(f"Invalid line number or position: {error_message}")
                    elif 'path' in error_message.lower():
                        raise ValidationError(f"Invalid file path: {error_message}")
                    else:
                        raise ValidationError(f"Invalid review comment data: {error_message}")
                except (ValueError, AttributeError):
                    raise ValidationError(f"Invalid review comment data: {e}")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error creating GitHub PR review comment: {e}")

    def update_issue(self, issue_number: int, **kwargs) -> Dict[str, Any]:
        """
        Update a GitHub issue.

        Args:
            issue_number: The issue number to update
            **kwargs: Fields to update (state, labels, assignees, milestone, etc.)

        Returns:
            Updated issue data (or simulated data in dry-run mode)

        Raises:
            ValidationError: If issue_number is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(issue_number, int) or issue_number <= 0:
            raise ValidationError("Issue number must be a positive integer")

        if not kwargs:
            raise ValidationError("No fields to update")

        # In dry-run mode, return simulated data
        if self.dry_run:
            return {
                'number': issue_number,
                'state': kwargs.get('state', 'open'),
                'html_url': f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"
            }

        try:
            response = self._make_request_with_retry('PATCH', f"{self.base_url}/issues/{issue_number}", json=kwargs)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Issue not found: {issue_number}", status_code=404)
            elif e.response.status_code == 422:
                raise ValidationError(f"Invalid issue update data: {e}")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error updating GitHub issue: {e}")
        
    def update_pull_request(self, pull_number: int, **kwargs) -> Dict[str, Any]:
        """
        Update a GitHub pull request.

        Args:
            pull_number: The pull request number to update
            **kwargs: Fields to update (state, title, body, base, etc.)

        Returns:
            Updated pull request data (or simulated data in dry-run mode)

        Raises:
            ValidationError: If pull_number is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not isinstance(pull_number, int) or pull_number <= 0:
            raise ValidationError("Pull request number must be a positive integer")

        if not kwargs:
            raise ValidationError("No fields to update")

        # In dry-run mode, return simulated data
        if self.dry_run:
            return {
                'number': pull_number,
                'state': kwargs.get('state', 'open'),
                'title': kwargs.get('title', f'Pull Request #{pull_number}'),
                'body': kwargs.get('body', ''),
                'html_url': f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}"
            }

        try:
            response = self._make_request_with_retry('PATCH', f"{self.base_url}/pulls/{pull_number}", json=kwargs)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Pull request not found: {pull_number}", status_code=404)
            elif e.response.status_code == 422:
                raise ValidationError(f"Invalid pull request update data: {e}")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error updating GitHub pull request: {e}")

    def get_issue_types(self, org: str) -> Dict[str, int]:
        """
        Fetch issue types configured for a GitHub organization.

        Args:
            org: Organization name

        Returns:
            Dictionary mapping type name (lowercase) to type ID

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        # Read operations are allowed in dry-run mode
        url = f"https://api.github.com/orgs/{org}/issue-types"

        try:
            response = self._make_request_with_retry('GET', url)
            response.raise_for_status()
            issue_types = response.json()

            type_mapping = {}
            for issue_type in issue_types:
                name = issue_type.get('name', '')
                type_id = issue_type.get('id')
                if name and type_id:
                    # Capitalize the first letter for consistent display
                    capitalized_name = name.capitalize()
                    type_mapping[capitalized_name] = type_id

            return type_mapping

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                # Organization issue types not found - this is normal for personal repos
                return {}
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except (ValueError, AttributeError, TypeError) as e:
            # Handle JSON parsing errors from issue_types
            raise APIError(f"Error parsing issue types response: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error fetching GitHub issue types: {e}")

    def get_milestones(self, state: str = 'all') -> List[Dict[str, Any]]:
        """
        Get all milestones for the repository.
        
        Args:
            state: Filter by state ('open', 'closed', 'all')
        
        Returns:
            List of milestone dictionaries
        
        Raises:
            ValidationError: If state is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if state not in ['open', 'closed', 'all']:
            raise ValidationError("State must be 'open', 'closed', or 'all'")
        
        # Read operations are allowed in dry-run mode
        milestones = []
        params = {'state': state, 'per_page': 100}
        url = f"{self.base_url}/milestones"
        
        try:
            # Paginate through all milestones
            while url:
                response = self._make_request_with_retry('GET', url, params=params)
                response.raise_for_status()
                
                page_data = response.json()
                milestones.extend(page_data)
                
                # Get next page URL from Link header
                link_header = response.headers.get('Link', '')
                url = None
                params = None  # Only use params on first request
                
                if link_header:
                    # Parse Link header for next page
                    for link in link_header.split(','):
                        if 'rel="next"' in link:
                            url = link[link.index('<')+1:link.index('>')]
                            break
            
            return milestones
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Repository not found: {self.owner}/{self.repo}", status_code=404)
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error fetching GitHub milestones: {e}")

    def get_milestone_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """
        Find a milestone by its title (case-sensitive).
        
        Args:
            title: Milestone title to search for
        
        Returns:
            Milestone dict if found, None otherwise
        
        Raises:
            ValidationError: If title is empty
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not title or not title.strip():
            raise ValidationError("Milestone title cannot be empty")
        
        try:
            # Fetch all milestones (both open and closed)
            all_milestones = self.get_milestones(state='all')
            
            # Search for milestone with matching title (case-sensitive)
            for milestone in all_milestones:
                if milestone.get('title') == title.strip():
                    return milestone
            
            return None
        
        except (APIError, AuthenticationError, NetworkError):
            raise  # Re-raise client exceptions
        except Exception as e:
            raise APIError(f"Unexpected error searching for milestone: {e}")

    def create_milestone(self, title: str, state: str = 'open',
                        description: Optional[str] = None,
                        due_on: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new milestone on GitHub.
        
        Args:
            title: Milestone title (required)
            state: 'open' or 'closed' (default: 'open')
            description: Optional milestone description
            due_on: Optional due date (ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ)
        
        Returns:
            Created milestone data with 'number' field
        
        Raises:
            ValidationError: If title is empty or state is invalid
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not title or not title.strip():
            raise ValidationError("Milestone title cannot be empty")
        if state not in ['open', 'closed']:
            raise ValidationError("State must be 'open' or 'closed'")
        
        # In dry-run mode, return simulated data
        if self.dry_run:
            number = self.simulated_milestone_counter
            self.simulated_milestone_counter += 1
            return {
                'number': number,
                'title': title.strip(),
                'state': state,
                'description': description or '',
                'due_on': due_on,
                'html_url': f"https://github.com/{self.owner}/{self.repo}/milestone/{number}"
            }
        
        payload = {
            'title': title.strip(),
            'state': state
        }
        
        if description is not None:
            payload['description'] = description
        if due_on is not None:
            payload['due_on'] = due_on
        
        try:
            response = self._make_request_with_retry(
                'POST',
                f"{self.base_url}/milestones",
                json=payload
            )
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                raise APIError(f"Repository not found: {self.owner}/{self.repo}", status_code=404)
            elif e.response.status_code == 422:
                # Parse error message for more context
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('message', str(e))
                    raise ValidationError(f"Invalid milestone data: {error_message}")
                except (ValueError, AttributeError):
                    raise ValidationError(f"Invalid milestone data: {e}")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error creating GitHub milestone: {e}")

    def check_branch_exists(self, branch_name: str) -> bool:
        """
        Check if a branch exists in the GitHub repository.

        Args:
            branch_name: Name of the branch to check

        Returns:
            True if branch exists, False otherwise

        Raises:
            ValidationError: If branch_name is empty
            APIError: If the API request fails (except 404)
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        if not branch_name or not branch_name.strip():
            raise ValidationError("Branch name cannot be empty")

        # Read operations are allowed in dry-run mode
        try:
            response = self._make_request_with_retry('GET', f"{self.base_url}/branches/{branch_name.strip()}")
            if response.status_code == 200:
                return True
            elif response.status_code == 404:
                return False
            else:
                response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error checking GitHub branch: {e}")

        return False

    def get_repository_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the GitHub repository.

        Returns:
            Repository data from GitHub API

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        # Read operations are allowed in dry-run mode
        try:
            response = self._make_request_with_retry('GET', self.base_url)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 403:
                # Check if this is a rate limit or abuse detection
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get('message', '').lower()
                        # Check for rate limiting
                        if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'abuse', 'blocked']):
                            # Re-raise the APIError so retry logic in _make_request_with_retry can catch it
                            raise APIError("GitHub API rate limit exceeded. Please wait before retrying.")
                except (ValueError, AttributeError, TypeError):
                    pass
                raise AuthenticationError("GitHub API access forbidden. Please check your token permissions.")
            elif e.response.status_code == 404:
                raise APIError(f"Repository not found: {self.owner}/{self.repo}", status_code=404)
            else:
                raise APIError(f"GitHub API error: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error communicating with GitHub API: {e}")
        except APIError:
            # Re-raise APIError to let _make_request_with_retry's retry logic handle rate limits
            raise
        except Exception as e:
            raise APIError(f"Unexpected error fetching GitHub repository info: {e}")

    def test_connection(self, detailed: bool = False) -> bool:
        """
        Test the GitHub API connection.

        Args:
            detailed: If True, also test issues and pull requests endpoints for comprehensive auth validation

        Returns:
            True if connection is successful, False otherwise

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
        """
        # In dry-run mode, always return True
        if self.dry_run:
            return True
        
        # Read operations are allowed in dry-run mode
        try:
            # Try to fetch repository info as a basic connection test
            self.get_repository_info()

            if detailed:
                # Test issues endpoint
                issues_response = self._make_request_with_retry('GET', f"{self.base_url}/issues")
                issues_response.raise_for_status()

                # Test pull requests endpoint
                prs_response = self._make_request_with_retry('GET', f"{self.base_url}/pulls")
                prs_response.raise_for_status()

            return True

        except (APIError, AuthenticationError, NetworkError):
            # Re-raise the specific exceptions
            raise
        except Exception as e:
            raise APIError(f"Unexpected error testing GitHub connection: {e}")