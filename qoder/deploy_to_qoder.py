"""
Qoder Sites 自动部署脚本
将项目部署到 Qoder Sites 平台
"""

import os
import json
import requests
from pathlib import Path


class QoderSitesDeployer:
    """Qoder Sites 部署器"""
    
    def __init__(self):
        self.project_dir = Path(__file__).parent
        self.site_name = "smart-knowledge-hub"
        
    def create_deployment_config(self):
        """创建部署配置文件"""
        config = {
            "name": self.site_name,
            "description": "智能知识库 - Smart Knowledge Hub",
            "framework": "python-flask",
            "build": {
                "command": "pip install -r requirements.txt && python init_db.py",
                "output_directory": "."
            },
            "start": {
                "command": "python app.py",
                "port": 5000
            },
            "environment": {
                "FLASK_DEBUG": "False",
                "SEEKDB_HOST": "localhost",
                "SEEKDB_PORT": "3306",
                "SEEKDB_USER": "root",
                "SEEKDB_PASSWORD": "${SEEKDB_PASSWORD}",
                "SEEKDB_DATABASE": "knowledge_hub",
                "POWERCONTEXT_API_KEY": "${POWERCONTEXT_API_KEY}"
            }
        }
        
        config_file = self.project_dir / "qoder-sites.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"✓ 部署配置已创建: {config_file}")
        return config_file
    
    def create_qoder_sites_yml(self):
        """创建 Qoder Sites YAML 配置"""
        yml_content = """# Qoder Sites 部署配置
site:
  name: smart-knowledge-hub
  description: 智能知识库系统
  
build:
  command: pip install -r requirements.txt && python init_db.py
  output: .
  
start:
  command: python app.py
  port: 5000
  
environment:
  FLASK_DEBUG: "False"
  SEEKDB_HOST: localhost
  SEEKDB_PORT: "3306"
  SEEKDB_USER: root
  SEEKDB_PASSWORD: ${SEEKDB_PASSWORD}
  SEEKDB_DATABASE: knowledge_hub
  POWERCONTEXT_API_KEY: ${POWERCONTEXT_API_KEY}
"""
        
        yml_file = self.project_dir / "qoder-sites.yml"
        with open(yml_file, 'w', encoding='utf-8') as f:
            f.write(yml_content)
        
        print(f"✓ YAML 配置已创建: {yml_file}")
        return yml_file
    
    def prepare_for_deployment(self):
        """准备部署"""
        print("=" * 60)
        print("准备部署到 Qoder Sites")
        print("=" * 60)
        
        # 1. 创建配置文件
        self.create_deployment_config()
        self.create_qoder_sites_yml()
        
        # 2. 检查必要文件
        required_files = [
            'app.py',
            'requirements.txt',
            'init_db.py',
            'README.md'
        ]
        
        print("\n检查必要文件:")
        for file in required_files:
            if (self.project_dir / file).exists():
                print(f"  ✓ {file}")
            else:
                print(f"  ✗ {file} 缺失!")
        
        # 3. 生成部署说明
        self.generate_deployment_instructions()
        
        print("\n" + "=" * 60)
        print("部署准备完成！")
        print("=" * 60)
    
    def generate_deployment_instructions(self):
        """生成部署说明文档"""
        instructions = """# Qoder Sites 部署步骤

## 🚀 手动部署步骤

### 步骤 1: 登录 Qoder
访问 https://qoder.ai 并登录您的账号

### 步骤 2: 创建 Site
1. 点击左侧菜单 **"Sites"**
2. 点击 **"Create Site"** 按钮
3. 填写信息：
   - **Name**: `smart-knowledge-hub`
   - **Description**: 智能知识库系统
4. 点击 **"Create"**

### 步骤 3: 连接 GitHub 仓库
1. 在 Site 页面，找到 **"Source Code"** 部分
2. 点击 **"Connect GitHub Repository"**
3. 选择仓库：`qiu-ggg/powercontext`
4. 分支选择：`main`
5. 点击 **"Connect"**

### 步骤 4: 配置构建设置
在 **"Build Settings"** 中配置：

**Build Command**:
```bash
pip install -r requirements.txt && python init_db.py
```

**Start Command**:
```bash
python app.py
```

**Port**: `5000`

### 步骤 5: 设置环境变量
在 **"Environment Variables"** 中添加以下变量：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `FLASK_DEBUG` | `False` | 生产环境关闭调试 |
| `SEEKDB_HOST` | `localhost` | 数据库主机 |
| `SEEKDB_PORT` | `3306` | 数据库端口 |
| `SEEKDB_USER` | `root` | 数据库用户 |
| `SEEKDB_PASSWORD` | `your_password` | 数据库密码（替换为实际值） |
| `SEEKDB_DATABASE` | `knowledge_hub` | 数据库名称 |
| `POWERCONTEXT_API_KEY` | `your_api_key` | PowerContext API密钥（替换为实际值） |

⚠️ **重要**: 请将 `your_password` 和 `your_api_key` 替换为您的实际值！

### 步骤 6: 部署
1. 点击 **"Deploy"** 按钮
2. 等待部署完成（约 2-5 分钟）
3. 查看部署日志确认成功

### 步骤 7: 获取访问链接
部署成功后，您会看到一个访问链接，格式类似：
```
https://smart-knowledge-hub.qoder-sites.com
```

复制这个链接，它就是您的 **作品链接**！

---

## ✅ 验证部署

部署完成后，访问您的网站链接，应该能看到：
- 首页正常显示
- 搜索功能可用
- 仪表盘可以访问

---

## 🔧 常见问题

### Q1: 部署失败
**A**: 检查以下几点：
- 环境变量是否正确配置
- 数据库连接是否正常
- 查看部署日志中的错误信息

### Q2: 网站无法访问
**A**: 
- 确认部署状态为 "Live"
- 检查 Start Command 是否正确
- 查看应用日志

### Q3: 数据库连接失败
**A**: 
- 确认 SEEKDB 服务正在运行
- 检查用户名和密码是否正确
- 确认数据库已创建

---

## 📝 提交表单

获得作品链接后，填写成绩提测表单：

| 字段 | 填写内容 |
|------|---------|
| **代码仓库地址** | 已自动填充 |
| **Commit id** | 执行 `git log --format="%H" -n 1` 获取 |
| **Branch** | `main` |
| **作品链接** | `https://smart-knowledge-hub.qoder-sites.com` |

---

**祝您部署顺利！** 🎉
"""
        
        instructions_file = self.project_dir / "DEPLOYMENT_INSTRUCTIONS.md"
        with open(instructions_file, 'w', encoding='utf-8') as f:
            f.write(instructions)
        
        print(f"\n✓ 部署说明已生成: {instructions_file}")


def main():
    """主函数"""
    deployer = QoderSitesDeployer()
    deployer.prepare_for_deployment()
    
    print("\n" + "=" * 60)
    print("接下来请按照 DEPLOYMENT_INSTRUCTIONS.md 中的步骤操作")
    print("=" * 60)


if __name__ == '__main__':
    main()
