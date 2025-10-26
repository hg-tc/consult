# Git 上传指南

## ✅ 已创建 `.gitignore` 文件

`.gitignore` 已创建在项目根目录，包含以下规则：

### 🔴 忽略的目录和文件

#### Python 后端相关
- `venv/` - Python 虚拟环境（16MB）
- `__pycache__/` - Python 缓存
- `*.pyc` - Python 字节码
- `*.egg-info/` - Python 包信息

#### Node.js 前端相关
- `node_modules/` - Node 依赖（661MB）
- `.next/` - Next.js 构建输出（47MB）
- `out/` - 构建产物

#### 数据库和存储
- `global_vector_db/` - 向量数据库
- `langchain_vector_db/` - LangChain 向量数据库
- `web_search_cache/` - 网络搜索缓存
- `global_data/` - 全局数据
- `*.db`, `*.sqlite` - SQLite 文件

#### 日志文件
- `*.log` - 所有日志文件
- `backend.log` (14KB)
- `frontend.log` (389B)
- `system.log` (633KB)

#### 环境变量
- `.env` - 环境变量（敏感信息）
- `.env.local` - 本地环境变量
- `.env.*` - 其他环境配置

#### 上传和临时文件
- `uploads/` - 上传文件目录
- `temp/` - 临时文件
- `generated/` - 生成的文件
- `test_data/` - 测试数据

#### 备份和压缩文件
- `*.backup`, `*.bak` - 备份文件
- `*.zip`, `*.tar.gz` - 压缩文件
- `恢复指南.txt`
- `iptables-rules.backup`

#### IDE 配置
- `.vscode/`, `.idea/` - IDE 配置
- `*.swp`, `.DS_Store` - 系统文件

### ✅ 会被上传的文件

- ✅ `.gitignore` 本身
- ✅ `README.md` 项目说明
- ✅ `start.sh`, `stop.sh`, `restart.sh` - 启动脚本
- ✅ `status.sh`, `setup.sh` - 系统脚本
- ✅ `backend/` - 后端代码（不含 venv）
- ✅ `frontend/` - 前端代码（不含 node_modules 和 .next）
- ✅ `backend/requirements.txt` - Python 依赖
- ✅ `frontend/package.json` - Node 依赖
- ✅ `frontend/pnpm-lock.yaml` - 锁文件

## 📦 上传到 Git 的步骤

### 1. 初始化 Git 仓库（如果还没有）
```bash
cd /root/workspace/consult
git init
```

### 2. 添加文件到 Git
```bash
git add .
```

### 3. 提交代码
```bash
git commit -m "Initial commit: Agent Service Platform with frontend and backend"
```

### 4. 添加远程仓库
```bash
git remote add origin <your-github-repo-url>
```

### 5. 推送到远程
```bash
git branch -M main
git push -u origin main
```

## 📊 预期上传大小

**会上传的文件大小：** 约 **15-30 MB**
- 源代码文件（主要是文本文件）
- 配置文件
- 文档文件

**不会上传的内容：**
- ❌ `node_modules/` (661MB)
- ❌ `.next/` (47MB)
- ❌ `backend/venv/` (16MB)
- ❌ 日志文件（约 650KB）
- ❌ 向量数据库
- ❌ 缓存文件

## 🔒 安全提示

**重要：** 请确保以下文件不会包含敏感信息：

1. **环境变量文件** - `.env` 已被忽略 ✅
2. **API 密钥** - 请勿硬编码在代码中
3. **数据库密码** - 使用环境变量
4. **私钥文件** - 不应上传

## 🚀 克隆项目后的设置

克隆项目后，需要：

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd consult

# 2. 设置后端环境
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 设置前端环境
cd ../frontend
pnpm install  # 或 npm install

# 4. 创建环境变量文件
# 在 backend/ 和 frontend/ 目录创建 .env 文件
# 参考 backend/.env.example （如果有）

# 5. 启动服务
cd ..
./start.sh
```

## 📝 注意事项

1. **Python 版本**: 项目使用 Python 3.8+
2. **Node 版本**: 推荐使用 Node.js 18+
3. **包管理器**: 前端使用 pnpm（已上传 `pnpm-lock.yaml`）
4. **端口配置**:
   - 后端: http://localhost:8000
   - 前端: http://localhost:13000

