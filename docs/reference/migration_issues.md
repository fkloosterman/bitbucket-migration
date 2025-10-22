# Issues Migration

## What Gets Migrated
Issues are created on GitHub with the following structure:

```markdown
**Migrated from Bitbucket**
- Original Author: @alice-github (or **Alice Smith** *(no GitHub account)*)
- Original Created: 2023-05-15T10:30:00Z
- Original URL: https://bitbucket.org/...
- Kind: bug
- Priority: major

---

[Original issue description]
```

GitHub displays:

- **Reporter**: Your migration account (the person running the script)
- **Created Date**: Today (migration date)
- **Assignee**: Can be set if mapped (API supports this)

## What IS Preserved
- ✅ **Issue Numbers**: Preserved exactly from Bitbucket (placeholders fill gaps).
- ✅ **Title**: Migrated as-is.
- ✅ **Description**: Full content with markdown preserved.
- ✅ **Assignees**: Set via API if user mapping exists.
- ✅ **Labels**: Applied (e.g., 'migrated-from-bitbucket').
- ✅ **Milestones**: Automatically created on GitHub and applied to issues.
- ✅ **State (open/closed)**: Set based on original state.
- ✅ **Original Timestamps**: Mentioned in description.
- ✅ **Original Authors**: Mentioned and @tagged in description for notifications.
- ✅ **Votes**: Noted in description.
- ✅ **Kind and Priority**: Noted in description.

## What Is NOT Preserved
- ❌ **Original Author as Creator**: API limitation - migration account is shown as creator.
- ❌ **Original Creation Date**: API limitation - shows migration date.
- ❌ **Watchers**: No equivalent field in GitHub.
- ❌ **Custom Fields**: Bitbucket custom fields are not migrated.

## Handling Non-Migratable Information
- **Deleted Users**: Noted as "Unknown (deleted user)" in description and comments.
- **Unmapped Users**: Mentioned as "**Name** *(no GitHub account)*" in description; not assigned.
- **Placeholders for Gaps**: Issues deleted in Bitbucket are created as closed placeholder issues to maintain numbering.
- **Attachments and Images**: See [Attachment Migration](migration_attachments.md) and [Image Migration](migration_images.md).