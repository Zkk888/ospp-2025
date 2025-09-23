# 23. src/api/__init__.py
"""
API接口层 - eulermaker-docker-optimizer的API模块

******OSPP-2025-张金荣******

提供完整的API接口层，包括：
- Web API服务器（FastAPI/Flask）
- WebSocket服务器（用于终端集成）
- RPC服务器（内部服务通信）
- API路由模块（不同功能的路由分组）

主要组件：
- web_server: Web API服务器，提供RESTful接口
- websocket_server: WebSocket服务器，支持实时通信
- rpc_server: RPC服务器，提供内部服务调用
- routes: API路由模块，按功能分组的路由定义

使用示例：
    from api.web_server import WebServer
    from api.websocket_server import WebSocketServer

    # 创建Web服务器
    web_server = WebServer()
    await web_server.start()

    # 创建WebSocket服务器
    ws_server = WebSocketServer()
    await ws_server.start()
"""

from typing import Dict, List, Optional, Any
import asyncio
from datetime import datetime

from utils.logger import get_logger
from utils.exceptions import APIError

logger = get_logger(__name__)

# API版本信息
API_VERSION = "1.0.0"
API_TITLE = "EulerMaker Docker Optimizer API"
API_DESCRIPTION = """
EulerMaker Docker优化器的API接口服务

这个API提供了完整的Docker容器管理、RPM构建和终端访问功能：

## 主要功能

### 容器管理
- 容器生命周期管理（创建、启动、停止、删除）
- 容器信息查询和监控
- 容器资源使用情况统计
- 容器网络和存储管理

### RPM构建
- 构建任务提交和管理
- 构建进度监控
- 构建结果下载
- 构建历史查询

### 终端服务
- Web终端连接
- 容器内命令执行
- 终端会话管理
- 多用户终端支持

### 监控探针
- 容器性能监控
- 系统资源监控
- 自定义监控指标
- 告警和通知

## 认证和授权

API支持多种认证方式：
- API Key认证
- JWT令牌认证
- 基础HTTP认证

## 错误处理

所有API错误都遵循统一的错误格式：
```json
{
    "error": {
        "code": "error_code",
        "message": "错误描述信息",
        "details": {},
        "timestamp": "2025-08-01T00:00:00Z"
    }
}
```

## 版本兼容性

当前API版本：v1.0.0
- 支持向后兼容
- 废弃的API会提前通知
- 新版本会保持URL路径兼容性
"""

# API配置常量
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_WS_PORT = 8001
DEFAULT_RPC_PORT = 8002

# API路径前缀
API_V1_PREFIX = "/api/v1"
WEBSOCKET_PREFIX = "/ws"
RPC_PREFIX = "/rpc"

# 响应状态码
class APIStatus:
    """API响应状态码"""
    SUCCESS = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    INTERNAL_SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503

# API错误代码
class APIErrorCode:
    """API错误代码"""
    # 通用错误
    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHORIZATION_FAILED = "authorization_failed"
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_CONFLICT = "resource_conflict"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"

    # 容器相关错误
    CONTAINER_NOT_FOUND = "container_not_found"
    CONTAINER_NOT_RUNNING = "container_not_running"
    CONTAINER_ALREADY_EXISTS = "container_already_exists"
    CONTAINER_OPERATION_FAILED = "container_operation_failed"

    # 构建相关错误
    BUILD_NOT_FOUND = "build_not_found"
    BUILD_ALREADY_RUNNING = "build_already_running"
    BUILD_FAILED = "build_failed"
    BUILD_CANCELLED = "build_cancelled"

    # 终端相关错误
    TERMINAL_SESSION_NOT_FOUND = "terminal_session_not_found"
    TERMINAL_CONNECTION_FAILED = "terminal_connection_failed"
    TERMINAL_PERMISSION_DENIED = "terminal_permission_denied"

    # 探针相关错误
    PROBE_NOT_FOUND = "probe_not_found"
    PROBE_EXECUTION_FAILED = "probe_execution_failed"
    MONITORING_TARGET_NOT_FOUND = "monitoring_target_not_found"

def create_error_response(error_code: str, message: str,
                          details: Optional[Dict[str, Any]] = None,
                          status_code: int = APIStatus.INTERNAL_SERVER_ERROR) -> Dict[str, Any]:
    """创建标准API错误响应

    Args:
        error_code: 错误代码
        message: 错误消息
        details: 错误详细信息
        status_code: HTTP状态码

    Returns:
        标准格式的错误响应
    """
    return {
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
            "status_code": status_code
        }
    }

def create_success_response(data: Any = None, message: str = "操作成功",
                            meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """创建标准API成功响应

    Args:
        data: 响应数据
        message: 成功消息
        meta: 元数据信息

    Returns:
        标准格式的成功响应
    """
    response = {
        "success": True,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }

    if data is not None:
        response["data"] = data

    if meta:
        response["meta"] = meta

    return response

def create_paginated_response(items: List[Any], total: int, page: int = 1,
                              per_page: int = 20, message: str = "获取成功") -> Dict[str, Any]:
    """创建分页响应

    Args:
        items: 数据项列表
        total: 总数量
        page: 当前页码
        per_page: 每页数量
        message: 响应消息

    Returns:
        分页格式的响应
    """
    total_pages = (total + per_page - 1) // per_page
    has_next = page < total_pages
    has_prev = page > 1

    return create_success_response(
        data=items,
        message=message,
        meta={
            "pagination": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        }
    )

class APIMetrics:
    """API指标收集器"""

    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.response_times = []
        self.endpoints_stats = {}
        self.start_time = datetime.now()

    def record_request(self, endpoint: str, method: str, status_code: int, response_time: float):
        """记录API请求指标"""
        self.request_count += 1

        if status_code >= 400:
            self.error_count += 1

        self.response_times.append(response_time)

        # 限制响应时间历史记录大小
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-500:]

        endpoint_key = f"{method} {endpoint}"
        if endpoint_key not in self.endpoints_stats:
            self.endpoints_stats[endpoint_key] = {
                "count": 0,
                "errors": 0,
                "avg_response_time": 0.0,
                "total_response_time": 0.0
            }

        stats = self.endpoints_stats[endpoint_key]
        stats["count"] += 1
        stats["total_response_time"] += response_time
        stats["avg_response_time"] = stats["total_response_time"] / stats["count"]

        if status_code >= 400:
            stats["errors"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取API统计信息"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0

        return {
            "uptime_seconds": uptime,
            "total_requests": self.request_count,
            "total_errors": self.error_count,
            "error_rate": self.error_count / self.request_count if self.request_count > 0 else 0,
            "average_response_time": avg_response_time,
            "requests_per_second": self.request_count / uptime if uptime > 0 else 0,
            "endpoints": dict(self.endpoints_stats)
        }

    def reset_stats(self):
        """重置统计信息"""
        self.request_count = 0
        self.error_count = 0
        self.response_times.clear()
        self.endpoints_stats.clear()
        self.start_time = datetime.now()

# 全局API指标实例
api_metrics = APIMetrics()

def get_api_info() -> Dict[str, Any]:
    """获取API基本信息"""
    return {
        "title": API_TITLE,
        "version": API_VERSION,
        "description": API_DESCRIPTION,
        "endpoints": {
            "web_api": API_V1_PREFIX,
            "websocket": WEBSOCKET_PREFIX,
            "rpc": RPC_PREFIX
        },
        "status": "running",
        "started_at": api_metrics.start_time.isoformat(),
        "metrics": api_metrics.get_stats()
    }

async def health_check() -> Dict[str, Any]:
    """API健康检查"""
    try:
        # 这里可以添加更多的健康检查逻辑
        # 比如检查数据库连接、外部服务状态等

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": API_VERSION,
            "uptime": (datetime.now() - api_metrics.start_time).total_seconds(),
            "components": {
                "web_server": "healthy",
                "websocket_server": "healthy",
                "rpc_server": "healthy"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

# 导出主要组件和工具
__all__ = [
    # API信息和版本
    "API_VERSION",
    "API_TITLE",
    "API_DESCRIPTION",

    # 配置常量
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_WS_PORT",
    "DEFAULT_RPC_PORT",
    "API_V1_PREFIX",
    "WEBSOCKET_PREFIX",
    "RPC_PREFIX",

    # 状态码和错误代码
    "APIStatus",
    "APIErrorCode",

    # 响应创建函数
    "create_error_response",
    "create_success_response",
    "create_paginated_response",

    # 指标和工具
    "APIMetrics",
    "api_metrics",
    "get_api_info",
    "health_check"
]