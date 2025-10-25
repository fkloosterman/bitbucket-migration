# Migration Configuration Reference

This file defines how the migration tool connects to Bitbucket and GitHub, and how user identities are mapped.

---

## 🔧 File Overview

`migration_config.json` is generated automatically when you run the audit script. You can edit it before running the actual migration.

```json
{
  "bitbucket": {
    "workspace": "myworkspace",
    "repo": "myrepo",
    "email": "you@example.com",
    "token": "SET_BITBUCKET_TOKEN_ENV_VAR"
  },
  "github": {
    "owner": "your-github-username",
    "repo": "myrepo",
    "token": "YOUR_GITHUB_TOKEN_HERE"
  },
  "user_mapping": {
    "Alice Smith": "alice-smith-gh",
    "Bob Jones": "bjones",
    "Unknown (deleted user)": null
  },
  "repository_mapping": {
    "workspace/other-repo": "github-owner/other-repo",
    "workspace/shared-lib": "shared-lib"
  },
  "issue_type_mapping": {
    "bug": "Bug",
    "task": "Task",
    "enhancement": "Feature Request"
  }
}
```

---

## 🔊 Key Fields

| Section               | Key                  | Description                                            |
| --------------------- | -------------------- | ------------------------------------------------------ |
| `bitbucket.workspace` | Workspace name       | Bitbucket Cloud workspace containing the repo          |
| `bitbucket.repo`      | Repository name      | Name of the Bitbucket repo                             |
| `bitbucket.email`     | Your Atlassian email | Required for API authentication                        |
| `bitbucket.token`     | API token            | Set via BITBUCKET_TOKEN env var or .env file; see [API Tokens](api_tokens.md) |
| `github.owner`        | GitHub user/org name | Destination owner for repository                       |
| `github.repo`         | Repository name      | Destination repo name (must exist and be empty)        |
| `github.token`        | GitHub PAT           | Set in config or via GITHUB_TOKEN env var; must include `repo` scope |
| `user_mapping`        | Mapping table        | Links Bitbucket display names to GitHub usernames      |
| `repository_mapping`  | Repository mapping   | Maps Bitbucket repositories to GitHub repositories for cross-repo link rewriting |
| `issue_type_mapping`  | Issue type mapping   | Maps Bitbucket issue types to GitHub issue types       |

---

## 🌍 Environment Variables

For security, tokens can be set via environment variables instead of in the config file. This prevents sensitive data from being stored in plain text.

### Supported Variables

| Variable              | Description                          | Required |
| --------------------- | ------------------------------------ | -------- |
| `BITBUCKET_TOKEN`     | Bitbucket API token                   | Yes      |
| `BITBUCKET_API_TOKEN` | Alternative Bitbucket API token       | Yes      |
| `GITHUB_TOKEN`        | GitHub Personal Access Token          | Yes      |
| `GITHUB_API_TOKEN`    | Alternative GitHub API token          | Yes      |

### Usage

1. Set the variables in your shell:
   ```bash
   export BITBUCKET_TOKEN="your_bitbucket_token"
   export GITHUB_TOKEN="your_github_token"
   ```

2. Or create a `.env` file in the project root:
   ```
   BITBUCKET_TOKEN=your_bitbucket_token
   GITHUB_TOKEN=your_github_token
   ```

3. The system will automatically load tokens from env vars if not present in the config file.

### Security Benefits

- Tokens are not stored in version control
- Easier to manage in CI/CD environments
- Reduces risk of accidental exposure

---


## 👥 User Mapping Rules

* If a Bitbucket user **does not** have a GitHub account, map to `null`.
* Deleted users can be represented as `"Unknown (deleted user)": null`.
* Use GitHub usernames, not emails.
* You can edit `user_mapping` manually or import from `user_mapping_template.txt`.

Example:

```json
"user_mapping": {
  "External Consultant": null,
  "Former Employee": null,
  "Alice": "alice-gh",
  "Bob": "bob-dev"
}
```

---

## Repository Mapping

This optional section allows automatic rewriting of cross-repository links when migrating multiple related repositories.

```json
"repository_mapping": {
  "workspace/other-repo": "github-owner/other-repo",
  "workspace/shared-lib": "shared-lib"
}
```

### Supported Link Types
- Repository home: `https://bitbucket.org/workspace/other-repo` → `[other-repo](github_url)`
- Issues: `https://bitbucket.org/workspace/other-repo/issues/42` → `[other-repo #42](github_url)` (numbers preserved)
- Source files: `https://bitbucket.org/workspace/other-repo/src/hash/file.cpp` → `[other-repo/file.cpp](github_url)`
- Commits: `https://bitbucket.org/workspace/other-repo/commits/abc123` → `[other-repo@abc123](github_url)`

### Not Supported
- Pull Requests (may become issues or be skipped, numbers not predictable)
- Downloads (use GitHub Releases instead)
- Wiki pages (migrate wiki separately)
- Images in repo storage (need manual download/upload)

If you don't specify a GitHub owner (e.g., "shared-lib"), it uses the same owner as the current repository.

All unmapped/unsafe cross-repo links appear in the "Unhandled Links" report.

---

## Issue Type Mapping

This optional section allows mapping Bitbucket issue types (kinds) to GitHub issue types. GitHub issue types are organization-specific and must be configured in your GitHub organization settings.

```json
"issue_type_mapping": {
  "bug": "Bug",
  "task": "Task",
  "enhancement": "Feature Request"
}
```

### How It Works
- The tool fetches available GitHub issue types for your organization.
- It applies your custom mappings first, then attempts automatic matching based on case-insensitive name similarity (e.g., "bug" → "Bug").
- If a Bitbucket issue type is not mapped, it falls back to using labels or no type.
- Mappings are case-insensitive for both Bitbucket and GitHub types.

### Requirements
- Only available for GitHub organizations (not personal repositories).
- GitHub issue types must be enabled and configured in your organization.
- If the specified GitHub type does not exist, the mapping is skipped with a warning.

### Tips
- Use the audit report (`audit_report.md`) to see all unique Bitbucket issue types.
- Map only the types you need; unmapped types will use fallback methods.
- Common mappings: "bug" → "Bug", "task" → "Task", "enhancement" → "Feature Request".

---

## 💡 Tips

* Use the audit report (`audit_report.md`) to find active users.
* Focus mapping on high-activity users.
* If unsure, set to `null` — the tool will still credit them by name in issue text.

---

