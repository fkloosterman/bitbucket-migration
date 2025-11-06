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
- ❌ **Comment Edit History**: Only final version migrated. Content changes are noted in the comment body but edit history is not preserved.
- ❌ **Threaded Replies**: For PRs migrated as issues, replies are flattened with notes. For PRs migrated as PRs, inline review comments support threading.
- ❌ **Inline Code Comments**: PR code review comments are migrated as regular comments with code context information when inline attachment fails.
- ❌ **Resolved/Unresolved Status**: Comment resolution status not preserved.

## Special Handling
- ✅ **Deleted Comments**: Comments marked as deleted in Bitbucket are skipped during migration to avoid data pollution.
- ✅ **Pending Comments**: Comments marked as pending approval in Bitbucket are migrated with a clear annotation: **[PENDING APPROVAL]** at the top of the comment body.
- ✅ **Threaded Replies**:
  - For PRs migrated as GitHub PRs, inline review comments support threading using GitHub's `in_reply_to` field.
  - For PRs migrated as issues or other cases, replies are flattened with a note: **[Reply to Bitbucket Comment {ID}]**.
  - Comments are processed in topological order to ensure parents are created before replies.
