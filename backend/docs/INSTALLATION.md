# LangGraph + LlamaIndex RAG 系统安装指南

## 前置要求

- Python 3.9+
- pip 或 conda
- 16GB+ RAM 推荐

## 安装步骤

### 1. 激活虚拟环境

```bash
cd /root/consult/backend
source venv/bin/activate  # 如果使用虚拟环境
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 安装额外依赖

新添加的依赖包括：

- `langgraph>=0.2.0` - 状态机工作流
- `langsmith>=0.0.60` - 监控工具
- `rank-bm25>=0.2.2` - BM25 检索
- `llama-index>=0.10.0` - 高级检索
- `llama-index-core>=0.10.0` - LlamaIndex 核心

如果安装失败，可以单独安装：

```bash
pip install langgraph langsmith rank-bm25
pip install llama-index llama-index-core llama-index-embeddings-huggingface
```

### 4. 配置环境变量

创建或编辑 `.env` 文件：

```bash
# LLM 配置
OPENAI_API_KEY=your_openai_api_key
# 或
THIRD_PARTY_API=your_third_party_api_url
THIRD_PARTY_API_KEY=your_third_party_api_key

# LangSmith 配置（可选，用于监控）
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=rag-system
```

### 5. 配置 RAG 系统

编辑 `rag_config.yaml` 文件以自定义配置：

```yaml
llamaindex:
  embedding:
    model_name: "BAAI/bge-large-zh-v1.5"
  
  retrieval:
    use_hybrid: true
    top_k: 5

langgraph:
  rag_workflow:
    max_refinement_iterations: 2
    quality_threshold: 0.7
```

### 6. 启动服务

```bash
# 开发模式
python app_simple.py

# 或使用 uvicorn
uvicorn app_simple:app --host 0.0.0.0 --port 13000
```

### 7. 验证安装

访问 API 文档：
- http://localhost:13000/docs

测试 LangGraph API：
```bash
curl -X POST "http://localhost:13000/api/chat/langgraph" \
  -H "Content-Type: application/json" \
  -d '{"question": "测试问题", "workspace_id": "global"}'
```

## 常见问题

### 1. 导入错误

如果遇到 `ImportError`，确保安装了所有依赖：

```bash
pip install --upgrade langchain langchain-openai langchain-community
pip install langgraph langsmith
```

### 2. LlamaIndex 兼容性问题

如果 LlamaIndex 版本冲突，可以创建隔离环境：

```bash
conda create -n rag-env python=3.10
conda activate rag-env
pip install -r requirements.txt
```

### 3. 内存不足

如果遇到内存不足，减少并发数：

编辑 `rag_config.yaml`：
```yaml
performance:
  parallel:
    max_concurrent_retrievals: 5  # 减少并发数
    max_concurrent_generations: 2
```

### 4. CUDA/GPU 支持

如果需要 GPU 加速：

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

然后修改 `rag_config.yaml`：
```yaml
llamaindex:
  embedding:
    device: "cuda"  # 使用 GPU
```

## 下一步

安装完成后，请查看：
- [使用文档](LANGGRAPH_IMPLEMENTATION.md)
- [API 文档](http://localhost:13000/docs)
- [配置说明](../rag_config.yaml)

## 卸载

如果需要卸载新添加的包：

```bash
pip uninstall langgraph langsmith rank-bm25
pip uninstall llama-index llama-index-core
```

