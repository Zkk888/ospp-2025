"""
Eulermaker-docker-optimizer 的日志记录实用工具


******OSPP-2025-张金荣******

提供集中式的日志记录系统，支持以下功能：
• 采用 JSON 格式的结构化日志记录
• 异步安全的日志记录
• 上下文感知的日志记录
• 性能日志记录
• 错误追踪
"""

import logging
import logging.config
import asyncio
import json
import sys
import traceback
from typing import Any, Dict, Optional, Union
from pathlib import Path
from datetime import datetime
from functools import wraps

from config.settings import get_logging_settings


class JSONFormatter(logging.Formatter):
    """自定义JSON格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为JSON格式"""
        # 基础日志信息
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 添加进程和线程信息
        log_data["process"] = record.process
        log_data["thread"] = record.thread

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }

        # 添加自定义字段
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)

        # 添加请求ID（如果存在）
        if hasattr(record, 'request_id'):
            log_data["request_id"] = record.request_id

        # 添加容器ID（如果存在）
        if hasattr(record, 'container_id'):
            log_data["container_id"] = record.container_id

        # 添加构建ID（如果存在）
        if hasattr(record, 'build_id'):
            log_data["build_id"] = record.build_id

        return json.dumps(log_data, ensure_ascii=False)


class ContextFilter(logging.Filter):
    """上下文过滤器，添加请求上下文信息"""

    def filter(self, record: logging.LogRecord) -> bool:
        """添加上下文信息到日志记录"""
        # 尝试从asyncio任务中获取上下文信息
        try:
            current_task = asyncio.current_task()
            if current_task and hasattr(current_task, 'context'):
                context = current_task.context
                if 'request_id' in context:
                    record.request_id = context['request_id']
                if 'container_id' in context:
                    record.container_id = context['container_id']
                if 'build_id' in context:
                    record.build_id = context['build_id']
        except RuntimeError:
            # 不在异步上下文中
            pass

        return True


class AsyncSafeHandler(logging.Handler):
    """异步安全的日志处理器"""

    def __init__(self, handler: logging.Handler):
        super().__init__()
        self.handler = handler
        self.queue = asyncio.Queue()
        self._task = None

    async def start(self):
        """启动异步日志处理任务"""
        self._task = asyncio.create_task(self._process_logs())

    async def stop(self):
        """停止异步日志处理任务"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def emit(self, record: logging.LogRecord):
        """发送日志记录"""
        try:
            # 在事件循环中运行时，将记录放入队列
            if asyncio.get_running_loop():
                asyncio.create_task(self.queue.put(record))
            else:
                # 同步环境直接处理
                self.handler.emit(record)
        except RuntimeError:
            # 没有运行的事件循环，直接处理
            self.handler.emit(record)

    async def _process_logs(self):
        """处理日志队列中的记录"""
        while True:
            try:
                record = await self.queue.get()
                self.handler.emit(record)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error processing log: {e}", file=sys.stderr)


class EulerMakerLogger:
    """EulerMaker自定义日志器"""

    def __init__(self, name: str, logger: logging.Logger):
        self.name = name
        self._logger = logger
        self._context: Dict[str, Any] = {}

    def with_context(self, **context) -> 'EulerMakerLogger':
        """添加上下文信息"""
        new_logger = EulerMakerLogger(self.name, self._logger)
        new_logger._context = {**self._context, **context}
        return new_logger

    def _log(self, level: int, message: str, *args, **kwargs):
        """内部日志方法"""
        if self._logger.isEnabledFor(level):
            # 创建日志记录
            record = self._logger.makeRecord(
                self.name, level, "(unknown file)", 0, message, args, None
            )

            # 添加上下文信息
            if self._context:
                record.extra_data = self._context

            # 添加kwargs中的额外信息
            extra = kwargs.get('extra', {})
            if extra:
                if hasattr(record, 'extra_data'):
                    record.extra_data.update(extra)
                else:
                    record.extra_data = extra

            self._logger.handle(record)

    def debug(self, message: str, *args, **kwargs):
        """记录调试信息"""
        self._log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        """记录信息"""
        self._log(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """记录警告"""
        self._log(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        """记录错误"""
        self._log(logging.ERROR, message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        """记录严重错误"""
        self._log(logging.CRITICAL, message, *args, **kwargs)

    def exception(self, message: str, *args, **kwargs):
        """记录异常信息"""
        kwargs['exc_info'] = True
        self._log(logging.ERROR, message, *args, **kwargs)

    async def async_info(self, message: str, *args, **kwargs):
        """异步记录信息"""
        self.info(message, *args, **kwargs)

    async def async_error(self, message: str, *args, **kwargs):
        """异步记录错误"""
        self.error(message, *args, **kwargs)

    async def async_exception(self, message: str, *args, **kwargs):
        """异步记录异常"""
        self.exception(message, *args, **kwargs)


class LoggerMixin:
    """日志器混合类，为其他类提供日志功能"""

    @property
    def logger(self) -> EulerMakerLogger:
        """获取当前类的日志器"""
        if not hasattr(self, '_logger'):
            logger_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
            self._logger = get_logger(logger_name)
        return self._logger


class PerformanceLogger:
    """性能日志器"""

    def __init__(self, logger: EulerMakerLogger):
        self.logger = logger
        self.start_time = None
        self.operation = None

    def __enter__(self):
        self.start_time = datetime.now()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            if exc_type:
                self.logger.error(
                    f"Operation '{self.operation}' failed after {duration:.3f}s",
                    extra={"operation": self.operation, "duration": duration, "error": str(exc_val)}
                )
            else:
                self.logger.info(
                    f"Operation '{self.operation}' completed in {duration:.3f}s",
                    extra={"operation": self.operation, "duration": duration}
                )

    def set_operation(self, operation: str):
        """设置操作名称"""
        self.operation = operation


# 全局日志器字典
_loggers: Dict[str, EulerMakerLogger] = {}
_logging_configured = False


def setup_logging(config_file: Optional[str] = None, log_level: Optional[str] = None) -> None:
    """
    设置日志系统

    Args:
        config_file: 日志配置文件路径
        log_level: 日志级别
    """
    global _logging_configured

    if _logging_configured:
        return

    settings = get_logging_settings()

    # 确保日志目录存在
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / settings.log_file

    # 设置日志级别
    level = log_level or settings.log_level

    # 日志配置
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': settings.log_format,
                'datefmt': settings.log_date_format
            },
            'json': {
                '()': JSONFormatter,
            },
        },
        'filters': {
            'context_filter': {
                '()': ContextFilter,
            },
        },
        'handlers': {
            'console': {
                'level': level,
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
                'stream': 'ext://sys.stdout',
                'filters': ['context_filter'],
            },
            'file': {
                'level': level,
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'json',
                'filename': str(log_file_path),
                'maxBytes': _parse_size(settings.log_max_size),
                'backupCount': settings.log_backup_count,
                'encoding': 'utf-8',
                'filters': ['context_filter'],
            },
        },
        'loggers': {
            '': {  # root logger
                'handlers': ['console', 'file'],
                'level': level,
                'propagate': False,
            },
            'eulermaker': {
                'handlers': ['console', 'file'],
                'level': level,
                'propagate': False,
            },
            'aiodocker': {
                'handlers': ['console', 'file'],
                'level': 'WARNING',
                'propagate': False,
            },
            'aiohttp': {
                'handlers': ['console', 'file'],
                'level': 'WARNING',
                'propagate': False,
            },
        },
    }

    # 应用配置
    logging.config.dictConfig(config)
    _logging_configured = True


def get_logger(name: str) -> EulerMakerLogger:
    """
    获取日志器实例

    Args:
        name: 日志器名称

    Returns:
        EulerMakerLogger实例
    """
    if not _logging_configured:
        setup_logging()

    if name not in _loggers:
        logger = logging.getLogger(name)
        _loggers[name] = EulerMakerLogger(name, logger)

    return _loggers[name]


def log_performance(operation: str):
    """
    性能日志装饰器

    Args:
        operation: 操作名称
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                logger = get_logger(f"{func.__module__}.{func.__qualname__}")
                with PerformanceLogger(logger) as perf:
                    perf.set_operation(operation)
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                logger = get_logger(f"{func.__module__}.{func.__qualname__}")
                with PerformanceLogger(logger) as perf:
                    perf.set_operation(operation)
                    return func(*args, **kwargs)
            return sync_wrapper
    return decorator


def log_errors(logger_name: Optional[str] = None):
    """
    错误日志装饰器

    Args:
        logger_name: 日志器名称
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                log_name = logger_name or f"{func.__module__}.{func.__qualname__}"
                logger = get_logger(log_name)
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.exception(f"Error in {func.__name__}: {str(e)}")
                    raise
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                log_name = logger_name or f"{func.__module__}.{func.__qualname__}"
                logger = get_logger(log_name)
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.exception(f"Error in {func.__name__}: {str(e)}")
                    raise
            return sync_wrapper
    return decorator


def _parse_size(size_str: str) -> int:
    """解析大小字符串，返回字节数"""
    size_str = size_str.strip().upper()
    if size_str.endswith('KB'):
        return int(size_str[:-2]) * 1024
    elif size_str.endswith('MB'):
        return int(size_str[:-2]) * 1024 * 1024
    elif size_str.endswith('GB'):
        return int(size_str[:-2]) * 1024 * 1024 * 1024
    else:
        return int(size_str)


# 便捷函数
def debug(message: str, logger_name: str = "eulermaker", **kwargs):
    """记录调试信息"""
    get_logger(logger_name).debug(message, **kwargs)


def info(message: str, logger_name: str = "eulermaker", **kwargs):
    """记录信息"""
    get_logger(logger_name).info(message, **kwargs)


def warning(message: str, logger_name: str = "eulermaker", **kwargs):
    """记录警告"""
    get_logger(logger_name).warning(message, **kwargs)


def error(message: str, logger_name: str = "eulermaker", **kwargs):
    """记录错误"""
    get_logger(logger_name).error(message, **kwargs)


def exception(message: str, logger_name: str = "eulermaker", **kwargs):
    """记录异常"""
    get_logger(logger_name).exception(message, **kwargs)