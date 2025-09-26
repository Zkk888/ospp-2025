# 24. src/api/routes/__init__.py
"""
API路由模块 - eulermaker-docker-optimizer的路由管理

******OSPP-2025-张金荣******

统一管理所有API路由，提供：
- 路由注册和配置
- 路由装饰器和中间件
- API版本管理
- 统一的错误处理
- 请求验证和响应格式化
- 路由权限控制

主要功能：
- 自动路由发现和注册
- 路由分组和标签管理
- API文档自动生成
- 请求限流和缓存
- 跨域资源共享(CORS)
- 统一认证和授权
"""

import asyncio
import functools
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from collections import defaultdict

from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from utils.logger import get_logger
from utils.exceptions import APIError, ValidationError
from api import (
    API_V1_PREFIX, APIStatus, APIErrorCode,
    create_error_response, create_success_response
)

logger = get_logger(__name__)

# 全局路由注册器
_registered_routers: List[APIRouter] = []
_route_stats: Dict[str, Dict[str, Any]] = defaultdict(dict)

# 认证方案
security = HTTPBearer(auto_error=False)

class BaseRouter:
    """基础路由器类，提供统一的路由管理功能"""

    def __init__(self, prefix: str, tags: List[str] = None):
        self.router = APIRouter(prefix=prefix, tags=tags or [])
        self.prefix = prefix
        self.tags = tags or []
        self.middleware = []
        self.route_count = 0

        logger.info(f"BaseRouter created: {prefix} with tags: {tags}")

    def add_middleware(self, middleware_func: Callable):
        """添加路由中间件"""
        self.middleware.append(middleware_func)

    def get_routes_info(self) -> List[Dict[str, Any]]:
        """获取路由信息"""
        routes_info = []
        for route in self.router.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                routes_info.append({
                    "path": route.path,
                    "methods": list(route.methods),
                    "name": getattr(route, 'name', None),
                    "tags": self.tags
                })
        return routes_info

class RouteDecorators:
    """路由装饰器集合"""

    @staticmethod
    def require_auth(required_permissions: List[str] = None):
        """认证装饰器"""
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # 从kwargs中获取认证信息
                credentials = kwargs.get('credentials')
                if not credentials:
                    # 尝试从依赖注入中获取
                    for key, value in kwargs.items():
                        if isinstance(value, HTTPAuthorizationCredentials):
                            credentials = value
                            break

                if not credentials:
                    raise HTTPException(
                        status_code=APIStatus.UNAUTHORIZED,
                        detail="需要认证"
                    )

                # 简化的权限检查（实际项目中应该从数据库或缓存中获取用户信息）
                user_permissions = ["*"]  # 管理员权限

                if required_permissions:
                    if "*" not in user_permissions:
                        for perm in required_permissions:
                            if perm not in user_permissions:
                                raise HTTPException(
                                    status_code=APIStatus.FORBIDDEN,
                                    detail=f"需要权限: {perm}"
                                )

                return await func(*args, **kwargs)
            return wrapper
        return decorator

    @staticmethod
    def rate_limit(requests_per_minute: int = 60, requests_per_hour: int = None):
        """限流装饰器"""
        def decorator(func):
            request_history = defaultdict(list)

            @functools.wraps(func)
            async def wrapper(request: Request = None, *args, **kwargs):
                if not request:
                    # 从args中查找Request对象
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break

                if request:
                    client_ip = request.client.host if request.client else "unknown"
                    now = datetime.now()

                    # 清理过期的请求记录
                    minute_ago = now - timedelta(minutes=1)
                    hour_ago = now - timedelta(hours=1)

                    request_history[client_ip] = [
                        req_time for req_time in request_history[client_ip]
                        if req_time > hour_ago
                    ]

                    # 检查速率限制
                    recent_requests = [
                        req_time for req_time in request_history[client_ip]
                        if req_time > minute_ago
                    ]

                    if len(recent_requests) >= requests_per_minute:
                        raise HTTPException(
                            status_code=APIStatus.TOO_MANY_REQUESTS,
                            detail="请求过于频繁，请稍后再试"
                        )

                    if requests_per_hour:
                        if len(request_history[client_ip]) >= requests_per_hour:
                            raise HTTPException(
                                status_code=APIStatus.TOO_MANY_REQUESTS,
                                detail="每小时请求次数超限"
                            )

                    # 记录本次请求
                    request_history[client_ip].append(now)

                return await func(*args, **kwargs)
            return wrapper
        return decorator

    @staticmethod
    def log_requests(include_response: bool = False):
        """请求日志装饰器"""
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(request: Request = None, *args, **kwargs):
                start_time = time.time()

                if not request:
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break

                if request:
                    logger.info(f"API Request: {request.method} {request.url.path}")

                try:
                    result = await func(*args, **kwargs)

                    duration = time.time() - start_time
                    if request:
                        logger.info(f"API Response: {request.method} {request.url.path} - Success - {duration:.3f}s")

                        # 记录路由统计信息
                        route_key = f"{request.method}:{request.url.path}"
                        if route_key not in _route_stats:
                            _route_stats[route_key] = {
                                "total_requests": 0,
                                "total_time": 0,
                                "avg_time": 0,
                                "last_request": None
                            }

                        _route_stats[route_key]["total_requests"] += 1
                        _route_stats[route_key]["total_time"] += duration
                        _route_stats[route_key]["avg_time"] = (
                                _route_stats[route_key]["total_time"] /
                                _route_stats[route_key]["total_requests"]
                        )
                        _route_stats[route_key]["last_request"] = datetime.now()

                    if include_response:
                        logger.debug(f"Response data: {result}")

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    if request:
                        logger.error(f"API Error: {request.method} {request.url.path} - {str(e)} - {duration:.3f}s")
                    raise

            return wrapper
        return decorator

    @staticmethod
    def validate_json(schema: Dict[str, Any] = None):
        """JSON验证装饰器"""
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(request: Request = None, *args, **kwargs):
                if request and request.method in ["POST", "PUT", "PATCH"]:
                    try:
                        # 基本的JSON格式验证
                        body = await request.json()

                        # 如果提供了schema，进行基本验证
                        if schema and "required" in schema:
                            missing_fields = []
                            for field in schema["required"]:
                                if field not in body:
                                    missing_fields.append(field)

                            if missing_fields:
                                raise HTTPException(
                                    status_code=APIStatus.BAD_REQUEST,
                                    detail=f"缺少必填字段: {', '.join(missing_fields)}"
                                )

                        # 将验证后的数据添加到kwargs
                        kwargs['validated_data'] = body

                    except ValueError as e:
                        raise HTTPException(
                            status_code=APIStatus.BAD_REQUEST,
                            detail="无效的JSON格式"
                        )

                return await func(*args, **kwargs)
            return wrapper
        return decorator

def register_router(router: BaseRouter):
    """注册路由器到全局注册表"""
    _registered_routers.append(router.router)
    logger.info(f"Router registered: {router.prefix} with {len(router.router.routes)} routes")

async def setup_routes(app: FastAPI):
    """设置所有路由"""
    try:
        logger.info("Setting up API routes...")

        # 导入并创建所有路由
        from .container_routes import create_container_router
        from .build_routes import create_build_router
        from .terminal_routes import create_terminal_router

        # 注册路由
        container_router = create_container_router()
        build_router = create_build_router()
        terminal_router = create_terminal_router()

        register_router(container_router)
        register_router(build_router)
        register_router(terminal_router)

        # 将注册的路由添加到应用
        for router in _registered_routers:
            app.include_router(router, prefix=API_V1_PREFIX)

        # 添加系统级路由
        await setup_system_routes(app)

        logger.info(f"Successfully registered {len(_registered_routers)} routers")

    except Exception as e:
        logger.error(f"Failed to setup routes: {e}")
        raise

async def setup_system_routes(app: FastAPI):
    """设置系统级路由"""

    @app.get(f"{API_V1_PREFIX}/health",
             summary="健康检查",
             description="检查API服务健康状态",
             tags=["系统"])
    async def health_check():
        """健康检查端点"""
        from api import health_check
        return await health_check()

    @app.get(f"{API_V1_PREFIX}/info",
             summary="API信息",
             description="获取API基本信息",
             tags=["系统"])
    async def api_info():
        """API信息端点"""
        from api import get_api_info
        return await get_api_info()

    @app.get(f"{API_V1_PREFIX}/routes",
             summary="路由信息",
             description="获取所有注册的路由信息",
             tags=["系统"])
    async def route_info():
        """路由信息端点"""
        routes_info = []
        for router in _registered_routers:
            for route in router.routes:
                if hasattr(route, 'path') and hasattr(route, 'methods'):
                    routes_info.append({
                        "path": route.path,
                        "methods": list(route.methods),
                        "name": getattr(route, 'name', None),
                        "tags": getattr(route, 'tags', [])
                    })

        return create_success_response(
            data={
                "routes": routes_info,
                "total_routes": len(routes_info),
                "total_routers": len(_registered_routers)
            },
            message="路由信息获取成功"
        )

    @app.get(f"{API_V1_PREFIX}/stats",
             summary="API统计信息",
             description="获取API使用统计信息",
             tags=["系统"])
    async def api_stats():
        """API统计信息端点"""
        return create_success_response(
            data={
                "route_stats": dict(_route_stats),
                "total_registered_routes": len(_route_stats),
                "active_routers": len(_registered_routers)
            },
            message="API统计信息获取成功"
        )

def get_route_stats() -> Dict[str, Any]:
    """获取路由统计信息"""
    return dict(_route_stats)

def clear_route_stats():
    """清空路由统计信息"""
    global _route_stats
    _route_stats.clear()
    logger.info("Route statistics cleared")

# 中间件类
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 记录请求开始
        logger.debug(f"Request started: {request.method} {request.url}")

        try:
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 添加响应头
            response.headers["X-Process-Time"] = str(process_time)

            # 记录请求完成
            logger.debug(f"Request completed: {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")

            return response

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(f"Request failed: {request.method} {request.url.path} - {str(e)} - {process_time:.3f}s")
            raise

# 错误处理中间件
class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """统一错误处理中间件"""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except HTTPException:
            raise  # FastAPI会自动处理HTTPException
        except APIError as e:
            # 处理自定义API错误
            logger.warning(f"API Error: {e}")
            raise HTTPException(
                status_code=e.status_code,
                detail=e.message
            )
        except ValidationError as e:
            # 处理验证错误
            logger.warning(f"Validation Error: {e}")
            raise HTTPException(
                status_code=APIStatus.BAD_REQUEST,
                detail=f"数据验证失败: {str(e)}"
            )
        except Exception as e:
            # 处理未知错误
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="服务器内部错误"
            )

# 导出主要组件
__all__ = [
    "BaseRouter",
    "RouteDecorators",
    "register_router",
    "setup_routes",
    "get_route_stats",
    "clear_route_stats",
    "RequestLoggingMiddleware",
    "ErrorHandlingMiddleware",
    "security"
]