"""
业务服务层包 - eulermaker-docker-optimizer的业务服务层

******OSPP-2025-张金荣******

包含所有业务服务类，提供高层次的业务逻辑封装：
- 容器服务：容器管理的业务逻辑封装
- 构建服务：RPM构建业务逻辑封装
- 探针服务：监控探针业务逻辑封装
- 终端服务：Web终端业务逻辑封装

业务服务层位于核心功能层之上，API接口层之下，负责：
- 封装复杂的业务操作流程
- 提供统一的服务接口
- 处理业务逻辑和数据转换
- 协调多个核心组件的操作
"""

from .container_service import (
    ContainerService,
    ContainerOperation,
    ContainerHealthStatus,
)

from .build_service import (
    BuildService,
    BuildOperationType,
    BuildScheduler,
)

from .probe_service import (
    ProbeService,
    MonitoringScheduler,
    AlertManager,
)

from .terminal_service import (
    TerminalService,
    TerminalSession,
    TerminalWebSocketHandler,
)

# 版本信息
__version__ = "1.0.0"

# 导出所有服务类
__all__ = [
    # Container Service
    "ContainerService",
    "ContainerOperation",
    "ContainerHealthStatus",

    # Build Service
    "BuildService",
    "BuildOperationType",
    "BuildScheduler",

    # Probe Service
    "ProbeService",
    "MonitoringScheduler",
    "AlertManager",

    # Terminal Service
    "TerminalService",
    "TerminalSession",
    "TerminalWebSocketHandler",
]

# 服务注册表
_service_instances = {}


async def get_container_service() -> ContainerService:
    """获取容器服务实例"""
    if 'container_service' not in _service_instances:
        from core import get_docker_manager, get_container_manager
        docker_manager = await get_docker_manager()
        container_manager = await get_container_manager()

        _service_instances['container_service'] = ContainerService(
            docker_manager, container_manager
        )

    return _service_instances['container_service']


async def get_build_service() -> BuildService:
    """获取构建服务实例"""
    if 'build_service' not in _service_instances:
        from core import get_build_manager
        build_manager = await get_build_manager()

        _service_instances['build_service'] = BuildService(build_manager)

    return _service_instances['build_service']


async def get_probe_service() -> ProbeService:
    """获取探针服务实例"""
    if 'probe_service' not in _service_instances:
        from core import get_probe_manager
        probe_manager = await get_probe_manager()

        _service_instances['probe_service'] = ProbeService(probe_manager)

    return _service_instances['probe_service']


async def get_terminal_service() -> TerminalService:
    """获取终端服务实例"""
    if 'terminal_service' not in _service_instances:
        from core import get_docker_manager, get_container_manager
        docker_manager = await get_docker_manager()
        container_manager = await get_container_manager()

        _service_instances['terminal_service'] = TerminalService(
            docker_manager, container_manager
        )

    return _service_instances['terminal_service']


async def initialize_all_services():
    """初始化所有服务"""
    services = [
        get_container_service(),
        get_build_service(),
        get_probe_service(),
        get_terminal_service()
    ]

    # 并发初始化所有服务
    import asyncio
    await asyncio.gather(*services, return_exceptions=True)


async def cleanup_all_services():
    """清理所有服务"""
    import asyncio
    cleanup_tasks = []

    for service_name, service in _service_instances.items():
        if hasattr(service, 'cleanup'):
            cleanup_tasks.append(service.cleanup())

    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    _service_instances.clear()


def get_service_health_status() -> dict:
    """获取所有服务的健康状态"""
    status = {}

    for service_name, service in _service_instances.items():
        if hasattr(service, 'is_healthy'):
            try:
                # 同步调用健康检查
                import asyncio
                if asyncio.iscoroutinefunction(service.is_healthy):
                    # 异步方法需要在事件循环中执行
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            status[service_name] = "unknown"  # 无法在运行中的循环内执行
                        else:
                            status[service_name] = "healthy" if loop.run_until_complete(
                                service.is_healthy()
                            ) else "unhealthy"
                    except RuntimeError:
                        status[service_name] = "unknown"
                else:
                    status[service_name] = "healthy" if service.is_healthy() else "unhealthy"
            except Exception:
                status[service_name] = "error"
        else:
            status[service_name] = "unknown"

    return status


def get_service_stats() -> dict:
    """获取所有服务的统计信息"""
    stats = {}

    for service_name, service in _service_instances.items():
        if hasattr(service, 'get_stats'):
            try:
                import asyncio
                if asyncio.iscoroutinefunction(service.get_stats):
                    # 异步方法需要特殊处理
                    try:
                        loop = asyncio.get_event_loop()
                        if not loop.is_running():
                            stats[service_name] = loop.run_until_complete(service.get_stats())
                        else:
                            stats[service_name] = {"status": "unavailable"}
                    except RuntimeError:
                        stats[service_name] = {"status": "unavailable"}
                else:
                    stats[service_name] = service.get_stats()
            except Exception as e:
                stats[service_name] = {"error": str(e)}
        else:
            stats[service_name] = {"status": "no_stats_available"}

    return stats