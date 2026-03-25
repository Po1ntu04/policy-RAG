# 项目启动指南

政务文档智能处理系统是一个基于 FastAPI 的私有化 GPT 服务，支持多种 LLM 模型和向量数据库。本项目包含后端 API 服务和前端 Web 界面。

## 项目结构

```
private-gpt/
├── private_gpt/          # 后端 Python 代码
├── frontend/             # 前端 Vue.js 应用
├── settings.yaml         # 默认配置文件
├── pyproject.toml        # Python 依赖配置
└── poetry.lock          # Poetry 锁定文件
```

## 环境要求

- **Python**: 3.11.x
- **Node.js**: 18.x 或更高版本
- **Poetry**: Python 包管理工具
- **npm**: Node.js 包管理工具

## 后端启动

### 1. 安装 Python 依赖

```bash
# 安装 Poetry（如果未安装）
pip install poetry

# 安装项目依赖
poetry install

# 安装特定功能的额外依赖（可选）
poetry install --with ui                    # 包含 Gradio UI
# poetry install --with llms-ollama          # 可选择包含 Ollama LLM 支持
poetry install --with embeddings-huggingface # 包含 HuggingFace 嵌入模型
poetry install --with vector-stores-qdrant  # 包含 Qdrant 向量数据库
# 标准
poetry install -E llms-openai-like -E embeddings-huggingface -E vector-stores-qdrant -E ui

# Postgres 指标库与登录所需依赖
poetry add psycopg2-binary
```

### 2. 配置设置

项目使用 `settings.yaml` 进行配置。主要配置项包括：

```yaml
server:
  port: 8001
  cors:
    enabled: true
    allow_origins: ["*"]

llm:
  mode: "ollama"  # 或 "llama-cpp", "openai", "azure-openai" 等

embeddings:
  mode: "ollama"  # 或 "huggingface", "openai" 等

vectorstore:
  database: "qdrant"  # 或 "postgres", "chroma", "milvus" 等
```

### 3. 启动前端开发服务器

```bash
# 方式 1: 使用 Poetry
poetry run python -m private_gpt

# 说明：默认 profile（settings.yaml）使用 llamacpp，本机必须存在 GGUF 模型文件（通常放在项目根目录的 models/ 下）。
# 如果您使用千问（settings-qwen.yaml），推荐先编辑 scripts\run_backend_qwen.cmd 中的占位符：
#   DASHSCOPE_API_KEY=<your_dashscope_api_key>
#   HF_TOKEN=<your_huggingface_token>
#   PGPT_AUTH_SECRET=<your_auth_secret>
# 保存后直接运行：scripts\run_backend_qwen.cmd

# 方式 2: 直接运行
poetry run private-gpt

# 方式 3: 使用 uvicorn
poetry run uvicorn private_gpt.main:app --host 0.0.0.0 --port 8001
```

后端服务将在 `http://localhost:8001` 启动，API 文档可在 `http://localhost:8001/docs` 查看。

## 数据库与登录（Postgres + RBAC）

系统默认使用 JSON 指标库，如需启用 Postgres，请准备本地 Postgres 并设置以下环境变量：

```bash
set PGPT_INDICATOR_STORE=postgres
set PGPT_AUTO_MIGRATE=1
set PGPT_AUTH_SECRET=your-secret-key
```

默认演示账号（登录页可直接使用）：

- 管理员：admin / admin123
- 工作人员：staff / staff123
- 领导：leader / leader123
- 公众：public / public123

如需手动初始化数据库脚本：

```bash
psql -d gov_rag -f db/schema_postgres.sql
psql -d gov_rag -f db/seed.sql
```

## 前端启动

### 1. 安装 Node.js 依赖

```bash
cd frontend
npm install
```

### 2. 配置环境变量

在 `frontend/` 目录下创建 `.env.development` 文件：

```env
# Vue CLI 项目请使用 VUE_APP_* 前缀（VITE_* 仅适用于 Vite 项目）
VUE_APP_API_BASE=http://localhost:8001/v1

# （可选）保留 VITE_API_BASE 仅用于兼容历史配置
VITE_API_BASE=http://localhost:8001/v1
```

### 3. 启动前端开发服务器

```bash
cd frontend
npm run serve
```

前端应用将在 `http://localhost:8080` 启动。

## 完整启动流程

### 1. 启动后端

```bash
# 终端 1: 启动后端
cd /path/to/private-gpt
poetry install
poetry install -E llms-openai-like -E embeddings-huggingface -E vector-stores-qdrant -E ui

# （推荐）千问模型实例
# 请先编辑 scripts\run_backend_qwen.cmd，将其中的占位符替换为您自己的密钥与认证配置，然后运行：
scripts\run_backend_qwen.cmd

# 或通过以下命令设置：
#设置qwen的配置文件， 对应到了settings-qwen.yaml  修改settings-qwen的模型qwen3-30b-a3b-instruct-2507
set PGPT_PROFILES=qwen  
set DASHSCOPE_API_KEY=XXXXXXXXXXXXXXXXXXXXXXX  #千问百炼token
set HF_TOKEN=XXXXXXXXXXXXXX        #huggingface的token下载embedding模型，如要使用ollma自动修改匹配的配置文件 
set PGPT_INDICATOR_STORE=postgres
set PGPT_AUTO_MIGRATE=1
set PGPT_AUTH_SECRET=your-secret-key
poetry run python -m private_gpt
```

### 2. 启动前端

```bash
# 终端 2: 启动前端
cd /path/to/private-gpt/frontend
npm install
npm run serve
```

### 3. 访问应用

- 前端界面: <http://localhost:8080>
- 后端 API: <http://localhost:8001>
- API 文档: <http://localhost:8001/docs>

## 故障排除

### 常见问题

1. **端口冲突**: 如果 8001 端口被占用，可以在 `settings.yaml` 中修改 `server.port`

2. **依赖安装失败**: 确保使用 Python 3.11.x 版本，并使用 Poetry 安装依赖

3. **前端无法连接后端**: 检查 CORS 配置和 API 基础 URL 设置

4. **模型加载失败**: 检查 LLM 配置和模型文件路径

### 日志查看

后端日志会直接输出到控制台，前端日志可在浏览器开发者工具中查看
---
