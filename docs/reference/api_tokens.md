# API Tokens Setup Guide

This comprehensive guide explains all authentication requirements for the Bitbucket to GitHub migration tools, including the audit script and migration script.

---

## 🔑 Authentication Overview

The migration process requires multiple authentication methods depending on which tools you use:

| Tool | Bitbucket Token | GitHub PAT | Purpose |
|------|----------------|------------|---------|
| `migrate_bitbucket_to_github test-auth` | ✅ Required | ✅ Required | Test authentication |
| `migrate_bitbucket_to_github audit` | ✅ Required | ❌ Not needed | Audit repository content |
| `migrate_bitbucket_to_github migrate --dry-run` | ✅ Required | ✅ Required | Dry-run migrate issues/PRs |
| `migrate_bitbucket_to_github migrate` | ✅ Required | ✅ Required | Migrate issues/PRs |
| `migrate_bitbucket_to_github cross-link` | ✅ Required | ✅ Required | Post-migration link updates |

**What you need:**

- **Migration:** Bitbucket API Token + GitHub PAT
- **Post-Migration:** Bitbucket API Token + GitHub PAT (for cross-repository link updates)

---

## 🔑 Bitbucket Cloud API Token

**Required for:** `migrate_bitbucket_to_github audit`, `migrate_bitbucket_to_github migrate`

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
  "workspace": "your-workspace",
  "email": "you@example.com",
  "token": "SET_BITBUCKET_TOKEN_ENV_VAR"
}
```

**Note:** Tokens are no longer stored in config files. Set them via environment variables instead.

---

## 🔑 GitHub Authentication

**Required for:** `migrate_bitbucket_to_github dry-run` and `migrate_bitbucket_to_github migrate`

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
  "token": "YOUR_GITHUB_TOKEN_HERE"
}
```

**Note:** Tokens are no longer stored in config files. Set them via environment variables instead.

---

## 🔧 Token Security Best Practices

### Environment Variables (Recommended)

```bash
# Create .env file
BITBUCKET_TOKEN=ATAT1234...
GITHUB_TOKEN=ghp_abcd123...

# Or set in shell
export BITBUCKET_TOKEN="ATAT1234..."
export GITHUB_TOKEN="ghp_abcd123..."

# Run scripts (tokens loaded automatically from env vars or .env)
migrate_bitbucket_to_github audit --workspace YOUR_WORKSPACE --repo YOUR_REPO --email you@example.com
```

### Security Guidelines

* **Never commit tokens** to Git repositories
* **Use environment variables** or .env files for token storage (recommended)
* **Use read-only tokens** where possible (audit script only needs read access)
* **Rotate tokens regularly** (especially after migration completion)
* **Use separate tokens** for different purposes (audit vs migration)
* **Delete unused tokens** once migration is verified
* **Store securely** in password managers or secure credential storage
* **Secure or remove** any token files like bitbucket_api_token.txt

### Token Permissions Matrix

| Operation | Bitbucket Token | GitHub PAT |
|-----------|----------------|------------|
| Repository audit | Read access | Not needed |
| Issue migration | Read access | Repo access |
| PR migration | Read access | Repo access |
| Attachment upload | Read access | Repo access |
| Cross-repo link updates | Read access | Repo access |

---

## ✅ Authentication Testing

### Test Bitbucket Authentication

Use the provided test script to verify your Bitbucket token:

```bash
migrate_bitbucket_to_github test-auth --workspace YOUR_WORKSPACE --repo YOUR_REPO --email you@example.com --gh-owner YOUR_GITHUB_OWNER --gh-repo YOUR_GITHUB_REPO
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
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# Test repository access
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/repos/YOUR_ORG/YOUR_REPO

# Test issue creation (dry run)
curl -X POST -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/YOUR_ORG/YOUR_REPO/issues \
  -d '{"title":"Test Issue","body":"Testing authentication"}'
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


---

## 💡 Verification Workflow

### Before Running Audit Script

1. **Set environment variables:**
    ```bash
    export BITBUCKET_TOKEN="ATAT1234..."
    ```

2. **Test Bitbucket authentication:**
    ```bash
    migrate_bitbucket_to_github test-auth --workspace YOUR_WORKSPACE --repo YOUR_REPO --email you@example.com
    ```

3. **Verify repository access:**
    ```bash
    curl -u you@example.com:$BITBUCKET_TOKEN https://api.bitbucket.org/2.0/repositories/YOUR_WORKSPACE/YOUR_REPO
    ```

4. **Run audit script:**
    ```bash
    migrate_bitbucket_to_github audit --workspace YOUR_WORKSPACE --repo YOUR_REPO --email you@example.com
    ```

### Before Running Migration Script

1. **Set environment variables:**
    ```bash
    export BITBUCKET_TOKEN="ATAT123..."
    export GITHUB_TOKEN="ghp_123..."
    ```

2. **Test authentication:**
    ```bash
    migrate_bitbucket_to_github test-auth --workspace YOUR_WORKSPACE --repo YOUR_REPO --email you@example.com --gh-owner YOUR_ORG --gh-repo YOUR_REPO
    ```

3. **Run dry-run migration:**
    ```bash
    migrate_bitbucket_to_github migrate --config config.json --dry-run
    ```

### After Authentication Issues

1. **Check token scopes and permissions**
2. **Verify repository access**
3. **Test with minimal operations first**
4. **Use dry-run modes to validate setup**
5. **Check the troubleshooting guides above**

---

## 🚀 Quick Start Commands

### Basic Setup
```bash
# 1. Set environment variables
export BITBUCKET_TOKEN="ATAT123..."
export GITHUB_TOKEN="ghp_456..."

# 2. Test authentication
migrate_bitbucket_to_github test-auth --workspace myteam --repo myrepo --email me@company.com --gh-owner myorg --gh-repo myrepo

# 3. Run audit
migrate_bitbucket_to_github audit --workspace myteam --repo myrepo --email me@company.com --gh-owner myorg

# 4. Run migration dry-run
migrate_bitbucket_to_github migrate --config config.json --dry-run

# 5. Run full migration
migrate_bitbucket_to_github migrate --config config.json

# 6. Update cross-repository links (post-migration)
migrate_bitbucket_to_github cross-link --config config.json
```

---

## 📋 Token Requirements Summary
| Feature | Bitbucket Token | GitHub PAT |
|---------|----------------|------------|
| Repository audit | ✅ User-level, read access | ❌ |
| Issue migration | ✅ User-level, read access | ✅ `repo` scope |
| PR migration | ✅ User-level, read access | ✅ `repo` scope |
| Attachment upload | ✅ User-level, read access | ✅ `repo` scope |
| Cross-repo link updates | ✅ User-level, read access | ✅ `repo` scope |
| User mapping | ✅ User-level, read access | ✅ `repo`, `user:email` |

**Key Points:**

- Always use **user-level** Bitbucket API tokens (not Repository Access Tokens)
- GitHub PAT requires **`repo`** scope for full functionality
- **Test authentication** before running migration scripts
- Use **dry-run modes** to validate your setup
- Attachments require **manual upload** due to GitHub API limitations


