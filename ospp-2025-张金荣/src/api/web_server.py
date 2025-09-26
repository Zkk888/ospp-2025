# 28. src/api/web_server.py
"""
Web API服务器 - eulermaker-docker-optimizer的主Web API服务器

******OSPP-2025-张金荣******

基于FastAPI实现的高性能Web API服务器，提供：
- RESTful API接口服务
- 自动API文档生成（Swagger/OpenAPI）
- 请求验证和响应序列化
- 中间件集成（CORS、认证、日志、限流等）
- 健康检查和监控端点
- 静态文件服务
- 优雅启动和关闭

主要特性：
- 异步高性能处理
- 自动错误处理和日志记录
- API版本管理
- 请求/响应格式标准化
- 安全性增强（HTTPS、CORS、认证等）
- 监控指标收集
- 开发友好的调试功能
"""

import asyncio
import signal
import sys
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
import uvicorn
from datetime import datetime

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.sessions import SessionMiddleware

from utils.logger import get_logger, setup_logging
from utils.exceptions import APIError
from config.settings import get_settings
from api import (
    API_VERSION, API_TITLE, API_DESCRIPTION,
    DEFAULT_HOST, DEFAULT_PORT, API_V1_PREFIX,
    get_api_info, health_check
)
from api.routes import setup_routes

logger = get_logger(__name__)
settings = get_settings()

# 全局变量
app_instance = None
server_start_time = None

# HTTP Bearer认证方案
security = HTTPBearer(auto_error=False)

class WebServer:
    """Web API服务器类"""

    def __init__(self,
                 host: str = None,
                 port: int = None,
                 debug: bool = None,
                 reload: bool = False):
        """
        初始化Web服务器

        Args:
            host: 服务器绑定地址
            port: 服务器端口
            debug: 调试模式
            reload: 热重载模式（开发用）
        """
        self.host = host or settings.API_HOST or DEFAULT_HOST
        self.port = port or settings.API_PORT or DEFAULT_PORT
        self.debug = debug if debug is not None else settings.DEBUG
        self.reload = reload and self.debug  # 只在调试模式下启用热重载

        # 服务器状态
        self.is_running = False
        self.server = None
        self.app = None

        logger.info(f"WebServer initialized - host: {self.host}, port: {self.port}, debug: {self.debug}")

    async def create_app(self) -> FastAPI:
        """创建FastAPI应用实例"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """应用生命周期管理"""
            # 启动时执行
            global server_start_time
            server_start_time = datetime.now()

            logger.info("Starting up web server...")

            # 初始化各种服务组件
            await self.initialize_services()

            logger.info("Web server startup complete")

            yield  # 应用运行期间

            # 关闭时执行
            logger.info("Shutting down web server...")
            await self.cleanup_services()
            logger.info("Web server shutdown complete")

        # 创建FastAPI应用
        app = FastAPI(
            title=API_TITLE,
            version=API_VERSION,
            description=API_DESCRIPTION,
            debug=self.debug,
            lifespan=lifespan,
            openapi_url=f"{API_V1_PREFIX}/openapi.json" if self.debug else None,
            docs_url=f"{API_V1_PREFIX}/docs" if self.debug else None,
            redoc_url=f"{API_V1_PREFIX}/redoc" if self.debug else None,
            # 自定义OpenAPI配置
            openapi_tags=[
                {
                    "name": "健康检查",
                    "description": "系统健康状态和监控相关接口"
                },
                {
                    "name": "系统信息",
                    "description": "系统信息和资源状态接口"
                },
                {
                    "name": "容器管理",
                    "description": "Docker容器生命周期管理接口"
                },
                {
                    "name": "构建管理",
                    "description": "RPM包构建任务管理接口"
                },
                {
                    "name": "终端服务",
                    "description": "Web终端访问和管理接口"
                }
            ]
        )

        # 配置中间件
        await self.setup_middlewares(app)

        # 配置路由
        await self.setup_routes(app)

        # 配置静态文件服务
        await self.setup_static_files(app)

        # 配置自定义端点
        await self.setup_custom_endpoints(app)

        return app

    async def setup_middlewares(self, app: FastAPI):
        """配置中间件"""

        # 1. 受信任主机中间件（安全性）
        if not self.debug:
            trusted_hosts = settings.ALLOWED_HOSTS or ["*"]
            app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)

        # 2. 会话中间件
        session_secret = settings.SECRET_KEY or "dev-secret-key-change-in-production"
        app.add_middleware(SessionMiddleware, secret_key=session_secret)

        # 3. 自定义请求日志中间件
        @app.middleware("http")
        async def request_logging_middleware(request: Request, call_next):
            start_time = datetime.now()

            # 记录请求开始
            logger.debug(f"Request started: {request.method} {request.url}")

            try:
                # 执行请求
                response = await call_next(request)

                # 计算处理时间
                process_time = (datetime.now() - start_time).total_seconds()

                # 记录请求完成
                logger.info(
                    f"Request completed: {request.method} {request.url.path} "
                    f"- Status: {response.status_code} "
                    f"- Duration: {process_time:.3f}s"
                )

                # 添加响应头
                response.headers["X-Process-Time"] = str(process_time)
                response.headers["X-Server-Time"] = datetime.now().isoformat()

                return response

            except Exception as e:
                process_time = (datetime.now() - start_time).total_seconds()
                logger.error(
                    f"Request failed: {request.method} {request.url.path} "
                    f"- Error: {str(e)} "
                    f"- Duration: {process_time:.3f}s"
                )
                raise

        # 4. 安全头中间件
        @app.middleware("http")
        async def security_headers_middleware(request: Request, call_next):
            response = await call_next(request)

            # 添加安全相关的HTTP头
            if not self.debug:
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["X-XSS-Protection"] = "1; mode=block"
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

            response.headers["X-API-Version"] = API_VERSION
            response.headers["Server"] = "EulerMaker-Docker-Optimizer"

            return response

    async def setup_routes(self, app: FastAPI):
        """配置路由"""
        try:
            # 使用统一路由设置函数
            await setup_routes(app)
            logger.info("All routes configured successfully")

        except Exception as e:
            logger.error(f"Failed to setup routes: {e}")
            raise

    async def setup_static_files(self, app: FastAPI):
        """配置静态文件服务"""
        try:
            static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
            if os.path.exists(static_dir):
                app.mount("/static", StaticFiles(directory=static_dir), name="static")
                logger.info(f"Static files mounted from: {static_dir}")
            else:
                logger.warning(f"Static directory not found: {static_dir}")

        except Exception as e:
            logger.error(f"Failed to setup static files: {e}")

    async def setup_custom_endpoints(self, app: FastAPI):
        """配置自定义端点"""

        @app.get("/",
                 summary="API根路径",
                 description="获取API基本信息和状态")
        async def root():
            """API根端点"""
            return await get_api_info()

        @app.get("/ping",
                 summary="简单健康检查",
                 description="快速健康检查端点")
        async def ping():
            """简单ping端点"""
            return {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "version": API_VERSION
            }

        @app.get("/favicon.ico", include_in_schema=False)
        async def favicon():
            """网站图标"""
            return Response(status_code=204)

        # 开发模式下的调试端点
        if self.debug:
            @app.get("/debug/info",
                     summary="调试信息",
                     description="获取服务器调试信息")
            async def debug_info():
                """调试信息端点"""
                import psutil
                import platform

                return {
                    "server_info": {
                        "python_version": platform.python_version(),
                        "platform": platform.platform(),
                        "host": self.host,
                        "port": self.port,
                        "debug_mode": self.debug,
                        "start_time": server_start_time.isoformat() if server_start_time else None
                    },
                    "system_info": {
                        "cpu_count": psutil.cpu_count(),
                        "memory_total": psutil.virtual_memory().total,
                        "disk_usage": dict(psutil.disk_usage('/'))
                    },
                    "process_info": {
                        "pid": os.getpid(),
                        "memory_usage": psutil.Process().memory_info().rss,
                        "cpu_percent": psutil.Process().cpu_percent()
                    }
                }

            @app.get("/debug/routes",
                     summary="路由信息",
                     description="获取所有注册的路由信息")
            async def debug_routes():
                """路由信息端点"""
                routes = []
                for route in app.routes:
                    if hasattr(route, 'path') and hasattr(route, 'methods'):
                        routes.append({
                            "path": route.path,
                            "methods": list(route.methods),
                            "name": getattr(route, 'name', None)
                        })

                return {
                    "total_routes": len(routes),
                    "routes": routes
                }

    async def initialize_services(self):
        """初始化各种服务组件"""
        try:
            # 这里可以初始化各种服务
            # 例如：数据库连接、缓存、外部服务等

            # 初始化日志系统
            setup_logging()

            # 初始化其他服务
            logger.info("All services initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            raise

    async def cleanup_services(self):
        """清理服务组件"""
        try:
            # 清理各种资源
            # 例如：关闭数据库连接、清理缓存等

            logger.info("All services cleaned up successfully")

        except Exception as e:
            logger.error(f"Failed to cleanup services: {e}")

    async def start(self):
        """启动Web服务器"""
        try:
            if self.is_running:
                logger.warning("Web server is already running")
                return

            logger.info(f"Starting web server on {self.host}:{self.port}")

            # 创建FastAPI应用
            self.app = await self.create_app()
            global app_instance
            app_instance = self.app

            # 配置uvicorn服务器
            config = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                reload=self.reload,
                log_config=None,  # 使用自定义日志配置
                access_log=self.debug,
                server_header=False,
                date_header=False
            )

            # 创建服务器实例
            self.server = uvicorn.Server(config)

            # 设置信号处理器
            self.setup_signal_handlers()

            # 标记服务器为运行状态
            self.is_running = True

            # 启动服务器
            logger.info(f"Web server starting at http://{self.host}:{self.port}")
            if self.debug:
                logger.info(f"API documentation available at http://{self.host}:{self.port}{API_V1_PREFIX}/docs")

            await self.server.serve()

        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            self.is_running = False
            raise

    async def stop(self):
        """停止Web服务器"""
        try:
            if not self.is_running:
                logger.warning("Web server is not running")
                return

            logger.info("Stopping web server...")

            if self.server:
                self.server.should_exit = True

            self.is_running = False
            logger.info("Web server stopped")

        except Exception as e:
            logger.error(f"Failed to stop web server: {e}")
            raise

    def setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            if self.server:
                self.server.should_exit = True

        # 只在主线程中设置信号处理器
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, signal_handler)

    def get_app(self) -> FastAPI:
        """获取FastAPI应用实例"""
        return self.app

# 认证依赖函数
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[Dict[str, Any]]:
    """获取当前认证用户

    这是一个简化的认证实现，生产环境应该使用更安全的方式
    """
    if not credentials:
        return None

    try:
        # 这里应该实现实际的token验证逻辑
        # 例如：JWT验证、API Key验证等

        # 简化实现：检查token格式
        if credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")

        token = credentials.credentials

        # 这里应该验证token并返回用户信息
        # 目前返回模拟用户数据
        return {
            "user_id": "admin",
            "username": "admin",
            "permissions": ["*"]  # 管理员权限
        }

    except Exception as e:
        logger.warning(f"Authentication failed: {e}")
        return None

def require_auth(permissions: List[str] = None):
    """认证装饰器依赖"""
    def _auth_dependency(user: Dict[str, Any] = Depends(get_current_user)):
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Authentication required"
            )

        # 检查权限
        if permissions:
            user_permissions = user.get("permissions", [])
            if "*" not in user_permissions:  # 管理员权限
                for perm in permissions:
                    if perm not in user_permissions:
                        raise HTTPException(
                            status_code=403,
                            detail=f"Permission '{perm}' required"
                        )

        return user

    return _auth_dependency

# 工厂函数
def create_web_server(**kwargs) -> WebServer:
    """创建Web服务器实例"""
    return WebServer(**kwargs)

async def run_web_server(host: str = None,
                         port: int = None,
                         debug: bool = None,
                         reload: bool = False):
    """运行Web服务器（便捷函数）"""
    server = create_web_server(host=host, port=port, debug=debug, reload=reload)
    await server.start()

# 用于开发的快速启动函数
def dev_server(host: str = "127.0.0.1", port: int = 8000):
    """开发服务器快速启动"""
    async def _run():
        await run_web_server(host=host, port=port, debug=True, reload=True)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Development server stopped by user")
    except Exception as e:
        logger.error(f"Development server error: {e}")
        sys.exit(1)

# 命令行入口
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EulerMaker Docker Optimizer Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    if args.debug or args.reload:
        logger.info("Starting in development mode")
        dev_server(host=args.host, port=args.port)
    else:
        logger.info("Starting in production mode")
        asyncio.run(run_web_server(
            host=args.host,
            port=args.port,
            debug=args.debug,
            reload=args.reload
        ))

# 导出主要组件
__all__ = [
    "WebServer",
    "create_web_server",
    "run_web_server",
    "dev_server",
    "get_current_user",
    "require_auth",
    "app_instance"
]