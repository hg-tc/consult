"""
应用注册器 - 从配置文件加载并注册应用
"""
import json
import logging
import importlib
from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI

logger = logging.getLogger(__name__)


class AppRegistry:
    """应用注册器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化应用注册器
        
        Args:
            config_path: 配置文件路径，默认为 apps.config.json
        """
        if config_path is None:
            # 默认配置文件路径
            apps_dir = Path(__file__).parent
            config_path = apps_dir / "apps.config.json"
        
        self.config_path = Path(config_path)
        self.apps_config = self._load_config()
        self.registered_apps: Dict[str, Any] = {}
    
    def _load_config(self) -> Dict[str, Any]:
        """加载应用配置文件"""
        try:
            if not self.config_path.exists():
                logger.warning(f"应用配置文件不存在: {self.config_path}")
                return {"apps": []}
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"加载应用配置: {len(config.get('apps', []))} 个应用")
                return config
        except Exception as e:
            logger.error(f"加载应用配置失败: {e}")
            return {"apps": []}
    
    def register_apps(self, app: FastAPI, api_prefix: str = "/api"):
        """
        注册所有启用的应用到 FastAPI 应用
        
        Args:
            app: FastAPI 应用实例
            api_prefix: API 前缀，默认为 /api
        """
        apps_list = self.apps_config.get("apps", [])
        registered_count = 0
        
        for app_config in apps_list:
            if not app_config.get("enabled", True):
                logger.info(f"跳过未启用的应用: {app_config.get('id')}")
                continue
            
            try:
                app_id = app_config.get("id")
                app_file = app_config.get("file")
                api_prefix_config = app_config.get("api_prefix", "")
                
                if not app_file:
                    logger.warning(f"应用 {app_id} 未指定文件，跳过注册")
                    continue
                
                # 动态导入应用模块
                module_path = f"app.apps.{app_file.replace('.py', '')}"
                logger.info(f"导入应用模块: {module_path}")
                
                module = importlib.import_module(module_path)
                
                # 获取应用实例（假设每个模块有一个 get_app() 函数或 APP 实例）
                app_instance = None
                if hasattr(module, "get_app"):
                    app_instance = module.get_app()
                elif hasattr(module, "APP"):
                    app_instance = module.APP
                else:
                    logger.error(f"应用模块 {module_path} 未找到应用实例（需要 get_app() 函数或 APP 实例）")
                    continue
                
                # 获取路由器
                router = None
                if hasattr(app_instance, "get_router"):
                    router = app_instance.get_router()
                elif hasattr(app_instance, "router"):
                    router = app_instance.router
                else:
                    logger.error(f"应用 {app_id} 无法获取路由器（应用实例缺少 get_router() 方法或 router 属性）")
                    continue
                
                if router is None or not hasattr(router, "routes"):
                    logger.error(f"应用 {app_id} 的路由器无效")
                    continue
                
                # 使用配置的 API 前缀
                full_prefix = api_prefix_config if api_prefix_config else f"{api_prefix}/apps/{app_id}"
                
                app.include_router(router, prefix=full_prefix, tags=[app_config.get("name", app_id)])
                
                self.registered_apps[app_id] = {
                    "config": app_config,
                    "instance": app_instance,
                    "prefix": full_prefix
                }
                
                registered_count += 1
                logger.info(f"✅ 成功注册应用: {app_id} ({app_config.get('name')}) - 路由前缀: {full_prefix}")
                
            except Exception as e:
                logger.error(f"❌ 注册应用失败 {app_config.get('id')}: {e}", exc_info=True)
                continue
        
        logger.info(f"应用注册完成: 共 {registered_count}/{len(apps_list)} 个应用")
        return registered_count
    
    def get_app_info(self, app_id: str) -> Dict[str, Any]:
        """获取指定应用信息"""
        for app_config in self.apps_config.get("apps", []):
            if app_config.get("id") == app_id:
                return app_config
        return {}
    
    def list_apps(self) -> List[Dict[str, Any]]:
        """列出所有应用配置"""
        return self.apps_config.get("apps", [])

