# Migration Configuration Reference

This file defines how the migration tool connects to Bitbucket and GitHub, and how user identities are mapped.

---

## 🔧 Configuration Format

The migration tool uses a unified configuration format (v2.0) that supports both single and multiple repository migrations.

**Key Features:**
- Single configuration format for all migration scenarios
- Required `"format_version": "2.0"` field
- Base directory management with standard subdirectories
- Options grouped in `options` object
- Template variable support (`{workspace}`, `{repo}`)

---

## 🔧 Configuration File

The configuration file is typically named `config.json` and lives at the root of your migration workspace.

```json
{
  "format_version": "2.0",
  "base_dir": "./migration_workspace",

  "bitbucket": {
    "workspace": "myworkspace",
    "email": "user@example.com",
    "token": "${BITBUCKET_TOKEN}"
  },

  "github": {
    "owner": "myorg",
    "token": "${GITHUB_TOKEN}"
  },

  "repositories": [
    {
      "bitbucket_repo": "repo1",
      "github_repo": "repo1"
    },
    {
      "bitbucket_repo": "repo2",
      "github_repo": "repo2-renamed"
    }
  ],

  "external_repositories": [
    {
      "bitbucket_repo": "shared-lib",
      "github_repo": "shared-lib",
      "github_owner": "other-org"
    }
  ],

  "options": {
    "skip_issues": false,
    "skip_prs": false,
    "skip_pr_as_issue": false
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

  "cross_repo_mappings_file": "cross_repo_mappings.json"
}
```

---

## 🔧 Configuration Fields

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `format_version` | string | **Must be "2.0"** - identifies the configuration format |
| `bitbucket.workspace` | string | Bitbucket Cloud workspace name |
| `bitbucket.email` | string | Your Atlassian email for API authentication |
| `github.owner` | string | GitHub user/org name for destination repositories |
| `repositories` | array | List of repositories to migrate |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `base_dir` | string | `"."` | Base directory for migration workspace |
| `bitbucket.token` | string | - | Bitbucket API token (or use BITBUCKET_TOKEN env var) |
| `github.token` | string | - | GitHub PAT (or use GITHUB_TOKEN env var) |
| `external_repositories` | array | `[]` | Repositories referenced but not migrated |
| `options` | object | `{}` | Migration control options |
| `user_mapping` | object | `{}` | Bitbucket to GitHub user mapping |
| `issue_type_mapping` | object | `{}` | Bitbucket issue types to GitHub issue types |
| `link_rewriting_config` | object | `{}` | Link rewriting behavior and templates |
| `cross_repo_mappings_file` | string | `"cross_repo_mappings.json"` | Path to shared mappings file |

### Repository Configuration

Each repository in the `repositories` array:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bitbucket_repo` | string | Yes | Name of the Bitbucket repository |
| `github_repo` | string | Yes | Name of the destination GitHub repository |

### External Repository Configuration

External repositories are referenced in links but not migrated:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bitbucket_repo` | string | Yes | Name of the Bitbucket repository |
| `github_repo` | string | No | Name of the GitHub repository (if null, links are preserved) |
| `github_owner` | string | No | GitHub owner/org (defaults to main config) |

### Options Configuration

Migration control options grouped in the `options` object:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `skip_issues` | boolean | `false` | Skip migrating issues |
| `skip_prs` | boolean | `false` | Skip migrating pull requests |
| `skip_pr_as_issue` | boolean | `false` | Skip migrating closed PRs as issues |

---

## 📁 Directory Structure

The migration tool uses a standardized directory structure based on the `base_dir` setting:

```
{base_dir}/                    # Base directory (defaults to ".")
├── config.json                # Configuration file
├── cross_repo_mappings.json   # Shared cross-repository mappings
├── audit/                     # Audit command outputs
│   └── {workspace}_{repo}/    # Per-repository audit results
├── dry-run/                   # Dry-run command outputs
│   └── {workspace}_{repo}/    # Per-repository dry-run results
└── migrate/                   # Migration command outputs
    └── {workspace}_{repo}/    # Per-repository migration results
```

**Key Points:**
- Config file lives at `{base_dir}/config.json`
- Each subcommand creates its own subdirectory
- Outputs are organized by workspace and repository
- Cross-repository mappings file is shared at the base level

---

## 🔧 Configuration Validation

The tool validates configurations and provides clear error messages:

### Format Version Validation
```bash
Error: Unsupported config format. Expected version 2.0, got 1.0.
See docs/reference/migration_config.md for current format.
```

### Required Fields Validation
```bash
Error: Config must have 'repositories' array.
See docs/reference/migration_config.md for format.
```

### Legacy Format Detection
```bash
Error: Invalid config: 'repo' field not allowed in bitbucket/github sections.
Use 'repositories' array instead.
```

### Troubleshooting
- **"format_version must be 2.0"**: Update your config to use the v2.0 format
- **"'repositories' array required"**: Convert from per-repo format to unified format
- **"'repo' field not allowed"**: Remove `repo` fields from `bitbucket`/`github` sections

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

Use the `cross-link` subcommand for Phase 2 operations.

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
  "skip_pr_as_issue": false
}
```

- `skip_issues`: Skip migrating issues entirely
- `skip_prs`: Skip migrating pull requests as PRs (but may still migrate as issues if `skip_pr_as_issue` is false)
- `skip_pr_as_issue`: Skip migrating closed/merged PRs as issues

## 📋 Migration Workflow

### Phase 0: Setup and Audit

1. **Create unified config** with `format_version: "2.0"`
2. **Run audit** to analyze repositories and generate user mappings
3. **Review and edit** the config file with correct user mappings

### Phase 1: Migrate Repositories

1. **Migrate repositories** one by one or all at once
2. **Cross-repo mappings** are automatically saved to `cross_repo_mappings.json`
3. **Links within migrated repos** are rewritten immediately

### Phase 2: Update Cross-Repository Links

1. **Run `migrate_bitbucket_to_github cross-link`** to rewrite deferred cross-repo links
2. **All repositories** use the complete mappings file for accurate link rewriting

### Directory Organization

The tool automatically organizes outputs in standardized subdirectories:

- **Audit outputs**: `{base_dir}/audit/{workspace}_{repo}/`
- **Dry-run outputs**: `{base_dir}/dry-run/{workspace}_{repo}/`
- **Migration outputs**: `{base_dir}/migrate/{workspace}_{repo}/`

No manual `output_dir` configuration needed - the tool handles this automatically.

## 💡 Tips

* Use the audit report (`audit_report.md`) to find active users and issue types.
* Focus mapping on high-activity users first.
* If unsure about a user mapping, set to `null` — the tool will still credit them by name.
* For multi-repo migrations, the `cross_repo_mappings_file` is automatically managed.
* Customize `note_templates` to match your organization's style preferences.
* The `format_version: "2.0"` field is required for all new configurations.
* Use environment variables for tokens instead of storing them in the config file.
* External repositories help with accurate cross-repo link rewriting.

---

