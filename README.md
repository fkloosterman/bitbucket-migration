# Bitbucket → GitHub Migration Tools

This repository provides a set of Python-based tools and documentation to assist in migrating repositories from **Bitbucket Cloud** to **GitHub**. It covers the full process — from auditing and mirroring git history to migrating issues, pull requests, and attachments.

The goal is to provide a **reliable, transparent, and repeatable migration workflow** that minimizes manual steps while ensuring that all relevant metadata is preserved.

---

## ✨ Features

* Audit and analyze Bitbucket repositories before migration
* Migrate commits, branches, tags, issues, PRs, and comments
* Generate mapping and verification reports
* Manual upload support for attachments (with clear guidance)
* Step-by-step documentation and checklists for every phase

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
# 1. Clone this repo
 git clone https://github.com/fkloosterman/bitbucket-migration.git
 cd bitbucket-migration

# 2. Audit Bitbucket repo
 python audit_bitbucket.py --workspace WORKSPACE --repo REPO --generate-config

# 3. Edit configuration
 vim migration_config.json

# 4. Run migration
 python migrate_bitbucket_to_github.py --config migration_config.json

# 5. Follow documentation for attachment upload and verification
```

For full instructions, visit the [Migration Guide](https://fkloosterman.github.io/bitbucket-migration/migration_guide/).

---

## 🧩 Contributing

Contributions are welcome! See the [issues](https://github.com/fkloosterman/bitbucket-migration/issues) page for open tasks or suggestions.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

© 2025 F Kloosterman. All rights reserved.
