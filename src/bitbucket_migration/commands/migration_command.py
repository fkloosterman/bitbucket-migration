#!/usr/bin/env python3
"""
Migration command for Bitbucket to GitHub migration.

This module contains the run_migration function that handles
executing migration or dry-run using configuration file.
"""

import sys
from bitbucket_migration.config.secure_config import SecureConfigLoader
from bitbucket_migration.exceptions import ConfigurationError, ValidationError
from bitbucket_migration.core.migration_orchestrator import MigrationOrchestrator


def run_migration(args):
    """Execute migration or dry-run using configuration file.

    Loads migration configuration and executes either a full migration or a dry-run
    simulation. Supports both unified multi-repo and legacy per-repo configurations.
    In dry-run mode, all validation and planning occurs without making
    any changes to GitHub. Supports overriding configuration values via command-line.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments containing config path and optional overrides:
        config (required), skip_issues, skip_prs, skip_pr_as_issue,
        repo (for unified config), repos (for unified config).

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
    SystemExit
        Exits with code 1 if configuration loading or validation fails.

    Examples
    --------
    >>> args = argparse.Namespace(config='migration_config.json')
    >>> run_migration(args)  # Execute migration (dry-run controlled by config)
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
    
    # Parse repository selection for unified config (both --repo and --repos are aliases)
    selected_repos = None
    if hasattr(args, 'repo') and args.repo:
        # Handle both list and string inputs
        if isinstance(args.repo, list):
            selected_repos = [r.strip() for r in args.repo]
        elif isinstance(args.repo, str):
            # Handle comma-separated string
            if args.repo.strip():
                selected_repos = [r.strip() for r in args.repo.split(',')]
            else:
                selected_repos = None  # Empty string means all repos
    # If --all is specified or no selection made, selected_repos stays None (all repos)

    # Override config options with command line arguments
    if hasattr(args, 'skip_issues'):
        config.options.skip_issues = args.skip_issues.lower() == 'true'
    if hasattr(args, 'open_issues_only'):
        config.options.open_issues_only = args.open_issues_only.lower() == 'true'
    if hasattr(args, 'skip_prs'):
        config.options.skip_prs = args.skip_prs.lower() == 'true'
    if hasattr(args, 'open_prs_only'):
        config.options.open_prs_only = args.open_prs_only.lower() == 'true'
    if hasattr(args, 'skip_pr_as_issue'):
        config.options.skip_pr_as_issue = args.skip_pr_as_issue.lower() == 'true'
    if hasattr(args, 'skip_milestones'):
        config.options.skip_milestones = args.skip_milestones.lower() == 'true'
    if hasattr(args, 'open_milestones_only'):
        config.options.open_milestones_only = args.open_milestones_only.lower() == 'true'
    if hasattr(args, 'dry_run'):
        config.options.dry_run = args.dry_run.lower() == 'true'
    
    log_level = "DEBUG" if getattr(args, 'debug', False) else "INFO"

    # Use orchestrator (base_dir comes from config)
    orchestrator = MigrationOrchestrator(config, selected_repos=selected_repos, dry_run=config.options.dry_run, log_level=log_level)
    orchestrator.run_migration()