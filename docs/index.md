---
hide:
  - navigation
#   - toc
---

<div style="text-align: center;" markdown="1">

# Bitbucket → GitHub Migration Tools

**Intelligent • Safe • Comprehensive**

Migrate your Bitbucket Cloud repositories to GitHub with confidence using our smart migration platform that preserves everything while making intelligent decisions about PRs, branches, and metadata.

**[🚀 Get Started](#quick-start) • [📖 Full Guide](migration_guide.md)**

</div>

---

<div style="text-align: center;" markdown="1">

## ⚡ Key Features

</div>

<div class="grid cards" style="text-align: center;" markdown="1">

-   **🧠 Smart PR Migration**
    
    ---
    
    Open PRs become GitHub PRs, closed PRs become Issues with full metadata preservation. No more broken references or lost context.
    

-   **🛡️ Safe by Design**
    
    ---
    
    Conservative approach prevents re-merging closed PRs. Comprehensive dry-run validation ensures successful migrations.

-   **🔍 Pre-Migration Audit**
    
    ---
    
    See exactly what will migrate before you start. Get user mapping recommendations and gap analysis automatically.

-   **🔗 Automatic Link Rewriting**
    
    ---
    
    Cross-references between issues and PRs are automatically updated to point to GitHub while preserving original context.

</div>

---

## 🚀 Quick Start

**Install:**
```bash
pipx install bitbucket-migration
```

**Example Usage:**
```bash
audit_bitbucket --workspace YOUR_WORKSPACE --repo YOUR_REPO --generate-config
migrate_bitbucket_to_github --config migration_config.json --dry-run
```

---

## 📚 Documentation

<div class="grid cards" markdown="1">

-   **[📖 Migration Guide](migration_guide.md)**

    Complete step-by-step migration process with detailed explanations, checklists, troubleshooting, and attachment upload instructions.

-   **[⚙️ Migration Config](reference/migration_config.md)**

    Configuration file format, user mapping, and repository mapping options.

-   **[📋 Migration Details](reference/migration_details.md)**

    Detailed reference on what metadata is preserved and how non-migratable information is handled.

-   **[🖥️ CLI Reference](reference/cli_reference.md)**

    Command-line interface guide for audit, migration, and authentication scripts.

-   **[� User Mapping](reference/user_mapping.md)**

    How to map Bitbucket users to GitHub accounts and handle unmapped users.

-   **[🔑 API Tokens](reference/api_tokens.md)**

    Setup guides for Bitbucket and GitHub API authentication.

</div>

---

<div style="text-align: center;" markdown="1">

**Built with ❤️ for reliable repository migrations**

[🐛 Report Issues](https://github.com/fkloosterman/bitbucket-migration/issues) • [📚 API References](reference/migration_config.md)

</div>

