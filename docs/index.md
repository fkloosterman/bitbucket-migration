# Bitbucket → GitHub Migration Documentation

Welcome! This documentation explains how to migrate a Bitbucket **Cloud** repository to **GitHub**, using the provided Python migration tools.
It’s designed for **repository administrators, DevOps engineers, and technical leads** who need a reliable, repeatable migration process.

---

## 🚀 Quick Start

| Step | Task                                                                 | Estimated Time | Reference                         |
| ---- | -------------------------------------------------------------------- | -------------- | --------------------------------- |
| 1    | [Run Audit](migration_guide.md#step-1-run-audit)                     | 15–30 min      | Generates audit report and config |
| 2    | [Push Git Mirror](migration_guide.md#step-3-migrate-git-history)     | 15–30 min      | Copies commits, branches, tags    |
| 3    | [Dry Run Migration](migration_guide.md#step-4-dry-run-migration)     | 15 min         | Validate configuration            |
| 4    | [Run Full Migration](migration_guide.md#step-5-run-full-migration) | 1–3 h          | Migrates issues and PRs           |
| 5    | [Upload Attachments](attachment_upload.md)                           | 30–90 min      | Manual step due to API limits     |
| 6    | [Verify & Clean Up](checklists/post_migration.md)                    | 30–60 min      | Validate and finalize repo        |

---

## 📂 Documentation Structure

| Section                                         | Purpose                                  |
| ----------------------------------------------- | ---------------------------------------- |
| [Migration Guide](migration_guide.md)           | Main step-by-step workflow               |
| [Attachment Upload Guide](attachment_upload.md) | Manual process for migrating attachments |
| [Troubleshooting](troubleshooting.md)           | Fix common API or config errors          |
| [Reference](reference/migration_config.md)      | JSON config, API tokens, user mapping    |
| [Checklists](checklists/pre_migration.md)       | Ready-to-use task lists                  |
| [Glossary](reference/glossary.md)               | Key terms used throughout the docs       |

---

## 🧭 Who Should Use This Guide

* **Migration administrators** moving Bitbucket Cloud repos to GitHub.
* **Developers** verifying migrated data (issues, PRs, attachments).
* **Team leads** planning the cutover and post-migration cleanup.

If you only need to upload attachments after migration, skip directly to
➡️ [**Attachment Upload Guide**](attachment_upload.md).

---

## 🛠️ Requirements

* Python **3.7+**
* Git **2.x+**
* Bitbucket Cloud account (API token)
* GitHub account (Personal Access Token with `repo` scope)

See detailed setup in [Prerequisites](migration_guide.md#prerequisites).

---

## 📋 Resources

* [GitHub REST API v3](https://docs.github.com/en/rest)
* [Bitbucket Cloud REST API 2.0](https://developer.atlassian.com/cloud/bitbucket/rest/)
* [GitHub Import Service Docs](https://docs.github.com/en/migrations)

---

## 🕐 Estimated Migration Duration

| Repository Size         | Typical Duration | Notes                         |
| ----------------------- | ---------------- | ----------------------------- |
| Small (≤50 issues)      | 1–2 hours        | Minimal verification          |
| Medium (100–300 issues) | 3–5 hours        | Includes manual upload        |
| Large (500+ issues)     | 6–9 hours        | May require chunked migration |

---

**Next step →** [Start the Migration Guide](migration_guide.md)

---
