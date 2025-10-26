"""
性能监控和日志分析服务
提供系统性能监控、日志分析、指标统计等功能
"""

import os
import logging
import time
import json
import psutil
import threading
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
import aiofiles
from contextlib import contextmanager
import traceback

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """性能指标"""
    timestamp: float
    metric_name: str
    value: float
    unit: str
    tags: Dict[str, str] = None


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: float
    level: str
    message: str
    module: str
    function: str
    line_number: int
    extra_data: Dict[str, Any] = None


@dataclass
class SystemStats:
    """系统统计"""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_usage_percent: float
    disk_free_gb: float
    network_sent_mb: float
    network_recv_mb: float
    active_connections: int
    timestamp: float


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_metrics: int = 10000):
        self.max_metrics = max_metrics
        self.metrics: deque = deque(maxlen=max_metrics)
        self.lock = threading.RLock()
        self.monitoring = False
        self.monitor_thread = None
        
        # 性能指标收集器
        self.collectors = {
            'cpu': self._collect_cpu_metrics,
            'memory': self._collect_memory_metrics,
            'disk': self._collect_disk_metrics,
            'network': self._collect_network_metrics,
            'custom': []
        }
    
    def start_monitoring(self, interval: float = 5.0):
        """开始监控"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()
        logger.info(f"性能监控已启动，间隔: {interval}秒")
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("性能监控已停止")
    
    def add_custom_metric(self, name: str, value: float, unit: str = "", tags: Dict[str, str] = None):
        """添加自定义指标"""
        metric = PerformanceMetric(
            timestamp=time.time(),
            metric_name=name,
            value=value,
            unit=unit,
            tags=tags or {}
        )
        
        with self.lock:
            self.metrics.append(metric)
    
    def get_metrics(self, metric_name: Optional[str] = None, 
                   start_time: Optional[float] = None,
                   end_time: Optional[float] = None) -> List[PerformanceMetric]:
        """获取指标数据"""
        with self.lock:
            metrics = list(self.metrics)
        
        # 过滤
        if metric_name:
            metrics = [m for m in metrics if m.metric_name == metric_name]
        
        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]
        
        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]
        
        return metrics
    
    def get_latest_metrics(self, count: int = 100) -> List[PerformanceMetric]:
        """获取最新指标"""
        with self.lock:
            return list(self.metrics)[-count:]
    
    def _monitoring_loop(self, interval: float):
        """监控循环"""
        while self.monitoring:
            try:
                # 收集系统指标
                for collector_name, collector in self.collectors.items():
                    if callable(collector):
                        metrics = collector()
                        for metric in metrics:
                            with self.lock:
                                self.metrics.append(metric)
                
                time.sleep(interval)
            except Exception as e:
                logger.error(f"性能监控循环错误: {str(e)}")
                time.sleep(interval)
    
    def _collect_cpu_metrics(self) -> List[PerformanceMetric]:
        """收集CPU指标"""
        metrics = []
        current_time = time.time()
        
        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=1)
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="cpu_percent",
            value=cpu_percent,
            unit="percent"
        ))
        
        # CPU核心数
        cpu_count = psutil.cpu_count()
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="cpu_count",
            value=cpu_count,
            unit="cores"
        ))
        
        # CPU频率
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            metrics.append(PerformanceMetric(
                timestamp=current_time,
                metric_name="cpu_frequency",
                value=cpu_freq.current,
                unit="MHz"
            ))
        
        return metrics
    
    def _collect_memory_metrics(self) -> List[PerformanceMetric]:
        """收集内存指标"""
        metrics = []
        current_time = time.time()
        
        memory = psutil.virtual_memory()
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="memory_percent",
            value=memory.percent,
            unit="percent"
        ))
        
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="memory_used_mb",
            value=memory.used / 1024 / 1024,
            unit="MB"
        ))
        
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="memory_total_mb",
            value=memory.total / 1024 / 1024,
            unit="MB"
        ))
        
        # 交换内存
        swap = psutil.swap_memory()
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="swap_percent",
            value=swap.percent,
            unit="percent"
        ))
        
        return metrics
    
    def _collect_disk_metrics(self) -> List[PerformanceMetric]:
        """收集磁盘指标"""
        metrics = []
        current_time = time.time()
        
        # 系统磁盘
        disk_usage = psutil.disk_usage('/')
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="disk_usage_percent",
            value=disk_usage.percent,
            unit="percent"
        ))
        
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="disk_free_gb",
            value=disk_usage.free / 1024 / 1024 / 1024,
            unit="GB"
        ))
        
        metrics.append(PerformanceMetric(
            timestamp=current_time,
            metric_name="disk_total_gb",
            value=disk_usage.total / 1024 / 1024 / 1024,
            unit="GB"
        ))
        
        return metrics
    
    def _collect_network_metrics(self) -> List[PerformanceMetric]:
        """收集网络指标"""
        metrics = []
        current_time = time.time()
        
        # 网络IO
        net_io = psutil.net_io_counters()
        if net_io:
            metrics.append(PerformanceMetric(
                timestamp=current_time,
                metric_name="network_sent_mb",
                value=net_io.bytes_sent / 1024 / 1024,
                unit="MB"
            ))
            
            metrics.append(PerformanceMetric(
                timestamp=current_time,
                metric_name="network_recv_mb",
                value=net_io.bytes_recv / 1024 / 1024,
                unit="MB"
            ))
        
        return metrics


class LogAnalyzer:
    """日志分析器"""
    
    def __init__(self, log_dir: str = "logs", max_entries: int = 50000):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.entries: deque = deque(maxlen=max_entries)
        self.lock = threading.RLock()
        
        # 日志统计
        self.stats = {
            'total_entries': 0,
            'error_count': 0,
            'warning_count': 0,
            'info_count': 0,
            'debug_count': 0,
            'module_stats': defaultdict(int),
            'hourly_stats': defaultdict(int)
        }
    
    def add_log_entry(self, level: str, message: str, module: str = "", 
                     function: str = "", line_number: int = 0, 
                     extra_data: Dict[str, Any] = None):
        """添加日志条目"""
        entry = LogEntry(
            timestamp=time.time(),
            level=level,
            message=message,
            module=module,
            function=function,
            line_number=line_number,
            extra_data=extra_data or {}
        )
        
        with self.lock:
            self.entries.append(entry)
            self._update_stats(entry)
    
    def get_logs(self, level: Optional[str] = None,
                module: Optional[str] = None,
                start_time: Optional[float] = None,
                end_time: Optional[float] = None,
                limit: Optional[int] = None) -> List[LogEntry]:
        """获取日志条目"""
        with self.lock:
            logs = list(self.entries)
        
        # 过滤
        if level:
            logs = [log for log in logs if log.level == level]
        
        if module:
            logs = [log for log in logs if module in log.module]
        
        if start_time:
            logs = [log for log in logs if log.timestamp >= start_time]
        
        if end_time:
            logs = [log for log in logs if log.timestamp <= end_time]
        
        # 限制数量
        if limit:
            logs = logs[-limit:]
        
        return logs
    
    def get_error_logs(self, hours: int = 24) -> List[LogEntry]:
        """获取错误日志"""
        start_time = time.time() - hours * 3600
        return self.get_logs(level='ERROR', start_time=start_time)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取日志统计"""
        with self.lock:
            return dict(self.stats)
    
    def analyze_patterns(self) -> Dict[str, Any]:
        """分析日志模式"""
        with self.lock:
            logs = list(self.entries)
        
        patterns = {
            'common_errors': defaultdict(int),
            'common_warnings': defaultdict(int),
            'module_errors': defaultdict(int),
            'hourly_distribution': defaultdict(int)
        }
        
        for log in logs:
            hour = datetime.fromtimestamp(log.timestamp).hour
            patterns['hourly_distribution'][hour] += 1
            
            if log.level == 'ERROR':
                # 提取错误关键词
                error_key = self._extract_error_key(log.message)
                patterns['common_errors'][error_key] += 1
                patterns['module_errors'][log.module] += 1
            
            elif log.level == 'WARNING':
                warning_key = self._extract_warning_key(log.message)
                patterns['common_warnings'][warning_key] += 1
        
        return {
            'common_errors': dict(sorted(patterns['common_errors'].items(), 
                                       key=lambda x: x[1], reverse=True)[:10]),
            'common_warnings': dict(sorted(patterns['common_warnings'].items(), 
                                         key=lambda x: x[1], reverse=True)[:10]),
            'module_errors': dict(sorted(patterns['module_errors'].items(), 
                                        key=lambda x: x[1], reverse=True)[:10]),
            'hourly_distribution': dict(patterns['hourly_distribution'])
        }
    
    def _update_stats(self, entry: LogEntry):
        """更新统计信息"""
        self.stats['total_entries'] += 1
        self.stats[f'{entry.level.lower()}_count'] += 1
        self.stats['module_stats'][entry.module] += 1
        
        hour = datetime.fromtimestamp(entry.timestamp).hour
        self.stats['hourly_stats'][hour] += 1
    
    def _extract_error_key(self, message: str) -> str:
        """提取错误关键词"""
        # 简单的错误分类
        if 'timeout' in message.lower():
            return 'timeout'
        elif 'connection' in message.lower():
            return 'connection'
        elif 'permission' in message.lower():
            return 'permission'
        elif 'not found' in message.lower():
            return 'not_found'
        else:
            return 'other'
    
    def _extract_warning_key(self, message: str) -> str:
        """提取警告关键词"""
        if 'deprecated' in message.lower():
            return 'deprecated'
        elif 'slow' in message.lower():
            return 'performance'
        elif 'retry' in message.lower():
            return 'retry'
        else:
            return 'other'


class SystemMonitor:
    """系统监控器"""
    
    def __init__(self):
        self.performance_monitor = PerformanceMonitor()
        self.log_analyzer = LogAnalyzer()
        self.monitoring = False
        
        # 系统状态
        self.system_stats = SystemStats(
            cpu_percent=0,
            memory_percent=0,
            memory_used_mb=0,
            memory_total_mb=0,
            disk_usage_percent=0,
            disk_free_gb=0,
            network_sent_mb=0,
            network_recv_mb=0,
            active_connections=0,
            timestamp=time.time()
        )
    
    def start_monitoring(self):
        """开始监控"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.performance_monitor.start_monitoring()
        
        # 启动系统状态更新
        self._update_system_stats()
        
        logger.info("系统监控已启动")
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        self.performance_monitor.stop_monitoring()
        logger.info("系统监控已停止")
    
    def get_system_stats(self) -> SystemStats:
        """获取系统状态"""
        return self.system_stats
    
    def get_performance_metrics(self) -> List[PerformanceMetric]:
        """获取性能指标"""
        return self.performance_monitor.get_latest_metrics()
    
    def get_log_analysis(self) -> Dict[str, Any]:
        """获取日志分析"""
        return {
            'stats': self.log_analyzer.get_stats(),
            'patterns': self.log_analyzer.analyze_patterns(),
            'recent_errors': self.log_analyzer.get_error_logs(hours=1)
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        stats = self.system_stats
        
        # 健康检查
        health_checks = {
            'cpu_healthy': stats.cpu_percent < 80,
            'memory_healthy': stats.memory_percent < 85,
            'disk_healthy': stats.disk_usage_percent < 90,
            'overall_healthy': True
        }
        
        # 整体健康状态
        health_checks['overall_healthy'] = all([
            health_checks['cpu_healthy'],
            health_checks['memory_healthy'],
            health_checks['disk_healthy']
        ])
        
        return {
            'status': 'healthy' if health_checks['overall_healthy'] else 'warning',
            'checks': health_checks,
            'timestamp': time.time()
        }
    
    def _update_system_stats(self):
        """更新系统状态"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 内存
            memory = psutil.virtual_memory()
            
            # 磁盘
            disk = psutil.disk_usage('/')
            
            # 网络
            net_io = psutil.net_io_counters()
            
            # 连接数
            connections = len(psutil.net_connections())
            
            self.system_stats = SystemStats(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / 1024 / 1024,
                memory_total_mb=memory.total / 1024 / 1024,
                disk_usage_percent=disk.percent,
                disk_free_gb=disk.free / 1024 / 1024 / 1024,
                network_sent_mb=net_io.bytes_sent / 1024 / 1024 if net_io else 0,
                network_recv_mb=net_io.bytes_recv / 1024 / 1024 if net_io else 0,
                active_connections=connections,
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"更新系统状态失败: {str(e)}")


# 装饰器：性能监控
def monitor_performance(metric_name: str, unit: str = ""):
    """性能监控装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                # 记录性能指标
                system_monitor.performance_monitor.add_custom_metric(
                    f"{metric_name}_execution_time",
                    execution_time,
                    unit or "seconds"
                )
                
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                
                # 记录错误
                system_monitor.log_analyzer.add_log_entry(
                    'ERROR',
                    f"函数 {func.__name__} 执行失败: {str(e)}",
                    module=func.__module__,
                    function=func.__name__
                )
                
                # 记录性能指标
                system_monitor.performance_monitor.add_custom_metric(
                    f"{metric_name}_error_time",
                    execution_time,
                    unit or "seconds"
                )
                
                raise
        
        return wrapper
    return decorator


# 上下文管理器：性能监控
@contextmanager
def performance_context(metric_name: str, unit: str = ""):
    """性能监控上下文管理器"""
    start_time = time.time()
    try:
        yield
    finally:
        execution_time = time.time() - start_time
        system_monitor.performance_monitor.add_custom_metric(
            metric_name,
            execution_time,
            unit
        )


# 全局系统监控器实例
system_monitor = SystemMonitor()


# 测试函数
def test_monitoring_system():
    """测试监控系统"""
    print("测试监控系统...")
    
    # 启动监控
    system_monitor.start_monitoring()
    
    # 添加一些测试日志
    system_monitor.log_analyzer.add_log_entry(
        'INFO', '系统启动', 'test_module', 'test_function'
    )
    system_monitor.log_analyzer.add_log_entry(
        'ERROR', '测试错误', 'test_module', 'test_function'
    )
    
    # 添加自定义指标
    system_monitor.performance_monitor.add_custom_metric(
        'test_metric', 123.45, 'count'
    )
    
    # 等待一段时间收集数据
    time.sleep(2)
    
    # 获取系统状态
    stats = system_monitor.get_system_stats()
    print(f"系统状态: CPU {stats.cpu_percent}%, 内存 {stats.memory_percent}%")
    
    # 获取性能指标
    metrics = system_monitor.get_performance_metrics()
    print(f"性能指标数量: {len(metrics)}")
    
    # 获取日志分析
    log_analysis = system_monitor.get_log_analysis()
    print(f"日志统计: {log_analysis['stats']}")
    
    # 获取健康状态
    health = system_monitor.get_health_status()
    print(f"健康状态: {health['status']}")
    
    # 停止监控
    system_monitor.stop_monitoring()
    
    print("✅ 监控系统测试完成")


if __name__ == "__main__":
    test_monitoring_system()
