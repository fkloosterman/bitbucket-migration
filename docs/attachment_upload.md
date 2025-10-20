# Post-Migration Attachment Upload Guide

After running the migration script, attachments from Bitbucket are downloaded to the local folder `attachments_temp/`. GitHub’s API doesn’t allow automatic upload of these files, so they must be added manually.

This guide explains how to locate, upload, and verify migrated attachments.

---

## 🚀 Quick Start

```
POST-MIGRATION: Attachment Handling
===================================

8 attachments were downloaded to: attachments_temp/

To upload attachments to GitHub issues:
1. Navigate to the issue on GitHub
2. Click the comment box
3. Drag and drop the file from attachments_temp/
4. The file will be uploaded and embedded
```

---

## 🔧 Step-by-Step Instructions

### 1. Locate the Attachment Files

```bash
cd attachments_temp/
ls -lh
```

Example output:

```
screenshot.png          2.3M
design-mockup.pdf       5.1M
error-log.txt           150K
```

---

### 2. Identify the Target Issue or PR

Check your GitHub repository for comments added by the migration script. Each issue with attachments includes:

```markdown
📎 **Attachment from Bitbucket**: `screenshot.png` (2.3 MB)

*Note: This file was attached to the original Bitbucket issue.*
```

You can also search your migration logs:

```bash
grep "Attachment from Bitbucket" migration.log
```

---

### 3. Upload the File

#### Option A — Add a New Comment with the File

1. Open the issue on GitHub
2. Scroll to the comment box
3. Drag and drop the file into the box
4. Wait for the upload to finish
5. Add text if desired and click **Comment**

#### Option B — Edit the Existing Attachment Comment

1. Find the comment starting with “📎 Attachment from Bitbucket”
2. Click **... → Edit**
3. Drag the file into the editor
4. Update text if needed
5. Click **Update comment**

---

### 4. Verify Upload

* Images preview inline
* PDFs and other files appear as downloadable links
* The file is now stored permanently on GitHub

---

## 🛠️ Bulk Upload with GitHub CLI

If you have many attachments, you can automate uploads.

```bash
# Install GitHub CLI
brew install gh  # macOS
# or download from https://cli.github.com

# Authenticate
gh auth login

# Bulk upload script
cd attachments_temp
while IFS=',' read -r file issue_num; do
  echo "Uploading $file to issue #$issue_num"
  gh issue comment "$issue_num" \
    --repo OWNER/REPO \
    --body "**Attachment:** $file" \
    --attach "$file"
  sleep 2
done < attachment_mapping.csv
```

The file `attachment_mapping.csv` should list each file and its associated issue number.

---

## 📈 Prioritization

| Priority      | Typical Files                              | Action                 |
| ------------- | ------------------------------------------ | ---------------------- |
| **Critical**  | Screenshots, design mockups, key documents | Upload first           |
| **Important** | Logs, configuration templates              | Upload within 2 weeks  |
| **Optional**  | Old screenshots, test data                 | Upload if time permits |
| **Skip**      | Temporary or obsolete files                | No action              |

---

## 📄 Tracking Upload Progress

Create `attachment-status.md` to track progress:

```markdown
# Attachment Upload Status

## Summary
- Total: 8
- Uploaded: 3
- Pending: 5
- Skipped: 0

### Critical
- [x] #5 screenshot.png (2.3 MB)
- [ ] #12 design-mockup.pdf (5.1 MB)

### Important
- [ ] #23 error-log.txt (150 KB)
```

---

## 🔧 Tips & Best Practices

* **Preview before upload:** `open attachments_temp/filename.png`
* **Rename confusing files:** `mv "Screen Shot 2024-01-15.png" issue-5-login-error.png`
* **Check file size:** GitHub web upload limit is 25 MB. For larger files, use Git LFS or external hosting.
* **Backup before deleting:** Keep `attachments_temp/` for 30 days after migration.

---

## 🔧 Cleanup and Backup

After verifying uploads:

```bash
cd ..
tar -czf migration_attachments_$(date +%Y%m%d).tar.gz attachments_temp/
mv migration_attachments_*.tar.gz ~/backups/
rm -rf attachments_temp/
```

Keep the backup archive and mapping files (`migration_mapping.json`, `audit_report.md`) for future reference.

---

## 📣 Team Communication Template

```markdown
Subject: Action Required – Upload Attachments After Migration

Hi Team,

The migration to GitHub is complete! Please upload attachments from `attachments_temp/` to their corresponding GitHub issues.

**Priority:**
- Critical: This week
- Important: Within 2 weeks
- Optional: As time permits

Steps:
1. Open the target issue on GitHub
2. Drag the file into a new or existing comment
3. Check it displays correctly

Thanks for helping complete the migration.
```

---

## ✅ Success Criteria

* All critical attachments uploaded within 1 week
* Important attachments uploaded within 2 weeks
* Backup created and verified
* Team tracking document updated

---
