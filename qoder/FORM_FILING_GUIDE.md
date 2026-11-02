# 表单填写指南（2026-11-02 更新）

## 1. 代码仓库地址（表单已固定，不要修改）

```
https://github.com/qiu-ggg/powercontext.git
```

提交系统会使用报名登记的团队仓库，并配合平台生成的只读令牌访问。**不要把令牌写入任何文件或文档。**

---

## 2. Commit id

推送完成后在项目目录执行：

```bash
git rev-parse HEAD
```

输出完整的 40 位 SHA，全部填入。如果推送后又在仓库里改了文件，需要重新提交并取最新 SHA。

---

## 3. Branch

```
2026-competition-ecosystem
```

这是比赛指定的开发分支（源自 oceanbase/powercontext 同名分支）。项目资产放在该分支的 `qoder/` 目录下。

---

## 4. 作品链接

```
https://smartknowledgehub-2yrvvh4q95p.qoder.zone
```

已通过 Qoder Sites 发布（`published: true`）。该站点是提交展示页；Flask 应用按 `RUNNING.md` 本地运行。

---

## 填写表格

| 字段 | 填写内容 |
|------|---------|
| **代码仓库地址** | 保持表单自动填充值 |
| **Commit id** | `git rev-parse HEAD` 的 40 位结果 |
| **Branch** | `2026-competition-ecosystem` |
| **作品链接** | `https://smartknowledgehub-2yrvvh4q95p.qoder.zone` |

填完后点击提交。

---

## 备注

- 若测评平台要求提交材料打包，使用 `SmartKnowledgeHub-submission-2026.zip`，内部包含同一套文档与截图。
- Qoder 账号 UID 需报名账号本人填写，项目内不伪造。
- 旧版 WorkBuddy 演示站不是本次作品链接，请勿填写。
