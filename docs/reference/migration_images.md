# Images Migration

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

## Handling Non-Migratable Information
- **Bitbucket-Hosted Images**: Detected and downloaded to `attachments_temp/`.
- **Inline Image Detection**: Scans issue/PR descriptions and comments for `![alt](url)` syntax.
- **Upload Notes**: Added to descriptions/comments indicating where to find and upload images.
- **With gh CLI**: Images are noted for upload; manual integration into comments may be needed due to gh CLI limitations with comment edits.
- **External Images**: Images hosted elsewhere (imgur, etc.) are left as-is.
