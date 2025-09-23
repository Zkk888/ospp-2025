"""
容器生命周期管理器 - eulermaker-docker-optimizer的容器生命周期管理核心

******OSPP-2025-张金荣******

提供容器完整生命周期的管理，包括：
- 容器状态跟踪和转换
- 容器创建、启动、停止、重启流程管理
- 容器健康检查和监控
- 容器资源使用监控
- 容器事件处理和生命周期回调
- 容器清理和回收机制
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import weakref

from utils.logger import get_logger, LoggerMixin, log_performance, log_errors
from utils.exceptions import ContainerError, DockerError
from utils.helpers import generate_uuid, format_timestamp, retry_async
from models.container_model import (
    ContainerInfo, ContainerConfig, ContainerStatus, ContainerStats, ContainerEvent
)
from .docker_manager import DockerManager


class ContainerState(Enum):
    """容器状态枚举 - 扩展的状态管理"""
    PENDING = "pending"              # 等待创建
    CREATING = "creating"            # 创建中
    CREATED = "created"              # 已创建
    STARTING = "starting"            # 启动中
    RUNNING = "running"              # 运行中
    STOPPING = "stopping"           # 停止中
    STOPPED = "stopped"             # 已停止
    RESTARTING = "restarting"       # 重启中
    PAUSED = "paused"               # 已暂停
    REMOVING = "removing"           # 删除中
    REMOVED = "removed"             # 已删除
    ERROR = "error"                 # 错误状态

    def can_transition_to(self, target_state: 'ContainerState') -> bool:
        """检查是否可以转换到目标状态"""
        # 定义状态转换规则
        transitions = {
            self.PENDING: [self.CREATING, self.ERROR],
            self.CREATING: [self.CREATED, self.ERROR],
            self.CREATED: [self.STARTING, self.REMOVING, self.ERROR],
            self.STARTING: [self.RUNNING, self.ERROR],
            self.RUNNING: [self.STOPPING, self.PAUSED, self.RESTARTING, self.REMOVING, self.ERROR],
            self.STOPPING: [self.STOPPED, self.ERROR],
            self.STOPPED: [self.STARTING, self.REMOVING, self.ERROR],
            self.RESTARTING: [self.RUNNING, self.STOPPED, self.ERROR],
            self.PAUSED: [self.RUNNING, self.STOPPING, self.ERROR],
            self.REMOVING: [self.REMOVED, self.ERROR],
            self.REMOVED: [],  # 终态
            self.ERROR: [self.REMOVING, self.STARTING, self.STOPPING]  # 错误状态可以尝试恢复
        }

        return target_state in transitions.get(self, [])

    def is_active(self) -> bool:
        """检查是否为活跃状态"""
        return self in [self.RUNNING, self.STARTING, self.RESTARTING]

    def is_terminal(self) -> bool:
        """检查是否为终态"""
        return self in [self.REMOVED]


@dataclass
class LifecycleEvent:
    """生命周期事件"""
    container_id: str                   # 容器ID
    container_name: str                 # 容器名称
    event_type: str                     # 事件类型
    old_state: Optional[ContainerState] = None  # 旧状态
    new_state: Optional[ContainerState] = None  # 新状态
    timestamp: datetime = field(default_factory=datetime.now)
    message: str = ""                   # 事件消息
    details: Dict[str, Any] = field(default_factory=dict)  # 事件详情

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "container_id": self.container_id,
            "container_name": self.container_name,
            "event_type": self.event_type,
            "old_state": self.old_state.value if self.old_state else None,
            "new_state": self.new_state.value if self.new_state else None,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "details": self.details
        }


@dataclass
class ContainerMetadata:
    """容器元数据"""
    container_id: str                   # 容器ID
    config: ContainerConfig             # 容器配置
    state: ContainerState               # 当前状态
    info: Optional[ContainerInfo] = None  # 容器信息
    stats: Optional[ContainerStats] = None  # 统计信息
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_health_check: Optional[datetime] = None
    health_check_failures: int = 0
    restart_count: int = 0

    def update_state(self, new_state: ContainerState, message: str = ""):
        """更新状态"""
        if not self.state.can_transition_to(new_state):
            raise ContainerError(
                f"Invalid state transition: {self.state.value} -> {new_state.value}",
                container_id=self.container_id,
                details={"current_state": self.state.value, "target_state": new_state.value}
            )

        old_state = self.state
        self.state = new_state
        self.updated_at = datetime.now()

        return LifecycleEvent(
            container_id=self.container_id,
            container_name=self.config.name,
            event_type="state_change",
            old_state=old_state,
            new_state=new_state,
            message=message
        )


class ContainerLifecycleManager(LoggerMixin):
    """容器生命周期管理器"""

    def __init__(self, docker_manager: DockerManager):
        super().__init__()
        self.docker_manager = docker_manager
        self._containers: Dict[str, ContainerMetadata] = {}  # 容器元数据存储
        self._event_handlers: Dict[str, List[Callable]] = {}  # 事件处理器
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}  # 监控任务
        self._health_check_tasks: Dict[str, asyncio.Task] = {}  # 健康检查任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._initialized = False

        # 配置参数
        self.health_check_interval = 30  # 健康检查间隔（秒）
        self.stats_collection_interval = 10  # 统计收集间隔（秒）
        self.cleanup_interval = 300  # 清理间隔（秒）
        self.max_health_check_failures = 3  # 最大健康检查失败次数

    async def initialize(self):
        """初始化生命周期管理器"""
        try:
            # 注册Docker事件监听器
            self.docker_manager.add_event_listener("all", self._handle_docker_event)

            # 启动清理任务
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            # 同步现有容器状态
            await self._sync_existing_containers()

            self._initialized = True
            self.logger.info("Container lifecycle manager initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize container lifecycle manager: {str(e)}")
            raise ContainerError(f"Lifecycle manager initialization failed: {str(e)}", cause=e)

    async def cleanup(self):
        """清理资源"""
        self._initialized = False

        # 停止所有监控任务
        for task in list(self._monitoring_tasks.values()):
            task.cancel()

        for task in list(self._health_check_tasks.values()):
            task.cancel()

        if self._cleanup_task:
            self._cleanup_task.cancel()

        # 等待任务完成
        all_tasks = list(self._monitoring_tasks.values()) + \
                    list(self._health_check_tasks.values())

        if self._cleanup_task:
            all_tasks.append(self._cleanup_task)

        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)

        self.logger.info("Container lifecycle manager cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    # ================== 容器生命周期操作 ==================

    @log_performance("create_and_start_container")
    async def create_and_start_container(self, config: ContainerConfig) -> str:
        """创建并启动容器"""
        container_id = None

        try:
            # 创建容器元数据
            metadata = ContainerMetadata(
                container_id="",  # 临时为空
                config=config,
                state=ContainerState.PENDING
            )

            # 发送创建开始事件
            await self._emit_event(LifecycleEvent(
                container_id="",
                container_name=config.name,
                event_type="create_start",
                new_state=ContainerState.CREATING,
                message="开始创建容器"
            ))

            # 更新状态为创建中
            event = metadata.update_state(ContainerState.CREATING, "正在创建容器")

            # 调用Docker API创建容器
            container_id = await self.docker_manager.create_container(config)

            # 更新容器ID
            metadata.container_id = container_id

            # 获取容器信息
            metadata.info = await self.docker_manager.get_container_info(container_id)

            # 更新状态为已创建
            event = metadata.update_state(ContainerState.CREATED, "容器创建完成")

            # 存储容器元数据
            self._containers[container_id] = metadata

            # 发送创建完成事件
            await self._emit_event(event)

            # 启动容器
            await self._start_container_internal(container_id)

            self.logger.info(
                f"Container created and started successfully: {config.name}",
                extra={"container_id": container_id}
            )

            return container_id

        except Exception as e:
            # 如果创建失败，尝试清理
            if container_id:
                try:
                    await self.docker_manager.remove_container(container_id, force=True)
                except:
                    pass

                # 移除元数据
                self._containers.pop(container_id, None)

            # 发送创建失败事件
            await self._emit_event(LifecycleEvent(
                container_id=container_id or "",
                container_name=config.name,
                event_type="create_failed",
                new_state=ContainerState.ERROR,
                message=f"容器创建失败: {str(e)}"
            ))

            raise ContainerError(
                f"Failed to create and start container: {str(e)}",
                container_name=config.name,
                operation="create_and_start",
                cause=e
            )

    async def _start_container_internal(self, container_id: str):
        """内部启动容器方法"""
        metadata = self._containers.get(container_id)
        if not metadata:
            raise ContainerError(f"Container metadata not found: {container_id}")

        try:
            # 更新状态为启动中
            event = metadata.update_state(ContainerState.STARTING, "正在启动容器")
            await self._emit_event(event)

            # 调用Docker API启动容器
            await self.docker_manager.start_container(container_id)

            # 更新容器信息
            metadata.info = await self.docker_manager.get_container_info(container_id)

            # 更新状态为运行中
            event = metadata.update_state(ContainerState.RUNNING, "容器启动完成")
            await self._emit_event(event)

            # 启动监控任务
            await self._start_monitoring(container_id)

        except Exception as e:
            # 更新状态为错误
            event = metadata.update_state(ContainerState.ERROR, f"启动失败: {str(e)}")
            await self._emit_event(event)
            raise

    @log_performance("start_container")
    async def start_container(self, container_id: str) -> bool:
        """启动容器"""
        metadata = self._containers.get(container_id)
        if not metadata:
            raise ContainerError(f"Container not managed by lifecycle manager: {container_id}")

        if metadata.state in [ContainerState.RUNNING, ContainerState.STARTING]:
            self.logger.debug(f"Container already running or starting: {container_id}")
            return True

        try:
            await self._start_container_internal(container_id)
            return True

        except Exception as e:
            raise ContainerError(
                f"Failed to start container: {str(e)}",
                container_id=container_id,
                operation="start",
                cause=e
            )

    @log_performance("stop_container")
    async def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """停止容器"""
        metadata = self._containers.get(container_id)
        if not metadata:
            raise ContainerError(f"Container not managed by lifecycle manager: {container_id}")

        if metadata.state in [ContainerState.STOPPED, ContainerState.STOPPING]:
            self.logger.debug(f"Container already stopped or stopping: {container_id}")
            return True

        try:
            # 更新状态为停止中
            event = metadata.update_state(ContainerState.STOPPING, "正在停止容器")
            await self._emit_event(event)

            # 停止监控任务
            await self._stop_monitoring(container_id)

            # 调用Docker API停止容器
            await self.docker_manager.stop_container(container_id, timeout)

            # 更新容器信息
            metadata.info = await self.docker_manager.get_container_info(container_id)

            # 更新状态为已停止
            event = metadata.update_state(ContainerState.STOPPED, "容器停止完成")
            await self._emit_event(event)

            return True

        except Exception as e:
            # 更新状态为错误
            event = metadata.update_state(ContainerState.ERROR, f"停止失败: {str(e)}")
            await self._emit_event(event)

            raise ContainerError(
                f"Failed to stop container: {str(e)}",
                container_id=container_id,
                operation="stop",
                cause=e
            )

    @log_performance("restart_container")
    async def restart_container(self, container_id: str, timeout: int = 10) -> bool:
        """重启容器"""
        metadata = self._containers.get(container_id)
        if not metadata:
            raise ContainerError(f"Container not managed by lifecycle manager: {container_id}")

        try:
            # 更新状态为重启中
            event = metadata.update_state(ContainerState.RESTARTING, "正在重启容器")
            await self._emit_event(event)

            # 增加重启计数
            metadata.restart_count += 1

            # 停止监控任务
            await self._stop_monitoring(container_id)

            # 调用Docker API重启容器
            await self.docker_manager.restart_container(container_id, timeout)

            # 更新容器信息
            metadata.info = await self.docker_manager.get_container_info(container_id)

            # 更新状态为运行中
            event = metadata.update_state(ContainerState.RUNNING, "容器重启完成")
            await self._emit_event(event)

            # 重新启动监控任务
            await self._start_monitoring(container_id)

            return True

        except Exception as e:
            # 更新状态为错误
            event = metadata.update_state(ContainerState.ERROR, f"重启失败: {str(e)}")
            await self._emit_event(event)

            raise ContainerError(
                f"Failed to restart container: {str(e)}",
                container_id=container_id,
                operation="restart",
                cause=e
            )

    @log_performance("remove_container")
    async def remove_container(self, container_id: str, force: bool = False) -> bool:
        """删除容器"""
        metadata = self._containers.get(container_id)
        if not metadata:
            # 尝试直接从Docker删除
            try:
                await self.docker_manager.remove_container(container_id, force)
                return True
            except:
                raise ContainerError(f"Container not found: {container_id}")

        try:
            # 更新状态为删除中
            event = metadata.update_state(ContainerState.REMOVING, "正在删除容器")
            await self._emit_event(event)

            # 停止所有监控任务
            await self._stop_monitoring(container_id)
            await self._stop_health_check(container_id)

            # 调用Docker API删除容器
            await self.docker_manager.remove_container(container_id, force)

            # 更新状态为已删除
            event = metadata.update_state(ContainerState.REMOVED, "容器删除完成")
            await self._emit_event(event)

            # 移除元数据
            self._containers.pop(container_id, None)

            return True

        except Exception as e:
            # 更新状态为错误
            if container_id in self._containers:
                event = metadata.update_state(ContainerState.ERROR, f"删除失败: {str(e)}")
                await self._emit_event(event)

            raise ContainerError(
                f"Failed to remove container: {str(e)}",
                container_id=container_id,
                operation="remove",
                cause=e
            )

    # ================== 容器查询和状态管理 ==================

    def get_container_metadata(self, container_id: str) -> Optional[ContainerMetadata]:
        """获取容器元数据"""
        return self._containers.get(container_id)

    def get_all_containers(self) -> Dict[str, ContainerMetadata]:
        """获取所有容器元数据"""
        return self._containers.copy()

    def get_containers_by_state(self, state: ContainerState) -> List[ContainerMetadata]:
        """根据状态获取容器列表"""
        return [metadata for metadata in self._containers.values() if metadata.state == state]

    def get_running_containers(self) -> List[ContainerMetadata]:
        """获取运行中的容器"""
        return self.get_containers_by_state(ContainerState.RUNNING)

    def get_container_count_by_state(self) -> Dict[str, int]:
        """获取各状态容器数量统计"""
        counts = {}
        for state in ContainerState:
            counts[state.value] = len(self.get_containers_by_state(state))
        return counts

    async def get_stats(self) -> Dict[str, Any]:
        """获取生命周期管理器统计信息"""
        total_containers = len(self._containers)
        active_containers = len([m for m in self._containers.values() if m.state.is_active()])

        state_counts = self.get_container_count_by_state()

        return {
            "total": total_containers,
            "active": active_containers,
            "by_state": state_counts,
            "monitoring_tasks": len(self._monitoring_tasks),
            "health_check_tasks": len(self._health_check_tasks)
        }

    async def is_healthy(self) -> bool:
        """检查生命周期管理器健康状态"""
        try:
            # 检查Docker管理器状态
            if not await self.docker_manager.is_healthy():
                return False

            # 检查是否有过多的错误状态容器
            error_containers = len(self.get_containers_by_state(ContainerState.ERROR))
            total_containers = len(self._containers)

            if total_containers > 0 and error_containers / total_containers > 0.5:
                return False

            return True

        except Exception:
            return False

    # ================== 监控和健康检查 ==================

    async def _start_monitoring(self, container_id: str):
        """启动容器监控"""
        # 启动统计收集任务
        if container_id not in self._monitoring_tasks:
            task = asyncio.create_task(self._monitor_container_stats(container_id))
            self._monitoring_tasks[container_id] = task

        # 启动健康检查任务
        if container_id not in self._health_check_tasks:
            task = asyncio.create_task(self._health_check_loop(container_id))
            self._health_check_tasks[container_id] = task

    async def _stop_monitoring(self, container_id: str):
        """停止容器监控"""
        # 停止统计收集任务
        if container_id in self._monitoring_tasks:
            task = self._monitoring_tasks.pop(container_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 停止健康检查任务
        await self._stop_health_check(container_id)

    async def _stop_health_check(self, container_id: str):
        """停止健康检查"""
        if container_id in self._health_check_tasks:
            task = self._health_check_tasks.pop(container_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _monitor_container_stats(self, container_id: str):
        """监控容器统计信息"""
        while True:
            try:
                metadata = self._containers.get(container_id)
                if not metadata or metadata.state != ContainerState.RUNNING:
                    break

                # 获取容器统计信息
                stats = await self.docker_manager.get_container_stats(container_id)
                metadata.stats = stats
                metadata.updated_at = datetime.now()

                # 发送统计更新事件
                await self._emit_event(LifecycleEvent(
                    container_id=container_id,
                    container_name=metadata.config.name,
                    event_type="stats_updated",
                    message="统计信息已更新",
                    details={"stats": stats.to_dict()}
                ))

                await asyncio.sleep(self.stats_collection_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.warning(
                    f"Error collecting stats for container {container_id}: {str(e)}"
                )
                await asyncio.sleep(self.stats_collection_interval)

    async def _health_check_loop(self, container_id: str):
        """健康检查循环"""
        while True:
            try:
                metadata = self._containers.get(container_id)
                if not metadata or not metadata.state.is_active():
                    break

                # 执行健康检查
                is_healthy = await self._perform_health_check(container_id)

                metadata.last_health_check = datetime.now()

                if is_healthy:
                    metadata.health_check_failures = 0

                    await self._emit_event(LifecycleEvent(
                        container_id=container_id,
                        container_name=metadata.config.name,
                        event_type="health_check_passed",
                        message="健康检查通过"
                    ))
                else:
                    metadata.health_check_failures += 1

                    await self._emit_event(LifecycleEvent(
                        container_id=container_id,
                        container_name=metadata.config.name,
                        event_type="health_check_failed",
                        message=f"健康检查失败 (失败次数: {metadata.health_check_failures})"
                    ))

                    # 如果连续失败次数过多，标记为不健康
                    if metadata.health_check_failures >= self.max_health_check_failures:
                        await self._handle_unhealthy_container(container_id)

                await asyncio.sleep(self.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.warning(
                    f"Error in health check for container {container_id}: {str(e)}"
                )
                await asyncio.sleep(self.health_check_interval)

    async def _perform_health_check(self, container_id: str) -> bool:
        """执行健康检查"""
        try:
            # 检查容器是否还在运行
            info = await self.docker_manager.get_container_info(container_id)

            # 更新容器信息
            metadata = self._containers.get(container_id)
            if metadata:
                metadata.info = info

            # 基本健康检查：容器是否在运行
            if not info.is_running():
                return False

            # 可以在这里添加更多自定义健康检查逻辑
            # 例如：检查特定端口是否响应，检查进程是否存在等

            return True

        except Exception as e:
            self.logger.debug(f"Health check failed for container {container_id}: {str(e)}")
            return False

    async def _handle_unhealthy_container(self, container_id: str):
        """处理不健康的容器"""
        metadata = self._containers.get(container_id)
        if not metadata:
            return

        self.logger.warning(
            f"Container {container_id} is unhealthy after {metadata.health_check_failures} failures"
        )

        await self._emit_event(LifecycleEvent(
            container_id=container_id,
            container_name=metadata.config.name,
            event_type="container_unhealthy",
            message=f"容器不健康，连续失败{metadata.health_check_failures}次",
            details={"failure_count": metadata.health_check_failures}
        ))

        # 可以在这里实现自动恢复策略，例如重启容器
        # 这里暂时只记录事件，具体策略可以通过事件处理器实现

    # ================== 事件处理 ==================

    def add_event_handler(self, event_type: str, handler: Callable):
        """添加事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []

        self._event_handlers[event_type].append(handler)
        self.logger.debug(f"Added event handler for {event_type}")

    def remove_event_handler(self, event_type: str, handler: Callable):
        """移除事件处理器"""
        if event_type in self._event_handlers:
            try:
                self._event_handlers[event_type].remove(handler)
                self.logger.debug(f"Removed event handler for {event_type}")
            except ValueError:
                pass

    async def _emit_event(self, event: LifecycleEvent):
        """发送事件"""
        self.logger.debug(f"Emitting event: {event.event_type} for {event.container_name}")

        # 调用通用事件处理器
        await self._call_event_handlers("all", event)

        # 调用特定事件处理器
        await self._call_event_handlers(event.event_type, event)

    async def _call_event_handlers(self, event_type: str, event: LifecycleEvent):
        """调用事件处理器"""
        handlers = self._event_handlers.get(event_type, [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                self.logger.error(f"Error in event handler for {event_type}: {str(e)}")

    async def _handle_docker_event(self, docker_event: ContainerEvent):
        """处理Docker事件"""
        container_id = docker_event.container_id

        # 检查是否是我们管理的容器
        metadata = self._containers.get(container_id)
        if not metadata:
            return

        # 根据Docker事件更新容器状态
        try:
            if docker_event.action == "start":
                if metadata.state != ContainerState.RUNNING:
                    event = metadata.update_state(ContainerState.RUNNING, "Docker事件：容器已启动")
                    await self._emit_event(event)
                    await self._start_monitoring(container_id)

            elif docker_event.action == "stop":
                if metadata.state != ContainerState.STOPPED:
                    event = metadata.update_state(ContainerState.STOPPED, "Docker事件：容器已停止")
                    await self._emit_event(event)
                    await self._stop_monitoring(container_id)

            elif docker_event.action == "die":
                if metadata.state != ContainerState.STOPPED:
                    event = metadata.update_state(ContainerState.STOPPED, "Docker事件：容器已退出")
                    await self._emit_event(event)
                    await self._stop_monitoring(container_id)

            elif docker_event.action == "destroy":
                if metadata.state != ContainerState.REMOVED:
                    event = metadata.update_state(ContainerState.REMOVED, "Docker事件：容器已删除")
                    await self._emit_event(event)
                    await self._stop_monitoring(container_id)
                    # 移除元数据
                    self._containers.pop(container_id, None)

        except Exception as e:
            self.logger.warning(f"Error handling Docker event {docker_event.action}: {str(e)}")

    # ================== 同步和清理 ==================

    async def _sync_existing_containers(self):
        """同步现有容器状态"""
        try:
            # 获取所有现有容器
            containers = await self.docker_manager.list_containers(all=True)

            for container_info in containers:
                try:
                    # 检查是否已经在管理中
                    if container_info.id in self._containers:
                        continue

                    # 尝试从容器标签中恢复配置信息
                    # 这里简化处理，实际项目中可能需要更复杂的配置恢复逻辑
                    config = ContainerConfig(
                        name=container_info.name,
                        image=container_info.image
                    )

                    # 映射Docker状态到内部状态
                    if container_info.status == ContainerStatus.RUNNING:
                        state = ContainerState.RUNNING
                    elif container_info.status == ContainerStatus.PAUSED:
                        state = ContainerState.PAUSED
                    elif container_info.status in [ContainerStatus.EXITED, ContainerStatus.DEAD]:
                        state = ContainerState.STOPPED
                    else:
                        state = ContainerState.CREATED

                    # 创建元数据
                    metadata = ContainerMetadata(
                        container_id=container_info.id,
                        config=config,
                        state=state,
                        info=container_info,
                        created_at=container_info.created_at
                    )

                    self._containers[container_info.id] = metadata

                    # 如果容器正在运行，启动监控
                    if state == ContainerState.RUNNING:
                        await self._start_monitoring(container_info.id)

                except Exception as e:
                    self.logger.warning(f"Failed to sync container {container_info.id}: {str(e)}")
                    continue

            self.logger.info(f"Synced {len(self._containers)} existing containers")

        except Exception as e:
            self.logger.error(f"Failed to sync existing containers: {str(e)}")

    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_stale_metadata()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {str(e)}")

    async def _cleanup_stale_metadata(self):
        """清理过期的元数据"""
        stale_containers = []
        current_time = datetime.now()

        for container_id, metadata in self._containers.items():
            # 检查已删除的容器元数据
            if metadata.state == ContainerState.REMOVED:
                # 删除状态超过一定时间的容器元数据可以清理
                if current_time - metadata.updated_at > timedelta(minutes=30):
                    stale_containers.append(container_id)

            # 检查长时间没有更新的容器
            elif current_time - metadata.updated_at > timedelta(hours=1):
                try:
                    # 尝试获取容器信息来验证是否还存在
                    info = await self.docker_manager.get_container_info(container_id)
                    metadata.info = info
                    metadata.updated_at = current_time

                except ContainerError as e:
                    if "not found" in str(e).lower():
                        # 容器不存在，标记为已删除
                        stale_containers.append(container_id)

        # 清理过期容器
        for container_id in stale_containers:
            self.logger.info(f"Cleaning up stale container metadata: {container_id}")
            self._containers.pop(container_id, None)
            await self._stop_monitoring(container_id)

    # ================== 批量操作 ==================

    async def stop_all_containers(self, timeout: int = 10) -> Dict[str, bool]:
        """停止所有运行中的容器"""
        results = {}
        running_containers = self.get_running_containers()

        tasks = []
        for metadata in running_containers:
            task = asyncio.create_task(self._safe_stop_container(metadata.container_id, timeout))
            tasks.append((metadata.container_id, task))

        for container_id, task in tasks:
            try:
                result = await task
                results[container_id] = result
            except Exception as e:
                self.logger.error(f"Failed to stop container {container_id}: {str(e)}")
                results[container_id] = False

        return results

    async def _safe_stop_container(self, container_id: str, timeout: int) -> bool:
        """安全停止容器"""
        try:
            await self.stop_container(container_id, timeout)
            return True
        except Exception:
            return False

    async def remove_all_stopped_containers(self) -> Dict[str, bool]:
        """删除所有已停止的容器"""
        results = {}
        stopped_containers = self.get_containers_by_state(ContainerState.STOPPED)

        for metadata in stopped_containers:
            try:
                await self.remove_container(metadata.container_id)
                results[metadata.container_id] = True
            except Exception as e:
                self.logger.error(f"Failed to remove container {metadata.container_id}: {str(e)}")
                results[metadata.container_id] = False

        return results


# 便捷函数
async def create_container_manager(docker_manager: DockerManager) -> ContainerLifecycleManager:
    """创建并初始化容器生命周期管理器"""
    manager = ContainerLifecycleManager(docker_manager)
    await manager.initialize()
    return manager