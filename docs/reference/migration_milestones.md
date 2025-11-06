# Milestones Migration

## Overview
Milestones are automatically migrated from Bitbucket to GitHub during the migration process. The migration preserves milestone metadata and assigns issues and PRs to their corresponding milestones.

## What Gets Migrated

### Milestone Properties
- ✅ **Name**: Preserved exactly from Bitbucket
- ✅ **Description**: Migrated if present in Bitbucket
- ✅ **Due Date**: Migrated and converted to GitHub format
- ✅ **State**: Preserved ('open' or 'closed')

### Assignments
- ✅ **Issue Associations**: Issues are assigned to correct milestones
- ✅ **PR Associations**: PRs (and PRs-as-issues) are assigned to correct milestones

### Tracking
- ✅ **Milestone Mapping**: Tracked in migration report
- ✅ **Duplicate Detection**: Existing milestones reused, not recreated

## What Is NOT Preserved
- ❌ **Completion Percentage**: Calculated by GitHub based on closed issues
- ❌ **Creation/Update Timestamps**: Set to migration time on GitHub

## Migration Process

### Phase 1: Milestone Creation
1. Fetch all milestones from Bitbucket
2. Fetch existing milestones from GitHub (to detect duplicates)
3. For each Bitbucket milestone:
   - Check if milestone with same name already exists
   - If duplicate: Log warning and use existing milestone
   - If new: Create milestone on GitHub with all properties
4. Build milestone lookup table for issue/PR assignment

### Phase 2: Issue/PR Assignment
1. During issue migration, assign milestone based on Bitbucket data
2. During PR migration, assign milestone for both PRs and PRs-as-issues
3. Log warnings if milestone referenced but not found

## Duplicate Handling

When a milestone name already exists on GitHub:
- ⚠️ **Warning logged**: "Milestone '{name}' already exists on GitHub (#{number})"
- ✅ **Existing milestone reused**: No new milestone created
- ✅ **Issues/PRs assigned**: To the existing milestone
- ℹ️ **Reported**: Marked as duplicate in migration report

## Error Handling

### Common Issues
1. **Invalid due date format**: Logged as error, milestone created without due date
2. **Missing required fields**: Milestone creation skipped, logged as warning
3. **API errors**: Retried with exponential backoff, logged appropriately
4. **Permission errors**: Clear error message indicating token permissions needed

### Recovery
- Milestone migration errors don't stop issue/PR migration
- Issues/PRs can be manually assigned to milestones post-migration
- Failed milestones can be recreated manually or by re-running migration

## Migration Report

The migration report includes:
- Total milestones processed
- Successfully created vs. duplicates
- Milestone properties (name, state, due date, description)
- Issues/PRs assigned to each milestone
- Any warnings or errors encountered

### Example Report Section

```markdown
## Milestones

**Total Milestones Processed:** 5
  - Created on GitHub: 3
  - Already Existed (Duplicates): 2

| Name | GitHub # | State | Due Date | Description | Remarks |
|------|----------|-------|----------|-------------|---------|
| Sprint 1 | #1 | closed | 2024-01-31 | Initial development phase | - |
| Version 1.0 | #2 | open | 2024-06-30 | First major release | - |
| Version 2.0 | #3 | open | - | Second major release | Reused existing milestone |
```

## Logging Output

During migration, you'll see detailed logging for milestone operations:

```
Creating milestones on GitHub...
  Found 5 milestones in Bitbucket
  Found 2 existing milestones on GitHub
  Processing milestone: Version 1.0
    ✓ Created milestone #1: Version 1.0
  Processing milestone: Version 2.0
    ⚠️  Milestone 'Version 2.0' already exists on GitHub (#2)
  ✓ Milestone migration complete:
    Created: 3
    Reused (duplicates): 2

Migrating issue #42: Fix login bug
  Assigning to milestone: Version 1.0 (#1)
  ✓ Created issue #42 -> #42
```

## Configuration

No special configuration required. Milestones are migrated automatically.

### Token Permissions
Ensure GitHub token has `repo` scope for milestone creation.

## Manual Post-Migration Steps

If needed, you can:
1. Adjust milestone due dates
2. Update milestone descriptions
3. Close completed milestones
4. Reassign issues/PRs to different milestones

## API References

- **Bitbucket**: `GET /2.0/repositories/{workspace}/{repo}/milestones`
- **GitHub**: `POST /repos/{owner}/{repo}/milestones`
- **GitHub**: `GET /repos/{owner}/{repo}/milestones`

## Implementation Details

### Components

1. **MilestoneMigrator**
   - Handles all milestone migration logic
   - Performs duplicate detection
   - Creates milestones with full metadata

2. **GitHubClient Methods**
   - `get_milestones()`: Fetch all milestones with pagination
   - `get_milestone_by_title()`: Find milestone by exact title
   - `create_milestone()`: Create new milestone with metadata

3. **RepoMigrator Integration**
   - Calls milestone migration before issues/PRs
   - Passes milestone lookup to migrators
   - Tracks records for reporting

*Note: These components are part of the source code in the `src/bitbucket_migration/` directory.*

### Migration Flow

```
1. RepoMigrator._create_milestones()
   ↓
2. MilestoneMigrator.migrate_milestones()
   ↓
3. Fetch Bitbucket milestones
   ↓
4. Fetch existing GitHub milestones
   ↓
5. For each milestone:
   - Check duplicates
   - Create if new OR use existing
   ↓
6. Return milestone_lookup dict
   ↓
7. IssueMigrator/PullRequestMigrator
   - Use lookup to assign milestones
```

## Troubleshooting

### Milestone Not Assigned to Issue

**Symptoms**: Issue migrated but no milestone assigned

**Causes**:
- Milestone name in Bitbucket doesn't match created milestone
- Milestone creation failed but issue migration continued
- Milestone was in Bitbucket but not fetched by API

**Solutions**:
1. Check migration log for milestone warnings
2. Verify milestone exists on GitHub
3. Manually assign milestone post-migration

### Duplicate Milestone Created

**Symptoms**: Two milestones with same/similar names on GitHub

**Causes**:
- Name matching is case-sensitive
- Whitespace differences in names

**Solutions**:
1. Merge duplicate milestones on GitHub
2. Reassign issues/PRs to correct milestone
3. Delete extra milestone

### Invalid Due Date Error

**Symptoms**: Milestone created but without due date

**Causes**:
- Invalid date format from Bitbucket
- Date parsing error

**Solutions**:
- Milestone still created successfully
- Manually set due date on GitHub
- Check migration log for details

## Best Practices

1. **Pre-Migration**:
   - Review Bitbucket milestones before migrating
   - Clean up duplicate or unused milestones
   - Verify milestone names are consistent

2. **During Migration**:
   - Monitor logs for milestone warnings
   - Note any duplicates detected
   - Track failed milestone creations

3. **Post-Migration**:
   - Verify all milestones created correctly
   - Check issue/PR milestone assignments
   - Update milestone due dates if needed
   - Close completed milestones

## Dry-Run Mode

Milestone migration fully supports dry-run mode:
- Simulates milestone creation
- Returns mock milestone data
- Logs all actions that would be taken
- No actual GitHub API calls made
- Safe for testing configuration
