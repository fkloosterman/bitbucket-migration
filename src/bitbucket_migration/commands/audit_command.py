#!/usr/bin/env python3
"""
Audit command for Bitbucket to GitHub migration.

This module contains the run_audit function that handles repository auditing
for migration planning and configuration generation.
"""

import sys
import getpass
import os
from dotenv import load_dotenv

# Import custom exceptions
from bitbucket_migration.exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    ValidationError,
)

# Import audit and config modules
from bitbucket_migration.audit.audit_orchestrator import AuditOrchestrator
from bitbucket_migration.utils.base_dir_manager import BaseDirManager
from bitbucket_migration.config.secure_config import SecureConfigLoader

def run_audit(args, parser=None):
    """Run comprehensive audit of Bitbucket repository for migration planning.

    Performs a complete analysis of the Bitbucket repository including issues, pull
    requests, branches, and user mappings. Generates detailed reports and creates
    a migration configuration file. Prompts for any missing required arguments.

    Supports single-repo, multi-repo (explicit list), and auto-discovery modes.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments containing workspace, repo, email, token, and optional
        flags like gh_owner, gh_repo, repos, discover.
    parser : argparse.ArgumentParser, optional
        The argument parser instance for extracting help text during prompting.

    Side Effects
    ------------
    - Prompts user for missing arguments interactively
    - Creates BitbucketClient and AuditOrchestrator instances
    - Makes API calls to Bitbucket
    - Generates and saves audit reports (bitbucket_audit_report.json, audit_report.md)
    - Generates migration configuration file (migration_config.json)

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
    # Determine log level
    log_level = "DEBUG" if getattr(args, 'debug', False) else "INFO"
    
    # Determine which repos to audit
    repo_names = None
    external_repo_names = []
    
    # Create BaseDirManager once
    base_dir = getattr(args, 'base_dir', None) or '.'
    base_dir_manager = BaseDirManager(base_dir)

    # Try to load existing config to use as defaults
    existing_config = None
    config_path = base_dir_manager.get_config_path()

    if config_path.exists():
        try:
            existing_config = SecureConfigLoader.load_from_file(str(config_path))
            # Use existing values as defaults for missing arguments
            if not getattr(args, 'workspace', None) and hasattr(existing_config, 'bitbucket'):
                args.workspace = existing_config.bitbucket.workspace
            if not getattr(args, 'email', None) and hasattr(existing_config, 'bitbucket'):
                args.email = existing_config.bitbucket.email
            if not getattr(args, 'gh_owner', None) and hasattr(existing_config, 'github'):
                args.gh_owner = existing_config.github.owner
        except Exception as e:
            # If we can't load existing config, just warn and continue
            print(f"⚠️  Could not load existing config, will prompt for required fields: {e}")


    if getattr(args, 'discover', False):
        # Auto-discovery mode
        required_fields = ['workspace', 'email', 'token']
        args = prompt_for_missing_args(args, required_fields, parser)

        try:
            # Create multi-repo auditor for discovery
            multi_auditor = AuditOrchestrator(
                workspace=args.workspace,
                email=args.email,
                token=args.token,
                log_level=log_level
            )

            # Discover repositories
            all_repo_names = multi_auditor.discover_repositories()

            if not all_repo_names:
                print("⚠️  No repositories found in workspace")
                return

            # Ask user to specify repositories to migrate and external references
            print(f"\n{'='*80}")
            print(f"Found {len(all_repo_names)} repositories:")
            for i, name in enumerate(all_repo_names, 1):
                print(f"  {i}. {name}")
            print(f"{'='*80}\n")

            # Get repositories to migrate
            migrate_input = input("Enter repository numbers to migrate (comma-separated, or 'all' for all): ").strip()
            if migrate_input.lower() == 'all':
                repo_names = all_repo_names.copy()
            else:
                try:
                    # Parse numbers and convert to repo names
                    indices = [int(x.strip()) - 1 for x in migrate_input.split(',') if x.strip()]
                    repo_names = []
                    invalid_indices = []
                    for idx in indices:
                        if 0 <= idx < len(all_repo_names):
                            repo_names.append(all_repo_names[idx])
                        else:
                            invalid_indices.append(str(idx + 1))
                    if invalid_indices:
                        print(f"❌ Invalid repository numbers: {', '.join(invalid_indices)}")
                        print(f"Available repositories: 1-{len(all_repo_names)}")
                        return
                except ValueError:
                    print("❌ Invalid input. Please enter numbers separated by commas or 'all'")
                    return

            if not repo_names:
                print("⚠️  No repositories selected for migration")
                return

            # Get external reference repositories
            external_input = input("Enter external reference repository numbers (comma-separated, or empty for none): ").strip()
            if external_input:
                try:
                    # Parse numbers and convert to repo names
                    indices = [int(x.strip()) - 1 for x in external_input.split(',') if x.strip()]
                    invalid_indices = []
                    for idx in indices:
                        if 0 <= idx < len(all_repo_names):
                            external_repo_names.append(all_repo_names[idx])
                        else:
                            invalid_indices.append(str(idx + 1))
                    if invalid_indices:
                        print(f"❌ Invalid external repository numbers: {', '.join(invalid_indices)}")
                        print(f"Available repositories: 1-{len(all_repo_names)}")
                        return
                except ValueError:
                    print("❌ Invalid input. Please enter numbers separated by commas or leave empty")
                    return

            # Check for overlap
            overlap = set(repo_names) & set(external_repo_names)
            if overlap:
                print(f"❌ Repositories cannot be both migrated and external: {', '.join(overlap)}")
                return

        except KeyboardInterrupt:
            print("\nAudit interrupted by user")
            sys.exit(1)
        except (APIError, AuthenticationError, NetworkError, ValidationError) as e:
            print(f"\n❌ Error during repository discovery: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Unexpected error during repository discovery: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    elif getattr(args, 'repo', None):
        # Explicit list of repos (using --repo or --repos, they're aliases)
        required_fields = ['workspace', 'email', 'token']
        args = prompt_for_missing_args(args, required_fields, parser)

        # Handle both string (single repo) and list (multiple repos)
        if isinstance(args.repo, list):
            repo_names = [r.strip() for r in args.repo]
        else:
            repo_names = [args.repo.strip()]

        print(f"\n{'='*80}")
        print(f"Auditing {len(repo_names)} repositories:")
        for i, name in enumerate(repo_names, 1):
            print(f"  {i}. {name}")
        print(f"{'='*80}\n")
    
    else:
        # Single repo (existing behavior)
        required_fields = ['workspace', 'repo', 'email', 'token']
        args = prompt_for_missing_args(args, required_fields, parser)
        repo_names = [args.repo]
    
    try:

        # Prompt for gh_owner if not provided (always generate config now)
        if not getattr(args, 'gh_owner', None):
            args.gh_owner = input('GitHub owner: ')

        # Run audit based on mode
        multi_auditor = AuditOrchestrator(
            workspace=args.workspace,
            email=args.email,
            token=args.token,
            log_level=log_level,
            base_dir_manager=base_dir_manager
        )

        # Audit all repositories
        reports = multi_auditor.audit_repositories(repo_names=repo_names, save_reports=True)

        # Always generate unified config (merges with existing if present)
        gh_owner = args.gh_owner
        # Convert MigrationConfig object to dict for merging
        existing_config_dict = None
        if existing_config:
            existing_config_dict = {
                'bitbucket': {
                    'workspace': existing_config.bitbucket.workspace,
                    'email': existing_config.bitbucket.email,
                    'token': existing_config.bitbucket.token
                },
                'github': {
                    'owner': existing_config.github.owner,
                    'token': existing_config.github.token
                },
                'repositories': [{'bitbucket_repo': r.bitbucket_repo, 'github_repo': r.github_repo} for r in (existing_config.repositories or [])],
                'external_repositories': [{'bitbucket_repo': r.bitbucket_repo, 'github_repo': r.github_repo} for r in (existing_config.external_repositories or [])],
                'user_mapping': existing_config.user_mapping or {},
                'base_dir': str(existing_config.base_dir) if hasattr(existing_config, 'base_dir') else None,
                'options': existing_config.options.__dict__ if hasattr(existing_config, 'options') else {}
            }
        unified_config = multi_auditor.generate_config(reports, gh_owner, external_repo_names, existing_config_dict)

        # Save unified config
        multi_auditor.save_config(unified_config)

        print(f"\n✅ Multi-repository audit completed!")
        print(f"📄 Reports saved to: {base_dir_manager.base_dir / "audit"}/")
        print(f"📋 Unified migration config generated: {base_dir_manager.get_config_path()}")
        if external_repo_names:
            print(f"   - Migration repositories: {len(repo_names)}")
            print(f"   - External reference repositories: {len(external_repo_names)}")
        
    
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