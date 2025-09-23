"""
Eulermaker-docker-optimizer 的辅助函数和实用工具


******OSPP-2025-张金荣******

包含在整个应用程序中使用的各种实用函数，
用于执行常见操作，例如：
• UUID 生成
• 时间格式化
• 大小格式化
• JSON 操作
• 异步实用工具
• 文件操作
"""

import uuid
import json
import asyncio
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable, Awaitable, TypeVar
from functools import wraps
import time
import re
import os

from .exceptions import EulerMakerError, ValidationError


T = TypeVar('T')


# UUID相关工具
def generate_uuid() -> str:
    """生成UUID字符串"""
    return str(uuid.uuid4())


def generate_short_uuid(length: int = 8) -> str:
    """生成短UUID字符串"""
    return str(uuid.uuid4()).replace('-', '')[:length]


def generate_container_id() -> str:
    """生成容器ID"""
    return f"euler-{generate_short_uuid(12)}"


def generate_build_id() -> str:
    """生成构建ID"""
    return f"build-{generate_short_uuid(10)}"


def generate_session_id() -> str:
    """生成会话ID"""
    return f"session-{generate_short_uuid(16)}"


# 时间相关工具
def format_timestamp(dt: Optional[datetime] = None, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    格式化时间戳

    Args:
        dt: datetime对象，默认为当前时间
        format_str: 格式字符串

    Returns:
        格式化的时间字符串
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime(format_str)


def parse_timestamp(timestamp_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    """
    解析时间戳字符串

    Args:
        timestamp_str: 时间戳字符串
        format_str: 格式字符串

    Returns:
        datetime对象
    """
    try:
        return datetime.strptime(timestamp_str, format_str)
    except ValueError as e:
        raise ValidationError(f"Invalid timestamp format: {timestamp_str}", cause=e)


def get_current_timestamp() -> float:
    """获取当前时间戳（秒）"""
    return time.time()


def get_current_timestamp_ms() -> int:
    """获取当前时间戳（毫秒）"""
    return int(time.time() * 1000)


def format_duration(seconds: float) -> str:
    """
    格式化持续时间

    Args:
        seconds: 秒数

    Returns:
        格式化的持续时间字符串
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.1f}s"


# 大小相关工具
def format_size(size_bytes: int) -> str:
    """
    格式化文件大小

    Args:
        size_bytes: 字节数

    Returns:
        格式化的大小字符串
    """
    if size_bytes == 0:
        return "0B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)

    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1

    return f"{size:.1f}{size_names[i]}"


def parse_size(size_str: str) -> int:
    """
    解析大小字符串，返回字节数

    Args:
        size_str: 大小字符串，如 "1GB", "512MB", "1024KB"

    Returns:
        字节数
    """
    size_str = size_str.strip().upper()

    size_multipliers = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 ** 2,
        'GB': 1024 ** 3,
        'TB': 1024 ** 4,
    }

    # 匹配数字和单位
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGT]?B)$', size_str)
    if not match:
        raise ValidationError(f"Invalid size format: {size_str}")

    number, unit = match.groups()
    return int(float(number) * size_multipliers[unit])


# JSON相关工具
def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    安全的JSON序列化

    Args:
        obj: 要序列化的对象
        **kwargs: json.dumps的额外参数

    Returns:
        JSON字符串
    """
    try:
        # 设置默认参数
        kwargs.setdefault('ensure_ascii', False)
        kwargs.setdefault('indent', 2)
        kwargs.setdefault('default', _json_serializer)

        return json.dumps(obj, **kwargs)
    except Exception as e:
        raise EulerMakerError(f"JSON serialization failed: {str(e)}", cause=e)


def safe_json_loads(json_str: str, **kwargs) -> Any:
    """
    安全的JSON反序列化

    Args:
        json_str: JSON字符串
        **kwargs: json.loads的额外参数

    Returns:
        Python对象
    """
    try:
        return json.loads(json_str, **kwargs)
    except Exception as e:
        raise EulerMakerError(f"JSON deserialization failed: {str(e)}", cause=e)


def _json_serializer(obj: Any) -> Any:
    """JSON序列化的默认处理器"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, Path):
        return str(obj)
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    else:
        return str(obj)


# 异步工具
def retry_async(
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0,
        exceptions: tuple = (Exception,)
):
    """
    异步重试装饰器

    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟倍数
        exceptions: 要重试的异常类型
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        break

                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception
        return wrapper
    return decorator


def timeout_async(timeout_seconds: float):
    """
    异步超时装饰器

    Args:
        timeout_seconds: 超时时间（秒）
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                raise EulerMakerError(
                    f"Function {func.__name__} timed out after {timeout_seconds} seconds"
                )
        return wrapper
    return decorator


async def run_in_executor(func: Callable[..., T], *args, **kwargs) -> T:
    """
    在执行器中运行同步函数

    Args:
        func: 要运行的函数
        *args: 函数参数
        **kwargs: 函数关键字参数

    Returns:
        函数返回值
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def run_async(coro: Awaitable[T]) -> T:
    """
    在同步环境中运行异步函数

    Args:
        coro: 协程对象

    Returns:
        协程返回值
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise EulerMakerError("Cannot run async function in running event loop")
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# 文件和路径工具
def ensure_path(path: Union[str, Path], is_file: bool = False) -> Path:
    """
    确保路径存在

    Args:
        path: 路径
        is_file: 是否为文件路径

    Returns:
        Path对象
    """
    path_obj = Path(path)

    if is_file:
        # 创建父目录
        path_obj.parent.mkdir(parents=True, exist_ok=True)
    else:
        # 创建目录
        path_obj.mkdir(parents=True, exist_ok=True)

    return path_obj


def cleanup_path(path: Union[str, Path], force: bool = False) -> bool:
    """
    清理路径

    Args:
        path: 要清理的路径
        force: 是否强制删除

    Returns:
        是否成功删除
    """
    path_obj = Path(path)

    if not path_obj.exists():
        return True

    try:
        if path_obj.is_file():
            path_obj.unlink()
        elif path_obj.is_dir():
            shutil.rmtree(path_obj)
        return True
    except Exception as e:
        if force:
            raise EulerMakerError(f"Failed to cleanup path {path}: {str(e)}", cause=e)
        return False


def get_file_hash(file_path: Union[str, Path], algorithm: str = 'sha256') -> str:
    """
    获取文件哈希值

    Args:
        file_path: 文件路径
        algorithm: 哈希算法

    Returns:
        哈希值字符串
    """
    path_obj = Path(file_path)
    if not path_obj.exists():
        raise EulerMakerError(f"File not found: {file_path}")

    hash_func = hashlib.new(algorithm)

    with open(path_obj, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_func.update(chunk)

    return hash_func.hexdigest()


def copy_file_with_permissions(src: Union[str, Path], dst: Union[str, Path]) -> None:
    """
    复制文件并保持权限

    Args:
        src: 源文件路径
        dst: 目标文件路径
    """
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        raise EulerMakerError(f"Source file not found: {src}")

    # 确保目标目录存在
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    # 复制文件和权限
    shutil.copy2(src_path, dst_path)


# 字符串工具
def sanitize_name(name: str, max_length: int = 64) -> str:
    """
    清理名称，使其符合Docker命名规范

    Args:
        name: 原始名称
        max_length: 最大长度

    Returns:
        清理后的名称
    """
    # 转换为小写
    name = name.lower()

    # 替换非法字符为连字符
    name = re.sub(r'[^a-z0-9\-_.]', '-', name)

    # 移除连续的连字符
    name = re.sub(r'-+', '-', name)

    # 移除首尾的连字符
    name = name.strip('-')

    # 限制长度
    if len(name) > max_length:
        name = name[:max_length].rstrip('-')

    return name or 'unnamed'


def mask_sensitive_data(data: str, mask_char: str = '*', visible_chars: int = 4) -> str:
    """
    遮蔽敏感数据

    Args:
        data: 敏感数据
        mask_char: 遮蔽字符
        visible_chars: 可见字符数

    Returns:
        遮蔽后的字符串
    """
    if len(data) <= visible_chars * 2:
        return mask_char * len(data)

    return (
            data[:visible_chars] +
            mask_char * (len(data) - visible_chars * 2) +
            data[-visible_chars:]
    )


# 数据结构工具
def deep_merge(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """
    深度合并字典

    Args:
        dict1: 字典1
        dict2: 字典2

    Returns:
        合并后的字典
    """
    result = dict1.copy()

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def flatten_dict(d: Dict[str, Any], separator: str = '.', prefix: str = '') -> Dict[str, Any]:
    """
    扁平化字典

    Args:
        d: 要扁平化的字典
        separator: 分隔符
        prefix: 前缀

    Returns:
        扁平化的字典
    """
    result = {}

    for key, value in d.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            result.update(flatten_dict(value, separator, new_key))
        else:
            result[new_key] = value

    return result


def chunk_list(lst: List[T], chunk_size: int) -> List[List[T]]:
    """
    将列表分块

    Args:
        lst: 要分块的列表
        chunk_size: 块大小

    Returns:
        分块后的列表
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


# 环境变量工具
def get_env_bool(key: str, default: bool = False) -> bool:
    """
    获取布尔类型环境变量

    Args:
        key: 环境变量键
        default: 默认值

    Returns:
        布尔值
    """
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in ('true', '1', 'yes', 'on')


def get_env_int(key: str, default: int = 0) -> int:
    """
    获取整数类型环境变量

    Args:
        key: 环境变量键
        default: 默认值

    Returns:
        整数值
    """
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_float(key: str, default: float = 0.0) -> float:
    """
    获取浮点类型环境变量

    Args:
        key: 环境变量键
        default: 默认值

    Returns:
        浮点值
    """
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_env_list(key: str, separator: str = ',', default: Optional[List[str]] = None) -> List[str]:
    """
    获取列表类型环境变量

    Args:
        key: 环境变量键
        separator: 分隔符
        default: 默认值

    Returns:
        字符串列表
    """
    value = os.getenv(key)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(separator) if item.strip()]