# 31. src/__init__.py
"""
eulermaker-docker-optimizer 主包初始化文件

******OSPP-2025-张金荣******

EulerMaker Docker优化器的主包入口，提供：
- 包版本信息和元数据
- 主要组件的快捷导入
- 全局配置和初始化
- 包级别的工具函数
- 向后兼容性支持

主要功能：
- 统一的包接口
- 组件依赖管理
- 全局异常处理
- 日志系统初始化
- 配置验证和加载

使用示例：
    import eulermaker_optimizer as emo

    # 创建应用实例
    app = emo.create_application()

    # 运行服务
    await app.run()

    # 或者使用便捷函数
    emo.run_server(host="0.0.0.0", port=8000)
"""

import os
import sys
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path

# 版本信息
__version__ = "1.0.0"
__author__ = "张金荣"
__email__ = "3487232360@qq.com"
__license__ = "MIT"
__description__ = "EulerMaker Docker Optimizer - 高性能Docker容器和RPM构建管理系统"

# 包元数据
__title__ = "eulermaker-docker-optimizer"
__url__ = "https://github.com/eulermaker/docker-optimizer"
__status__ = "Development"  # Development, Production
__maintainer__ = "张金荣"
__maintainer_email__ = "3487232360@qq.com"

# 兼容性信息
__python_requires__ = ">=3.8"
__platforms__ = ["Linux", "Darwin", "Windows"]

# 包根目录
PACKAGE_ROOT = Path(__file__).parent
PROJECT_ROOT = PACKAGE_ROOT.parent

# 初始化状态
_initialized = False
_app_instance = None

class PackageInfo:
    """包信息类"""

    def __init__(self):
        self.version = __version__
        self.author = __author__
        self.email = __email__
        self.license = __license__
        self.description = __description__
        self.title = __title__
        self.url = __url__
        self.status = __status__
        self.python_requires = __python_requires__
        self.platforms = __platforms__
        self.root_path = PACKAGE_ROOT
        self.project_root = PROJECT_ROOT

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "version": self.version,
            "author": self.author,
            "email": self.email,
            "license": self.license,
            "description": self.description,
            "title": self.title,
            "url": self.url,
            "status": self.status,
            "python_requires": self.python_requires,
            "platforms": self.platforms,
            "root_path": str(self.root_path),
            "project_root": str(self.project_root)
        }

    def __str__(self) -> str:
        return f"{self.title} v{self.version}"

    def __repr__(self) -> str:
        return f"PackageInfo(title='{self.title}', version='{self.version}')"

# 全局包信息实例
package_info = PackageInfo()

def get_version() -> str:
    """获取包版本"""
    return __version__

def get_package_info() -> PackageInfo:
    """获取包信息"""
    return package_info

def check_python_version():
    """检查Python版本兼容性"""
    import sys

    required_version = (3, 8)
    current_version = sys.version_info[:2]

    if current_version < required_version:
        raise RuntimeError(
            f"Python {required_version[0]}.{required_version[1]} or higher is required. "
            f"Current version: {current_version[0]}.{current_version[1]}"
        )

def check_dependencies():
    """检查依赖包"""
    required_packages = [
        'docker',
        'fastapi',
        'uvicorn',
        'aiohttp',
        'pydantic',
        'psutil',
        'msgpack'
    ]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        raise ImportError(
            f"Missing required packages: {', '.join(missing_packages)}. "
            f"Please install them using: pip install {' '.join(missing_packages)}"
        )

def setup_package_paths():
    """设置包路径"""
    # 确保包路径在sys.path中
    package_path = str(PACKAGE_ROOT)
    if package_path not in sys.path:
        sys.path.insert(0, package_path)

    # 设置环境变量
    os.environ['EULERMAKER_PACKAGE_ROOT'] = str(PACKAGE_ROOT)
    os.environ['EULERMAKER_PROJECT_ROOT'] = str(PROJECT_ROOT)

def initialize_logging():
    """初始化日志系统"""
    try:
        from utils.logger import setup_logging
        setup_logging()
    except ImportError as e:
        print(f"Warning: Failed to initialize logging: {e}")

def initialize_config():
    """初始化配置系统"""
    try:
        from config.settings import get_settings
        settings = get_settings()
        return settings
    except ImportError as e:
        print(f"Warning: Failed to initialize config: {e}")
        return None

def validate_environment():
    """验证运行环境"""
    errors = []
    warnings = []

    # 检查Python版本
    try:
        check_python_version()
    except RuntimeError as e:
        errors.append(str(e))

    # 检查依赖包
    try:
        check_dependencies()
    except ImportError as e:
        errors.append(str(e))

    # 检查系统平台
    import platform
    current_platform = platform.system()
    if current_platform not in __platforms__:
        warnings.append(f"Untested platform: {current_platform}")

    # 检查Docker环境
    try:
        import docker
        client = docker.from_env()
        client.ping()
    except Exception as e:
        warnings.append(f"Docker not available: {e}")

    return {"errors": errors, "warnings": warnings}

async def initialize_package():
    """异步初始化包"""
    global _initialized

    if _initialized:
        return

    # 验证环境
    validation_result = validate_environment()

    if validation_result["errors"]:
        raise RuntimeError(f"Environment validation failed: {validation_result['errors']}")

    if validation_result["warnings"]:
        print(f"Environment warnings: {validation_result['warnings']}")

    # 设置路径
    setup_package_paths()

    # 初始化日志
    initialize_logging()

    # 初始化配置
    initialize_config()

    # 标记为已初始化
    _initialized = True

    print(f"EulerMaker Docker Optimizer v{__version__} initialized successfully")

def initialize_package_sync():
    """同步初始化包"""
    asyncio.run(initialize_package())

# 懒加载导入 - 避免循环导入和提高启动速度
def _lazy_import_services():
    """懒加载服务组件"""
    try:
        from services.container_service import ContainerService
        from services.build_service import BuildService
        from services.terminal_service import TerminalService
        from services.probe_service import ProbeService
        return {
            "container": ContainerService,
            "build": BuildService,
            "terminal": TerminalService,
            "probe": ProbeService
        }
    except ImportError as e:
        print(f"Warning: Failed to import services: {e}")
        return {}

def _lazy_import_api():
    """懒加载API组件"""
    try:
        from api.web_server import WebServer, create_web_server
        from api.websocket_server import WebSocketServer, ws_server
        from api.rpc_server import RPCServer, create_rpc_server
        return {
            "web_server": WebServer,
            "create_web_server": create_web_server,
            "websocket_server": WebSocketServer,
            "ws_server": ws_server,
            "rpc_server": RPCServer,
            "create_rpc_server": create_rpc_server
        }
    except ImportError as e:
        print(f"Warning: Failed to import API components: {e}")
        return {}

def _lazy_import_core():
    """懒加载核心组件"""
    try:
        from core.docker_manager import DockerManager
        from core.container_lifecycle import ContainerLifecycle
        from core.build_manager import BuildManager
        from core.probe_manager import ProbeManager
        return {
            "docker_manager": DockerManager,
            "container_lifecycle": ContainerLifecycle,
            "build_manager": BuildManager,
            "probe_manager": ProbeManager
        }
    except ImportError as e:
        print(f"Warning: Failed to import core components: {e}")
        return {}

class Application:
    """应用程序主类"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.services = {}
        self.servers = {}
        self.is_running = False

        # 初始化组件
        self._initialize_components()

    def _initialize_components(self):
        """初始化应用组件"""
        # 懒加载服务
        services = _lazy_import_services()
        for name, service_class in services.items():
            if service_class:
                self.services[name] = service_class()

        # 懒加载API服务器
        api_components = _lazy_import_api()
        if "create_web_server" in api_components:
            self.servers["web"] = api_components["create_web_server"]()
        if "ws_server" in api_components:
            self.servers["websocket"] = api_components["ws_server"]
        if "create_rpc_server" in api_components:
            self.servers["rpc"] = api_components["create_rpc_server"]()

    async def start(self):
        """启动应用"""
        if self.is_running:
            print("Application is already running")
            return

        print(f"Starting {package_info.title} v{package_info.version}...")

        # 确保包已初始化
        await initialize_package()

        # 启动服务器
        start_tasks = []

        if "web" in self.servers:
            start_tasks.append(self.servers["web"].start())

        if "websocket" in self.servers:
            start_tasks.append(self.servers["websocket"].start())

        if "rpc" in self.servers:
            start_tasks.append(self.servers["rpc"].start())

        if start_tasks:
            await asyncio.gather(*start_tasks, return_exceptions=True)

        self.is_running = True
        print("Application started successfully")

    async def stop(self):
        """停止应用"""
        if not self.is_running:
            print("Application is not running")
            return

        print("Stopping application...")

        # 停止服务器
        stop_tasks = []

        if "web" in self.servers:
            stop_tasks.append(self.servers["web"].stop())

        if "websocket" in self.servers:
            stop_tasks.append(self.servers["websocket"].stop())

        if "rpc" in self.servers:
            stop_tasks.append(self.servers["rpc"].stop())

        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        self.is_running = False
        print("Application stopped")

    async def run(self):
        """运行应用（启动并等待）"""
        try:
            await self.start()

            # 等待直到收到停止信号
            while self.is_running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("Received interrupt signal")
        finally:
            await self.stop()

    def get_service(self, name: str):
        """获取服务实例"""
        return self.services.get(name)

    def get_server(self, name: str):
        """获取服务器实例"""
        return self.servers.get(name)

def create_application(config: Dict[str, Any] = None) -> Application:
    """创建应用实例"""
    global _app_instance

    if _app_instance is None:
        _app_instance = Application(config)

    return _app_instance

def get_application() -> Optional[Application]:
    """获取应用实例"""
    return _app_instance

# 便捷函数
async def run_server(host: str = "0.0.0.0", port: int = 8000,
                     enable_websocket: bool = True, enable_rpc: bool = True,
                     config: Dict[str, Any] = None):
    """运行服务器（便捷函数）"""
    app_config = {
        "web_server": {
            "host": host,
            "port": port
        },
        "enable_websocket": enable_websocket,
        "enable_rpc": enable_rpc
    }

    if config:
        app_config.update(config)

    app = create_application(app_config)
    await app.run()

def run_server_sync(host: str = "0.0.0.0", port: int = 8000, **kwargs):
    """同步运行服务器"""
    asyncio.run(run_server(host=host, port=port, **kwargs))

# 模块级别的初始化
def _module_init():
    """模块初始化"""
    # 在导入时自动进行基本检查
    try:
        check_python_version()
        setup_package_paths()
    except Exception as e:
        print(f"Warning: Module initialization failed: {e}")

# 自动执行模块初始化
_module_init()

# 导出的主要接口
__all__ = [
    # 版本和包信息
    "__version__",
    "__author__",
    "__email__",
    "__license__",
    "__description__",
    "__title__",
    "__url__",
    "package_info",
    "get_version",
    "get_package_info",

    # 应用类和函数
    "Application",
    "create_application",
    "get_application",
    "run_server",
    "run_server_sync",

    # 初始化函数
    "initialize_package",
    "initialize_package_sync",
    "validate_environment",

    # 实用函数
    "check_python_version",
    "check_dependencies",

    # 路径常量
    "PACKAGE_ROOT",
    "PROJECT_ROOT"
]

# 提供快捷导入
try:
    # 尝试导入常用组件，失败时不影响包的基本使用
    from utils.logger import get_logger
    from utils.exceptions import APIError, ValidationError
    from config.settings import get_settings

    __all__.extend([
        "get_logger",
        "APIError",
        "ValidationError",
        "get_settings"
    ])

except ImportError:
    # 导入失败时显示警告但不中断
    pass

# 包级别的文档字符串
__doc__ = f"""
{__title__} v{__version__}

{__description__}

这个包提供了完整的Docker容器管理和RPM包构建解决方案，包括：

核心功能：
- Docker容器生命周期管理
- RPM包构建和管理  
- Web终端服务
- 系统监控和告警
- RESTful API接口
- WebSocket实时通信
- RPC服务接口

主要组件：
- Web服务器 (FastAPI)
- WebSocket服务器
- RPC服务器
- 容器管理服务
- 构建管理服务
- 终端服务
- 监控探针服务

快速开始：
    import eulermaker_optimizer as emo
    
    # 创建并运行应用
    app = emo.create_application()
    await app.run()
    
    # 或使用便捷函数
    emo.run_server_sync(host="0.0.0.0", port=8000)

"""