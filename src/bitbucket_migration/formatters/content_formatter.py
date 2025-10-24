from abc import ABC, abstractmethod
from typing import Dict, Tuple, List, Optional

from ..services.user_mapper import UserMapper
from ..services.link_rewriter import LinkRewriter
from ..services.attachment_handler import AttachmentHandler


class ContentFormatter(ABC):
    """
    Abstract base class for content formatters.

    Content formatters are responsible for formatting different types of content
    (issues, pull requests, comments) from Bitbucket format to GitHub format.
    """

    def __init__(self, user_mapper: UserMapper, link_rewriter: LinkRewriter, attachment_handler: AttachmentHandler):
        """
        Initialize the formatter with required services.

        Args:
            user_mapper: Service for mapping Bitbucket users to GitHub users
            link_rewriter: Service for rewriting links and mentions
            attachment_handler: Service for handling attachments and inline images
        """
        self.user_mapper = user_mapper
        self.link_rewriter = link_rewriter
        self.attachment_handler = attachment_handler

    @abstractmethod
    def format(self, item: Dict, **kwargs) -> Tuple[str, int, List[Dict]]:
        """
        Format content for GitHub.

        Args:
            item: The Bitbucket item to format (issue, PR, comment, etc.)
            **kwargs: Additional formatting options

        Returns:
            Tuple of (formatted_body, links_rewritten_count, inline_images)
        """
        pass


class IssueContentFormatter(ContentFormatter):
    """
    Formatter for Bitbucket issues.
    """

    def format(self, issue: Dict, **kwargs) -> Tuple[str, int, List[Dict]]:
        """
        Format Bitbucket issue for GitHub.

        Args:
            issue: Bitbucket issue data

        Returns:
            Tuple of (formatted_body, links_rewritten_count, inline_images)
        """
        reporter = issue.get('reporter', {}).get('display_name', 'Unknown') if issue.get('reporter') else 'Unknown (deleted user)'
        gh_reporter = self.user_mapper.map_user(reporter) if reporter != 'Unknown (deleted user)' else None

        # Format reporter mention
        if gh_reporter:
            reporter_mention = f"@{gh_reporter}"
        elif reporter == 'Unknown (deleted user)':
            reporter_mention = f"**{reporter}**"
        else:
            reporter_mention = f"**{reporter}** *(no GitHub account)*"

        created = issue.get('created_on', '')
        bb_url = issue.get('links', {}).get('html', {}).get('href', '')
        kind = issue.get('kind', 'bug')
        priority = issue.get('priority', 'major')

        # Rewrite links in the issue content
        content = issue.get('content', {}).get('raw', '')
        content, links_count, unhandled_links, mentions_replaced, mentions_unmapped, unmapped_list = self.link_rewriter.rewrite_links(content, 'issue', issue['id'])

        # Extract and download inline images
        content, inline_images = self.attachment_handler.extract_and_download_inline_images(content, kwargs.get('use_gh_cli', False))

        body = f"""**Migrated from Bitbucket**
- Original Author: {reporter_mention}
- Original Created: {created}
- Original URL: {bb_url}
- Kind: {kind}
- Priority: {priority}

---

{content}
"""
        return body, links_count, inline_images


class PullRequestContentFormatter(ContentFormatter):
    """
    Formatter for Bitbucket pull requests.
    """

    def format(self, pr: Dict, as_issue: bool = False, **kwargs) -> Tuple[str, int, List[Dict]]:
        """
        Format Bitbucket pull request for GitHub.

        Args:
            pr: Bitbucket pull request data
            as_issue: If True, format as an issue (for closed PRs). If False, format as PR.

        Returns:
            Tuple of (formatted_body, links_rewritten_count, inline_images)
        """
        if as_issue:
            return self._format_pr_as_issue(pr, **kwargs)
        else:
            return self._format_pr_as_pr(pr, **kwargs)

    def _format_pr_as_issue(self, pr: Dict, **kwargs) -> Tuple[str, int, List[Dict]]:
        """
        Format PR as an issue (for closed/merged PRs).
        """
        author = pr.get('author', {}).get('display_name', 'Unknown') if pr.get('author') else 'Unknown (deleted user)'
        gh_author = self.user_mapper.map_user(author) if author != 'Unknown (deleted user)' else None

        # Format author mention
        if gh_author:
            author_mention = f"@{gh_author}"
        elif author == 'Unknown (deleted user)':
            author_mention = f"**{author}**"
        else:
            author_mention = f"**{author}** *(no GitHub account)*"

        created = pr.get('created_on', '')
        updated = pr.get('updated_on', '')
        bb_url = pr.get('links', {}).get('html', {}).get('href', '')
        state = pr.get('state', 'UNKNOWN')
        source = pr.get('source', {}).get('branch', {}).get('name', 'unknown')
        dest = pr.get('destination', {}).get('branch', {}).get('name', 'unknown')

        # Rewrite links in the PR description
        description = pr.get('description', '')
        description, links_count, unhandled_links, mentions_replaced, mentions_unmapped, unmapped_list = self.link_rewriter.rewrite_links(description, 'pr', pr['id'])

        # Extract and download inline images
        description, inline_images = self.attachment_handler.extract_and_download_inline_images(description, kwargs.get('use_gh_cli', False))

        body = f"""⚠️ **This was a Pull Request on Bitbucket (migrated as an issue)**

**Original PR Metadata:**
- Author: {author_mention}
- State: {state}
- Created: {created}
- Updated: {updated}
- Source Branch: `{source}`
- Destination Branch: `{dest}`
- Original URL: {bb_url}

---

**Description:**

{description}

---

*Note: This PR was {state.lower()} on Bitbucket. It was migrated as a GitHub issue to preserve all metadata and comments. The actual code changes are in the git history.*
"""
        return body, links_count, inline_images

    def _format_pr_as_pr(self, pr: Dict, **kwargs) -> Tuple[str, int, List[Dict]]:
        """
        Format PR as an actual GitHub PR (for open PRs).
        """
        author = pr.get('author', {}).get('display_name', 'Unknown') if pr.get('author') else 'Unknown (deleted user)'
        gh_author = self.user_mapper.map_user(author) if author != 'Unknown (deleted user)' else None

        # Format author mention
        if gh_author:
            author_mention = f"@{gh_author}"
        elif author == 'Unknown (deleted user)':
            author_mention = f"**{author}**"
        else:
            author_mention = f"**{author}** *(no GitHub account)*"

        created = pr.get('created_on', '')
        bb_url = pr.get('links', {}).get('html', {}).get('href', '')

        # Rewrite links in the PR description
        description = pr.get('description', '')
        description, links_count, unhandled_links, mentions_replaced, mentions_unmapped, unmapped_list = self.link_rewriter.rewrite_links(description, 'pr', pr['id'])

        # Extract and download inline images
        description, inline_images = self.attachment_handler.extract_and_download_inline_images(description, kwargs.get('use_gh_cli', False))

        body = f"""**Migrated from Bitbucket**
- Original Author: {author_mention}
- Original Created: {created}
- Original URL: {bb_url}

---

{description}
"""
        return body, links_count, inline_images


class CommentContentFormatter(ContentFormatter):
    """
    Formatter for Bitbucket comments.
    """

    def format(self, comment: Dict, item_type: str = 'issue', item_number: Optional[int] = None, commit_id: Optional[str] = None, **kwargs) -> Tuple[str, int, List[Dict]]:
        """
        Format Bitbucket comment for GitHub.

        Args:
            comment: Bitbucket comment data
            item_type: 'issue' or 'pr' for link rewriting context
            item_number: The issue/PR number for link rewriting context
            commit_id: Optional commit ID for inline comments

        Returns:
            Tuple of (formatted_comment, links_rewritten_count, inline_images)
        """
        author = comment.get('user', {}).get('display_name', 'Unknown') if comment.get('user') else 'Unknown (deleted user)'
        gh_author = self.user_mapper.map_user(author) if author != 'Unknown (deleted user)' else None

        # Format author mention
        if gh_author:
            author_mention = f"@{gh_author}"
        elif author == 'Unknown (deleted user)':
            author_mention = f"**{author}**"
        else:
            author_mention = f"**{author}** *(no GitHub account)*"

        created = comment.get('created_on', '')
        content = comment.get('content', {}).get('raw', '')

        # Rewrite links in the comment
        content, links_count, unhandled_links, mentions_replaced, mentions_unmapped, unmapped_list = self.link_rewriter.rewrite_links(content, item_type, item_number)

        # Extract and download inline images
        content, inline_images = self.attachment_handler.extract_and_download_inline_images(content, kwargs.get('use_gh_cli', False))

        # Check if this is an inline code comment (for PR comments)
        inline_data = comment.get('inline')
        code_context = ""

        if inline_data:
            # This is an inline comment - add context information
            file_path = inline_data.get('path', 'unknown file')
            line_from = inline_data.get('from')
            line_to = inline_data.get('to')
            start_from = inline_data.get('start_from')
            start_to = inline_data.get('start_to')

            if line_to:
                if start_to and start_to != line_to:
                    line_info = f"lines {start_to}-{line_to}"
                else:
                    line_info = f"line {line_to}"

                if line_from and line_from != line_to:
                    line_info += f" (was line {line_from})"

                code_context = f"\n\n> 💬 **Code comment on `{file_path}` ({line_info})"
                if commit_id:
                    code_context += f" (commit: `{commit_id[:7]}`)"
                code_context += "**\n"

        comment_body = f"""**Comment by {author_mention} on {created}:**
{code_context}
{content}
"""
        return comment_body, links_count, inline_images