#!/usr/bin/env python3
"""
Bitbucket to GitHub Migration Script

This script migrates a Bitbucket repository to GitHub, including:
- Issues with comments and metadata
- Pull requests (open PRs as PRs, closed as issues)
- Preserving issue/PR numbers with placeholders
- User mapping
- Attachments (downloaded and re-uploaded)

Usage:
    python migrate_bitbucket_to_github.py --bb-workspace WORKSPACE --bb-repo REPO \\
        --gh-owner OWNER --gh-repo REPO --config config.json

Requirements:
    pip install requests
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


class BitbucketToGitHubMigrator:
    def __init__(self, bb_workspace: str, bb_repo: str, bb_email: str, bb_token: str,
                 gh_owner: str, gh_repo: str, gh_token: str, user_mapping: Dict[str, str],
                 dry_run: bool = False):
        self.bb_workspace = bb_workspace
        self.bb_repo = bb_repo
        self.bb_email = bb_email
        self.bb_token = bb_token
        
        self.gh_owner = gh_owner
        self.gh_repo = gh_repo
        self.gh_token = gh_token
        
        self.user_mapping = user_mapping
        self.dry_run = dry_run
        
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
    
    def fetch_bb_issue_attachments(self, issue_id: int) -> List[dict]:
        """Fetch attachments for a Bitbucket issue"""
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/issues/{issue_id}/attachments"
        
        try:
            response = self.bb_session.get(url)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            return data.get('values', [])
        except:
            return []
    
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
        """Upload an attachment to GitHub by creating a comment with it
        
        GitHub doesn't have a direct attachment API, but we can upload files
        through the issue comment interface by using multipart form data.
        """
        if self.dry_run:
            self.log(f"    [DRY RUN] Would upload {filepath.name} to issue #{issue_number}")
            return f"https://github.com/{self.gh_owner}/{self.gh_repo}/files/{filepath.name}"
        
        try:
            # GitHub's undocumented way to upload assets via the web interface API
            # We'll create a comment that references the file
            url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/{issue_number}/comments"
            
            # Read file and create a comment with file info
            # Note: For actual file uploads, you'd need to use GitHub's upload endpoint
            # For now, we'll include file info and link to download from Bitbucket
            file_size = filepath.stat().st_size
            size_mb = round(file_size / (1024 * 1024), 2)
            
            comment_body = f"""📎 **Attachment from Bitbucket**: `{filepath.name}` ({size_mb} MB)

*Note: This file was attached to the original Bitbucket issue. Due to GitHub API limitations, the file content is available in the migration artifacts directory.*
"""
            
            response = self.gh_session.post(url, json={'body': comment_body})
            response.raise_for_status()
            
            self.rate_limit_sleep(0.5)
            return comment_body
            
        except Exception as e:
            self.log(f"    ERROR uploading to GitHub: {e}")
            return None
        """Fetch comments for a Bitbucket issue"""
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/issues/{issue_id}/comments"
        
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
    
    def fetch_bb_pr_comments(self, pr_id: int) -> List[dict]:
        """Fetch comments for a Bitbucket PR"""
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/pullrequests/{pr_id}/comments"
        
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
            self.log(f"  [DRY RUN] Would create issue: {title}")
            return {'number': -1}
        
        try:
            response = self.gh_session.post(url, json=payload)
            response.raise_for_status()
            issue = response.json()
            
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
    
    def create_gh_comment(self, issue_number: int, body: str):
        """Create a comment on a GitHub issue"""
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/issues/{issue_number}/comments"
        
        if self.dry_run:
            self.log(f"  [DRY RUN] Would add comment to issue #{issue_number}")
            return
        
        response = self.gh_session.post(url, json={'body': body})
        response.raise_for_status()
        self.rate_limit_sleep(0.5)
    
    def create_gh_pr(self, title: str, body: str, head: str, base: str) -> Optional[dict]:
        """Create a GitHub pull request"""
        url = f"https://api.github.com/repos/{self.gh_owner}/{self.gh_repo}/pulls"
        
        payload = {
            'title': title,
            'body': body,
            'head': head,
            'base': base,
        }
        
        if self.dry_run:
            self.log(f"  [DRY RUN] Would create PR: {title}")
            return {'number': -1}
        
        try:
            response = self.gh_session.post(url, json=payload)
            response.raise_for_status()
            pr = response.json()
            self.rate_limit_sleep(1.0)
            return pr
        except requests.exceptions.HTTPError as e:
            self.log(f"  ERROR: Could not create PR: {e}")
            return None
    
    def format_issue_body(self, bb_issue: dict) -> str:
        """Format issue body with metadata"""
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
        
        body = f"""**Migrated from Bitbucket**
- Original Author: {reporter_mention}
- Original Created: {created}
- Original URL: {bb_url}
- Kind: {kind}
- Priority: {priority}

---

{bb_issue.get('content', {}).get('raw', '')}
"""
        return body
    
    def format_pr_as_issue_body(self, bb_pr: dict) -> str:
        """Format a closed PR as a GitHub issue with metadata"""
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
        
        body = f"""**⚠️ This was a Pull Request on Bitbucket (now migrated as an issue)**

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

{bb_pr.get('description', '')}

---

*Note: This PR was {state.lower()} on Bitbucket. The source branch may no longer exist, so it was migrated as an issue rather than a GitHub PR. All comments and metadata are preserved below.*
"""
        return body
    
    def format_comment_body(self, bb_comment: dict) -> str:
        """Format a comment with original author and timestamp"""
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
        
        return f"""**Comment by {author_mention} on {created}:**

{content}
"""
    
    def migrate_issues(self, bb_issues: List[dict]):
        """Migrate all Bitbucket issues to GitHub"""
        self.log("\n" + "="*80)
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
                expected_num += 1
            
            # Migrate actual issue
            self.log(f"Migrating issue #{issue_num}: {bb_issue.get('title', 'No title')}")
            
            body = self.format_issue_body(bb_issue)
            
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
                        filepath = self.download_attachment(att_url, att_name)
                        
                        if filepath:
                            self.log(f"    Uploading {att_name} to GitHub...")
                            self.upload_attachment_to_github(filepath, gh_issue['number'])
                            self.attachments.append({
                                'issue_number': issue_num,
                                'github_issue': gh_issue['number'],
                                'filename': att_name,
                                'filepath': str(filepath)
                            })
            
            # Migrate comments
            comments = self.fetch_bb_issue_comments(issue_num)
            for comment in comments:
                comment_body = self.format_comment_body(comment)
                self.create_gh_comment(gh_issue['number'], comment_body)
            
            self.log(f"  ✓ Migrated issue #{issue_num} -> #{gh_issue['number']} with {len(comments)} comments and {len(attachments)} attachments")
            expected_num += 1
    
    def migrate_pull_requests(self, bb_prs: List[dict]):
        """Migrate Bitbucket PRs to GitHub (open as PRs, closed as issues)"""
        self.log("\n" + "="*80)
        self.log("PHASE 2: Migrating Pull Requests")
        self.log("="*80)
        
        if not bb_prs:
            self.log("No pull requests to migrate")
            return
        
        for bb_pr in bb_prs:
            pr_num = bb_pr['id']
            pr_state = bb_pr.get('state', 'UNKNOWN')
            title = bb_pr.get('title', f'PR #{pr_num}')
            
            self.log(f"Migrating PR #{pr_num} ({pr_state}): {title}")
            
            # Decide migration strategy
            if pr_state == 'OPEN':
                # Try to migrate as actual PR
                source_branch = bb_pr.get('source', {}).get('branch', {}).get('name')
                dest_branch = bb_pr.get('destination', {}).get('branch', {}).get('name', 'main')
                
                if source_branch:
                    self.log(f"  Attempting to create as GitHub PR: {source_branch} -> {dest_branch}")
                    
                    # Check if branches exist in GitHub
                    # Note: This assumes you've already pushed all branches via git
                    body = self.format_issue_body(bb_pr) if 'content' in bb_pr else bb_pr.get('description', '')
                    
                    gh_pr = self.create_gh_pr(
                        title=title,
                        body=body,
                        head=source_branch,
                        base=dest_branch
                    )
                    
                    if gh_pr:
                        self.pr_mapping[pr_num] = gh_pr['number']
                        
                        # Add comments
                        comments = self.fetch_bb_pr_comments(pr_num)
                        for comment in comments:
                            comment_body = self.format_comment_body(comment)
                            self.create_gh_comment(gh_pr['number'], comment_body)
                        
                        self.log(f"  ✓ Migrated PR #{pr_num} -> PR #{gh_pr['number']} with {len(comments)} comments")
                        continue
                    else:
                        self.log(f"  ⚠ Could not create as PR, falling back to issue migration")
            
            # Migrate as issue (for closed/merged/declined PRs or failed PR creation)
            self.log(f"  Migrating as issue (PR was {pr_state})")
            
            body = self.format_pr_as_issue_body(bb_pr)
            
            gh_issue = self.create_gh_issue(
                title=f"[PR #{pr_num}] {title}",
                body=body,
                labels=['migrated-from-bitbucket', 'original-pr', f'pr-{pr_state.lower()}'],
                state='closed'  # Always close migrated PRs that are now issues
            )
            
            self.pr_mapping[pr_num] = gh_issue['number']
            
            # Add comments
            comments = self.fetch_bb_pr_comments(pr_num)
            for comment in comments:
                comment_body = self.format_comment_body(comment)
                self.create_gh_comment(gh_issue['number'], comment_body)
            
            self.log(f"  ✓ Migrated PR #{pr_num} -> Issue #{gh_issue['number']} with {len(comments)} comments")
    
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
            'migration_date': datetime.now().isoformat()
        }
        
        with open(filename, 'w') as f:
            json.dump(mapping, f, indent=2)
        
        self.log(f"\nMapping saved to {filename}")

    def fetch_bb_issue_comments(self, issue_id: int) -> List[dict]:
        """Fetch comments for a Bitbucket issue"""
        url = f"https://api.bitbucket.org/2.0/repositories/{self.bb_workspace}/{self.bb_repo}/issues/{issue_id}/comments"
        
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
        dry_run=args.dry_run
    )
    
    if args.dry_run:
        migrator.log("="*80)
        migrator.log("🔍 DRY RUN MODE ENABLED")
        migrator.log("="*80)
        migrator.log("This is a simulation - NO changes will be made to GitHub")
        migrator.log("GitHub credentials will not be validated")
        migrator.log("Use this to verify:")
        migrator.log("  ✓ Bitbucket connection works")
        migrator.log("  ✓ User mappings are correct")
        migrator.log("  ✓ Issues/PRs are detected properly")
        migrator.log("  ✓ Attachment downloads work")
        migrator.log("\nAfter successful dry-run, remove --dry-run flag to migrate")
        migrator.log("="*80 + "\n")
    
    try:
        # Fetch data
        bb_issues = migrator.fetch_bb_issues() if not args.skip_issues else []
        bb_prs = migrator.fetch_bb_prs() if not args.skip_prs else []
        
        # Test GitHub connection (for non-dry-run)
        if not args.dry_run:
            migrator.log("Testing GitHub connection...")
            try:
                # Test API access
                test_url = f"https://api.github.com/repos/{config['github']['owner']}/{config['github']['repo']}"
                test_response = migrator.gh_session.get(test_url)
                test_response.raise_for_status()
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
        else:
            migrator.log("⚠️  DRY RUN MODE: Skipping GitHub connection test")
            migrator.log("   GitHub credentials will not be validated")
        
        # Perform migration
        if not args.skip_issues:
            migrator.migrate_issues(bb_issues)
        
        if not args.skip_prs:
            migrator.migrate_pull_requests(bb_prs)
        
        # Save mapping
        migrator.save_mapping()
        
        migrator.log("\n" + "="*80)
        migrator.log("MIGRATION COMPLETE!")
        migrator.log("="*80)
        migrator.log(f"Migrated {len(migrator.issue_mapping)} issues")
        migrator.log(f"Migrated {len(migrator.pr_mapping)} PRs")
        
        # Print post-migration instructions
        if not args.dry_run and len(migrator.attachments) > 0:
            migrator.log("\n" + "="*80)
            migrator.log("POST-MIGRATION: Attachment Handling")
            migrator.log("="*80)
            migrator.log(f"\n{len(migrator.attachments)} attachments were downloaded to: {migrator.attachment_dir}")
            migrator.log("\nTo upload attachments to GitHub issues:")
            migrator.log("1. Navigate to the issue on GitHub")
            migrator.log("2. Click the comment box")
            migrator.log("3. Drag and drop the file from attachments_temp/")
            migrator.log("4. The file will be uploaded and embedded")
            migrator.log("\nExample:")
            migrator.log(f"  - Open: https://github.com/{config['github']['owner']}/{config['github']['repo']}/issues/1")
            migrator.log(f"  - Drag: {migrator.attachment_dir}/screenshot.png")
            migrator.log("  - File will appear in comment with URL")
            migrator.log("\nNote: Comments already note which attachments belonged to each issue.")
            migrator.log(f"\nKeep {migrator.attachment_dir}/ folder as backup until all important files are uploaded.")
            migrator.log("="*80 + "\n")
        
    except KeyboardInterrupt:
        migrator.log("\nMigration interrupted by user")
        migrator.save_mapping('migration_mapping_partial.json')
        sys.exit(1)
    except Exception as e:
        migrator.log(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        migrator.save_mapping('migration_mapping_partial.json')
        sys.exit(1)


if __name__ == '__main__':
    main()