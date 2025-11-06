#!/usr/bin/env python3
"""
Clean command for Bitbucket to GitHub migration.

This module contains the run_clean function that handles cleaning
migration outputs with granular filtering.
"""

def run_clean(args):
    """Clean migration outputs with granular filtering.

    Supports cleaning specific subcommand directories or all outputs.
    Can determine base directory from config file or explicit flag.
    Supports file tracking filters for workspace, repo, and subcommand.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments containing filter flags and base directory options.

    Side Effects
    ------------
    - Removes specified files and directories
    - Prints status messages to stdout
    - Exits with error code 1 if removal fails

    Examples
    --------
    >>> args = argparse.Namespace(config='config.json', subcommand=['audit'])
    >>> run_clean(args)  # Clean only audit outputs
    >>> args = argparse.Namespace(base_dir='./project', reset=True)
    >>> run_clean(args)  # Clean all outputs from base directory
    """
    from bitbucket_migration.utils.base_dir_manager import BaseDirManager
    from bitbucket_migration.config.secure_config import SecureConfigLoader
    import shutil
    from pathlib import Path
    import sys

    # Determine base directory
    if getattr(args, 'config', None):
        try:
            config = SecureConfigLoader.load_from_file(args.config)
            base_dir = config.base_dir
            print(f"🧹 Using base directory from config: {base_dir}")
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            sys.exit(1)
    elif getattr(args, 'base_dir', None):
        base_dir = args.base_dir
        print(f"🧹 Using explicit base directory: {base_dir}")
    else:
        base_dir = '.'
        print("🧹 Using current directory as base directory")

    base_dir_manager = BaseDirManager(base_dir)
    base_path = base_dir_manager.base_dir

    dry_run = getattr(args, 'dry_run', False)

    if dry_run:
        print("\nDRY-RUN mode: no files or folders will be deleted.\n")

    # Determine what to clean
    if getattr(args, 'reset', False):
        # Reset mode: delete everything including config
        print(f"⚠️  This will delete the entire base directory: {base_path}/")
        print("   Including config.json and cross_repo_mappings.json")

        confirm = input("Are you sure? Type 'yes' to confirm: ")
        if confirm.lower() != 'yes':
            print("❌ Reset cancelled")
            return

        try:
            if not dry_run:
                base_dir_manager.clean_everything()
        except Exception as e:
            print(f"❌ Error during reset: {e}")
            sys.exit(1)
        return

    # Check if using file tracking filters
    use_file_tracking = any([
        getattr(args, 'workspace', None),
        getattr(args, 'repo', None),
        getattr(args, 'subcommand', None)
    ])

    # Build filter criteria
    filters = {
        'subcommand': getattr(args, 'subcommand', []),
        'workspace': getattr(args, 'workspace', []),
        'repo': getattr(args, 'repo', []),
        }

    # Get files matching filters
    if use_file_tracking:
        print(f"🧹 Using file tracking to clean with filters:")
        for key, value in filters.items():
            if value:
                print(f"   - {key}: {value}")
        print()
    else:
        print(f"🧹 Cleaning all outputs from base directory: {base_path}")
        print()
    
    try:
        # Get list of files to clean
        folders_to_clean, files_to_clean = base_dir_manager.get_folders_and_files(**filters, exists_only=True)
        
        if folders_to_clean and not files_to_clean:
            print("✅ No folders or files found matching filters.")
            return
        
        print(f"Found {len(folders_to_clean)} folder(s) and {len(files_to_clean)} file(s) matching filters:")
        
        if len(folders_to_clean) > 0:
            print("Folders to delete:")
            for folder in folders_to_clean:
                print(f"  - {folder}")

        if len(files_to_clean) > 0:
            print("Files to delete:")
            for file_info in files_to_clean[:10]:  # Show first 10
                print(f"  - {file_info['path']} ({file_info.get('category', 'N/A')})")
            if len(files_to_clean) > 10:
                print(f"  ... and {len(files_to_clean) - 10} more")
        
        confirm = input(f"\nProceed with cleaning{' dry-run' if dry_run else ''}? [Y/n]: ")
        if confirm.lower() not in ['', 'y', 'yes']:
            print("❌ Clean cancelled")
            return
        
        # Perform cleanup
        results = base_dir_manager.clean_files(dry_run=dry_run, **filters)
        
        print(f"\n✅ Clean completed!")
        print(f"   - Deleted: {len(results['deleted'])} file(s)")
        print(f"   - Failed: {results['failures']} file(s)")
        if results['failures'] > 0:
            print("\nFailed deletions (first 5):")
            for error in results['errors'][:5]:
                print(f"   - {error['path']}: {error['error']}")
        
        if dry_run:
            print("\nDRY-RUN mode: no files or folders were deleted.\n")

    except Exception as e:
        print(f"❌ Error during file tracking cleanup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)