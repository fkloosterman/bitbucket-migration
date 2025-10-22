# API Tokens Setup Guide

This comprehensive guide explains all authentication requirements for the Bitbucket to GitHub migration tools, including the audit script, migration script, and optional GitHub CLI integration.

---

## 🔑 Authentication Overview

The migration process requires multiple authentication methods depending on which tools you use:

| Tool | Bitbucket Token | GitHub PAT | GitHub CLI | Purpose |
|------|----------------|------------|------------|---------|
| `audit_bitbucket.py` | ✅ Required | ❌ Not needed | ❌ Not needed | Audit repository content |
| `migrate_bitbucket_to_github.py` | ✅ Required | ✅ Required | ❌ Optional | Migrate issues/PRs |
| `migrate_bitbucket_to_github.py --use-gh-cli` | ✅ Required | ✅ Required | ✅ Required | Auto-upload attachments |

**Choose your path:**

- **Basic Migration:** Bitbucket API Token + GitHub PAT
- **Advanced Migration:** All three authentication methods (for automatic attachment uploads)

---

## 🔑 Bitbucket Cloud API Token

**Required for:** `audit_bitbucket.py`, `migrate_bitbucket_to_github.py`

### Creating Your Token

1. Go to **Atlassian Account Settings → Security → Create and manage API tokens**
2. Click **Create API token**
3. Name it: `Migration Tool`
4. Choose **Bitbucket** as the app
5. Set **Full access** (or minimally: read repos, issues, PRs)
6. Copy the token immediately – it won't be shown again

### Required Permissions

```json
{
  "scopes": [
    "repository:read",
    "pullrequest:read",
    "issue:read",
    "account:read"
  ]
}
```

**Note:** User-level API tokens (not Repository Access Tokens) are required for issue and PR access.

### Usage in Configuration

```json
"bitbucket": {
  "email": "you@example.com",
  "token": "ATAT1234..."
}
```

---

## 🔑 GitHub Authentication

**Required for:** `migrate_bitbucket_to_github.py`

### GitHub Personal Access Token (PAT)

#### Creating Your Token

1. Go to **GitHub Settings → Developer settings → Personal access tokens (classic)**
2. Click **Generate new token (classic)**
3. Name it `Bitbucket Migration`
4. **Select scopes:**
    - `repo` (Full control of private repositories)
    - `user:email` (Read-only access to email addresses)
5. Click **Generate token** and copy it

#### Required Scopes Explained

| Scope | Purpose | Why Needed |
|-------|---------|------------|
| `repo` | Full repository access | Create issues, PRs, comments, manage assignees |
| `user:email` | Read email addresses | User mapping and author identification |

#### Usage in Configuration

```json
"github": {
  "owner": "my-org",
  "repo": "my-repo",
  "token": "ghp_abcd123..."
}
```

### GitHub CLI Authentication (Optional)

**Required only for:** `--use-gh-cli` flag (automatic attachment uploads)

#### Setup Instructions

1. **Install GitHub CLI:**
    ```bash
    # macOS
    brew install gh
 
    # Ubuntu/Debian
    sudo apt update && sudo apt install gh
 
    # Windows (using winget)
    winget install --id GitHub.cli
 
    # Other platforms: https://cli.github.com/
    ```

2. **Authenticate GitHub CLI:**
    ```bash
    gh auth login

    # Follow prompts:
    # - GitHub.com
    # - HTTPS
    # - Login with web browser
    # - Authorize GitHub CLI
    ```

3. **Verify authentication:**
    ```bash
    gh auth status
    ```

**Important:** GitHub CLI must be authenticated to the **same GitHub account/organization** as your PAT.

---

## 🔧 Token Security Best Practices

### Environment Variables (Recommended)

```bash
# Create .env file
BITBUCKET_EMAIL=you@example.com
BITBUCKET_TOKEN=ATAT1234...
GITHUB_TOKEN=ghp_abcd123...

# Load in your scripts
python audit_bitbucket.py --workspace $BITBUCKET_WORKSPACE --repo $BITBUCKET_REPO --email $BITBUCKET_EMAIL --token $BITBUCKET_TOKEN
```

### Security Guidelines

* **Never commit tokens** to Git repositories
* **Use read-only tokens** where possible (audit script only needs read access)
* **Rotate tokens regularly** (especially after migration completion)
* **Use separate tokens** for different purposes (audit vs migration)
* **Delete unused tokens** once migration is verified
* **Store securely** in password managers or secure credential storage

### Token Permissions Matrix

| Operation | Bitbucket Token | GitHub PAT | GitHub CLI |
|-----------|----------------|------------|------------|
| Repository audit | Read access | Not needed | Not needed |
| Issue migration | Read access | Repo access | Not needed |
| PR migration | Read access | Repo access | Not needed |
| Attachment upload | Read access | Repo access | Authenticated |

---

## ✅ Authentication Testing

### Test Bitbucket Authentication

Use the provided test script to verify your Bitbucket token:

```bash
python test_auth.py --workspace YOUR_WORKSPACE --repo YOUR_REPO --email you@example.com --token ATAT1234...
```

**Expected output:**
```
✅ All tests passed! Your API Token is working correctly.
```

**If tests fail:** The script provides detailed troubleshooting guidance and token creation instructions.

### Test GitHub Authentication

Verify your GitHub PAT works correctly:

```bash
# Test basic authentication
curl -H "Authorization: token ghp_abcd123..." https://api.github.com/user

# Test repository access
curl -H "Authorization: token ghp_abcd123..." https://api.github.com/repos/YOUR_ORG/YOUR_REPO

# Test issue creation (dry run)
curl -X POST -H "Authorization: token ghp_abcd123..." \
  https://api.github.com/repos/YOUR_ORG/YOUR_REPO/issues \
  -d '{"title":"Test Issue","body":"Testing authentication"}'
```

### Test GitHub CLI Authentication

```bash
# Check authentication status
gh auth status

# Test repository access
gh repo view YOUR_ORG/YOUR_REPO

# Test issue creation (dry run)
gh issue create --title "Test Issue" --body "Testing CLI auth" --repo YOUR_ORG/YOUR_REPO
```

---

## 🔍 Troubleshooting Authentication Issues

### Bitbucket Token Problems

**"401 Unauthorized"**

- Verify token is correct (copy-paste errors are common)
- Check if token has expired
- Ensure you're using a user-level API token (not Repository Access Token)
- Confirm token has issue and PR read permissions

**"403 Forbidden"**

- Token may lack required permissions
- Repository may be private and token doesn't have access
- Workspace access may be restricted

**"404 Not Found"**

- Verify workspace and repository names are correct
- Check if repository exists and is accessible

### GitHub Token Problems

**"401 Unauthorized"**

- Verify PAT is correct and not expired
- Check if PAT has `repo` scope enabled
- Ensure you're using a classic token (not fine-grained)

**"403 Forbidden"**

- PAT may lack required scopes
- Repository may be private and PAT doesn't have access
- Organization may require PAT approval

**"404 Not Found"**

- Verify repository exists and is accessible
- Check if organization/repository names are correct

### GitHub CLI Problems

**"gh: Not logged in"**
```bash
gh auth login
```

**"Repository not found"**

- Verify repository exists
- Check if CLI is authenticated to correct GitHub account
- Ensure repository is accessible with current authentication

**"Permission denied"**

- CLI may be authenticated to different account than PAT
- Repository may require different access level
- Organization may restrict CLI access

### Integration Issues

**"GitHub CLI not available" (when using --use-gh-cli)**

- Install GitHub CLI: https://cli.github.com/
- Verify installation: `gh --version`
- Authenticate: `gh auth login`

**"Authentication mismatch"**

- Ensure GitHub PAT and CLI are authenticated to same account
- Check if you're a member of the target organization
- Verify repository access permissions

---

## 💡 Verification Workflow

### Before Running Audit Script

1. **Test Bitbucket authentication:**
    ```bash
    python test_auth.py --workspace YOUR_WORKSPACE --repo YOUR_REPO --email you@example.com --token ATAT1234...
    ```

2. **Verify repository access:**
    ```bash
    curl -u you@example.com:ATAT1234... https://api.bitbucket.org/2.0/repositories/YOUR_WORKSPACE/YOUR_REPO
    ```

3. **Run audit script:**
    ```bash
    python audit_bitbucket.py --workspace YOUR_WORKSPACE --repo YOUR_REPO --email you@example.com --token ATAT1234...
    ```

### Before Running Migration Script

1. **Test GitHub PAT:**
    ```bash
    curl -H "Authorization: token ghp_123..." https://api.github.com/user
    ```

2. **Test repository access:**
    ```bash
    curl -H "Authorization: token ghp_123..." https://api.github.com/repos/YOUR_ORG/YOUR_REPO
    ```

3. **Test GitHub CLI (if using --use-gh-cli):**
    ```bash
    gh auth status
    gh repo view YOUR_ORG/YOUR_REPO
    ```

4. **Run dry-run migration:**
    ```bash
    python migrate_bitbucket_to_github.py --config config.json --dry-run
    ```

### After Authentication Issues

1. **Check token scopes and permissions**
2. **Verify repository access**
3. **Test with minimal operations first**
4. **Use dry-run modes to validate setup**
5. **Check the troubleshooting guides above**

---

## 🚀 Quick Start Commands

### Basic Setup (No Attachments)
```bash
# 1. Test Bitbucket token
python test_auth.py --workspace myteam --repo myrepo --email me@company.com --token ATAT123...

# 2. Run audit
python audit_bitbucket.py --workspace myteam --repo myrepo --email me@company.com --token ATAT123...

# 3. Test GitHub PAT
curl -H "Authorization: token ghp_456..." https://api.github.com/user

# 4. Run migration dry-run
python migrate_bitbucket_to_github.py --config config.json --dry-run
```

### Advanced Setup (With Auto-Upload)
```bash
# 1. Install and setup GitHub CLI
gh auth login

# 2. Test CLI authentication
gh auth status

# 3. Run migration with auto-upload
python migrate_bitbucket_to_github.py --config config.json --use-gh-cli
```

---

## 📋 Token Requirements Summary

| Feature | Bitbucket Token | GitHub PAT | GitHub CLI |
|---------|----------------|------------|------------|
| Repository audit | ✅ User-level, read access | ❌ | ❌ |
| Issue migration | ✅ User-level, read access | ✅ `repo` scope | ❌ |
| PR migration | ✅ User-level, read access | ✅ `repo` scope | ❌ |
| Attachment upload | ✅ User-level, read access | ✅ `repo` scope | ✅ Authenticated |
| User mapping | ✅ User-level, read access | ✅ `repo`, `user:email` | ❌ |

**Key Points:**

- Always use **user-level** Bitbucket API tokens (not Repository Access Tokens)
- GitHub PAT requires **`repo`** scope for full functionality
- GitHub CLI is **only needed** for automatic attachment uploads
- **Test authentication** before running migration scripts
- Use **dry-run modes** to validate your setup


