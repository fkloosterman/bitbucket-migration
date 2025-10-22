# Pull Requests Migration

## What Gets Migrated
Pull Requests follow a similar pattern to issues:

```markdown
**Migrated from Bitbucket**
- Original Author: @alice-github (or **Alice Smith** *(no GitHub account)*)
- Original Created: 2023-05-15T10:30:00Z
- Original URL: https://bitbucket.org/...

---

[Original PR description]
```

For PRs migrated as GitHub Issues (merged/closed/declined):

```markdown
⚠️ **This was a Pull Request on Bitbucket (migrated as an issue)**

**Original PR Metadata:**
- Author: @alice-github
- State: MERGED
- Created: 2023-05-15T10:30:00Z
- Updated: 2023-05-16T14:22:00Z
- Source Branch: `feature-xyz`
- Destination Branch: `main`
- Original URL: https://bitbucket.org/...

---

**Description:**

[Original PR description]

---

*Note: This PR was merged on Bitbucket. It was migrated as a GitHub issue to preserve all metadata and comments. The actual code changes are in the git history.*
```

GitHub displays:

- **Author**: Migration account (API limitation).
- **Created Date**: Migration date.
- **Assignees**: Can be set if mapped.

## What IS Preserved
- ✅ **Title**: Migrated as-is (prefixed with `[PR #N]` if migrated as issue).
- ✅ **Description**: Full content with markdown preserved.
- ✅ **Assignees**: Set via API if user mapping exists.
- ✅ **Labels**: Applied (e.g., 'migrated-from-bitbucket', 'original-pr', 'pr-merged').
- ✅ **State**: Open PRs remain open; merged/closed PRs become closed issues.
- ✅ **Original Timestamps**: Mentioned in description.
- ✅ **Original Authors**: Mentioned and @tagged in description.
- ✅ **Source/Destination Branches**: Noted in description.
- ✅ **Commit Count**: Noted in description.
- ✅ **Participant Count**: Noted in description.

## What Is NOT Preserved
- ❌ **PR Numbers**: PRs share GitHub's issue numbering sequence, so numbers may change.
- ❌ **Original Author as Creator**: Migration account is shown as author.
- ❌ **Original Creation Date**: Shows migration date.
- ❌ **Reviewers**: Cannot be set via API during creation (noted in description).
- ❌ **Approval Status**: PR reviews cannot be migrated (noted in description).
- ❌ **Code Review Comments**: Inline code comments are not migrated (general comments are).
- ❌ **Diff View**: For PRs migrated as issues, no interactive diff available.

## Handling Non-Migratable Information
- **Merged/Declined PRs**: Migrated as closed issues to preserve metadata without risking re-merge.
- **Missing Branches**: PRs with missing branches become issues; noted in description.
- **Deleted Users**: Noted as "Unknown (deleted user)".
- **Unmapped Users**: Mentioned as "**Name** *(no GitHub account)*".
- **Labels**: Added based on original state (e.g., 'pr-merged', 'pr-declined', 'original-pr').
- **Reviewers**: Listed in PR description but not set as official reviewers.
