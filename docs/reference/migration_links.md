# Links and Cross-Links Migration

## What Gets Rewritten

### Same Repository Links (Automatic)
No configuration needed - these are automatically rewritten:

- **Issues**: `https://bitbucket.org/workspace/repo/issues/42` → `[#45](github_url)` *(was BB #42)*
- **Source Files**: `https://bitbucket.org/.../src/hash/file.cpp#lines-143` → `[file.cpp](github_url#L143)`
- **Commits**: `https://bitbucket.org/.../commits/abc123` → `[abc123](github_url)`
- **Short References**: `#123` → `[#125](github_url)` *(was BB #123)*
- **PR References**: `PR #45` → `[#127](github_url)` *(was BB PR #45, migrated as issue)*

### Cross-Repository Links (Requires Configuration)
Add `repository_mapping` to your config to enable:

- **Repository Home**: `https://bitbucket.org/workspace/other-repo` → `[other-repo](github_url)`
- **Issues**: `https://bitbucket.org/workspace/other-repo/issues/42` → `[other-repo #42](github_url)`
- **Source Files**: `https://bitbucket.org/workspace/other-repo/src/hash/file.cpp` → `[other-repo/file.cpp](github_url)`
- **Commits**: `https://bitbucket.org/workspace/other-repo/commits/abc123` → `[other-repo@abc123d](github_url)`
- **Pull Requests**: `https://bitbucket.org/workspace/other-repo/pull-requests/42` → `[other-repo #42](github_url)`

## What Is NOT Rewritten
- **Wiki Pages**: `https://bitbucket.org/.../wiki/`
- **Downloads**: `https://bitbucket.org/.../downloads/`
- **Branches/Tags**: `https://bitbucket.org/.../branch/feature`
- **New PR/Compare Pages**: UI-specific URLs
- **Repository Images**: `https://bitbucket.org/repo/UUID/images/...`

## Handling Non-Migratable Information
- **Unhandled Links**: Flagged in migration reports with context.
- **Current Repository Links**: Automatically rewritten without needing repository_mapping.
- **Cross-Repo Links**: Can be rewritten if repository_mapping configured in cross_repo_mappings.json.
- **Original References**: Preserved in italics for context (e.g., *(was `[BB #123](bitbucket_url)`)*).
- **Manual Attention**: Unmapped cross-repo links or unsupported types require manual review post-migration.
- **Line Numbers**: Bitbucket's `#lines-143` format converted to GitHub's `#L143`.
- **Deferred Links**: Cross-repo links are processed in a second pass after all repositories are migrated.
