# User Mapping Reference

User mapping ensures migrated issues, pull requests, and comments are correctly attributed to GitHub users.

---

## 👤 How It Works

Bitbucket users are identified by display name; GitHub identifies by username. The migration tool uses the mapping in `migration_config.json` to link them.

If a user cannot be mapped:

* Their name appears in bold in issue text (e.g., `**John Doe** (no GitHub account)`).
* They are **not assigned** to issues.

---

## 🔧 Example Mapping

```json
"user_mapping": {
  "Alice Smith": "alice-smith-gh",
  "Bob Jones": "bobj",
  "Charlie Brown": null,
  "Unknown (deleted user)": null
}
```

---

## 🛠️ Creating the Mapping

1. Run the audit script: `python audit_bitbucket.py --generate-config`.
2. Review `user_mapping_template.txt` for all users found in issues and PRs.
3. Fill in GitHub usernames for active contributors.
4. Leave inactive or deleted users as `null`.

---

## 💡 Tips for Accurate Mapping

* Use GitHub usernames, not display names.
* Confirm active users’ GitHub handles before migration.
* Prioritize frequent contributors first.
* Keep the mapping consistent across multiple repos if migrating several.

---

## 🔧 Verification

After migration, check a few issues or PRs:

* Comment text includes correct GitHub mention.
* Usernames resolve (clickable links).
* Unmapped users are correctly marked as `no GitHub account`.

If needed, you can re-run the migration after updating the mapping.

---
