# Bitbucket → GitHub Migration Tools

This repository provides a set of Python-based tools and documentation to assist in migrating repositories from **Bitbucket Cloud** to **GitHub**. It covers the full process — from auditing and mirroring git history to migrating issues, pull requests, and attachments.

The goal is to provide a **reliable, transparent, and repeatable migration workflow** that minimizes manual steps while ensuring that all relevant metadata is preserved.

---

## ⚖️ Disclaimer

**Migration Tools Created with Claude.ai**

These migration tools were developed with assistance from Claude.ai, an AI language model by Anthropic. While every effort has been made to ensure the tools are reliable and safe:

- **Use at your own risk**: Always perform a dry run (`--dry-run` flag) before actual migration
- **Backup your data**: Ensure you have backups of your Bitbucket repositories before migration
- **Review and verify**: Carefully review the migration report and verify the results
- **Test thoroughly**: Test the migration process in a non-production environment first

The tools follow a conservative migration strategy (e.g., closed PRs become issues rather than GitHub PRs) to minimize risks, but repository migrations involve complex metadata and edge cases that may require manual intervention.

---

## ✨ Features

* **Audit and analyze** Bitbucket repositories before migration
* **Migrate commits, branches, tags, issues, PRs, and comments** with full metadata preservation
* **Intelligent PR migration strategy**: OPEN PRs with existing branches become GitHub PRs, others become issues (safest approach)
* **Automatic link rewriting**: Cross-references between issues/PRs are automatically updated to point to GitHub
* **Comprehensive attachment handling**: Downloads all attachments and inline images with GitHub CLI upload support
* **Advanced user mapping**: Maps Bitbucket users to GitHub accounts with support for unmapped users
* **Dry-run capability**: Simulate entire migration without making changes to validate configuration
* **Comprehensive reporting**: Detailed markdown reports with migration statistics and troubleshooting notes
* **Placeholder issue creation**: Preserves original numbering with placeholders for deleted/missing content
* **Generate mapping and verification reports**: Machine-readable mapping and comprehensive migration reports
* **Attachment/image upload support**: For attachments and images with clear guidance and automated options
* **Step-by-step documentation** and checklists for every phase of the migration process

---

## 📘 Documentation

Comprehensive documentation is available at:

👉 **[Bitbucket → GitHub Migration Guide](https://fkloosterman.github.io/bitbucket-migration/)**

It includes:

* Quick start instructions
* Migration and verification guides
* Troubleshooting steps
* Configuration references
* Pre-/post-migration checklists

---

## 🧰 Requirements

* Python 3.7+
* Git 2.x+
* Bitbucket API token
* GitHub Personal Access Token (with `repo` scope)

---

## 🚀 Quick Start

```bash
# 1. Install the package globally (recommended)
 pipx install bitbucket-migration

# 2. Audit Bitbucket repo
 audit_bitbucket --workspace WORKSPACE --repo REPO --generate-config

# 3. Edit configuration
 vim migration_config.json

# 4. Run migration
 migrate_bitbucket_to_github --config migration_config.json

# 5. Follow documentation for attachment upload and verification
```

**Alternative: Run without installing**
```bash
# Run audit script directly
pipx run bitbucket-migration audit_bitbucket --workspace WORKSPACE --repo REPO --generate-config
# OR: uvx bitbucket-migration audit_bitbucket --workspace WORKSPACE --repo REPO --generate-config

# Run migration script directly
pipx run bitbucket-migration migrate_bitbucket_to_github --config migration_config.json
# OR: uvx bitbucket-migration migrate_bitbucket_to_github --config migration_config.json
```

**Alternative: Clone from source**
```bash
git clone https://github.com/fkloosterman/bitbucket-migration.git
cd bitbucket-migration
python audit_bitbucket.py --workspace WORKSPACE --repo REPO --generate-config
```

For full instructions, visit the [Migration Guide](https://fkloosterman.github.io/bitbucket-migration/migration_guide/).

---

## 🧩 Contributing

Contributions are welcome! See the [issues](https://github.com/fkloosterman/bitbucket-migration/issues) page for open tasks or suggestions.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE.txt) file for details.

---

© 2025 F Kloosterman. All rights reserved.
