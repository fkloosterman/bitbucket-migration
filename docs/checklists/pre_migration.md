# Pre-Migration Checklist

Use this checklist before starting the Bitbucket → GitHub migration. Completing these steps ensures a smooth and reliable process.

---

## 🔧 Setup Verification

| Task                                                      | Status |
| --------------------------------------------------------- | ------ |
| [ ] Python 3.7+ installed                                 |        |
| [ ] Git 2.x+ installed                                    |        |
| [ ] `requests` package installed (`pip install requests`) |        |
| [ ] Access to Bitbucket Cloud repo confirmed              |        |
| [ ] Access to GitHub destination repo confirmed           |        |
| [ ] Sufficient disk space (2× repo size)                  |        |

---

## 🔑 Authentication

| Task                                              | Status |
| ------------------------------------------------- | ------ |
| [ ] Bitbucket API token created                   |        |
| [ ] GitHub PAT created with `repo` scope          |        |
| [ ] Both tokens tested with `curl`                |        |
| [ ] Tokens stored securely (not committed to Git) |        |

---

## 🗂️ Repository Preparation

| Task                                         | Status |
| -------------------------------------------- | ------ |
| [ ] Bitbucket repo name noted                |        |
| [ ] GitHub repo created and **empty**        |        |
| [ ] Repo visibility (private/public) decided |        |
| [ ] Branch protection rules documented       |        |

---

## 👥 User Mapping

| Task                                            | Status |
| ----------------------------------------------- | ------ |
| [ ] Audit script run with `--generate-config`   |        |
| [ ] `user_mapping_template.txt` reviewed        |        |
| [ ] All active users mapped to GitHub usernames |        |
| [ ] Deleted users mapped to `null`              |        |

---

## 🧾 Audit & Configuration

| Task                                                     | Status |
| -------------------------------------------------------- | ------ |
| [ ] `audit_report.md` reviewed                           |        |
| [ ] `migration_config.json` validated (no syntax errors) |        |
| [ ] Issue and PR counts recorded                         |        |
| [ ] Attachments noted (count, total size)                |        |

---

## ✅ Ready to Proceed

| Task                                    | Status |
| --------------------------------------- | ------ |
| [ ] Backup of Bitbucket repo created    |        |
| [ ] All above steps complete            |        |
| [ ] Team notified of migration schedule |        |

---

