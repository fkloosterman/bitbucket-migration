"""
Milestone migrator for Bitbucket to GitHub migration.

This module contains the MilestoneMigrator class that handles the migration
of Bitbucket milestones to GitHub, including duplicate detection and
metadata preservation.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from ..exceptions import APIError, AuthenticationError, NetworkError, ValidationError

from ..core.migration_context import MigrationState, MigrationEnvironment

class MilestoneMigrator:
    """
    Handles migration of Bitbucket milestones to GitHub.

    This class encapsulates all logic related to milestone migration, including
    fetching, duplicate detection, creating, and tracking migration progress.
    """

    def __init__(self,
                 environment: MigrationEnvironment,
                 state: MigrationState
                 ):
        """
        Initialize the MilestoneMigrator.

        Args:
            environment: Migration environment containing all services and configuration
            state: Migration state containing mappings and records
        """

        self.environment = environment
        self.state = state

    def migrate_milestones(self, open_milestones_only: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Migrate all Bitbucket milestones to GitHub.

        Returns:
            milestone_lookup: Dict mapping milestone name to GitHub milestone data
                             including 'number', 'title', 'state', etc.
        """
        self.environment.logger.info("Fetching Bitbucket milestones...")

        # Step 1: Fetch Bitbucket milestones
        try:
            bb_milestones = self.environment.clients.bb.get_milestones()
            self.environment.logger.info(f"  Found {len(bb_milestones)} milestones in Bitbucket")
        except (APIError, AuthenticationError, NetworkError) as e:
            self.environment.logger.warning(f"  Warning: Could not fetch Bitbucket milestones: {e}")
            return {}
        except Exception as e:
            self.environment.logger.warning(f"  Warning: Unexpected error fetching Bitbucket milestones: {e}")
            return {}

        if not bb_milestones:
            self.environment.logger.info("  No milestones to migrate")
            return {}

        # Step 2: Fetch existing GitHub milestones for duplicate detection
        try:
            existing_gh_milestones = self.environment.clients.gh.get_milestones(state='all')
            self.environment.logger.info(f"  Found {len(existing_gh_milestones)} existing milestones on GitHub")
        except (APIError, AuthenticationError, NetworkError) as e:
            self.environment.logger.warning(f"  Warning: Could not fetch existing GitHub milestones: {e}")
            existing_gh_milestones = []
        except Exception as e:
            self.environment.logger.warning(f"  Warning: Unexpected error fetching GitHub milestones: {e}")
            existing_gh_milestones = []

        # Step 3: Process each Bitbucket milestone
        for bb_milestone in bb_milestones:
            milestone_name = bb_milestone.get('name')
            
            if not milestone_name:
                self.environment.logger.warning("  Skipping milestone with no name")
                continue
            
            if open_milestones_only and bb_milestone.get('state', 'open') == 'closed':
                self.environment.logger.info(f"  Skipping closed milestone {milestone_name}")
                continue

            self.environment.logger.info(f"  Processing milestone: {milestone_name}")

            # Check for duplicates
            existing_milestone = self._check_duplicate(milestone_name, existing_gh_milestones)

            if existing_milestone:
                # Use existing milestone
                self.environment.logger.warning(f"    ⚠️  Milestone '{milestone_name}' already exists on GitHub (#{existing_milestone['number']})")
                self.state.mappings.milestones[milestone_name] = existing_milestone

                # Record as duplicate
                self.state.milestone_records.append({
                    'bb_name': milestone_name,
                    'gh_number': existing_milestone['number'],
                    'gh_title': existing_milestone['title'],
                    'state': existing_milestone['state'],
                    'description': existing_milestone.get('description', ''),
                    'due_date': existing_milestone.get('due_on', ''),
                    'is_duplicate': True,
                    'remarks': ['Already existed on GitHub', 'Reused existing milestone']
                })
            else:
                # Create new milestone
                try:
                    gh_milestone = self._create_milestone(bb_milestone)
                    self.state.mappings.milestones[milestone_name] = gh_milestone
                    self.environment.logger.info(f"    ✓ Created milestone #{gh_milestone['number']}: {milestone_name}")

                    # Record creation
                    self.state.milestone_records.append({
                        'bb_name': milestone_name,
                        'gh_number': gh_milestone['number'],
                        'gh_title': gh_milestone['title'],
                        'state': gh_milestone['state'],
                        'description': gh_milestone.get('description', ''),
                        'due_date': gh_milestone.get('due_on', ''),
                        'is_duplicate': False,
                        'remarks': ['Created successfully']
                    })

                except (APIError, AuthenticationError, NetworkError, ValidationError) as e:
                    self.environment.logger.error(f"    ✗ Failed to create milestone '{milestone_name}': {e}")
                    # Record failure
                    self.state.milestone_records.append({
                        'bb_name': milestone_name,
                        'gh_number': None,
                        'gh_title': milestone_name,
                        'state': 'N/A',
                        'description': bb_milestone.get('description', ''),
                        'due_date': bb_milestone.get('due_on', ''),
                        'is_duplicate': False,
                        'remarks': [f'Failed to create: {str(e)}']
                    })
                except Exception as e:
                    self.environment.logger.error(f"    ✗ Unexpected error creating milestone '{milestone_name}': {e}")
                    self.state.milestone_records.append({
                        'bb_name': milestone_name,
                        'gh_number': None,
                        'gh_title': milestone_name,
                        'state': 'N/A',
                        'description': bb_milestone.get('description', ''),
                        'due_date': bb_milestone.get('due_on', ''),
                        'is_duplicate': False,
                        'remarks': [f'Unexpected error: {str(e)}']
                    })

        # Step 4: Return milestone lookup for use by issue/PR migrators
        self.environment.logger.info(f"  Milestone migration complete: {len(self.state.mappings.milestones)} milestones available")
        return self.state.mappings.milestones

    def _check_duplicate(self, milestone_name: str, 
                         existing_milestones: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Check if a milestone with the same name already exists.

        Args:
            milestone_name: Name to check
            existing_milestones: List of existing GitHub milestones

        Returns:
            Existing milestone dict if found, None otherwise
        """
        for milestone in existing_milestones:
            if milestone.get('title') == milestone_name:
                return milestone
        return None

    def _create_milestone(self, bb_milestone: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a GitHub milestone from Bitbucket milestone data.

        Args:
            bb_milestone: Bitbucket milestone dictionary

        Returns:
            Created GitHub milestone data

        Raises:
            APIError: If the API request fails
            AuthenticationError: If authentication fails
            NetworkError: If there's a network connectivity issue
            ValidationError: If milestone data is invalid
        """
        # Extract fields from bb_milestone
        name = bb_milestone.get('name')
        description = bb_milestone.get('description', '')
        state = bb_milestone.get('state', 'open')
        due_on = bb_milestone.get('due_on')

        # Map state: Bitbucket uses same values as GitHub ('open'/'closed')
        if state not in ['open', 'closed']:
            state = 'open'  # Default to open if unknown state

        # Format due_on date if present
        formatted_due_on = self._format_date(due_on) if due_on else None

        # Create milestone on GitHub
        try:
            gh_milestone = self.environment.clients.gh.create_milestone(
                title=name,
                state=state,
                description=description if description else None,
                due_on=formatted_due_on
            )
            return gh_milestone

        except ValidationError as e:
            # If due date is invalid, try creating without it
            if 'due_on' in str(e).lower() or 'due date' in str(e).lower():
                self.environment.logger.warning(f"    Invalid due date format, creating milestone without due date")
                gh_milestone = self.environment.clients.gh.create_milestone(
                    title=name,
                    state=state,
                    description=description if description else None,
                    due_on=None
                )
                return gh_milestone
            else:
                raise  # Re-raise other validation errors

    def _format_date(self, date_str: str) -> Optional[str]:
        """
        Format Bitbucket date to GitHub-compatible ISO 8601 format.

        GitHub expects: YYYY-MM-DDTHH:MM:SSZ
        Bitbucket provides: ISO 8601 format (should be compatible)

        Args:
            date_str: Bitbucket date string

        Returns:
            GitHub-compatible date string or None if invalid
        """
        if not date_str:
            return None

        try:
            # Try parsing the date to validate it
            if date_str.endswith('+00:00'):
                # Convert +00:00 to Z for GitHub
                date_str = date_str.replace('+00:00', 'Z')
            elif not date_str.endswith('Z'):
                # Ensure it ends with Z
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date_str = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            return date_str

        except (ValueError, AttributeError) as e:
            self.environment.logger.warning(f"    Could not parse date '{date_str}': {e}")
            return None