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
    "email": "you@example.com"
  },
  "github": {
    "owner": "your-github-username",
    "repo": "myrepo"
  },
  "user_mapping": {
    "Alice Smith": {
      "github": "alice-smith-gh",
      "bitbucket_username": "asmith",
      "display_name": "Alice Smith"
    },
    "Bob Jones": {
      "github": "bjones",
      "bitbucket_username": "bjones",
      "display_name": "Bob Jones"
    },
    "Unknown (deleted user)": null
  },
  "issue_type_mapping": {
    "bug": "Bug",
    "task": "Task",
    "enhancement": "Feature Request"
  },
  "skip_issues": false,
  "skip_prs": false,
  "skip_pr_as_issue": false,
  "use_gh_cli": false,
  "link_rewriting_config": {
    "enabled": true,
    "enable_notes": true,
    "enable_markdown_context_awareness": true,
    "note_templates": {
      "issue_link": " *(was [BB #{bb_num}]({bb_url}))*",
      "pr_link": " *(was [BB PR #{bb_num}]({bb_url}))*",
      "commit_link": " *(was [Bitbucket]({bb_url}))*",
      "branch_link": " *(was [Bitbucket]({bb_url}))*",
      "compare_link": " *(was [Bitbucket]({bb_url}))*",
      "repo_home_link": "",
      "cross_repo_link": " *(was [Bitbucket]({bb_url}))*",
      "short_issue_ref": " *(was BB `#{bb_num}`)*",
      "pr_ref": " *(was BB PR `#{bb_num}`)*",
      "mention": "",
      "default": " *(migrated link)*"
    }
  },
  "output_dir": ".",
  "cross_repo_mappings_file": "cross_repo_mappings.json"
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
| `user_mapping`        | Mapping table        | Links Bitbucket display names/usernames to GitHub usernames (enhanced format) |
| `issue_type_mapping`  | Issue type mapping   | Maps Bitbucket issue types to GitHub issue types       |
| `skip_issues`         | Skip issues          | Skip migrating issues if true                          |
| `skip_prs`            | Skip PRs             | Skip migrating pull requests if true                   |
| `skip_pr_as_issue`    | Skip PR→issue        | Skip migrating closed PRs as issues if true            |
| `use_gh_cli`          | Use GitHub CLI       | Use GitHub CLI for attachment uploads if true          |
| `link_rewriting_config` | Link rewriting       | Configuration for link rewriting behavior and templates |
| `output_dir`          | Output directory     | Directory for migration logs, reports, and attachments |
| `cross_repo_mappings_file` | Cross-repo mappings | Path to shared mappings file for multi-repo migrations |

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

The user mapping now supports an enhanced format that includes display names and Bitbucket usernames for better mapping accuracy.

### Simple Format (Legacy)
```json
"user_mapping": {
  "Alice Smith": "alice-github",
  "Bob Jones": "bjones",
  "External Consultant": null
}
```

### Enhanced Format (Recommended)
```json
"user_mapping": {
  "Alice Smith": {
    "github": "alice-github",
    "bitbucket_username": "asmith",
    "display_name": "Alice Smith"
  },
  "Bob Jones": {
    "github": "bjones",
    "bitbucket_username": "bjones",
    "display_name": "Bob Jones"
  },
  "External Contractor": null
}
```

### Mapping Rules
* If a Bitbucket user **does not** have a GitHub account, map to `null`.
* Deleted users can be represented as `"Unknown (deleted user)": null`.
* Use GitHub usernames, not emails.
* The enhanced format provides better accuracy for @mentions and display name resolution.
* Display names are used when users are mentioned by name in comments (not just @username).
* You can edit `user_mapping` manually or import from `user_mapping_template.txt`.

---

## Link Rewriting Configuration

This section controls how links are rewritten during migration, including templates for different link types and behavior settings.

```json
"link_rewriting_config": {
  "enabled": true,
  "enable_notes": true,
  "enable_markdown_context_awareness": true,
  "note_templates": {
    "issue_link": " *(was [BB #{bb_num}]({bb_url}))*",
    "pr_link": " *(was [BB PR #{bb_num}]({bb_url}))*",
    "commit_link": " *(was [Bitbucket]({bb_url}))*",
    "branch_link": " *(was [Bitbucket]({bb_url}))*",
    "compare_link": " *(was [Bitbucket]({bb_url}))*",
    "repo_home_link": "",
    "cross_repo_link": " *(was [Bitbucket]({bb_url}))*",
    "short_issue_ref": " *(was BB `#{bb_num}`)*",
    "pr_ref": " *(was BB PR `#{bb_num}`)*",
    "mention": "",
    "default": " *(migrated link)*"
  }
}
```

### Configuration Options
- `enabled`: Enable/disable link rewriting entirely
- `enable_notes`: Add explanatory notes to rewritten links
- `enable_markdown_context_awareness`: Handle links differently in markdown vs plain text
- `note_templates`: Custom templates for different link types using `{bb_num}`, `{bb_url}`, `{gh_url}` placeholders

### Supported Link Types
- **Issue/PR Links**: Full URLs to issues and pull requests
- **Commit Links**: Links to specific commits
- **Branch Links**: Links to branch commit history
- **Compare Links**: Links to commit comparisons
- **Repository Home**: Links to repository root pages
- **Cross-repo Links**: Links between different repositories
- **Short References**: `#123` (issues) and `PR #456` (pull requests)
- **@Mentions**: User mentions that get rewritten to GitHub usernames

## Cross-Repository Mappings

For multi-repository migrations, use a shared mappings file to handle cross-repository links.

```json
"cross_repo_mappings_file": "cross_repo_mappings.json"
```

This file contains mappings from Bitbucket repositories to their migrated GitHub locations, enabling proper link rewriting between repositories that haven't been migrated yet (deferred links).

### Phase 1 vs Phase 2 Migration
- **Phase 1**: Migrate repositories and save mappings to the shared file
- **Phase 2**: Update cross-repository links using the complete mappings

Use the `--update-links-only` flag for Phase 2 operations.

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

## Migration Control Options

These boolean flags control various aspects of the migration process:

```json
{
  "skip_issues": false,
  "skip_prs": false,
  "skip_pr_as_issue": false,
  "use_gh_cli": false
}
```

- `skip_issues`: Skip migrating issues entirely
- `skip_prs`: Skip migrating pull requests as PRs (but may still migrate as issues if `skip_pr_as_issue` is false)
- `skip_pr_as_issue`: Skip migrating closed/merged PRs as issues
- `use_gh_cli`: Use GitHub CLI for attachment uploads instead of API

## Output Directory

Specify where migration outputs (logs, reports, attachments) are stored:

```json
"output_dir": "myworkspace_myrepo"
```

- Defaults to `{workspace}_{repo}` format
- Created automatically if it doesn't exist
- Can be overridden with `--output-dir` CLI flag

## 💡 Tips

* Use the audit report (`audit_report.md`) to find active users.
* Focus mapping on high-activity users.
* If unsure, set to `null` — the tool will still credit them by name in issue text.
* For multi-repo migrations, use the same `cross_repo_mappings_file` across all repositories.
* Customize `note_templates` to match your organization's style preferences.

---

