import requests
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ..core.migration_context import MigrationEnvironment, MigrationState
from .services_data import AttachmentData


class AttachmentHandler:
    """
    Handles downloading and uploading attachments from Bitbucket to GitHub.

    This class manages the attachment migration process, including downloading
    attachments from Bitbucket, storing them temporarily, and uploading them
    to GitHub issues via the GitHub CLI or by creating manual upload comments.
    """
    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        """
        Initialize the AttachmentHandler.

        Args:
            environment: Migration environment containing config and clients
            state: Migration state for storing attachment data
        """
        self.environment = environment
        self.state = state

        self.data = AttachmentData()
        self.state.services[self.__class__.__name__] = self.data

        self.logger = self.environment.logger

        self.data.attachment_dir = self.environment.base_dir_manager.get_subcommand_dir(
            "dry-run" if self.environment.dry_run else "migrate",
            self.environment.config.bitbucket.workspace,
            self.environment.config.bitbucket.repo
        ) / 'attachments_temp'

        self.data.attachment_dir.mkdir(exist_ok=True)

        self.dry_run = self.environment.dry_run
    
    def download_attachment(self, url: str, filename: str, item_type: str = None, item_number: int = None, comment_seq: int = None) -> Optional[Path]:
        """Download attachment from Bitbucket

        Args:
            url: The attachment URL
            filename: The filename to save as
            item_type: 'issue' or 'pr' (optional)
            item_number: The issue or PR number (optional)
            comment_seq: Comment sequence number if attachment is from a comment (optional)
        """
        filepath = self.data.attachment_dir / filename
        if self.dry_run:
            # In dry-run, just record without downloading
            self.data.attachments.append({
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
            self.data.attachments.append({
                'filename': filename,
                'filepath': str(filepath),
                'item_type': item_type,
                'item_number': item_number,
                'comment_seq': comment_seq
            })
            return filepath
        except Exception as e:
            self.logger.error(f"Failed to download attachment {filename}: {e} (Context: filename={filename}, error={str(e)})")
            return None
    
    def upload_to_github(self, filepath: Path, issue_number: int) -> Optional[str]:
        """
        Upload attachment to GitHub issue.

        Creates a comment with upload instructions for manual attachment upload.

        Args:
            filepath: Path to the attachment file
            issue_number: GitHub issue number to attach to

        Returns:
            The comment body that was created
        """
        return self._create_upload_comment(filepath, issue_number)

    def _create_upload_comment(self, filepath: Path, issue_number: int) -> str:
        """
        Create a comment with instructions for manual attachment upload.

        Args:
            filepath: Path to the attachment file
            issue_number: GitHub issue number

        Returns:
            The comment body that was created
        """
        github_client = self.environment.clients.gh

        file_size = filepath.stat().st_size
        size_mb = round(file_size / (1024 * 1024), 2)

        comment_body = f'''📎 **Attachment from Bitbucket**: `{filepath.name}` ({size_mb} MB)

*Note: This file was attached to the original Bitbucket issue. Please drag and drop this file from `{self.data.attachment_dir}/{filepath.name}` to embed it in this issue.*
'''
        github_client.create_comment(issue_number, comment_body)
        return comment_body

    def extract_and_download_inline_images(self, text: str, item_type: str = None, item_number: int = None, comment_seq: int = None) -> tuple[str, list]:
        """
        Extract Bitbucket-hosted inline images from markdown and download them.

        Processes markdown image syntax ![alt](url) and downloads any images hosted
        on Bitbucket or Bytebucket domains. Updates the markdown with appropriate
        notes for manual upload.

        Args:
            text: The markdown text to process
            item_type: 'issue' or 'pr' (optional, for context tracking)
            item_number: The issue or PR number (optional, for context tracking)
            comment_seq: Comment sequence number if processing a comment (optional)

        Returns:
            Tuple of (updated_text, downloaded_images_list)
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
                        return f"![{alt_text}]({image_url})\n\n📷 *Inline image: `{filename}` (will be downloaded to {self.data.attachment_dir})*"
                    else:
                        # Return modified markdown with note about manual upload
                        return f"![{alt_text}]({image_url})\n\n📷 *Original Bitbucket image (download from `{self.data.attachment_dir}/{filename}` and drag-and-drop here)*"
                else:
                    # Failed to download
                    return match.group(0)
            else:
                # Return unchanged for non-Bitbucket images
                return match.group(0)

        updated_text = re.sub(image_pattern, replace_image, text)

        return updated_text, downloaded_images