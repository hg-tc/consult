"""
应用基类 - 定义应用接口规范
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from fastapi import APIRouter


class BaseApp(ABC):
    """应用基类，所有应用应继承此类"""
    
    def __init__(self, app_id: str, app_name: str, app_description: str):
        self.app_id = app_id
        self.app_name = app_name
        self.app_description = app_description
        self.router = APIRouter()
        self._register_routes()
    
    @abstractmethod
    def _register_routes(self):
        """注册应用的路由端点，子类必须实现此方法"""
        pass
    
    def get_router(self) -> APIRouter:
        """获取应用的路由器"""
        return self.router
    
    def get_metadata(self) -> Dict[str, Any]:
        """获取应用元数据"""
        return {
            "id": self.app_id,
            "name": self.app_name,
            "description": self.app_description,
            "routes": [route.path for route in self.router.routes]
        }

