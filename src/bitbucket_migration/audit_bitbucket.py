#!/usr/bin/env python3
"""
Bitbucket to GitHub Migration Audit Script

⚠️  DISCLAIMER: This audit tool was developed with assistance from Claude.ai, an AI language model.
   Use at your own risk. Always verify audit results and API permissions before migration.

This script performs a comprehensive audit of a Bitbucket repository to assess migration
readiness and requirements for GitHub migration. It analyzes all repository content
and generates detailed reports to help plan and execute a successful migration.

PURPOSE:
    - Analyze repository structure and content for migration planning
    - Identify potential migration challenges and data preservation issues
    - Generate user mapping templates and migration configuration files
    - Provide detailed estimates for migration time and API requirements
    - Create comprehensive reports for stakeholders and migration teams

OUTPUTS GENERATED:
    - bitbucket_audit_report.json      - Complete audit data in JSON format
    - audit_report.md                  - Human-readable markdown report
    - bitbucket_issues_detail.json     - Detailed issue data for reference
    - bitbucket_prs_detail.json        - Detailed pull request data for reference
    - migration_config.json            - Migration configuration template (if --generate-config used)
    - user_mapping_template.txt        - User mapping reference file (if --generate-config used)

AUDIT INCLUDES:
    - Issue and pull request counts, states, and number gaps
    - User activity analysis and account mapping requirements
    - Attachment inventory with size calculations
    - Milestone and label usage tracking
    - PR migratability analysis (which PRs can be migrated as PRs vs issues)
    - Migration time and API call estimates

USAGE:
    Basic audit:
        python audit_bitbucket.py --workspace WORKSPACE --repo REPO --email EMAIL

    With API token provided:
        python audit_bitbucket.py --workspace WORKSPACE --repo REPO --email EMAIL --token API_TOKEN

    Generate migration configuration:
        python audit_bitbucket.py --workspace WORKSPACE --repo REPO --email EMAIL \\
            --generate-config --gh-owner GITHUB_USERNAME --gh-repo GITHUB_REPO

ARGUMENTS:
    --workspace WORKSPACE    Bitbucket workspace name (required)
    --repo REPO             Repository name within the workspace (required)
    --email EMAIL           Atlassian account email for API authentication (required)
    --token TOKEN           Bitbucket API token (prompted if not provided)
    --generate-config       Generate migration configuration template
    --gh-owner USERNAME     GitHub username/organization for config template
    --gh-repo REPO_NAME     GitHub repository name for config template

AUTHENTICATION:
    Requires a user-level API Token (NOT Repository Access Token)
    Create at: Settings > Atlassian account settings > Security > API tokens

    Required permissions:
        - Read access to repositories
        - Read access to pull requests
        - Read access to issues

    Note: Use your Atlassian account email (from Bitbucket > Personal settings > Email aliases)

REQUIREMENTS:
    pip install requests

EXAMPLES:
    # Basic audit with token prompt
    python audit_bitbucket.py --workspace myteam --repo myproject --email user@example.com

    # Audit with token provided
    python audit_bitbucket.py --workspace myteam --repo myproject \\
        --email user@example.com --token abc123def456

    # Generate migration config for GitHub migration
    python audit_bitbucket.py --workspace myteam --repo myproject \\
        --email user@example.com --generate-config \\
        --gh-owner myusername --gh-repo myproject

CREATING API TOKENS:
    1. Go to: Settings > Atlassian account settings > Security
    2. Click "Create and manage API tokens"
    3. Click "Create API token with scopes"
    4. Name it (e.g., "Migration Audit")
    5. Set expiry date
    6. Select "Bitbucket" as the app
    7. Select permissions (or "Full access" for simplicity)
    8. Click "Create" and copy the token

NOTES:
    - User-level API tokens replace App Passwords (deprecated Sept 2025)
    - Repository Access Tokens do NOT support issue APIs
    - The script handles deleted users and missing data gracefully
    - Large repositories may take several minutes to audit completely
"""

import argparse
import json
import sys
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Set, Tuple
import requests


class BitbucketAuditor:
    def __init__(self, workspace: str, repo: str, email: str, api_token: str):
        self.workspace = workspace
        self.repo = repo
        self.email = email
        self.api_token = api_token
        self.base_url = "https://api.bitbucket.org/2.0"
        self.session = requests.Session()
        # Use HTTP Basic Auth with Atlassian email and API token
        self.session.auth = (email, api_token)
        
        # Data storage
        self.issues = []
        self.pull_requests = []
        self.users = set()
        self.labels = Counter()
        self.milestones = set()
        self.attachments = []
        
        # User activity tracking
        self.user_stats = defaultdict(lambda: {
            'issues_created': 0,
            'issues_assigned': 0,
            'prs_created': 0,
            'issue_comments': 0,
            'pr_comments': 0,
            'pr_reviews': 0,
            'commits': 0
        })
        
    def _paginate(self, url: str, params: dict = None) -> List[dict]:
        """Fetch all pages of results from Bitbucket API"""
        results = []
        next_url = url
        first_request = True
        
        while next_url:
            try:
                # Only use params on the first request
                # Bitbucket's 'next' URL already includes all necessary parameters
                if first_request and params:
                    response = self.session.get(next_url, params=params)
                    first_request = False
                else:
                    response = self.session.get(next_url)
                
                # Check for errors
                if response.status_code == 403:
                    print(f"  ERROR: 403 Forbidden - API token may lack permissions for: {url}", file=sys.stderr)
                    print(f"  Check that your API token has the necessary read permissions", file=sys.stderr)
                    break
                elif response.status_code == 404:
                    # 404 can be normal for some resources (deleted branches, etc.)
                    # Don't print error, just return empty list
                    break
                    
                response.raise_for_status()
                data = response.json()
                
                if 'values' in data:
                    results.extend(data['values'])
                else:
                    results.append(data)
                
                next_url = data.get('next')
                
            except requests.exceptions.HTTPError as e:
                if response.status_code == 404:
                    # Already handled above, just break
                    break
                print(f"  HTTP Error {response.status_code}: {e}", file=sys.stderr)
                print(f"  URL: {url}", file=sys.stderr)
                print(f"  Response: {response.text[:500]}", file=sys.stderr)
                break
            except requests.exceptions.RequestException as e:
                print(f"  Error fetching data: {e}", file=sys.stderr)
                break
                
        return results
    
    def audit_issues(self):
        """Audit all issues in the repository"""
        print("Auditing issues...")
        url = f"{self.base_url}/repositories/{self.workspace}/{self.repo}/issues"
        
        # Fetch all issues (open and closed)
        all_issues = self._paginate(url, params={'pagelen': 100})
        
        for issue in all_issues:
            issue_data = {
                'number': issue['id'],
                'title': issue['title'],
                'state': issue['state'],
                'kind': issue.get('kind', 'bug'),
                'priority': issue.get('priority', 'major'),
                'created_on': issue['created_on'],
                'updated_on': issue['updated_on'],
                'reporter': issue.get('reporter', {}).get('display_name', 'Unknown') if issue.get('reporter') else 'Unknown (deleted user)',
                'assignee': issue.get('assignee', {}).get('display_name') if issue.get('assignee') else None,
                'comment_count': 0,
                'attachment_count': 0,
                'votes': issue.get('votes', 0),
            }
            
            # Collect users - handle deleted/missing users gracefully
            if issue.get('reporter') and issue.get('reporter', {}).get('display_name'):
                reporter_name = issue['reporter'].get('display_name', 'Unknown')
                self.users.add(reporter_name)
                self.user_stats[reporter_name]['issues_created'] += 1
            else:
                # User account deleted or missing
                self.users.add('Unknown (deleted user)')
                
            if issue.get('assignee') and issue.get('assignee', {}).get('display_name'):
                assignee_name = issue['assignee'].get('display_name')
                self.users.add(assignee_name)
                self.user_stats[assignee_name]['issues_assigned'] += 1
            
            # Collect milestone
            if issue.get('milestone'):
                self.milestones.add(issue['milestone'].get('name'))
            
            # Fetch comments for this issue
            comments_url = f"{self.base_url}/repositories/{self.workspace}/{self.repo}/issues/{issue['id']}/comments"
            comments = self._paginate(comments_url)
            issue_data['comment_count'] = len(comments)
            
            for comment in comments:
                if comment.get('user') and comment.get('user', {}).get('display_name'):
                    commenter_name = comment['user'].get('display_name', 'Unknown')
                    self.users.add(commenter_name)
                    self.user_stats[commenter_name]['issue_comments'] += 1
                else:
                    self.users.add('Unknown (deleted user)')
            
            # Fetch attachments
            attachments_url = f"{self.base_url}/repositories/{self.workspace}/{self.repo}/issues/{issue['id']}/attachments"
            try:
                response = self.session.get(attachments_url)
                if response.status_code == 200:
                    attachments_data = response.json()
                    attachments = attachments_data.get('values', [])
                    issue_data['attachment_count'] = len(attachments)
                    
                    for attachment in attachments:
                        self.attachments.append({
                            'issue_number': issue['id'],
                            'type': 'issue',
                            'name': attachment.get('name'),
                            'size': attachment.get('size', 0),
                        })
            except:
                pass
            
            self.issues.append(issue_data)
        
        print(f"  Found {len(self.issues)} issues")
        
    def audit_pull_requests(self):
        """Audit all pull requests in the repository"""
        print("Auditing pull requests...")
        url = f"{self.base_url}/repositories/{self.workspace}/{self.repo}/pullrequests"
        
        # Fetch all PRs - IMPORTANT: must specify state to get all PRs, not just OPEN
        # Valid states: MERGED, SUPERSEDED, OPEN, DECLINED
        # Note: PR endpoint has max pagelen of 50 (not 100 like other endpoints)
        params = {'state': 'MERGED,SUPERSEDED,OPEN,DECLINED', 'pagelen': 50}
        
        print(f"  Fetching PRs with params: {params}")
        all_prs = self._paginate(url, params=params)
        print(f"  API returned {len(all_prs)} pull requests")
        
        if len(all_prs) == 0:
            print("  WARNING: No pull requests found. This could mean:")
            print("    - The repository has no PRs")
            print("    - The API token lacks pull request read permissions")
            print("    - There's an API authentication issue")
            print("  Continuing with audit...")
        
        for pr in all_prs:
            pr_data = {
                'number': pr['id'],
                'title': pr['title'],
                'state': pr['state'],
                'created_on': pr['created_on'],
                'updated_on': pr['updated_on'],
                'author': pr.get('author', {}).get('display_name', 'Unknown'),
                'source_branch': pr.get('source', {}).get('branch', {}).get('name'),
                'destination_branch': pr.get('destination', {}).get('branch', {}).get('name'),
                'comment_count': pr.get('comment_count', 0),
                'task_count': pr.get('task_count', 0),
                'participants': len(pr.get('participants', [])),
                'reviewers': len(pr.get('reviewers', [])),
                'commit_count': 0,
                'migratable': True,  # Can we migrate this PR?
                'migration_issues': []  # What problems might we encounter?
            }
            
            # Check if source branch still exists
            if pr_data['source_branch']:
                # We'll assume branch exists for now - checking every branch would be too slow
                # But we can check the PR state
                if pr_data['state'] in ['MERGED', 'DECLINED', 'SUPERSEDED']:
                    # These PRs might have deleted branches
                    pr_data['migration_issues'].append(f"PR is {pr_data['state']} - source branch may be deleted")
                    pr_data['migratable'] = False
            else:
                pr_data['migration_issues'].append("No source branch information")
                pr_data['migratable'] = False
            
            # Collect users
            if pr.get('author'):
                author_name = pr['author'].get('display_name', 'Unknown')
                self.users.add(author_name)
                self.user_stats[author_name]['prs_created'] += 1
            
            for participant in pr.get('participants', []):
                if participant.get('user'):
                    participant_name = participant['user'].get('display_name', 'Unknown')
                    self.users.add(participant_name)
            
            for reviewer in pr.get('reviewers', []):
                if reviewer.get('display_name'):
                    reviewer_name = reviewer.get('display_name')
                    self.users.add(reviewer_name)
                    self.user_stats[reviewer_name]['pr_reviews'] += 1
            
            # Fetch comments
            comments_url = f"{self.base_url}/repositories/{self.workspace}/{self.repo}/pullrequests/{pr['id']}/comments"
            comments = self._paginate(comments_url)
            pr_data['comment_count'] = len(comments)
            
            for comment in comments:
                if comment.get('user') and comment.get('user', {}).get('display_name'):
                    commenter_name = comment['user'].get('display_name', 'Unknown')
                    self.users.add(commenter_name)
                    self.user_stats[commenter_name]['pr_comments'] += 1
                else:
                    self.users.add('Unknown (deleted user)')
            
            # Fetch commits in this PR
            commits_url = f"{self.base_url}/repositories/{self.workspace}/{self.repo}/pullrequests/{pr['id']}/commits"
            try:
                commits = self._paginate(commits_url)
                pr_data['commit_count'] = len(commits)
                
                for commit in commits:
                    if commit.get('author') and commit['author'].get('user'):
                        commit_author = commit['author']['user'].get('display_name', 'Unknown')
                        self.users.add(commit_author)
                        self.user_stats[commit_author]['commits'] += 1
            except Exception as e:
                # Some PRs may not have accessible commits (declined, branch deleted, etc.)
                pr_data['commit_count'] = 0
                pr_data['migration_issues'].append("Commits not accessible (branch may be deleted)")
                if pr_data['state'] != 'OPEN':
                    pr_data['migratable'] = False
            
            self.pull_requests.append(pr_data)
        
        print(f"  Found {len(self.pull_requests)} pull requests")
    
    def analyze_pr_migratability(self) -> dict:
        """Analyze which PRs can be migrated completely vs partially"""
        fully_migratable = []  # Open PRs with branches intact
        partially_migratable = []  # Closed PRs - can migrate as issues
        migration_challenges = []  # PRs with specific issues
        
        for pr in self.pull_requests:
            pr_analysis = {
                'number': pr['number'],
                'title': pr['title'],
                'state': pr['state'],
                'source_branch': pr['source_branch'],
                'can_migrate_as_pr': pr['migratable'],
                'issues': pr['migration_issues'],
                'data_preserved': {
                    'description': True,
                    'comments': pr['comment_count'] > 0,
                    'commits': pr['commit_count'] > 0,
                    'reviewers': pr['reviewers'] > 0,
                    'diff': pr['migratable'],  # Only if branches exist
                }
            }
            
            if pr['state'] == 'OPEN' and pr['migratable']:
                fully_migratable.append(pr_analysis)
            elif pr['state'] in ['MERGED', 'DECLINED', 'SUPERSEDED']:
                partially_migratable.append(pr_analysis)
            else:
                migration_challenges.append(pr_analysis)
        
        return {
            'fully_migratable': {
                'count': len(fully_migratable),
                'prs': fully_migratable
            },
            'partially_migratable': {
                'count': len(partially_migratable),
                'prs': partially_migratable,
                'note': 'These PRs can be migrated as issues with PR metadata in description'
            },
            'migration_challenges': {
                'count': len(migration_challenges),
                'prs': migration_challenges
            }
        }
        """Analyze number gaps in issues or PRs"""
        if not items:
            return [], 0
        
        numbers = sorted([item['number'] for item in items])
        gaps = []
        
        if numbers:
            expected = 1
            for num in numbers:
                while expected < num:
                    gaps.append(expected)
                    expected += 1
                expected = num + 1
        
        return gaps, len(gaps)
    
    def analyze_gaps(self, items: List[dict]) -> Tuple[List[int], int]:
        """Analyze number gaps in issues or PRs"""
        if not items:
            return [], 0
        
        numbers = sorted([item['number'] for item in items])
        gaps = []
        
        if numbers:
            expected = 1
            for num in numbers:
                while expected < num:
                    gaps.append(expected)
                    expected += 1
                expected = num + 1
        
        return gaps, len(gaps)
    
    def generate_report(self) -> dict:
        """Generate comprehensive audit report"""
        print("\nGenerating report...")
        
        issue_gaps, issue_gap_count = self.analyze_gaps(self.issues)
        pr_gaps, pr_gap_count = self.analyze_gaps(self.pull_requests)
        
        # Analyze PR migratability
        pr_migration_analysis = self.analyze_pr_migratability()
        
        # Calculate attachment sizes
        total_attachment_size = sum(a['size'] for a in self.attachments)
        
        # Analyze issue states
        issue_states = Counter(i['state'] for i in self.issues)
        pr_states = Counter(p['state'] for p in self.pull_requests)
        
        # Calculate date ranges
        def get_date_range(items, date_field='created_on'):
            if not items:
                return None, None
            dates = [datetime.fromisoformat(i[date_field].replace('Z', '+00:00')) for i in items]
            return min(dates), max(dates)
        
        issue_first, issue_last = get_date_range(self.issues)
        pr_first, pr_last = get_date_range(self.pull_requests)
        
        report = {
            'repository': {
                'workspace': self.workspace,
                'repo': self.repo,
                'audit_date': datetime.now().isoformat(),
            },
            'issues': {
                'total': len(self.issues),
                'by_state': dict(issue_states),
                'number_range': {
                    'min': min([i['number'] for i in self.issues]) if self.issues else 0,
                    'max': max([i['number'] for i in self.issues]) if self.issues else 0,
                },
                'gaps': {
                    'count': issue_gap_count,
                    'numbers': issue_gaps[:50],  # First 50 gaps
                    'note': f"Showing first 50 of {issue_gap_count} gaps" if issue_gap_count > 50 else "All gaps shown"
                },
                'date_range': {
                    'first': issue_first.isoformat() if issue_first else None,
                    'last': issue_last.isoformat() if issue_last else None,
                },
                'total_comments': sum(i['comment_count'] for i in self.issues),
                'with_attachments': sum(1 for i in self.issues if i['attachment_count'] > 0),
            },
            'pull_requests': {
                'total': len(self.pull_requests),
                'by_state': dict(pr_states),
                'number_range': {
                    'min': min([p['number'] for p in self.pull_requests]) if self.pull_requests else 0,
                    'max': max([p['number'] for p in self.pull_requests]) if self.pull_requests else 0,
                },
                'gaps': {
                    'count': pr_gap_count,
                    'numbers': pr_gaps[:50],
                    'note': f"Showing first 50 of {pr_gap_count} gaps" if pr_gap_count > 50 else "All gaps shown"
                },
                'date_range': {
                    'first': pr_first.isoformat() if pr_first else None,
                    'last': pr_last.isoformat() if pr_last else None,
                },
                'total_comments': sum(p['comment_count'] for p in self.pull_requests),
            },
            'attachments': {
                'total': len(self.attachments),
                'total_size_bytes': total_attachment_size,
                'total_size_mb': round(total_attachment_size / (1024 * 1024), 2),
                'by_issue': sum(1 for a in self.attachments if a['type'] == 'issue'),
            },
            'users': {
                'total_unique': len(self.users),
                'list': sorted(list(self.users)),
                'activity_breakdown': {
                    user: {
                        'issues_created': stats['issues_created'],
                        'issues_assigned': stats['issues_assigned'],
                        'prs_created': stats['prs_created'],
                        'issue_comments': stats['issue_comments'],
                        'pr_comments': stats['pr_comments'],
                        'pr_reviews': stats['pr_reviews'],
                        'commits': stats['commits'],
                        'total_activity': (
                            stats['issues_created'] + 
                            stats['issues_assigned'] + 
                            stats['prs_created'] + 
                            stats['issue_comments'] + 
                            stats['pr_comments'] + 
                            stats['pr_reviews'] +
                            stats['commits']
                        )
                    }
                    for user, stats in sorted(
                        self.user_stats.items(),
                        key=lambda x: (
                            x[1]['issues_created'] + 
                            x[1]['prs_created'] + 
                            x[1]['issue_comments'] + 
                            x[1]['pr_comments'] +
                            x[1]['commits']
                        ),
                        reverse=True
                    )
                }
            },
            'milestones': {
                'total': len(self.milestones),
                'list': sorted(list(self.milestones)),
            },
            'migration_estimates': {
                'placeholder_issues_needed': issue_gap_count,
                'total_api_calls_estimate': (
                    len(self.issues) * 3 +  # Create issue, comments, close if needed
                    len(self.pull_requests) * 2 +  # Create PR, comments
                    issue_gap_count +  # Placeholder issues
                    len(self.attachments)  # Attachment uploads
                ),
                'estimated_time_minutes': round(
                    (len(self.issues) + len(self.pull_requests) + issue_gap_count) * 0.5,  # ~0.5 min per item
                    1
                ),
            },
            'pr_migration_analysis': pr_migration_analysis
        }
        
        return report
    
    def print_report(self, report: dict):
        """Print human-readable report"""
        print("\n" + "="*80)
        print(f"BITBUCKET MIGRATION AUDIT REPORT")
        print(f"Repository: {report['repository']['workspace']}/{report['repository']['repo']}")
        print(f"Audit Date: {report['repository']['audit_date']}")
        print("="*80)
        
        print("\n📋 ISSUES")
        print(f"  Total Issues: {report['issues']['total']}")
        print(f"  States: {report['issues']['by_state']}")
        print(f"  Number Range: #{report['issues']['number_range']['min']} - #{report['issues']['number_range']['max']}")
        print(f"  Number Gaps: {report['issues']['gaps']['count']} missing issue numbers")
        if report['issues']['gaps']['numbers']:
            print(f"    First gaps: {report['issues']['gaps']['numbers'][:10]}")
        print(f"  Total Comments: {report['issues']['total_comments']}")
        print(f"  Issues with Attachments: {report['issues']['with_attachments']}")
        
        print("\n🔀 PULL REQUESTS")
        print(f"  Total PRs: {report['pull_requests']['total']}")
        print(f"  States: {report['pull_requests']['by_state']}")
        print(f"  Number Range: #{report['pull_requests']['number_range']['min']} - #{report['pull_requests']['number_range']['max']}")
        print(f"  Number Gaps: {report['pull_requests']['gaps']['count']} missing PR numbers")
        print(f"  Total Comments: {report['pull_requests']['total_comments']}")
        
        print("\n📎 ATTACHMENTS")
        print(f"  Total Files: {report['attachments']['total']}")
        print(f"  Total Size: {report['attachments']['total_size_mb']} MB")
        
        print("\n👥 USERS")
        print(f"  Unique Users: {report['users']['total_unique']}")
        
        print("\n  User Activity Breakdown:")
        print(f"  {'User':<30} {'Issues':<8} {'PRs':<6} {'Commits':<9} {'Comments':<10} {'Reviews':<8} {'Total':<8}")
        print(f"  {'-'*30} {'-'*8} {'-'*6} {'-'*9} {'-'*10} {'-'*8} {'-'*8}")
        
        for user, stats in list(report['users']['activity_breakdown'].items())[:20]:
            issue_count = stats['issues_created']
            pr_count = stats['prs_created']
            commit_count = stats['commits']
            comment_count = stats['issue_comments'] + stats['pr_comments']
            review_count = stats['pr_reviews']
            total = stats['total_activity']
            
            print(f"  {user:<30} {issue_count:<8} {pr_count:<6} {commit_count:<9} {comment_count:<10} {review_count:<8} {total:<8}")
        
        if report['users']['total_unique'] > 20:
            print(f"  ... and {report['users']['total_unique'] - 20} more users")
        
        print("\n🏷️  MILESTONES")
        print(f"  Total: {report['milestones']['total']}")
        if report['milestones']['list']:
            print(f"  List: {', '.join(report['milestones']['list'])}")
        
        print("\n📊 MIGRATION ESTIMATES")
        print(f"  Placeholder Issues Needed: {report['migration_estimates']['placeholder_issues_needed']}")
        print(f"  Estimated API Calls: ~{report['migration_estimates']['total_api_calls_estimate']}")
        print(f"  Estimated Time: ~{report['migration_estimates']['estimated_time_minutes']} minutes")
        
        print("\n🔀 PULL REQUEST MIGRATION ANALYSIS")
        pr_analysis = report['pr_migration_analysis']
        print(f"  Fully Migratable PRs: {pr_analysis['fully_migratable']['count']}")
        print(f"    (Open PRs with branches intact - can be migrated as actual PRs)")
        print(f"  Partially Migratable PRs: {pr_analysis['partially_migratable']['count']}")
        print(f"    (Merged/Closed PRs - best migrated as issues with PR metadata)")
        
        if pr_analysis['migration_challenges']['count'] > 0:
            print(f"  PRs with Migration Challenges: {pr_analysis['migration_challenges']['count']}")
            print(f"    (May have missing branches or other issues)")
        
        print("\n  Migration Strategy Recommendations:")
        print(f"    1. Migrate {pr_analysis['fully_migratable']['count']} open PRs as actual GitHub PRs")
        print(f"    2. Migrate {pr_analysis['partially_migratable']['count']} closed PRs as GitHub issues")
        print(f"       (Include original PR metadata, state, and links in description)")
        print(f"    3. All PR comments, commits, and history will be preserved in descriptions")
        
        print("\n" + "="*80)
        print("Report saved to: bitbucket_audit_report.json")
        print("="*80 + "\n")
    
    def save_detailed_data(self):
        """Save detailed issue and PR data for reference"""
        with open('bitbucket_issues_detail.json', 'w') as f:
            json.dump(self.issues, f, indent=2, default=str)
        
        with open('bitbucket_prs_detail.json', 'w') as f:
            json.dump(self.pull_requests, f, indent=2, default=str)
        
        print("Detailed data saved to:")
        print("  - bitbucket_issues_detail.json")
        print("  - bitbucket_prs_detail.json")
    
    def generate_migration_config(self, gh_owner: str = "", gh_repo: str = "") -> dict:
        """Generate a migration configuration template"""
        # Use provided values or defaults
        if not gh_owner:
            gh_owner = "YOUR_GITHUB_USERNAME"
        if not gh_repo:
            gh_repo = self.repo
        
        # Create user mapping template
        user_mapping = {}
        for user in sorted(self.users):
            # Add comment hints for common cases
            if user.lower() == 'unknown':
                user_mapping[user] = None
            else:
                user_mapping[user] = ""  # Empty string to be filled in
        
        config = {
            "_comment": "Bitbucket to GitHub Migration Configuration",
            "_instructions": {
                "step_1": "Fill in your GitHub personal access token (needs 'repo' scope)",
                "step_2": "Set github.owner to your GitHub username or organization",
                "step_3": "Set github.repo to your target repository name",
                "step_4": "For each user in user_mapping - set to their GitHub username if they have an account, or set to null/empty if they don't",
                "step_5": "Bitbucket credentials are pre-filled from audit",
                "step_6": "Run with dry-run first - python migrate_bitbucket_to_github.py --config migration_config.json --dry-run",
                "step_7": "After dry-run succeeds, remove --dry-run to perform actual migration"
            },
            "bitbucket": {
                "workspace": self.workspace,
                "repo": self.repo,
                "email": self.email,
                "token": self.api_token
            },
            "github": {
                "owner": gh_owner,
                "repo": gh_repo,
                "token": "YOUR_GITHUB_TOKEN_HERE"
            },
            "user_mapping": user_mapping
        }
        
        return config
    
    def save_migration_config(self, filename: str = 'migration_config.json', 
                             gh_owner: str = "", gh_repo: str = ""):
        """Save migration configuration template to file"""
        config = self.generate_migration_config(gh_owner, gh_repo)
        
        with open(filename, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n{'='*80}")
        print(f"Migration configuration template saved to: {filename}")
        print(f"{'='*80}")
        print("\nNext steps:")
        print("1. Edit migration_config.json:")
        print("   - Add your GitHub token")
        print("   - Set github.owner to your GitHub username")
        print("   - Map Bitbucket users to GitHub usernames")
        print("     (use null for users without GitHub accounts)")
        print("\n2. Test with dry run:")
        print(f"   python migrate_bitbucket_to_github.py --config {filename} --dry-run")
        print("\n3. Run actual migration:")
        print(f"   python migrate_bitbucket_to_github.py --config {filename}")
        print(f"{'='*80}\n")
        
        # Also create a user mapping template file for easier editing
        user_template_file = 'user_mapping_template.txt'
        with open(user_template_file, 'w') as f:
            f.write("# User Mapping Template\n")
            f.write("# Copy these mappings to migration_config.json\n")
            f.write("# Format: \"Bitbucket Display Name\": \"github-username\"\n")
            f.write("# Use null for users without GitHub accounts\n\n")
            
            for user in sorted(self.users):
                activity = self.user_stats.get(user, {})
                total = (activity.get('issues_created', 0) + 
                        activity.get('prs_created', 0) + 
                        activity.get('commits', 0) +
                        activity.get('issue_comments', 0) +
                        activity.get('pr_comments', 0))
                
                f.write(f"# {user} - {total} total activities\n")
                f.write(f'"{user}": "",\n\n')
        
        print(f"User mapping template also saved to: {user_template_file}")
        print("This file shows all users with their activity counts for reference.\n")
    
    def generate_markdown_report(self, report: dict) -> str:
        """Generate a detailed Markdown report"""
        md = []
        
        md.append("# Bitbucket to GitHub Migration Audit Report\n")
        md.append(f"**Repository:** {report['repository']['workspace']}/{report['repository']['repo']}\n")
        md.append(f"**Audit Date:** {report['repository']['audit_date']}\n")
        md.append("---\n\n")
        
        # Executive Summary
        md.append("## Executive Summary\n\n")
        md.append(f"- **Total Issues:** {report['issues']['total']}\n")
        md.append(f"- **Total Pull Requests:** {report['pull_requests']['total']}\n")
        md.append(f"- **Unique Users:** {report['users']['total_unique']}\n")
        md.append(f"- **Total Attachments:** {report['attachments']['total']} ({report['attachments']['total_size_mb']} MB)\n")
        md.append(f"- **Estimated Migration Time:** ~{report['migration_estimates']['estimated_time_minutes']} minutes\n\n")
        
        # Issues Section
        md.append("## Issues\n\n")
        md.append(f"- **Total Issues:** {report['issues']['total']}\n")
        md.append(f"- **States:** {report['issues']['by_state']}\n")
        md.append(f"- **Number Range:** #{report['issues']['number_range']['min']} to #{report['issues']['number_range']['max']}\n")
        md.append(f"- **Missing Numbers (gaps):** {report['issues']['gaps']['count']}\n")
        if report['issues']['gaps']['numbers']:
            md.append(f"  - First gaps: {report['issues']['gaps']['numbers'][:20]}\n")
        md.append(f"- **Total Comments:** {report['issues']['total_comments']}\n")
        md.append(f"- **Issues with Attachments:** {report['issues']['with_attachments']}\n\n")
        
        # Pull Requests Section
        md.append("## Pull Requests\n\n")
        md.append(f"- **Total PRs:** {report['pull_requests']['total']}\n")
        md.append(f"- **States:** {report['pull_requests']['by_state']}\n")
        md.append(f"- **Number Range:** #{report['pull_requests']['number_range']['min']} to #{report['pull_requests']['number_range']['max']}\n")
        md.append(f"- **Missing Numbers (gaps):** {report['pull_requests']['gaps']['count']}\n")
        md.append(f"- **Total Comments:** {report['pull_requests']['total_comments']}\n\n")
        
        # PR Migration Analysis
        md.append("### Pull Request Migration Strategy\n\n")
        pr_analysis = report['pr_migration_analysis']
        md.append(f"- **Fully Migratable (as PRs):** {pr_analysis['fully_migratable']['count']}\n")
        md.append(f"  - These are OPEN PRs with intact branches\n")
        md.append(f"- **Partially Migratable (as Issues):** {pr_analysis['partially_migratable']['count']}\n")
        md.append(f"  - These are MERGED/CLOSED/DECLINED PRs (branches likely deleted)\n")
        if pr_analysis['migration_challenges']['count'] > 0:
            md.append(f"- **Migration Challenges:** {pr_analysis['migration_challenges']['count']}\n\n")
        else:
            md.append("\n")
        
        # User Activity
        md.append("## User Activity Breakdown\n\n")
        md.append("| User | Issues | PRs | Commits | Comments | Reviews | Total |\n")
        md.append("|------|--------|-----|---------|----------|---------|-------|\n")
        
        for user, stats in list(report['users']['activity_breakdown'].items())[:30]:
            issue_count = stats['issues_created']
            pr_count = stats['prs_created']
            commit_count = stats['commits']
            comment_count = stats['issue_comments'] + stats['pr_comments']
            review_count = stats['pr_reviews']
            total = stats['total_activity']
            
            md.append(f"| {user} | {issue_count} | {pr_count} | {commit_count} | {comment_count} | {review_count} | {total} |\n")
        
        if report['users']['total_unique'] > 30:
            md.append(f"\n*... and {report['users']['total_unique'] - 30} more users*\n")
        
        md.append("\n")
        
        # Migration Estimates
        md.append("## Migration Estimates\n\n")
        md.append(f"- **Placeholder Issues Needed:** {report['migration_estimates']['placeholder_issues_needed']}\n")
        md.append(f"- **Estimated API Calls:** ~{report['migration_estimates']['total_api_calls_estimate']}\n")
        md.append(f"- **Estimated Time:** ~{report['migration_estimates']['estimated_time_minutes']} minutes\n\n")
        
        # Attachments
        md.append("## Attachments\n\n")
        md.append(f"- **Total Files:** {report['attachments']['total']}\n")
        md.append(f"- **Total Size:** {report['attachments']['total_size_mb']} MB\n\n")
        
        # Next Steps
        md.append("## Next Steps\n\n")
        md.append("### 1. Generate Migration Configuration\n\n")
        md.append("```bash\n")
        md.append(f"python audit_bitbucket.py \\\n")
        md.append(f"  --workspace {report['repository']['workspace']} \\\n")
        md.append(f"  --repo {report['repository']['repo']} \\\n")
        md.append(f"  --email YOUR_EMAIL \\\n")
        md.append(f"  --generate-config \\\n")
        md.append(f"  --gh-owner YOUR_GITHUB_USERNAME \\\n")
        md.append(f"  --gh-repo {report['repository']['repo']}\n")
        md.append("```\n\n")
        
        md.append("### 2. Edit Configuration\n\n")
        md.append("Edit `migration_config.json`:\n")
        md.append("- Add your GitHub personal access token\n")
        md.append("- Map Bitbucket users to GitHub usernames\n")
        md.append("- Set users without GitHub accounts to `null`\n\n")
        
        md.append("### 3. Push Git History\n\n")
        md.append("```bash\n")
        md.append(f"git clone --mirror https://bitbucket.org/{report['repository']['workspace']}/{report['repository']['repo']}.git\n")
        md.append(f"cd {report['repository']['repo']}.git\n")
        md.append("git remote add github https://github.com/YOUR_USERNAME/YOUR_REPO.git\n")
        md.append("git push --mirror github\n")
        md.append("```\n\n")
        
        md.append("### 4. Test Migration (Dry Run)\n\n")
        md.append("```bash\n")
        md.append("python migrate_bitbucket_to_github.py --config migration_config.json --dry-run\n")
        md.append("```\n\n")
        
        md.append("### 5. Run Actual Migration\n\n")
        md.append("```bash\n")
        md.append("python migrate_bitbucket_to_github.py --config migration_config.json\n")
        md.append("```\n\n")
        
        md.append("---\n\n")
        md.append("*For detailed migration strategy and limitations, see MIGRATION_GUIDE.md*\n")
        
        return ''.join(md)
    
    def save_markdown_report(self, report: dict, filename: str = 'audit_report.md'):
        """Save the audit report as Markdown"""
        md_content = self.generate_markdown_report(report)
        
        with open(filename, 'w') as f:
            f.write(md_content)
        
        print(f"Markdown audit report saved to: {filename}")


def main():
    parser = argparse.ArgumentParser(
        description='Audit Bitbucket repository for GitHub migration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python audit_bitbucket.py --workspace myteam --repo myproject --email user@example.com
  
  # API token will be prompted if not provided
  python audit_bitbucket.py --workspace myteam --repo myproject --email user@example.com --token API_TOKEN
  
  # Generate migration config with GitHub info
  python audit_bitbucket.py --workspace myteam --repo myproject --email user@example.com \\
      --generate-config --gh-owner myusername --gh-repo myrepo
  
Creating a user-level API Token:
  1. Go to: Settings > Atlassian account settings > Security
  2. Click "Create and manage API tokens"
  3. Click "Create API token with scopes"
  4. Name it (e.g., "Migration Audit")
  5. Set expiry date
  6. Select "Bitbucket" as the app
  7. Select permissions (or "Full access" for simplicity)
  8. Click "Create" and copy the token
  
Note: 
  - Use your Atlassian account email (from Bitbucket > Personal settings > Email aliases)
  - User-level API tokens replace App Passwords (deprecated Sept 2025)
  - Repository Access Tokens do NOT support issue APIs
        """
    )
    
    parser.add_argument('--workspace', required=True, help='Bitbucket workspace name')
    parser.add_argument('--repo', required=True, help='Repository name')
    parser.add_argument('--email', required=True, help='Atlassian account email')
    parser.add_argument('--token', help='Bitbucket API token (will prompt if not provided)')
    parser.add_argument('--generate-config', action='store_true', 
                       help='Generate migration configuration file')
    parser.add_argument('--gh-owner', help='GitHub username/org for migration config')
    parser.add_argument('--gh-repo', help='GitHub repository name for migration config')
    
    args = parser.parse_args()
    
    # Get API token if not provided
    api_token = args.token
    if not api_token:
        import getpass
        api_token = getpass.getpass('Bitbucket API token: ')
    
    # Run audit
    auditor = BitbucketAuditor(args.workspace, args.repo, args.email, api_token)
    
    try:
        auditor.audit_issues()
        auditor.audit_pull_requests()
        
        report = auditor.generate_report()
        
        # Save report
        with open('bitbucket_audit_report.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Print summary
        auditor.print_report(report)
        
        # Save detailed data
        auditor.save_detailed_data()
        
        # Save markdown report
        auditor.save_markdown_report(report)
        
        # Generate migration config if requested
        if args.generate_config:
            gh_owner = args.gh_owner or ""
            gh_repo = args.gh_repo or args.repo
            auditor.save_migration_config('migration_config.json', gh_owner, gh_repo)
        
    except KeyboardInterrupt:
        print("\nAudit interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError during audit: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()