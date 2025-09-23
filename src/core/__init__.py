"""
******OSPP-2025-张金荣******

Eulermaker-docker-optimizer 的核心功能包

此软件包包含核心业务逻辑和管理类：
• Docker API 集成与容器管理
• 容器生命周期管理
• 构建任务执行与管理
• 探针与监控系统
"""

from .docker_manager import (
    DockerManager,
    DockerClient,
)

from .container_lifecycle import (
    ContainerLifecycleManager,
    ContainerState,
    LifecycleEvent,
)

from .build_manager import (
    BuildManager,
    BuildExecutor,
    BuildQueue,
)

from .probe_manager import (
    ProbeManager,
    ProbeExecutor,
    MonitoringService,
)

# 版本信息
__version__ = "1.0.0"

# 导出核心管理器类
__all__ = [
    # Docker管理
    "DockerManager",
    "DockerClient",

    # 容器生命周期管理
    "ContainerLifecycleManager",
    "ContainerState",
    "LifecycleEvent",

    # 构建管理
    "BuildManager",
    "BuildExecutor",
    "BuildQueue",

    # 探针管理
    "ProbeManager",
    "ProbeExecutor",
    "MonitoringService",
]


# 核心管理器工厂
class CoreManagerFactory:
    """核心管理器工厂类"""

    def __init__(self):
        self._docker_manager = None
        self._container_manager = None
        self._build_manager = None
        self._probe_manager = None

    async def get_docker_manager(self) -> DockerManager:
        """获取Docker管理器实例"""
        if self._docker_manager is None:
            self._docker_manager = DockerManager()
            await self._docker_manager.initialize()
        return self._docker_manager

    async def get_container_manager(self) -> ContainerLifecycleManager:
        """获取容器生命周期管理器实例"""
        if self._container_manager is None:
            docker_manager = await self.get_docker_manager()
            self._container_manager = ContainerLifecycleManager(docker_manager)
            await self._container_manager.initialize()
        return self._container_manager

    async def get_build_manager(self) -> BuildManager:
        """获取构建管理器实例"""
        if self._build_manager is None:
            docker_manager = await self.get_docker_manager()
            container_manager = await self.get_container_manager()
            self._build_manager = BuildManager(docker_manager, container_manager)
            await self._build_manager.initialize()
        return self._build_manager

    async def get_probe_manager(self) -> ProbeManager:
        """获取探针管理器实例"""
        if self._probe_manager is None:
            docker_manager = await self.get_docker_manager()
            container_manager = await self.get_container_manager()
            self._probe_manager = ProbeManager(docker_manager, container_manager)
            await self._probe_manager.initialize()
        return self._probe_manager

    async def cleanup(self):
        """清理所有管理器资源"""
        managers = [
            self._probe_manager,
            self._build_manager,
            self._container_manager,
            self._docker_manager
        ]

        for manager in managers:
            if manager and hasattr(manager, 'cleanup'):
                try:
                    await manager.cleanup()
                except Exception as e:
                    # 记录清理错误但继续清理其他管理器
                    print(f"Error cleaning up {manager.__class__.__name__}: {e}")

        # 重置实例
        self._docker_manager = None
        self._container_manager = None
        self._build_manager = None
        self._probe_manager = None


# 全局管理器工厂实例
_manager_factory = CoreManagerFactory()


# 便捷访问函数
async def get_docker_manager() -> DockerManager:
    """获取Docker管理器"""
    return await _manager_factory.get_docker_manager()


async def get_container_manager() -> ContainerLifecycleManager:
    """获取容器管理器"""
    return await _manager_factory.get_container_manager()


async def get_build_manager() -> BuildManager:
    """获取构建管理器"""
    return await _manager_factory.get_build_manager()


async def get_probe_manager() -> ProbeManager:
    """获取探针管理器"""
    return await _manager_factory.get_probe_manager()


async def cleanup_core():
    """清理核心模块资源"""
    await _manager_factory.cleanup()


# 核心服务状态检查
async def check_core_health() -> dict:
    """检查核心服务健康状态"""
    health_status = {
        "docker_manager": "unknown",
        "container_manager": "unknown",
        "build_manager": "unknown",
        "probe_manager": "unknown"
    }

    try:
        # 检查Docker管理器
        docker_manager = await get_docker_manager()
        if await docker_manager.is_healthy():
            health_status["docker_manager"] = "healthy"
        else:
            health_status["docker_manager"] = "unhealthy"
    except Exception:
        health_status["docker_manager"] = "error"

    try:
        # 检查容器管理器
        container_manager = await get_container_manager()
        if hasattr(container_manager, 'is_healthy') and await container_manager.is_healthy():
            health_status["container_manager"] = "healthy"
        else:
            health_status["container_manager"] = "unhealthy"
    except Exception:
        health_status["container_manager"] = "error"

    try:
        # 检查构建管理器
        build_manager = await get_build_manager()
        if hasattr(build_manager, 'is_healthy') and await build_manager.is_healthy():
            health_status["build_manager"] = "healthy"
        else:
            health_status["build_manager"] = "unhealthy"
    except Exception:
        health_status["build_manager"] = "error"

    try:
        # 检查探针管理器
        probe_manager = await get_probe_manager()
        if hasattr(probe_manager, 'is_healthy') and await probe_manager.is_healthy():
            health_status["probe_manager"] = "healthy"
        else:
            health_status["probe_manager"] = "unhealthy"
    except Exception:
        health_status["probe_manager"] = "error"

    # 计算整体健康状态
    healthy_count = sum(1 for status in health_status.values() if status == "healthy")
    total_count = len(health_status)

    if healthy_count == total_count:
        overall_status = "healthy"
    elif healthy_count > 0:
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return {
        "overall_status": overall_status,
        "services": health_status,
        "healthy_services": healthy_count,
        "total_services": total_count
    }


# 核心统计信息
async def get_core_stats() -> dict:
    """获取核心服务统计信息"""
    stats = {
        "containers": {"active": 0, "total": 0},
        "builds": {"active": 0, "completed": 0, "failed": 0},
        "probes": {"active": 0, "healthy": 0, "unhealthy": 0}
    }

    try:
        # 获取容器统计
        container_manager = await get_container_manager()
        if hasattr(container_manager, 'get_stats'):
            container_stats = await container_manager.get_stats()
            stats["containers"] = container_stats
    except Exception:
        pass

    try:
        # 获取构建统计
        build_manager = await get_build_manager()
        if hasattr(build_manager, 'get_stats'):
            build_stats = await build_manager.get_stats()
            stats["builds"] = build_stats
    except Exception:
        pass

    try:
        # 获取探针统计
        probe_manager = await get_probe_manager()
        if hasattr(probe_manager, 'get_stats'):
            probe_stats = await probe_manager.get_stats()
            stats["probes"] = probe_stats
    except Exception:
        pass

    return stats