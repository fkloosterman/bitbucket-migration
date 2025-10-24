#!/usr/bin/env python3
"""
Bitbucket to GitHub Migration Audit Script

⚠️  DEPRECATED: This script is deprecated. Use the following command instead:
   python migrate_bitbucket_to_github.py audit --workspace WORKSPACE --repo REPO --email EMAIL

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
import getpass

# Import migration modules
from bitbucket_migration.exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    ValidationError
)

# Import audit orchestrator
from bitbucket_migration.audit.audit_orchestrator import AuditOrchestrator




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
        api_token = getpass.getpass('Bitbucket API token: ')
    
    # Run audit using new orchestrator
    try:
        auditor = AuditOrchestrator(args.workspace, args.repo, args.email, api_token)
        report = auditor.run_audit()

        # Save reports
        auditor.save_reports(report)

        # Generate migration config if requested
        if args.generate_config:
            gh_owner = args.gh_owner or ""
            gh_repo = args.gh_repo or args.repo
            config = auditor.generate_migration_config(gh_owner, gh_repo)
            auditor.save_migration_config(config, 'migration_config.json')

    except KeyboardInterrupt:
        print("\nAudit interrupted by user")
        sys.exit(1)
    except (APIError, AuthenticationError, NetworkError, ValidationError) as e:
        print(f"\nError during audit: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error during audit: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()