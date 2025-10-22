# Comments Migration

## What Gets Migrated
Comments are added to issues/PRs with attribution:

```markdown
**Comment by @alice-github on 2023-05-15:**

[Original comment text]
```

## What IS Preserved
- ✅ **Comment Text**: Full content including markdown.
- ✅ **Original Author**: @tagged for notifications.
- ✅ **Original Timestamp**: Noted in comment.
- ✅ **Link Rewrites**: Cross-references updated to GitHub URLs.
- ✅ **@Mentions**: Updated to GitHub usernames.
- ✅ **Attachments**: Downloaded and noted (see Attachments section).

## What Is NOT Preserved
- ❌ **Comment Author**: Shows as migration account.
- ❌ **Comment Date**: Shows as migration date.
- ❌ **Comment Edit History**: Only final version migrated.
- ❌ **Threaded Replies**: Flattened to sequential comments.
- ❌ **Inline Code Comments**: PR code review comments are not migrated.
- ❌ **Resolved/Unresolved Status**: Comment resolution status not preserved.
