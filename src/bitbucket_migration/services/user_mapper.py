"""
User mapping service for Bitbucket to GitHub migration.

This module handles mapping Bitbucket users to GitHub users, including
resolving account IDs to usernames and handling various user mapping formats.
"""

from typing import Dict, Any, Optional, List
import re
from ..clients.bitbucket_client import BitbucketClient
from ..exceptions import APIError, AuthenticationError, NetworkError

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import UserMapperData


class UserMapper:
    """
    Handles mapping of Bitbucket users to GitHub users.

    This class manages user mappings for @mentions and user references during
    migration, supporting various mapping formats and account ID resolution.
    """

    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the UserMapper.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing user mapping data
        """
        self.environment = environment
        self.state = state

        self.data = UserMapperData()
        self.state.services[self.__class__.__name__] = self.data

        # Handle different config formats (dict during audit, dataclass during migration)
        try:
            self.user_mapping = self.environment.config.user_mapping
        except AttributeError:
            self.user_mapping = {}

        self.bb_client = self.environment.clients.bb
    
    def map_user(self, bb_username: str) -> Optional[str]:
        """
        Map Bitbucket username or display name to GitHub username.

        Args:
            bb_username: Bitbucket username or display name to map

        Returns:
            GitHub username if found, None otherwise
        """
        if not bb_username:
            return None

        # Try direct mapping first (username as key)
        gh_user = self.user_mapping.get(bb_username)

        # Handle enhanced format
        if isinstance(gh_user, dict):
            return gh_user.get('github')

        if gh_user and gh_user != "":
            return gh_user

        # If no direct mapping found, check if this is a display name
        # and try to find the associated username mapping
        for key, value in self.user_mapping.items():
            if isinstance(value, dict):
                # Check if this display name matches any configured display_name
                configured_display_name = value.get('display_name')
                if configured_display_name and configured_display_name == bb_username:
                    github_user = value.get('github')
                    return github_user if github_user != "" else None
            else:
                # For simple string mappings, we can't distinguish username from display name
                # so we skip this case to avoid false positives
                continue

        # No mapping found
        return None
    
    def map_mention(self, bb_username: str) -> Optional[str]:
        """
        Map Bitbucket username (from @mention) to GitHub username.

        This specifically handles @mentions which use Bitbucket usernames,
        not display names. Searches through all mapping formats.

        Also handles account IDs by first resolving them to usernames.

        Args:
            bb_username: Bitbucket username (from @mention) or account ID

        Returns:
            GitHub username if mapped, None if no mapping found
        """
        if not bb_username:
            return None
        
        # First, check if this is an account ID and resolve it to a username
        resolved_username = bb_username
        if bb_username in self.data.account_id_to_username or bb_username in self.data.account_id_to_display_name:
            # Try username first (if available)
            username = self.data.account_id_to_username.get(bb_username)
            display_name = self.data.account_id_to_display_name.get(bb_username)
            
            # Prefer username, but fall back to display_name if username is None
            if username:
                resolved_username = username
            elif display_name:
                resolved_username = display_name
            
            # If the resolved value doesn't map, try the other one
            if resolved_username not in self.user_mapping:
                # Try the alternative
                if username and display_name and display_name in self.user_mapping:
                    resolved_username = display_name
                elif display_name and username and username in self.user_mapping:
                    resolved_username = username
        
        # Try direct mapping (username as key)
        gh_user = self.user_mapping.get(resolved_username)
        
        # Check if it's enhanced format
        if isinstance(gh_user, dict):
            return gh_user.get('github')
        elif gh_user is not None and gh_user != "":
            return gh_user
        
        # Second, search through enhanced format entries for matching bitbucket_username
        for key, value in self.user_mapping.items():
            if isinstance(value, dict):
                if value.get('bitbucket_username') == resolved_username:
                    github_user = value.get('github')
                    # Return None if explicitly set to null (no GitHub account)
                    return github_user if github_user != "" else None
        
        # No mapping found
        return None
    
    def add_account_mapping(self, account_id: str, username: str, display_name: str = None):
        """
        Add account ID to username mapping.

        Args:
            account_id: Bitbucket account ID
            username: Associated Bitbucket username
            display_name: Optional display name for the user
        """
        self.data.account_id_to_username[account_id] = username
        if display_name:
            self.data.account_id_to_display_name[account_id] = display_name

    def build_account_id_mappings(self, bb_issues: List[Dict[str, Any]], bb_prs: List[Dict[str, Any]]) -> int:
        """
        Build mappings from account IDs to usernames by scanning all Bitbucket data.

        This extracts account_id -> username mappings from user objects in the API responses.
        These are needed because @mentions in content sometimes use account IDs instead of usernames.

        Args:
            bb_issues: List of Bitbucket issues to scan
            bb_prs: List of Bitbucket pull requests to scan

        Returns:
            Number of unique account IDs found
        """
        users_found = {}  # account_id -> (username, display_name)
        
        # Scan issues for user information
        for issue in bb_issues:
            # Reporter
            if issue.get('reporter'):
                reporter = issue['reporter']
                account_id = reporter.get('account_id')
                username = reporter.get('username')
                display_name = reporter.get('display_name')
                
                if account_id:
                    if username:
                        self.data.account_id_to_username[account_id] = username
                    if display_name:
                        self.data.account_id_to_display_name[account_id] = display_name
                    if account_id not in users_found:
                        users_found[account_id] = (username, display_name)
            
            # Assignee
            if issue.get('assignee'):
                assignee = issue['assignee']
                account_id = assignee.get('account_id')
                username = assignee.get('username')
                display_name = assignee.get('display_name')
                
                if account_id:
                    if username:
                        self.data.account_id_to_username[account_id] = username
                    if display_name:
                        self.data.account_id_to_display_name[account_id] = display_name
                    if account_id not in users_found:
                        users_found[account_id] = (username, display_name)
        
        # Scan PRs for user information
        for pr in bb_prs:
            # Author
            if pr.get('author'):
                author = pr['author']
                account_id = author.get('account_id')
                username = author.get('username')
                display_name = author.get('display_name')
                
                if account_id:
                    if username:
                        self.data.account_id_to_username[account_id] = username
                    if display_name:
                        self.data.account_id_to_display_name[account_id] = display_name
                    if account_id not in users_found:
                        users_found[account_id] = (username, display_name)
            
            # Participants
            for participant in pr.get('participants', []):
                if participant.get('user'):
                    user = participant['user']
                    account_id = user.get('account_id')
                    username = user.get('username')
                    display_name = user.get('display_name')
                    
                    if account_id:
                        if username:
                            self.data.account_id_to_username[account_id] = username
                        if display_name:
                            self.data.account_id_to_display_name[account_id] = display_name
                        if account_id not in users_found:
                            users_found[account_id] = (username, display_name)
            
            # Reviewers
            for reviewer in pr.get('reviewers', []):
                account_id = reviewer.get('account_id')
                username = reviewer.get('username')
                display_name = reviewer.get('display_name')
                
                if account_id:
                    if username:
                        self.data.account_id_to_username[account_id] = username
                    if display_name:
                        self.data.account_id_to_display_name[account_id] = display_name
                    if account_id not in users_found:
                        users_found[account_id] = (username, display_name)
        
        return len(users_found)

    def lookup_account_id_via_api(self, account_id: str) -> Optional[Dict[str, str]]:
        """
        Look up a Bitbucket account ID using the API.

        Args:
            account_id: The account ID to look up (e.g., "557058:c250d1e9-df76-4236-bc2f-a98d056b56b5")

        Returns:
            Dict with 'username' and 'display_name' if found, None otherwise
        """
        try:
            return self.bb_client.get_user_info(account_id)
        except (APIError, AuthenticationError, NetworkError):
            return None
        except Exception:
            return None

    def scan_comments_for_account_ids(self, bb_issues: List[Dict[str, Any]], bb_prs: List[Dict[str, Any]]) -> None:
        """
        Scan all comments for account IDs to pre-resolve them via API.

        This is needed because account IDs in @mentions within comment text
        are not captured by build_account_id_mappings (which only looks at
        participant metadata).

        Args:
            bb_issues: List of Bitbucket issues to scan
            bb_prs: List of Bitbucket pull requests to scan
        """
        pattern_mention = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_:][a-zA-Z0-9_:-]*)'
        
        unresolved_account_ids = set()
        
        # Scan issue comments
        for issue in bb_issues:
            comments = self.bb_client.get_comments("issue", issue['id'])
            for comment in comments:
                content = comment.get('content', {}).get('raw', '') or ''
                if content and '@' in content:
                    mentions = re.findall(pattern_mention, content)
                    for mention_match in mentions:
                        mention = mention_match[1:-1] if mention_match.startswith('{') else mention_match
                        
                        # Check if it's an account ID
                        is_account_id = ':' in mention or (len(mention) == 24 and all(c in '0123456789abcdef' for c in mention.lower()))
                        
                        if is_account_id and mention not in self.data.account_id_to_username:
                            unresolved_account_ids.add(mention)
        
        # Scan PR comments
        for pr in bb_prs:
            comments = self.bb_client.get_comments("pr", pr['id'])
            for comment in comments:
                content = comment.get('content', {}).get('raw', '') or ''
                if content and '@' in content:
                    mentions = re.findall(pattern_mention, content)
                    for mention_match in mentions:
                        mention = mention_match[1:-1] if mention_match.startswith('{') else mention_match
                        
                        is_account_id = ':' in mention or (len(mention) == 24 and all(c in '0123456789abcdef' for c in mention.lower()))
                        
                        if is_account_id and mention not in self.data.account_id_to_username:
                            unresolved_account_ids.add(mention)
        
        if unresolved_account_ids:
            # Resolve via API
            for account_id in unresolved_account_ids:
                user_info = self.lookup_account_id_via_api(account_id)
                if user_info:
                    username = user_info.get('username') or user_info.get('nickname')
                    display_name = user_info.get('display_name')
                    
                    if username:
                        self.data.account_id_to_username[account_id] = username
                    if display_name:
                        self.data.account_id_to_display_name[account_id] = display_name