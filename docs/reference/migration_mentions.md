# Mentions Migration

## What Gets Migrated
- **@Mentions**: Mapped to GitHub usernames using `user_mapping`.
- **Account IDs**: Automatically resolved by cross-referencing with issue/PR participants, or via Bitbucket API lookup.
- **Display Names**: Used when Bitbucket username is not available.
- **Enhanced User Mapping**: Supports detailed mapping configurations with bitbucket_username, display_name, and github fields.

## Formats Supported
The script handles multiple @mention formats:

- Simple: `@username`
- Braced: `@{username-with-dashes}`
- Spaces: `@{user name with spaces}`
- Account IDs: `@557058:c250d1e9-df76-4236-bc2f-a98d056b56b5`

## What IS Preserved
- ✅ **@Mention Intent**: Users are notified via GitHub @mentions.
- ✅ **Context**: Original mention preserved if unmapped.
- ✅ **Display Names**: Used for readability when username unavailable.

## Handling Non-Migratable Information
- **Unmapped Users**: Preserved as "@username *(Bitbucket user, needs GitHub mapping)*".
- **Account IDs with Display Names**: Replaced with "**Display Name** *(Bitbucket user, no GitHub account)*".
- **Unresolvable Account IDs**: If API lookup fails (403 or deleted user), left as-is with warning note.
- **Deleted Users**: Noted as "Unknown (deleted user)".
- **No GitHub Account**: Users mapped to `null` are mentioned in text but not assigned or @tagged.

## Resolution Process
1. Check if mention is a username or account ID
2. If account ID, resolve to username via:
   - Issue/PR participant data (primary method)
   - Bitbucket API lookup (fallback if not found)
   - Display name only (if username unavailable)
3. Map username/display name to GitHub via `user_mapping`
4. Support enhanced mapping formats with bitbucket_username, display_name, and github fields
5. If mapped: Replace with GitHub @mention
6. If not mapped but have display name: Use readable format
7. If not mapped and no display name: Preserve with note
8. Handle null mappings (users with no GitHub account)
