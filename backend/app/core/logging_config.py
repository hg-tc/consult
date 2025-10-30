"""
全局日志配置
提供标准日志等级控制：DEBUG / INFO / WARNING / ERROR。
"""

import logging
import os
from typing import Optional


def _normalize_level_name(level_name: Optional[str]) -> str:
    if not level_name:
        return "INFO"
    upper = str(level_name).strip().upper()
    return upper if upper in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO"


def setup_logging(level_name: Optional[str] = None) -> None:
    """根据给定等级初始化全局日志。

    Args:
        level_name: 字符串等级，DEBUG/INFO/WARNING/ERROR
    """
    # 读取环境变量兜底
    if level_name is None:
        level_name = os.getenv("APP_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO"))

    normalized = _normalize_level_name(level_name)
    level = getattr(logging, normalized, logging.INFO)

    # 配置 root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 若没有 handler，则添加一个简单的控制台 handler
    if not root_logger.handlers:
        console = logging.StreamHandler()
        console.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console.setFormatter(formatter)
        root_logger.addHandler(console)

    # 为所有已存在的 handler 同步等级
    for handler in root_logger.handlers:
        handler.setLevel(level)
        # 不做降级处理，遵循标准等级


