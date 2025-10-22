# Attachments Migration

## Migrated Metadata
- **File Name and Size**: Noted in GitHub comments.
- **Association to Issues/PRs**: Comments indicate which issue/PR the attachment belongs to.
- **Download Location**: All files saved to `attachments_temp/` for reference.

## What Gets Created
Comments are added to issues/PRs noting attachments:

```markdown
📎 **Attachment from Bitbucket**: `screenshot.png` (2.5 MB)

*Note: This file was attached to the original Bitbucket issue. Please drag and drop this file from `attachments_temp/screenshot.png` to embed it in this issue.*
```

Or with `--use-gh-cli`:

```markdown
📎 **Attachment from Bitbucket**: `screenshot.png` (2.5 MB)
```
(File automatically uploaded and embedded)

## Handling Non-Migratable Information
- **Direct Upload**: GitHub API does not support direct attachment upload; files are downloaded locally to `attachments_temp/`.
- **Manual Upload Required**: Comments are created on GitHub issues with instructions to drag-and-drop files.
- **Auto-Upload Option**: With `--use-gh-cli`, attachments are uploaded automatically using GitHub CLI.
- **Inline Images**: Treated as attachments; extracted from markdown and downloaded separately.
- **Large Files**: Files are downloaded regardless of size; GitHub has its own upload limits.
