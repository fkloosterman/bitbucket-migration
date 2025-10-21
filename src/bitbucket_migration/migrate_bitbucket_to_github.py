#!/usr/bin/env python3
"""
Bitbucket to GitHub Migration Script

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

User Mapping:
    Maps Bitbucket display names to GitHub usernames in configuration file.
    Users without GitHub accounts are mentioned as "Name (no GitHub account)".
    Supports null values for users who shouldn't be mapped.

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

import argparse
import json
import sys
import time
import re
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
import requests
from pathlib import Path
from urllib.parse import urlparse
import subprocess
import shutil


class BitbucketToGitHubMigrator:
    def __init__(self, bb_workspace: str, bb_repo: str, bb_email: str, bb_token: str,
                 gh_owner: str, gh_repo: str, gh_token: str, user_mapping: Dict[str, str],
                 dry_run: bool = False, skip_pr_as_issue: bool = False,
                 use_gh_cli: bool = False):
        self.bb_workspace = bb_workspace
        self.bb_repo = bb_repo
        self.bb_email = bb_email
        self.bb_token = bb_token
        
        self.gh_owner = gh_owner
        self.gh_repo = gh_repo
        self.gh_token = gh_token
        
        self.user_mapping = user_mapping
        self.dry_run = dry_run
        self.skip_pr_as_issue = skip_pr_as_issue
        self.use_gh_cli = use_gh_cli
        
        # Check if gh CLI is available when requested
        if self.use_gh_cli and not self.dry_run:
            if not self.check_gh_cli_available():
                self.log("ERROR: --use-gh-cli specified but GitHub CLI is not available")
                self.log("Please install gh CLI: https://cli.github.com/")
                raise RuntimeError("GitHub CLI not available")

        # Setup API sessions
        self.bb_session = requests.Session()
        self.bb_session.auth = (bb_email, bb_token)
        
        self.gh_session = requests.Session()
        self.gh_session.headers.update({
            'Authorization': f'token {gh_token}',
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
    
    def rewrite_bitbucket_links(self, text: str, item_type: str = 'issue', item_number: int = None) -> tuple:
        """Rewrite Bitbucket issue/PR references to point to GitHub
        
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
        
    def log(self, message: str):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def rate_limit_sleep(self, duration: float = 1.0):
        """Sleep to avoid hitting rate limits"""
        if not self.dry_run:
            time.sleep(duration)
    
    def map_user(self, bb_username: str) -> Optional[str]:
        """Map Bitbucket username to GitHub username
        
        Returns:
            GitHub username if mapped, None if user doesn't have GitHub account
        """
        if not bb_username:
            return None
        
        gh_user = self.user_mapping.get(bb_username)
        
        # Return None if explicitly mapped to None or empty string
        if gh_user == "" or gh_user is None:
            return None
            
        return gh_user
    
    def check_gh_cli_available(self) -> bool:
        """Check if GitHub CLI is installed and authenticated"""
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
        """Check if a branch exists in the GitHub repository
        
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
        except Exception as e:
            self.log(f"    ✗ Error checking branch '{branch_name}': {e}")
            return False

    def fetch_bb_issues(self) -> List[dict]:
        """Fetch all issues from Bitbucket"""
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
    
    def fetch_bb_prs(self) -> List[dict]:
        """Fetch all pull requests from Bitbucket"""
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
    
    def fetch_bb_attachments(self, url, item='item', item_id=0) -> List[dict]:
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
            self.log(f"    Warning: HTTP error fetching attachments for {item} #{item_id}: {e}")
            return []
        except Exception as e:
            self.log(f"    Warning: Error fetching attachments for {item} #{item_id}: {e}")
            return []

    def fetch_bb_issue_attachments(self, issue_id: int) -> List[dict]:
        """Fetch attachments for a Bitbucket issue"""
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/issues/{issue_id}/attachments"
        return self.fetch_bb_attachments(url, "issue", issue_id)
    
    def fetch_bb_pr_attachments(self, pr_id: int) -> List[dict]:
        """Fetch attachments for a Bitbucket PR"""
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/pullrequests/{pr_id}/attachments"
        return self.fetch_bb_attachments(url, "PR", pr_id)

    def download_attachment(self, attachment_url: str, filename: str) -> Optional[Path]:
        """Download an attachment from Bitbucket"""
        try:
            response = self.bb_session.get(attachment_url, stream=True)
            response.raise_for_status()
            
            # Save to temp directory
            filepath = self.attachment_dir / filename
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return filepath
        except Exception as e:
            self.log(f"    ERROR downloading attachment {filename}: {e}")
            return None
    
    def upload_attachment_to_github(self, filepath: Path, issue_number: int) -> Optional[str]:
        """Upload attachment to GitHub issue/PR
        
        If --use-gh-cli is enabled, uses GitHub CLI to upload the file directly.
        Otherwise, creates a comment noting the attachment for manual upload.
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
    
    def fetch_bb_comments(self, url) ->List[dict]:
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

    def fetch_bb_issue_comments(self, issue_id: int) -> List[dict]:
        """Fetch comments for a Bitbucket issue"""
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/issues/{issue_id}/comments"
        return self.fetch_bb_comments(url)
    
    def fetch_bb_pr_comments(self, pr_id: int) -> List[dict]:
        """Fetch comments for a Bitbucket PR"""
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/pullrequests/{pr_id}/comments"
        return self.fetch_bb_comments(url)
    
    def extract_and_download_inline_images(self, text: str, item_type: str, item_number: int) -> tuple:
        """Extract Bitbucket-hosted inline images from markdown and download them
        
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

    def upload_inline_images_to_comment(self, comment_id: int, inline_images: List[dict]) -> bool:
        """Upload inline images to an existing GitHub comment using gh CLI
        
        Note: This appends the images to the comment. The user may want to 
        edit the comment to integrate them inline with the text.
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

    def create_gh_issue(self, title: str, body: str, labels: List[str] = None, 
                       state: str = 'open', assignees: List[str] = None) -> dict:
        """Create a GitHub issue"""
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues"
        
        payload = {
            'title': title,
            'body': body,
        }
        
        if labels:
            payload['labels'] = labels
        if assignees:
            payload['assignees'] = assignees
        
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
            if response.status_code == 401:
                self.log(f"  ERROR: GitHub authentication failed. Check your token.")
                raise
            elif response.status_code == 404:
                self.log(f"  ERROR: Repository {self.gh_owner}/{self.gh_repo} not found.")
                self.log(f"  Make sure the repository exists and your token has access.")
                raise
            else:
                self.log(f"  ERROR: Failed to create issue: {e}")
                raise
    
    def close_gh_issue(self, issue_number: int):
        """Close a GitHub issue"""
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/{issue_number}"
        
        if self.dry_run:
            self.log(f"  [DRY RUN] Would close issue #{issue_number}")
            return
        
        response = self.gh_session.patch(url, json={'state': 'closed'})
        response.raise_for_status()
        self.rate_limit_sleep(0.5)
    
    def create_gh_comment(self, issue_number: int, body: str, is_pr: bool = False):
        """Create a comment on a GitHub issue or PR
        
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
    
    def create_gh_pr(self, title: str, body: str, head: str, base: str) -> Optional[dict]:
        """Create a GitHub pull request
        
        Note: This creates an OPEN PR. Both head and base branches must exist.
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
            self.log(f"  ERROR: Could not create PR: {e}")
            if hasattr(response, 'text'):
                self.log(f"  Response: {response.text}")
            return None
    
    def close_gh_pr(self, pr_number: int):
        """Close a GitHub PR without merging
        
        This is safe - it just changes the PR state to 'closed' without
        performing any git operations.
        """
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/pulls/{pr_number}"
        
        if self.dry_run:
            self.log(f"  [DRY RUN] Would close PR #{pr_number}")
            return
        
        try:
            response = self.gh_session.patch(url, json={'state': 'closed'})
            response.raise_for_status()
            self.rate_limit_sleep(0.5)
        except Exception as e:
            self.log(f"  ERROR: Could not close PR #{pr_number}: {e}")
    
    def format_issue_body(self, bb_issue: dict) -> tuple:
        """Format issue body with metadata
        
        Returns:
            Tuple of (formatted_body, links_rewritten_count)
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
    
    def format_pr_as_issue_body(self, bb_pr: dict) -> tuple:
        """Format a PR (that will be migrated as an issue) with full metadata
        
        Returns:
            Tuple of (formatted_body, links_rewritten_count)
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
    
    def format_pr_body(self, bb_pr: dict) -> tuple:
        """Format PR body for an actual GitHub PR (for OPEN PRs)
        
        Returns:
            Tuple of (formatted_body, links_rewritten_count)
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
    
    def format_comment_body(self, bb_comment: dict, item_type: str = 'issue', item_number: int = None) -> tuple:
        """Format a comment with original author and timestamp
        
        Args:
            bb_comment: Bitbucket comment data
            item_type: 'issue' or 'pr' for link rewriting context
            item_number: The issue/PR number for link rewriting context
            
        Returns:
            Tuple of (formatted_comment, links_rewritten_count)
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
    
    def migrate_issues(self, bb_issues: List[dict]):
        """Migrate all Bitbucket issues to GitHub"""
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
            
            # Create issue
            gh_issue = self.create_gh_issue(
                title=bb_issue.get('title', f'Issue #{issue_num}'),
                body=body,
                labels=['migrated-from-bitbucket'],
                state='open' if bb_issue.get('state') in ['new', 'open'] else 'closed',
                assignees=assignees
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
    
    def migrate_pull_requests(self, bb_prs: List[dict]):
        """Migrate Bitbucket PRs to GitHub with intelligent branch checking
        
        Strategy:
        - OPEN PRs: Try to create as GitHub PRs (if branches exist)
        - MERGED/DECLINED/SUPERSEDED PRs: Always migrate as issues (safest approach)
        
        This avoids any risk of re-merging already-merged code.
        """
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
                        
                        if gh_pr:
                            self.pr_mapping[pr_num] = gh_pr['number']
                            self.stats['prs_as_prs'] += 1
                            
                            # Record PR migration details
                            author = bb_pr.get('author', {}).get('display_name', 'Unknown') if bb_pr.get('author') else 'Unknown (deleted user)'
                            gh_author = self.map_user(author) if author != 'Unknown (deleted user)' else None
                            
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
                                'bb_url': bb_pr.get('links', {}).get('html', {}).get('href', ''),
                                'gh_url': f"https://github.com/{self.gh_owner}/{self.gh_repo}/pull/{gh_pr['number']}",
                                'remarks': ['Migrated as GitHub PR', 'Branches exist on GitHub']
                            })
                            
                            # Add comments
                            comments = self.fetch_bb_pr_comments(pr_num)
                            for comment in comments:
                                comment_body = self.format_comment_body(comment, 'pr', pr_num)
                                self.create_gh_comment(gh_pr['number'], comment_body, is_pr=True)
                            
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
                state='closed'  # Always close migrated PRs that are now issues
            )
            
            self.pr_mapping[pr_num] = gh_issue['number']
            self.stats['prs_as_issues'] += 1
            
            # Add comments
            comments = self.fetch_bb_pr_comments(pr_num)
            links_in_comments = 0
            for comment in comments:
                comment_body, comment_links, inline_images_comment = self.format_comment_body(comment, 'pr', pr_num)
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
    
    def save_mapping(self, filename: str = 'migration_mapping.json'):
        """Save issue/PR mapping to file"""
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
    
    def generate_migration_report(self, report_filename: str = 'migration_report.md'):
        """Generate a comprehensive markdown migration report"""
        
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
        report.append("")
        
        # Table of Contents
        report.append("## Table of Contents")
        report.append("")
        report.append("1. [Issues Migration](#issues-migration)")
        report.append("2. [Pull Requests Migration](#pull-requests-migration)")
        report.append("3. [Attachments](#attachments)")
        report.append("4. [User Mapping](#user-mapping)")
        report.append("5. [Unhandled Bitbucket Links](#-unhandled-bitbucket-links)")
        report.append("6. [Migration Statistics](#migration-statistics)")
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
            report.append("| Item | URL | Context |")
            report.append("|------|-----|---------|")
            
            for link_info in self.unhandled_bb_links:
                item_label = f"{link_info['item_type'].capitalize()} #{link_info['item_number']}"
                url = link_info['url']
                # Truncate context and escape pipe characters
                context = link_info['context'][:100].replace('|', '\\|').replace('\n', ' ')
                if len(link_info['context']) > 100:
                    context += '...'
                
                report.append(f"| {item_label} | `{url}` | {context} |")
            
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
    
    def print_summary(self):
        """Print migration summary statistics"""
        self.log("="*80)
        self.log("MIGRATION SUMMARY")
        self.log("="*80)
        
        self.log(f"Issues:")
        self.log(f"  Total migrated: {len(self.issue_mapping)}")
        
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
        
        if self.unhandled_bb_links:
            self.log(f"⚠️  Unhandled Bitbucket Links:")
            self.log(f"  Found {len(self.unhandled_bb_links)} Bitbucket link(s) that were not automatically migrated")
            self.log(f"  See migration report for details")

        self.log(f"Reports Generated:")
        self.log(f"  ✓ migration_mapping.json - Machine-readable mapping")
        if self.dry_run:
            self.log(f"  ✓ migration_report_dry_run.md - Comprehensive migration report")
        else:
            self.log(f"  ✓ migration_report.md - Comprehensive migration report")
        
        self.log("="*80)


def load_config(config_file: str) -> dict:
    """Load configuration from JSON file"""
    with open(config_file, 'r') as f:
        return json.load(f)


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
    config = load_config(args.config)
    
    # Validate configuration
    required_keys = ['bitbucket', 'github', 'user_mapping']
    for key in required_keys:
        if key not in config:
            print(f"ERROR: Missing required key '{key}' in configuration file")
            sys.exit(1)
    
    # Create migrator
    migrator = BitbucketToGitHubMigrator(
        bb_workspace=config['bitbucket']['workspace'],
        bb_repo=config['bitbucket']['repo'],
        bb_email=config['bitbucket']['email'],
        bb_token=config['bitbucket']['token'],
        gh_owner=config['github']['owner'],
        gh_repo=config['github']['repo'],
        gh_token=config['github']['token'],
        user_mapping=config.get('user_mapping', {}),
        dry_run=args.dry_run,
        skip_pr_as_issue=args.skip_pr_as_issue,
        use_gh_cli=args.use_gh_cli
    )
    
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
        
        # Test GitHub connection (read-only, safe for dry-run)
        migrator.log("Testing GitHub connection...")
        try:
            # Test API access (read-only)
            test_url = f"https://api.github.com/repos/{config['github']['owner']}/{config['github']['repo']}"
            test_response = migrator.gh_session.get(test_url)
            test_response.raise_for_status()
            
            if args.dry_run:
                migrator.log("  ✓ GitHub connection successful (read-only check)")
            else:
                migrator.log("  ✓ GitHub connection successful")
        except requests.exceptions.HTTPError as e:
            if test_response.status_code == 401:
                migrator.log("  ✗ ERROR: GitHub authentication failed")
                migrator.log("  Please check your GitHub token in migration_config.json")
                sys.exit(1)
            elif test_response.status_code == 404:
                migrator.log(f"  ✗ ERROR: Repository not found: {config['github']['owner']}/{config['github']['repo']}")
                migrator.log("  Please verify the repository exists and you have access")
                sys.exit(1)
            else:
                raise
        
        # Perform migration
        if not args.skip_issues:
            migrator.migrate_issues(bb_issues)
        
        if not args.skip_prs:
            migrator.migrate_pull_requests(bb_prs)
        
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
                migrator.log(f"  - Open: https://github.com/{config['github']['owner']}/{config['github']['repo']}/issues/1")
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
    except Exception as e:
        migrator.log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        migrator.save_mapping('migration_mapping_partial.json')
        sys.exit(1)


if __name__ == '__main__':
    main()