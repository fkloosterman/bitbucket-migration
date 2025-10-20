#!/usr/bin/env python3
"""
Test Bitbucket API authentication before running the full audit.

This script validates Bitbucket API credentials and permissions by testing multiple
API endpoints including repository info, issues, and pull requests. It helps diagnose
authentication issues and verify that the provided API token has the necessary
permissions for the migration process.

Args:
    workspace (str): Bitbucket workspace name (e.g., 'myteam')
    repo (str): Repository name (e.g., 'myrepo')
    email (str): Atlassian account email address
    api_token (str): Bitbucket user-level API token

Returns:
    bool: True if all authentication tests pass, False otherwise

Raises:
    SystemExit: Exits with code 0 on success, 1 on failure

Authentication Notes:
    - Uses user-level API Token (replacement for App Passwords)
    - Repository Access Tokens do NOT support issue APIs
    - Requires HTTP Basic Auth with email + token format

Test Coverage:
    - Repository Info: Verifies repository access and basic metadata
    - Issues List: Confirms issues API permissions
    - Pull Requests List: Validates pull request API access

Output:
    - Detailed test results for each API endpoint
    - Authentication status and user information
    - Troubleshooting guidance for failed tests
    - Step-by-step API token creation instructions on failure

Example:
    python test_auth.py --workspace myteam --repo myrepo --email user@example.com --token API_TOKEN
"""

import sys
import requests
import getpass


def test_authentication(workspace, repo, email, api_token):
    """Test various Bitbucket API endpoints to verify authentication"""
    
    print("Testing Bitbucket API Authentication")
    print("=" * 60)
    print(f"Workspace: {workspace}")
    print(f"Repository: {repo}")
    print(f"Email: {email}")
    print(f"Using user-level API Token authentication")
    print("=" * 60 + "\n")
    
    session = requests.Session()
    # Bitbucket API tokens use HTTP Basic Auth with email + token
    session.auth = (email, api_token)
    
    tests = [
        {
            'name': 'Repository Info',
            'url': f'https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}',
            'description': 'Verify repository access'
        },
        {
            'name': 'Issues List',
            'url': f'https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/issues',
            'description': 'Verify issues API access'
        },
        {
            'name': 'Pull Requests List',
            'url': f'https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pullrequests',
            'description': 'Verify pull requests API access'
        },
    ]
    
    all_passed = True
    
    for i, test in enumerate(tests, 1):
        print(f"Test {i}/{len(tests)}: {test['name']}")
        print(f"  {test['description']}")
        print(f"  URL: {test['url']}")
        
        try:
            response = session.get(test['url'], timeout=10)
            
            if response.status_code == 200:
                print(f"  ✅ SUCCESS (200 OK)")
                
                # Show some data for successful requests
                data = response.json()
                if 'username' in data:
                    print(f"     Authenticated as: {data['username']}")
                elif 'name' in data:
                    print(f"     Repository: {data['name']}")
                elif 'size' in data:
                    print(f"     Found {data['size']} items")
                    
            elif response.status_code == 401:
                print(f"  ❌ FAILED: 401 Unauthorized")
                print(f"     Authentication credentials are invalid or missing permissions")
                all_passed = False
                
            elif response.status_code == 403:
                print(f"  ❌ FAILED: 403 Forbidden")
                print(f"     You don't have permission to access this resource")
                all_passed = False
                
            elif response.status_code == 404:
                print(f"  ❌ FAILED: 404 Not Found")
                print(f"     Repository or resource doesn't exist")
                all_passed = False
                
            else:
                print(f"  ⚠️  UNEXPECTED: {response.status_code}")
                print(f"     {response.reason}")
                all_passed = False
                
        except requests.exceptions.Timeout:
            print(f"  ❌ FAILED: Request timeout")
            all_passed = False
            
        except requests.exceptions.ConnectionError:
            print(f"  ❌ FAILED: Connection error")
            all_passed = False
            
        except Exception as e:
            print(f"  ❌ FAILED: {str(e)}")
            all_passed = False
        
        print()
    
    print("=" * 60)
    if all_passed:
        print("✅ All tests passed! Your API Token is working correctly.")
        print("You can now run the full audit script.")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        print("\nHow to create a user-level API Token:")
        print("\n1. Go to: Settings > Atlassian account settings > Security")
        print("2. Click 'Create and manage API tokens'")
        print("3. Click 'Create API token with scopes'")
        print("4. Name it (e.g., 'Migration Audit')")
        print("5. Set expiry date")
        print("6. Select 'Bitbucket' as the app")
        print("7. Select permissions or choose 'Full access'")
        print("8. Click 'Create' and copy the token")
        print("\nIMPORTANT:")
        print("- Use your Atlassian account email (Bitbucket > Personal settings > Email aliases)")
        print("- User-level API tokens replace App Passwords (deprecated Sept 2025)")
        print("- Repository Access Tokens do NOT support issue access")
        print(f"\n3. Verify repository access:")
        print(f"   https://bitbucket.org/{workspace}/{repo}")
    print("=" * 60)
    
    return all_passed


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Test Bitbucket API authentication',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using user-level API Token
  python test_auth.py --workspace myteam --repo myrepo --email user@example.com --token API_TOKEN
  
  # Token will be prompted if not provided
  python test_auth.py --workspace myteam --repo myrepo --email user@example.com

Creating a user-level API Token:
  Go to: Settings > Atlassian account settings > Security > API tokens
  This is the replacement for App Passwords (deprecated Sept 2025)
  
Note: Repository Access Tokens do NOT support issue APIs.
      You MUST use a user-level API token.
        """
    )
    parser.add_argument('--workspace', required=True, help='Bitbucket workspace name')
    parser.add_argument('--repo', required=True, help='Repository name')
    parser.add_argument('--email', required=True, help='Atlassian account email')
    parser.add_argument('--token', help='Bitbucket API token (will prompt if not provided)')
    
    args = parser.parse_args()
    
    api_token = args.token
    if not api_token:
        api_token = getpass.getpass('Bitbucket API token: ')
    
    success = test_authentication(args.workspace, args.repo, args.email, api_token)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()