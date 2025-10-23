#!/usr/bin/env python3
"""
Bitbucket to GitHub Migration Script

⚠️  DISCLAIMER: This migration tool was developed with assistance from Claude.ai, an AI language model.
   Use at your own risk. Always perform dry runs and verify results before production use.

Comprehensive migration tool that transfers a Bitbucket repository to GitHub while preserving
all metadata, comments, attachments, and cross-references between issues and pull requests.

Purpose:
    Migrates entire Bitbucket repositories to GitHub with intelligent handling of:
    - Issues with full comment history and metadata preservation
    - Pull requests using smart migration strategy (open PRs → GitHub PRs, others → issues)
    - User mapping from Bitbucket display names to GitHub usernames
    - Attachments downloaded locally for manual upload to GitHub
    - Automatic link rewriting to maintain issue/PR references
    - Placeholder issues for deleted/missing content to preserve numbering

Arguments:
    --config FILE          Path to configuration JSON file (required)
                           Configuration file must contain bitbucket, github, and user_mapping sections
    --dry-run              Simulate migration without making any changes to GitHub
                           Shows exactly what would be migrated and validates connections
    --skip-issues          Skip issue migration phase (migrate only pull requests)
    --skip-prs             Skip pull request migration phase (migrate only issues)
    --skip-pr-as-issue     Skip migrating closed/merged PRs as issues (only migrate open PRs as PRs)
                           Useful when you don't want to preserve closed PR metadata as issues
    --use_gh_cli           Attachments are automatically uploaded using GitHub CLI
                           Files are preserved locally in attachments_temp/ as backup

Outputs:
    migration_mapping.json      Machine-readable mapping of Bitbucket → GitHub issue/PR numbers
    migration_report.md         Comprehensive markdown report with migration statistics,
                               detailed issue/PR tables, user mapping summary, and troubleshooting notes
    migration_report_dry_run.md If run with --dry-run flag, simulation report
    attachments_temp/           Directory containing downloaded attachments for manual upload
    Console output              Detailed progress logging with timestamps and status indicators

Migration Strategy:
    Issues: All Bitbucket issues become GitHub issues, preserving original numbering with placeholders
    Pull Requests:
        - OPEN PRs with existing branches → GitHub PRs (remain open)
        - OPEN PRs with missing branches → GitHub Issues
        - MERGED/DECLINED/SUPERSEDED PRs → GitHub Issues (safest approach)

Link Rewriting:
    Automatically rewrites cross-references between issues and PRs:
    - Full URLs: https://bitbucket.org/.../issues/123 → [#456](github_url) *(was BB #123)*
    - Short references: #123 → [#456](github_url) *(was BB #123)*
    - PR references: PR #45 → [PR #456](github_url) *(was BB PR #45)*
    - Commit URLs: https://bitbucket.org/.../commits/abc123 → [`abc123`](github_url) *(was Bitbucket)*
    - Branch commit URLs: https://bitbucket.org/.../commits/branch/feature → [commits on `feature`](github_url) *(was Bitbucket)*
    - Compare URLs: https://bitbucket.org/.../compare/abc123..def456 → [compare `abc123`...`def456`](github_url) *(was Bitbucket)*
    - Unhandled links detection: Identifies Bitbucket links that need manual attention
    - Cross-repository links: Links to other Bitbucket repos can be rewritten if configured

Cross-Repository Link Rewriting:
    If you're migrating multiple related repositories, you can configure automatic rewriting
    of links between them. Add a "repository_mapping" section to your config:
    
    "repository_mapping": {
      "workspace/other-repo": "github-owner/other-repo",
      "workspace/shared-lib": "shared-lib"
    }
    
    Supported cross-repo link types (safe to rewrite):
    - Repository home: https://bitbucket.org/workspace/other-repo
      → [other-repo](github_url)
    - Issues: https://bitbucket.org/workspace/other-repo/issues/42
      → [other-repo #42](github_url) - Numbers are preserved during migration
    - Source files: https://bitbucket.org/workspace/other-repo/src/hash/file.cpp
      → [other-repo/file.cpp](github_url)
    - Source with lines: https://bitbucket.org/.../file.cpp#lines-143
      → [other-repo/file.cpp](github_url#L143)
    - Commits: https://bitbucket.org/workspace/other-repo/commits/abc123
      → [other-repo@abc123d](github_url)
    
    NOT rewritten (require manual handling):
    - Pull Requests: May become issues or be skipped, numbers not predictable
    - Downloads: Use GitHub Releases instead
    - Wiki pages: Migrate wiki separately
    - New PR/branch pages: UI-specific, not applicable
    - Images in repo storage: Need manual download/upload
    
    If you don't specify a GitHub owner (e.g., "shared-lib"), it uses the same
    owner as the current repository.
    
    All unmapped/unsafe cross-repo links appear in the "Unhandled Links" report.
    The repository_mapping is optional. If you're only migrating a single repo
    or don't have cross-repo links, you can omit it. Links to unmapped repos
    will be flagged in the "Unhandled Bitbucket Links" report.

User Mapping:
    Maps Bitbucket display names to GitHub usernames in configuration file.
    For @mentions, also map Bitbucket usernames (see formats below)
    Users without GitHub accounts are mentioned as "Name (no GitHub account)".
    Supports null values for users who shouldn't be mapped.
    Unmapped @mentions preserved as: "@user *(Bitbucket user, needs GitHub mapping)*"

User Mapping Formats:

Format 1 - Simple (works for authors/assignees):
  "user_mapping": {
    "Alice Smith": "alice-github"
  }

Format 2 - Enhanced (works for @mentions AND account IDs):
  "user_mapping": {
    "Alice Smith": {
      "github": "alice-github",
      "bitbucket_username": "asmith"
    }
  }

Format 3 - Direct username mapping (works for @mentions):
  "user_mapping": {
    "asmith": "alice-github"
  }

Format 4 - No GitHub account:
  "user_mapping": {
    "External User": null
  }

Format 5 - Account ID mentions (auto-resolved):
  Account IDs like @557058:c250d1e9-df76-4236-bc2f-a98d056b56b5 are 
  automatically resolved to Bitbucket usernames, then mapped to GitHub.
  You don't need to map account IDs directly - just map the username.

You can mix formats in the same config. Enhanced format is recommended
if your team uses @mentions frequently or if you see account ID mentions
in the dry-run report.

EXAMPLE:
  "user_mapping": {
    "Alice Smith": {
      "github": "alice-gh",
      "bitbucket_username": "asmith"
    },
    "Bob Jones": "bjones",
    "charlie": "charlie-dev",
    "old-employee": null
  }

This handles:
- Alice as issue author (by display name "Alice Smith")
- Alice in @asmith mentions (by username)
- Alice in @557058:abc... account ID mentions (auto-resolved to "asmith")
- Bob as issue author OR in @bjones mentions
- charlie in @charlie mentions  
- old-employee won't be mentioned (null = no GitHub account)

Attachment Handling:
    Downloads all attachments to local attachments_temp/ directory.
    Creates comments on GitHub issues noting attached files.
    Extracts and downloads Bitbucket-hosted inline images from markdown content.
    Processes images in issue/PR descriptions and comments automatically.
    Files must be manually uploaded via GitHub web interface (API limitation).

+GitHub CLI Upload with --use-gh-cli:
    Requires GitHub CLI (gh) installed: https://cli.github.com/
    Must be authenticated: gh auth login
    Automatically uploads all attachments and saves manual work
    Use --dry-run --use-gh-cli to test without uploading

Requirements:
    pip install requests

Prerequisites:
    1. Create empty GitHub repository
    2. Push git history: git push --mirror <github-url>
    3. Generate Bitbucket API token with repository read access
    4. Generate GitHub personal access token with repository write access
    5. Create user mapping configuration file
    6. Run audit script first to understand migration scope

Examples:
    # Dry run to validate configuration and see what will be migrated
    python migrate_bitbucket_to_github.py --config config.json --dry-run

    # Full migration
    python migrate_bitbucket_to_github.py --config config.json

    # Migrate only issues
    python migrate_bitbucket_to_github.py --config config.json --skip-prs

    # Migrate only pull requests
    python migrate_bitbucket_to_github.py --config config.json --skip-issues
"""

"""
Bitbucket to GitHub Migration Script

⚠️  DISCLAIMER: This migration tool was developed with assistance from Claude.ai, an AI language model.
   Use at your own risk. Always perform dry runs and verify results before production use.

Comprehensive migration tool that transfers a Bitbucket repository to GitHub while preserving
all metadata, comments, attachments, and cross-references between issues and pull requests.
"""

import argparse
import json
import sys
import time
import re
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union
import requests
from pathlib import Path
from urllib.parse import urlparse
import subprocess
import shutil

# Import custom exceptions
from exceptions import (
    MigrationError,
    APIError,
    AuthenticationError,
    NetworkError,
    ConfigurationError,
    ValidationError,
    BranchNotFoundError,
    AttachmentError
)

# Import configuration management
from config.migration_config import (
    MigrationConfig,
    ConfigLoader,
    BitbucketConfig,
    GitHubConfig
)


class BitbucketToGitHubMigrator:
    """
    Main migration class that orchestrates the transfer of Bitbucket repositories to GitHub.

    This class handles the complete migration workflow including:
    - Fetching data from Bitbucket API
    - Creating corresponding issues and PRs on GitHub
    - Migrating comments, attachments, and metadata
    - Rewriting links and user mentions
    - Generating comprehensive migration reports

    Attributes:
        config (MigrationConfig): Complete migration configuration
        bb_workspace (str): Bitbucket workspace name
        bb_repo (str): Bitbucket repository name
        bb_email (str): Bitbucket user email for API authentication
        bb_token (str): Bitbucket API token
        gh_owner (str): GitHub repository owner
        gh_repo (str): GitHub repository name
        gh_token (str): GitHub API token
        user_mapping (Dict[str, Any]): Mapping of Bitbucket users to GitHub users
        repository_mapping (Optional[Dict[str, str]]): Cross-repository link mappings
        dry_run (bool): Whether to simulate migration without making changes
        skip_pr_as_issue (bool): Whether to skip migrating closed PRs as issues
        use_gh_cli (bool): Whether to use GitHub CLI for attachment uploads
    """

    def __init__(self, config: MigrationConfig) -> None:
        """
        Initialize the migration with configuration.

        Args:
            config: Complete migration configuration object
        """
        # Store config reference
        self.config = config

        # Extract values from config
        self.bb_workspace = config.bitbucket.workspace
        self.bb_repo = config.bitbucket.repo
        self.bb_email = config.bitbucket.email
        self.bb_token = config.bitbucket.token

        self.gh_owner = config.github.owner
        self.gh_repo = config.github.repo
        self.gh_token = config.github.token

        self.user_mapping = config.user_mapping
        self.dry_run = config.dry_run
        self.skip_pr_as_issue = config.skip_pr_as_issue
        self.use_gh_cli = config.use_gh_cli

        # Repository mapping for cross-repo links
        self.repo_mapping = config.repository_mapping or {}
        
        # Track cross-repo links for reporting
        self.cross_repo_links_rewritten = 0

        # Organization issue types support
        self.is_org_repo = False
        self.org_issue_types = {}  # name -> id mapping

        # Milestone mapping (BB name -> GH number)
        self.milestone_mapping = {}

        # Build account ID to username mapping (for @mention resolution)
        self.account_id_to_username = {}  # Maps account_id -> bitbucket_username
        self.account_id_to_display_name = {}  # Maps account_id -> display_name

        # Check if gh CLI is available when requested
        if self.use_gh_cli and not self.dry_run:
            if not self.check_gh_cli_available():
                self.log("ERROR: --use-gh-cli specified but GitHub CLI is not available")
                self.log("Please install gh CLI: https://cli.github.com/")
                raise ConfigurationError("GitHub CLI not available. Please install from https://cli.github.com/")

        # Setup API sessions
        self.bb_session = requests.Session()
        self.bb_session.auth = (self.bb_email, self.bb_token)
        
        self.gh_session = requests.Session()
        self.gh_session.headers.update({
            'Authorization': f'token {self.gh_token}',
            'Accept': 'application/vnd.github.v3+json'
        })
        
        # Track migration progress
        self.issue_mapping = {}  # BB issue # -> GH issue #
        self.pr_mapping = {}  # BB PR # -> GH issue/PR #
        self.attachment_dir = Path('attachments_temp')
        self.attachment_dir.mkdir(exist_ok=True)
        self.attachments = []  # Track all downloaded attachments
        
        # Migration statistics
        self.stats = {
            'prs_as_prs': 0,  # Open PRs that became GitHub PRs
            'prs_as_issues': 0,  # PRs that became GitHub issues
            'pr_branch_missing': 0,  # PRs that couldn't be migrated due to missing branches
            'pr_merged_as_issue': 0,  # Merged PRs migrated as issues (safest approach)
        }
        
        # Dry-run tracking: simulate issue/PR counter
        self.next_github_number = 1  # Track next expected GitHub issue/PR number
        
        # Detailed migration records for report generation
        self.issue_records = []  # Detailed issue migration records
        self.pr_records = []  # Detailed PR migration records
        
        # Link rewriting tracking
        self.link_rewrites = {
            'issues': 0,
            'prs': 0,
            'total_links': 0
        }
        
        # Track unhandled Bitbucket links for warning
        self.unhandled_bb_links = []
    
        # Track unmapped mentions
        self.unmapped_mentions = {}  # {bb_username: count}
    
    def rewrite_bitbucket_links(self,
                               text: str,
                               item_type: str = 'issue',
                               item_number: Optional[int] = None) -> Tuple[str, int]:
        """
        Rewrite Bitbucket issue/PR references to point to GitHub.

        This method processes text content and replaces Bitbucket URLs and references
        with corresponding GitHub links while preserving the original context.

        Args:
            text: The text to rewrite (issue body or comment)
            item_type: 'issue' or 'pr' for logging purposes
            item_number: The current item number for logging

        Returns:
            Tuple of (rewritten_text, links_found_count)

        Strategy:
            - Make GitHub link primary: [#123](github_url) (was [BB #123](bitbucket_url))
            - This makes it easy to click to GitHub while preserving history
        """
        if not text:
            return text, 0
        
        original_text = text
        links_found = 0
        
        # Pattern 1: Full Bitbucket issue URLs
        # https://bitbucket.org/workspace/repo/issues/123
        pattern_issue_url = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/issues/(\d+)'
        
        def replace_issue_url(match):
            nonlocal links_found
            bb_num = int(match.group(1))
            gh_num = self.issue_mapping.get(bb_num)
            
            if gh_num:
                links_found += 1
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                bb_url = match.group(0)
                return f"[#{gh_num}]({gh_url}) *(was [BB #{bb_num}]({bb_url}))*"
            return match.group(0)
        
        text = re.sub(pattern_issue_url, replace_issue_url, text)
        
        # Pattern 2: Full Bitbucket PR URLs
        # https://bitbucket.org/workspace/repo/pull-requests/45
        pattern_pr_url = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/pull-requests/(\d+)'
        
        def replace_pr_url(match):
            nonlocal links_found
            bb_num = int(match.group(1))
            gh_num = self.pr_mapping.get(bb_num)
            
            if gh_num:
                links_found += 1
                # Check if it became a PR or issue
                pr_record = next((r for r in self.pr_records if r['bb_number'] == bb_num), None)
                if pr_record and pr_record['gh_type'] == 'PR':
                    gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/pull/{gh_num}"
                    return f"[PR #{gh_num}]({gh_url}) *(was [BB PR #{bb_num}]({match.group(0)}))*"
                else:
                    gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                    return f"[#{gh_num}]({gh_url}) *(was [BB PR #{bb_num}]({match.group(0)}))*"
            return match.group(0)
        
        text = re.sub(pattern_pr_url, replace_pr_url, text)
        
        # Pattern 5: Bitbucket commit URLs
        # https://bitbucket.org/workspace/repo/commits/abc123def456...
        pattern_commit_url = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/commits/([0-9a-f]{{7,40}})'
        
        def replace_commit_url(match):
            nonlocal links_found
            commit_sha = match.group(1)
            
            links_found += 1
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/commit/{commit_sha}"
            bb_url = match.group(0)
            return f"[`{commit_sha[:7]}`]({gh_url}) *(was [Bitbucket]({bb_url}))*"
        
        text = re.sub(pattern_commit_url, replace_commit_url, text)
        
        # Pattern 6: Bitbucket branch/tag commit URLs
        # https://bitbucket.org/workspace/repo/commits/branch/branch-name
        pattern_branch_url = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/commits/branch/([^/\s\)]+)'
        
        def replace_branch_url(match):
            nonlocal links_found
            branch_name = match.group(1)
            
            links_found += 1
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/commits/{branch_name}"
            bb_url = match.group(0)
            return f"[commits on `{branch_name}`]({gh_url}) *(was [Bitbucket]({bb_url}))*"
        
        text = re.sub(pattern_branch_url, replace_branch_url, text)
        
        # Pattern 7: Bitbucket compare URLs
        # https://bitbucket.org/workspace/repo/compare/abc123..def456
        pattern_compare_url = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/compare/([0-9a-f]{{7,40}})\.\.([0-9a-f]{{7,40}})'
        
        def replace_compare_url(match):
            nonlocal links_found
            sha1 = match.group(1)
            sha2 = match.group(2)
            
            links_found += 1
            # GitHub uses triple dots for compare
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/compare/{sha1}...{sha2}"
            bb_url = match.group(0)
            return f"[compare `{sha1[:7]}`...`{sha2[:7]}`]({gh_url}) *(was [Bitbucket]({bb_url}))*"
        
        text = re.sub(pattern_compare_url, replace_compare_url, text)

        # Pattern 8: Cross-repository links - Safe types
        # We can safely rewrite:
        # - Issues (numbers are preserved)
        # - Source files, commits (don't change)
        # NOT PRs (might become issues, be skipped, or get renumbered)
        # # This handles BOTH cross-repo AND current repo links
        pattern_cross_repo = r'https://bitbucket\.org/([^/]+)/([^/]+)/(issues|src|commits)(/[^\s\)"\'>]+)'
        
        def replace_cross_repo(match):
            nonlocal links_found
            workspace = match.group(1)
            repo = match.group(2)
            resource_type = match.group(3)
            resource_path = match.group(4)[1:]  # Remove leading slash
            
            # Determine if this is current repo or cross-repo
            if workspace == self.bb_workspace and repo == self.bb_repo:
                # Current repo - use current repo's GitHub info
                gh_owner = self.gh_owner
                gh_repo = self.gh_repo
            else:
                # Cross-repo - check if we have a mapping
                repo_key = f"{workspace}/{repo}"
            
                if repo_key not in self.repo_mapping:
                    # No mapping - will be caught by unhandled links
                    return match.group(0)
                
                gh_repo_full = self.repo_mapping[repo_key]
                
                # Parse GitHub owner/repo
                if '/' in gh_repo_full:
                    gh_owner, gh_repo = gh_repo_full.split('/', 1)
                else:
                    # Assume same owner as current repo
                    gh_owner = self.gh_owner
                    gh_repo = gh_repo_full

            # Now process the link (same logic for both current and cross-repo)
            links_found += 1
            if workspace != self.bb_workspace or repo != self.bb_repo:
                self.cross_repo_links_rewritten += 1
            
            bb_url = match.group(0)
            
            # Map resource types
            if resource_type == 'issues':
                # Issues maintain their original numbers, so this is safe
                issue_number = resource_path.split('/')[0] if '/' in resource_path else resource_path
                
                # For current repo, check if we already mapped this issue
                if workspace == self.bb_workspace and repo == self.bb_repo:
                    # Use our mapping if available
                    gh_issue_num = self.issue_mapping.get(int(issue_number), int(issue_number))
                    gh_url = f"https://github.com/{gh_owner}/{gh_repo}/issues/{gh_issue_num}"
                    if int(issue_number) != gh_issue_num:
                        return f"[#{gh_issue_num}]({gh_url}) *(was BB #{issue_number})*"
                    else:
                        return f"[#{gh_issue_num}]({gh_url})"
                else:
                    # Cross-repo issue
                    gh_url = f"https://github.com/{gh_owner}/{gh_repo}/issues/{issue_number}"
                    return f"[{gh_repo} #{issue_number}]({gh_url}) *(was [Bitbucket {repo}]({bb_url}))*"
            elif resource_type == 'src':
                # Parse src URLs which can be very complex:
                # /commit-hash/path/to/file.cpp
                # /commit-hash/path/to/file.cpp#lines-143
                # /branch/path/to/file.cpp
                parts = resource_path.split('/', 1)
                if len(parts) == 2:
                    ref, file_path = parts
                    
                    # Check if it has line numbers
                    if '#lines-' in file_path:
                        file_path, line_ref = file_path.split('#lines-', 1)
                        # GitHub uses #L notation
                        gh_url = f"https://github.com/{gh_owner}/{gh_repo}/blob/{ref}/{file_path}#L{line_ref}"
                    else:
                        gh_url = f"https://github.com/{gh_owner}/{gh_repo}/blob/{ref}/{file_path}"
                    
                    # Create a readable link text
                    filename = file_path.split('/')[-1] if '/' in file_path else file_path
                    
                    if workspace == self.bb_workspace and repo == self.bb_repo:
                        # Current repo - simpler format
                        return f"[{filename}]({gh_url})"
                    else:
                        # Cross-repo
                        return f"[{gh_repo}/{filename}]({gh_url}) *(was [Bitbucket]({bb_url}))*"
                else:
                    # Malformed path, leave as-is
                    return match.group(0)
            elif resource_type == 'commits':
                # commits/abc123def456
                commit_hash = resource_path.split('/')[0] if '/' in resource_path else resource_path
                gh_url = f"https://github.com/{gh_owner}/{gh_repo}/commit/{commit_hash}"
                
                if workspace == self.bb_workspace and repo == self.bb_repo:
                    # Current repo
                    return f"[`{commit_hash[:7]}`]({gh_url})"
                else:
                    # Cross-repo
                    return f"[{gh_repo}@{commit_hash[:7]}]({gh_url}) *(was [Bitbucket]({bb_url}))*"
            else:
                # No mapping - will be caught by unhandled links
                return match.group(0)
        
        text = re.sub(pattern_cross_repo, replace_cross_repo, text)
        
        # Pattern 8b: Repository home page links (no specific resource)
        # https://bitbucket.org/workspace/repo-name (just the repo root)
        pattern_repo_home = r'https://bitbucket\.org/([^/]+)/([^/\s\)"\'>]+)(?=/|\s|\)|"|\'|>|$)'
        
        def replace_repo_home(match):
            nonlocal links_found
            workspace = match.group(1)
            repo = match.group(2)
            
            # Check if this is the current repo
            if workspace == self.bb_workspace and repo == self.bb_repo:
                # Current repo - rewrite to GitHub
                links_found += 1
                bb_url = match.group(0)
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}"
                return f"[repository]({gh_url})"                
            
            # Check if we have a mapping for this repo
            repo_key = f"{workspace}/{repo}"
            
            if repo_key in self.repo_mapping:
                links_found += 1
                self.cross_repo_links_rewritten += 1
                gh_repo_full = self.repo_mapping[repo_key]
                
                # Parse GitHub owner/repo
                if '/' in gh_repo_full:
                    gh_owner, gh_repo = gh_repo_full.split('/', 1)
                else:
                    gh_owner = self.gh_owner
                    gh_repo = gh_repo_full
                
                bb_url = match.group(0)
                gh_url = f"https://github.com/{gh_owner}/{gh_repo}"
                
                return f"[{gh_repo}]({gh_url}) *(was [Bitbucket {repo}]({bb_url}))*"
            else:
                # No mapping - will be caught by unhandled links
                return match.group(0)
        
        text = re.sub(pattern_repo_home, replace_repo_home, text)

        # Pattern 9: Bitbucket @mentions
        # Matches: @username, @{username-with-dashes}, @{user name with spaces}
        # Must be careful not to match email addresses or markdown
        pattern_mention = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_][a-zA-Z0-9_-]*)'
        
        mentions_replaced = 0
        mentions_unmapped = 0
        
        def replace_mention(match):
            nonlocal mentions_replaced, mentions_unmapped
            bb_mention = match.group(1)
            
            # Remove braces if present: @{user name} -> user name
            if bb_mention.startswith('{') and bb_mention.endswith('}'):
                bb_username = bb_mention[1:-1]
                # Bitbucket allows spaces in braced mentions, normalize for GitHub
                bb_username_normalized = bb_username.replace(' ', '-')
            else:
                bb_username = bb_mention
                bb_username_normalized = bb_username
            
            # Try to map to GitHub username
            gh_username = self.map_mention(bb_username)
            
            if gh_username:
                # Successfully mapped
                mentions_replaced += 1
                return f"@{gh_username}"
            else:
                # No mapping found - check if this is an account ID that we can make readable
                is_account_id = ':' in bb_username or (len(bb_username) == 24 and all(c in '0123456789abcdef' for c in bb_username.lower()))
                
                if is_account_id:
                    # Try to get display name for this account ID
                    display_name = self.account_id_to_display_name.get(bb_username)
                    
                    if display_name:
                        # Replace account ID with readable display name
                        mentions_unmapped += 1
                        
                        # Track for warning/report (use display name as key for better reporting)
                        if display_name not in self.unmapped_mentions:
                            self.unmapped_mentions[display_name] = 0
                        self.unmapped_mentions[display_name] += 1
                        
                        # Return display name with note
                        return f"**{display_name}** *(Bitbucket user, no GitHub account)*"
                    # else: fall through to default handling below

                # No mapping found
                mentions_unmapped += 1
                
                # Track for warning/report
                if bb_username not in self.unmapped_mentions:
                    self.unmapped_mentions[bb_username] = 0
                self.unmapped_mentions[bb_username] += 1
                
                # KEEP THE ORIGINAL MENTION - don't break it
                # Add a note so it's visible that this needs attention
                return f"@{bb_username_normalized} *(Bitbucket user, needs GitHub mapping)*"
        
        text = re.sub(pattern_mention, replace_mention, text)
        
        if mentions_replaced > 0 or mentions_unmapped > 0:
            if self.dry_run:
                self.log(f"  [DRY RUN] @mentions: {mentions_replaced} mapped, {mentions_unmapped} unmapped/replaced")
            else:
                self.log(f"  → @mentions: {mentions_replaced} mapped, {mentions_unmapped} unmapped/replaced")
                if mentions_unmapped > 0:
                    self.log(f"     (Account IDs replaced with display names where available)")  

        # Pattern 3: Short issue references: #123 or issue #123
        # Be careful not to match markdown headers or already-processed links
        pattern_short_issue = r'(?<!\[)(?<!BB )#(\d+)(?!\])'
        
        def replace_short_issue(match):
            nonlocal links_found
            bb_num = int(match.group(1))
            gh_num = self.issue_mapping.get(bb_num)
            
            if gh_num and bb_num != gh_num:  # Only rewrite if numbers differ
                links_found += 1
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                return f"[#{gh_num}]({gh_url}) *(was BB #{bb_num})*"
            elif gh_num and bb_num == gh_num:
                # Numbers match, just make it a clickable link
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                return f"[#{gh_num}]({gh_url})"
            return match.group(0)
        
        text = re.sub(pattern_short_issue, replace_short_issue, text)
        
        # Pattern 4: PR references: PR #45, pull request #45
        pattern_pr_ref = r'(?:PR|pull request)\s*#(\d+)'
        
        def replace_pr_ref(match):
            nonlocal links_found
            bb_num = int(match.group(1))
            gh_num = self.pr_mapping.get(bb_num)
            
            if gh_num:
                links_found += 1
                # Check if it became a PR or issue
                pr_record = next((r for r in self.pr_records if r['bb_number'] == bb_num), None)
                if pr_record and pr_record['gh_type'] == 'PR':
                    gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/pull/{gh_num}"
                    return f"[PR #{gh_num}]({gh_url}) *(was BB PR #{bb_num})*"
                else:
                    gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                    return f"[#{gh_num}]({gh_url}) *(was BB PR #{bb_num}, migrated as issue)*"
            return match.group(0)
        
        text = re.sub(pattern_pr_ref, replace_pr_ref, text, flags=re.IGNORECASE)
        
        # Pattern 8: Catch any remaining Bitbucket links that we haven't handled
        # This helps identify links that might need manual attention
        remaining_bb_pattern = r'https?://(?:www\.)?bitbucket\.org/[^\s\)"\'>]+'
        
        remaining_matches = re.findall(remaining_bb_pattern, text)
        for unhandled_url in remaining_matches:
            # Check if this URL was already handled by previous patterns
            # (It might still exist in the text due to our "was Bitbucket" notes)
            if '*(was' not in text[max(0, text.find(unhandled_url)-50):text.find(unhandled_url)+len(unhandled_url)+50]:
                # This is a genuinely unhandled link
                self.unhandled_bb_links.append({
                    'url': unhandled_url,
                    'item_type': item_type,
                    'item_number': item_number,
                    'context': text[max(0, text.find(unhandled_url)-50):min(len(text), text.find(unhandled_url)+len(unhandled_url)+50)]
                })
                
                if self.dry_run:
                    self.log(f"  ⚠️  [DRY RUN] Found unhandled Bitbucket link in {item_type} #{item_number}: {unhandled_url}")
                else:
                    self.log(f"  ⚠️  Warning: Unhandled Bitbucket link in {item_type} #{item_number}: {unhandled_url}")
 
        # Log if links were found
        if links_found > 0:
            self.link_rewrites['total_links'] += links_found
            if item_type == 'issue':
                self.link_rewrites['issues'] += 1
            elif item_type == 'pr':
                self.link_rewrites['prs'] += 1
            
            if self.dry_run:
                self.log(f"  [DRY RUN] Would rewrite {links_found} link(s) in {item_type} #{item_number}")
            else:
                self.log(f"  → Rewrote {links_found} link(s) in {item_type} #{item_number}")
        
        return text, links_found
        
    def log(self, message: str) -> None:
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")

    def rate_limit_sleep(self, duration: float = 1.0) -> None:
        """Sleep to avoid hitting rate limits."""
        if not self.dry_run:
            time.sleep(duration)

    def map_user(self, bb_username: str) -> Optional[str]:
        """
        Map Bitbucket display name or username to GitHub username.

        Supports multiple config formats:
        1. Simple: "Display Name": "github-username"
        2. Enhanced: "Display Name": {"github": "github-username", "bitbucket_username": "bbuser"}
        3. Direct: "bitbucket-username": "github-username"

        Args:
            bb_username: Bitbucket username or display name to map

        Returns:
            GitHub username if mapped, None if user doesn't have GitHub account
        """
        if not bb_username:
            return None
        
        gh_user = self.user_mapping.get(bb_username)

        # Check if it's enhanced format (dict)
        if isinstance(gh_user, dict):
            gh_user = gh_user.get('github')
        
        # Return None if explicitly mapped to None or empty string
        if gh_user == "" or gh_user is None:
            return None
            
        return gh_user

    def check_if_organization(self) -> bool:
        """
        Check if the repository belongs to an organization.

        Returns:
            True if repo is under an organization, False if personal
        """
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}"

        try:
            response = self.gh_session.get(url)
            response.raise_for_status()
            repo_data = response.json()

            owner_type = repo_data.get('owner', {}).get('type')
            is_org = owner_type == 'Organization'

            if is_org:
                self.log(f"  ✓ Repository is under organization: {self.gh_owner}")
            else:
                self.log(f"  ℹ Repository is personal (owner type: {owner_type})")

            return is_org

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                self.log(f"  Warning: Authentication failed checking repository type: {e}")
                return False
            elif e.response.status_code == 404:
                self.log(f"  Warning: Repository not found: {e}")
                return False
            else:
                self.log(f"  Warning: API error checking repository type: {e}")
                return False
        except requests.exceptions.RequestException as e:
            self.log(f"  Warning: Network error checking repository type: {e}")
            return False
        except Exception as e:
            self.log(f"  Warning: Unexpected error checking repository type: {e}")
            return False

    def fetch_org_issue_types(self) -> Dict[str, int]:
        """
        Fetch issue types configured for the organization.

        Returns:
            Dictionary mapping type name (lowercase) to type ID
        """
        if not self.is_org_repo:
            return {}
        
        url = f"https://api.github.com/orgs/{self.gh_owner}/issue-types"
        
        try:
            response = self.gh_session.get(url)
            response.raise_for_status()
            issue_types = response.json()
            
            type_mapping = {}
            for issue_type in issue_types:
                name = issue_type.get('name', '').lower()
                type_id = issue_type.get('id')
                if name and type_id:
                    type_mapping[name] = type_id
            
            if type_mapping:
                self.log(f"  ✓ Found {len(type_mapping)} organization issue types: {', '.join(type_mapping.keys())}")
            else:
                self.log(f"  ℹ No issue types configured for organization")
            
            return type_mapping
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                self.log(f"  Warning: Authentication failed fetching issue types: {e}")
            elif e.response.status_code == 404:
                self.log(f"  Warning: Organization issue types endpoint not found: {e}")
            else:
                self.log(f"  Warning: API error fetching issue types: {e}")
            return {}
        except requests.exceptions.RequestException as e:
            self.log(f"  Warning: Network error fetching issue types: {e}")
            return {}
        except Exception as e:
            self.log(f"  Warning: Unexpected error fetching issue types: {e}")
            return {}
    
    def map_bitbucket_type_to_github(self, bb_kind: str) -> Tuple[Optional[str], bool]:
        """
        Map Bitbucket issue kind to GitHub issue type.

        Args:
            bb_kind: Bitbucket issue kind (bug, enhancement, proposal, task)

        Returns:
            Tuple of (type_name, is_available) - type_name is the GitHub type,
            is_available is True if it exists in org issue types
        """
        # Mapping from Bitbucket kinds to GitHub type names
        BITBUCKET_TO_GITHUB = {
            'bug': 'bug',
            'enhancement': 'feature',
            'proposal': 'feature',
            'task': 'task',
        }

        gh_type_name = BITBUCKET_TO_GITHUB.get(bb_kind.lower())
        if gh_type_name:
            is_available = gh_type_name in self.org_issue_types
            return gh_type_name, is_available

        return None, False

    def fetch_bb_milestones(self) -> List[Dict[str, Any]]:
        """
        Fetch all milestones from Bitbucket.

        Returns:
            List of milestone dictionaries with name, description, etc.
        """
        self.log("Fetching Bitbucket milestones...")
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/milestones"
        
        try:
            milestones = self._paginate(url, params={'pagelen': 100})
            self.log(f"  Found {len(milestones)} milestones")
            return milestones
        except Exception as e:
            self.log(f"  Warning: Could not fetch milestones: {e}")
            return []
    
    def _paginate(self, url: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Fetch all pages of results from Bitbucket API.

        Args:
            url: The API endpoint URL to paginate
            params: Optional query parameters for the first request

        Returns:
            List of all items from all pages
        """
        results = []
        next_url = url
        first_request = True

        while next_url:
            try:
                if first_request and params:
                    response = self.bb_session.get(next_url, params=params)
                    first_request = False
                else:
                    response = self.bb_session.get(next_url)

                response.raise_for_status()
                data = response.json()

                if 'values' in data:
                    results.extend(data['values'])
                else:
                    results.append(data)

                next_url = data.get('next')
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    self.log(f"  Authentication error: {e}")
                    raise AuthenticationError(f"Bitbucket API authentication failed: {e}")
                elif e.response.status_code >= 500:
                    self.log(f"  Server error: {e}")
                    raise NetworkError(f"Bitbucket API server error: {e}")
                else:
                    self.log(f"  API error: {e}")
                    raise APIError(f"Bitbucket API error: {e}", status_code=e.response.status_code)
            except requests.exceptions.RequestException as e:
                self.log(f"  Network error: {e}")
                raise NetworkError(f"Network error communicating with Bitbucket API: {e}")
            except Exception as e:
                self.log(f"  Unexpected error: {e}")
                raise MigrationError(f"Unexpected error during API pagination: {e}")

        return results

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
        if bb_username in self.account_id_to_username or bb_username in self.account_id_to_display_name:
            # Try username first (if available)
            username = self.account_id_to_username.get(bb_username)
            display_name = self.account_id_to_display_name.get(bb_username)
            
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

    def create_or_get_milestone(self,
                               milestone_name: str,
                               milestone_data: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Create a milestone on GitHub or get existing one.

        Args:
            milestone_name: Name of the milestone from Bitbucket
            milestone_data: Optional full milestone data from Bitbucket API containing:
                - description: Milestone description
                - due_on: Due date in ISO format
                - state: 'open' or 'closed'

        Returns:
            GitHub milestone number, or None if creation failed
        """
        # Check if we already mapped this milestone
        if milestone_name in self.milestone_mapping:
            return self.milestone_mapping[milestone_name]
        
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/milestones"
        
        if self.dry_run:
            # Simulate - just assign a fake number
            fake_number = len(self.milestone_mapping) + 1
            self.milestone_mapping[milestone_name] = fake_number
            self.log(f"  [DRY RUN] Would create milestone: {milestone_name}")
            return fake_number
        
        try:
            # First, check if milestone already exists
            response = self.gh_session.get(url, params={'state': 'all'})
            response.raise_for_status()
            milestones = response.json()
            
            for milestone in milestones:
                if milestone['title'] == milestone_name:
                    # Already exists
                    self.milestone_mapping[milestone_name] = milestone['number']
                    self.log(f"  Found existing milestone: {milestone_name} (#{milestone['number']})")
                    return milestone['number']
            
            # Doesn't exist, create it
            payload = {
                'title': milestone_name,
                'state': 'open'
            }
            
            # Add optional fields from Bitbucket data
            if milestone_data:
                if milestone_data.get('description'):
                    payload['description'] = milestone_data['description']
                if milestone_data.get('due_on'):
                    # Bitbucket uses 'due_on', GitHub uses 'due_on' - compatible!
                    payload['due_on'] = milestone_data['due_on']
                # Note: We default to 'open', can close later based on issue states

            response = self.gh_session.post(url, json=payload)
            response.raise_for_status()
            milestone = response.json()
            
            self.milestone_mapping[milestone_name] = milestone['number']
            desc_note = " with description" if milestone_data and milestone_data.get('description') else ""
            due_note = f" (due: {milestone_data.get('due_on', '')[:10]})" if milestone_data and milestone_data.get('due_on') else ""
            self.log(f"  Created milestone: {milestone_name} (#{milestone['number']}){desc_note}{due_note}")

            self.rate_limit_sleep(0.5)
            
            return milestone['number']
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                self.log(f"  Warning: Authentication failed creating milestone: {e}")
            elif e.response.status_code == 404:
                self.log(f"  Warning: Repository not found creating milestone: {e}")
            elif e.response.status_code == 422:
                self.log(f"  Warning: Invalid milestone data: {e}")
            else:
                self.log(f"  Warning: API error creating milestone: {e}")
            return None
        except requests.exceptions.RequestException as e:
            self.log(f"  Warning: Network error creating milestone: {e}")
            return None
        except Exception as e:
            self.log(f"  Warning: Unexpected error creating milestone '{milestone_name}': {e}")
            return None

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
        self.log("Building account ID to username mappings...")
        
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
                        self.account_id_to_username[account_id] = username
                    if display_name:
                        self.account_id_to_display_name[account_id] = display_name
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
                        self.account_id_to_username[account_id] = username
                    if display_name:
                        self.account_id_to_display_name[account_id] = display_name
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
                        self.account_id_to_username[account_id] = username
                    if display_name:
                        self.account_id_to_display_name[account_id] = display_name
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
                            self.account_id_to_username[account_id] = username
                        if display_name:
                            self.account_id_to_display_name[account_id] = display_name
                        if account_id not in users_found:
                            users_found[account_id] = (username, display_name)
            
            # Reviewers
            for reviewer in pr.get('reviewers', []):
                account_id = reviewer.get('account_id')
                username = reviewer.get('username')
                display_name = reviewer.get('display_name')
                
                if account_id:
                    if username:
                        self.account_id_to_username[account_id] = username
                    if display_name:
                        self.account_id_to_display_name[account_id] = display_name
                    if account_id not in users_found:
                        users_found[account_id] = (username, display_name)
        
        self.log(f"  Found {len(users_found)} unique account IDs with username mappings")
        
        # Log sample mappings for verification
        if users_found:
            self.log("  Sample account ID mappings:")
            for account_id, (username, display_name) in list(users_found.items())[:5]:
                self.log(f"    {account_id[:40]}... -> {username} ({display_name})")
        
        return len(users_found)

    def lookup_account_id_via_api(self, account_id: str) -> Optional[Dict[str, str]]:
        """
        Look up a Bitbucket account ID using the API.

        Args:
            account_id: The account ID to look up (e.g., "557058:c250d1e9-df76-4236-bc2f-a98d056b56b5")

        Returns:
            Dict with 'username' and 'display_name' if found, None otherwise
        """
        # Bitbucket API endpoint for user lookup
        url = f"https://api.bitbucket.org/2.0/users/{account_id}"
        
        try:
            response = self.bb_session.get(url, timeout=5)
            if response.status_code == 200:
                user_data = response.json()
                return {
                    'username': user_data.get('username'),
                    'nickname': user_data.get('nickname'),  # Often same as username
                    'display_name': user_data.get('display_name'),
                    'account_id': user_data.get('account_id')
                }
            elif response.status_code == 404:
                # User not found (deleted account, etc.)
                return None
            else:
                self.log(f"  Warning: Could not lookup account ID {account_id[:40]}... (HTTP {response.status_code})")
                return None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # User not found (deleted account, etc.) - this is expected
                return None
            elif e.response.status_code == 401:
                self.log(f"  Warning: Authentication failed looking up account ID: {e}")
                return None
            else:
                self.log(f"  Warning: API error looking up account ID: {e}")
                return None
        except requests.exceptions.RequestException as e:
            self.log(f"  Warning: Network error looking up account ID: {e}")
            return None
        except Exception as e:
            self.log(f"  Warning: Unexpected error looking up account ID {account_id[:40]}...: {e}")
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
        self.log("Scanning comments for account IDs...")
        
        import re
        pattern_mention = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_:][a-zA-Z0-9_:-]*)'
        
        unresolved_account_ids = set()
        
        # Scan issue comments
        for issue in bb_issues:
            comments = self.fetch_bb_issue_comments(issue['id'])
            for comment in comments:
                content = comment.get('content', {}).get('raw', '') or ''
                if content and '@' in content:
                    mentions = re.findall(pattern_mention, content)
                    for mention_match in mentions:
                        mention = mention_match[1:-1] if mention_match.startswith('{') else mention_match
                        
                        # Check if it's an account ID
                        is_account_id = ':' in mention or (len(mention) == 24 and all(c in '0123456789abcdef' for c in mention.lower()))
                        
                        if is_account_id and mention not in self.account_id_to_username:
                            unresolved_account_ids.add(mention)
        
        # Scan PR comments
        for pr in bb_prs:
            comments = self.fetch_bb_pr_comments(pr['id'])
            for comment in comments:
                content = comment.get('content', {}).get('raw', '') or ''
                if content and '@' in content:
                    mentions = re.findall(pattern_mention, content)
                    for mention_match in mentions:
                        mention = mention_match[1:-1] if mention_match.startswith('{') else mention_match
                        
                        is_account_id = ':' in mention or (len(mention) == 24 and all(c in '0123456789abcdef' for c in mention.lower()))
                        
                        if is_account_id and mention not in self.account_id_to_username:
                            unresolved_account_ids.add(mention)
        
        if unresolved_account_ids:
            self.log(f"  Found {len(unresolved_account_ids)} account ID(s) in comment text")
            
            # Resolve via API
            resolved_count = 0
            for account_id in unresolved_account_ids:
                user_info = self.lookup_account_id_via_api(account_id)
                if user_info:
                    username = user_info.get('username') or user_info.get('nickname')
                    display_name = user_info.get('display_name')
                    
                    if username:
                        self.account_id_to_username[account_id] = username
                        resolved_count += 1
                        self.log(f"    ✓ {account_id[:40]}... → {username}")
                    if display_name:
                        self.account_id_to_display_name[account_id] = display_name
            
            self.log(f"  ✓ Resolved {resolved_count}/{len(unresolved_account_ids)} account ID(s) from comments")
        else:
            self.log(f"  No account IDs found in comment text")

    def check_gh_cli_available(self) -> bool:
        """
        Check if GitHub CLI is installed and authenticated.

        Returns:
            True if GitHub CLI is available and authenticated, False otherwise
        """
        try:
            # Check if gh is installed
            result = subprocess.run(['gh', '--version'],
                                  capture_output=True,
                                  text=True,
                                  timeout=5)
            if result.returncode != 0:
                return False

            self.log(f"  ✓ GitHub CLI found: {result.stdout.split()[2]}")

            # Check if gh is authenticated
            result = subprocess.run(['gh', 'auth', 'status'],
                                  capture_output=True,
                                  text=True,
                                  timeout=5)
            if result.returncode != 0:
                self.log("  ✗ GitHub CLI is not authenticated. Run: gh auth login")
                return False

            self.log("  ✓ GitHub CLI is authenticated")
            return True

        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            self.log("  ✗ GitHub CLI check timed out")
            return False
        except Exception as e:
            self.log(f"  ✗ Error checking GitHub CLI: {e}")
            return False

    def check_branch_exists(self, branch_name: str) -> bool:
        """
        Check if a branch exists in the GitHub repository.

        Args:
            branch_name: Name of the branch to check

        Returns:
            True if branch exists, False otherwise

        Note: This is a read-only operation, safe to run even in dry-run mode
        """
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/branches/{branch_name}"
        
        try:
            response = self.gh_session.get(url)
            exists = response.status_code == 200
            
            if exists:
                log_msg = f"    ✓ Branch '{branch_name}' exists on GitHub"
            else:
                log_msg = f"    ✗ Branch '{branch_name}' not found on GitHub"
            
            if self.dry_run:
                self.log(f"    [DRY RUN CHECK] {log_msg}")
            else:
                self.log(log_msg)
            
            self.rate_limit_sleep(0.3)  # Small delay for branch checks
            return exists
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Branch doesn't exist - this is expected
                return False
            elif e.response.status_code == 401:
                self.log(f"    ✗ Authentication error checking branch: {e}")
                return False
            else:
                self.log(f"    ✗ API error checking branch: {e}")
                return False
        except requests.exceptions.RequestException as e:
            self.log(f"    ✗ Network error checking branch: {e}")
            return False
        except Exception as e:
            self.log(f"    ✗ Unexpected error checking branch '{branch_name}': {e}")
            return False

    def fetch_bb_issues(self) -> List[Dict[str, Any]]:
        """
        Fetch all issues from Bitbucket.

        Returns:
            List of Bitbucket issues sorted by ID
        """
        self.log("Fetching Bitbucket issues...")
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/issues"
        params = {'pagelen': 100, 'sort': 'id'}

        issues = []
        next_url = url

        while next_url:
            response = self.bb_session.get(next_url, params=params if next_url == url else None)
            response.raise_for_status()
            data = response.json()

            issues.extend(data.get('values', []))
            next_url = data.get('next')
            params = None

        self.log(f"  Found {len(issues)} issues")
        return sorted(issues, key=lambda x: x['id'])

    def fetch_bb_prs(self) -> List[Dict[str, Any]]:
        """
        Fetch all pull requests from Bitbucket.

        Returns:
            List of Bitbucket pull requests sorted by ID
        """
        self.log("Fetching Bitbucket pull requests...")
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/pullrequests"
        params = {'state': 'MERGED,SUPERSEDED,OPEN,DECLINED', 'pagelen': 50, 'sort': 'id'}

        prs = []
        next_url = url

        while next_url:
            response = self.bb_session.get(next_url, params=params if next_url == url else None)
            response.raise_for_status()
            data = response.json()

            prs.extend(data.get('values', []))
            next_url = data.get('next')
            params = None

        self.log(f"  Found {len(prs)} pull requests")
        return sorted(prs, key=lambda x: x['id'])
    
    def fetch_bb_attachments(self,
                            url: str,
                            item: str = 'item',
                            item_id: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a Bitbucket issue or PR.

        Args:
            url: The API URL to fetch attachments from
            item: Description of the item type (for logging)
            item_id: The item ID (for logging)

        Returns:
            List of attachment dictionaries
        """
        try:
            response = self.bb_session.get(url)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()

            # Handle pagination
            attachments = data.get('values', [])
            next_url = data.get('next')

            while next_url:
                try:
                    response = self.bb_session.get(next_url)
                    response.raise_for_status()
                    data = response.json()
                    attachments.extend(data.get('values', []))
                    next_url = data.get('next')
                except Exception as e:
                    self.log(f"    Warning: Error fetching next page of {item} attachments: {e}")
                    break

            return attachments

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # No attachments found - this is normal
                return []
            elif e.response.status_code == 401:
                self.log(f"    Warning: Authentication error fetching attachments: {e}")
                return []
            else:
                self.log(f"    Warning: API error fetching attachments: {e}")
                return []
        except requests.exceptions.RequestException as e:
            self.log(f"    Warning: Network error fetching attachments: {e}")
            return []
        except Exception as e:
            self.log(f"    Warning: Unexpected error fetching attachments for {item} #{item_id}: {e}")
            return []

    def fetch_bb_issue_attachments(self, issue_id: int) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a Bitbucket issue.

        Args:
            issue_id: The Bitbucket issue ID

        Returns:
            List of attachment dictionaries
        """
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/issues/{issue_id}/attachments"
        return self.fetch_bb_attachments(url, "issue", issue_id)

    def fetch_bb_pr_attachments(self, pr_id: int) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a Bitbucket PR.

        Args:
            pr_id: The Bitbucket pull request ID

        Returns:
            List of attachment dictionaries
        """
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/pullrequests/{pr_id}/attachments"
        return self.fetch_bb_attachments(url, "PR", pr_id)

    def download_attachment(self, attachment_url: str, filename: str) -> Optional[Path]:
        """
        Download an attachment from Bitbucket.

        Args:
            attachment_url: URL of the attachment to download
            filename: Local filename to save as

        Returns:
            Path to downloaded file, or None if download failed
        """
        try:
            response = self.bb_session.get(attachment_url, stream=True)
            response.raise_for_status()

            # Save to temp directory
            filepath = self.attachment_dir / filename
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return filepath
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                self.log(f"    ERROR: Attachment not found: {filename}")
                raise AttachmentError(f"Attachment not found: {filename}", filename=filename)
            elif e.response.status_code == 401:
                self.log(f"    ERROR: Authentication failed downloading attachment: {filename}")
                raise AuthenticationError(f"Authentication failed downloading attachment: {filename}")
            else:
                self.log(f"    ERROR: API error downloading attachment: {filename}")
                raise APIError(f"API error downloading attachment: {filename}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            self.log(f"    ERROR: Network error downloading attachment: {filename}")
            raise NetworkError(f"Network error downloading attachment: {filename}")
        except Exception as e:
            self.log(f"    ERROR: Unexpected error downloading attachment {filename}: {e}")
            raise AttachmentError(f"Unexpected error downloading attachment: {filename}", filename=filename)
    
    def upload_attachment_to_github(self, filepath: Path, issue_number: int) -> Optional[str]:
        """
        Upload attachment to GitHub issue/PR.

        If --use-gh-cli is enabled, uses GitHub CLI to upload the file directly.
        Otherwise, creates a comment noting the attachment for manual upload.

        Args:
            filepath: Path to the local attachment file
            issue_number: GitHub issue/PR number to attach to

        Returns:
            Upload result message or None if failed
        """
        if self.dry_run:
            if self.use_gh_cli:
                self.log(f"    [DRY RUN] Would upload {filepath.name} to issue #{issue_number} using gh CLI")
            else:
                self.log(f"    [DRY RUN] Would create attachment comment for {filepath.name} on issue #{issue_number}")

            return f"https://github.com/{self.gh_owner}/{self.gh_repo}/files/{filepath.name}"
        
        try:
            file_size = filepath.stat().st_size
            size_mb = round(file_size / (1024 * 1024), 2)
            
            if self.use_gh_cli:
                # Use GitHub CLI to upload the attachment directly
                self.log(f"    Uploading {filepath.name} via gh CLI...")
                
                # Create a comment with the attached file
                result = subprocess.run([
                    'gh', 'issue', 'comment', str(issue_number),
                    '--repo', f'{self.gh_owner}/{self.gh_repo}',
                    '--body', f'📎 **Attachment from Bitbucket**: `{filepath.name}` ({size_mb} MB)',
                    '--attach', str(filepath)
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    self.log(f"    ✓ Successfully uploaded {filepath.name}")
                    self.rate_limit_sleep(0.5)
                    return f"Uploaded via gh CLI"
                else:
                    self.log(f"    ✗ Failed to upload {filepath.name}: {result.stderr}")
                    # Fall back to creating a note comment
                    comment_body = f"""📎 **Attachment from Bitbucket**: `{filepath.name}` ({size_mb} MB)

*Note: Automatic upload failed. Please drag and drop this file from `attachments_temp/{filepath.name}` to embed it in this issue.*
 """
                    url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/{issue_number}/comments"
                    response = self.gh_session.post(url, json={'body': comment_body})
                    response.raise_for_status()
                    self.rate_limit_sleep(0.5)
                    return comment_body
            else:
                # Manual upload - create a note comment
                comment_body = f"""📎 **Attachment from Bitbucket**: `{filepath.name}` ({size_mb} MB)

*Note: This file was attached to the original Bitbucket issue. Please drag and drop this file from `attachments_temp/{filepath.name}` to embed it in this issue.*
"""
                url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/{issue_number}/comments"
                response = self.gh_session.post(url, json={'body': comment_body})
                response.raise_for_status()
                self.rate_limit_sleep(0.5)
                return comment_body

        except Exception as e:
            self.log(f"    ERROR creating attachment comment: {e}")
            return None
        except subprocess.TimeoutExpired:
            self.log(f"    ERROR: gh CLI command timed out for {filepath.name}")
            return None
    
    def fetch_bb_comments(self, url: str) -> List[Dict[str, Any]]:
        """
        Fetch comments from a Bitbucket API endpoint.

        Args:
            url: The API URL to fetch comments from

        Returns:
            List of comment dictionaries
        """
        comments = []
        next_url = url

        while next_url:
            response = self.bb_session.get(next_url)
            if response.status_code == 404:
                break
            response.raise_for_status()
            data = response.json()

            comments.extend(data.get('values', []))
            next_url = data.get('next')

        return comments

    def fetch_bb_issue_comments(self, issue_id: int) -> List[Dict[str, Any]]:
        """
        Fetch comments for a Bitbucket issue.

        Args:
            issue_id: The Bitbucket issue ID

        Returns:
            List of comment dictionaries
        """
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/issues/{issue_id}/comments"
        return self.fetch_bb_comments(url)

    def fetch_bb_pr_comments(self, pr_id: int) -> List[Dict[str, Any]]:
        """
        Fetch comments for a Bitbucket PR.

        Args:
            pr_id: The Bitbucket pull request ID

        Returns:
            List of comment dictionaries
        """
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/pullrequests/{pr_id}/comments"
        return self.fetch_bb_comments(url)
    
    def extract_and_download_inline_images(self,
                                          text: str,
                                          item_type: str,
                                          item_number: int) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Extract Bitbucket-hosted inline images from markdown and download them.

        Args:
            text: Markdown text containing images
            item_type: 'issue' or 'pr' for context
            item_number: Issue/PR number for logging

        Returns:
            Tuple of (updated_text, list_of_downloaded_image_info)
        """
        if not text:
            return text, []
        
        import re
        
        # Pattern to match markdown images: ![alt](url)
        image_pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
        
        downloaded_images = []
        images_found = 0
        
        def replace_image(match):
            nonlocal images_found
            alt_text = match.group(1)
            image_url = match.group(2)
            
            # Only process Bitbucket-hosted images
            if 'bitbucket.org' in image_url or 'bytebucket.org' in image_url or f'/{self.bb_workspace}/{self.bb_repo}' in image_url:
                images_found += 1
                
                # Extract filename from URL
                filename = image_url.split('/')[-1].split('?')[0]
                if not filename or filename == '':
                    filename = f"image_{images_found}.png"
                
                if self.dry_run:
                    self.log(f"    [DRY RUN] Would download inline image: {filename}")
                    downloaded_images.append({
                        'filename': filename,
                        'url': image_url,
                        'filepath': f"attachments_temp/{filename}"
                    })
                    # Return modified markdown with note
                    return f"![{alt_text}]({image_url})\n\n📷 *Inline image: `{filename}` (will be downloaded)*"
                else:
                    # Download the image
                    filepath = self.download_attachment(image_url, filename)
                    if filepath:
                        downloaded_images.append({
                            'filename': filename,
                            'url': image_url,
                            'filepath': str(filepath)
                        })
                        self.log(f"    Downloaded inline image: {filename}")

                        if self.use_gh_cli:
                            # With gh CLI, the image will be uploaded, so just keep the markdown
                            return f"![{alt_text}]({image_url})\n\n📷 *Original Bitbucket image (will be uploaded via gh CLI)*"
                        else:
                            # Return modified markdown with note about manual upload
                            return f"![{alt_text}]({image_url})\n\n📷 *Original Bitbucket image (download from `{filepath}` and drag-and-drop here)*"

                    else:
                        self.log(f"    Failed to download inline image: {filename}")
            
            # Return unchanged for non-Bitbucket images or failed downloads
            return match.group(0)
        
        updated_text = re.sub(image_pattern, replace_image, text)
        
        if images_found > 0:
            if self.dry_run:
                self.log(f"    [DRY RUN] Found {images_found} inline image(s) in {item_type} #{item_number}")
            else:
                self.log(f"    Found and downloaded {len(downloaded_images)} inline image(s) in {item_type} #{item_number}")
        
        return updated_text, downloaded_images

    def upload_inline_images_to_comment(self, comment_id: int, inline_images: List[Dict[str, Any]]) -> bool:
        """
        Upload inline images to an existing GitHub comment using gh CLI.

        Note: This appends the images to the comment. The user may want to
        edit the comment to integrate them inline with the text.

        Args:
            comment_id: GitHub comment ID to upload images to
            inline_images: List of image information dictionaries

        Returns:
            True if upload successful, False otherwise
        """
        if not self.use_gh_cli or not inline_images:
            return False
        
        if self.dry_run:
            self.log(f"    [DRY RUN] Would upload {len(inline_images)} inline image(s) via gh CLI")
            return True
        
        try:
            # Get the existing comment body
            url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/comments/{comment_id}"
            response = self.gh_session.get(url)
            response.raise_for_status()
            existing_body = response.json()['body']
            
            # Append image upload info
            updated_body = existing_body + "\n\n---\n**Inline Images:**\n"
            
            for img in inline_images:
                # Note: gh CLI doesn't support editing comments with attachments
                # So we'll create a separate comment for images
                pass
            
            # Actually, gh CLI limitation: can't attach to comment edits
            # Best we can do is note that images exist
            self.log(f"    Note: {len(inline_images)} inline image(s) downloaded but need manual upload")
            return False
            
        except Exception as e:
            self.log(f"    Error uploading inline images: {e}")
            return False

    def create_gh_issue(self,
                        title: str,
                        body: str,
                        labels: Optional[List[str]] = None,
                        state: str = 'open',
                        assignees: Optional[List[str]] = None,
                        milestone: Optional[int] = None,
                        issue_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a GitHub issue.

        Args:
            title: Issue title
            body: Issue body content
            labels: Optional list of label names
            state: Issue state ('open' or 'closed')
            assignees: Optional list of GitHub usernames to assign
            milestone: Optional milestone number
            issue_type: Optional issue type for organizations

        Returns:
            Created GitHub issue data
        """
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues"

        payload = {
            'title': title,
            'body': body,
        }

        if labels:
            payload['labels'] = labels
        if assignees:
            payload['assignees'] = assignees
        if milestone:
            payload['milestone'] = milestone
        if issue_type:
            payload['type'] = issue_type

        if self.dry_run:
            # Simulate issue creation with correct numbering
            simulated_number = self.next_github_number
            self.next_github_number += 1
            self.log(f"  [DRY RUN] Would create issue #{simulated_number}: {title}")
            if state == 'closed':
                self.log(f"  [DRY RUN] Would close issue #{simulated_number}")
            return {'number': simulated_number}

        try:
            response = self.gh_session.post(url, json=payload)
            response.raise_for_status()
            issue = response.json()

            # Update counter for real migrations too
            if issue['number'] >= self.next_github_number:
                self.next_github_number = issue['number'] + 1

            # Close if needed
            if state == 'closed':
                self.close_gh_issue(issue['number'])

            self.rate_limit_sleep(1.0)
            return issue
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                self.log(f"  ERROR: GitHub authentication failed. Check your token.")
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif e.response.status_code == 404:
                self.log(f"  ERROR: Repository {self.gh_owner}/{self.gh_repo} not found.")
                self.log(f"  Make sure the repository exists and your token has access.")
                raise APIError(f"Repository not found: {self.gh_owner}/{self.gh_repo}", status_code=404)
            elif e.response.status_code == 422:
                self.log(f"  ERROR: Invalid issue data: {e}")
                raise ValidationError(f"Invalid issue data: {e}")
            else:
                self.log(f"  ERROR: Failed to create issue: {e}")
                raise APIError(f"Failed to create GitHub issue: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            self.log(f"  ERROR: Network error creating issue: {e}")
            raise NetworkError(f"Network error creating GitHub issue: {e}")
        except Exception as e:
            self.log(f"  ERROR: Unexpected error creating issue: {e}")
            raise MigrationError(f"Unexpected error creating GitHub issue: {e}")
    
    def close_gh_issue(self, issue_number: int) -> None:
        """
        Close a GitHub issue.

        Args:
            issue_number: The GitHub issue number to close
        """
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/{issue_number}"

        if self.dry_run:
            self.log(f"  [DRY RUN] Would close issue #{issue_number}")
            return

        response = self.gh_session.patch(url, json={'state': 'closed'})
        response.raise_for_status()
        self.rate_limit_sleep(0.5)

    def create_gh_comment(self, issue_number: int, body: str, is_pr: bool = False) -> None:
        """
        Create a comment on a GitHub issue or PR.

        Args:
            issue_number: The issue or PR number
            body: Comment text
            is_pr: Whether this is a PR (for better logging)
        """
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/{issue_number}/comments"

        if self.dry_run:
            item_type = "PR" if is_pr else "issue"
            self.log(f"  [DRY RUN] Would add comment to {item_type} #{issue_number}")
            return

        response = self.gh_session.post(url, json={'body': body})
        response.raise_for_status()
        self.rate_limit_sleep(0.5)
    
    def create_gh_pr(self, title: str, body: str, head: str, base: str) -> Optional[Dict[str, Any]]:
        """
        Create a GitHub pull request.

        Note: This creates an OPEN PR. Both head and base branches must exist.

        Args:
            title: PR title
            body: PR body content
            head: Source branch name
            base: Target branch name

        Returns:
            Created GitHub PR data, or None if creation failed
        """
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/pulls"

        payload = {
            'title': title,
            'body': body,
            'head': head,
            'base': base,
        }

        if self.dry_run:
            # Simulate PR creation with correct numbering
            # PRs and issues share the same numbering sequence on GitHub
            simulated_number = self.next_github_number
            self.next_github_number += 1
            self.log(f"  [DRY RUN] Would create PR #{simulated_number}: {title} ({head} -> {base})")
            return {'number': simulated_number}

        try:
            response = self.gh_session.post(url, json=payload)
            response.raise_for_status()
            pr = response.json()

            # Update counter for real migrations too
            if pr['number'] >= self.next_github_number:
                self.next_github_number = pr['number'] + 1

            self.rate_limit_sleep(1.0)
            return pr
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                self.log(f"  ERROR: GitHub authentication failed creating PR")
                raise AuthenticationError("GitHub authentication failed creating PR")
            elif e.response.status_code == 404:
                self.log(f"  ERROR: Repository or branches not found creating PR")
                raise APIError("Repository or branches not found", status_code=404)
            elif e.response.status_code == 422:
                self.log(f"  ERROR: Invalid PR data or branch doesn't exist")
                raise ValidationError("Invalid PR data or branch doesn't exist")
            else:
                self.log(f"  ERROR: Could not create PR: {e}")
                if hasattr(e.response, 'text'):
                    self.log(f"  Response: {e.response.text}")
                raise APIError(f"Failed to create GitHub PR: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            self.log(f"  ERROR: Network error creating PR: {e}")
            raise NetworkError(f"Network error creating GitHub PR: {e}")
        except Exception as e:
            self.log(f"  ERROR: Unexpected error creating PR: {e}")
            raise MigrationError(f"Unexpected error creating GitHub PR: {e}")
    
    def close_gh_pr(self, pr_number: int) -> None:
        """
        Close a GitHub PR without merging.

        This is safe - it just changes the PR state to 'closed' without
        performing any git operations.

        Args:
            pr_number: The GitHub PR number to close
        """
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/pulls/{pr_number}"

        if self.dry_run:
            self.log(f"  [DRY RUN] Would close PR #{pr_number}")
            return

        try:
            response = self.gh_session.patch(url, json={'state': 'closed'})
            response.raise_for_status()
            self.rate_limit_sleep(0.5)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                self.log(f"  ERROR: Authentication failed closing PR")
                raise AuthenticationError("GitHub authentication failed closing PR")
            elif e.response.status_code == 404:
                self.log(f"  ERROR: PR not found")
                raise APIError("PR not found", status_code=404)
            else:
                self.log(f"  ERROR: API error closing PR")
                raise APIError(f"Failed to close GitHub PR: {e}", status_code=e.response.status_code)
        except requests.exceptions.RequestException as e:
            self.log(f"  ERROR: Network error closing PR")
            raise NetworkError(f"Network error closing GitHub PR: {e}")
        except Exception as e:
            self.log(f"  ERROR: Unexpected error closing PR #{pr_number}: {e}")
            raise MigrationError(f"Unexpected error closing GitHub PR: {e}")
    
    def format_issue_body(self, bb_issue: Dict[str, Any]) -> Tuple[str, int, List[Dict[str, Any]]]:
        """
        Format issue body with metadata.

        Args:
            bb_issue: Bitbucket issue data

        Returns:
            Tuple of (formatted_body, links_rewritten_count, inline_images)
        """
        reporter = bb_issue.get('reporter', {}).get('display_name', 'Unknown') if bb_issue.get('reporter') else 'Unknown (deleted user)'
        gh_reporter = self.map_user(reporter) if reporter != 'Unknown (deleted user)' else None
        
        # Format reporter mention
        if gh_reporter:
            reporter_mention = f"@{gh_reporter}"
        elif reporter == 'Unknown (deleted user)':
            reporter_mention = f"**{reporter}**"
        else:
            reporter_mention = f"**{reporter}** *(no GitHub account)*"
        
        created = bb_issue.get('created_on', '')
        bb_url = bb_issue.get('links', {}).get('html', {}).get('href', '')
        kind = bb_issue.get('kind', 'bug')
        priority = bb_issue.get('priority', 'major')
        
        # Rewrite links in the issue content
        content = bb_issue.get('content', {}).get('raw', '')
        content, links_count = self.rewrite_bitbucket_links(content, 'issue', bb_issue['id'])        
        
        # Extract and download inline images
        content, inline_images = self.extract_and_download_inline_images(content, 'issue', bb_issue['id'])

        body = f"""**Migrated from Bitbucket**
- Original Author: {reporter_mention}
- Original Created: {created}
- Original URL: {bb_url}
- Kind: {kind}
- Priority: {priority}

---

{content}
"""
        return body, links_count, inline_images
    
    def format_pr_as_issue_body(self, bb_pr: Dict[str, Any]) -> Tuple[str, int, List[Dict[str, Any]]]:
        """
        Format a PR (that will be migrated as an issue) with full metadata.

        Args:
            bb_pr: Bitbucket pull request data

        Returns:
            Tuple of (formatted_body, links_rewritten_count, inline_images)
        """
        author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
        gh_author = self.map_user(author) if author != 'Unknown (deleted user)' else None
        
        # Format author mention
        if gh_author:
            author_mention = f"@{gh_author}"
        elif author == 'Unknown (deleted user)':
            author_mention = f"**{author}**"
        else:
            author_mention = f"**{author}** *(no GitHub account)*"
        
        created = bb_pr.get('created_on', '')
        updated = bb_pr.get('updated_on', '')
        bb_url = bb_pr.get('links', {}).get('html', {}).get('href', '')
        state = bb_pr.get('state', 'UNKNOWN')
        source = bb_pr.get('source', {}).get('branch', {}).get('name', 'unknown')
        dest = bb_pr.get('destination', {}).get('branch', {}).get('name', 'unknown')
        
        # Rewrite links in the PR description
        description = bb_pr.get('description', '')
        description, links_count = self.rewrite_bitbucket_links(description, 'pr', bb_pr['id'])
        
        # Extract and download inline images
        description, inline_images = self.extract_and_download_inline_images(description, 'pr', bb_pr['id'])

        body = f"""⚠️ **This was a Pull Request on Bitbucket (migrated as an issue)**

**Original PR Metadata:**
- Author: {author_mention}
- State: {state}
- Created: {created}
- Updated: {updated}
- Source Branch: `{source}`
- Destination Branch: `{dest}`
- Original URL: {bb_url}

---

**Description:**

{description}

---

*Note: This PR was {state.lower()} on Bitbucket. It was migrated as a GitHub issue to preserve all metadata and comments. The actual code changes are in the git history.*
"""
        return body, links_count, inline_images
    
    def format_pr_body(self, bb_pr: Dict[str, Any]) -> Tuple[str, int, List[Dict[str, Any]]]:
        """
        Format PR body for an actual GitHub PR (for OPEN PRs).

        Args:
            bb_pr: Bitbucket pull request data

        Returns:
            Tuple of (formatted_body, links_rewritten_count, inline_images)
        """
        author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
        gh_author = self.map_user(author) if author != 'Unknown (deleted user)' else None
        
        # Format author mention
        if gh_author:
            author_mention = f"@{gh_author}"
        elif author == 'Unknown (deleted user)':
            author_mention = f"**{author}**"
        else:
            author_mention = f"**{author}** *(no GitHub account)*"
        
        created = bb_pr.get('created_on', '')
        bb_url = bb_pr.get('links', {}).get('html', {}).get('href', '')
        
        # Rewrite links in the PR description
        description = bb_pr.get('description', '')
        description, links_count = self.rewrite_bitbucket_links(description, 'pr', bb_pr['id'])
        
        # Extract and download inline images
        description, inline_images = self.extract_and_download_inline_images(description, 'pr', bb_pr['id'])

        body = f"""**Migrated from Bitbucket**
- Original Author: {author_mention}
- Original Created: {created}
- Original URL: {bb_url}

---

{description}
"""
        return body, links_count, inline_images
    
    def format_comment_body(self,
                          bb_comment: Dict[str, Any],
                          item_type: str = 'issue',
                          item_number: Optional[int] = None) -> Tuple[str, int, List[Dict[str, Any]]]:
        """
        Format a comment with original author and timestamp.

        Args:
            bb_comment: Bitbucket comment data
            item_type: 'issue' or 'pr' for link rewriting context
            item_number: The issue/PR number for link rewriting context

        Returns:
            Tuple of (formatted_comment, links_rewritten_count, inline_images)
        """
        author = bb_comment.get('user', {}).get('display_name', 'Unknown') if bb_comment.get('user') else 'Unknown (deleted user)'
        gh_author = self.map_user(author) if author != 'Unknown (deleted user)' else None
        
        # Format author mention
        if gh_author:
            author_mention = f"@{gh_author}"
        elif author == 'Unknown (deleted user)':
            author_mention = f"**{author}**"
        else:
            author_mention = f"**{author}** *(no GitHub account)*"
        
        created = bb_comment.get('created_on', '')
        content = bb_comment.get('content', {}).get('raw', '')
        
        # Rewrite links in the comment
        content, links_count = self.rewrite_bitbucket_links(content, item_type, item_number)
        
        # Extract and download inline images
        content, inline_images = self.extract_and_download_inline_images(content, item_type, item_number)

        comment_body = f"""**Comment by {author_mention} on {created}:**

{content}
"""
        return comment_body, links_count, inline_images

    def format_pr_comment_body(self,
                             bb_comment: Dict[str, Any],
                             item_type: str = 'pr',
                             item_number: Optional[int] = None) -> Tuple[str, int, List[Dict[str, Any]]]:
        """
        Format a PR comment with code context if it's an inline comment.

        Args:
            bb_comment: Bitbucket comment data
            item_type: 'pr' for link rewriting context
            item_number: The PR number for link rewriting context

        Returns:
            Tuple of (formatted_comment, links_rewritten_count, inline_images)
        """
        author = bb_comment.get('user', {}).get('display_name', 'Unknown') if bb_comment.get('user') else 'Unknown (deleted user)'
        gh_author = self.map_user(author) if author != 'Unknown (deleted user)' else None
        
        # Format author mention
        if gh_author:
            author_mention = f"@{gh_author}"
        elif author == 'Unknown (deleted user)':
            author_mention = f"**{author}**"
        else:
            author_mention = f"**{author}** *(no GitHub account)*"
        
        created = bb_comment.get('created_on', '')
        content = bb_comment.get('content', {}).get('raw', '')
        
        # Rewrite links in the comment
        content, links_count = self.rewrite_bitbucket_links(content, item_type, item_number)
        
        # Extract and download inline images
        content, inline_images = self.extract_and_download_inline_images(content, item_type, item_number)
        
        # Check if this is an inline code comment
        inline_data = bb_comment.get('inline')
        code_context = ""
        
        if inline_data:
            # This is an inline comment - add context information
            file_path = inline_data.get('path', 'unknown file')
            line_from = inline_data.get('from')
            line_to = inline_data.get('to')
            
            if line_from:
                if line_to and line_to != line_from:
                    line_info = f"lines {line_from}-{line_to}"
                else:
                    line_info = f"line {line_from}"
                
                code_context = f"\n\n> 💬 **Code comment on `{file_path}` ({line_info})**\n"
        
        comment_body = f"""**Comment by {author_mention} on {created}:**
{code_context}
{content}
"""
        return comment_body, links_count, inline_images

    def migrate_issues(self, bb_issues: List[Dict[str, Any]], milestone_lookup: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """
        Migrate all Bitbucket issues to GitHub.

        Args:
            bb_issues: List of Bitbucket issues to migrate
            milestone_lookup: Optional mapping of milestone names to GitHub milestone data
        """
        milestone_lookup = milestone_lookup or {}
        
        self.log("="*80)
        self.log("PHASE 1: Migrating Issues")
        self.log("="*80)
        
        if not bb_issues:
            self.log("No issues to migrate")
            return
        
        # Determine range and gaps
        issue_numbers = [issue['id'] for issue in bb_issues]
        min_num = min(issue_numbers)
        max_num = max(issue_numbers)
        
        self.log(f"Issue range: #{min_num} to #{max_num}")
        
        # Track issue type usage for reporting
        type_stats = {'using_native': 0, 'using_labels': 0, 'no_type': 0}
        type_fallbacks = []  # Track types that fell back to labels

        # Create placeholder issues for gaps
        expected_num = 1
        for bb_issue in bb_issues:
            issue_num = bb_issue['id']
            
            # Fill gaps with placeholders
            while expected_num < issue_num:
                self.log(f"Creating placeholder issue #{expected_num}")
                placeholder = self.create_gh_issue(
                    title=f"[Placeholder] Issue #{expected_num} was deleted in Bitbucket",
                    body="This issue number was skipped or deleted in the original Bitbucket repository.",
                    labels=['migration-placeholder'],
                    state='closed'
                )
                self.issue_mapping[expected_num] = placeholder['number']
                
                # Record placeholder for report
                self.issue_records.append({
                    'bb_number': expected_num,
                    'gh_number': placeholder['number'],
                    'title': '[Placeholder - Deleted Issue]',
                    'reporter': 'N/A',
                    'gh_reporter': None,
                    'state': 'deleted',
                    'kind': 'N/A',
                    'priority': 'N/A',
                    'comments': 0,
                    'attachments': 0,
                    'links_rewritten': 0,
                    'bb_url': '',
                    'gh_url': f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{placeholder['number']}",
                    'remarks': ['Placeholder for deleted/missing issue']
                })
                
                expected_num += 1
            
            # Migrate actual issue
            self.log(f"Migrating issue #{issue_num}: {bb_issue.get('title', 'No title')}")
            
            # Extract reporter info (needed for both body and record)
            reporter = bb_issue.get('reporter', {}).get('display_name', 'Unknown') if bb_issue.get('reporter') else 'Unknown (deleted user)'
            gh_reporter = self.map_user(reporter) if reporter != 'Unknown (deleted user)' else None
            
            body, links_in_body, inline_images_body = self.format_issue_body(bb_issue)
            
            # Track inline images as attachments
            for img in inline_images_body:
                self.attachments.append({
                    'issue_number': issue_num,
                    'github_issue': gh_issue['number'],
                    'filename': img['filename'],
                    'filepath': img['filepath'],
                    'type': 'inline_image'
                })

            # Map assignee
            assignees = []
            if bb_issue.get('assignee'):
                assignee_name = bb_issue['assignee'].get('display_name', '')
                gh_user = self.map_user(assignee_name)
                if gh_user:
                    assignees = [gh_user]
                else:
                    self.log(f"  Note: Assignee '{assignee_name}' has no GitHub account, mentioned in body instead")

            # Map milestone
            milestone_number = None
            if bb_issue.get('milestone'):
                milestone_name = bb_issue['milestone'].get('name')
                if milestone_name:
                    milestone_number = self.create_or_get_milestone(milestone_name, milestone_lookup.get(milestone_name))

            # Map issue kind/type as labels
            labels = ['migrated-from-bitbucket']
            issue_type_name = None

            kind = bb_issue.get('kind')
            if kind:
                # Try to use organization issue type first
                type_name, is_available = self.map_bitbucket_type_to_github(kind)
                if type_name and is_available:
                    issue_type_name = type_name
                    type_stats['using_native'] += 1
                else:
                    # Fallback to label
                    labels.append(f'type: {kind}')
                    type_stats['using_labels'] += 1
                    type_fallbacks.append((kind, type_name))
            else:
                type_stats['no_type'] += 1

            priority = bb_issue.get('priority')
            if priority:
                labels.append(f'priority: {priority}')

            # Create issue
            gh_issue = self.create_gh_issue(
                title=bb_issue.get('title', f'Issue #{issue_num}'),
                body=body,
                labels=labels,
                state='open' if bb_issue.get('state') in ['new', 'open'] else 'closed',
                assignees=assignees,
                milestone=milestone_number,
                issue_type=issue_type_name
            )
            
            self.issue_mapping[issue_num] = gh_issue['number']
            
            # Migrate attachments
            attachments = self.fetch_bb_issue_attachments(issue_num)
            if attachments:
                self.log(f"  Migrating {len(attachments)} attachments...")
                for attachment in attachments:
                    att_name = attachment.get('name', 'unknown')
                    att_url = attachment.get('links', {}).get('self', {}).get('href')
                    
                    if att_url:
                        self.log(f"    Downloading {att_name}...")
                        if self.dry_run:
                            # In dry-run, record attachment without downloading
                            self.attachments.append({
                                'issue_number': issue_num,
                                'github_issue': gh_issue['number'],
                                'filename': att_name,
                                'filepath': f"attachments_temp/{att_name}"
                            })
                            self.log(f"    [DRY RUN] Would download {att_name}")
                        else:
                            filepath = self.download_attachment(att_url, att_name)
                            if filepath:
                                self.log(f"    Creating attachment note on GitHub...")
                                upload_result = self.upload_attachment_to_github(filepath, gh_issue['number'])
                                self.attachments.append({
                                    'issue_number': issue_num,
                                    'github_issue': gh_issue['number'],
                                    'filename': att_name,
                                    'filepath': str(filepath),
                                    'type': 'attachment',
                                    'uploaded': self.use_gh_cli and upload_result and 'Uploaded via gh CLI' in str(upload_result)
                                })
            
            # Migrate comments
            comments = self.fetch_bb_issue_comments(issue_num)
            links_in_comments = 0
            for comment in comments:
                comment_body, comment_links, inline_images_comment = self.format_comment_body(comment, 'issue', issue_num)
                links_in_comments += comment_links

                # Track inline images from comments
                for img in inline_images_comment:
                    self.attachments.append({
                        'issue_number': issue_num,
                        'github_issue': gh_issue['number'],
                        'filename': img['filename'],
                        'filepath': img['filepath'],
                        'type': 'inline_image_comment'
                    })

                self.create_gh_comment(gh_issue['number'], comment_body)
            
            # Record migration details for report (after we have all the data)
            self.issue_records.append({
                'bb_number': issue_num,
                'gh_number': gh_issue['number'],
                'title': bb_issue.get('title', f'Issue #{issue_num}'),
                'reporter': reporter,
                'gh_reporter': gh_reporter,
                'state': bb_issue.get('state', 'unknown'),
                'kind': bb_issue.get('kind', 'bug'),
                'priority': bb_issue.get('priority', 'major'),
                'comments': len(comments),
                'attachments': len(attachments),
                'links_rewritten': links_in_body + links_in_comments,
                'bb_url': bb_issue.get('links', {}).get('html', {}).get('href', ''),
                'gh_url': f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_issue['number']}",
                'remarks': []
            })
            
            self.log(f"  ✓ Migrated issue #{issue_num} -> #{gh_issue['number']} with {len(comments)} comments and {len(attachments)} attachments")
            expected_num += 1

        # Report type usage statistics
        self.log(f"\nIssue Type Migration Summary:")
        self.log(f"  Using native issue types: {type_stats['using_native']}")
        self.log(f"  Using labels (fallback): {type_stats['using_labels']}")
        self.log(f"  No type specified: {type_stats['no_type']}")
        
        if type_fallbacks:
            self.log(f"\n  ℹ Types that fell back to labels:")
            fallback_summary = {}
            for bb_type, gh_type in type_fallbacks:
                fallback_summary[bb_type] = fallback_summary.get(bb_type, 0) + 1
            for bb_type, count in fallback_summary.items():
                gh_suggestion = self.map_bitbucket_type_to_github(bb_type)[1]
                self.log(f"    - '{bb_type}' ({count} issues) → Would map to '{gh_suggestion}' if available")

    def migrate_pull_requests(self, bb_prs: List[Dict[str, Any]], milestone_lookup: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """
        Migrate Bitbucket PRs to GitHub with intelligent branch checking.

        Strategy:
        - OPEN PRs: Try to create as GitHub PRs (if branches exist)
        - MERGED/DECLINED/SUPERSEDED PRs: Always migrate as issues (safest approach)

        This avoids any risk of re-merging already-merged code.

        Args:
            bb_prs: List of Bitbucket pull requests to migrate
            milestone_lookup: Optional mapping of milestone names to GitHub milestone data
        """
        milestone_lookup = milestone_lookup or {}
        
        self.log("="*80)
        self.log("PHASE 2: Migrating Pull Requests")
        self.log("="*80)
        
        if not bb_prs:
            self.log("No pull requests to migrate")
            return
        
        for bb_pr in bb_prs:
            pr_num = bb_pr['id']
            pr_state = bb_pr.get('state', 'UNKNOWN')
            title = bb_pr.get('title', f'PR #{pr_num}')
            source_branch = bb_pr.get('source', {}).get('branch', {}).get('name')
            dest_branch = bb_pr.get('destination', {}).get('branch', {}).get('name', 'main')
            
            self.log(f"Migrating PR #{pr_num} ({pr_state}): {title}")
            self.log(f"  Source: {source_branch} -> Destination: {dest_branch}")
            
            # Strategy: Only OPEN PRs become GitHub PRs (safest approach)
            if pr_state == 'OPEN':
                if source_branch and dest_branch:
                    # Check if both branches exist on GitHub
                    self.log(f"  Checking branch existence on GitHub...")
                    source_exists = self.check_branch_exists(source_branch)
                    dest_exists = self.check_branch_exists(dest_branch)
                    
                    if source_exists and dest_exists:
                        # Try to create as actual GitHub PR
                        self.log(f"  ✓ Both branches exist, creating as GitHub PR")
                        
                        body, links_in_body, inline_images_body = self.format_pr_body(bb_pr)

                        # Map milestone for PRs
                        milestone_number = None
                        if bb_pr.get('milestone'):
                            milestone_name = bb_pr['milestone'].get('name')
                            if milestone_name:
                                milestone_number = self.create_or_get_milestone(milestone_name, milestone_lookup.get(milestone_name))

                        # Track inline images
                        for img in inline_images_body:
                            self.attachments.append({
                                'pr_number': pr_num,
                                'github_pr': gh_pr['number'],
                                'filename': img['filename'],
                                'filepath': img['filepath'],
                                'type': 'inline_image'
                            })

                        gh_pr = self.create_gh_pr(
                            title=title,
                            body=body,
                            head=source_branch,
                            base=dest_branch
                        )
                        
                        # Apply milestone to PR (must be done after creation)
                        if milestone_number and gh_pr:
                            try:
                                url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/{gh_pr['number']}"
                                if not self.dry_run:
                                    response = self.gh_session.patch(url, json={'milestone': milestone_number})
                                    response.raise_for_status()
                                    self.log(f"    Applied milestone to PR #{gh_pr['number']}")
                                    self.rate_limit_sleep(0.5)
                                else:
                                    self.log(f"  [DRY RUN] Would apply milestone to PR #{gh_pr['number']}")
                            except Exception as e:
                                self.log(f"    Warning: Could not apply milestone to PR: {e}")

                        if gh_pr:
                            self.pr_mapping[pr_num] = gh_pr['number']
                            self.stats['prs_as_prs'] += 1
                            
                            # Record PR migration details
                            author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
                            gh_author = self.map_user(author) if author != 'Unknown (deleted user)' else None
                            
                            # Add comments
                            comments = self.fetch_bb_pr_comments(pr_num)
                            links_in_comments = 0
                            for comment in comments:
                                comment_body, comment_links, inline_images_comment = self.format_pr_comment_body(comment, 'pr', pr_num)
                                links_in_comments += comment_links
                                # Track inline images from PR comments
                                for img in inline_images_comment:
                                    self.attachments.append({
                                        'pr_number': pr_num,
                                        'github_pr': gh_pr['number'],
                                        'filename': img['filename'],
                                        'filepath': img['filepath'],
                                        'type': 'inline_image_comment'
                                    })
                                self.create_gh_comment(gh_pr['number'], comment_body, is_pr=True)
                            
                            self.pr_records.append({
                                'bb_number': pr_num,
                                'gh_number': gh_pr['number'],
                                'gh_type': 'PR',
                                'title': title,
                                'author': author,
                                'gh_author': gh_author,
                                'state': pr_state,
                                'source_branch': source_branch,
                                'dest_branch': dest_branch,
                                'comments': len(self.fetch_bb_pr_comments(pr_num)),
                                'links_rewritten': links_in_body + links_in_comments,
                                'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                                'gh_url': f"https://github.com/{self.gh_owner}/{self.gh_repo}/pull/{gh_pr['number']}",
                                'remarks': ['Migrated as GitHub PR', 'Branches exist on GitHub']
                            })

                            # Migrate PR attachments
                            pr_attachments = self.fetch_bb_pr_attachments(pr_num)
                            if pr_attachments:
                                self.log(f"  Migrating {len(pr_attachments)} PR attachments...")
                                for attachment in pr_attachments:
                                    att_name = attachment.get('name', 'unknown')
                                    att_url = attachment.get('links', {}).get('self', {}).get('href')
                                    
                                    if att_url:
                                        self.log(f"    Processing {att_name}...")
                                        if self.dry_run:
                                            self.attachments.append({
                                                'pr_number': pr_num,
                                                'github_pr': gh_pr['number'],
                                                'filename': att_name,
                                                'filepath': f"attachments_temp/{att_name}"
                                            })
                                        else:
                                            filepath = self.download_attachment(att_url, att_name)
                                            if filepath:
                                                self.upload_attachment_to_github(filepath, gh_pr['number'])
                                                self.attachments.append({
                                                    'pr_number': pr_num,
                                                    'github_pr': gh_pr['number'],
                                                    'filename': att_name,
                                                    'filepath': str(filepath)
                                                })

                            self.log(f"  ✓ Successfully migrated as PR #{gh_pr['number']} with {len(comments)} comments")
                            continue
                        else:
                            self.log(f"  ✗ Failed to create GitHub PR, falling back to issue migration")
                    else:
                        # Branches don't exist
                        self.log(f"  ✗ Cannot create as PR - branches missing on GitHub")
                        self.stats['pr_branch_missing'] += 1
                else:
                    self.log(f"  ✗ Missing branch information in Bitbucket data")
            else:
                # MERGED, DECLINED, or SUPERSEDED - always migrate as issue
                if self.skip_pr_as_issue:
                    self.log(f"  → Skipping migration as issue (PR was {pr_state}, --skip-pr-as-issue enabled)")
                else:
                    self.log(f"  → Migrating as issue (PR was {pr_state} - safest approach)")

                if pr_state in ['MERGED', 'SUPERSEDED']:
                    self.stats['pr_merged_as_issue'] += 1
            
            # Skip or migrate as issue based on flag
            if self.skip_pr_as_issue:
                self.log(f"  ✓ Skipped PR #{pr_num} (not migrated as issue due to --skip-pr-as-issue flag)")
                
                # Still record PR details for report
                author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
                gh_author = self.map_user(author) if author != 'Unknown (deleted user)' else None
                
                # Determine remarks
                remarks = ['Not migrated (--skip-pr-as-issue flag)']
                if pr_state in ['MERGED', 'SUPERSEDED']:
                    remarks.append('Original PR was merged')
                elif pr_state == 'DECLINED':
                    remarks.append('Original PR was declined')
                if not source_branch or not dest_branch:
                    remarks.append('Branch information missing')
                elif not self.check_branch_exists(source_branch) or not self.check_branch_exists(dest_branch):
                    remarks.append('One or both branches do not exist on GitHub')
                
                self.pr_records.append({
                    'bb_number': pr_num,
                    'gh_number': None,  # Not migrated
                    'gh_type': 'Skipped',
                    'title': title,
                    'author': author,
                    'gh_author': gh_author,
                    'state': pr_state,
                    'source_branch': source_branch or 'unknown',
                    'dest_branch': dest_branch or 'unknown',
                    'comments': 0,  # Not migrated, so no comments counted
                    'links_rewritten': 0,
                    'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                    'gh_url': '',  # No GitHub URL since not migrated
                    'remarks': remarks
                })
                
                continue  # Skip to next PR
            
            # Migrate as issue (for all non-open PRs or failed PR creation)
            self.log(f"  Creating as GitHub issue...")
            
            body, links_in_body, inline_images_body = self.format_pr_as_issue_body(bb_pr)

            # Map milestone for PRs migrated as issues
            milestone_number = None
            if bb_pr.get('milestone'):
                milestone_name = bb_pr['milestone'].get('name')
                if milestone_name:
                    milestone_number = self.create_or_get_milestone(milestone_name, milestone_lookup.get(milestone_name))

            # Track inline images
            for img in inline_images_body:
                self.attachments.append({
                    'pr_number': pr_num,
                    'github_issue': gh_issue['number'],
                    'filename': img['filename'],
                    'filepath': img['filepath'],
                    'type': 'inline_image'
                })
            
            # Determine labels based on original state
            labels = ['migrated-from-bitbucket', 'original-pr']
            if pr_state == 'MERGED':
                labels.append('pr-merged')
            elif pr_state == 'DECLINED':
                labels.append('pr-declined')
            elif pr_state == 'SUPERSEDED':
                labels.append('pr-superseded')
            
            gh_issue = self.create_gh_issue(
                title=f"[PR #{pr_num}] {title}",
                body=body,
                labels=labels,
                state='closed',  # Always close migrated PRs that are now issues
                milestone=milestone_number
            )
            
            self.pr_mapping[pr_num] = gh_issue['number']
            self.stats['prs_as_issues'] += 1
            
            # Add comments
            comments = self.fetch_bb_pr_comments(pr_num)
            links_in_comments = 0
            for comment in comments:
                comment_body, comment_links, inline_images_comment = self.format_pr_comment_body(comment, 'pr', pr_num)
                links_in_comments += comment_links

                # Track inline images from PR comments
                for img in inline_images_comment:
                    self.attachments.append({
                        'pr_number': pr_num,
                        'github_pr': gh_pr['number'],  # or gh_issue['number'] depending on path
                        'filename': img['filename'],
                        'filepath': img['filepath'],
                        'type': 'inline_image_comment'
                    })

                self.create_gh_comment(gh_issue['number'], comment_body)
            
            # Record PR-as-issue migration details (after comments are fetched)
            author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
            gh_author = self.map_user(author) if author != 'Unknown (deleted user)' else None
            
            # Determine remarks
            remarks = ['Migrated as GitHub Issue']
            if pr_state in ['MERGED', 'SUPERSEDED']:
                remarks.append('Original PR was merged - safer as issue to avoid re-merge')
            elif pr_state == 'DECLINED':
                remarks.append('Original PR was declined')
            if not source_branch or not dest_branch:
                remarks.append('Branch information missing')
            elif not self.check_branch_exists(source_branch) or not self.check_branch_exists(dest_branch):
                remarks.append('One or both branches do not exist on GitHub')
            
            self.pr_records.append({
                'bb_number': pr_num,
                'gh_number': gh_issue['number'],
                'gh_type': 'Issue',
                'title': title,
                'author': author,
                'gh_author': gh_author,
                'state': pr_state,
                'source_branch': source_branch or 'unknown',
                'dest_branch': dest_branch or 'unknown',
                'comments': len(comments),
                'links_rewritten': links_in_body + links_in_comments,
                'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                'gh_url': f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_issue['number']}",
                'remarks': remarks
            })
            
            self.log(f"  ✓ Migrated as Issue #{gh_issue['number']} with {len(comments)} comments")

            # Migrate PR attachments  
            pr_attachments = self.fetch_bb_pr_attachments(pr_num)
            if pr_attachments:
                self.log(f"  Migrating {len(pr_attachments)} PR attachments...")
                for attachment in pr_attachments:
                    att_name = attachment.get('name', 'unknown')
                    att_url = attachment.get('links', {}).get('self', {}).get('href')
                    
                    if att_url:
                        if self.dry_run:
                            self.attachments.append({
                                'pr_number': pr_num,
                                'github_issue': gh_issue['number'],
                                'filename': att_name,
                                'filepath': f"attachments_temp/{att_name}",
                                'type': 'pr_attachment'
                            })
                            self.log(f"    [DRY RUN] Would download {att_name}")
                        else:
                            self.log(f"    Downloading {att_name}...")
                            filepath = self.download_attachment(att_url, att_name)
                            if filepath:
                                self.log(f"    Creating attachment note...")
                                self.upload_attachment_to_github(filepath, gh_issue['number'])
                                self.attachments.append({
                                    'pr_number': pr_num,
                                    'github_issue': gh_issue['number'],
                                    'filename': att_name,
                                    'filepath': str(filepath),
                                    'type': 'pr_attachment'
                                })           
    
    def save_mapping(self, filename: str = 'migration_mapping.json') -> None:
        """
        Save issue/PR mapping to file.

        Args:
            filename: Output filename for the mapping JSON
        """
        mapping = {
            'bitbucket': {
                'workspace': self.bb_workspace,
                'repo': self.bb_repo
            },
            'github': {
                'owner': self.gh_owner,
                'repo': self.gh_repo
            },
            'issue_mapping': self.issue_mapping,
            'pr_mapping': self.pr_mapping,
            'statistics': self.stats,
            'migration_date': datetime.now().isoformat()
        }

        with open(filename, 'w') as f:
            json.dump(mapping, f, indent=2)

        self.log(f"Mapping saved to {filename}")

    def generate_migration_report(self, report_filename: str = 'migration_report.md') -> str:
        """
        Generate a comprehensive markdown migration report.

        Args:
            report_filename: Output filename for the report

        Returns:
            The filename where the report was saved
        """
        
        report = []
        report.append("# Bitbucket to GitHub Migration Report")
        report.append("")
        report.append(f"**Migration Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Source:** Bitbucket `{self.bb_workspace}/{self.bb_repo}`")
        report.append(f"**Destination:** GitHub `{self.gh_owner}/{self.gh_repo}`")
        report.append("")
        
        if self.dry_run:
            report.append("**⚠️ DRY RUN MODE** - This is a simulation report")
            report.append("")
        
        # Executive Summary
        report.append("## Executive Summary")
        report.append("")
        report.append(f"- **Total Issues Migrated:** {len(self.issue_records)}")
        report.append(f"  - Real Issues: {len([r for r in self.issue_records if r['state'] != 'deleted'])}")
        report.append(f"  - Placeholders: {len([r for r in self.issue_records if r['state'] == 'deleted'])}")

        # Issue Type Migration Summary
        if self.is_org_repo:
            report.append("")
            report.append("### Issue Type Migration")
            report.append("")
            
            if self.org_issue_types:
                report.append(f"**Organization Issue Types Available:** {', '.join(self.org_issue_types.keys())}")
                report.append("")
                
                # Analyze which Bitbucket types were mapped
                bb_types_found = {}
                for record in self.issue_records:
                    if record.get('kind'):
                        bb_types_found[record['kind']] = bb_types_found.get(record['kind'], 0) + 1
                
                if bb_types_found:
                    report.append("| Bitbucket Type | Count | GitHub Mapping | Status |")
                    report.append("|----------------|-------|----------------|--------|")
                    
                    for bb_type, count in sorted(bb_types_found.items()):
                        gh_type, is_available = self.map_bitbucket_type_to_github(bb_type)
                        if gh_type and is_available:
                            status = "✓ Using native type"
                        elif gh_type:
                            status = f"⚠️ Using label ('{gh_type}' not configured)"
                        else:
                            status = "⚠️ Using label (no mapping)"
                        
                        gh_mapping = gh_type if gh_type else f"type: {bb_type}"
                        report.append(f"| {bb_type} | {count} | {gh_mapping} | {status} |")
                    
                    report.append("")
                    report.append("**To use native issue types instead of labels:**")
                    report.append("1. Create missing issue types in your organization settings")
                    report.append("2. Re-run the migration (issues will use native types)")
                    report.append("")
            else:
                report.append("**No organization issue types configured.** Issues use labels for type classification.")
                report.append("")

        if self.milestone_mapping:
            report.append(f"- **Milestones Created:** {len(self.milestone_mapping)}")
            for bb_name, gh_num in sorted(self.milestone_mapping.items()):
                report.append(f"  - {bb_name} → Milestone #{gh_num}")

        # Calculate PR statistics
        total_prs = len(self.pr_records)
        skipped_prs = len([r for r in self.pr_records if r['gh_type'] == 'Skipped'])
        migrated_prs = total_prs - skipped_prs
        
        report.append(f"- **Total Pull Requests Processed:** {total_prs}")
        report.append(f"  - Migrated: {migrated_prs}")
        report.append(f"  - As GitHub PRs: {self.stats['prs_as_prs']}")
        report.append(f"  - As GitHub Issues: {self.stats['prs_as_issues']}")
        if skipped_prs > 0:
            report.append(f"  - Skipped (not migrated): {skipped_prs}")

        report.append(f"- **Total Attachments:** {len(self.attachments)}")
        report.append(f"- **Link Rewriting:**")
        report.append(f"  - Issues with rewritten links: {self.link_rewrites['issues']}")
        report.append(f"  - PRs with rewritten links: {self.link_rewrites['prs']}")
        report.append(f"  - Total links rewritten: {self.link_rewrites['total_links']}")
        
        if self.cross_repo_links_rewritten > 0:
            report.append(f"  - Cross-repository links rewritten: {self.cross_repo_links_rewritten}")
        
        report.append("")
        
        # Table of Contents
        report.append("## Table of Contents")
        report.append("")
        report.append("1. [Issues Migration](#issues-migration)")
        report.append("2. [Pull Requests Migration](#pull-requests-migration)")
        report.append("3. [Attachments](#attachments)")
        report.append("4. [User Mapping](#user-mapping)")
        report.append("5. [Unhandled Bitbucket Links](#-unhandled-bitbucket-links)")
        report.append("6. [Unmapped @Mentions](#-unmapped-mentions)")
        report.append("7. [Migration Statistics](#migration-statistics)")
        report.append("")
        
        # Issues Migration
        report.append("---")
        report.append("")
        report.append("## Issues Migration")
        report.append("")
        report.append(f"**Total Issues:** {len(self.issue_records)}")
        report.append("")
        
        # Issues table
        report.append("| BB # | GH # | Title | Reporter | State | Kind | Comments | Attachments | Links | Remarks |")
        report.append("|------|------|-------|----------|-------|------|----------|-------------|-------|---------|")
        
        for record in sorted(self.issue_records, key=lambda x: x['bb_number']):
            bb_num = record['bb_number']
            gh_num = record['gh_number']
            title = record['title'][:50] + ('...' if len(record['title']) > 50 else '')
            reporter = record['reporter'][:20] if record['reporter'] != 'N/A' else 'N/A'
            state = record['state']
            kind = record['kind']
            comments = record['comments']
            attachments = record['attachments']
            links = record.get('links_rewritten', 0)  # Use .get() with default
            remarks = ', '.join(record['remarks']) if record['remarks'] else '-'
            
            # Create links
            if record['bb_url']:
                bb_link = f"[#{bb_num}]({record['bb_url']})"
            else:
                bb_link = f"#{bb_num}"
            
            gh_link = f"[#{gh_num}]({record['gh_url']})"
            
            report.append(f"| {bb_link} | {gh_link} | {title} | {reporter} | {state} | {kind} | {comments} | {attachments} | {links} | {remarks} |")
        
        report.append("")
        
        # Pull Requests Migration
        report.append("---")
        report.append("")
        report.append("## Pull Requests Migration")
        report.append("")
        report.append(f"**Total Pull Requests:** {len(self.pr_records)}")
        report.append("")
        
        # PRs table
        report.append("| BB PR # | GH # | Type | Title | Author | State | Source → Dest | Comments | Links | Remarks |")
        report.append("|---------|------|------|-------|--------|-------|---------------|----------|-------|---------|")
        
        for record in sorted(self.pr_records, key=lambda x: x['bb_number']):
            bb_num = record['bb_number']
            gh_num = record['gh_number']
            gh_type = record['gh_type']
            title = record['title'][:40] + ('...' if len(record['title']) > 40 else '')
            author = record['author'][:20]
            state = record['state']
            branches = f"`{record['source_branch'][:15]}` → `{record['dest_branch'][:15]}`"
            comments = record['comments']
            links = record.get('links_rewritten', 0)  # Use .get() with default
            remarks = '<br>'.join(record['remarks'])
            
            # Create links
            bb_link = f"[PR #{bb_num}]({record['bb_url']})"
            
            if gh_num is None:
                gh_link = "Not migrated"
            elif gh_type == 'PR':
                gh_link = f"[PR #{gh_num}]({record['gh_url']})"
            else:
                gh_link = f"[Issue #{gh_num}]({record['gh_url']})"
            
            report.append(f"| {bb_link} | {gh_link} | {gh_type} | {title} | {author} | {state} | {branches} | {comments} | {links} | {remarks} |")
        
        report.append("")
        
        # Attachments
        report.append("---")
        report.append("")
        report.append("## Attachments")
        report.append("")
        report.append(f"**Total Attachments Downloaded:** {len(self.attachments)}")
        report.append("")
        
        if self.attachments:
            report.append("| Issue/PR | GitHub # | Type | Filename | Local Path |")
            report.append("|----------|----------|------|----------|------------|")
            
            for att in sorted(self.attachments, key=lambda x: x.get('issue_number', x.get('pr_number', 0))):
                issue_num = att.get('issue_number', att.get('pr_number', 'N/A'))
                gh_num = att.get('github_issue', att.get('github_pr', 'N/A'))
                filename = att['filename']
                filepath = att['filepath']
                att_type = att.get('type', 'attachment')
                
                item_label = f"Issue #{issue_num}" if 'issue_number' in att else f"PR #{issue_num}"
                report.append(f"| {item_label} | [#{gh_num}](https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}) | {att_type} | `{filename}` | `{filepath}` |")
            
            report.append("")
            report.append("**Note:** Attachments have been downloaded to the local `attachments_temp/` directory.")
            report.append("They need to be manually uploaded to the corresponding GitHub issues.")
        else:
            report.append("No attachments were found in the migration.")
        
        report.append("")
        
        # User Mapping
        report.append("---")
        report.append("")
        report.append("## User Mapping")
        report.append("")
        report.append("The following user mappings were used during migration:")
        report.append("")
        report.append("| Bitbucket User | GitHub User | Status |")
        report.append("|----------------|-------------|--------|")   

        # Collect all unique users from records
        all_users = set()
        for record in self.issue_records:
            if record['reporter'] not in ['N/A', 'Unknown (deleted user)']:
                all_users.add((record['reporter'], record['gh_reporter']))
        for record in self.pr_records:
            if record['author'] not in ['Unknown (deleted user)']:
                all_users.add((record['author'], record['gh_author']))
        
        for bb_user, gh_user in sorted(all_users, key=lambda x: x[0]):
            if gh_user:
                status = "✓ Mapped"
                gh_display = f"@{gh_user}"
            else:
                status = "⚠️ No GitHub account"
                gh_display = "-"
            
            report.append(f"| {bb_user} | {gh_display} | {status} |")
        
        report.append("")
        
        # Account ID Resolution Section
        if self.account_id_to_username or self.account_id_to_display_name:
            report.append("---")
            report.append("")
            report.append("## Account ID Resolution")
            report.append("")
            report.append("Bitbucket uses internal account IDs for @mentions in some contexts.")
            report.append("The migration script automatically resolves these to usernames or display names.")
            report.append("")
            
            # Collect all unique account IDs
            all_account_ids = set(self.account_id_to_username.keys()) | set(self.account_id_to_display_name.keys())
            
            if all_account_ids:
                report.append(f"**Total Account IDs Found:** {len(all_account_ids)}")
                report.append("")
                report.append("| Account ID | Bitbucket Username | Display Name | GitHub Mapping | Status |")
                report.append("|------------|-------------------|--------------|----------------|--------|")
                
                for account_id in sorted(all_account_ids):
                    username = self.account_id_to_username.get(account_id, 'N/A')
                    display_name = self.account_id_to_display_name.get(account_id, 'N/A')
                    
                    # Try to get GitHub mapping
                    gh_username = self.map_mention(account_id)
                    
                    if gh_username:
                        gh_mapping = f"`@{gh_username}`"
                        status = "✓ Mapped"
                    else:
                        gh_mapping = "-"
                        if username != 'N/A' or display_name != 'N/A':
                            status = "⚠️ Not mapped"
                        else:
                            status = "❌ Not resolved"
                    
                    # Truncate long account IDs for display
                    display_id = account_id if len(account_id) <= 40 else account_id[:37] + '...'
                    username_display = username if username != 'N/A' else '-'
                    display_name_display = display_name if display_name != 'N/A' else '-'
                    
                    report.append(f"| `{display_id}` | {username_display} | {display_name_display} | {gh_mapping} | {status} |")
                
                report.append("")
                report.append("**Resolution Methods:**")
                report.append("- **From Repository Data**: Account IDs found in issue/PR participants")
                report.append("- **Via API Lookup**: Account IDs not found in repo data, looked up via Bitbucket API")
                report.append("- **Display Name Only**: Username not available, using display name for mapping")
                report.append("")
                
                # Count statuses
                mapped_count = sum(1 for aid in all_account_ids if self.map_mention(aid))
                unmapped_count = len(all_account_ids) - mapped_count
                
                report.append("**Summary:**")
                report.append(f"- Mapped to GitHub: {mapped_count}")
                report.append(f"- Not mapped: {unmapped_count}")
                
                if unmapped_count > 0:
                    report.append("")
                    report.append("**Action Required for Unmapped Account IDs:**")
                    report.append("")
                    report.append("Add mappings to your config based on username or display name:")
                    report.append("```json")
                    report.append('"user_mapping": {')
                    
                    for account_id in sorted(all_account_ids):
                        if not self.map_mention(account_id):
                            username = self.account_id_to_username.get(account_id)
                            display_name = self.account_id_to_display_name.get(account_id)
                            key = username if username else display_name if display_name else account_id
                            report.append(f'  "{key}": "their-github-username",')
                    
                    report.append('}')
                    report.append("```")
                report.append("")


        # Unmapped Mentions
        if self.unmapped_mentions:
            report.append("---")
            report.append("")
            report.append("## ⚠️ Unmapped @Mentions")
            report.append("")
            report.append(f"**Total Unmapped Mentions:** {len(self.unmapped_mentions)} unique usernames")
            report.append(f"**Total Occurrences:** {sum(self.unmapped_mentions.values())}")
            report.append("")
            report.append("The following Bitbucket @mentions could not be mapped to GitHub usernames:")
            report.append("")
            report.append("- **Account IDs with display names** have been replaced with: `**Display Name** *(Bitbucket user, no GitHub account)*`")
            report.append("- **Usernames/Account IDs without display names** are preserved as: `@username *(Bitbucket user, needs GitHub mapping)*`")
            report.append("")
            report.append("| Bitbucket Username | Type | Resolved To | Occurrences | Suggested Mapping |")
            report.append("|--------------------|------|-------------|-------------|-------------------|")


            
            for bb_username, count in sorted(self.unmapped_mentions.items(), key=lambda x: x[1], reverse=True):
                # Check if this is an account ID
                is_account_id = ':' in bb_username or (len(bb_username) == 24 and all(c in '0123456789abcdef' for c in bb_username.lower()))

                # Check if this is a display name (from account ID resolution)
                # These are tracked under display name rather than account ID
                is_display_name_entry = not is_account_id and bb_username in self.account_id_to_display_name.values()
                
                if is_display_name_entry:
                    # This is a display name entry (account ID was already resolved and replaced)
                    mention_type = "Display Name"
                    resolved_to = "-"
                    suggestion = f'`"{bb_username}": "github-user"` (if they get a GitHub account)'
                    display_username = bb_username
                elif is_account_id:
                    # Check if we resolved it
                    resolved_username = self.account_id_to_username.get(bb_username)
                    display_name = self.account_id_to_display_name.get(bb_username)
                    
                    mention_type = "Account ID"
                    if resolved_username:
                        # Have username
                        resolved_to = f"`{resolved_username}`"
                        suggestion = f'`"{resolved_username}": "github-user"`'
                    elif display_name:
                        # Have display name but not username
                        resolved_to = f"`{display_name}` (display only)"
                        suggestion = f'`"{display_name}": "github-user"`'
                    else:
                        # Try API lookup as last resort
                        user_info = self.lookup_account_id_via_api(bb_username)
                        if user_info:
                            username = user_info.get('username') or user_info.get('nickname')
                            display = user_info.get('display_name')
                            
                            if username:
                                resolved_to = f"`{username}` (via API)"
                                suggestion = f'`"{username}": "github-user"`'
                            elif display:
                                resolved_to = f"`{display}` (via API)"
                                suggestion = f'`"{display}": "github-user"`'
                            else:
                                resolved_to = "❌ Not found"
                                suggestion = "User may be deleted"
                            
                            # Cache it
                            if username:
                                self.account_id_to_username[bb_username] = username
                            if display:
                                self.account_id_to_display_name[bb_username] = display
                        else:
                            resolved_to = "❌ Not found"
                            suggestion = "User may be deleted"
                else:
                    mention_type = "Username"
                    resolved_to = "-"
                    suggestion = f'`"{bb_username}": "github-user"`'
                    display_username = bb_username
                
                # Truncate long account IDs for display
                display_username = bb_username if len(bb_username) <= 40 else bb_username[:37] + '...'
                report.append(f"| `@{display_username}` | {mention_type} | {resolved_to} | {count} | {suggestion} |")

            
            report.append("")
            report.append("### How to Fix Unmapped Mentions")
            report.append("")
            report.append("**For Display Names (account IDs that were made readable):**")
            report.append("")
            report.append("These mentions have already been converted from cryptic account IDs to readable names.")
            report.append("They appear as `**Name** *(Bitbucket user, no GitHub account)*` in the migrated content.")
            report.append("")
            report.append("- If the user creates a GitHub account later, add: `\"Display Name\": \"their-github-username\"`")
            report.append("- Otherwise, no action needed - the readable format is already user-friendly")
            report.append("")
            report.append("**For Usernames and Unresolved Account IDs:**")
            report.append("")
            report.append("**Option 1: Add direct username mappings**")
            report.append("")
            report.append("```json")
            report.append('"user_mapping": {')
            # Only show non-display-name entries as examples
            non_display_entries = [u for u in self.unmapped_mentions.keys() 
                                  if u not in self.account_id_to_display_name.values()]
            for bb_username in non_display_entries[:3]:
                report.append(f'  "{bb_username}": "their-github-username",')
            if len(non_display_entries) > 3:
                report.append('  ...')
            report.append('}')
            report.append("```")
            report.append("")
            report.append("**Option 2: Manually fix on GitHub**")
            report.append("")
            report.append("Search for the pattern `*(Bitbucket user, needs GitHub mapping)*` in your issues/PRs")
            report.append("and edit the mentions directly on GitHub.")
            report.append("")
            report.append("**Note:** Display names from account IDs are already human-readable and don't need fixing")
            report.append("unless those users later get GitHub accounts.")
            report.append("")

        # Unhandled Bitbucket Links
        if self.unhandled_bb_links:
            report.append("---")
            report.append("")
            report.append("## ⚠️ Unhandled Bitbucket Links")
            report.append("")
            report.append(f"**Total Unhandled Links:** {len(self.unhandled_bb_links)}")
            report.append("")
            report.append("The following Bitbucket links were found but not automatically migrated. These may require manual attention:")
            report.append("")
            report.append("| Item | URL |")
            report.append("|------|-----|")
            
            for link_info in self.unhandled_bb_links:
                item_label = f"{link_info['item_type'].capitalize()} #{link_info['item_number']}"
                url = link_info['url']
                # Escape the URL to prevent markdown interpretation
                # Use inline code blocks for URL to prevent link rendering
                report.append(f"| {item_label} | `{url}` |")
            
            report.append("")
            report.append("**Context for each link:**")
            report.append("")
            
            for link_info in self.unhandled_bb_links:
                item_label = f"{link_info['item_type'].capitalize()} #{link_info['item_number']}"
                url = link_info['url']
                context = link_info['context'][:200]
                if len(link_info['context']) > 200:
                    context += '...'
                
                # Use code block for context to preserve all special characters
                report.append(f"- **{item_label}**: `{url}`")
                report.append(f"```\n")
                report.append(f"  {context}")
                report.append(f"\n```")
                report.append("")

            report.append("")
            report.append("**Common types of unhandled links:**")
            report.append("- Download links (`/downloads/`)")
            report.append("- Wiki pages (`/wiki/`)")
            report.append("- Repository settings/admin pages")
            report.append("- User profile links")
            report.append("- Branch comparison pages (complex formats)")
            report.append("- Snippet/gist links")
            report.append("")
            report.append("**Recommended actions:**")
            report.append("1. Review each link and determine if it needs migration")
            report.append("2. For downloads, consider hosting files elsewhere (GitHub Releases, etc.)")
            report.append("3. For wiki pages, migrate wiki separately")
            report.append("4. Update links manually in the migrated issues/PRs if needed")
            report.append("")    

        # Migration Statistics
        report.append("---")
        report.append("")
        report.append("## Migration Statistics")
        report.append("")
        
        report.append("### Issues")
        report.append("")
        report.append(f"- Total issues processed: {len(self.issue_records)}")
        report.append(f"- Real issues: {len([r for r in self.issue_records if r['state'] != 'deleted'])}")
        report.append(f"- Placeholder issues: {len([r for r in self.issue_records if r['state'] == 'deleted'])}")
        report.append(f"- Open issues: {len([r for r in self.issue_records if r['state'] in ['new', 'open']])}")
        report.append(f"- Closed issues: {len([r for r in self.issue_records if r['state'] not in ['new', 'open', 'deleted']])}")
        report.append(f"- Total comments: {sum(r['comments'] for r in self.issue_records)}")
        report.append(f"- Total attachments: {sum(r['attachments'] for r in self.issue_records)}")
        report.append("")
        
        report.append("### Pull Requests")
        report.append("")
        report.append(f"- Total PRs processed: {len(self.pr_records)}")
        report.append(f"- Migrated as GitHub PRs: {self.stats['prs_as_prs']}")
        report.append(f"- Migrated as GitHub Issues: {self.stats['prs_as_issues']}")
        report.append(f"  - Due to merged/closed state: {self.stats['pr_merged_as_issue']}")
        report.append(f"  - Due to missing branches: {self.stats['pr_branch_missing']}")
        report.append(f"- Total PR comments: {sum(r['comments'] for r in self.pr_records)}")
        report.append("")
        
        # State breakdown for PRs
        pr_states = {}
        for record in self.pr_records:
            state = record['state']
            pr_states[state] = pr_states.get(state, 0) + 1
        
        report.append("### Pull Request States")
        report.append("")
        for state, count in sorted(pr_states.items()):
            report.append(f"- {state}: {count}")
        report.append("")
        
        # Footer
        report.append("---")
        report.append("")
        report.append("## Notes")
        report.append("")
        report.append("- All issues maintain their original numbering from Bitbucket (with placeholders for gaps)")
        report.append("- Pull requests share the same numbering sequence as issues on GitHub")
        report.append("- Merged/closed PRs were migrated as issues to avoid re-merging code")
        report.append("- Original metadata (dates, authors, URLs) are preserved in issue/PR descriptions")
        report.append("- All comments include original author and timestamp information")
        report.append("- **Links to other issues/PRs have been rewritten:**")
        report.append("  - GitHub links are now primary (clickable)")
        report.append("  - Original Bitbucket references preserved in italics")
        report.append(f"  - Format: [#123](github_url) *(was [BB #123](bitbucket_url))*")
        report.append(f"  - Total of {self.link_rewrites['total_links']} cross-references updated")
        report.append("")
        report.append(f"**Migration completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        report.append("---")
        report.append("")
        report.append("*This report was automatically generated by the Bitbucket to GitHub migration script.*")
        
        # Write report to file
        report_content = '\n'.join(report)
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        self.log(f"Migration report saved to {report_filename}")
        
        return report_filename
    
    def print_summary(self) -> None:
        """Print migration summary statistics."""
        self.log("="*80)
        self.log("MIGRATION SUMMARY")
        self.log("="*80)

        self.log(f"Issues:")
        self.log(f"  Total migrated: {len(self.issue_mapping)}")

        if self.milestone_mapping:
            self.log(f"Milestones:")
            self.log(f"  Total created/mapped: {len(self.milestone_mapping)}")

        self.log(f"Pull Requests:")
        self.log(f"  Total processed: {len(self.pr_mapping)}")
        self.log(f"  Migrated as GitHub PRs: {self.stats['prs_as_prs']}")
        self.log(f"  Migrated as GitHub Issues: {self.stats['prs_as_issues']}")
        self.log(f"    - Due to merged/closed state: {self.stats['pr_merged_as_issue']}")
        self.log(f"    - Due to missing branches: {self.stats['pr_branch_missing']}")

        skipped_prs = len([r for r in self.pr_records if r['gh_type'] == 'Skipped'])
        if skipped_prs > 0:
            self.log(f"  Skipped (not migrated as issues): {skipped_prs}")

        self.log(f"Attachments:")
        self.log(f"  Total downloaded: {len(self.attachments)}")
        self.log(f"  Location: {self.attachment_dir}/")

        self.log(f"Link Rewriting:")
        self.log(f"  Issues with rewritten links: {self.link_rewrites['issues']}")
        self.log(f"  PRs with rewritten links: {self.link_rewrites['prs']}")
        self.log(f"  Total links rewritten: {self.link_rewrites['total_links']}")

        if self.cross_repo_links_rewritten > 0:
            self.log(f"  Cross-repository links rewritten: {self.cross_repo_links_rewritten}")

        if self.unhandled_bb_links:
            self.log(f"⚠️  Unhandled Bitbucket Links:")
            self.log(f"  Found {len(self.unhandled_bb_links)} Bitbucket link(s) that were not automatically migrated")
            self.log(f"  See migration report for details")

        if self.unmapped_mentions:
            self.log(f"⚠️  Unmapped @Mentions:")
            self.log(f"  Found {len(self.unmapped_mentions)} Bitbucket username(s) in @mentions")
            self.log(f"  Total occurrences: {sum(self.unmapped_mentions.values())}")
            self.log(f"  These have been preserved with notes - see migration report")

        self.log(f"Reports Generated:")
        self.log(f"  ✓ migration_mapping.json - Machine-readable mapping")
        if self.dry_run:
            self.log(f"  ✓ migration_report_dry_run.md - Comprehensive migration report")
        else:
            self.log(f"  ✓ migration_report.md - Comprehensive migration report")

        self.log("="*80)

    def diagnose_mentions(self, bb_issues: List[Dict[str, Any]], bb_prs: List[Dict[str, Any]]) -> None:
        """
        Diagnostic: scan all content for @ symbols and account IDs.

        This helps identify where account ID mentions are coming from.

        Args:
            bb_issues: List of Bitbucket issues to scan
            bb_prs: List of Bitbucket pull requests to scan
        """
        self.log("\n" + "="*80)
        self.log("DIAGNOSTIC: Scanning for @ mentions and account IDs")
        self.log("="*80)
        
        import re
        
        total_at_symbols = 0
        account_ids_found = []
        mentions_to_test = {}  # Track all unique mentions found

        # Scan issues
        self.log(f"Scanning {len(bb_issues)} issues...")
        for issue in bb_issues:
            content = issue.get('content', {}).get('raw', '')
            
            if content and '@' in content:
                # Extract all @mentions using same pattern as actual migration
                pattern_mention = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_][a-zA-Z0-9_-]*)'
                mentions = re.findall(pattern_mention, content)
                
                for mention_match in mentions:
                    # Remove braces if present
                    if mention_match.startswith('{') and mention_match.endswith('}'):
                        mention = mention_match[1:-1]
                    else:
                        mention = mention_match
                    
                    total_at_symbols += 1
                    
                    # Track this mention
                    if mention not in mentions_to_test:
                        mentions_to_test[mention] = {'count': 0, 'locations': []}
                    mentions_to_test[mention]['count'] += 1
                    mentions_to_test[mention]['locations'].append(('issue', issue['id']))
                    
                    # Check if account ID
                    if ':' in mention:
                        account_ids_found.append(('issue', issue['id'], mention, 'AAID'))
                    elif len(mention) == 24 and all(c in '0123456789abcdef' for c in mention.lower()):
                        account_ids_found.append(('issue', issue['id'], mention, 'Legacy'))

            # Also scan comments for this issue
            comments = self.fetch_bb_issue_comments(issue['id'])
            for comment in comments:
                comment_content = comment.get('content', {}).get('raw', '')
                if comment_content and '@' in comment_content:
                    pattern_mention = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_][a-zA-Z0-9_-]*)'
                    mentions = re.findall(pattern_mention, comment_content)
                    
                    for mention_match in mentions:
                        if mention_match.startswith('{') and mention_match.endswith('}'):
                            mention = mention_match[1:-1]
                        else:
                            mention = mention_match
                        
                        total_at_symbols += 1
                        
                        if mention not in mentions_to_test:
                            mentions_to_test[mention] = {'count': 0, 'locations': []}
                        mentions_to_test[mention]['count'] += 1
                        mentions_to_test[mention]['locations'].append(('issue_comment', issue['id']))
                        
                        if ':' in mention:
                            account_ids_found.append(('issue_comment', issue['id'], mention, 'AAID'))
                        elif len(mention) == 24 and all(c in '0123456789abcdef' for c in mention.lower()):
                            account_ids_found.append(('issue_comment', issue['id'], mention, 'Legacy'))

        # Scan PRs
        self.log(f"Scanning {len(bb_prs)} pull requests...")
        for pr in bb_prs:
            description = pr.get('description', '')
            
            if description and '@' in description:
                pattern_mention = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_][a-zA-Z0-9_-]*)'
                mentions = re.findall(pattern_mention, description)
                
                for mention_match in mentions:
                    if mention_match.startswith('{') and mention_match.endswith('}'):
                        mention = mention_match[1:-1]
                    else:
                        mention = mention_match
                    
                    total_at_symbols += 1
                    
                    if mention not in mentions_to_test:
                        mentions_to_test[mention] = {'count': 0, 'locations': []}
                    mentions_to_test[mention]['count'] += 1
                    mentions_to_test[mention]['locations'].append(('pr', pr['id']))
                    
                    # Check if account ID
                    if ':' in mention:
                        account_ids_found.append(('pr', pr['id'], mention, 'AAID'))
                    elif len(mention) == 24 and all(c in '0123456789abcdef' for c in mention.lower()):
                        account_ids_found.append(('pr', pr['id'], mention, 'Legacy'))

            # Also scan PR comments
            pr_comments = self.fetch_bb_pr_comments(pr['id'])
            for comment in pr_comments:
                comment_content = comment.get('content', {}).get('raw', '')
                if comment_content and '@' in comment_content:
                    pattern_mention = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_][a-zA-Z0-9_-]*)'
                    mentions = re.findall(pattern_mention, comment_content)
                    
                    for mention_match in mentions:
                        if mention_match.startswith('{') and mention_match.endswith('}'):
                            mention = mention_match[1:-1]
                        else:
                            mention = mention_match
                        
                        total_at_symbols += 1
                        
                        if mention not in mentions_to_test:
                            mentions_to_test[mention] = {'count': 0, 'locations': []}
                        mentions_to_test[mention]['count'] += 1
                        mentions_to_test[mention]['locations'].append(('pr_comment', pr['id']))
                        
                        if ':' in mention:
                            account_ids_found.append(('pr_comment', pr['id'], mention, 'AAID'))
                        elif len(mention) == 24 and all(c in '0123456789abcdef' for c in mention.lower()):
                            account_ids_found.append(('pr_comment', pr['id'], mention, 'Legacy'))

        self.log(f"\n" + "="*80)
        self.log(f"DIAGNOSTIC SUMMARY")
        self.log(f"="*80)
        self.log(f"Total @ symbols found: {total_at_symbols}")
        self.log(f"Unique @mentions found: {len(mentions_to_test)}")
        self.log(f"Account IDs detected: {len(account_ids_found)}")
        self.log("")
        
        # Test which mentions would be mapped/unmapped
        self.log("Testing mention mapping...")
        mapped_mentions = []
        unmapped_mentions = []
        
        for mention, data in sorted(mentions_to_test.items(), key=lambda x: x[1]['count'], reverse=True):
            gh_user = self.map_mention(mention)
            
            if gh_user:
                mapped_mentions.append((mention, gh_user, data['count']))
            else:
                unmapped_mentions.append((mention, data['count'], data['locations'][:3]))  # First 3 locations
        
        self.log("")
        self.log(f"✓ Mentions that WILL be mapped: {len(mapped_mentions)}")
        if mapped_mentions:
            for bb_mention, gh_user, count in mapped_mentions[:10]:
                self.log(f"  @{bb_mention} → @{gh_user} ({count} occurrences)")
            if len(mapped_mentions) > 10:
                self.log(f"  ... and {len(mapped_mentions) - 10} more")
        
        self.log("")
        self.log(f"⚠️  Mentions that will be UNMAPPED: {len(unmapped_mentions)}")
        if unmapped_mentions:
            for mention, count, locations in unmapped_mentions[:20]:
                loc_str = ', '.join([f"{t} #{n}" for t, n in locations])
                self.log(f"  @{mention} ({count} occurrences) - e.g. {loc_str}")
            if len(unmapped_mentions) > 20:
                self.log(f"  ... and {len(unmapped_mentions) - 20} more")
         
        self.log("")

        if account_ids_found:
            self.log(f"⚠️  Account IDs found: {len(account_ids_found)}")
            # Group by account ID
            from collections import defaultdict
            ids_by_value = defaultdict(list)
            for item_type, item_num, account_id, id_type in account_ids_found:
                ids_by_value[account_id].append((item_type, item_num, id_type))

            self.log("")
            self.log("  Account ID Resolution:")

            unresolved_ids = []  # Track IDs that need API lookup

            for account_id, occurrences in sorted(ids_by_value.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
                # Try to resolve this account ID from our mappings
                resolved_username = self.account_id_to_username.get(account_id)
                display_name = self.account_id_to_display_name.get(account_id)
                gh_username = self.map_mention(account_id)
                
                self.log(f"  @{account_id} ({len(occurrences)} occurrences)")
                
                # Check what we have
                has_username = resolved_username is not None
                has_display = display_name is not None
                
                if has_username or has_display:
                    # We have some info from the repo data
                    if has_username:
                        self.log(f"    ├─ Bitbucket username: {resolved_username}")
                    else:
                        self.log(f"    ├─ Bitbucket username: None (not in API response)")
                    
                    if has_display:
                        self.log(f"    ├─ Display name: {display_name}")
                    
                    if gh_username:
                        self.log(f"    └─ ✓ GitHub: @{gh_username}")
                    else:
                        self.log(f"    └─ ⚠️  Not mapped to GitHub")
                        # Give specific suggestion based on what we have
                        if has_username:
                            self.log(f"       Add to config: \"{resolved_username}\": \"github-username\"")
                        elif has_display:
                            self.log(f"       Add to config: \"{display_name}\": \"github-username\"")

                else:
                    # Not resolved from existing data - will need API lookup
                    unresolved_ids.append(account_id)
                    self.log(f"    └─ ⚠️  Not found in repo data (will lookup via API)")

                
                # Show sample locations (just first 2)
                for item_type, item_num, _ in occurrences[:2]:
                    self.log(f"       Found in: {item_type} #{item_num}")
            
            if len(ids_by_value) > 20:
                self.log(f"  ... and {len(ids_by_value) - 20} more account IDs")
            
            # Now lookup unresolved IDs via API
            if unresolved_ids:
                self.log("")
                self.log(f"  Looking up {len(unresolved_ids)} unresolved account ID(s) via Bitbucket API...")
                self.log(f"  Note: This requires user lookup permissions on your API token")

                for account_id in unresolved_ids[:10]:  # Limit to first 10 to avoid too many API calls
                    user_info = self.lookup_account_id_via_api(account_id)
                    
                    if user_info:
                        username = user_info.get('username') or user_info.get('nickname')
                        display = user_info.get('display_name', 'Unknown')
                        
                        self.log(f"    ✓ {account_id[:40]}...")
                        self.log(f"      → Username: {username or 'None'}")
                        self.log(f"      → Display: {display}")
                        
                        if username:
                            self.log(f"      Add to config: \"{username}\": \"github-username\"")
                        elif display:
                            self.log(f"      Add to config: \"{display}\": \"github-username\"")
                        
                        # Save this for future use
                        if username:
                            self.account_id_to_username[account_id] = username
                        if display:
                            self.account_id_to_display_name[account_id] = display
                    else:
                        self.log(f"    ✗ {account_id[:40]}... - Could not lookup (permission denied or deleted)")
                
                if len(unresolved_ids) > 10:
                    self.log(f"    ... and {len(unresolved_ids) - 10} more (not looked up)")

                self.log("")
                self.log(f"  If you see 403 errors, your API token may lack user lookup permissions")
                self.log(f"  This is OK - the display names from repo data are usually sufficient")

            self.log("")
            self.log(f"  NOTE: Account IDs are Bitbucket's internal identifiers")
            self.log(f"        The script will resolve them to usernames automatically")
            self.log(f"        Add username mappings to your config for unmapped accounts")
        else:
            self.log(f"✓ No account IDs found")
        
        self.log("="*80 + "\n")



def main():
    parser = argparse.ArgumentParser(
        description='Migrate Bitbucket repository to GitHub',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration file format (config.json):
{
  "bitbucket": {
    "workspace": "myworkspace",
    "repo": "myrepo",
    "email": "user@example.com",
    "token": "BITBUCKET_API_TOKEN"
  },
  "github": {
    "owner": "myuser",
    "repo": "myrepo",
    "token": "GITHUB_TOKEN"
  },
  "user_mapping": {
    "Bitbucket User": "github-username",
    "Another User": "another-gh-user",
    "User Without GitHub": null
  }
}

IMPROVEMENTS IN THIS VERSION:
- Branch existence checking before creating PRs
- Only OPEN PRs are migrated as GitHub PRs (if branches exist)
- MERGED/CLOSED PRs always become issues (safest - no re-merging!)
- Better logging showing branch status and migration decisions
- Migration statistics tracking
- **Automatic link rewriting** - References to other issues/PRs are rewritten to point to GitHub
- Comprehensive migration report in Markdown format

PR MIGRATION STRATEGY:
- OPEN PRs with existing branches → GitHub PRs (remain open)
- OPEN PRs with missing branches → GitHub Issues
- MERGED/DECLINED/SUPERSEDED PRs → GitHub Issues (always)

Why this approach?
- Avoids any risk of re-merging already-merged code
- Preserves full metadata for closed PRs in issue format
- Only active (OPEN) PRs become actual GitHub PRs
- Git history already contains all merged changes

LINK REWRITING:
- References to Bitbucket issues/PRs are automatically rewritten
- GitHub links become primary (clickable)
- Original Bitbucket references preserved for context
- Handles: Full URLs, #123 references, PR #45 references
- Works in: Issue descriptions, PR descriptions, all comments
- Example: #5 becomes [#8](github_url) *(was BB #5)*

User Mapping Notes:
- Map Bitbucket display names to GitHub usernames
- Use null or "" for users without GitHub accounts
- Unmapped users will be mentioned as "**Name** (no GitHub account)"
- Users without GitHub accounts won't be assigned to issues

Attachment Handling:
- Attachments are downloaded to ./attachments_temp/
- Attachment metadata is added as comments on GitHub issues
- Files are preserved locally for manual upload if needed
- GitHub API doesn't support direct attachment upload

Important: Before running this script:
1. Create an empty GitHub repository
2. Push your git history: git push --mirror github-url
3. Run the audit script first to understand what will be migrated
4. Create a user mapping configuration

Example:
  python migrate_bitbucket_to_github.py --config config.json
  python migrate_bitbucket_to_github.py --config config.json --dry-run
        """
    )
    
    parser.add_argument('--config', required=True, help='Path to configuration JSON file')
    parser.add_argument('--dry-run', action='store_true', help='Simulate migration without making changes')
    parser.add_argument('--skip-issues', action='store_true', help='Skip issue migration')
    parser.add_argument('--skip-prs', action='store_true', help='Skip PR migration')
    parser.add_argument('--skip-pr-as-issue', action='store_true', 
                        help='Skip migrating closed/merged PRs as issues (only migrate open PRs as PRs)')
    parser.add_argument('--use-gh-cli', action='store_true',
                        help='Use GitHub CLI to automatically upload attachments (requires gh CLI installed and authenticated)')
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = ConfigLoader.load_from_file(args.config)
    except ConfigurationError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except ValidationError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error loading configuration: {e}")
        sys.exit(1)
    
    # Create migrator
    migrator = BitbucketToGitHubMigrator(config)
    
    if args.dry_run:
        migrator.log("="*80)
        migrator.log("🔍 DRY RUN MODE ENABLED")
        migrator.log("="*80)
        migrator.log("This is a simulation - NO changes will be made to GitHub")
        migrator.log("")
        migrator.log("What WILL happen (read-only):")
        migrator.log("  ✓ Fetch all issues and PRs from Bitbucket")
        migrator.log("  ✓ Check if branches exist on GitHub")
        migrator.log("  ✓ Download attachments to local folder")
        migrator.log("  ✓ Validate user mappings")
        migrator.log("  ✓ Show exactly which PRs become GitHub PRs vs Issues")
        migrator.log("")
        migrator.log("What WON'T happen (no writes):")
        migrator.log("  ✗ No issues created on GitHub")
        migrator.log("  ✗ No PRs created on GitHub")
        migrator.log("  ✗ No comments added to GitHub")
        migrator.log("  ✗ No labels applied")
        migrator.log("")
        migrator.log("Use this to verify:")
        migrator.log("  • Bitbucket connection works")
        migrator.log("  • GitHub connection works (read-only check)")
        migrator.log("  • User mappings are correct")
        migrator.log("  • Branch existence (actual check)")
        migrator.log("  • PR migration strategy (which become PRs vs issues)")
        migrator.log("  • Exact GitHub issue/PR numbers that will be created")
        migrator.log("")
        migrator.log("After successful dry-run, remove --dry-run flag to migrate")
        migrator.log("="*80 + "\n")
    
    try:
        # Fetch data
        bb_issues = migrator.fetch_bb_issues() if not args.skip_issues else []
        bb_prs = migrator.fetch_bb_prs() if not args.skip_prs else []
        
        # Check if repository is under an organization and fetch issue types
        migrator.log("\nChecking repository type and issue type support...")
        migrator.is_org_repo = migrator.check_if_organization()
        if migrator.is_org_repo:
            migrator.org_issue_types = migrator.fetch_org_issue_types()

        # Build account ID mappings from the fetched data
        migrator.build_account_id_mappings(bb_issues, bb_prs)

        # Scan comments for additional account IDs
        # This catches account IDs in @mentions within comment text
        migrator.scan_comments_for_account_ids(bb_issues, bb_prs)

        # Lookup any unresolved account IDs via API before migration
        if migrator.account_id_to_display_name:
            migrator.log("\nChecking for unresolved account IDs...")
            
            # Find account IDs that have display names but no usernames
            unresolved_ids = []
            for account_id in migrator.account_id_to_display_name.keys():
                if account_id not in migrator.account_id_to_username or migrator.account_id_to_username[account_id] is None:
                    unresolved_ids.append(account_id)
            
            if unresolved_ids:
                migrator.log(f"  Found {len(unresolved_ids)} account ID(s) without usernames")
                migrator.log(f"  Attempting API lookup to resolve usernames...")
                
                resolved_count = 0
                for account_id in unresolved_ids:
                    user_info = migrator.lookup_account_id_via_api(account_id)
                    if user_info:
                        username = user_info.get('username') or user_info.get('nickname')
                        display_name = user_info.get('display_name')
                        
                        if username:
                            migrator.account_id_to_username[account_id] = username
                            resolved_count += 1
                            migrator.log(f"    ✓ Resolved {account_id[:40]}... → {username}")
                        if display_name and account_id not in migrator.account_id_to_display_name:
                            migrator.account_id_to_display_name[account_id] = display_name
                
                if resolved_count > 0:
                    migrator.log(f"  ✓ Resolved {resolved_count} account ID(s) to usernames")
                migrator.log("")

        # Fetch and create milestones before migration
        bb_milestones = migrator.fetch_bb_milestones()
        milestone_lookup = {}  # name -> full data
        
        if bb_milestones:
            migrator.log("\nCreating milestones on GitHub...")
            for milestone in bb_milestones:
                name = milestone.get('name')
                if name:
                    milestone_lookup[name] = milestone
                    # Pre-create milestone
                    migrator.create_or_get_milestone(name, milestone)

        # Diagnostic: check for account IDs in raw data
        if args.dry_run:
            migrator.diagnose_mentions(bb_issues, bb_prs)

        # Test GitHub connection (read-only, safe for dry-run)
        migrator.log("Testing GitHub connection...")
        try:
            # Test API access (read-only)
            test_url = f"https://api.github.com/repos/{migrator.gh_owner}/{migrator.gh_repo}"
            test_response = migrator.gh_session.get(test_url)
            test_response.raise_for_status()

            if migrator.dry_run:
                migrator.log("  ✓ GitHub connection successful (read-only check)")
            else:
                migrator.log("  ✓ GitHub connection successful")
        except requests.exceptions.HTTPError as e:
            if test_response.status_code == 401:
                migrator.log("  ✗ ERROR: GitHub authentication failed")
                migrator.log("  Please check your GitHub token in configuration file")
                raise AuthenticationError("GitHub authentication failed. Please check your token.")
            elif test_response.status_code == 404:
                migrator.log(f"  ✗ ERROR: Repository not found: {migrator.gh_owner}/{migrator.gh_repo}")
                migrator.log("  Please verify the repository exists and you have access")
                raise APIError(f"Repository not found: {migrator.gh_owner}/{migrator.gh_repo}", status_code=404)
            else:
                raise APIError(f"GitHub API error: {e}", status_code=test_response.status_code)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error testing GitHub connection: {e}")
        
        # Perform migration
        if not args.skip_issues:
            migrator.migrate_issues(bb_issues, milestone_lookup)
        
        if not args.skip_prs:
            migrator.migrate_pull_requests(bb_prs, milestone_lookup)
        
        # Save mapping
        migrator.save_mapping()
        
        # Generate comprehensive migration report
        if args.dry_run:
            migrator.generate_migration_report(report_filename = "migration_report_dry_run.md")
        else:
            migrator.generate_migration_report()
        
        # Print summary
        migrator.print_summary()
        
        # Print post-migration instructions
        if not args.dry_run and len(migrator.attachments) > 0:
            migrator.log("="*80)
            migrator.log("POST-MIGRATION: Attachment Handling")
            migrator.log("="*80)
            migrator.log(f"{len(migrator.attachments)} attachments were downloaded to: {migrator.attachment_dir}")
            
            if migrator.use_gh_cli:
                uploaded_count = len([a for a in migrator.attachments if a.get('uploaded', False)])
                migrator.log(f"✓ Attachments were automatically uploaded using GitHub CLI")
                migrator.log(f"  Successfully uploaded: {uploaded_count}/{len(migrator.attachments)}")
                
                failed_count = len(migrator.attachments) - uploaded_count
                if failed_count > 0:
                    migrator.log(f"⚠️  {failed_count} attachment(s) failed to upload")
                    migrator.log("  These need manual upload via drag-and-drop")
                    migrator.log("  Check migration.log for details")
                
                migrator.log(f"Note: Inline images in comments still need manual upload")
                migrator.log("      (gh CLI limitation - can't attach to comment edits)")
            else:
                migrator.log("To upload attachments to GitHub issues:")
                migrator.log("1. Navigate to the issue on GitHub")
                migrator.log("2. Click the comment box")
                migrator.log("3. Drag and drop the file from attachments_temp/")
                migrator.log("4. The file will be uploaded and embedded")
                migrator.log("Example:")
                migrator.log(f"  - Open: https://github.com/{migrator.gh_owner}/{migrator.gh_repo}/issues/1")
                migrator.log(f"  - Drag: {migrator.attachment_dir}/screenshot.png")
                migrator.log("  - File will appear in comment with URL")
                migrator.log("Note: Comments already note which attachments belonged to each issue.")
                migrator.log("Tip: Use --use-gh-cli flag to automatically upload attachments")
            
            migrator.log(f"Keep {migrator.attachment_dir}/ folder as backup until verified.")

            migrator.log("="*80 + "\n")
        
        # Print PR migration explanation
        if not args.dry_run and not args.skip_prs:
            migrator.log("="*80)
            migrator.log("ABOUT PR MIGRATION")
            migrator.log("="*80)
            migrator.log("PR Migration Strategy:")
            migrator.log(f"  - OPEN PRs with existing branches → GitHub PRs ({migrator.stats['prs_as_prs']} migrated)")
            migrator.log(f"  - All other PRs → GitHub Issues ({migrator.stats['prs_as_issues']} migrated)")
            migrator.log("Why merged PRs become issues:")
            migrator.log("  - Prevents re-merging already-merged code")
            migrator.log("  - Git history already contains all merged changes")
            migrator.log("  - Full metadata preserved in issue description")
            migrator.log("  - Safer approach - no risk of repository corruption")
            migrator.log("Merged PRs are labeled 'pr-merged' so you can easily identify them.")
            migrator.log("="*80 + "\n")
        
    except KeyboardInterrupt:
        migrator.log("Migration interrupted by user")
        migrator.save_mapping('migration_mapping_partial.json')
        sys.exit(1)
    except ConfigurationError as e:
        migrator.log(f"CONFIGURATION ERROR: {e}")
        sys.exit(1)
    except AuthenticationError as e:
        migrator.log(f"AUTHENTICATION ERROR: {e}")
        migrator.log("Please check your API tokens and permissions")
        sys.exit(1)
    except NetworkError as e:
        migrator.log(f"NETWORK ERROR: {e}")
        migrator.log("Please check your internet connection and try again")
        sys.exit(1)
    except ValidationError as e:
        migrator.log(f"VALIDATION ERROR: {e}")
        sys.exit(1)
    except MigrationError as e:
        migrator.log(f"MIGRATION ERROR: {e}")
        import traceback
        traceback.print_exc()
        migrator.save_mapping('migration_mapping_partial.json')
        sys.exit(1)
    except Exception as e:
        migrator.log(f"UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        migrator.save_mapping('migration_mapping_partial.json')
        sys.exit(1)


if __name__ == '__main__':
    main()