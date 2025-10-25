#!/usr/bin/env python3
"""
Bitbucket to GitHub Migration Toolkit

Comprehensive migration toolkit for transferring Bitbucket repositories to GitHub while
preserving metadata, comments, attachments, and cross-references between issues and pull requests.

.. warning::
   This tool was developed with AI assistance. Use at your own risk.
   Always perform dry runs and verify results before production use.

Architecture
------------
The tool uses a modular architecture with separate components:
- MigrationOrchestrator: Coordinates the overall migration process
- AuditOrchestrator: Handles pre-migration analysis and planning
- IssueMigrator: Handles issue migration with attachments and comments
- PullRequestMigrator: Handles PR migration with branch checking
- ReportGenerator: Generates comprehensive migration reports
- SecureConfigLoader: Loads configuration with security enhancements

Subcommands
-----------
audit     Audit repository for migration planning and generate configuration
migrate   Run full migration (requires configuration file)
dry-run   Simulate migration without making changes to GitHub
test-auth Test Bitbucket and GitHub API authentication

Migration Strategy
------------------
Issues: All Bitbucket issues become GitHub issues, preserving original numbering with placeholders
Pull Requests:
    - OPEN PRs with existing branches → GitHub PRs (remain open)
    - OPEN PRs with missing branches → GitHub Issues
    - MERGED/DECLINED/SUPERSEDED PRs → GitHub Issues (safest approach)

Security Features
-----------------
- Tokens can be loaded from environment variables (BITBUCKET_TOKEN, GITHUB_TOKEN)
- Token format validation for added security
- Structured logging with file rotation
- Secure configuration loading with validation

Prerequisites
-------------
1. Create empty GitHub repository
2. Push git history: git push --mirror <github-url>
3. Generate Bitbucket API token with repository read access
4. Generate GitHub personal access token with repository write access
5. Run audit to understand migration scope and generate configuration

Examples
--------
# Audit repository before migration (recommended first step)
python migrate_bitbucket_to_github.py audit --workspace myteam --repo myproject --email user@example.com

# Test authentication before migration
python migrate_bitbucket_to_github.py test-auth --workspace myteam --repo myproject \\
    --email user@example.com --gh-owner myuser --gh-repo myproject

# Dry run to validate configuration
python migrate_bitbucket_to_github.py dry-run --config config.json

# Full migration
python migrate_bitbucket_to_github.py migrate --config config.json
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
from dotenv import load_dotenv

# Import custom exceptions
from bitbucket_migration.exceptions import (
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
from bitbucket_migration.config.migration_config import (
    MigrationConfig,
    ConfigLoader,
    BitbucketConfig,
    GitHubConfig
)
from bitbucket_migration.config.secure_config import SecureConfigLoader

# Import API clients
from bitbucket_migration.clients.bitbucket_client import BitbucketClient
from bitbucket_migration.clients.github_client import GitHubClient
from bitbucket_migration.clients.github_cli_client import GitHubCliClient

# Import services
from bitbucket_migration.services.user_mapper import UserMapper
from bitbucket_migration.services.link_rewriter import LinkRewriter
from bitbucket_migration.services.attachment_handler import AttachmentHandler

# Import formatters
from bitbucket_migration.formatters import FormatterFactory

# Import logging
from bitbucket_migration.utils.logging_config import setup_logger, MigrationLogger

# Import new migration components
from bitbucket_migration.core.orchestrator import MigrationOrchestrator
from bitbucket_migration.migration.issue_migrator import IssueMigrator
from bitbucket_migration.migration.pr_migrator import PullRequestMigrator
from bitbucket_migration.migration.report_generator import ReportGenerator

# Import audit components
from bitbucket_migration.audit.audit_orchestrator import AuditOrchestrator


def create_main_parser():
    """Create and configure the main argument parser with subcommands.

    Sets up the command-line interface with comprehensive help text, subcommands
    for audit, migrate, dry-run, and test-auth operations, along with all
    required and optional arguments for each subcommand.

    Returns
    -------
    argparse.ArgumentParser
        Configured argument parser with all subcommands and options.

    Notes
    -----
    The parser includes detailed help text and examples in the epilog.
    All subcommands support interactive prompting for missing required arguments.
    """
    parser = argparse.ArgumentParser(
        description='Bitbucket to GitHub Migration Tools',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Bitbucket to GitHub Migration Toolkit

This tool provides comprehensive migration capabilities from Bitbucket to GitHub,
including audit, dry-run, full migration, and authentication testing functionality.

SUBCOMMANDS:
   audit     Audit repository for migration planning
   migrate   Run full migration (requires config file)
   dry-run   Simulate migration without making changes
   test-auth Test Bitbucket and GitHub API authentication (includes GitHub CLI check)
   clean     Remove output files generated by other subcommands

EXAMPLES:
  # Audit repository before migration
  python migrate_bitbucket_to_github.py audit --workspace myteam --repo myproject --email user@example.com

  # Generate migration config from audit (default behavior)
  python migrate_bitbucket_to_github.py audit --workspace myteam --repo myproject --email user@example.com

  # Skip config generation
  python migrate_bitbucket_to_github.py audit --workspace myteam --repo myproject --email user@example.com --no-config

  # Test authentication before migration (includes GitHub CLI check)
  python migrate_bitbucket_to_github.py test-auth --workspace myteam --repo myproject --email user@example.com --gh-owner myuser --gh-repo myproject

  # Dry run to validate configuration
  python migrate_bitbucket_to_github.py dry-run --config config.json

  # Full migration
  python migrate_bitbucket_to_github.py migrate --config config.json

  # Clean output files (keeps config)
  python migrate_bitbucket_to_github.py clean

  # Clean all files including config
  python migrate_bitbucket_to_github.py clean --all

CONFIGURATION:
For migration and dry-run commands, provide a configuration file with:
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
    "Bitbucket User": "github-username"
  }
}

SECURITY: Tokens can be loaded from environment variables (BITBUCKET_TOKEN, GITHUB_TOKEN)
to avoid storing sensitive data in configuration files.
        """
    )

    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Audit subcommand
    audit_parser = subparsers.add_parser('audit', help='Audit repository for migration planning')
    audit_parser.add_argument('--workspace', help='Bitbucket workspace name')
    audit_parser.add_argument('--repo', help='Repository name')
    audit_parser.add_argument('--email', help='Bitbucket email')
    audit_parser.add_argument('--token', help='Bitbucket API token')
    audit_parser.add_argument('--no-config', action='store_true', help='Do not generate migration configuration file')
    audit_parser.add_argument('--gh-owner', help='GitHub owner for config template')
    audit_parser.add_argument('--gh-repo', help='GitHub repository name for config template')

    # Migration subcommand
    migrate_parser = subparsers.add_parser('migrate', help='Run full migration')
    migrate_parser.add_argument('--config', required=True, help='Path to configuration JSON file')
    migrate_parser.add_argument('--skip-issues', type=str, nargs='?', const='true', default=argparse.SUPPRESS,
                               help='Skip issue migration (true/false, default from config)')
    migrate_parser.add_argument('--skip-prs', type=str, nargs='?', const='true', default=argparse.SUPPRESS,
                               help='Skip PR migration (true/false, default from config)')
    migrate_parser.add_argument('--skip-pr-as-issue', type=str, nargs='?', const='true', default=argparse.SUPPRESS,
                               help='Skip migrating closed/merged PRs as issues (true/false, default from config)')
    migrate_parser.add_argument('--use-gh-cli', type=str, nargs='?', const='true', default=argparse.SUPPRESS,
                               help='Use GitHub CLI to automatically upload attachments (true/false, default from config)')

    # Dry-run subcommand
    dry_run_parser = subparsers.add_parser('dry-run', help='Simulate migration without making changes')
    dry_run_parser.add_argument('--config', required=True, help='Path to configuration JSON file')
    dry_run_parser.add_argument('--skip-issues', type=str, nargs='?', const='true', default=argparse.SUPPRESS,
                                help='Skip issue migration (true/false, default from config)')
    dry_run_parser.add_argument('--skip-prs', type=str, nargs='?', const='true', default=argparse.SUPPRESS,
                                help='Skip PR migration (true/false, default from config)')
    dry_run_parser.add_argument('--skip-pr-as-issue', type=str, nargs='?', const='true', default=argparse.SUPPRESS,
                                help='Skip migrating closed/merged PRs as issues (true/false, default from config)')
    dry_run_parser.add_argument('--use-gh-cli', type=str, nargs='?', const='true', default=argparse.SUPPRESS,
                                help='Use GitHub CLI to automatically upload attachments (true/false, default from config)')

    # Test-auth subcommand
    test_auth_parser = subparsers.add_parser('test-auth', help='Test Bitbucket and GitHub API authentication')
    test_auth_parser.add_argument('--workspace', help='Bitbucket workspace name')
    test_auth_parser.add_argument('--repo', help='Repository name')
    test_auth_parser.add_argument('--email', help='Bitbucket email')
    test_auth_parser.add_argument('--token', help='Bitbucket API token')
    test_auth_parser.add_argument('--gh-owner', help='GitHub owner')
    test_auth_parser.add_argument('--gh-repo', help='GitHub repository name')
    test_auth_parser.add_argument('--gh-token', help='GitHub API token')

    # Clean subcommand
    clean_parser = subparsers.add_parser('clean', help='Remove output files generated by audit, dry-run, and migrate subcommands')
    clean_parser.add_argument('--all', action='store_true', help='Remove all outputs including the config file')

    return parser


def prompt_for_missing_args(args, required_fields, parser=None):
    """Prompt user for missing required command-line arguments.

    Interactively prompts the user to input missing required arguments, with special
    handling for sensitive fields like API tokens using getpass for secure input.
    Attempts to provide helpful prompts by extracting help text from the argument parser.
    Checks environment variables and .env file for tokens before prompting.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command-line arguments object to be updated.
    required_fields : list of str
        List of field names that need to be prompted if missing.
    parser : argparse.ArgumentParser, optional
        The argument parser instance for extracting help text, by default None.

    Returns
    -------
    argparse.Namespace
        Updated args object with user-provided values for missing fields.

    Side Effects
    ------------
    - Prompts user for input via stdin
    - Uses getpass for secure token input
    - Modifies the input args object in-place

    Examples
    --------
    >>> args = argparse.Namespace(workspace='myteam', repo='myproject')
    >>> required = ['workspace', 'repo', 'email', 'token']
    >>> updated_args = prompt_for_missing_args(args, required)
    >>> print(updated_args.email)
    user@example.com
    """
    import getpass

    # Load environment variables from .env file if it exists
    load_dotenv()

    for field in required_fields:
        value = getattr(args, field, None)
        if not value or (isinstance(value, str) and not value.strip()):
            # Check environment variables for tokens before prompting
            if field == 'token':
                # Check for Bitbucket token in environment
                env_token = os.getenv('BITBUCKET_TOKEN') or os.getenv('BITBUCKET_API_TOKEN')
                if env_token:
                    setattr(args, field, env_token)
                    continue
            elif field == 'gh_token':
                # Check for GitHub token in environment
                env_token = os.getenv('GITHUB_TOKEN') or os.getenv('GITHUB_API_TOKEN')
                if env_token:
                    setattr(args, field, env_token)
                    continue

            # If not found in env vars, prompt the user
            if field in ['token', 'gh_token']:
                prompt_text = 'GitHub API token: ' if field == 'gh_token' else 'Bitbucket API token: '
                setattr(args, field, getpass.getpass(prompt_text))
            else:
                # Try to get help text from parser if available
                prompt_text = f'{field.capitalize()}: '
                if parser and hasattr(args, 'command'):
                    # Find the subparsers action and get the correct subparser
                    for action in parser._actions:
                        if hasattr(action, 'choices') and hasattr(action.choices, 'get') and args.command in action.choices:
                            subparser = action.choices[args.command]
                            # Search in the subparser actions
                            for subaction in subparser._actions:
                                if hasattr(subaction, 'dest') and subaction.dest == field and subaction.help:
                                    prompt_text = f'{subaction.help}: '
                                    break
                            break
                setattr(args, field, input(prompt_text))

    return args


def run_audit(args, parser=None):
    """Run comprehensive audit of Bitbucket repository for migration planning.

    Performs a complete analysis of the Bitbucket repository including issues, pull
    requests, branches, and user mappings. Generates detailed reports and optionally
    creates a migration configuration file. Prompts for any missing required arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments containing workspace, repo, email, token, and optional
        flags like no_config, gh_owner, gh_repo.
    parser : argparse.ArgumentParser, optional
        The argument parser instance for extracting help text during prompting.

    Side Effects
    ------------
    - Prompts user for missing arguments interactively
    - Creates BitbucketClient and AuditOrchestrator instances
    - Makes API calls to Bitbucket
    - Generates and saves audit reports (bitbucket_audit_report.json, audit_report.md)
    - Optionally generates migration configuration file (migration_config.json)

    Raises
    ------
    APIError
        If Bitbucket API calls fail.
    AuthenticationError
        If Bitbucket authentication fails.
    NetworkError
        If network connectivity issues occur.
    ValidationError
        If provided arguments are invalid.
    KeyboardInterrupt
        If user interrupts the audit process.

    Examples
    --------
    >>> args = argparse.Namespace(workspace='myteam', repo='myproject')
    >>> run_audit(args)
    # Prompts for email and token, then runs audit
    """
    # Prompt for missing arguments
    required_fields = ['workspace', 'repo', 'email', 'token']
    args = prompt_for_missing_args(args, required_fields, parser)

    try:
        # Prompt for gh_owner and gh_repo BEFORE audit if config is being generated and not provided
        if not getattr(args, 'no_config', False):
            if not args.gh_owner:
                args.gh_owner = input('GitHub owner: ')
            if not args.gh_repo:
                prompt = f'GitHub repository name (default: {args.repo}): '
                args.gh_repo = input(prompt).strip() or args.repo

        # Create audit orchestrator
        auditor = AuditOrchestrator(args.workspace, args.repo, args.email, args.token)
        report = auditor.run_audit()

        # Save reports
        auditor.save_reports(report)

        # Generate migration config if not disabled
        if not getattr(args, 'no_config', False):
            gh_owner = args.gh_owner
            gh_repo = args.gh_repo
            config = auditor.generate_migration_config(gh_owner, gh_repo)
            auditor.save_migration_config(config, 'migration_config.json')

        print("\n✅ Audit completed successfully!")
        print("📄 Reports saved: bitbucket_audit_report.json, bitbucket_audit_report.md")
        if not getattr(args, 'no_config', False):
            print("📋 Migration config generated: migration_config.json")

    except KeyboardInterrupt:
        print("\nAudit interrupted by user")
        sys.exit(1)
    except (APIError, AuthenticationError, NetworkError, ValidationError) as e:
        print(f"\n❌ Error during audit: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error during audit: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _check_gh_cli_available(gh_token: str) -> Dict[str, Any]:
    """Check if GitHub CLI is available and authenticated.

    Verifies the installation and authentication status of the GitHub CLI tool,
    which is required for automatic attachment uploads during migration.

    Parameters
    ----------
    gh_token : str
        GitHub personal access token for authentication checks.

    Returns
    -------
    dict
        Dictionary containing check results with the following keys:
        - 'available' (bool): Whether GitHub CLI is installed
        - 'authenticated' (bool): Whether GitHub CLI is authenticated
        - 'details' (str): Human-readable description of the status
        - 'version' (str): GitHub CLI version if available, empty string otherwise

    Notes
    -----
    This is a private helper function used by authentication testing.
    Uses GitHubCliClient for checks.
    """
    result = {
        'available': False,
        'authenticated': False,
        'details': '',
        'version': ''
    }

    try:
        # Create CLI client for checks
        cli_client = GitHubCliClient(gh_token)

        if cli_client.is_available():
            result['available'] = True
            result['version'] = cli_client.get_version() or 'unknown'
            result['details'] = f"GitHub CLI {result['version']} is installed"

            if cli_client.is_authenticated():
                result['authenticated'] = True
                result['details'] += " and authenticated"
            else:
                result['details'] += " but not authenticated"
        else:
            result['details'] = "GitHub CLI not installed"

    except Exception as e:
        result['details'] = f"Error checking GitHub CLI: {e}"

    return result


def _authenticate_gh_cli(token: str) -> Dict[str, Any]:
    """Authenticate GitHub CLI using the provided personal access token.

    Attempts to authenticate the GitHub CLI tool using the provided token.
    This enables automatic attachment uploads during the migration process.

    Parameters
    ----------
    token : str
        GitHub personal access token with repository permissions.

    Returns
    -------
    dict
        Dictionary containing authentication results with keys:
        - 'success' (bool): Whether authentication was successful
        - 'error' (str): Error message if authentication failed, empty if successful

    Notes
    -----
    This is a private helper function used by authentication testing.
    Uses GitHubCliClient for authentication.
    """
    result = {
        'success': False,
        'error': ''
    }

    try:
        # Create CLI client and attempt authentication
        cli_client = GitHubCliClient(token)
        if cli_client.authenticate():
            result['success'] = True
        else:
            result['error'] = "Authentication failed"

    except Exception as e:
        result['error'] = f"Authentication error: {e}"

    return result


def run_test_auth(args, parser=None):
    """Test authentication for both Bitbucket and GitHub APIs plus GitHub CLI.

    Performs comprehensive authentication testing for all services required during
    migration: Bitbucket API, GitHub API, and GitHub CLI. Provides detailed feedback
    and troubleshooting guidance for any failures. Prompts for missing arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments containing all required authentication parameters:
        workspace, repo, email, token, gh_owner, gh_repo, gh_token.
    parser : argparse.ArgumentParser, optional
        The argument parser instance for extracting help text during prompting.

    Side Effects
    ------------
    - Prompts user for missing authentication parameters
    - Makes API calls to Bitbucket and GitHub
    - Checks and potentially modifies GitHub CLI authentication state
    - Prints detailed status and troubleshooting information to stdout
    - May exit the program with error code 1 if authentication fails

    Raises
    ------
    SystemExit
        Exits with code 1 if any authentication tests fail.

    Examples
    --------
    >>> args = argparse.Namespace(workspace='myteam', repo='myproject')
    >>> run_test_auth(args)
    # Prompts for all missing auth parameters, then tests connections
    """
    # Prompt for missing arguments
    required_fields = ['workspace', 'repo', 'email', 'token', 'gh_owner', 'gh_repo', 'gh_token']
    args = prompt_for_missing_args(args, required_fields, parser)

    # Track test results
    results = {
        'bitbucket': {'success': False, 'error': None, 'details': ''},
        'github': {'success': False, 'error': None, 'details': ''},
        'gh_cli': {'available': False, 'authenticated': False, 'error': None, 'details': ''}
    }

    print("🔍 Testing API connections...")
    print("=" * 50)

    # Test Bitbucket connection
    try:
        print("Testing Bitbucket API...")
        bb_client = BitbucketClient(args.workspace, args.repo, args.email, args.token)
        if bb_client.test_connection(detailed=True):
            results['bitbucket']['success'] = True
            print("✅ Bitbucket authentication successful")
        else:
            results['bitbucket']['success'] = False
            results['bitbucket']['details'] = "Connection test returned False"
            print("❌ Bitbucket authentication failed")
    except ValidationError as e:
        results['bitbucket']['error'] = 'validation'
        results['bitbucket']['details'] = str(e)
        print(f"❌ Bitbucket validation error: {e}")
    except AuthenticationError as e:
        results['bitbucket']['error'] = 'auth'
        results['bitbucket']['details'] = str(e)
        print(f"❌ Bitbucket authentication failed: {e}")
    except APIError as e:
        results['bitbucket']['error'] = 'api'
        results['bitbucket']['details'] = str(e)
        if "404" in str(e):
            print(f"❌ Bitbucket API error (404): Repository not found or no access")
            print(f"   Please verify: https://bitbucket.org/{args.workspace}/{args.repo}")
        else:
            print(f"❌ Bitbucket API error: {e}")
    except NetworkError as e:
        results['bitbucket']['error'] = 'network'
        results['bitbucket']['details'] = str(e)
        print(f"❌ Bitbucket network error: {e}")
    except Exception as e:
        results['bitbucket']['error'] = 'unexpected'
        results['bitbucket']['details'] = str(e)
        print(f"❌ Bitbucket unexpected error: {e}")

    print()

    # Test GitHub connection
    try:
        print("Testing GitHub API...")
        gh_client = GitHubClient(args.gh_owner, args.gh_repo, args.gh_token)
        if gh_client.test_connection(detailed=True):
            results['github']['success'] = True
            print("✅ GitHub authentication successful")
        else:
            results['github']['success'] = False
            results['github']['details'] = "Connection test returned False"
            print("❌ GitHub authentication failed")
    except ValidationError as e:
        results['github']['error'] = 'validation'
        results['github']['details'] = str(e)
        print(f"❌ GitHub validation error: {e}")
    except AuthenticationError as e:
        results['github']['error'] = 'auth'
        results['github']['details'] = str(e)
        print(f"❌ GitHub authentication failed: {e}")
    except APIError as e:
        results['github']['error'] = 'api'
        results['github']['details'] = str(e)
        if "404" in str(e):
            print(f"❌ GitHub API error (404): Repository not found or no access")
            print(f"   Please verify: https://github.com/{args.gh_owner}/{args.gh_repo}")
        else:
            print(f"❌ GitHub API error: {e}")
    except NetworkError as e:
        results['github']['error'] = 'network'
        results['github']['details'] = str(e)
        print(f"❌ GitHub network error: {e}")
    except Exception as e:
        results['github']['error'] = 'unexpected'
        results['github']['details'] = str(e)
        print(f"❌ GitHub unexpected error: {e}")

    print()

    # Test GitHub CLI availability and authentication
    print("Testing GitHub CLI...")
    try:
        gh_cli_result = _check_gh_cli_available(args.gh_token)
        results['gh_cli']['available'] = gh_cli_result['available']
        results['gh_cli']['authenticated'] = gh_cli_result['authenticated']
        results['gh_cli']['details'] = gh_cli_result['details']

        if gh_cli_result['available']:
            print("✅ GitHub CLI is installed")
            if gh_cli_result['authenticated']:
                print("✅ GitHub CLI is authenticated")
            else:
                print("❌ GitHub CLI is not authenticated")
                # Try to authenticate automatically
                print("Attempting automatic GitHub CLI authentication...")
                auth_result = _authenticate_gh_cli(args.gh_token)
                if auth_result['success']:
                    print("✅ GitHub CLI authentication successful")
                    results['gh_cli']['authenticated'] = True
                    results['gh_cli']['details'] = "Authenticated automatically"
                else:
                    print(f"❌ GitHub CLI authentication failed: {auth_result['error']}")
                    results['gh_cli']['details'] = auth_result['error']
        else:
            print("❌ GitHub CLI is not installed")
            print("GitHub CLI is required for automatic attachment uploads.")
            print("Install from: https://cli.github.com/")

    except Exception as e:
        results['gh_cli']['error'] = 'unexpected'
        results['gh_cli']['details'] = str(e)
        print(f"❌ GitHub CLI check failed: {e}")

    print()
    print("=" * 50)

    # Summary
    bb_success = results['bitbucket']['success']
    gh_success = results['github']['success']
    gh_cli_available = results['gh_cli']['available']

    if bb_success and gh_success:
        print("✅ All authentication tests passed!")
        if gh_cli_available:
            print("✅ GitHub CLI is ready for automatic attachment uploads")
        else:
            print("⚠️  GitHub CLI not available - attachments will need manual upload")
            print("   Install GitHub CLI for automatic attachment uploads: https://cli.github.com/")
        print("\nYou can now proceed with the migration using:")
        print(f"   python migrate_bitbucket_to_github.py migrate --config migration_config.json")
        if not gh_cli_available:
            print(f"   python migrate_bitbucket_to_github.py migrate --config migration_config.json --use-gh-cli")
    else:
        print("❌ Some authentication tests failed:")
        if not bb_success:
            print(f"   Bitbucket: {results['bitbucket']['details']}")
        if not gh_success:
            print(f"   GitHub: {results['github']['details']}")
        if not gh_cli_available:
            print(f"   GitHub CLI: {results['gh_cli']['details']}")

        # Provide specific guidance based on error types
        if results['bitbucket']['error'] == 'validation':
            print("\nFor Bitbucket:")
            print("  - Ensure workspace name, repository name, email, and token are provided")
            print("  - Use your Atlassian account email (not a secondary email)")
            print("  - Use a user-level API token (not repository access token)")
        elif results['bitbucket']['error'] == 'auth':
            print("\nFor Bitbucket:")
            print("  - Verify your API token is valid and not expired")
            print("  - Ensure the token has repository read permissions")
            print("  - Check: Settings > Atlassian account settings > Security > API tokens")
        elif results['bitbucket']['error'] == 'api':
            print("\nFor Bitbucket:")
            print(f"  - Verify the repository exists: https://bitbucket.org/{args.workspace}/{args.repo}")
            print("  - Ensure you have access to the repository")
            print("  - Check if the workspace name is correct")

        if results['github']['error'] == 'validation':
            print("\nFor GitHub:")
            print("  - Ensure owner, repository name, and token are provided")
            print("  - Use a personal access token with 'repo' scope")
        elif results['github']['error'] == 'auth':
            print("\nFor GitHub:")
            print("  - Verify your personal access token is valid and not expired")
            print("  - Ensure the token has 'repo' scope permissions")
            print("  - Check: Settings > Developer settings > Personal access tokens")
        elif results['github']['error'] == 'api':
            print("\nFor GitHub:")
            print(f"  - Verify the repository exists: https://github.com/{args.gh_owner}/{args.gh_repo}")
            print("  - Ensure you have access to the repository")
            print("  - Check if the owner and repository names are correct")

        if not gh_cli_available:
            print("\nFor GitHub CLI:")
            print("  - Install GitHub CLI for automatic attachment uploads")
            print("  - Visit: https://cli.github.com/")
            print("  - After installation, run: gh auth login")

        sys.exit(1)


def run_clean(args):
    """Remove output files generated by audit, dry-run, and migrate subcommands.

    By default, removes all output files except the configuration file.
    With --all flag, removes everything including the config file.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments containing the --all flag.

    Side Effects
    ------------
    - Removes specified files and directories
    - Prints status messages to stdout
    - Exits with error code 1 if removal fails

    Examples
    --------
    >>> args = argparse.Namespace(all=False)
    >>> run_clean(args)  # Remove outputs, keep config
    >>> args = argparse.Namespace(all=True)
    >>> run_clean(args)  # Remove everything
    """
    import shutil

    # List of output files to remove (excluding config by default)
    output_files = [
        'bitbucket_audit_report.json',
        'bitbucket_audit_report.md',
        'bitbucket_issues_detail.json',
        'bitbucket_prs_detail.json',
        'migration_log.txt',
        'migration_dry_run_log.txt',
        'migration_mapping.json',
        'migration_report.md',
        'migration_report_dry_run.md',
        'migration_mapping_partial.json'
    ]

    # List of directories to remove
    output_dirs = [
        'attachments_temp'
    ]

    # Config file
    config_file = 'migration_config.json'

    # Determine what to remove
    if getattr(args, 'all', False):
        files_to_remove = output_files + [config_file]
        print("🧹 Cleaning all output files including configuration...")
    else:
        files_to_remove = output_files
        print("🧹 Cleaning output files (keeping configuration)...")

    # Remove files
    for file in files_to_remove:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"  ✓ Removed {file}")
            except Exception as e:
                print(f"  ❌ Error removing {file}: {e}")
                sys.exit(1)
        else:
            print(f"  - {file} not found (already clean)")

    # Remove directories
    for dir in output_dirs:
        if os.path.exists(dir):
            try:
                shutil.rmtree(dir)
                print(f"  ✓ Removed directory {dir}")
            except Exception as e:
                print(f"  ❌ Error removing directory {dir}: {e}")
                sys.exit(1)
        else:
            print(f"  - Directory {dir} not found (already clean)")

    print("✅ Clean completed!")


def run_migration(args, dry_run=False):
    """Execute migration or dry-run using configuration file.

    Loads migration configuration and executes either a full migration or a dry-run
    simulation. In dry-run mode, all validation and planning occurs without making
    any changes to GitHub. Supports overriding configuration values via command-line.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments containing config path and optional overrides:
        config (required), skip_issues, skip_prs, skip_pr_as_issue, use_gh_cli.
    dry_run : bool, optional
        If True, simulate migration without making changes to GitHub, by default False.

    Side Effects
    ------------
    - Loads configuration from JSON file
    - Creates MigrationOrchestrator instance
    - Makes API calls to Bitbucket and GitHub (read-only in dry-run mode)
    - Downloads attachments to local directory
    - Prints detailed logging information to console and files
    - In full migration mode: creates issues, PRs, comments, and labels on GitHub

    Raises
    ------
    ConfigurationError
        If configuration file is invalid or missing required fields.
    ValidationError
        If configuration values are invalid.
    APIError
        If API calls to Bitbucket or GitHub fail.
    AuthenticationError
        If authentication with either service fails.
    NetworkError
        If network connectivity issues occur.

    Examples
    --------
    >>> args = argparse.Namespace(config='migration_config.json')
    >>> run_migration(args, dry_run=True)  # Simulate migration
    >>> run_migration(args, dry_run=False)  # Execute full migration
    """
    # Load configuration securely
    try:
        config = SecureConfigLoader.load_from_file(args.config)
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    except ValidationError as e:
        print(f"❌ Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        sys.exit(1)

    # Override config values with command line arguments
    if hasattr(args, 'skip_issues'):
        config.skip_issues = args.skip_issues.lower() == 'true'
    if hasattr(args, 'skip_prs'):
        config.skip_prs = args.skip_prs.lower() == 'true'
    if hasattr(args, 'skip_pr_as_issue'):
        config.skip_pr_as_issue = args.skip_pr_as_issue.lower() == 'true'
    if hasattr(args, 'use_gh_cli'):
        config.use_gh_cli = args.use_gh_cli.lower() == 'true'

    # Set dry run mode
    config.dry_run = dry_run

    # Create orchestrator
    orchestrator = MigrationOrchestrator(config)

    if dry_run:
        orchestrator.logger.info("="*80)
        orchestrator.logger.info("🔍 DRY RUN MODE ENABLED")
        orchestrator.logger.info("="*80)
        orchestrator.logger.info("This is a simulation - NO changes will be made to GitHub")
        orchestrator.logger.info("")
        orchestrator.logger.info("What WILL happen (read-only):")
        orchestrator.logger.info("  ✓ Fetch all issues and PRs from Bitbucket")
        orchestrator.logger.info("  ✓ Check if branches exist on GitHub")
        orchestrator.logger.info("  ✓ Download attachments to local folder")
        orchestrator.logger.info("  ✓ Validate user mappings")
        orchestrator.logger.info("  ✓ Show exactly which PRs become GitHub PRs vs Issues")
        orchestrator.logger.info("")
        orchestrator.logger.info("What WON'T happen (no writes):")
        orchestrator.logger.info("  ✗ No issues created on GitHub")
        orchestrator.logger.info("  ✗ No PRs created on GitHub")
        orchestrator.logger.info("  ✗ No comments added to GitHub")
        orchestrator.logger.info("  ✗ No labels applied")
        orchestrator.logger.info("")
        orchestrator.logger.info("Use this to verify:")
        orchestrator.logger.info("  • Bitbucket connection works")
        orchestrator.logger.info("  • GitHub connection works (read-only check)")
        orchestrator.logger.info("  • User mappings are correct")
        orchestrator.logger.info("  • Branch existence (actual check)")
        orchestrator.logger.info("  • PR migration strategy (which become PRs vs issues)")
        orchestrator.logger.info("  • Exact GitHub issue/PR numbers that will be created")
        orchestrator.logger.info("")
        orchestrator.logger.info("After successful dry-run, use migrate subcommand to perform actual migration")
        orchestrator.logger.info("="*80 + "\n")

    # Run migration using orchestrator
    orchestrator.run_migration()


def main():
    """Main entry point for the Bitbucket to GitHub migration CLI tool.

    Parses command-line arguments and routes execution to the appropriate subcommand
    handler (audit, migrate, dry-run, or test-auth). Provides comprehensive error
    handling and user-friendly error messages.

    Side Effects
    ------------
    - Parses command-line arguments using argparse
    - Routes to appropriate subcommand handler function
    - May prompt user for missing required arguments
    - Exits program with appropriate error codes on failures
    - Prints status messages and errors to stdout/stderr

    Raises
    ------
    SystemExit
        Always exits with code 0 on success, 1 on error.

    Examples
    --------
    Run from command line with subcommands:

    $ python migrate_bitbucket_to_github.py audit --workspace myteam --repo myproject
    $ python migrate_bitbucket_to_github.py migrate --config migration_config.json
    $ python migrate_bitbucket_to_github.py dry-run --config migration_config.json
    $ python migrate_bitbucket_to_github.py test-auth --workspace myteam --repo myproject
    """
    parser = create_main_parser()
    args = parser.parse_args()

    if args.command == 'audit':
        run_audit(args, parser)
    elif args.command == 'migrate':
        run_migration(args, dry_run=False)
    elif args.command == 'dry-run':
        run_migration(args, dry_run=True)
    elif args.command == 'test-auth':
        run_test_auth(args, parser)
    elif args.command == 'clean':
        run_clean(args)
    else:
        print(f"❌ Unknown command: {args.command}")
        sys.exit(1)
        


if __name__ == '__main__':
    main()