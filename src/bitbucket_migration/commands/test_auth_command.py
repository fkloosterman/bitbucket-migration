#!/usr/bin/env python3
"""
Test authentication command for Bitbucket to GitHub migration.

This module contains the run_test_auth function that handles testing
authentication for both Bitbucket and GitHub APIs.
"""

import sys
import getpass
import os
from dotenv import load_dotenv
from bitbucket_migration.clients.bitbucket_client import BitbucketClient
from bitbucket_migration.clients.github_client import GitHubClient
from bitbucket_migration.exceptions import (
    MigrationError,
    APIError,
    AuthenticationError,
    NetworkError,
    ValidationError
)


def run_test_auth(args, parser=None):
    """Test authentication for both Bitbucket and GitHub APIs.

    Performs comprehensive authentication testing for all services required during
    migration: Bitbucket API and GitHub API. Provides detailed feedback
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
        'github': {'success': False, 'error': None, 'details': ''}
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
    print("=" * 50)

    # Summary
    bb_success = results['bitbucket']['success']
    gh_success = results['github']['success']

    if bb_success and gh_success:
        print("✅ All authentication tests passed!")
        print("\nNote: Attachments will need manual upload via drag-and-drop in GitHub issues")
        print("\nYou can now proceed with the repository audit\n")
    else:
        print("❌ Some authentication tests failed:")
        if not bb_success:
            print(f"   Bitbucket: {results['bitbucket']['details']}")
        if not gh_success:
            print(f"   GitHub: {results['github']['details']}")

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