# Bitbucket to GitHub Migration Guide

**Version:** 1.0  
**Last Updated:** 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Migration Strategy](#migration-strategy)
3. [What Can Be Migrated](#what-can-be-migrated)
4. [What Cannot Be Migrated](#what-cannot-be-migrated)
5. [Workarounds](#workarounds)
6. [Recommended Workflow](#recommended-workflow)
7. [Prerequisites](#prerequisites)
8. [Step-by-Step Instructions](#step-by-step-instructions)
9. [Troubleshooting](#troubleshooting)
10. [Post-Migration Tasks](#post-migration-tasks)

---

## Overview

This migration tool helps you move a Bitbucket Cloud repository to GitHub while preserving as much data and context as possible. The migration consists of two main components:

1. **Git History Migration**: Moving all commits, branches, and tags
2. **Metadata Migration**: Moving issues, pull requests, comments, and attachments

### Key Features

- ✅ Preserves issue and PR numbers (using placeholders for gaps)
- ✅ Maintains all comments with original timestamps and authors
- ✅ Handles users without GitHub accounts gracefully
- ✅ Migrates attachments (with limitations)
- ✅ Smart PR migration strategy (open as PRs, closed as issues)
- ✅ Dry-run mode for testing
- ✅ Detailed audit reports

---

## Migration Strategy

### Phase 1: Git History

**Method:** Mirror push using git CLI

```bash
git clone --mirror <bitbucket-url>
git push --mirror <github-url>
```

**What migrates:**
- All commits with full history
- All branches
- All tags
- Commit authors and dates

**Limitations:**
- Git LFS objects require separate handling
- Very large repositories (>5GB) may need special handling

### Phase 2: Issues

**Method:** GitHub API issue creation

**Strategy:**
1. Fetch all issues from Bitbucket (including closed)
2. Create placeholder issues for number gaps (deleted issues)
3. Create each issue with original metadata in description
4. Add all comments
5. Close issues that were closed in Bitbucket

**Number Preservation:**
- Uses placeholders to maintain exact issue numbers
- Example: If issues #1, #3, #5 exist, creates placeholder for #2 and #4

### Phase 3: Pull Requests

**Method:** Smart dual-strategy migration

**Strategy:**

**Open PRs (branches still exist):**
- Attempt to create as actual GitHub PRs
- Preserves full PR experience with diffs
- Requires source branch to exist on GitHub

**Closed/Merged PRs (branches likely deleted):**
- Migrate as GitHub issues with special formatting
- Include all PR metadata in issue description
- Add labels: `original-pr`, `pr-merged`, `pr-declined`, etc.
- Preserve all comments

**Why this approach?**
- GitHub PR API requires actual branches
- Deleted branches can't be recreated
- Issue format preserves all data and context

---

## What Can Be Migrated

### ✅ Fully Migrated (100% Preserved)

| Data | Method | Notes |
|------|--------|-------|
| Git commits | Mirror push | Complete history |
| Branches | Mirror push | All branches |
| Tags | Mirror push | All tags |
| Issue titles | API | Exact copy |
| Issue descriptions | API | Full markdown |
| Issue states | API | Open/closed |
| Issue comments | API | All comments |
| Issue numbers | Placeholders | Exact numbering |
| PR titles | API | Exact copy |
| PR descriptions | API | Full markdown |
| PR comments | API | All comments |
| Commit messages | Git | Preserved in history |

### ⚠️ Partially Migrated (Modified Format)

| Data | What Changes | Workaround |
|------|-------------|------------|
| Issue authors | Text mention in description | `@username` or `**Name** (no GitHub account)` |
| Comment authors | Text in comment body | Each comment includes "Comment by @user on date" |
| Timestamps | Noted in text | "Original Created: 2024-01-15" in description |
| Closed PRs | Become issues | Full metadata preserved in issue description |
| Issue assignees | GitHub assignment if mapped | Mentioned in text if no GitHub account |
| Attachments | Downloaded locally | Comment with file info; files in `attachments_temp/` |

### ❌ Cannot Be Migrated

| Data | Reason | Impact |
|------|--------|--------|
| Actual creation timestamps | GitHub API limitation | Dates shown as text only |
| PR merge commits (deleted branches) | Branch required | PR migrated as issue instead |
| PR review approvals | No API endpoint | Lost; mentioned in description |
| PR requested reviewers | Limited API | Listed in description text |
| Bitbucket-specific fields | Platform difference | Documented in descriptions |
| Watch/star lists | User-specific data | Not accessible via API |
| Repository settings | Not in scope | Must be configured manually |
| Webhooks | Not in scope | Must be recreated |
| Branch permissions | Platform-specific | Configure on GitHub |

---

## Workarounds

### 1. Deleted User Accounts

**Problem:** User left Bitbucket, account deleted  
**Solution:**
- Script handles gracefully: `"Unknown (deleted user)"`
- No crashes or data loss
- Users are still credited in text

**Configuration:**
```json
"user_mapping": {
  "Unknown (deleted user)": null
}
```

### 2. Users Without GitHub Accounts

**Problem:** Bitbucket user doesn't have GitHub account  
**Solution:**
- Map to `null` in configuration
- Mentioned as: `**John Doe** (no GitHub account)`
- Not assigned to issues (would fail)

**Configuration:**
```json
"user_mapping": {
  "External Consultant": null,
  "Former Employee": null
}
```

### 3. Closed PRs (Deleted Branches)

**Problem:** Can't create PR without source branch  
**Solution:**
- Migrate as GitHub issue
- Full metadata in description
- All comments preserved
- Special labels added

**Example migrated PR as issue:**
```markdown
⚠️ This was a Pull Request on Bitbucket (now migrated as an issue)

Original PR Metadata:
- Author: @alice
- State: MERGED
- Created: 2024-01-15T10:30:00Z
- Source Branch: `feature/new-api`
- Destination Branch: `main`
- Original URL: https://bitbucket.org/...

[Description content...]

Note: This PR was merged on Bitbucket. The source branch may no 
longer exist, so it was migrated as an issue rather than a GitHub PR.
```

### 4. Attachments

**Problem:** GitHub API doesn't support attachment uploads  
**Solution:**
- Download all attachments to `attachments_temp/`
- Create comment noting attachment details
- Files available for manual upload

**Process:**
1. Script downloads: `attachments_temp/screenshot.png`
2. Creates comment: `📎 Attachment from Bitbucket: screenshot.png (2.3 MB)`
3. After migration, drag-and-drop to GitHub issue if needed

### 5. Original Timestamps

**Problem:** GitHub API doesn't allow setting creation dates  
**Solution:**
- Include original date in description/comment
- Example: `Original Created: 2024-01-15T10:30:00Z`
- Searchable and visible to users

### 6. Large Repositories

**Problem:** >5GB repositories may timeout  
**Solution:**
- Use `--skip-issues` and `--skip-prs` flags to migrate in chunks
- Or use GitHub's import service for git history
- Then run script for metadata only

---

## Recommended Workflow

### Complete Migration Timeline: ~2-4 hours

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Preparation (30 min)                           │
├─────────────────────────────────────────────────────────┤
│ 1. Run audit                                            │
│ 2. Review audit report                                  │
│ 3. Create user mapping                                  │
│ 4. Generate migration config                            │
│ 5. Edit config with GitHub token & user mappings       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 2: Git Migration (15-30 min)                      │
├─────────────────────────────────────────────────────────┤
│ 1. Create empty GitHub repository                      │
│ 2. Clone Bitbucket repo as mirror                      │
│ 3. Push mirror to GitHub                               │
│ 4. Verify all branches/tags migrated                   │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 3: Dry Run (15 min)                               │
├─────────────────────────────────────────────────────────┤
│ 1. Run migration with --dry-run flag                   │
│ 2. Review console output                               │
│ 3. Fix any configuration issues                        │
│ 4. Re-run dry run until successful                     │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 4: Actual Migration (1-2 hours)                   │
├─────────────────────────────────────────────────────────┤
│ 1. Run migration script (monitor progress)             │
│ 2. Script creates issues with placeholders             │
│ 3. Script migrates all PRs                             │
│ 4. Script downloads attachments                        │
│ 5. Review migration_mapping.json                       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 5: Post-Migration (30 min)                        │
├─────────────────────────────────────────────────────────┤
│ 1. Verify issue/PR counts                              │
│ 2. Spot-check migrated content                         │
│ 3. Upload important attachments manually               │
│ 4. Update repository settings                          │
│ 5. Notify team of new repository                       │
└─────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required Tools

- **Python 3.7+**
- **Git 2.x+**
- **pip** (Python package manager)

### Required Accounts & Tokens

1. **Bitbucket Cloud Account**
   - Access to repository to migrate
   - User-level API token

2. **GitHub Account**
   - Admin access to destination repository
   - Personal Access Token (PAT)

### Python Dependencies

```bash
pip install requests
```

### Create Bitbucket API Token

1. Go to: **Settings → Atlassian account settings → Security**
2. Click **"Create and manage API tokens"**
3. Click **"Create API token with scopes"**
4. Name: "Migration Tool"
5. Select app: **Bitbucket**
6. Permissions: **Full access** (or minimum: read repos, issues, PRs)
7. Copy token immediately

### Create GitHub Personal Access Token

1. Go to: **Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **"Generate new token (classic)"**
3. Name: "Bitbucket Migration"
4. Scopes: Check **`repo`** (full control of private repositories)
5. Click **"Generate token"**
6. Copy token immediately

---

## Step-by-Step Instructions

### Step 1: Run Audit

```bash
python audit_bitbucket.py \
  --workspace YOUR_WORKSPACE \
  --repo YOUR_REPO \
  --email YOUR_EMAIL \
  --generate-config \
  --gh-owner YOUR_GITHUB_USERNAME \
  --gh-repo YOUR_REPO
```

**Output files:**
- `bitbucket_audit_report.json` - Machine-readable report
- `audit_report.md` - Human-readable markdown report
- `bitbucket_issues_detail.json` - Detailed issue data
- `bitbucket_prs_detail.json` - Detailed PR data
- `migration_config.json` - Configuration template
- `user_mapping_template.txt` - User activity reference

**Review:**
- Open `audit_report.md` in any markdown viewer
- Check user activity table
- Note migration estimates

### Step 2: Configure User Mapping

Edit `migration_config.json`:

```json
{
  "bitbucket": {
    "workspace": "myworkspace",
    "repo": "myrepo",
    "email": "you@example.com",
    "token": "ATAT..." // Already filled!
  },
  "github": {
    "owner": "your-github-username", // ← Fill this
    "repo": "myrepo",
    "token": "ghp_..." // ← Fill this
  },
  "user_mapping": {
    "Alice Smith": "alice-smith-gh",  // ← Map users
    "Bob Jones": "bjones",
    "Unknown (deleted user)": null,   // ← Deleted accounts
    "External Consultant": null       // ← No GitHub account
  }
}
```

**Tips:**
- Use `user_mapping_template.txt` to see activity counts
- Focus on high-activity users
- Set `null` for deleted users or users without GitHub

### Step 3: Create GitHub Repository

```bash
# On GitHub web interface:
# 1. Click "New repository"
# 2. Name it (same as Bitbucket or different)
# 3. Make it PRIVATE (can change later)
# 4. DO NOT initialize with README, .gitignore, or license
# 5. Click "Create repository"
```

**Important:** Repository must be completely empty!

### Step 4: Migrate Git History

```bash
# Clone Bitbucket repo as mirror
git clone --mirror https://bitbucket.org/WORKSPACE/REPO.git
cd REPO.git

# Add GitHub remote
git remote add github https://github.com/OWNER/REPO.git

# Push everything to GitHub
git push --mirror github

# Verify
git ls-remote github
```

**Verify:**
- Check GitHub repo shows all branches
- Verify tags are present
- Confirm commit history is intact

### Step 5: Dry Run Migration

```bash
python migrate_bitbucket_to_github.py \
  --config migration_config.json \
  --dry-run
```

**What to check:**
- No errors in output
- All issues/PRs accounted for
- User mappings working correctly
- No authentication failures

**Common dry-run issues:**
- Invalid GitHub token → Regenerate with `repo` scope
- User not found → Set to `null` or correct username
- Repository not empty → Ensure step 4 completed

### Step 6: Run Actual Migration

```bash
python migrate_bitbucket_to_github.py \
  --config migration_config.json
```

**Monitor progress:**
- Console shows each issue/PR being migrated
- Issues created with placeholders
- Comments added
- Attachments downloaded to `attachments_temp/`

**Duration:** ~0.5 minutes per issue/PR (API rate limits)

**If interrupted:**
- Script saves `migration_mapping_partial.json`
- Can resume by editing code to skip completed items
- Or restart (will create duplicates)

### Step 7: Verify Migration

**Check counts:**
```bash
# Compare audit report numbers with GitHub
# Issues: GitHub should match Bitbucket (including placeholders)
# PRs: Open PRs as PRs, closed as issues
```

**Spot-check content:**
1. Open a random issue - verify description and comments
2. Check a closed PR (now issue) - verify metadata preserved
3. Verify user mentions working correctly
4. Check placeholder issues are closed and labeled

**Review mapping:**
```bash
cat migration_mapping.json
# Shows Bitbucket # → GitHub # for all items
```

### Step 8: Handle Attachments

```bash
ls -lh attachments_temp/
# Shows all downloaded attachments
```

**Understanding Attachment Migration:**

The script downloads all attachments because GitHub's API doesn't support direct file uploads. Each attachment:
- ✅ Downloaded to `attachments_temp/` folder
- ✅ Comment added to GitHub issue noting the attachment
- ⚠️ Requires manual upload to fully embed in GitHub

**Attachment Organization:**

```
attachments_temp/
├── screenshot.png          # From issue #5
├── design-mockup.pdf       # From issue #12  
├── error-log.txt           # From issue #23
└── database-diagram.png    # From PR #8 (now issue)
```

**How to Upload Attachments to GitHub:**

**Method 1: Drag and Drop (Recommended)**

1. Open the GitHub issue in your browser
   ```
   https://github.com/OWNER/REPO/issues/5
   ```

2. Scroll to the bottom and click in the comment box

3. Drag the file from `attachments_temp/` into the comment box
   - File will show upload progress
   - Image will preview if it's an image file

4. The uploaded file URL will appear like:
   ```
   ![screenshot](https://github.com/user-attachments/assets/...)
   ```

5. Either:
   - **Option A:** Submit the comment with just the file (creates new comment)
   - **Option B:** Edit the existing attachment comment and add the file there

6. The file is now permanently hosted by GitHub

**Method 2: Edit Existing Comment**

Each issue already has a comment noting the attachment:

```markdown
📎 **Attachment from Bitbucket**: `screenshot.png` (2.3 MB)

*Note: This file was attached to the original Bitbucket issue...*
```

To replace this with the actual file:

1. Find the attachment comment on the GitHub issue
2. Click the "..." menu → "Edit"
3. Drag and drop the file from `attachments_temp/`
4. Update the comment text if desired
5. Click "Update comment"

**Method 3: Bulk Upload Script (For Many Attachments)**

If you have many attachments, consider using GitHub CLI:

```bash
# Install GitHub CLI
brew install gh  # macOS
# or download from https://cli.github.com

# Authenticate
gh auth login

# Upload attachments using a script
for file in attachments_temp/*; do
  # Find which issue it belongs to from mapping
  issue_num=5  # Look this up from attachment comment
  gh issue comment $issue_num \
    --repo OWNER/REPO \
    --body "Attachment: $(basename $file)" \
    --attach "$file"
done
```

**Finding Which Attachment Goes Where:**

The script creates comments on each issue noting attachments:

```bash
# Search migration output or logs
grep "Uploading" migration.log

# Or check the GitHub issue comments
# Each has: "📎 Attachment from Bitbucket: filename.ext"
```

**After Migration Script Completes:**

The console output will show:

```
================================================================================
POST-MIGRATION: Attachment Handling
================================================================================

8 attachments were downloaded to: attachments_temp

To upload attachments to GitHub issues:
1. Navigate to the issue on GitHub
2. Click the comment box
3. Drag and drop the file from attachments_temp/
4. The file will be uploaded and embedded

Example:
  - Open: https://github.com/OWNER/REPO/issues/1
  - Drag: attachments_temp/screenshot.png
  - File will appear in comment with URL

Note: Comments already note which attachments belonged to each issue.

Keep attachments_temp/ folder as backup until all important files are uploaded.
================================================================================
```

**Prioritizing Attachments:**

Not all attachments need manual upload. Prioritize:

1. **High Priority:** 
   - Screenshots showing bugs/issues
   - Design mockups
   - Important documents referenced in discussions

2. **Medium Priority:**
   - Log files that might be useful for debugging
   - Configuration files
   - Test data

3. **Low Priority:**
   - Temporary files
   - Outdated documents
   - Files already available elsewhere

**Attachment Checklist:**

- [ ] Review all files in `attachments_temp/`
- [ ] Identify critical attachments (10-20%)
- [ ] Upload critical files to their GitHub issues
- [ ] Verify files display correctly
- [ ] Document attachment locations in team wiki
- [ ] Keep `attachments_temp/` folder for 1 month as backup
- [ ] After verification period, archive or delete folder

**Tips:**

- Images automatically preview in GitHub
- PDFs show as downloadable links
- Large files (>25MB) cannot be uploaded via web UI
- For very large files, consider external storage (Google Drive, Dropbox) and add links in comments

### Step 9: Post-Migration Cleanup

**On GitHub:**
1. Configure repository settings (description, topics)
2. Set branch protection rules
3. Add collaborators
4. Configure webhooks/integrations
5. Update README with migration notes

**On Bitbucket:**
1. Add deprecation notice to README
2. Update description: "Migrated to GitHub: [link]"
3. Consider archiving repository (makes read-only)
4. Inform team of new location

**Team communication:**
```markdown
📢 Repository Migration Notice

Our repository has been migrated from Bitbucket to GitHub:
- New location: https://github.com/OWNER/REPO
- All issues and PRs have been migrated
- Git history is fully preserved
- Please clone from new location: git clone https://github.com/OWNER/REPO.git
- Old Bitbucket repo is now read-only

Questions? See: [link to audit_report.md]
```

---

## Troubleshooting

### Authentication Errors

**Problem:** `401 Unauthorized`

**Solution:**
```bash
# For Bitbucket:
# - Verify API token is not expired
# - Check token has required permissions
# - Use Atlassian email, not Bitbucket username

# For GitHub:
# - Verify PAT has 'repo' scope
# - Check PAT is not expired
# - Ensure you're owner/admin of target repo
```

### Rate Limiting

**Problem:** `429 Too Many Requests`

**Solution:**
- Script has built-in delays
- If still hitting limits, increase delays in code:
  - Change `rate_limit_sleep(1.0)` to `rate_limit_sleep(2.0)`
- GitHub: 5000 requests/hour limit
- Bitbucket: Similar limits

### Missing Issues/PRs

**Problem:** Count doesn't match audit

**Solution:**
1. Check `migration_mapping.json` for what migrated
2. Look for errors in console output
3. Check GitHub for placeholder issues
4. Verify authentication didn't expire mid-migration

### User Not Found Errors

**Problem:** `User 'username' not found on GitHub`

**Solution:**
```json
// In migration_config.json, set to null:
"user_mapping": {
  "Problem User": null
}
```

### Branch Not Found for PR

**Problem:** `Can't create PR: branch 'feature/xyz' not found`

**Solution:**
- Expected for closed PRs (branches deleted)
- PR will be migrated as issue automatically
- Verify git mirror push completed (step 4)

### Attachment Download Failures

**Problem:** Some attachments not downloading

**Solution:**
- Check Bitbucket API token permissions
- Verify attachments exist in Bitbucket
- Check `attachments_temp/` for partial downloads
- Large files (>100MB) may timeout - download manually

---

## Post-Migration Tasks

### Post-Migration Tasks

**Immediate (Day 1):**

- [ ] **Verify Migration Completeness**
  - Check issue count: Bitbucket count = GitHub count (including placeholders)
  - Check PR count: Open PRs as PRs + closed PRs as issues
  - Spot-check 5-10 issues for accuracy
  - Verify user mentions working

- [ ] **Handle Critical Attachments** (Top 10-20%)
  - Review `attachments_temp/` folder
  - Identify must-have files (screenshots, important docs)
  - Upload to GitHub issues via drag-and-drop
  - Verify files display correctly

- [ ] **Update Repository Settings**
  - Add description and topics
  - Configure default branch
  - Set visibility (public/private)

- [ ] **Test Repository Access**
  - Clone from GitHub: `git clone https://github.com/OWNER/REPO.git`
  - Verify you can push/pull
  - Check team members can access

- [ ] **Communication**
  - Send migration complete announcement
  - Update team documentation with new repo URL
  - Post in team Slack/chat

### Short-term (Week 1)

- [ ] **Upload Remaining Important Attachments**
  - Work through medium-priority files
  - Update attachment comments with uploaded files
  - Document any missing files

- [ ] **Configure GitHub Settings**
  - Set up branch protection rules
  - Configure required reviews
  - Add status checks

- [ ] **Manage Access**
  - Add all team members as collaborators
  - Set appropriate permission levels
  - Remove any test/temporary accounts

- [ ] **Set Up Integrations**
  - Configure CI/CD (GitHub Actions, etc.)
  - Set up webhooks (Slack, Discord, etc.)
  - Connect project management tools

- [ ] **Repository Cleanup**
  - Review and close any placeholder issues you don't want visible
  - Add labels to migrated issues/PRs for organization
  - Pin important issues to repository

- [ ] **Bitbucket Deprecation**
  - Add notice to Bitbucket README
  - Update repository description with new GitHub URL
  - Consider archiving repository (makes it read-only)

### Long-term (Month 1)

- [ ] **Archive Migration Artifacts**
  - Backup `attachments_temp/` folder to long-term storage
  - Save `migration_mapping.json` to team wiki
  - Store `audit_report.md` for reference
  - Delete local migration files after backup

- [ ] **Clean Up Credentials**
  - Revoke Bitbucket API token
  - Rotate GitHub PAT if needed
  - Remove tokens from configuration files

- [ ] **Update External References**
  - Update links in documentation
  - Update CI/CD configurations pointing to Bitbucket
  - Update issue tracker links in Jira/other tools
  - Search codebase for Bitbucket URLs and update

- [ ] **Team Training**
  - Document GitHub workflow differences
  - Train team on new features (Actions, Projects, etc.)
  - Update contribution guidelines

- [ ] **Final Verification**
  - Confirm all critical data migrated
  - Verify attachments uploaded
  - Check that no work is stuck in Bitbucket
  - Get team confirmation repository is working

### Post-Migration Attachment Management

**Create an attachment tracking document:**

```markdown
# Attachment Upload Status

## Critical (Must Upload)
- [ ] Issue #5: screenshot.png - Shows login bug
- [ ] Issue #12: design-mockup.pdf - Current design reference
- [ ] Issue #23: error-log.txt - Production error details

## Important (Should Upload)
- [ ] Issue #34: config-example.json - Configuration template
- [ ] Issue #45: performance-graph.png - Baseline metrics

## Optional (Upload if Time Permits)
- [ ] Issue #67: old-screenshot.png - Historical reference
- [ ] Issue #89: temp-data.csv - Test data

## Skip (Not Needed)
- [ ] Issue #100: outdated-mockup.pdf - Superseded
- [ ] Issue #120: random-notes.txt - No longer relevant
```

**Attachment Upload Log Template:**

| GitHub Issue | Filename | Size | Priority | Status | Uploaded By | Date |
|--------------|----------|------|----------|--------|-------------|------|
| #5 | screenshot.png | 2.3 MB | Critical | ✅ Done | Alice | 2025-10-18 |
| #12 | design.pdf | 5.1 MB | Critical | ✅ Done | Bob | 2025-10-18 |
| #23 | error.log | 150 KB | Critical | ⏳ Pending | - | - |
| #34 | config.json | 12 KB | Important | ⏳ Pending | - | - |

---

## Best Practices

### Before Migration

1. **Communicate early** - Announce migration plan 1-2 weeks ahead
2. **Freeze changes** - Pause work during migration (or accept manual sync)
3. **Backup data** - Keep Bitbucket repo accessible for reference
4. **Test workflow** - Run dry-run multiple times

### During Migration

1. **Monitor progress** - Watch console for errors
2. **Don't interrupt** - Let script complete (or you'll need to resume manually)
3. **Document issues** - Note any errors for troubleshooting

### After Migration

1. **Verify immediately** - Check counts and spot-check content
2. **Upload attachments** - Handle critical files first
3. **Update links** - Find/replace Bitbucket URLs in docs
4. **Keep Bitbucket read-only** - Don't delete immediately

---

## Limitations Summary

| Limitation | Severity | Workaround |
|------------|----------|------------|
| Original timestamps not preserved | Medium | Noted in text |
| Closed PRs become issues | Medium | Full metadata preserved |
| Attachments not auto-uploaded | Low | Manual drag-and-drop |
| PR approvals not migrated | Low | Mentioned in description |
| Users without GitHub can't be assigned | Low | Mentioned in text |
| Deleted user accounts | Low | Marked as "deleted user" |

---

## Support and Resources

### Documentation

- This migration guide
- `audit_report.md` - Your repository's specific report
- `migration_config.json` - Configuration template
- `user_mapping_template.txt` - User reference

### GitHub Resources

- [GitHub API Documentation](https://docs.github.com/en/rest)
- [GitHub Import Documentation](https://docs.github.com/en/migrations)

### Bitbucket Resources

- [Bitbucket API Documentation](https://developer.atlassian.com/cloud/bitbucket/rest/)
- [Bitbucket Cloud Migration Guide](https://support.atlassian.com/bitbucket-cloud/)

---

## FAQ

**Q: Will this delete my Bitbucket repository?**  
A: No. The script only reads from Bitbucket and writes to GitHub. Your Bitbucket repo remains untouched.

**Q: Can I migrate multiple repositories at once?**  
A: Run the script separately for each repository. Consider scripting for bulk migrations.

**Q: What if I need to re-run the migration?**  
A: You'll need to delete the GitHub repository and start over, or manually merge changes.

**Q: Can I migrate from Bitbucket Server (self-hosted)?**  
A: This script is for Bitbucket Cloud only. Bitbucket Server has different APIs.

**Q: Will GitHub issue numbers exactly match Bitbucket?**  
A: Yes, thanks to placeholder issues for number gaps.

**Q: What about Git LFS files?**  
A: Migrate Git LFS separately using git-lfs commands before running this script.

**Q: Can I customize what gets migrated?**  
A: Yes, use `--skip-issues` or `--skip-prs` flags.

**Q: How long does migration take?**  
A: ~0.5 minutes per issue/PR, plus setup time. See audit report for estimates.

**Q: What happens to Bitbucket after migration?**  
A: Nothing changes on Bitbucket. Consider archiving it after verifying GitHub migration.

**Q: Can I test the migration first?**  
A: Yes! Use `--dry-run` flag to simulate the entire migration without making changes.

**Q: What if my organization uses Bitbucket Server (not Cloud)?**  
A: This tool is designed for Bitbucket Cloud only. Bitbucket Server has a different API structure.

**Q: Will webhook integrations be migrated?**  
A: No. Webhooks are configuration, not data. You'll need to recreate them on GitHub.

**Q: Can I cancel mid-migration?**  
A: Yes, press Ctrl+C. The script saves partial progress to `migration_mapping_partial.json`.

**Q: What about private repositories?**  
A: Works the same. Ensure your tokens have access to private repos.

---

## Migration Checklist

Use this checklist to track your migration progress:

### Pre-Migration
- [ ] Review MIGRATION_GUIDE.md
- [ ] Run audit script
- [ ] Review `audit_report.md`
- [ ] Create GitHub repository (empty)
- [ ] Create Bitbucket API token
- [ ] Create GitHub PAT with `repo` scope
- [ ] Map all users in `migration_config.json`
- [ ] Communicate migration plan to team
- [ ] Set migration date/time

### Git Migration
- [ ] Clone Bitbucket as mirror
- [ ] Push mirror to GitHub
- [ ] Verify all branches migrated
- [ ] Verify all tags migrated
- [ ] Test clone from GitHub

### Metadata Migration
- [ ] Run migration dry-run
- [ ] Fix any dry-run errors
- [ ] Run actual migration
- [ ] Monitor for errors
- [ ] Review `migration_mapping.json`

### Verification
- [ ] Issue count matches (including placeholders)
- [ ] PR count matches
- [ ] Spot-check 5-10 issues for accuracy
- [ ] Spot-check 3-5 PRs for accuracy
- [ ] Verify user mentions working
- [ ] Check attachments downloaded

### Post-Migration
- [ ] Upload critical attachments to GitHub
- [ ] Configure repository settings
- [ ] Set up branch protection
- [ ] Add collaborators
- [ ] Update webhooks/integrations
- [ ] Update team documentation
- [ ] Send migration announcement
- [ ] Archive Bitbucket repository
- [ ] Update external links (wiki, docs)
- [ ] Clean up temp files (after 1 month)

---

## Quick Reference

### Key Commands

```bash
# Audit
python audit_bitbucket.py \
  --workspace WORKSPACE --repo REPO --email EMAIL \
  --generate-config --gh-owner OWNER

# Git Migration
git clone --mirror https://bitbucket.org/WORKSPACE/REPO.git
cd REPO.git
git remote add github https://github.com/OWNER/REPO.git
git push --mirror github

# Dry Run
python migrate_bitbucket_to_github.py \
  --config migration_config.json --dry-run

# Actual Migration
python migrate_bitbucket_to_github.py \
  --config migration_config.json
```

### Key Files

| File | Purpose |
|------|---------|
| `MIGRATION_GUIDE.md` | This guide |
| `audit_report.md` | Your repo-specific report |
| `migration_config.json` | Configuration to edit |
| `user_mapping_template.txt` | User activity reference |
| `migration_mapping.json` | Bitbucket → GitHub number map |
| `attachments_temp/` | Downloaded attachments |

### Important URLs

- **Bitbucket API Token:** Settings → Security → API tokens
- **GitHub PAT:** Settings → Developer settings → Personal access tokens
- **Audit Reports:** Review before migration
- **Migration Guide:** This document

---

## Glossary

**API Token** - Authentication credential for accessing Bitbucket/GitHub APIs

**App Password** - Legacy Bitbucket authentication (deprecated Sept 2025)

**Dry Run** - Simulation mode that doesn't make actual changes

**Mirror Push** - Git operation that copies all branches and tags exactly

**PAT (Personal Access Token)** - GitHub authentication credential

**Placeholder Issue** - GitHub issue created to maintain numbering gaps

**PR (Pull Request)** - Code review request (called "Merge Request" in some systems)

**Rate Limiting** - API restriction on number of requests per hour

**Scope** - Permission level for API tokens

**User Mapping** - Configuration linking Bitbucket users to GitHub usernames

---

## Additional Resources

### Example User Mapping

```json
{
  "user_mapping": {
    "Alice Smith": "alice-gh",           // Active developer
    "Bob Jones": "bob-jones-dev",        // Active developer  
    "Charlie Brown": null,               // Left company, no GitHub
    "Diana Prince": "wonderwoman",       // Active developer
    "Eve Wilson": "eve-codes",           // Active developer
    "Frank Castle": null,                // Contractor, no GitHub
    "Grace Hopper": "amazing-grace",     // Active developer
    "Unknown (deleted user)": null       // Deleted accounts
  }
}
```

### Example Migration Timeline

**Small Repository (50 issues, 20 PRs):**
- Audit: 5 minutes
- Configuration: 15 minutes
- Git migration: 10 minutes
- Metadata migration: 35 minutes
- Verification: 15 minutes
- **Total: ~1.5 hours**

**Medium Repository (200 issues, 100 PRs):**
- Audit: 10 minutes
- Configuration: 20 minutes
- Git migration: 20 minutes
- Metadata migration: 2.5 hours
- Verification: 30 minutes
- **Total: ~3.5 hours**

**Large Repository (500 issues, 300 PRs):**
- Audit: 20 minutes
- Configuration: 30 minutes
- Git migration: 30 minutes
- Metadata migration: 6.5 hours
- Verification: 1 hour
- **Total: ~9 hours**

### Sample Migration Announcement

```markdown
Subject: [Action Required] Repository Migration to GitHub

Hi Team,

We're migrating our repository from Bitbucket to GitHub on [DATE] at [TIME].

**What's Changing:**
- New repository location: https://github.com/OWNER/REPO
- All issues and PRs will be migrated
- Git history fully preserved
- Bitbucket repo will become read-only

**What You Need to Do:**
1. After [TIME], clone from new location:
   git clone https://github.com/OWNER/REPO.git

2. Update your local repository remotes:
   git remote set-url origin https://github.com/OWNER/REPO.git

3. Update any external links/bookmarks

**During Migration:**
- Please don't push to Bitbucket during [TIME_RANGE]
- Migration expected to take [DURATION]
- You'll receive confirmation email when complete

**Questions?**
- See: [link to audit_report.md]
- Contact: [migration lead]

Thanks for your cooperation!
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-17 | Initial migration guide |
| 1.1 | TBD | Updated for API changes |

---

## Credits & License

**Migration Tools:**
- Audit Script: `audit_bitbucket.py`
- Migration Script: `migrate_bitbucket_to_github.py`

**Dependencies:**
- Python 3.7+
- requests library
- Git 2.x+

**Authors:**
- Migration tooling developed for Bitbucket Cloud to GitHub migrations
- Based on Bitbucket API 2.0 and GitHub REST API v3

**License:**
These scripts are provided as-is for migration purposes. Modify as needed for your use case.

---

## Feedback & Improvements

Found an issue or have suggestions? Consider documenting:
- What went wrong
- Error messages
- Steps to reproduce
- Suggested improvements

Common areas for contribution:
- Additional API error handling
- Support for Git LFS
- Bulk repository migration
- Progress bars / UI improvements
- Additional export formats (CSV, Excel)

---

## Final Notes

**Remember:**
- ✅ Always run dry-run first
- ✅ Keep Bitbucket as backup initially
- ✅ Verify migration thoroughly
- ✅ Communicate with your team
- ✅ Document any custom changes

**Success Criteria:**
- All issues migrated
- All PRs migrated (as PRs or issues)
- Git history intact
- Team can access new repository
- No data loss

**If Something Goes Wrong:**
- Don't panic - Bitbucket still has original
- Review troubleshooting section
- Check migration_mapping.json for progress
- Can re-run migration to empty repo
- Document issues for future reference

---

## Contact & Support

**For issues with these scripts:**
- Review troubleshooting section
- Check audit report for specifics
- Verify API tokens and permissions

**For GitHub support:**
- [GitHub Support](https://support.github.com)
- [GitHub Community](https://github.community)

**For Bitbucket support:**
- [Bitbucket Support](https://support.atlassian.com/bitbucket-cloud/)
- [Atlassian Community](https://community.atlassian.com)

---

**End of Migration Guide**

*This guide is a living document. Update it with your organization's specific experiences and requirements.*

**Good luck with your migration! 🚀**

---

### Document Information

- **Title:** Bitbucket to GitHub Migration Guide
- **Version:** 1.0
- **Last Updated:** October 17, 2025
- **Format:** Markdown
- **Intended Audience:** Development teams, DevOps engineers, Repository administrators
- **Prerequisites:** Familiarity with Git, API tokens, command line
- **Estimated Reading Time:** 30 minutes
- **Estimated Migration Time:** 2-9 hours (depending on repository size)

---

*Save this guide alongside your migration scripts for future reference.*