# User Mapping Reference

User mapping ensures migrated issues, pull requests, and comments are correctly attributed to GitHub users. This document provides comprehensive guidance on configuring user mappings to handle all Bitbucket user identification scenarios during migration.

---
## 🎯 Overview

The migration tool supports multiple user identification methods in Bitbucket and maps them to GitHub usernames. Understanding these mechanisms is crucial for accurate user attribution and @mention functionality.

**Key Concepts:**

- **Display Names**: Human-readable names shown in Bitbucket UI
- **Usernames**: Internal Bitbucket usernames used in @mentions
- **Account IDs**: Internal Bitbucket identifiers (UUIDs) used in API responses
- **GitHub Usernames**: Target GitHub usernames for mapping

---
## 📋 User Mapping Formats

The migration tool supports multiple mapping formats to handle different Bitbucket user identification scenarios.

### Format 1: Simple Display Name Mapping

Maps Bitbucket display names directly to GitHub usernames. Best for basic use cases.

```json
"user_mapping": {
  "Alice Smith": "alice-github",
  "Bob Jones": "bobjones",
  "Charlie Brown": null,
  "External Contractor": null
}
```

**Use when:**
- @mentions are infrequent or not critical
- Simple one-to-one mapping is sufficient
- Manual @mention fixes after migration are acceptable

### Format 2: Enhanced Mapping (Recommended)

Provides complete mapping information including both display names and Bitbucket usernames. Essential for @mention support.

```json
"user_mapping": {
  "Alice Smith": {
    "github": "alice-github",
    "bitbucket_username": "asmith",
    "display_name": "Alice Smith"
  },
  "Bob Jones": {
    "github": "bobjones",
    "bitbucket_username": "bjones",
    "display_name": "Bob Jones"
  },
  "Charlie Brown": null,
  "External Contractor": null
}
```

**Use when:**
- Team uses @mentions frequently
- Maximum compatibility required
- Account ID mentions need proper resolution
- Display names appear in comments and need mapping to GitHub users

**Note:** The `display_name` field is optional in the enhanced format. If omitted, the key itself is used as the display name for matching purposes.

### Format 3: Direct Username Mapping

Maps Bitbucket usernames directly to GitHub usernames. Useful for @mention-only scenarios.

```json
"user_mapping": {
  "asmith": "alice-github",
  "bjones": "bobjones",
  "old-user": null
}
```

**Use when:**
- You only need to fix @mentions
- Display names are handled separately
- Quick mapping for specific users

**Note:** This format maps Bitbucket usernames directly. It does not handle display name mapping in comments. Use enhanced format for complete coverage.

### Format 4: Mixed Format

Combines multiple formats for maximum flexibility.

```json
"user_mapping": {
  "Alice Smith": {
    "github": "alice-github",
    "bitbucket_username": "asmith"
  },
  "Bob Jones": "bobjones",
  "charlie": "charlie-dev",
  "external-user": null,
  "contractor": null
}
```

**Use when:**
- Different users require different mapping approaches
- Complex organizational structures
- Gradual migration of mapping strategies

**Note:** Mixed format allows combining simple string mappings with enhanced object mappings. The system automatically detects the format for each user entry.

---
## 🔍 Account ID Resolution

Bitbucket uses internal account IDs that appear in content and API responses. The migration tool automatically resolves these to usernames.

### Account ID Formats

**AAID Format (Modern):**
```
@557058:c250d1e9-df76-4236-bc2f-a98d056b56b5
```
- Contains colons (:)
- UUID-like structure
- Most common in current Bitbucket instances

**Legacy Format:**
```
@5d80e691b29eab0c3cba6a2e
```
- Exactly 24 hexadecimal characters
- No colons
- From older Bitbucket instances

### How Resolution Works

1. **Collection Phase**: Migration tool scans all Bitbucket data to build account ID mappings
2. **API Data Extraction**: Extracts `account_id` → `username` relationships from:
     - Issue reporters and assignees
     - PR authors and participants
     - Comment authors
     - Commit authors

3. **Comment Scanning**: Additionally scans all issue and PR comments for account IDs not captured in metadata
4. **API Lookup**: For unresolved account IDs found in comments, performs API lookups to resolve them

5. **Runtime Resolution**: During migration:
     - Account IDs in content are identified
     - Resolved to Bitbucket usernames using collected mappings
     - Usernames are then mapped to GitHub usernames
     - Unresolvable IDs are handled gracefully

### Resolution Example

```json
// During migration, this account ID:
"@557058:c250d1e9-df76-4236-bc2f-a98d056b56b5"

// Gets resolved through these steps:
// 1. Account ID found in API data for user "asmith"
// 2. "asmith" maps to display name "Alice Smith"
// 3. "Alice Smith" maps to GitHub username "alice-github"
// 4. Final result: "@alice-github"

// Display names in comments are also mapped:
// Original comment: "Alice Smith mentioned this issue"
// Becomes: "@alice-github mentioned this issue"
```

---
## 💬 @Mention Processing

The migration tool processes @mentions in all content and rewrites them to GitHub format.

### Processing Strategy

1. **Pattern Detection**: Uses regex to find @mentions in:
     - Issue descriptions
     - PR descriptions
     - Comments (issues and PRs)
     - Any markdown content

2. **Format Handling**: Processes multiple @mention formats:
     - `@username` (standard)
     - `@{user name}` (with braces for special characters)
     - `@557058:c250d1e9-...` (account IDs)

3. **Mapping Application**: For each mention found:
     - Extract the Bitbucket identifier
     - Apply user mapping configuration
     - Generate appropriate GitHub mention or fallback

4. **Display Name Mapping**: When display names appear in comments (not as @mentions):
     - Extract display names from comment text
     - Map them to GitHub usernames using configured display_name mappings
     - Convert to @mentions for proper GitHub attribution

5. **Fallback Handling**: For unmapped mentions:
     - Account IDs with known display names: `**Display Name** *(Bitbucket user, no GitHub account)*
     - Usernames without display names: `@username *(Bitbucket user, needs GitHub mapping)*

### @Mention Patterns

**Standard Username:**
```markdown
Original: @asmith mentioned this issue
Mapped:   @alice-github mentioned this issue
```

**Braced Username:**
```markdown
Original: @{john.doe} commented on the PR
Mapped:   @john-doe commented on the PR
```

**Account ID:**
```markdown
Original: @557058:c250d1e9-df76-4236-bc2f-a98d056b56b5 needs to review
Mapped:   @alice-github needs to review
```

### Unmapped @Mention Handling

When @mentions cannot be mapped:

**For Account IDs with Display Names:**
```markdown
Original: @557058:c250d1e9-df76-4236-bc2f-a98d056b56b5 commented
Becomes: **Alice Smith** *(Bitbucket user, no GitHub account)*
```

**For Usernames without Display Names:**
```markdown
Original: @unknown-user mentioned this
Becomes: @unknown-user *(Bitbucket user, needs GitHub mapping)*
```

---
## ✅ Validation and Error Handling

The migration tool includes comprehensive validation and error handling for user mappings.

### Pre-Migration Validation

**Configuration Validation:**

- Verifies `user_mapping` section exists
- Checks for valid JSON structure
- Validates mapping value types

**Connection Testing:**

- Tests Bitbucket API connectivity
- Tests GitHub API connectivity (read-only)
- Validates repository access permissions

**User Mapping Diagnostics:**

- Scans all content for @mentions and account IDs
- Tests mapping resolution for found mentions
- Reports unmappable mentions with suggestions

### Runtime Error Handling

**Mapping Failures:**

- Gracefully handles missing user mappings
- Preserves original content when mapping fails
- Logs detailed information for post-migration review

**API Errors:**

- Handles temporary API failures
- Retries failed operations where appropriate
- Provides clear error messages for configuration issues

**Data Issues:**

- Handles deleted or inaccessible users
- Manages missing branch information for PRs
- Processes malformed or corrupted content

### Logging and Reporting

**Migration Log Output:**
```
[2024-01-15 10:30:15] → @mentions: 45 mapped, 3 unmapped/replaced
[2024-01-15 10:30:15]     (Account IDs replaced with display names where available)
```

**Migration Report Sections:**

- User mapping summary with success/failure counts
- Unmapped mentions report with resolution suggestions
- Account ID resolution statistics
- Troubleshooting recommendations

---
## 🛠️ Integration with Audit Script

The audit subcommand (`migrate_bitbucket_to_github audit`) is essential for effective user mapping configuration.

### User Discovery Process

1. **Run Initial Audit:**
```bash
migrate_bitbucket_to_github audit --workspace YOUR_WORKSPACE --repo YOUR_REPO --email YOUR_EMAIL
```

2. **Review Generated Files:**
     - `bitbucket_audit_report.json` - Complete audit data
     - `audit_report.md` - Human-readable analysis
     - `user_mapping_template.txt` - Mapping template with activity counts

3. **Analyze User Activity:** The audit provides:
     - Complete list of all users found in repository
     - Activity breakdown (issues, PRs, comments, commits)
     - Bitbucket usernames for each user
     - Account ID mentions and their contexts
     - Account ID to username mappings discovered from API data
     - Additional account ID resolutions from comment scanning

### Using Audit Results

**Activity-Based Prioritization:**
```txt
# From user_mapping_template.txt:
# Alice Smith
#   Bitbucket username: asmith
#   Activity: 15 issues, 8 PRs, 45 comments
#   Total: 68
#
# Bob Jones
#   Bitbucket username: bjones
#   Activity: 3 issues, 12 PRs, 23 comments
#   Total: 38
```

**Account ID Analysis:** The audit identifies items containing account ID mentions:

- Lists specific issues/PRs with account IDs
- Shows types of account IDs found
- Provides context for investigation
- Builds account ID to username/display name mappings from API data
- Performs additional API lookups for account IDs found in comments

### Configuration Generation

**Generate Complete Configuration:**
```bash
migrate_bitbucket_to_github audit --workspace YOUR_WORKSPACE --repo YOUR_REPO --email YOUR_EMAIL \
  --gh-owner YOUR_GITHUB_USER --gh-repo YOUR_REPO
```

**Generated Files:**

- `migration_config.json` - Complete configuration template
- `user_mapping_template.txt` - Detailed mapping reference

**Configuration Generation:**

The audit command can generate complete migration configurations with:

```bash
migrate_bitbucket_to_github audit --workspace YOUR_WORKSPACE --repo YOUR_REPO --email YOUR_EMAIL \
  --gh-owner YOUR_GITHUB_USER --gh-repo YOUR_REPO
```

This creates a unified configuration file that includes user mappings, repository settings, and all discovered account ID mappings.

---
## 🔧 Setup and Configuration

### Step 1: Run Audit for User Discovery

```bash
migrate_bitbucket_to_github audit --workspace myworkspace --repo myrepo --email user@example.com
```

### Step 2: Review User Activity

Examine `audit_report.md` and `user_mapping_template.txt`:

- Identify high-activity users (focus mapping effort here first)
- Note Bitbucket usernames for @mention support
- Identify users without GitHub accounts

### Step 3: Create User Mapping Configuration

**For teams with frequent @mentions:**
```json
"user_mapping": {
  "Alice Smith": {
    "github": "alice-github",
    "bitbucket_username": "asmith",
    "display_name": "Alice Smith"
  },
  "Bob Jones": {
    "github": "bobjones",
    "bitbucket_username": "bjones",
    "display_name": "Bob Jones"
  },
  "External User": null
}
```

**For simple cases:**
```json
"user_mapping": {
  "Alice Smith": "alice-github",
  "Bob Jones": "bobjones",
  "External User": null
}
```

### Step 4: Test Configuration

```bash
migrate_bitbucket_to_github dry-run --config migration_config.json
```

Review the output for:

- Unmapped @mentions warnings
- Account ID resolution messages
- User mapping validation errors

### Step 5: Refine and Iterate

- Add missing GitHub usernames based on dry-run feedback
- Update account ID mappings if needed
- Re-run dry-run until no unmapped mentions remain

---
## 🚨 Troubleshooting and Common Issues

### Issue 1: Unmapped @Mentions After Migration

**Symptoms:**

- @mentions show as `@username *(Bitbucket user, needs GitHub mapping)*`
- Account IDs appear as `**Display Name** *(Bitbucket user, no GitHub account)*`

**Solutions:**

1. **Add Missing Username Mappings:**
```json
"user_mapping": {
  "Display Name": {
    "github": "github-username",
    "bitbucket_username": "bb-username"
  }
}
```

2. **Check Audit Results:**
    - Review `user_mapping_template.txt` for complete user list
    - Check activity counts to prioritize mapping effort

3. **Manual Fix on GitHub:**
    - Search for `*(Bitbucket user, needs GitHub mapping)*` pattern
    - Edit mentions directly on GitHub

### Issue 2: Account IDs Not Resolving

**Symptoms:**

- Account IDs appear in content after migration
- Users report broken @mentions

**Solutions:**

1. **Verify API Permissions:**
```bash
# Ensure your Bitbucket API token has user read permissions
migrate_bitbucket_to_github audit --workspace WORKSPACE --repo REPO --email EMAIL
```

2. **Check Account ID Format:**
    - AAID format: `@557058:c250d1e9-df76-4236-bc2f-a98d056b56b5`
    - Legacy format: `@5d80e691b29eab0c3cba6a2e`

3. **Manual Resolution:**
    - Look up account ID in original Bitbucket content
    - Find corresponding username in audit results
    - Add explicit mapping

### Issue 3: Mixed User Identification Methods

**Symptoms:**

- Some users map correctly, others don't
- Inconsistent @mention behavior

**Solutions:**

1. **Use Enhanced Format for All Users:**
```json
"user_mapping": {
  "User Name": {
    "github": "github-username",
    "bitbucket_username": "bb-username"
  }
}
```

2. **Standardize on Single Format:**
    - Choose either simple or enhanced format
    - Apply consistently across all users
    - Test thoroughly with dry-run

### Issue 4: Large Number of Unmapped Users

**Symptoms:**

- Many users without GitHub accounts
- Extensive unmapped mentions

**Solutions:**

1. **Prioritize by Activity:**
    - Focus on users with high activity counts first
    - Use audit results to identify key contributors

2. **Batch Processing:**
    - Map users in phases (high → medium → low activity)
    - Run multiple dry-run iterations

3. **Set Realistic Expectations:**
    - Accept that some users may remain unmapped
    - Plan for manual fixes post-migration

---
## ✅ Validation Checklist

### Pre-Migration Validation

- [ ] Run audit script and review all generated files
- [ ] Verify all high-activity users have GitHub accounts
- [ ] Check that @mention-heavy users use enhanced format
- [ ] Run dry-run and verify no unmapped mentions
- [ ] Confirm account ID resolution is working
- [ ] Test GitHub API connectivity and permissions

### Configuration Validation

- [ ] `user_mapping` section exists in config
- [ ] All users have valid GitHub usernames or `null`
- [ ] Enhanced format used for frequent @mention users
- [ ] No duplicate or conflicting mappings
- [ ] Configuration file is valid JSON

### Content Validation

- [ ] All @mentions resolve to valid GitHub usernames
- [ ] Account IDs resolve to display names or usernames
- [ ] No broken user references in issue/PR content
- [ ] User assignment works correctly
- [ ] Comment attribution is accurate

### Post-Migration Validation

- [ ] Search GitHub repository for unmapped mention patterns
- [ ] Verify user assignments are correct
- [ ] Check that @mentions work in GitHub interface
- [ ] Confirm no account IDs remain in content
- [ ] Validate cross-references between issues/PRs

---

## 🎯 Best Practices

### 1. Always Run Audit First
The audit subcommand provides essential user discovery and analysis capabilities.

### 2. Use Enhanced Format for @Mentions
When @mentions are important to your team, use the enhanced mapping format.

### 3. Test Thoroughly with Dry-Run
Run multiple dry-run iterations and address all unmapped mentions before actual migration.

### 4. Prioritize by Activity Level
Focus mapping efforts on users with high activity counts first.

### 5. Plan for Manual Fixes
Accept that some edge cases may require manual fixes after migration.

### 6. Document Mapping Decisions
Keep notes on why certain users were mapped (or not mapped) for future reference.

### 7. Validate Post-Migration
Thoroughly validate user attribution and @mention functionality after migration.

---
