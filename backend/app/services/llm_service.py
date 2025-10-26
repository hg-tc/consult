"""
大模型服务
提供多种大模型API的统一接口和智能数据处理
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, AsyncGenerator, Union
from abc import ABC, abstractmethod

from openai import AsyncOpenAI
import httpx

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """大模型客户端基类"""

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """聊天完成"""
        pass

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式聊天完成"""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI客户端"""

    def __init__(self, api_key: str, base_url: str = None):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1"
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> Dict[str, Any]:
        """OpenAI聊天完成"""
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            return {
                "content": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
        except Exception as e:
            logger.error(f"OpenAI API调用失败: {str(e)}")
            raise

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """OpenAI流式聊天完成"""
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )

            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"OpenAI流式API调用失败: {str(e)}")
            raise


class ClaudeClient(BaseLLMClient):
    """Claude客户端"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.anthropic.com/v1"

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-3-sonnet-20240229",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> Dict[str, Any]:
        """Claude聊天完成"""
        try:
            # 转换消息格式
            system_message = ""
            conversation_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    conversation_messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }

            data = {
                "model": model,
                "messages": conversation_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

            if system_message:
                data["system"] = system_message

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=data,
                    timeout=60.0
                )

            if response.status_code != 200:
                raise Exception(f"Claude API错误: {response.status_code} - {response.text}")

            result = response.json()

            return {
                "content": result["content"][0]["text"],
                "model": result["model"],
                "usage": {
                    "input_tokens": result["usage"]["input_tokens"],
                    "output_tokens": result["usage"]["output_tokens"]
                }
            }

        except Exception as e:
            logger.error(f"Claude API调用失败: {str(e)}")
            raise

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-3-sonnet-20240229",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Claude流式聊天完成"""
        # Claude目前不支持流式输出，先返回普通响应
        result = await self.chat_completion(
            messages, model, temperature, max_tokens, **kwargs
        )
        yield result["content"]


class LLMService:
    """大模型服务管理器"""

    def __init__(self):
        self.clients: Dict[str, BaseLLMClient] = {}
        self._initialize_clients()

    def _initialize_clients(self):
        """初始化大模型客户端"""
        # OpenAI客户端（支持第三方API）
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            # 检查是否是第三方API
            openai_base = os.getenv("OPENAI_BASE_URL")
            if not openai_base:
                # 如果没有指定基础URL，检查是否有第三方API配置
                third_party_base = os.getenv("THIRD_PARTY_API_BASE")
                if third_party_base:
                    openai_base = third_party_base
                else:
                    openai_base = "https://api.openai.com/v1"

            self.clients["openai"] = OpenAIClient(openai_key, openai_base)

        # Claude客户端（如果有API密钥）
        claude_key = os.getenv("CLAUDE_API_KEY")
        if claude_key:
            self.clients["claude"] = ClaudeClient(claude_key)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        provider: str = "openai",
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False,
        **kwargs
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """
        统一聊天接口

        Args:
            messages: 消息列表
            provider: 模型提供商 (openai, claude)
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            stream: 是否流式输出
            **kwargs: 其他参数

        Returns:
            普通模式返回结果字典，流式模式返回生成器
        """
        if provider not in self.clients:
            raise ValueError(f"不支持的模型提供商: {provider}")

        client = self.clients[provider]

        if stream:
            return client.chat_completion_stream(
                messages, model=model, temperature=temperature,
                max_tokens=max_tokens, **kwargs
            )
        else:
            return await client.chat_completion(
                messages, model=model, temperature=temperature,
                max_tokens=max_tokens, **kwargs
            )

    def get_available_providers(self) -> List[str]:
        """获取可用的模型提供商"""
        return list(self.clients.keys())

    def get_provider_models(self, provider: str) -> List[str]:
        """获取指定提供商的可用模型"""
        models = {
            "openai": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
            "claude": ["claude-3-sonnet-20240229", "claude-3-haiku-20240307"]
        }
        return models.get(provider, [])
