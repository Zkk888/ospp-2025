"""
容器服务 - eulermaker-docker-optimizer的容器管理业务服务

******OSPP-2025-张金荣******

提供容器管理的高级业务逻辑封装，包括：
- 容器生命周期管理的业务操作
- 容器健康状态监控和管理
- 容器资源使用监控
- 批量容器操作
- 容器模板和预设管理
- 容器事件处理和通知
- 容器性能优化建议
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable, Set, Union, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json
from collections import defaultdict

from config.settings import get_docker_settings
from utils.logger import get_logger, LoggerMixin, log_performance, log_errors
from utils.exceptions import ContainerError, DockerError, ValidationError
from utils.helpers import (
    generate_uuid, format_timestamp, sanitize_name,
    format_size, format_duration
)
from models.container_model import (
    ContainerInfo, ContainerConfig, ContainerStatus, ContainerStats, ContainerEvent
)
from core.docker_manager import DockerManager
from core.container_lifecycle import ContainerLifecycleManager, LifecycleEvent


class ContainerOperation(Enum):
    """容器操作类型"""
    CREATE = "create"
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    PAUSE = "pause"
    UNPAUSE = "unpause"
    REMOVE = "remove"
    UPDATE = "update"
    INSPECT = "inspect"
    LOGS = "logs"
    EXEC = "exec"


class ContainerHealthStatus(Enum):
    """容器健康状态"""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    CRITICAL = "critical"


@dataclass
class ContainerTemplate:
    """容器模板"""
    template_id: str
    name: str
    description: str
    config: ContainerConfig
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    used_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "config": self.config.to_dict(),
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "used_count": self.used_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContainerTemplate':
        """从字典创建实例"""
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'config' in data:
            data['config'] = ContainerConfig.from_dict(data['config'])
        return cls(**data)


@dataclass
class ContainerOperationResult:
    """容器操作结果"""
    operation: ContainerOperation
    container_id: str
    container_name: str
    success: bool
    message: str
    error: Optional[str] = None
    execution_time: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "operation": self.operation.value,
            "container_id": self.container_id,
            "container_name": self.container_name,
            "success": self.success,
            "message": self.message,
            "error": self.error,
            "execution_time": self.execution_time,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ContainerHealthCheck:
    """容器健康检查结果"""
    container_id: str
    status: ContainerHealthStatus
    last_check: datetime
    response_time: Optional[float] = None
    error_message: Optional[str] = None
    consecutive_failures: int = 0

    def is_healthy(self) -> bool:
        """检查是否健康"""
        return self.status in [ContainerHealthStatus.HEALTHY, ContainerHealthStatus.STARTING]


class ContainerService(LoggerMixin):
    """容器服务 - 提供高级容器管理功能"""

    def __init__(self, docker_manager: DockerManager,
                 container_manager: ContainerLifecycleManager):
        super().__init__()
        self.docker_manager = docker_manager
        self.container_manager = container_manager
        self.settings = get_docker_settings()

        # 容器模板存储
        self._templates: Dict[str, ContainerTemplate] = {}

        # 健康检查状态
        self._health_checks: Dict[str, ContainerHealthCheck] = {}

        # 操作历史记录
        self._operation_history: List[ContainerOperationResult] = []

        # 事件处理器
        self._event_handlers: Dict[str, List[Callable]] = {}

        # 监控任务
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._health_check_task: Optional[asyncio.Task] = None

        # 统计信息
        self._stats = {
            "operations": defaultdict(int),
            "containers_created": 0,
            "containers_removed": 0,
            "total_uptime": timedelta(),
            "last_reset": datetime.now()
        }

        self._initialized = False

    async def initialize(self):
        """初始化容器服务"""
        try:
            # 注册生命周期事件监听器
            self.container_manager.add_event_handler("all", self._handle_lifecycle_event)

            # 启动健康检查任务
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            # 加载预设模板
            await self._load_default_templates()

            self._initialized = True
            self.logger.info("Container service initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize container service: {str(e)}")
            raise ContainerError(f"Container service initialization failed: {str(e)}", cause=e)

    async def cleanup(self):
        """清理容器服务"""
        self._initialized = False

        # 停止健康检查任务
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # 停止所有监控任务
        for task in list(self._monitoring_tasks.values()):
            task.cancel()

        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks.values(), return_exceptions=True)

        self._monitoring_tasks.clear()

        self.logger.info("Container service cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    async def is_healthy(self) -> bool:
        """检查服务健康状态"""
        if not self._initialized:
            return False

        try:
            return await self.docker_manager.is_healthy()
        except Exception:
            return False

    # ================== 容器基本操作 ==================

    @log_performance("create_container")
    async def create_container(self, config: ContainerConfig,
                               template_id: Optional[str] = None) -> ContainerOperationResult:
        """创建容器"""
        start_time = datetime.now()

        try:
            # 如果使用模板，先应用模板配置
            if template_id and template_id in self._templates:
                template = self._templates[template_id]
                config = self._merge_template_config(template.config, config)
                template.used_count += 1

            # 验证容器配置
            self._validate_container_config(config)

            # 创建并启动容器
            container_id = await self.container_manager.create_and_start_container(config)

            # 记录操作
            execution_time = (datetime.now() - start_time).total_seconds()
            result = ContainerOperationResult(
                operation=ContainerOperation.CREATE,
                container_id=container_id,
                container_name=config.name,
                success=True,
                message=f"容器 {config.name} 创建成功",
                execution_time=execution_time
            )

            # 更新统计
            self._stats["operations"]["create"] += 1
            self._stats["containers_created"] += 1

            # 记录操作历史
            self._operation_history.append(result)

            # 启动容器监控
            await self._start_container_monitoring(container_id)

            self.logger.info(f"Container created successfully: {config.name} ({container_id})")
            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            result = ContainerOperationResult(
                operation=ContainerOperation.CREATE,
                container_id="",
                container_name=config.name,
                success=False,
                message=f"容器创建失败: {str(e)}",
                error=str(e),
                execution_time=execution_time
            )

            self._operation_history.append(result)

            raise ContainerError(
                f"Failed to create container: {str(e)}",
                container_name=config.name,
                operation="create",
                cause=e
            )

    @log_performance("start_container")
    async def start_container(self, container_id: str) -> ContainerOperationResult:
        """启动容器"""
        return await self._execute_container_operation(
            ContainerOperation.START,
            container_id,
            lambda: self.container_manager.start_container(container_id)
        )

    @log_performance("stop_container")
    async def stop_container(self, container_id: str,
                             timeout: int = 10) -> ContainerOperationResult:
        """停止容器"""
        return await self._execute_container_operation(
            ContainerOperation.STOP,
            container_id,
            lambda: self.container_manager.stop_container(container_id, timeout)
        )

    @log_performance("restart_container")
    async def restart_container(self, container_id: str,
                                timeout: int = 10) -> ContainerOperationResult:
        """重启容器"""
        return await self._execute_container_operation(
            ContainerOperation.RESTART,
            container_id,
            lambda: self.container_manager.restart_container(container_id, timeout)
        )

    @log_performance("remove_container")
    async def remove_container(self, container_id: str,
                               force: bool = False) -> ContainerOperationResult:
        """删除容器"""
        result = await self._execute_container_operation(
            ContainerOperation.REMOVE,
            container_id,
            lambda: self.container_manager.remove_container(container_id, force)
        )

        # 停止监控
        await self._stop_container_monitoring(container_id)

        # 更新统计
        if result.success:
            self._stats["containers_removed"] += 1

        return result

    async def _execute_container_operation(self, operation: ContainerOperation,
                                           container_id: str,
                                           operation_func: Callable) -> ContainerOperationResult:
        """执行容器操作的通用方法"""
        start_time = datetime.now()

        try:
            # 获取容器信息
            container_info = await self.get_container_info(container_id)
            container_name = container_info.name if container_info else container_id

            # 执行操作
            await operation_func()

            execution_time = (datetime.now() - start_time).total_seconds()
            result = ContainerOperationResult(
                operation=operation,
                container_id=container_id,
                container_name=container_name,
                success=True,
                message=f"容器 {operation.value} 操作成功",
                execution_time=execution_time
            )

            # 更新统计
            self._stats["operations"][operation.value] += 1

            # 记录操作历史
            self._operation_history.append(result)

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            result = ContainerOperationResult(
                operation=operation,
                container_id=container_id,
                container_name=container_id,
                success=False,
                message=f"容器 {operation.value} 操作失败: {str(e)}",
                error=str(e),
                execution_time=execution_time
            )

            self._operation_history.append(result)
            raise

    # ================== 容器信息查询 ==================

    async def get_container_info(self, container_id: str) -> Optional[ContainerInfo]:
        """获取容器信息"""
        try:
            return await self.docker_manager.get_container_info(container_id)
        except Exception as e:
            self.logger.warning(f"Failed to get container info {container_id}: {str(e)}")
            return None

    async def list_containers(self, all: bool = True,
                              status_filter: Optional[ContainerStatus] = None,
                              name_filter: Optional[str] = None) -> List[ContainerInfo]:
        """列出容器"""
        try:
            containers = await self.docker_manager.list_containers(all=all)

            # 应用过滤器
            if status_filter:
                containers = [c for c in containers if c.status == status_filter]

            if name_filter:
                containers = [c for c in containers if name_filter.lower() in c.name.lower()]

            return containers

        except Exception as e:
            self.logger.error(f"Failed to list containers: {str(e)}")
            raise ContainerError(f"Failed to list containers: {str(e)}", cause=e)

    async def get_container_stats(self, container_id: str) -> Optional[ContainerStats]:
        """获取容器统计信息"""
        try:
            return await self.docker_manager.get_container_stats(container_id)
        except Exception as e:
            self.logger.warning(f"Failed to get container stats {container_id}: {str(e)}")
            return None

    async def get_container_logs(self, container_id: str,
                                 tail: Optional[int] = None,
                                 since: Optional[str] = None,
                                 follow: bool = False) -> Union[str, Any]:
        """获取容器日志"""
        try:
            return await self.docker_manager.get_container_logs(
                container_id, tail=tail, since=since, follow=follow
            )
        except Exception as e:
            self.logger.error(f"Failed to get container logs {container_id}: {str(e)}")
            raise ContainerError(
                f"Failed to get container logs: {str(e)}",
                container_id=container_id,
                operation="logs",
                cause=e
            )

    # ================== 批量操作 ==================

    async def batch_start_containers(self, container_ids: List[str]) -> List[ContainerOperationResult]:
        """批量启动容器"""
        return await self._batch_operation(
            container_ids,
            ContainerOperation.START,
            lambda cid: self.container_manager.start_container(cid)
        )

    async def batch_stop_containers(self, container_ids: List[str],
                                    timeout: int = 10) -> List[ContainerOperationResult]:
        """批量停止容器"""
        return await self._batch_operation(
            container_ids,
            ContainerOperation.STOP,
            lambda cid: self.container_manager.stop_container(cid, timeout)
        )

    async def batch_remove_containers(self, container_ids: List[str],
                                      force: bool = False) -> List[ContainerOperationResult]:
        """批量删除容器"""
        results = await self._batch_operation(
            container_ids,
            ContainerOperation.REMOVE,
            lambda cid: self.container_manager.remove_container(cid, force)
        )

        # 停止监控
        for container_id in container_ids:
            await self._stop_container_monitoring(container_id)

        # 更新统计
        successful_removals = sum(1 for r in results if r.success)
        self._stats["containers_removed"] += successful_removals

        return results

    async def _batch_operation(self, container_ids: List[str],
                               operation: ContainerOperation,
                               operation_func: Callable) -> List[ContainerOperationResult]:
        """批量操作的通用方法"""
        results = []

        # 并发执行操作
        async def execute_single_operation(container_id: str) -> ContainerOperationResult:
            try:
                return await self._execute_container_operation(
                    operation, container_id, lambda: operation_func(container_id)
                )
            except Exception as e:
                return ContainerOperationResult(
                    operation=operation,
                    container_id=container_id,
                    container_name=container_id,
                    success=False,
                    message=f"操作失败: {str(e)}",
                    error=str(e)
                )

        tasks = [execute_single_operation(cid) for cid in container_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(ContainerOperationResult(
                    operation=operation,
                    container_id=container_ids[i],
                    container_name=container_ids[i],
                    success=False,
                    message=f"操作异常: {str(result)}",
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        return processed_results

    # ================== 容器模板管理 ==================

    async def create_template(self, name: str, description: str,
                              config: ContainerConfig,
                              tags: List[str] = None) -> str:
        """创建容器模板"""
        template_id = generate_uuid()

        template = ContainerTemplate(
            template_id=template_id,
            name=name,
            description=description,
            config=config,
            tags=tags or []
        )

        self._templates[template_id] = template

        self.logger.info(f"Container template created: {name} ({template_id})")
        return template_id

    async def get_template(self, template_id: str) -> Optional[ContainerTemplate]:
        """获取容器模板"""
        return self._templates.get(template_id)

    async def list_templates(self, tag_filter: Optional[str] = None) -> List[ContainerTemplate]:
        """列出容器模板"""
        templates = list(self._templates.values())

        if tag_filter:
            templates = [t for t in templates if tag_filter in t.tags]

        return templates

    async def delete_template(self, template_id: str) -> bool:
        """删除容器模板"""
        if template_id in self._templates:
            del self._templates[template_id]
            self.logger.info(f"Container template deleted: {template_id}")
            return True
        return False

    def _merge_template_config(self, template_config: ContainerConfig,
                               user_config: ContainerConfig) -> ContainerConfig:
        """合并模板配置和用户配置"""
        # 这里可以实现更复杂的配置合并逻辑
        merged_config = ContainerConfig(
            name=user_config.name or template_config.name,
            image=user_config.image or template_config.image,
            command=user_config.command or template_config.command,
            entrypoint=user_config.entrypoint or template_config.entrypoint,
            working_dir=user_config.working_dir or template_config.working_dir,
            environment={**template_config.environment, **(user_config.environment or {})},
            labels={**template_config.labels, **(user_config.labels or {})},
            ports=user_config.ports or template_config.ports,
            volumes=user_config.volumes or template_config.volumes,
            network=user_config.network or template_config.network,
            resources=user_config.resources or template_config.resources
        )

        return merged_config

    # ================== 健康检查 ==================

    async def get_container_health(self, container_id: str) -> Optional[ContainerHealthCheck]:
        """获取容器健康状态"""
        return self._health_checks.get(container_id)

    async def get_all_health_statuses(self) -> Dict[str, ContainerHealthCheck]:
        """获取所有容器的健康状态"""
        return self._health_checks.copy()

    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(30)  # 每30秒检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check loop: {str(e)}")
                await asyncio.sleep(10)  # 出错后等待10秒

    async def _perform_health_checks(self):
        """执行健康检查"""
        containers = await self.list_containers(all=False)  # 只检查运行中的容器

        for container in containers:
            await self._check_container_health(container)

    async def _check_container_health(self, container: ContainerInfo):
        """检查单个容器的健康状态"""
        container_id = container.id

        try:
            # 获取容器当前状态
            current_info = await self.get_container_info(container_id)
            if not current_info:
                status = ContainerHealthStatus.UNKNOWN
            elif current_info.is_running():
                # 获取容器统计信息来判断健康状态
                stats = await self.get_container_stats(container_id)
                if stats:
                    # 基于资源使用情况判断健康状态
                    if stats.memory_usage_percent > 95:
                        status = ContainerHealthStatus.CRITICAL
                    elif stats.cpu_usage > 95:
                        status = ContainerHealthStatus.UNHEALTHY
                    else:
                        status = ContainerHealthStatus.HEALTHY
                else:
                    status = ContainerHealthStatus.UNKNOWN
            else:
                status = ContainerHealthStatus.UNHEALTHY

            # 更新健康检查记录
            health_check = self._health_checks.get(container_id)
            if health_check:
                # 更新现有记录
                if health_check.status != status:
                    if status in [ContainerHealthStatus.UNHEALTHY, ContainerHealthStatus.CRITICAL]:
                        health_check.consecutive_failures += 1
                    else:
                        health_check.consecutive_failures = 0

                health_check.status = status
                health_check.last_check = datetime.now()
            else:
                # 创建新记录
                health_check = ContainerHealthCheck(
                    container_id=container_id,
                    status=status,
                    last_check=datetime.now(),
                    consecutive_failures=0 if status != ContainerHealthStatus.UNHEALTHY else 1
                )
                self._health_checks[container_id] = health_check

            # 如果连续失败次数过多，可以触发告警
            if health_check.consecutive_failures >= 3:
                await self._handle_unhealthy_container(container, health_check)

        except Exception as e:
            self.logger.warning(f"Failed to check health for container {container_id}: {str(e)}")

            # 记录检查失败
            health_check = self._health_checks.get(container_id)
            if health_check:
                health_check.status = ContainerHealthStatus.UNKNOWN
                health_check.last_check = datetime.now()
                health_check.error_message = str(e)

    async def _handle_unhealthy_container(self, container: ContainerInfo,
                                          health_check: ContainerHealthCheck):
        """处理不健康的容器"""
        self.logger.warning(
            f"Container {container.name} ({container.id}) is unhealthy "
            f"(consecutive failures: {health_check.consecutive_failures})"
        )

        # 这里可以实现自动恢复策略，比如重启容器
        # 目前只记录日志

    # ================== 监控管理 ==================

    async def _start_container_monitoring(self, container_id: str):
        """启动容器监控"""
        if container_id in self._monitoring_tasks:
            return  # 已经在监控中

        task = asyncio.create_task(self._monitor_container(container_id))
        self._monitoring_tasks[container_id] = task

    async def _stop_container_monitoring(self, container_id: str):
        """停止容器监控"""
        if container_id in self._monitoring_tasks:
            task = self._monitoring_tasks[container_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._monitoring_tasks[container_id]

    async def _monitor_container(self, container_id: str):
        """监控单个容器"""
        self.logger.debug(f"Started monitoring container: {container_id}")

        try:
            while True:
                try:
                    # 获取容器统计信息
                    stats = await self.get_container_stats(container_id)
                    if stats:
                        # 这里可以实现更复杂的监控逻辑
                        # 比如记录历史数据、检测异常等
                        pass

                    await asyncio.sleep(10)  # 每10秒收集一次统计信息

                except Exception as e:
                    self.logger.warning(f"Error monitoring container {container_id}: {str(e)}")
                    await asyncio.sleep(30)  # 出错后等待30秒

        except asyncio.CancelledError:
            self.logger.debug(f"Stopped monitoring container: {container_id}")
        except Exception as e:
            self.logger.error(f"Monitoring error for container {container_id}: {str(e)}")

    # ================== 事件处理 ==================

    async def _handle_lifecycle_event(self, event: LifecycleEvent):
        """处理容器生命周期事件"""
        self.logger.debug(f"Handling lifecycle event: {event.event_type} for {event.container_id}")

        # 根据事件类型处理
        if event.event_type == "state_change":
            if event.new_state and event.new_state.value == "removed":
                # 容器被删除，清理相关数据
                self._health_checks.pop(event.container_id, None)

        # 调用已注册的事件处理器
        await self._emit_event("lifecycle", event)

    def add_event_handler(self, event_type: str, handler: Callable):
        """添加事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def _emit_event(self, event_type: str, event: Any):
        """发送事件"""
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                self.logger.error(f"Error in event handler: {str(e)}")

    # ================== 工具方法 ==================

    def _validate_container_config(self, config: ContainerConfig):
        """验证容器配置"""
        if not config.name:
            raise ValidationError("Container name is required", field="name")

        if not config.image:
            raise ValidationError("Container image is required", field="image")

        # 验证名称格式
        sanitized_name = sanitize_name(config.name)
        if sanitized_name != config.name:
            self.logger.warning(f"Container name sanitized: {config.name} -> {sanitized_name}")
            config.name = sanitized_name

    async def _load_default_templates(self):
        """加载默认容器模板"""
        # 构建环境模板
        build_template = ContainerTemplate(
            template_id="build-env",
            name="RPM构建环境",
            description="用于RPM包构建的标准环境",
            config=ContainerConfig(
                name="rpm-build-env",
                image="openeuler/openeuler:latest",
                working_dir="/workspace",
                environment={
                    "LANG": "en_US.UTF-8",
                    "LC_ALL": "en_US.UTF-8"
                }
            ),
            tags=["build", "rpm", "openeuler"]
        )

        self._templates["build-env"] = build_template

        # 开发环境模板
        dev_template = ContainerTemplate(
            template_id="dev-env",
            name="开发环境",
            description="通用开发环境模板",
            config=ContainerConfig(
                name="dev-env",
                image="openeuler/openeuler:latest",
                working_dir="/workspace",
                environment={
                    "EDITOR": "vim",
                    "TERM": "xterm-256color"
                }
            ),
            tags=["development", "general"]
        )

        self._templates["dev-env"] = dev_template

    # ================== 统计和报告 ==================

    async def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        # 获取当前容器状态统计
        containers = await self.list_containers(all=True)
        status_counts = defaultdict(int)
        for container in containers:
            status_counts[container.status.value] += 1

        # 获取健康状态统计
        health_counts = defaultdict(int)
        for health_check in self._health_checks.values():
            health_counts[health_check.status.value] += 1

        return {
            "containers": {
                "total": len(containers),
                "by_status": dict(status_counts)
            },
            "health": dict(health_counts),
            "operations": dict(self._stats["operations"]),
            "templates": len(self._templates),
            "monitoring_tasks": len(self._monitoring_tasks),
            "operation_history_size": len(self._operation_history),
            "containers_created": self._stats["containers_created"],
            "containers_removed": self._stats["containers_removed"],
            "last_reset": self._stats["last_reset"].isoformat()
        }

    async def get_operation_history(self, limit: int = 100) -> List[ContainerOperationResult]:
        """获取操作历史"""
        return self._operation_history[-limit:]

    async def get_container_summary(self) -> Dict[str, Any]:
        """获取容器总体摘要"""
        containers = await self.list_containers(all=True)

        total_memory_usage = 0
        total_cpu_usage = 0
        stats_count = 0

        for container in containers:
            if container.is_running():
                stats = await self.get_container_stats(container.id)
                if stats:
                    total_memory_usage += stats.memory_usage
                    total_cpu_usage += stats.cpu_usage
                    stats_count += 1

        avg_memory_usage = total_memory_usage / stats_count if stats_count > 0 else 0
        avg_cpu_usage = total_cpu_usage / stats_count if stats_count > 0 else 0

        return {
            "total_containers": len(containers),
            "running_containers": len([c for c in containers if c.is_running()]),
            "average_memory_usage": format_size(int(avg_memory_usage)),
            "average_cpu_usage": f"{avg_cpu_usage:.1f}%",
            "templates_available": len(self._templates),
            "monitoring_active": len(self._monitoring_tasks)
        }