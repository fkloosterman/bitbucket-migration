---
hide:
#   - navigation
#   - toc
---

# Migration Reference

This reference document provides detailed information on how specific elements from Bitbucket are migrated to GitHub, including what metadata is preserved and how non-migratable information is handled.

## Overview

The migration script preserves as much metadata as possible while adapting to GitHub's structure. For elements that cannot be directly migrated (e.g., due to API limitations or platform differences), the script adds contextual notes to descriptions or comments to maintain transparency.

## Migration Strategy

### Issue Migration
- All Bitbucket issues become GitHub issues
- Original numbers are preserved using placeholder issues for gaps
- Example: BB issues #1, #2, #5 → GH issues #1, #2, #3 (placeholder), #4 (placeholder), #5

### Pull Request Migration
The script uses an intelligent strategy:

- **OPEN PRs with existing branches** → GitHub PRs (remain open)
- **OPEN PRs with missing branches** → GitHub Issues
- **MERGED/DECLINED/SUPERSEDED PRs** → GitHub Issues (safest approach to avoid re-merging)

This prevents accidentally re-merging already-merged code while preserving all metadata.

## Known Limitations

### API Restrictions
These limitations are imposed by GitHub's API and cannot be worked around:

- **No backdating**: GitHub API doesn't allow setting creation dates - all migrated content shows today's date
- **No author spoofing**: Cannot create content as other users - all content shows migration account as author
- **No PR reviewers**: Cannot set reviewers during PR creation via API
- **No attachment uploads**: Direct file upload not supported by standard GitHub API
- **No code review comments**: Inline PR code review comments cannot be migrated via API
- **No edit history**: Only the final version of content is migrated
- **No watchers**: Cannot set issue/PR watchers via API

### Platform Differences
- **Shared Numbering**: GitHub PRs and issues share the same numbering sequence
- **No Issue Types**: GitHub doesn't have 'bug', 'enhancement', etc. as built-in fields (noted in description)
- **No Priority**: GitHub doesn't have priority levels (noted in description)
- **No Wiki API**: Bitbucket wikis must be migrated separately

### Workarounds Implemented
- **Timestamps**: Noted in descriptions/comments with original dates
- **Authors**: @mentioned for notifications and transparency
- **Reviewers**: Listed in PR description for reference
- **Attachments**: Downloaded locally, uploaded manually or via `--use-gh-cli`
- **Issue Types/Priority**: Noted in description for reference
- **Deleted Issue Numbers**: Filled with placeholder issues to preserve numbering

## Why This Matters

Understanding what is preserved vs. not preserved has important implications for your team:

### Activity History is Lost
- Issues and PRs show as created by the migration account
- Affects contribution stats and team metrics
- Cannot filter by "author:alice" in GitHub searches
- All activity credit goes to migration account

### Notifications and Transparency
- **@Mentions Notify Real Users**: Original authors are @tagged in descriptions, so they receive notifications and know issues reference them
- **Clear Attribution**: Every issue/PR/comment clearly states original author and date
- **Transparency**: Notes like "Migrated from Bitbucket" make the migration obvious

### Continuity Preserved
- **Assignees are Preserved**: Work assignments remain intact, ensuring continuity
- **Milestones Maintained**: Project planning structure preserved
- **Cross-References Work**: Links between issues/PRs updated to point to GitHub

### Search and Discovery
- **Searchability Affected**: Original creation dates are not preserved, so time-based searches will use migration dates
- **Content Searchable**: All text content is fully searchable in GitHub
- **Link Navigation**: Cross-references between issues work correctly

### Manual Work Required
- **Attachments**: Must be uploaded manually unless using `--use-gh-cli`
- **Inline Images**: May need manual integration into comments
- **Unhandled Links**: Some Bitbucket links require manual updates post-migration
- **Unmapped Users**: Users without GitHub accounts should be mapped if they later join

This trade-off prioritizes preserving actionable information (assignees, @mentions, cross-references) over historical accuracy (exact authors/dates), while maintaining transparency through descriptive notes. The migration report provides detailed information about what was migrated and what needs manual attention.

## Migration Details

<div class="grid cards" style="text-align: center;" markdown="1">

- **[Issues](migration_issues.md)**

- **[Pull Requests](migration_pull_requests.md)**

- **[Comments](migration_comments.md)** 

- **[Attachments](migration_attachments.md)**

- **[Images](migration_images.md)**

- **[Links and Cross-Links](migration_links.md)**

- **[@Mentions](migration_mentions.md)**

- **[Milestones](migration_milestones.md)**

</div>