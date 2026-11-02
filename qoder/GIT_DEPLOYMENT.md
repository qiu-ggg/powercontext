# Git 部署指南

> 将代码推送到 GitHub 仓库

## 📦 已完成的 Git 操作

以下命令已经执行：

```bash
# 1. 初始化 Git 仓库
git init

# 2. 配置用户信息
git config user.name "qiu-ggg"
git config user.email "qiu-ggg@users.noreply.github.com"

# 3. 添加远程仓库（凭据通过 git credential manager 或环境变量提供，不要写进命令或文件）
git remote add origin https://github.com/qiu-ggg/powercontext.git

# 4. 添加所有文件到暂存区
git add .

# 5. 提交代码
git commit -m "Initial commit: 智能知识库项目完成"

# 6. 重命名主分支
git branch -M main

# 7. 推送到远程仓库
git push -u origin main
```

## ✅ 验证推送是否成功

### 方法 1: 检查 GitHub 仓库

访问您的 GitHub 仓库：
```
https://github.com/qiu-ggg/powercontext
```

如果推送成功，您应该能看到项目文件。

### 方法 2: 检查 Git 状态

在项目目录执行：
```bash
git status
```

如果看到以下信息，说明推送成功：
```
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

### 方法 3: 查看 Git 日志

```bash
git log --oneline
```

应该能看到提交记录。

## 🔧 如果推送失败

### 情况 1: 认证失败

如果提示认证错误，可能是 Token 问题。解决方法：

```bash
# 删除远程仓库
git remote remove origin

# 重新添加（使用您的新 Token）
git remote add origin https://qiu-ggg:YOUR_NEW_TOKEN@github.com/qiu-ggg/powercontext.git

# 再次推送
git push -u origin main
```

### 情况 2: 仓库已有内容

如果远程仓库已有内容，需要先拉取：

```bash
# 拉取远程内容
git pull origin main --allow-unrelated-histories

# 解决冲突（如果有）
# 然后提交
git add .
git commit -m "Merge remote changes"
git push -u origin main
```

### 情况 3: 网络问题

检查网络连接，然后重试：
```bash
git push -u origin main
```

## 📝 手动推送步骤

如果自动推送失败，您可以手动执行以下步骤：

### 步骤 1: 打开终端

在项目目录 `D:\SmartKnowledgeHub` 打开 PowerShell 或 CMD

### 步骤 2: 检查 Git 状态

```bash
git status
```

### 步骤 3: 查看提交日志

```bash
git log --oneline -5
```

### 步骤 4: 测试远程连接

```bash
git remote -v
```

应该能看到：
```
origin  https://github.com/qiu-ggg/powercontext.git (fetch)
origin  https://github.com/qiu-ggg/powercontext.git (push)
```

### 步骤 5: 推送到 GitHub

```bash
git push -u origin main
```

## 🎯 下一步：部署到 Qoder Sites

代码推送成功后，继续部署项目网站：

1. 登录 Qoder
2. 创建新的 Site
3. 连接 GitHub 仓库 `qiu-ggg/powercontext`
4. 配置构建命令
5. 设置环境变量
6. 部署并获取访问链接

## 📞 获取帮助

如果遇到 Git 相关问题，可以：

1. 查看 Git 错误信息
2. 检查 GitHub Token 是否有效
3. 确认仓库地址正确
4. 检查网络连接

---

**祝您部署顺利！** 🚀
