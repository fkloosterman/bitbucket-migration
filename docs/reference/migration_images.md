# Images Migration

## Overview
Inline images are images embedded in markdown content using `![alt](url)` syntax. Unlike traditional attachments, these are part of the text content and are handled during content formatting.

## Migrated Metadata
- **Image URLs in Markdown**: Preserved in text, with notes for manual upload.
- **Alt Text**: Maintained in markdown syntax.
- **Bitbucket-Hosted Inline Images**: Automatically detected and extracted from markdown.

## What Gets Detected
The script scans for:

- Markdown image syntax: `![alt](https://bitbucket.org/.../image.png)`
- Images in issue/PR descriptions
- Images in comments
- Bitbucket-hosted images only (external URLs preserved as-is)

## What Gets Created
Inline images are modified in the markdown content with upload instructions:

### Dry Run Mode
```markdown
![Screenshot](https://bitbucket.org/workspace/repo/images/screenshot.png)

📷 *Inline image: `screenshot.png` (will be downloaded to attachments_temp)*
```

### Manual Upload (Default)
```markdown
![Screenshot](https://bitbucket.org/workspace/repo/images/screenshot.png)

📷 *Original Bitbucket image (download from `attachments_temp/screenshot.png` and drag-and-drop here)*
```

### Auto-Upload with GitHub CLI
```markdown
![Screenshot](https://bitbucket.org/workspace/repo/images/screenshot.png)

📷 *Original Bitbucket image (will be uploaded via gh CLI)*
```

## Handling Non-Migratable Information
- **Bitbucket-Hosted Images**: Detected and downloaded to `attachments_temp/`.
- **Inline Image Detection**: Scans issue/PR descriptions and comments for `![alt](url)` syntax.
- **Upload Notes**: Added to descriptions/comments indicating where to find and upload images.
- **With gh CLI**: Images are noted for upload; manual integration into comments may be needed due to gh CLI limitations with comment edits.
- **External Images**: Images hosted elsewhere (imgur, etc.) are left as-is.

## Difference from Attachments
- **Inline Images**: Embedded in markdown content using `![alt](url)` syntax
- **Traditional Attachments**: Explicitly attached files via Bitbucket's attachment interface
- **Processing**: Both are downloaded to `attachments_temp/`, but inline images modify the markdown content directly (see [Attachments Migration](migration_attachments.md))
