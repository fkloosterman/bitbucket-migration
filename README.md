# Bitbucket → GitHub Migration Tools

This repository provides a set of Python-based tools and documentation to assist in migrating repositories from **Bitbucket Cloud** to **GitHub**. It covers the full process — from auditing and mirroring git history to migrating issues, pull requests, and attachments.

The goal is to provide a **reliable, transparent, and repeatable migration workflow** that minimizes manual steps while ensuring that all relevant metadata is preserved.

---

## ⚖️ Disclaimer

**Migration Tools Created with Claude.ai**

These migration tools were developed with assistance from Claude.ai, an AI language model by Anthropic. While every effort has been made to ensure the tools are reliable and safe:

- **Use at your own risk**: Always perform a dry run (`dry-run` subcommand) before actual migration
- **Backup your data**: Ensure you have backups of your Bitbucket repositories before migration
- **Review and verify**: Carefully review the migration report and verify the results
- **Test thoroughly**: Test the migration process in a non-production environment first

The tools follow a conservative migration strategy (e.g., closed PRs become issues rather than GitHub PRs) to minimize risks, but repository migrations involve complex metadata and edge cases that may require manual intervention.

---

## ✨ Features

* **🆕 Unified Migration Toolkit**: Single entry point with `audit`, `migrate`, `dry-run`, and `test-auth` subcommands
* **🔍 Interactive Audit**: Pre-migration analysis with automatic configuration generation and user prompting
* **📊 Comprehensive Analysis**: Repository structure, user activity, migration estimates, and gap detection
* **🔄 Intelligent PR Migration**: OPEN PRs with existing branches become GitHub PRs, others become issues (safest approach)
* **🔗 Automatic Link Rewriting**: Cross-references between issues/PRs are automatically updated to point to GitHub
* **📎 Advanced Attachment Handling**: Downloads all attachments and inline images with informative comments for manual upload
* **👥 Smart User Mapping**: Maps Bitbucket users to GitHub accounts with support for unmapped users and account ID resolution
* **🧪 Dry-run Capability**: Simulate entire migration without making changes to validate configuration
* **📋 Comprehensive Reporting**: Detailed markdown reports with migration statistics and troubleshooting notes
* **🔢 Placeholder Issue Creation**: Preserves original numbering with placeholders for deleted/missing content
* **📄 Configuration Management**: Generate and validate migration configurations automatically
* **🛡️  Secure Token Handling**: Environment variable support and token format validation
* **📚 Step-by-step Documentation**: Checklists and guides for every phase of the migration process

### Architecture Benefits

* **Modular Design**: Shared components eliminate code duplication between audit and migration
* **Single Source of Truth**: Consistent API interactions, user mapping, and error handling
* **Easy Maintenance**: Updates to core functionality benefit both audit and migration tools
* **Backward Compatibility**: Legacy scripts still supported alongside new unified toolkit

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

* Python 3.12+
* Git 2.x+
* Bitbucket API token
* GitHub Personal Access Token (with `repo` scope)

---

## 🚀 Quick Start

### Unified Migration Toolkit (Recommended)

```bash
# 1. Install the package globally (recommended)
pipx install bitbucket-migration

# 2. Audit Bitbucket repo (generates configuration)
migrate_bitbucket_to_github audit --workspace WORKSPACE --repo REPO --email EMAIL

# 3. Edit configuration
vim migration_config.json

# 4. Run dry-run to validate
migrate_bitbucket_to_github dry-run --config migration_config.json

# 5. Run full migration
migrate_bitbucket_to_github migrate --config migration_config.json

# 6. Follow documentation for attachment upload and verification
```

**Alternative: Clone from source**
```bash
git clone https://github.com/fkloosterman/bitbucket-migration.git
cd bitbucket-migration

# Use unified toolkit
migrate_bitbucket_to_github audit --workspace WORKSPACE --repo REPO --email EMAIL

# Or use the short alias (after installing package)
pip install -e .
bb2gh audit --workspace WORKSPACE --repo REPO --email EMAIL
```

For full instructions, visit the [Migration Guide](https://fkloosterman.github.io/bitbucket-migration/migration_guide/).

### Available Commands

```bash
# Show all available commands
migrate_bitbucket_to_github --help
# Or using the short alias
bb2gh --help

# Audit repository (interactive prompts for missing args)
migrate_bitbucket_to_github audit --workspace WORKSPACE --repo REPO --email EMAIL
# Or using the short alias
bb2gh audit --workspace WORKSPACE --repo REPO --email EMAIL

# Generate configuration from audit
migrate_bitbucket_to_github audit --workspace WORKSPACE --repo REPO --email EMAIL
# Or using the short alias
bb2gh audit --workspace WORKSPACE --repo REPO --email EMAIL

# Test authentication (Bitbucket and GitHub APIs)
migrate_bitbucket_to_github test-auth --workspace WORKSPACE --repo REPO --email EMAIL --gh-owner GH_OWNER --gh-repo GH_REPO

# Dry run migration (validate configuration)
migrate_bitbucket_to_github dry-run --config migration_config.json
# Or using the short alias
bb2gh dry-run --config migration_config.json

# Full migration
migrate_bitbucket_to_github migrate --config migration_config.json
# Or using the short alias
bb2gh migrate --config migration_config.json

# Migrate only issues
migrate_bitbucket_to_github migrate --config migration_config.json --skip-prs

# Migrate only pull requests
migrate_bitbucket_to_github migrate --config migration_config.json --skip-issues
```

---

## 🧩 Contributing

Contributions are welcome! See the [issues](https://github.com/fkloosterman/bitbucket-migration/issues) page for open tasks or suggestions.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE.txt) file for details.

---

© 2025 Fabian Kloosterman. All rights reserved.
