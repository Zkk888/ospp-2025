# 32. src/main.py
"""
eulermaker-docker-optimizer 主程序入口文件

******OSPP-2025-张金荣******

项目的主入口文件，负责：
- 初始化和启动所有核心服务
- 配置和管理应用生命周期
- 处理启动参数和配置选项
- 优雅启动和关闭流程
- 信号处理和异常管理

主要功能：
- Web API服务器启动
- WebSocket服务器启动
- RPC服务器启动
- 后台任务调度
- 系统监控和健康检查
- 配置热重载

支持的启动模式：
- 开发模式：单进程，热重载，详细日志
- 生产模式：多进程，负载均衡，优化性能
- 容器模式：Docker容器内运行
- 集群模式：分布式部署
"""

import asyncio
import signal
import sys
import os
import argparse
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from pathlib import Path

# 添加项目路径到sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入项目模块
from config.settings import get_settings
from utils.logger import get_logger, setup_logging
from utils.exceptions import APIError
from api.web_server import WebServer, create_web_server
from api.websocket_server import WebSocketServer, ws_server
from api.rpc_server import RPCServer, create_rpc_server

# 导入服务组件
from services.container_service import ContainerService
from services.build_service import BuildService
from services.terminal_service import TerminalService
from services.probe_service import ProbeService

# 导入核心组件
from core.docker_manager import DockerManager
from core.container_lifecycle import ContainerLifecycle
from core.build_manager import BuildManager
from core.probe_manager import ProbeManager

# 全局变量
logger = None
settings = None
app_instance = None

class EulerMakerDockerOptimizer:
    """EulerMaker Docker优化器主应用类"""

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化主应用

        Args:
            config: 应用配置字典
        """
        self.config = config or {}
        self.settings = get_settings()
        self.logger = get_logger(__name__)

        # 服务器实例
        self.web_server = None
        self.websocket_server = None
        self.rpc_server = None

        # 服务实例
        self.services = {}
        self.core_components = {}

        # 运行状态
        self.is_running = False
        self.startup_time = None
        self.background_tasks = []

        # 信号处理
        self.shutdown_event = asyncio.Event()

        self.logger.info(f"EulerMaker Docker Optimizer initialized")

    async def initialize_core_components(self):
        """初始化核心组件"""
        try:
            self.logger.info("Initializing core components...")

            # 初始化Docker管理器
            self.core_components['docker_manager'] = DockerManager()
            await self.core_components['docker_manager'].initialize()

            # 初始化容器生命周期管理器
            self.core_components['container_lifecycle'] = ContainerLifecycle(
                docker_manager=self.core_components['docker_manager']
            )

            # 初始化探针管理器
            self.core_components['probe_manager'] = ProbeManager(
                docker_manager=self.core_components['docker_manager']
            )
            await self.core_components['probe_manager'].initialize()

            # 初始化构建管理器
            self.core_components['build_manager'] = BuildManager(
                docker_manager=self.core_components['docker_manager'],
                container_lifecycle=self.core_components['container_lifecycle']
            )
            await self.core_components['build_manager'].initialize()

            self.logger.info("Core components initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize core components: {e}")
            raise

    async def initialize_services(self):
        """初始化业务服务"""
        try:
            self.logger.info("Initializing services...")

            # 初始化容器服务
            self.services['container'] = ContainerService()
            await self.services['container'].initialize()

            # 初始化构建服务
            self.services['build'] = BuildService()
            await self.services['build'].initialize()

            # 初始化终端服务
            self.services['terminal'] = TerminalService()
            await self.services['terminal'].initialize()

            # 初始化探针服务
            self.services['probe'] = ProbeService()
            await self.services['probe'].initialize()

            self.logger.info("Services initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize services: {e}")
            raise

    async def initialize_servers(self):
        """初始化服务器"""
        try:
            self.logger.info("Initializing servers...")

            # 获取配置
            web_config = self.config.get('web_server', {})
            websocket_config = self.config.get('websocket_server', {})
            rpc_config = self.config.get('rpc_server', {})

            # 初始化Web服务器
            if self.config.get('enable_web_server', True):
                self.web_server = create_web_server(
                    host=web_config.get('host', self.settings.API_HOST or '0.0.0.0'),
                    port=web_config.get('port', self.settings.API_PORT or 8000),
                    debug=web_config.get('debug', self.settings.DEBUG)
                )
                self.logger.info(f"Web server configured: {self.web_server.host}:{self.web_server.port}")

            # 初始化WebSocket服务器
            if self.config.get('enable_websocket_server', True):
                self.websocket_server = ws_server
                self.logger.info("WebSocket server configured")

            # 初始化RPC服务器
            if self.config.get('enable_rpc_server', True):
                self.rpc_server = create_rpc_server(
                    host=rpc_config.get('host', '0.0.0.0'),
                    port=rpc_config.get('port', self.settings.RPC_PORT or 9000)
                )
                self.logger.info(f"RPC server configured: {self.rpc_server.host}:{self.rpc_server.port}")

            self.logger.info("Servers initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize servers: {e}")
            raise

    async def start_background_tasks(self):
        """启动后台任务"""
        try:
            self.logger.info("Starting background tasks...")

            # 启动系统监控任务
            monitor_task = asyncio.create_task(self._system_monitor_task())
            self.background_tasks.append(monitor_task)

            # 启动健康检查任务
            health_check_task = asyncio.create_task(self._health_check_task())
            self.background_tasks.append(health_check_task)

            # 启动清理任务
            cleanup_task = asyncio.create_task(self._cleanup_task())
            self.background_tasks.append(cleanup_task)

            # 启动构建队列处理任务
            if 'build' in self.services:
                build_queue_task = asyncio.create_task(
                    self.services['build'].start_queue_processor()
                )
                self.background_tasks.append(build_queue_task)

            self.logger.info(f"Started {len(self.background_tasks)} background tasks")

        except Exception as e:
            self.logger.error(f"Failed to start background tasks: {e}")
            raise

    async def start_servers(self):
        """启动所有服务器"""
        try:
            self.logger.info("Starting servers...")

            start_tasks = []

            # 启动WebSocket服务器
            if self.websocket_server:
                start_tasks.append(self.websocket_server.start())

            # 启动RPC服务器
            if self.rpc_server:
                start_tasks.append(self.rpc_server.start())

            # 启动Web服务器（最后启动，因为它会阻塞）
            if self.web_server:
                start_tasks.append(self.web_server.start())

            if start_tasks:
                # 并发启动所有服务器
                await asyncio.gather(*start_tasks)

            self.logger.info("All servers started successfully")

        except Exception as e:
            self.logger.error(f"Failed to start servers: {e}")
            raise

    async def start(self):
        """启动应用"""
        try:
            import time
            start_time = time.time()

            self.logger.info("=" * 60)
            self.logger.info("Starting EulerMaker Docker Optimizer...")
            self.logger.info("=" * 60)

            # 初始化核心组件
            await self.initialize_core_components()

            # 初始化服务
            await self.initialize_services()

            # 初始化服务器
            await self.initialize_servers()

            # 启动后台任务
            await self.start_background_tasks()

            # 设置信号处理
            self._setup_signal_handlers()

            # 记录启动完成
            self.startup_time = time.time()
            startup_duration = self.startup_time - start_time

            self.logger.info("=" * 60)
            self.logger.info(f"EulerMaker Docker Optimizer started successfully!")
            self.logger.info(f"Startup time: {startup_duration:.2f} seconds")
            self.logger.info("=" * 60)

            # 打印服务信息
            self._print_service_info()

            self.is_running = True

            # 启动服务器（这会阻塞直到收到关闭信号）
            await self.start_servers()

        except Exception as e:
            self.logger.error(f"Failed to start application: {e}")
            await self.stop()
            raise

    async def stop(self):
        """停止应用"""
        if not self.is_running:
            self.logger.warning("Application is not running")
            return

        try:
            self.logger.info("Stopping EulerMaker Docker Optimizer...")

            # 停止后台任务
            if self.background_tasks:
                self.logger.info("Stopping background tasks...")
                for task in self.background_tasks:
                    if not task.done():
                        task.cancel()

                # 等待所有任务完成或取消
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
                self.background_tasks.clear()

            # 停止服务器
            stop_tasks = []

            if self.web_server:
                self.logger.info("Stopping Web server...")
                stop_tasks.append(self.web_server.stop())

            if self.websocket_server:
                self.logger.info("Stopping WebSocket server...")
                stop_tasks.append(self.websocket_server.stop())

            if self.rpc_server:
                self.logger.info("Stopping RPC server...")
                stop_tasks.append(self.rpc_server.stop())

            if stop_tasks:
                await asyncio.gather(*stop_tasks, return_exceptions=True)

            # 清理服务
            self.logger.info("Cleaning up services...")
            for service_name, service in self.services.items():
                try:
                    if hasattr(service, 'cleanup'):
                        await service.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up service {service_name}: {e}")

            # 清理核心组件
            self.logger.info("Cleaning up core components...")
            for component_name, component in self.core_components.items():
                try:
                    if hasattr(component, 'cleanup'):
                        await component.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up component {component_name}: {e}")

            self.is_running = False

            self.logger.info("EulerMaker Docker Optimizer stopped successfully")

        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}")
            self.shutdown_event.set()

        # 只在主线程中设置信号处理器
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, signal_handler)

    def _print_service_info(self):
        """打印服务信息"""
        self.logger.info("Service Information:")

        if self.web_server:
            self.logger.info(f"  Web API: http://{self.web_server.host}:{self.web_server.port}")
            self.logger.info(f"  API Docs: http://{self.web_server.host}:{self.web_server.port}/api/v1/docs")

        if self.websocket_server:
            host = self.web_server.host if self.web_server else 'localhost'
            port = self.web_server.port if self.web_server else 8000
            self.logger.info(f"  WebSocket: ws://{host}:{port}/ws/")

        if self.rpc_server:
            self.logger.info(f"  RPC API: http://{self.rpc_server.host}:{self.rpc_server.port}/rpc")

        self.logger.info(f"  Core Components: {len(self.core_components)}")
        self.logger.info(f"  Services: {len(self.services)}")
        self.logger.info(f"  Background Tasks: {len(self.background_tasks)}")

    async def _system_monitor_task(self):
        """系统监控后台任务"""
        try:
            import psutil

            while self.is_running:
                try:
                    # 获取系统资源使用情况
                    cpu_percent = psutil.cpu_percent(interval=1)
                    memory = psutil.virtual_memory()
                    disk = psutil.disk_usage('/')

                    # 记录系统状态（只在DEBUG模式下）
                    if self.settings.DEBUG:
                        self.logger.debug(f"System Stats - CPU: {cpu_percent}%, "
                                          f"Memory: {memory.percent}%, "
                                          f"Disk: {disk.percent}%")

                    # 检查资源使用是否过高
                    if cpu_percent > 90:
                        self.logger.warning(f"High CPU usage: {cpu_percent}%")

                    if memory.percent > 90:
                        self.logger.warning(f"High memory usage: {memory.percent}%")

                    if disk.percent > 90:
                        self.logger.warning(f"High disk usage: {disk.percent}%")

                    # 推送系统状态到WebSocket客户端
                    if self.websocket_server:
                        from api.websocket_server import push_system_alert

                        if cpu_percent > 80 or memory.percent > 80:
                            await push_system_alert(
                                "resource_usage",
                                f"系统资源使用率较高 - CPU: {cpu_percent}%, Memory: {memory.percent}%",
                                "warning"
                            )

                    await asyncio.sleep(60)  # 每分钟检查一次

                except Exception as e:
                    self.logger.error(f"Error in system monitor: {e}")
                    await asyncio.sleep(60)

        except asyncio.CancelledError:
            self.logger.info("System monitor task cancelled")
        except Exception as e:
            self.logger.error(f"System monitor task error: {e}")

    async def _health_check_task(self):
        """健康检查后台任务"""
        try:
            while self.is_running:
                try:
                    # 检查Docker连接
                    if 'docker_manager' in self.core_components:
                        docker_health = await self.core_components['docker_manager'].health_check()
                        if not docker_health:
                            self.logger.error("Docker connection unhealthy")

                    # 检查服务健康状态
                    unhealthy_services = []
                    for service_name, service in self.services.items():
                        if hasattr(service, 'health_check'):
                            try:
                                health = await service.health_check()
                                if not health:
                                    unhealthy_services.append(service_name)
                            except Exception as e:
                                self.logger.error(f"Health check failed for {service_name}: {e}")
                                unhealthy_services.append(service_name)

                    if unhealthy_services:
                        self.logger.warning(f"Unhealthy services: {unhealthy_services}")

                    await asyncio.sleep(30)  # 每30秒检查一次

                except Exception as e:
                    self.logger.error(f"Error in health check: {e}")
                    await asyncio.sleep(30)

        except asyncio.CancelledError:
            self.logger.info("Health check task cancelled")
        except Exception as e:
            self.logger.error(f"Health check task error: {e}")

    async def _cleanup_task(self):
        """清理任务"""
        try:
            while self.is_running:
                try:
                    # 清理过期的终端会话
                    if 'terminal' in self.services:
                        await self.services['terminal'].cleanup_expired_sessions()

                    # 清理完成的构建任务
                    if 'build' in self.services:
                        await self.services['build'].cleanup_completed_builds()

                    # 清理临时文件
                    temp_dir = Path('/tmp/eulermaker-optimizer')
                    if temp_dir.exists():
                        import shutil
                        try:
                            # 清理7天前的临时文件
                            import time
                            now = time.time()
                            for item in temp_dir.iterdir():
                                if now - item.stat().st_mtime > 7 * 24 * 3600:
                                    if item.is_file():
                                        item.unlink()
                                    elif item.is_dir():
                                        shutil.rmtree(item)
                        except Exception as e:
                            self.logger.error(f"Error cleaning temp files: {e}")

                    await asyncio.sleep(3600)  # 每小时清理一次

                except Exception as e:
                    self.logger.error(f"Error in cleanup task: {e}")
                    await asyncio.sleep(3600)

        except asyncio.CancelledError:
            self.logger.info("Cleanup task cancelled")
        except Exception as e:
            self.logger.error(f"Cleanup task error: {e}")

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="EulerMaker Docker Optimizer")

    # 基本参数
    parser.add_argument("--host", default="0.0.0.0", help="Web服务器绑定地址")
    parser.add_argument("--port", type=int, default=8000, help="Web服务器端口")
    parser.add_argument("--rpc-port", type=int, default=9000, help="RPC服务器端口")

    # 功能开关
    parser.add_argument("--disable-websocket", action="store_true", help="禁用WebSocket服务器")
    parser.add_argument("--disable-rpc", action="store_true", help="禁用RPC服务器")

    # 模式选择
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument("--reload", action="store_true", help="启用热重载（仅开发模式）")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数（生产模式）")

    # 配置文件
    parser.add_argument("--config", help="配置文件路径")

    # 日志级别
    parser.add_argument("--log-level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default='INFO', help="日志级别")

    return parser.parse_args()

def load_config_from_file(config_path: str) -> Dict[str, Any]:
    """从文件加载配置"""
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Failed to load config file {config_path}: {e}")
        return {}

def create_app_config(args) -> Dict[str, Any]:
    """创建应用配置"""
    config = {
        'web_server': {
            'host': args.host,
            'port': args.port,
            'debug': args.debug,
            'reload': args.reload and args.debug
        },
        'rpc_server': {
            'host': args.host,
            'port': args.rpc_port
        },
        'enable_websocket_server': not args.disable_websocket,
        'enable_rpc_server': not args.disable_rpc,
        'workers': args.workers,
        'log_level': args.log_level
    }

    # 如果指定了配置文件，合并配置
    if args.config and os.path.exists(args.config):
        file_config = load_config_from_file(args.config)
        config.update(file_config)

    return config

async def main():
    """主函数"""
    global logger, settings, app_instance

    try:
        # 解析命令行参数
        args = parse_arguments()

        # 初始化日志系统
        setup_logging(level=getattr(logging, args.log_level))
        logger = get_logger(__name__)

        # 加载设置
        settings = get_settings()

        # 创建应用配置
        app_config = create_app_config(args)

        logger.info(f"Starting with config: {app_config}")

        # 创建应用实例
        app_instance = EulerMakerDockerOptimizer(app_config)

        # 启动应用
        await app_instance.start()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if app_instance:
            await app_instance.stop()

def run_sync():
    """同步运行入口"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

# 程序入口点
if __name__ == "__main__":
    run_sync()