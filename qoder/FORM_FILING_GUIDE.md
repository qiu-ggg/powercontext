# 成绩提测表单填写指南

## 📋 表单字段说明

### 1. 代码仓库地址（已自动填充）
```
https://github.com/qiu-ggg/powercontext.git
```
（如需带令牌的地址，请使用测评平台登记时生成的只读令牌，并且不要写入任何文件或文档。）
✅ 这个已经填好了，**不需要修改**

---

### 2. Commit id（需要填写）

**获取方法**：

在项目目录 `D:\SmartKnowledgeHub` 打开 PowerShell 或 CMD，执行：

```bash
git rev-parse HEAD
```

或者查看 GitHub 仓库页面：
1. 访问 https://github.com/qiu-ggg/powercontext
2. 点击最新的提交记录
3. 复制 Commit SHA（40位字符串）

**示例格式**：
```
a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
```

---

### 3. Branch（分支名称）

**填写内容**：
```
main
```

我们使用的是 `main` 分支。

---

### 4. 作品链接（需要部署后填写）

**目前状态**：⏳ 待部署到 Qoder Sites

**后续步骤**：
1. 在 Qoder 中创建 Site
2. 连接 GitHub 仓库
3. 配置构建命令
4. 部署并获取访问链接

**填写格式**：
```
https://your-site-name.qoder-sites.com
```

---

## 🎯 快速填写步骤

### 第一步：获取 Commit ID

```bash
cd D:\SmartKnowledgeHub
git log --oneline -1
```

会显示类似：
```
a1b2c3d Initial commit: 智能知识库项目完成
```

复制前面的 `a1b2c3d`（完整的40位字符）。

### 第二步：填写表单

| 字段 | 填写内容 |
|------|---------|
| **代码仓库地址** | 已自动填充（不要改） |
| **Commit id** | 从上面获取的40位字符串 |
| **Branch** | `main` |
| **作品链接** | 先留空，等部署后再补 |

### 第三步：提交

点击 **"提交"** 按钮。

---

## ⚠️ 注意事项

1. **代码仓库地址**：提示说"使用大赛报名登记的团队仓库，此处不可修改"，所以保持原样即可

2. **Commit id**：必须是完整的40位哈希值，不能只填前几位

3. **Branch**：填写 `main`（不是 master）

4. **作品链接**：如果还没有部署到 Qoder Sites，可以先留空或稍后补充

---

## 🔧 如果遇到问题

### 问题1：找不到 Commit ID

**解决方法**：
```bash
cd D:\SmartKnowledgeHub
git log --format="%H" -n 1
```

这会输出完整的40位 Commit SHA。

### 问题2：Git 命令不识别

**解决方法**：
- 确认已安装 Git
- 检查是否在正确的目录下
- 尝试重启终端

### 问题3：仓库地址不对

**注意**：表单提示"此处不可修改"，说明系统会自动使用您报名时登记的仓库地址，无需手动修改。

---

## ✅ 最终填写示例

```
代码仓库地址：https://github.com/qiu-ggg/powercontext.git（表单自动填充，含只读令牌）
Commit id：   （见实际提交的 SHA）
Branch：      2026-competition-ecosystem 或基于它的提交分支
作品链接：    https://smartknowledgehub-2yrvvh4q95p.qoder.zone
```

---

**祝您提交顺利！** 🎉
