# Attachments Migration

## Overview
Attachments are files that were explicitly attached to Bitbucket issues or pull requests. The migration tool handles both traditional attachments and inline images embedded in markdown content.

## Migrated Metadata
- **File Name and Size**: Noted in GitHub comments.
- **Association to Issues/PRs**: Comments indicate which issue/PR the attachment belongs to.
- **Download Location**: All files saved to `attachments_temp/` for reference.

## What Gets Created
Comments are added to issues/PRs noting attachments:

### Attachment Comments
```markdown
📎 **Attachment from Bitbucket**: `screenshot.png` (2.5 MB)

*Note: This file was attached to the original Bitbucket issue. Please drag and drop this file from `attachments_temp/screenshot.png` to embed it in this issue.*
```

## Handling Non-Migratable Information
- **Direct Upload**: GitHub API does not support direct attachment upload; files are downloaded locally to `attachments_temp/`.
- **Manual Upload Required**: Comments are created on GitHub issues with instructions to drag-and-drop files.
- **Informative Comments**: The tool creates helpful comments with file names, sizes, and local paths for each attachment.
- **Large Files**: Files are downloaded regardless of size; GitHub has its own upload limits.

## Difference from Inline Images
- **Attachments**: Explicitly attached files via Bitbucket's attachment interface
- **Inline Images**: Images embedded in markdown content using `![alt](url)` syntax
- **Processing**: Both are downloaded to `attachments_temp/`, but inline images are handled differently in content formatting (see [Images Migration](migration_images.md))
