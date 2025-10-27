from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from langchain_core.language_models import BaseChatModel
import logging

logger = logging.getLogger(__name__)

class BaseProductionAgent(ABC):
    """生产级 Agent 基类"""
    
    def __init__(self, name: str, llm: BaseChatModel, config: dict = None):
        self.name = name
        self.llm = llm
        self.config = config or {}
        self.execution_count = 0
        self.error_count = 0
        
    @abstractmethod
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Agent 任务"""
        pass
    
    async def _log_execution(self, result: Dict[str, Any]):
        """记录执行信息"""
        self.execution_count += 1
        logger.info(f"Agent {self.name} 执行完成，总执行次数: {self.execution_count}")
        # LangSmith 追踪会自动记录

