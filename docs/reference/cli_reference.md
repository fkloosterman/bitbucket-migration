# CLI Reference Guide

This comprehensive guide covers the command-line interface for the unified migration tool `migrate_bitbucket_to_github`, which includes subcommands for authentication testing, repository auditing, and data migration. All functionality is integrated into a single script with subcommands for a streamlined workflow.

---

## 📋 Subcommand Overview

| Subcommand | Purpose | When to Use |
|------------|---------|-------------|
| test-auth | Authentication testing | Before audit to verify API access |
| audit | Repository analysis | Before migration to understand scope |
| dry-run | Simulate migration | To validate setup without making changes |
| migrate | Data migration | After audit and preparation |
| clean | Remove output files | After migration to clean up generated files |


---

## 🔐 Authentication Testing: `test-auth` Subcommand

Tests Bitbucket and GitHub API authentication and permissions before running the audit.

### Basic Syntax
```bash
migrate_bitbucket_to_github test-auth --workspace WORKSPACE --repo REPO --email EMAIL [OPTIONS]
```

### Arguments
**Note**: missing arguments will be prompted if not provided.
| Argument | Description | Example |
|----------|-------------|---------|
| `--workspace` | Bitbucket workspace name | `myteam` |
| `--repo` | Repository name | `myproject` |
| `--email` | Atlassian account email | `user@example.com` |
| `--token` | Bitbucket API token | `ATAT123...` |
| `--gh-owner` | GitHub owner | `myusername` |
| `--gh-repo` | GitHub repository name | `myproject` |
| `--gh-token` | GitHub API token | `ghp_...` |


### Examples

#### Simple Authentication Test
```bash
# Tokens will be prompted interactively
migrate_bitbucket_to_github test-auth --workspace myteam --repo myproject --email user@example.com --gh-owner myusername --gh-repo myproject
```

#### Authentication Test with Tokens
```bash
migrate_bitbucket_to_github test-auth --workspace myteam --repo myproject \
  --email user@example.com \
  --token ATAT1234567890abcdef \
  --gh-owner myusername \
  --gh-repo myproject \
  --gh-token ghp_1234567890abcdef
```

#### Batch Testing Multiple Repositories
```bash
# Test multiple repos in the same workspace
for repo in repo1 repo2 repo3; do
  migrate_bitbucket_to_github test-auth --workspace myteam --repo $repo --email user@example.com --token $TOKEN --gh-owner myusername --gh-repo $repo --gh-token $GH_TOKEN
done
```

### What It Tests

- ✅ Repository access and metadata
- ✅ Issues API permissions
- ✅ Pull requests API access
- ✅ Authentication credentials validity

### Expected Output
```
Testing Bitbucket API Authentication
============================================================
Workspace: myteam
Repository: myproject
Email: user@example.com
Using user-level API Token authentication
============================================================

Test 1/3: Repository Info
  Verify repository access
  URL: https://api.bitbucket.org/2.0/repositories/myteam/myproject
  ✅ SUCCESS (200 OK)
     Repository: myproject

Test 2/3: Issues List
  Verify issues API access
  URL: https://api.bitbucket.org/2.0/repositories/myteam/myproject/issues
  ✅ SUCCESS (200 OK)
     Found 42 items

Test 3/3: Pull Requests List
  Verify pull requests API access
  URL: https://api.bitbucket.org/2.0/repositories/myteam/myproject/pullrequests
  ✅ SUCCESS (200 OK)
     Found 18 items

============================================================
✅ All tests passed! Your API Token is working correctly.
You can now run the full audit script.
============================================================
```

---

## 🔍 Repository Audit: `audit` Subcommand

Performs comprehensive analysis of Bitbucket repository content for migration planning.

### Basic Syntax
```bash
migrate_bitbucket_to_github audit --workspace WORKSPACE --repo REPO --email EMAIL [OPTIONS]
```

### Required Arguments
| Argument | Description | Example |
|----------|-------------|---------|
| `--workspace` | Bitbucket workspace name | `myteam` |
| `--repo` | Repository name | `myproject` |
| `--email` | Atlassian account email | `user@example.com` |
| `--token` | API token (prompts if not provided) | `ATAT123...` |

### Optional Arguments
| Argument | Description | Example |
|----------|-------------|---------|
| `--no-config` | Do not generate migration configuration template (default is to generate) | |
| `--gh-owner` | GitHub username/org for config template | `myusername` |
| `--gh-repo` | GitHub repository name for config template | `myproject` |
| `--output-dir` | Output directory for audit files (reports, data files). Defaults to <workspace>_<repo> folder in current directory. | `myworkspace_myrepo` |
| `--debug` | Enable debug logging | |

**Note:** Missing required arguments will be prompted for interactively.

### Examples

#### Basic Repository Audit
```bash
# Token will be prompted interactively
migrate_bitbucket_to_github audit --workspace myteam --repo myproject --email user@example.com
```

#### Audit with Token Provided
```bash
migrate_bitbucket_to_github audit --workspace myteam --repo myproject \
  --email user@example.com \
  --token ATAT1234567890abcdef
```

#### Generate Migration Configuration
```bash
migrate_bitbucket_to_github audit --workspace myteam --repo myproject \
  --email user@example.com \
  --gh-owner mygithubusername \
  --gh-repo myproject
```

#### Automated Audit Pipeline
```bash
#!/bin/bash
# audit_and_config.sh - Automated audit for multiple repositories

WORKSPACE="myteam"
EMAIL="user@example.com"
TOKEN="ATAT123..."

for repo in $(cat repos_to_migrate.txt); do
  echo "Auditing $repo..."
  migrate_bitbucket_to_github audit \
    --workspace $WORKSPACE \
    --repo $repo \
    --email $EMAIL \
    --token $TOKEN \
    --gh-owner mygithubusername \
    --gh-repo $repo

  echo "Audit complete for $repo"
  echo "Configuration saved to migration_config.json"
  echo "Edit user mappings before running migration"
  echo "---"
done
```

### Generated Files

#### `bitbucket_audit_report.json`
Complete audit data in JSON format containing:

- Issue and PR counts, states, and gaps
- User activity analysis
- Attachment inventory with sizes
- Milestone and label usage
- Migration time estimates

#### `audit_report.md`
Human-readable markdown report with:

- Executive summary
- Detailed issue/PR analysis
- User activity breakdown
- Migration estimates
- Next steps and recommendations

#### `migration_config.json`
Migration configuration template with:

- Pre-filled Bitbucket credentials
- User mapping template
- GitHub repository settings

#### `user_mapping_template.txt`
User mapping reference showing:

- All users found in repository
- Activity counts for each user
- Multiple mapping format examples

### Audit Output Example
```
================================================================================
BITBUCKET MIGRATION AUDIT REPORT
Repository: myteam/myproject
Audit Date: 2024-01-15T10:30:45
================================================================================

📋 ISSUES
  Total Issues: 156
  States: {'open': 23, 'closed': 133}
  Number Range: #1 - #200
  Number Gaps: 44 missing issue numbers
  Total Comments: 892
  Issues with Attachments: 12

🔀 PULL REQUESTS
  Total PRs: 89
  States: {'OPEN': 5, 'MERGED': 78, 'DECLINED': 6}
  Number Range: #1 - #95
  Number Gaps: 6 missing PR numbers
  Total Comments: 445

📎 ATTACHMENTS
  Total Files: 28
  Total Size: 45.2 MB

👥 USERS
  Unique Users: 34

🏷️  MILESTONES
  Total: 8

📊 MIGRATION ESTIMATES
  Placeholder Issues Needed: 44
  Estimated API Calls: ~850
  Estimated Time: ~14 minutes

================================================================================
Report saved to: bitbucket_audit_report.json
================================================================================
```

---

## 🔄 Dry Run: `dry-run` Subcommand

Simulates the migration process without making any changes to GitHub. This is the recommended first step after audit to validate your configuration and setup.

### Basic Syntax
```bash
migrate_bitbucket_to_github dry-run --config CONFIG_FILE [OPTIONS]
```

### Required Arguments
| Argument | Description | Example |
|----------|-------------|---------|
| `--config` | Path to configuration JSON file | `migration_config.json` |

### Optional Arguments

**Note:** Missing required arguments will be prompted for interactively.

| Argument | Description | Example |
|----------|-------------|---------|
| `--skip-issues` | Skip issue migration phase |
| `--skip-prs` | Skip pull request migration phase |
| `--skip-pr-as-issue` | Skip migrating closed PRs as issues |
| `--use-gh-cli` | Auto-upload attachments using GitHub CLI |

### Examples

#### Basic Dry Run (Recommended First Step)
```bash
migrate_bitbucket_to_github dry-run --config migration_config.json
```

#### Dry Run with Selective Options
```bash
migrate_bitbucket_to_github dry-run --config migration_config.json \
  --skip-pr-as-issue \
  --use-gh-cli
```

#### Dry Run for Issues Only
```bash
migrate_bitbucket_to_github dry-run --config migration_config.json --skip-prs
```

### What It Does

- ✅ Fetches all issues and PRs from Bitbucket (read-only)
- ✅ Checks if branches exist on GitHub
- ✅ Downloads attachments to local folder
- ✅ Validates user mappings
- ✅ Shows exactly which PRs become GitHub PRs vs Issues
- ✅ Generates simulated GitHub issue/PR numbers
- ✅ Creates comprehensive dry-run report

### What It Doesn't Do

- ✗ No issues created on GitHub
- ✗ No PRs created on GitHub
- ✗ No comments added to GitHub
- ✗ No labels applied

### Generated Files

#### `migration_dry_run_log.txt`
Log file containing detailed execution information and any warnings.

#### `migration_report_dry_run.md`
Comprehensive markdown report with:
- Simulated migration statistics
- Detailed issue/PR migration tables
- User mapping validation results
- Attachment handling summary
- Link rewriting analysis
- Troubleshooting recommendations

#### `migration_mapping_partial.json`
Partial mapping file showing simulated Bitbucket → GitHub number mappings.

#### `attachments_temp/`
Directory containing downloaded attachments for review (no uploads occur).

### Dry Run Output Example
```
🔍 DRY RUN MODE ENABLED
This is a simulation - NO changes will be made to GitHub

What WILL happen (read-only):
  ✓ Fetch all issues and PRs from Bitbucket
  ✓ Check if branches exist on GitHub
  ✓ Download attachments to local folder
  ✓ Validate user mappings
  ✓ Show exactly which PRs become GitHub PRs vs Issues

What WON'T happen (no writes):
  ✗ No issues created on GitHub
  ✗ No PRs created on GitHub
  ✗ No comments added to GitHub
  ✗ No labels applied

Use this to verify:
  • Bitbucket connection works
  • GitHub connection works (read-only check)
  • User mappings are correct
  • Branch existence (actual check)
  • PR migration strategy (which become PRs vs issues)
  • Exact GitHub issue/PR numbers that will be created

After successful dry-run, use migrate subcommand to perform actual migration
```

---

## 🚀 Data Migration: `migrate` Subcommand

Migrates repository data from Bitbucket to GitHub with intelligent handling of different content types.

### Basic Syntax
```bash
migrate_bitbucket_to_github migrate --config CONFIG_FILE [OPTIONS]
```

### Required Arguments
| Argument | Description | Example |
|----------|-------------|---------|
| `--config` | Path to configuration JSON file | `migration_config.json` |

### Optional Arguments

**Note:** Missing required arguments will be prompted for interactively.

| Argument | Description | Example |
|----------|-------------|---------|
| `--skip-issues` | Skip issue migration phase |
| `--skip-prs` | Skip pull request migration phase |
| `--skip-pr-as-issue` | Skip migrating closed PRs as issues |
| `--use-gh-cli` | Auto-upload attachments using GitHub CLI |
| `--output-dir` | Directory for migration output files (logs, reports, attachments). Defaults to <workspace>_<repo> folder in current directory | `myworkspace_myrepo` |
| `--cross-repo-mappings` | Path to shared cross-repository mappings file (JSON). Used for rewriting cross-repo links. | `cross_repo_mappings.json` |
| `--update-links-only` | Phase 2 mode: Update cross-repository links only (assumes migration already complete) | |
| `--debug` | Enable debug logging | |
| `--output-dir` | Directory for migration output files (logs, reports, attachments). Defaults to <workspace>_<repo> folder in current directory | `myworkspace_myrepo` |
| `--cross-repo-mappings` | Path to shared cross-repository mappings file (JSON). Used for rewriting cross-repo links. | `cross_repo_mappings.json` |
| `--update-links-only` | Phase 2 mode: Update cross-repository links only (assumes migration already complete) | |
| `--debug` | Enable debug logging | |

### Examples

#### Full Migration (Basic)
```bash
migrate_bitbucket_to_github --config migration_config.json
```

#### Issues Only Migration
```bash
migrate_bitbucket_to_github --config migration_config.json --skip-prs
```

#### Pull Requests Only Migration
```bash
migrate_bitbucket_to_github --config migration_config.json --skip-issues
```

#### Migration with Automatic Attachment Upload
```bash
# Requires GitHub CLI installed and authenticated
migrate_bitbucket_to_github --config migration_config.json --use-gh-cli
```

#### Advanced Migration with Selective Options
```bash
migrate_bitbucket_to_github --config migration_config.json \
  --skip-pr-as-issue \
  --use-gh-cli
```

#### Batch Migration Script
```bash
#!/bin/bash
# migrate_multiple.sh - Migrate multiple repositories

CONFIG_DIR="./configs"
ATTACHMENTS_DIR="./attachments_temp"

for config in $CONFIG_DIR/*.json; do
  repo_name=$(basename "$config" .json)
  echo "Migrating $repo_name..."

  # Create separate attachments directory for each repo
  mkdir -p "$ATTACHMENTS_DIR/$repo_name"

  # Run migration with auto-upload
  migrate_bitbucket_to_github \
    --config "$config" \
    --use-gh-cli

  echo "Migration complete for $repo_name"
  echo "Attachments: $ATTACHMENTS_DIR/$repo_name/"
  echo "---"
done
```

### Migration Strategy

#### Issues Migration
- All Bitbucket issues become GitHub issues
- Original numbering preserved with placeholders for gaps
- Comments and attachments migrated
- Assignees and labels preserved where possible

#### Pull Requests Migration
- **OPEN PRs with existing branches** → GitHub PRs (if branches exist on GitHub)
- **OPEN PRs with missing branches** → GitHub Issues
- **MERGED/DECLINED/SUPERSEDED PRs** → GitHub Issues (safest approach)

#### Link Rewriting
- Cross-references between issues/PRs automatically updated
- GitHub links become primary, Bitbucket references preserved
- Format: `[#123](github_url) *(was [BB #123](bitbucket_url))*`

### Generated Files

#### `migration_mapping.json`
Machine-readable mapping of Bitbucket → GitHub numbers:
```json
{
  "bitbucket": {
    "workspace": "myteam",
    "repo": "myproject"
  },
  "github": {
    "owner": "myusername",
    "repo": "myproject"
  },
  "issue_mapping": {
    "1": 5,
    "2": 6,
    "3": 8
  },
  "pr_mapping": {
    "1": 7,
    "2": 9
  }
}
```

#### `migration_report.md`
Comprehensive markdown report with:

- Migration statistics and timing
- Detailed issue/PR migration tables
- User mapping summary
- Unhandled links and unmapped mentions
- Troubleshooting notes

#### `attachments_temp/`
Directory containing downloaded attachments for manual upload (unless using `--use-gh-cli`).

---

## 🧹 Cleanup: `clean` Subcommand

Removes output files generated by audit, dry-run, and migrate subcommands. Useful for cleaning up after migration or starting fresh.

### Basic Syntax
```bash
migrate_bitbucket_to_github clean [OPTIONS]
```

### Optional Arguments
| Argument | Description | Example |
|----------|-------------|---------|
| `--all` | Remove all outputs including the configuration file | |
| `--output-dir` | Clean specific output directory (default: current directory). Use this to clean outputs from a specific repository migration. | `myworkspace_myrepo` |
| `--workspace` | Bitbucket workspace name - used to find default output directory | `myworkspace` |
| `--repo` | Repository name - used to find default output directory | `myrepo` |

### Examples

#### Clean Output Files (Keep Config)
```bash
# Remove all generated files except migration_config.json
migrate_bitbucket_to_github clean
```

#### Clean All Files (Including Config)
```bash
# Remove everything including configuration
migrate_bitbucket_to_github clean --all
```

#### Cleanup After Migration
```bash
# After successful migration and verification
migrate_bitbucket_to_github clean

# Or if you want to start completely fresh
migrate_bitbucket_to_github clean --all
```

### What It Removes

#### Default Mode (without `--all`)
- `bitbucket_audit_report.json`
- `bitbucket_audit_report.md`
- `bitbucket_issues_detail.json`
- `bitbucket_prs_detail.json`
- `migration_log.txt`
- `migration_dry_run_log.txt`
- `migration_mapping.json`
- `migration_report.md`
- `migration_report_dry_run.md`
- `migration_mapping_partial.json`
- `attachments_temp/` (directory)

#### With `--all` Flag
- All of the above **plus**:
- `migration_config.json`

### Expected Output
```
🧹 Cleaning output files (keeping configuration)...
  ✓ Removed bitbucket_audit_report.json
  ✓ Removed migration_report.md
  ✓ Removed directory attachments_temp
  - migration_config.json not found (already clean)
✅ Clean completed!
```

---

## 🔄 Recommended Workflow

### Phase 1: Preparation and Testing
```bash
# 1. Test authentication
migrate_bitbucket_to_github test-auth --workspace myteam --repo myproject --email user@example.com --gh-owner mygithubusername --gh-repo myproject

# 2. Run comprehensive audit
migrate_bitbucket_to_github audit --workspace myteam --repo myproject \
  --email user@example.com \
  --gh-owner mygithubusername \
  --gh-repo myproject

# 3. Review audit results
cat audit_report.md
ls -la bitbucket_*.json

# 4. Edit configuration
vim migration_config.json
vim user_mapping_template.txt
```

### Phase 2: Pre-Migration Validation
```bash
# 5. Test migration setup (dry run)
migrate_bitbucket_to_github dry-run --config migration_config.json

# 6. Review dry-run results
cat migration_report_dry_run.md

# 7. Fix any issues found in dry run
# - Update user mappings
# - Check GitHub repository exists and is empty
# - Verify git history is pushed
```

### Phase 3: Actual Migration
```bash
# 8. Run the migration
migrate_bitbucket_to_github --config migration_config.json

# 9. Review migration results
cat migration_report.md

# 10. Handle attachments (if not using --use-gh-cli)
# Manually upload files from attachments_temp/ to GitHub issues
```

### Phase 4: Post-Migration Verification
```bash
# 11. Verify migration completeness
ls -la migration_*.json migration_*.md

# 12. Check for unmapped mentions or unhandled links
grep -n "Unmapped\|Unhandled" migration_report.md

# 13. Clean up (after verification)
migrate_bitbucket_to_github clean
# Or for complete cleanup: migrate_bitbucket_to_github clean --all
```

---

## 🛠️ Common Use Cases

### Use Case 1: Simple Repository Migration
```bash
# For straightforward migrations with minimal attachments
migrate_bitbucket_to_github test-auth --workspace myteam --repo myproject --email user@example.com --gh-owner myuser --gh-repo myproject
migrate_bitbucket_to_github audit --workspace myteam --repo myproject --email user@example.com --gh-owner myuser --gh-repo myproject
migrate_bitbucket_to_github dry-run --config migration_config.json
migrate_bitbucket_to_github migrate --config migration_config.json
```

### Use Case 2: Large Repository with Many Attachments
```bash
# For repositories with many/large attachments
migrate_bitbucket_to_github test-auth --workspace myteam --repo large-repo --email user@example.com --gh-owner myuser --gh-repo large-repo
migrate_bitbucket_to_github audit --workspace myteam --repo large-repo --email user@example.com --gh-owner myuser --gh-repo large-repo

# Install and setup GitHub CLI for auto-upload
gh auth login

# Run migration with auto-upload
migrate_bitbucket_to_github migrate --config migration_config.json --use-gh-cli
```

### Use Case 3: Issues-Only Migration
```bash
# When you only want to migrate issues, not PRs
migrate_bitbucket_to_github test-auth --workspace myteam --repo issues-only --email user@example.com --gh-owner myuser --gh-repo issues-only
migrate_bitbucket_to_github audit --workspace myteam --repo issues-only --email user@example.com --gh-owner myuser --gh-repo issues-only
migrate_bitbucket_to_github migrate --config migration_config.json --skip-prs
```

### Use Case 4: Enterprise Migration with Multiple Repositories
```bash
#!/bin/bash
# enterprise_migration.sh

ORG="myenterprise"
EMAIL="admin@company.com"
GH_ORG="myenterprise"

# Migrate all repositories
for repo in $(cat repo_list.txt); do
  echo "Migrating $ORG/$repo..."

  # Test and audit
  migrate_bitbucket_to_github test-auth --workspace $ORG --repo $repo --email $EMAIL --gh-owner $GH_ORG --gh-repo $repo
  migrate_bitbucket_to_github audit --workspace $ORG --repo $repo --email $EMAIL --gh-owner $GH_ORG --gh-repo $repo

  # Edit configuration with enterprise settings
  # ... manual step: edit migration_config.json ...

  # Migrate
  migrate_bitbucket_to_github migrate --config migration_config.json --use-gh-cli

  echo "Completed migration for $repo"
done
```

---

## 🔧 Troubleshooting CLI Issues

### Authentication Problems
```bash
# Always test authentication first
migrate_bitbucket_to_github test-auth --workspace WORKSPACE --repo REPO --email EMAIL --gh-owner GH_OWNER --gh-repo REPO --token TOKEN --gh-token GH_TOKEN

# If GitHub authentication fails
curl -H "Authorization: token ghp_..." https://api.github.com/user
```

### Permission Issues
```bash
# Check if your token has the right permissions
# Bitbucket: Test with a simple API call
curl -u EMAIL:TOKEN https://api.bitbucket.org/2.0/user

# GitHub: Check repository access
curl -H "Authorization: token ghp_..." https://api.github.com/repos/OWNER/REPO
```

### Large Repository Handling
```bash
# For large repositories, run phases separately
migrate_bitbucket_to_github migrate --config config.json --skip-prs    # Issues only
migrate_bitbucket_to_github migrate --config config.json --skip-issues  # PRs only
```

### Network and Timeout Issues
```bash
# The scripts handle rate limiting automatically, but for very slow connections:
# - Run during off-peak hours
# - Use dry-run subcommand first to estimate timing
# - Consider running audit and migration separately
```

---

## 📚 Related Documentation

| Topic | Reference | Description |
|-------|-----------|-------------|
| API Tokens | [`api_tokens.md`](api_tokens.md) | Complete authentication setup guide |
| Configuration | [`migration_config.md`](migration_config.md) | Configuration file format and options |
| User Mapping | [`user_mapping.md`](user_mapping.md) | User mapping strategies and formats |
| Migration Guide | [`../migration_guide.md`](../migration_guide.md) | Step-by-step migration instructions with troubleshooting |

---

## 💡 Tips and Best Practices

### CLI Efficiency
- Use `dry-run` subcommand first to validate your setup
- Run scripts during off-peak hours for large repositories
- Use `--use-gh-cli` for repositories with many attachments
- Keep the `attachments_temp/` directory until migration is verified

### Error Recovery
- Scripts save partial results if interrupted (Ctrl+C)
- Check the generated reports for unmapped users or unhandled links
- Use the mapping files to track what has been migrated

### Maintenance
- Keep API tokens secure and rotate them regularly
- Archive audit and migration reports for compliance
- Use `migrate_bitbucket_to_github clean` to remove generated files after migration
- Clean up `attachments_temp/` after successful migration (or let the clean command handle it)

### Performance Optimization
- Run audit script first to understand repository size
- Use `--skip-pr-as-issue` for repositories where closed PR metadata isn't needed
- Consider migrating issues and PRs separately for very large repositories

---

## 🔍 Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Migration completed successfully |
| 1 | Error | Check error messages and fix issues |

For detailed error information, check:
- Console output for immediate errors
- Generated report files for warnings
- Log messages for troubleshooting details

---

*This CLI reference focuses on the unified migration tool with subcommands. For complete migration instructions, see the [Migration Guide](../migration_guide.md).*