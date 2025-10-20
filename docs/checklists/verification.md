# Migration Verification Checklist

Use this checklist immediately after running the migration script to confirm data integrity.

---

## 🧩 Git Verification

| Task                                      | Status |
| ----------------------------------------- | ------ |
| [ ] All branches migrated                 |        |
| [ ] All tags present                      |        |
| [ ] Commit history identical to Bitbucket |        |
| [ ] Default branch set correctly          |        |

---

## 🧾 Issues & PRs

| Task                                             | Status |
| ------------------------------------------------ | ------ |
| [ ] Issue count matches audit report             |        |
| [ ] PR count matches audit report                |        |
| [ ] Closed PRs migrated as issues (where needed) |        |
| [ ] Labels and milestones correct                |        |
| [ ] Issue numbers sequential                     |        |

---

## 🗨️ Comments & Mentions

| Task                                              | Status |
| ------------------------------------------------- | ------ |
| [ ] All comments migrated                         |        |
| [ ] User mentions linked correctly                |        |
| [ ] Deleted users marked as `(no GitHub account)` |        |
| [ ] Timestamps present in comment text            |        |

---

## 📎 Attachments

| Task                                                                  | Status |
| --------------------------------------------------------------------- | ------ |
| [ ] All attachments downloaded to `attachments_temp/`                 |        |
| [ ] Attachment references visible in GitHub comments                  |        |
| [ ] Uploads scheduled via [Attachment Guide](../attachment_upload.md) |        |

---

## 🔍 Data Validation

| Task                                      | Status |
| ----------------------------------------- | ------ |
| [ ] Spot-check sample issues for accuracy |        |
| [ ] Spot-check sample PRs for accuracy    |        |
| [ ] Audit vs. migrated item counts match  |        |

---

## ⚙️ Repo Settings

| Task                          | Status |
| ----------------------------- | ------ |
| [ ] Default branch configured |        |
| [ ] Branch protections added  |        |
| [ ] CI/CD workflows updated   |        |
| [ ] Team permissions reviewed |        |

---

## ✅ Verification Complete

| Task                                      | Status |
| ----------------------------------------- | ------ |
| [ ] All data validated                    |        |
| [ ] Summary report generated              |        |
| [ ] Team notified of verification results |        |

---
