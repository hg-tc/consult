"""
RAG 配置加载工具
从 YAML 配置文件加载配置
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional

class RAGConfig:
    """RAG 配置类"""
    
    def __init__(self, config_path: str = "rag_config.yaml"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.load_config llama
    
    def load_config(self):
        """加载配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
            else:
                self.config = self._get_default_config()
                # 创建默认配置文件
                self._create_default_config_file()
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            self.config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "llamaindex": {
                "embedding": {
                    "model_name": "BAAI/bge-large-zh-v1.5",
                    "device": "cpu"
                },
                "retrieval": {
                    "use_hybrid": True,
                    "top_k": 5,
                    "similarity_threshold": 0.7
                }
            },
            "langgraph": {
                "rag_workflow": {
                    "max_refinement_iterations": 2,
                    "quality_threshold": 0.7
                },
                "doc_generation": {
                    "default_target_words": 5000
                }
            },
            "llm": {
                "model": "gpt-3.5-turbo",  # 默认值，实际从settings读取
                "temperature": 0.1
            }
        }
    
    def _create_default_config_file(self):
        """创建默认配置文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            print(f"创建配置文件失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value
    
    def get_llamaindex_config(self) -> Dict[str, Any]:
        """获取 LlamaIndex 配置"""
        return self.config.get("llamaindex", {})
    
    def get_langgraph_config(self) -> Dict[str, Any]:
        """获取 LangGraph 配置"""
        return self.config.get("langgraph", {})
    
    def get_llm_config(self) -> Dict[str, Any]:
        """获取 LLM 配置"""
        from app.core.config import settings
        llm_config = self.config.get("llm", {})
        # 如果配置中没有模型名称，从settings读取
        if "model" not in llm_config or llm_config.get("model") == "gpt-3.5-turbo":
            llm_config["model"] = settings.LLM_MODEL_NAME
        return llm_config

# 全局配置实例
_rag_config: Optional[RAGConfig] = None

def get_rag_config() -> RAGConfig:
    """获取全局配置实例"""
    global _rag_config
    if _rag_config is None:
        _rag_config = RAGConfig()
    return _rag_config

