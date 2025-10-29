"""
应用配置
"""

import os
from typing import List, Optional, Union
from pydantic import validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """应用设置"""

    # 项目信息
    PROJECT_NAME: str = "Agent Service Platform API"
    PROJECT_DESCRIPTION: str = "AI Agent服务平台后端API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # 数据库配置
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:password@localhost/agent_platform"
    )

    # JWT配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8天

    # 文件上传配置
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB
    UPLOAD_DIR: str = "uploads"
    ALLOWED_EXTENSIONS: List[str] = [
        ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
        ".txt", ".md", ".json", ".csv"
    ]

    # 大模型API配置
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # 向量数据库配置
    VECTOR_DB_PATH: str = "vector_db"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # 存储路径配置（支持环境变量，默认使用 /home 目录）
    # 先获取基础路径
    _storage_base = os.getenv(
        "STORAGE_BASE_PATH",
        "/home/consult_storage"  # 默认使用 /home 目录
    )
    STORAGE_BASE_PATH: str = _storage_base
    
    # LlamaIndex 存储路径
    LLAMAINDEX_STORAGE_PATH: str = os.getenv(
        "LLAMAINDEX_STORAGE_PATH",
        os.path.join(_storage_base, "llamaindex_storage")
    )
    # LangChain 向量数据库路径
    LANGCHAIN_VECTOR_DB_PATH: str = os.getenv(
        "LANGCHAIN_VECTOR_DB_PATH",
        os.path.join(_storage_base, "langchain_vector_db")
    )
    # 缓存存储路径
    CACHE_STORAGE_PATH: str = os.getenv(
        "CACHE_STORAGE_PATH",
        os.path.join(_storage_base, "cache_storage")
    )
    # 全局数据目录（JSON文件存储）
    GLOBAL_DATA_PATH: str = os.getenv(
        "GLOBAL_DATA_PATH",
        os.path.join(_storage_base, "global_data")
    )
    # 工作区数据目录（JSON文件存储）
    WORKSPACE_DATA_PATH: str = os.getenv(
        "WORKSPACE_DATA_PATH",
        os.path.join(_storage_base, "workspace_data")
    )

    # Redis配置（可选）
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")

    # CORS配置
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:13000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:13000",
    ]

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(
        cls, v: Union[str, List[str]]
    ) -> Union[List[str], str]:
        """解析CORS源"""
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"  # 忽略未定义的环境变量字段


settings = Settings()
