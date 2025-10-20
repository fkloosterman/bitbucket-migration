# API Tokens Setup Guide

This page explains how to generate and manage the required API tokens for Bitbucket Cloud and GitHub.

---

## 🔑 Bitbucket Cloud API Token

1. Go to **Atlassian Account Settings → Security → Create and manage API tokens**.
2. Click **Create API token**.
3. Name it: `Migration Tool`.
4. Choose **Bitbucket** as the app.
5. Set **Full access** (or minimally: read repos, issues, PRs).
6. Copy the token immediately – it won’t be shown again.

**Example usage in config:**

```json
"bitbucket": {
  "email": "you@example.com",
  "token": "ATAT1234..."
}
```

---

## 🔑 GitHub Personal Access Token (PAT)

1. Go to **GitHub Settings → Developer settings → Personal access tokens (classic)**.
2. Click **Generate new token (classic)**.
3. Name it `Bitbucket Migration`.
4. Enable scope **`repo`** (full control of private repos).
5. Click **Generate token** and copy it.

**Example usage in config:**

```json
"github": {
  "owner": "my-org",
  "repo": "my-repo",
  "token": "ghp_abcd123..."
}
```

---

## 🔧 Token Security Best Practices

* Never commit tokens to Git.
* Store them in environment variables or a `.env` file.
* Rotate tokens after migration.
* Use **read-only** tokens where possible.
* Delete unused tokens once verified.

---

## 💡 Verification

Test your tokens before running the migration:

```bash
# Test Bitbucket token
curl -u you@example.com:ATAT1234... https://api.bitbucket.org/2.0/user

# Test GitHub PAT
token=ghp_abcd123...
curl -H "Authorization: token $token" https://api.github.com/user
```

If both commands return your user info, the tokens are valid.

---
