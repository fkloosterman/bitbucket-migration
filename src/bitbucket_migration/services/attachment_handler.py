import requests
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ..clients.github_cli_client import GitHubCliClient

logger = logging.getLogger('bitbucket_migration')

class AttachmentHandler:
    def __init__(self, attachment_dir: Path, gh_cli_client: Optional[GitHubCliClient] = None, dry_run: bool = False):
        self.attachment_dir = attachment_dir
        self.attachment_dir.mkdir(exist_ok=True)
        self.gh_cli_client = gh_cli_client
        self.use_gh_cli = gh_cli_client is not None
        self.dry_run = dry_run
        self.attachments: List[Dict] = []
    
    def download_attachment(self, url: str, filename: str, item_type: str = None, item_number: int = None, comment_seq: int = None) -> Optional[Path]:
        """Download attachment from Bitbucket

        Args:
            url: The attachment URL
            filename: The filename to save as
            item_type: 'issue' or 'pr' (optional)
            item_number: The issue or PR number (optional)
            comment_seq: Comment sequence number if attachment is from a comment (optional)
        """
        filepath = self.attachment_dir / filename
        if self.dry_run:
            # In dry-run, just record without downloading
            self.attachments.append({
                'filename': filename,
                'filepath': str(filepath),
                'item_type': item_type,
                'item_number': item_number,
                'comment_seq': comment_seq
            })
            return filepath
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            self.attachments.append({
                'filename': filename,
                'filepath': str(filepath),
                'item_type': item_type,
                'item_number': item_number,
                'comment_seq': comment_seq
            })
            return filepath
        except Exception as e:
            logger.error("Failed to download attachment %s: %s", filename, e, extra={'filename': filename, 'error': str(e)})
            return None
    
    def upload_to_github(self, filepath: Path, issue_number: int, github_client, gh_owner: str, gh_repo: str) -> Optional[str]:
        """Upload attachment to GitHub issue"""
        if self.use_gh_cli and self.gh_cli_client:
            return self.gh_cli_client.upload_attachment(filepath, issue_number, gh_owner, gh_repo)
        else:
            return self._create_upload_comment(filepath, issue_number, github_client)
    
    
    def _create_upload_comment(self, filepath: Path, issue_number: int, github_client) -> str:
        """Create comment noting attachment for manual upload"""
        file_size = filepath.stat().st_size
        size_mb = round(file_size / (1024 * 1024), 2)
        
        comment_body = f'''📎 **Attachment from Bitbucket**: `{filepath.name}` ({size_mb} MB)

*Note: This file was attached to the original Bitbucket issue. Please drag and drop this file from `{self.attachment_dir}/{filepath.name}` to embed it in this issue.*
'''
        github_client.create_comment(issue_number, comment_body)
        return comment_body

    def extract_and_download_inline_images(self, text: str, use_gh_cli: bool = False, item_type: str = None, item_number: int = None, comment_seq: int = None) -> tuple:
        """Extract Bitbucket-hosted inline images from markdown and download them.

        Args:
            text: The markdown text to process
            use_gh_cli: Whether to use GitHub CLI for uploads
            item_type: 'issue' or 'pr' (optional)
            item_number: The issue or PR number (optional)
            comment_seq: Comment sequence number if processing a comment (optional)
        """
        if not text:
            return text, []

        import re

        # Pattern to match markdown images: ![alt](url)
        image_pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'

        downloaded_images = []
        images_found = 0

        def replace_image(match):
            nonlocal images_found
            alt_text = match.group(1)
            image_url = match.group(2)

            # Only process Bitbucket-hosted images
            if 'bitbucket.org' in image_url or 'bytebucket.org' in image_url:
                images_found += 1

                # Extract filename from URL
                filename = image_url.split('/')[-1].split('?')[0]
                if not filename or filename == '':
                    filename = f"image_{images_found}.png"

                # Download the image with context
                filepath = self.download_attachment(image_url, filename, item_type=item_type, item_number=item_number, comment_seq=comment_seq)
                if filepath:
                    downloaded_images.append({
                        'filename': filename,
                        'url': image_url,
                        'filepath': str(filepath)
                    })

                    if self.dry_run:
                        return f"![{alt_text}]({image_url})\n\n📷 *Inline image: `{filename}` (will be downloaded to {self.attachment_dir})*"
                    elif use_gh_cli:
                        # With gh CLI, the image will be uploaded, so just keep the markdown
                        return f"![{alt_text}]({image_url})\n\n📷 *Original Bitbucket image (will be uploaded via gh CLI)*"
                    else:
                        # Return modified markdown with note about manual upload
                        return f"![{alt_text}]({image_url})\n\n📷 *Original Bitbucket image (download from `{self.attachment_dir}/{filename}` and drag-and-drop here)*"
                else:
                    # Failed to download
                    return match.group(0)
            else:
                # Return unchanged for non-Bitbucket images
                return match.group(0)

        updated_text = re.sub(image_pattern, replace_image, text)

        return updated_text, downloaded_images