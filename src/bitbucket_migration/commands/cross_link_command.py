#!/usr/bin/env python3
"""
Cross-link command for Bitbucket to GitHub migration.

This module contains the run_cross_link function that handles
post-migration processing of cross-repository links.
"""

import sys
from bitbucket_migration.config.secure_config import SecureConfigLoader
from bitbucket_migration.exceptions import ConfigurationError, ValidationError
from bitbucket_migration.core.migration_orchestrator import CrossLinkOrchestrator

def run_cross_link(args):
    """Execute cross-link processing using configuration file.

    Loads migration configuration and processes cross-repository links
    for unified multi-repo configurations. Supports dry-run mode for
    validation without making changes. Can process specific repositories
    or all repositories in the configuration.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments containing config path and optional overrides.

    Side Effects
    ------------
    - Loads configuration from JSON file
    - Creates CrossLinkOrchestrator instance
    - Makes API calls to GitHub for link processing
    - Prints detailed logging information to console and files
    - Updates cross-repository links in GitHub issues and PRs

    Raises
    ------
    SystemExit
        Exits with code 1 if configuration loading or validation fails.

    Examples
    --------
    >>> args = argparse.Namespace(config='migration_config.json')
    >>> run_cross_link(args, dry_run=True)  # Simulate cross-linking
    >>> run_cross_link(args, dry_run=False)  # Execute cross-linking
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
    if hasattr(args, 'repo') and args.repo is not None:
        selected_repos = [r.strip() for r in args.repo] if args.repo else []
    if hasattr(args, 'dry_run') and args.dry_run is not None:
        config.options.dry_run = args.dry_run.lower() == 'true'
    # If --all is specified or no selection made, selected_repos stays None (all repos)

    log_level = "DEBUG" if getattr(args, 'debug', False) else "INFO"

    # Use orchestrator (base_dir comes from config)
    orchestrator = CrossLinkOrchestrator(config, selected_repos=selected_repos, dry_run=config.options.dry_run, log_level=log_level)
    orchestrator.run_migration()