# Migration Configuration Reference

This file defines how the migration tool connects to Bitbucket and GitHub, and how user identities are mapped.

---

## 🔧 File Overview

`migration_config.json` is generated automatically when you run the audit script with `--generate-config`. You can edit it before running the actual migration.

```json
{
  "bitbucket": {
    "workspace": "myworkspace",
    "repo": "myrepo",
    "email": "you@example.com",
    "token": "ATAT..."
  },
  "github": {
    "owner": "your-github-username",
    "repo": "myrepo",
    "token": "ghp_..."
  },
  "user_mapping": {
    "Alice Smith": "alice-smith-gh",
    "Bob Jones": "bjones",
    "Unknown (deleted user)": null
  },
  "repository_mapping": {
    "workspace/other-repo": "github-owner/other-repo",
    "workspace/shared-lib": "shared-lib"
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
| `bitbucket.token`     | API token            | Use full-access token; see [API Tokens](api_tokens.md) |
| `github.owner`        | GitHub user/org name | Destination owner for repository                       |
| `github.repo`         | Repository name      | Destination repo name (must exist and be empty)        |
| `github.token`        | GitHub PAT           | Must include `repo` scope                              |
| `user_mapping`        | Mapping table        | Links Bitbucket display names to GitHub usernames      |
| `repository_mapping`  | Repository mapping   | Maps Bitbucket repositories to GitHub repositories for cross-repo link rewriting |

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

## 💡 Tips

* Use the audit report (`audit_report.md`) to find active users.
* Focus mapping on high-activity users.
* If unsure, set to `null` — the tool will still credit them by name in issue text.

---

