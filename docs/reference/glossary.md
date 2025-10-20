
# Glossary

| Term                            | Definition                                                             |
| ------------------------------- | ---------------------------------------------------------------------- |
| **API Token**                   | Authentication credential used for accessing Bitbucket or GitHub APIs. |
| **App Password**                | Legacy Bitbucket auth method, deprecated as of Sept 2025.              |
| **Audit Report**                | Markdown summary file produced during `audit_bitbucket.py` run.        |
| **Dry Run**                     | Mode that simulates migration without creating data on GitHub.         |
| **Git Mirror Push**             | Exact copy of all branches, tags, and commits to new remote.           |
| **Placeholder Issue**           | Empty issue used to preserve issue numbering sequence.                 |
| **PR (Pull Request)**           | Proposed code change reviewed before merging.                          |
| **PAT (Personal Access Token)** | GitHub token that authenticates API requests.                          |
| **Rate Limiting**               | Restriction on the number of API requests per time window.             |
| **User Mapping**                | JSON table linking Bitbucket usernames to GitHub equivalents.          |
| **Migration Mapping**           | JSON output showing Bitbucket → GitHub issue/PR correspondence.        |
| **LFS (Large File Storage)**    | Git extension for storing large binary files outside Git history.      |
| **Attachment Comment**          | GitHub issue comment noting migrated Bitbucket attachment.             |
| **Verification Checklist**      | Post-migration validation list ensuring data completeness.             |

---
