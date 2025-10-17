# Post-Migration Attachment Upload Guide

## Quick Start

After running the migration script, you'll see:

```
================================================================================
POST-MIGRATION: Attachment Handling
================================================================================

8 attachments were downloaded to: attachments_temp/

To upload attachments to GitHub issues:
1. Navigate to the issue on GitHub
2. Click the comment box  
3. Drag and drop the file from attachments_temp/
4. The file will be uploaded and embedded
```

## Step-by-Step: Uploading an Attachment

### 1. Locate the Attachment

```bash
cd attachments_temp/
ls -lh
```

Output:
```
screenshot.png          2.3M
design-mockup.pdf       5.1M
error-log.txt          150K
```

### 2. Find Which Issue It Belongs To

Check the migration console output or look for the comment on GitHub. Each issue with attachments has a comment like:

```markdown
📎 **Attachment from Bitbucket**: `screenshot.png` (2.3 MB)

*Note: This file was attached to the original Bitbucket issue. 
Due to GitHub API limitations, the file content is available 
in the migration artifacts directory.*
```

### 3. Open the GitHub Issue

Navigate to: `https://github.com/OWNER/REPO/issues/NUMBER`

### 4. Upload the File

**Option A: Add New Comment with File**
1. Scroll to bottom of issue
2. Click in the comment text box
3. Drag `attachments_temp/screenshot.png` into the box
4. You'll see upload progress
5. File URL appears: `![screenshot](https://github.com/...)`
6. Add any text if desired
7. Click "Comment"

**Option B: Edit Existing Attachment Comment**
1. Find the comment that says "📎 Attachment from Bitbucket"
2. Click "..." menu → "Edit"
3. Drag the file into the comment editor
4. Update text if needed
5. Click "Update comment"

### 5. Verify Upload

- Image files will preview inline
- Other files show as download links
- File is now hosted by GitHub permanently

## Bulk Upload with GitHub CLI

For many attachments:

```bash
# Install GitHub CLI
brew install gh  # macOS
# or from https://cli.github.com

# Authenticate
gh auth login

# Upload script
#!/bin/bash
cd attachments_temp

# Assuming you have a mapping file
while IFS=',' read -r file issue_num; do
  echo "Uploading $file to issue #$issue_num"
  gh issue comment "$issue_num" \
    --repo OWNER/REPO \
    --body "**Attachment:** $file" \
    --attach "$file"
  sleep 2  # Rate limiting
done < attachment_mapping.csv
```

## Prioritization Guide

### Critical (Upload First)
- Screenshots showing bugs/issues
- Design mockups currently in use
- Important documents referenced in active discussions
- Configuration files that are templates
- Error logs for open issues

**How to identify:**
- Recent attachments (last 6 months)
- On open issues
- Multiple comments referencing them
- Large files (important enough to be big)

### Medium Priority
- Historical screenshots
- Log files for closed issues
- Test data that might be useful
- Documentation files

### Low Priority (Optional)
- Temporary/scratch files
- Files available elsewhere
- Outdated documents
- Files on resolved issues from 1+ year ago

### Skip Entirely
- Broken/corrupt files
- Duplicate files
- Files explicitly marked as "temp"
- Auto-generated files

## Attachment Tracking Template

Create a file `attachment-status.md`:

```markdown
# Attachment Upload Status

## Summary
- Total Attachments: 8
- Uploaded: 3
- Pending: 5
- Skipped: 0

## Upload Log

### Critical
- [x] Issue #5: `screenshot.png` (2.3 MB) - Uploaded by Alice on 2025-10-18
- [x] Issue #12: `design-mockup.pdf` (5.1 MB) - Uploaded by Bob on 2025-10-18
- [ ] Issue #23: `error-log.txt` (150 KB) - **PENDING**

### Important
- [ ] Issue #34: `config-example.json` (12 KB)
- [ ] Issue #45: `performance-graph.png` (890 KB)

### Optional
- [ ] Issue #67: `old-screenshot.png` (1.1 MB)
- [ ] Issue #89: `temp-data.csv` (45 KB)

### Skipped
- Issue #100: `outdated-mockup.pdf` - Superseded by #12
```

## Tips & Tricks

### 1. Preview Before Upload
```bash
# For images
open attachments_temp/screenshot.png

# For text files
cat attachments_temp/error-log.txt | head -20
```

### 2. Check File Size
```bash
ls -lh attachments_temp/
# GitHub has 25MB limit for web uploads
# Larger files need Git LFS or external hosting
```

### 3. Rename Confusing Files
```bash
cd attachments_temp/
mv "Screen Shot 2024-01-15.png" "issue-5-login-error.png"
```

### 4. Create Issue Links Document
```bash
# Map files to issues
grep "Attachment from Bitbucket" ~/migration.log > attachment-map.txt
```

### 5. Backup Before Cleanup
```bash
# After uploading everything important
tar -czf attachments_backup_$(date +%Y%m%d).tar.gz attachments_temp/
mv attachments_backup_*.tar.gz ~/migration_backups/
```

## Common Issues

### Upload Fails (File Too Large)
**Problem:** File >25MB  
**Solution:** 
- Use Git LFS for very large files
- Upload to Google Drive/Dropbox and add link in comment
- Compress file if possible

### Wrong Issue
**Problem:** Uploaded to wrong issue  
**Solution:**
- Delete the comment
- Re-upload to correct issue
- Or just add a new comment on correct issue

### File Type Not Supported
**Problem:** Executable or restricted file type  
**Solution:**
- Zip the file first
- Upload to external storage and link
- Convert to allowed format if possible

### Lost Track of Which File Goes Where
**Problem:** Forgot which attachment belongs to which issue  
**Solution:**
- Search GitHub for "Attachment from Bitbucket" comments
- Check original Bitbucket issue
- Look at file creation dates vs issue dates

## Cleanup After Upload

### Wait Period
Keep `attachments_temp/` for at least 30 days after migration to ensure:
- All critical files uploaded
- Team had time to request any missing files
- No issues discovered requiring original files

### Backup Before Delete
```bash
# Create archive
cd ..
tar -czf migration_attachments_$(date +%Y%m%d).tar.gz attachments_temp/

# Move to safe location
mv migration_attachments_*.tar.gz ~/backups/

# Verify archive
tar -tzf ~/backups/migration_attachments_*.tar.gz | head
```

### Final Cleanup
```bash
# After 30+ days and team confirmation
rm -rf attachments_temp/

# Keep these files permanently
# - migration_mapping.json
# - audit_report.md  
# - migration_attachments_YYYYMMDD.tar.gz (backup)
```

## Team Communication Template

Send this to your team:

```markdown
Subject: Action Required - Upload Attachments After Migration

Hi Team,

The migration to GitHub is complete! However, attachments need manual upload.

**What You Need to Do:**

1. Review the attachment list: [link to attachment-status.md]
2. Upload critical attachments from your areas
3. Mark them as complete in the tracking doc

**How to Upload:**
1. Find your file in: attachments_temp/
2. Open the GitHub issue  
3. Drag and drop the file into a comment
4. Done!

**Priority:**
- Critical: This week
- Important: Within 2 weeks
- Optional: If time permits

**Questions?**
See: [link to this guide]

Thanks!
```

## Metrics to Track

- Total attachments: `ls attachments_temp/ | wc -l`
- Total size: `du -sh attachments_temp/`
- Uploaded count: Track in status document
- Time spent: Estimate ~2-5 minutes per file

## Success Criteria

✅ All critical attachments (top 20%) uploaded within 1 week  
✅ Important attachments (next 30%) uploaded within 2 weeks  
✅ Team has access to all files they need  
✅ Original files backed up  
✅ Tracking document maintained  
✅ No blockers due to missing attachments  

---

**Remember:** You have the original files in Bitbucket as backup. No rush to upload everything immediately. Focus on what the team actually needs!