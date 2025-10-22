# Milestones Migration

## What Gets Migrated
Milestones are automatically created on GitHub during migration:

- **Name**: Preserved exactly from Bitbucket
- **State**: Created as 'open' by default
- **Assignment**: Applied to issues that had milestones in Bitbucket

## What IS Preserved
- ✅ **Milestone Names**: Created on GitHub with exact names.
- ✅ **Milestone Descriptions**: Migrated from Bitbucket if present.
- ✅ **Due Dates**: Migrated and set on GitHub milestones.
- ✅ **Issue Associations**: Issues are assigned to correct milestones.
- ✅ **PR Associations**: PRs (and PRs-as-issues) are assigned to correct milestones.
- ✅ **Milestone Mapping**: Tracked in migration report.

## What Is NOT Preserved
- ❌ **Completion Percentage**: Calculated by GitHub based on closed issues.
- ❌ **Milestone State**: All created as 'open' (GitHub updates based on issue completion).

## Handling Non-Migratable Information
- **Duplicate Names**: If milestone already exists on GitHub, existing one is used.
- **Creation Tracking**: All created/mapped milestones listed in migration report.
- **Pre-Creation**: All milestones are created upfront before issue/PR migration begins.
