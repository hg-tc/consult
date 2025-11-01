"""
生产级回调处理器
支持流式输出、Token 追踪、LangSmith 集成
"""

import logging
from typing import Optional, Dict, Any
from langchain.callbacks.base import AsyncCallbackHandler
from langsmith import Client
import json

logger = logging.getLogger(__name__)

class ProductionCallbackHandler(AsyncCallbackHandler):
    """生产级回调处理器"""
    
    def __init__(self, websocket=None, enable_langsmith: bool = True):
        self.websocket = websocket
        self.token_count = 0
        self.cost = 0.0
        self.stage_history = []
        self.enable_langsmith = enable_langsmith
        
        if enable_langsmith:
            try:
                self.langsmith_client = Client()
            except Exception as e:
                logger.warning(f"LangSmith 客户端初始化失败: {e}")
                self.enable_langsmith = False
    
    async def on_llm_start(self, serialized, prompts, **kwargs):
        """LLM 调用开始"""
        tags = kwargs.get("tags", [])
        stage = tags[0] if tags else "unknown"
        
        if self.websocket:
            try:
                await self.websocket.send_json({
                    "type": "llm_start",
                    "stage": stage,
                    "message": f"开始 LLM 调用: {stage}"
                })
            except Exception as e:
                logger.error(f"WebSocket 发送失败: {e}")
    
    async def on_llm_new_token(self, token: str, **kwargs):
        """新 Token（流式输出）"""
        self.token_count += 1
        
        if self.websocket:
            try:
                await self.websocket.send_json({
                    "type": "token",
                    "content": token
                })
            except Exception as e:
                logger.error(f"WebSocket 发送失败: {e}")
    
    async def on_llm_end(self, response, **kwargs):
        """LLM 调用结束"""
        # 计算成本
        usage = response.llm_output.get("token_usage", {}) if hasattr(response, 'llm_output') else {}
        
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        
        # 成本计算（GPT-3.5-turbo 价格）
        cost_per_1k = 0.002
        cost = (total_tokens / 1000) * cost_per_1k
        self.cost += cost
        
        if self.websocket:
            try:
                await self.websocket.send_json({
                    "type": "llm_end",
                    "tokens": total_tokens,
                    "cost": cost,
                    "cumulative_cost": self.cost
                })
            except Exception as e:
                logger.error(f"WebSocket 发送失败: {e}")
    
    async def on_chain_start(self, serialized, inputs, **kwargs):
        """链开始"""
        chain_name = serialized.get("name", "unknown") if isinstance(serialized, dict) else "unknown"
        
        self.stage_history.append({
            "stage": chain_name,
            "status": "started"
        })
        
        if self.websocket:
            try:
                await self.websocket.send_json({
                    "type": "stage_start",
                    "stage": chain_name,
                    "message": f"开始执行: {chain_name}"
                })
            except Exception as e:
                logger.error(f"WebSocket 发送失败: {e}")
    
    async def on_chain_end(self, outputs, **kwargs):
        """链结束"""
        serialized = kwargs.get("serialized", {})
        chain_name = serialized.get("name", "unknown") if isinstance(serialized, dict) else "unknown"
        
        for stage in self.stage_history:
            if stage["stage"] == chain_name and stage["status"] == "started":
                stage["status"] = "completed"
                break
        
        if self.websocket:
            try:
                await self.websocket.send_json({
                    "type": "stage_complete",
                    "stage": chain_name,
                    "message": f"完成: {chain_name}"
                })
            except Exception as e:
                logger.error(f"WebSocket 发送失败: {e}")
    
    async def on_agent_action(self, action, **kwargs):
        """Agent 执行动作"""
        if self.websocket:
            try:
                await self.websocket.send_json({
                    "type": "agent_action",
                    "agent": action.tool if hasattr(action, 'tool') else "unknown",
                    "input": str(action.tool_input)[:100] if hasattr(action, 'tool_input') else ""
                })
            except Exception as e:
                logger.error(f"WebSocket 发送失败: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return {
            "token_count": self.token_count,
            "total_cost": round(self.cost, 6),
            "stage_history": self.stage_history
        }

class CostTrackingHandler(AsyncCallbackHandler):
    """成本追踪处理器（独立使用）"""
    
    def __init__(self):
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_cost = 0.0
        self.model_costs = {
            "gpt-4": {"prompt": 0.03, "completion": 0.06},
            "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002}
        }
    
    def on_llm_end(self, response, **kwargs):
        """LLM 调用结束回调"""
        try:
            from app.core.config import settings
            usage = response.llm_output.get("token_usage", {})
            model = response.llm_output.get("model_name", settings.LLM_MODEL_NAME)
            
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.total_tokens += prompt_tokens + completion_tokens
            
            # 计算成本
            default_cost = self.model_costs.get(settings.LLM_MODEL_NAME, self.model_costs["gpt-3.5-turbo"])
            costs = self.model_costs.get(model, default_cost)
            cost = (prompt_tokens * costs["prompt"] + 
                    completion_tokens * costs["completion"]) / 1000
            self.total_cost += cost
        except Exception as e:
            logger.error(f"成本追踪失败: {e}")
    
    def get_summary(self) -> dict:
        """获取成本摘要"""
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_cost_usd": round(self.total_cost, 4)
        }

