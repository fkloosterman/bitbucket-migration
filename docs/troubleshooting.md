# Troubleshooting Guide

This guide lists common problems you may encounter during the migration and their solutions.

---

## 🔐 Authentication Errors

| Symptom            | Cause                                | Fix                                          |
| ------------------ | ------------------------------------ | -------------------------------------------- |
| `401 Unauthorized` | Invalid or expired token             | Regenerate Bitbucket API token or GitHub PAT |
| `403 Forbidden`    | Insufficient token scope             | Ensure GitHub PAT includes `repo` scope      |
| `404 Not Found`    | Wrong repository name or permissions | Verify repo exists and user has admin access |

---

## ⏱️ Rate Limiting

| Platform      | Limit                | Mitigation                         |
| ------------- | -------------------- | ---------------------------------- |
| **GitHub**    | ~5000 API calls/hour | Use `--dry-run` first; rerun later |
| **Bitbucket** | Dynamic throttling   | Increase delay between requests    |

If you repeatedly hit limits, edit the script:

```python
rate_limit_sleep(2.0)  # increase delay between calls
```

---

## 📄 Missing or Incomplete Data

| Issue                    | Explanation                | Resolution                                               |
| ------------------------ | -------------------------- | -------------------------------------------------------- |
| Missing issues or PRs    | API error or token expired | Re-run migration; check `migration_mapping_partial.json` |
| User mentions not linked | User not mapped            | Update `migration_config.json` user mapping              |
| Timestamps incorrect     | GitHub API limitation      | Confirm noted in description text                        |

---

## 🛠️ Attachment Problems

| Symptom                              | Cause                           | Fix                                                     |
| ------------------------------------ | ------------------------------- | ------------------------------------------------------- |
| Missing files in `attachments_temp/` | API timeout or permission issue | Re-run migration with valid Bitbucket token             |
| File >25 MB not uploaded             | Web UI limit                    | Use Git LFS or external hosting (Google Drive, Dropbox) |
| Uploaded to wrong issue              | Manual mismatch                 | Delete comment and re-upload to correct issue           |

---

## 🔧 Script or Environment Issues

| Error                                         | Resolution                                 |
| --------------------------------------------- | ------------------------------------------ |
| `ModuleNotFoundError: requests`               | Install dependency: `pip install requests` |
| `fatal: repository not found`                 | Check repository URL and permissions       |
| `OSError: [Errno 28] No space left on device` | Free disk space or change temp folder      |

---

## 🔀 Recovery Tips

1. Always keep **Bitbucket repo intact** until verification is complete.
2. If the migration halts mid-process:

   * Check the console output for the last migrated item.
   * Resume from the partial mapping file if available.
3. Use the audit report (`audit_report.md`) to confirm what’s missing.

---

## 🔧 When to Re-run Migration

Re-run the migration script if:

* Major portion of issues or PRs missing.
* Authentication tokens were invalid during initial run.
* User mapping file was incomplete.

To rerun safely:

1. Delete the GitHub repository.
2. Recreate it as **empty**.
3. Run the migration again using corrected configuration.

---

## 🔧 Support Resources

* [GitHub REST API Documentation](https://docs.github.com/en/rest)
* [Bitbucket Cloud API Documentation](https://developer.atlassian.com/cloud/bitbucket/rest/)
* [GitHub Support](https://support.github.com)
* [Atlassian Community](https://community.atlassian.com)

---

## ✅ Checklist Before Asking for Help

* [ ] Confirm both API tokens are active and scoped correctly
* [ ] Compare audit vs. migrated item counts
* [ ] Check `migration_mapping.json` for missing IDs
* [ ] Search console logs for `ERROR` or `429`
* [ ] Verify no network or disk errors occurred

If problems persist, open a support ticket with:

* Migration date and repo name
* Script version
* Last successful migration log line

---

**End of Troubleshooting Guide**
