# 21. src/services/build_service.py
"""
构建服务 - eulermaker-docker-optimizer的RPM构建业务服务

******OSPP-2025-张金荣******

提供RPM构建的高级业务逻辑封装，包括：
- RPM包构建任务管理
- 构建环境管理和优化
- 构建队列和调度管理
- 构建结果管理和存储
- 构建模板和预设管理
- 构建依赖分析和解决
- 构建性能监控和优化
- 构建失败重试和恢复
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable, Set, Union, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json
import os
import shutil
import tempfile
from pathlib import Path
from collections import defaultdict, deque
import hashlib

from config.settings import get_docker_settings
from utils.logger import get_logger, LoggerMixin, log_performance, log_errors
from utils.exceptions import BuildError, ContainerError, ValidationError, DockerError
from utils.helpers import (
    generate_uuid, format_timestamp, sanitize_name,
    format_size, format_duration, ensure_directory
)
from models.build_model import (
    BuildTask, BuildConfig, BuildStatus, BuildResult, BuildLog,
    BuildEnvironment, BuildDependency, BuildArtifact, BuildMetrics
)
from core.build_manager import BuildManager, BuildEvent


class BuildOperationType(Enum):
    """构建操作类型"""
    PREPARE = "prepare"
    BUILD = "build"
    TEST = "test"
    PACKAGE = "package"
    CLEANUP = "cleanup"
    RETRY = "retry"
    CANCEL = "cancel"


class BuildPriority(Enum):
    """构建优先级"""
    LOW = 1
    NORMAL = 3
    HIGH = 5
    URGENT = 7
    CRITICAL = 9


class BuildQueueStatus(Enum):
    """构建队列状态"""
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class BuildTemplate:
    """构建模板"""
    template_id: str
    name: str
    description: str
    config: BuildConfig
    environment: BuildEnvironment
    dependencies: List[BuildDependency] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    used_count: int = 0
    success_rate: float = 0.0
    average_build_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "config": self.config.to_dict(),
            "environment": self.environment.to_dict(),
            "dependencies": [dep.to_dict() for dep in self.dependencies],
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "used_count": self.used_count,
            "success_rate": self.success_rate,
            "average_build_time": self.average_build_time
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BuildTemplate':
        """从字典创建实例"""
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'config' in data:
            data['config'] = BuildConfig.from_dict(data['config'])
        if 'environment' in data:
            data['environment'] = BuildEnvironment.from_dict(data['environment'])
        if 'dependencies' in data:
            data['dependencies'] = [BuildDependency.from_dict(dep) for dep in data['dependencies']]

        return cls(**data)


@dataclass
class BuildQueueItem:
    """构建队列项"""
    queue_id: str
    task: BuildTask
    priority: BuildPriority = BuildPriority.NORMAL
    submitted_at: datetime = field(default_factory=datetime.now)
    estimated_duration: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3

    def calculate_score(self) -> float:
        """计算队列优先级分数"""
        # 基础优先级分数
        base_score = self.priority.value * 100

        # 等待时间加分（等待越久分数越高）
        wait_time = (datetime.now() - self.submitted_at).total_seconds()
        time_score = wait_time / 3600  # 每小时加1分

        # 重试次数减分
        retry_penalty = self.retry_count * 10

        return base_score + time_score - retry_penalty

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "queue_id": self.queue_id,
            "task": self.task.to_dict(),
            "priority": self.priority.value,
            "submitted_at": self.submitted_at.isoformat(),
            "estimated_duration": self.estimated_duration,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }


@dataclass
class BuildStatistics:
    """构建统计信息"""
    total_builds: int = 0
    successful_builds: int = 0
    failed_builds: int = 0
    cancelled_builds: int = 0
    total_build_time: float = 0.0
    average_build_time: float = 0.0
    success_rate: float = 0.0
    builds_by_status: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    builds_by_priority: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_reset: datetime = field(default_factory=datetime.now)

    def update(self, task: BuildTask):
        """更新统计信息"""
        self.total_builds += 1

        if task.status == BuildStatus.COMPLETED:
            self.successful_builds += 1
        elif task.status == BuildStatus.FAILED:
            self.failed_builds += 1
        elif task.status == BuildStatus.CANCELLED:
            self.cancelled_builds += 1

        self.builds_by_status[task.status.value] += 1

        if task.build_time:
            self.total_build_time += task.build_time
            self.average_build_time = self.total_build_time / self.total_builds

        if self.total_builds > 0:
            self.success_rate = (self.successful_builds / self.total_builds) * 100

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "total_builds": self.total_builds,
            "successful_builds": self.successful_builds,
            "failed_builds": self.failed_builds,
            "cancelled_builds": self.cancelled_builds,
            "total_build_time": self.total_build_time,
            "average_build_time": self.average_build_time,
            "success_rate": self.success_rate,
            "builds_by_status": dict(self.builds_by_status),
            "builds_by_priority": dict(self.builds_by_priority),
            "last_reset": self.last_reset.isoformat()
        }


class BuildScheduler:
    """构建调度器 - 管理构建任务的队列和调度"""

    def __init__(self, build_manager: BuildManager, max_concurrent_builds: int = 3):
        self.build_manager = build_manager
        self.max_concurrent_builds = max_concurrent_builds
        self.logger = get_logger(__name__)

        # 构建队列
        self._build_queue: deque[BuildQueueItem] = deque()
        self._running_builds: Dict[str, BuildTask] = {}

        # 调度器状态
        self._status = BuildQueueStatus.IDLE
        self._scheduler_task: Optional[asyncio.Task] = None

        # 事件处理器
        self._event_handlers: List[Callable] = []

        self._is_running = False

    async def start(self):
        """启动构建调度器"""
        if self._is_running:
            return

        self._is_running = True
        self._status = BuildQueueStatus.IDLE
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

        self.logger.info("Build scheduler started")

    async def stop(self):
        """停止构建调度器"""
        self._is_running = False
        self._status = BuildQueueStatus.STOPPING

        # 停止调度任务
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # 取消所有排队的构建
        for queue_item in self._build_queue:
            queue_item.task.status = BuildStatus.CANCELLED
            queue_item.task.finished_at = datetime.now()

        self._build_queue.clear()

        # 等待运行中的构建完成
        if self._running_builds:
            self.logger.info(f"Waiting for {len(self._running_builds)} running builds to complete")

            # 给运行中的构建一些时间完成
            timeout = 30  # 30秒超时
            start_time = time.time()

            while self._running_builds and (time.time() - start_time) < timeout:
                await asyncio.sleep(1)

            # 强制取消剩余的构建
            for task in self._running_builds.values():
                try:
                    await self.build_manager.cancel_build(task.task_id)
                except Exception as e:
                    self.logger.warning(f"Failed to cancel build {task.task_id}: {str(e)}")

        self._running_builds.clear()
        self._status = BuildQueueStatus.IDLE

        self.logger.info("Build scheduler stopped")

    def add_to_queue(self, task: BuildTask, priority: BuildPriority = BuildPriority.NORMAL) -> str:
        """添加构建任务到队列"""
        queue_id = generate_uuid()

        queue_item = BuildQueueItem(
            queue_id=queue_id,
            task=task,
            priority=priority
        )

        # 按优先级插入队列
        inserted = False
        for i, existing_item in enumerate(self._build_queue):
            if queue_item.calculate_score() > existing_item.calculate_score():
                self._build_queue.insert(i, queue_item)
                inserted = True
                break

        if not inserted:
            self._build_queue.append(queue_item)

        # 更新队列状态
        if self._status == BuildQueueStatus.IDLE and len(self._build_queue) > 0:
            self._status = BuildQueueStatus.BUSY

        self.logger.info(f"Added build task to queue: {task.task_id} (priority: {priority.name})")
        return queue_id

    def remove_from_queue(self, queue_id: str) -> bool:
        """从队列中移除构建任务"""
        for i, queue_item in enumerate(self._build_queue):
            if queue_item.queue_id == queue_id:
                removed_item = self._build_queue[i]
                del self._build_queue[i]

                # 取消任务
                removed_item.task.status = BuildStatus.CANCELLED
                removed_item.task.finished_at = datetime.now()

                self.logger.info(f"Removed build task from queue: {removed_item.task.task_id}")
                return True

        return False

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            "status": self._status.value,
            "queue_length": len(self._build_queue),
            "running_builds": len(self._running_builds),
            "max_concurrent_builds": self.max_concurrent_builds,
            "queued_tasks": [item.to_dict() for item in self._build_queue],
            "running_tasks": [task.to_dict() for task in self._running_builds.values()]
        }

    def get_queue_position(self, task_id: str) -> Optional[int]:
        """获取任务在队列中的位置"""
        for i, queue_item in enumerate(self._build_queue):
            if queue_item.task.task_id == task_id:
                return i + 1
        return None

    def add_event_handler(self, handler: Callable):
        """添加事件处理器"""
        self._event_handlers.append(handler)

    async def _scheduler_loop(self):
        """调度器主循环"""
        while self._is_running:
            try:
                # 检查是否可以启动新的构建
                if (len(self._running_builds) < self.max_concurrent_builds and
                        len(self._build_queue) > 0):

                    # 获取下一个要执行的任务
                    queue_item = self._build_queue.popleft()

                    # 启动构建任务
                    await self._start_build(queue_item)

                # 检查已完成的构建
                await self._check_completed_builds()

                # 更新状态
                if len(self._build_queue) == 0 and len(self._running_builds) == 0:
                    self._status = BuildQueueStatus.IDLE
                else:
                    self._status = BuildQueueStatus.BUSY

                await asyncio.sleep(1)  # 每秒检查一次

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {str(e)}")
                self._status = BuildQueueStatus.ERROR
                await asyncio.sleep(5)

    async def _start_build(self, queue_item: BuildQueueItem):
        """启动构建任务"""
        task = queue_item.task

        try:
            self.logger.info(f"Starting build task: {task.task_id}")

            # 更新任务状态
            task.status = BuildStatus.RUNNING
            task.started_at = datetime.now()

            # 添加到运行中的构建
            self._running_builds[task.task_id] = task

            # 启动构建
            await self.build_manager.start_build(task)

            # 触发事件
            await self._emit_event("build_started", {
                "task_id": task.task_id,
                "queue_id": queue_item.queue_id,
                "priority": queue_item.priority.name
            })

        except Exception as e:
            self.logger.error(f"Failed to start build {task.task_id}: {str(e)}")

            # 更新任务状态
            task.status = BuildStatus.FAILED
            task.finished_at = datetime.now()
            task.error_message = str(e)

            # 从运行中的构建列表移除
            self._running_builds.pop(task.task_id, None)

            # 检查是否需要重试
            if queue_item.retry_count < queue_item.max_retries:
                queue_item.retry_count += 1
                queue_item.task.status = BuildStatus.PENDING
                queue_item.submitted_at = datetime.now()

                self._build_queue.appendleft(queue_item)  # 重新加入队列头部
                self.logger.info(f"Retrying build {task.task_id} ({queue_item.retry_count}/{queue_item.max_retries})")
            else:
                await self._emit_event("build_failed", {
                    "task_id": task.task_id,
                    "error": str(e),
                    "retry_count": queue_item.retry_count
                })

    async def _check_completed_builds(self):
        """检查已完成的构建"""
        completed_tasks = []

        for task_id, task in self._running_builds.items():
            # 检查构建状态
            try:
                updated_task = await self.build_manager.get_build_task(task_id)
                if updated_task and updated_task.status in [
                    BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED
                ]:
                    completed_tasks.append(task_id)

                    # 更新任务信息
                    task.status = updated_task.status
                    task.finished_at = updated_task.finished_at
                    task.result = updated_task.result
                    task.error_message = updated_task.error_message

            except Exception as e:
                self.logger.error(f"Error checking build status {task_id}: {str(e)}")

        # 移除已完成的构建
        for task_id in completed_tasks:
            task = self._running_builds.pop(task_id)

            await self._emit_event("build_completed", {
                "task_id": task_id,
                "status": task.status.value,
                "build_time": task.build_time
            })

            self.logger.info(f"Build completed: {task_id} ({task.status.value})")

    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """发送事件"""
        for handler in self._event_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_type, data)
                else:
                    handler(event_type, data)
            except Exception as e:
                self.logger.error(f"Error in event handler: {str(e)}")


class BuildService(LoggerMixin):
    """构建服务 - 提供高级RPM构建管理功能"""

    def __init__(self, build_manager: BuildManager):
        super().__init__()
        self.build_manager = build_manager
        self.settings = get_docker_settings()

        # 构建调度器
        max_concurrent = self.settings.get('build', {}).get('max_concurrent_builds', 3)
        self.scheduler = BuildScheduler(build_manager, max_concurrent)

        # 构建模板
        self._templates: Dict[str, BuildTemplate] = {}

        # 构建缓存
        self._build_cache: Dict[str, Any] = {}

        # 构建工作目录
        self._work_dir = Path(tempfile.mkdtemp(prefix="build_service_"))

        # 统计信息
        self._statistics = BuildStatistics()

        # 事件处理器
        self._event_handlers: Dict[str, List[Callable]] = {}

        # 构建历史
        self._build_history: deque[BuildTask] = deque(maxlen=1000)

        # 依赖缓存
        self._dependency_cache: Dict[str, List[BuildDependency]] = {}

        self._initialized = False

    async def initialize(self):
        """初始化构建服务"""
        try:
            # 确保工作目录存在
            ensure_directory(self._work_dir)

            # 注册构建管理器事件监听器
            self.build_manager.add_event_handler("all", self._handle_build_event)

            # 启动构建调度器
            await self.scheduler.start()

            # 注册调度器事件处理器
            self.scheduler.add_event_handler(self._handle_scheduler_event)

            # 加载默认构建模板
            await self._load_default_templates()

            self._initialized = True
            self.logger.info("Build service initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize build service: {str(e)}")
            raise BuildError(f"Build service initialization failed: {str(e)}", cause=e)

    async def cleanup(self):
        """清理构建服务"""
        self._initialized = False

        # 停止构建调度器
        await self.scheduler.stop()

        # 清理工作目录
        try:
            if self._work_dir.exists():
                shutil.rmtree(self._work_dir)
        except Exception as e:
            self.logger.warning(f"Failed to cleanup work directory: {str(e)}")

        self.logger.info("Build service cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    async def is_healthy(self) -> bool:
        """检查服务健康状态"""
        if not self._initialized:
            return False

        try:
            return await self.build_manager.is_healthy()
        except Exception:
            return False

    # ================== 构建任务管理 ==================

    @log_performance("submit_build")
    async def submit_build(self, config: BuildConfig,
                           priority: BuildPriority = BuildPriority.NORMAL,
                           template_id: Optional[str] = None) -> str:
        """提交构建任务"""
        try:
            # 如果指定了模板，应用模板配置
            if template_id:
                template = await self.get_template(template_id)
                if template:
                    config = self._merge_template_config(template, config)
                    template.used_count += 1

            # 验证构建配置
            self._validate_build_config(config)

            # 创建构建任务
            task_id = generate_uuid()
            task = BuildTask(
                task_id=task_id,
                config=config,
                status=BuildStatus.PENDING,
                created_at=datetime.now(),
                submitted_by="build_service"
            )

            # 添加到调度器队列
            queue_id = self.scheduler.add_to_queue(task, priority)
            task.queue_id = queue_id

            # 添加到构建历史
            self._build_history.append(task)

            self.logger.info(f"Build task submitted: {task_id} (priority: {priority.name})")
            return task_id

        except Exception as e:
            raise BuildError(
                f"Failed to submit build task: {str(e)}",
                config=config.to_dict() if config else None,
                cause=e
            )

    @log_performance("cancel_build")
    async def cancel_build(self, task_id: str) -> bool:
        """取消构建任务"""
        try:
            # 尝试从队列中移除
            task = await self.get_build_task(task_id)
            if not task:
                return False

            if task.queue_id:
                removed = self.scheduler.remove_from_queue(task.queue_id)
                if removed:
                    self.logger.info(f"Build task cancelled from queue: {task_id}")
                    return True

            # 如果任务正在运行，取消执行
            if task.status == BuildStatus.RUNNING:
                await self.build_manager.cancel_build(task_id)
                task.status = BuildStatus.CANCELLED
                task.finished_at = datetime.now()

                self.logger.info(f"Running build task cancelled: {task_id}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to cancel build {task_id}: {str(e)}")
            raise BuildError(
                f"Failed to cancel build task: {str(e)}",
                task_id=task_id,
                cause=e
            )

    async def get_build_task(self, task_id: str) -> Optional[BuildTask]:
        """获取构建任务"""
        # 首先尝试从构建历史中查找
        for task in self._build_history:
            if task.task_id == task_id:
                # 如果任务还在运行，获取最新状态
                if task.status == BuildStatus.RUNNING:
                    try:
                        updated_task = await self.build_manager.get_build_task(task_id)
                        if updated_task:
                            return updated_task
                    except Exception:
                        pass
                return task

        # 从构建管理器查找
        try:
            return await self.build_manager.get_build_task(task_id)
        except Exception:
            return None

    async def list_build_tasks(self, status_filter: Optional[BuildStatus] = None,
                               limit: int = 100) -> List[BuildTask]:
        """列出构建任务"""
        tasks = list(self._build_history)

        if status_filter:
            tasks = [task for task in tasks if task.status == status_filter]

        # 按创建时间倒序排序
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[:limit]

    async def get_build_logs(self, task_id: str) -> Optional[List[BuildLog]]:
        """获取构建日志"""
        try:
            return await self.build_manager.get_build_logs(task_id)
        except Exception as e:
            self.logger.error(f"Failed to get build logs for {task_id}: {str(e)}")
            return None

    async def get_build_artifacts(self, task_id: str) -> List[BuildArtifact]:
        """获取构建产物"""
        try:
            return await self.build_manager.get_build_artifacts(task_id)
        except Exception as e:
            self.logger.error(f"Failed to get build artifacts for {task_id}: {str(e)}")
            return []

    # ================== 构建模板管理 ==================

    async def create_template(self, name: str, description: str,
                              config: BuildConfig, environment: BuildEnvironment,
                              dependencies: List[BuildDependency] = None,
                              tags: List[str] = None) -> str:
        """创建构建模板"""
        template_id = generate_uuid()

        template = BuildTemplate(
            template_id=template_id,
            name=name,
            description=description,
            config=config,
            environment=environment,
            dependencies=dependencies or [],
            tags=tags or []
        )

        self._templates[template_id] = template

        self.logger.info(f"Build template created: {name} ({template_id})")
        return template_id

    async def get_template(self, template_id: str) -> Optional[BuildTemplate]:
        """获取构建模板"""
        return self._templates.get(template_id)

    async def list_templates(self, tag_filter: Optional[str] = None) -> List[BuildTemplate]:
        """列出构建模板"""
        templates = list(self._templates.values())

        if tag_filter:
            templates = [t for t in templates if tag_filter in t.tags]

        return templates

    async def update_template(self, template_id: str, **kwargs) -> bool:
        """更新构建模板"""
        template = self._templates.get(template_id)
        if not template:
            return False

        # 更新模板属性
        for key, value in kwargs.items():
            if hasattr(template, key):
                setattr(template, key, value)

        self.logger.info(f"Build template updated: {template_id}")
        return True

    async def delete_template(self, template_id: str) -> bool:
        """删除构建模板"""
        if template_id in self._templates:
            del self._templates[template_id]
            self.logger.info(f"Build template deleted: {template_id}")
            return True
        return False

    def _merge_template_config(self, template: BuildTemplate, config: BuildConfig) -> BuildConfig:
        """合并模板配置和用户配置"""
        merged_config = BuildConfig(
            source_url=config.source_url or template.config.source_url,
            spec_file=config.spec_file or template.config.spec_file,
            build_arch=config.build_arch or template.config.build_arch,
            build_options={**template.config.build_options, **(config.build_options or {})},
            environment_vars={**template.environment.environment_vars, **(config.environment_vars or {})},
            dependencies=template.dependencies + (config.dependencies or []),
            timeout=config.timeout or template.config.timeout,
            enable_tests=config.enable_tests if config.enable_tests is not None else template.config.enable_tests,
            test_commands=config.test_commands or template.config.test_commands
        )

        return merged_config

    # ================== 依赖管理 ==================

    async def analyze_dependencies(self, spec_file_path: str) -> List[BuildDependency]:
        """分析构建依赖"""
        cache_key = self._calculate_file_hash(spec_file_path)

        # 检查缓存
        if cache_key in self._dependency_cache:
            return self._dependency_cache[cache_key]

        try:
            dependencies = await self.build_manager.analyze_dependencies(spec_file_path)

            # 缓存结果
            self._dependency_cache[cache_key] = dependencies

            return dependencies

        except Exception as e:
            self.logger.error(f"Failed to analyze dependencies: {str(e)}")
            return []

    async def resolve_dependencies(self, dependencies: List[BuildDependency]) -> Dict[str, str]:
        """解析依赖包"""
        try:
            return await self.build_manager.resolve_dependencies(dependencies)
        except Exception as e:
            self.logger.error(f"Failed to resolve dependencies: {str(e)}")
            return {}

    async def install_dependencies(self, task_id: str, dependencies: List[BuildDependency]) -> bool:
        """安装构建依赖"""
        try:
            return await self.build_manager.install_dependencies(task_id, dependencies)
        except Exception as e:
            self.logger.error(f"Failed to install dependencies for {task_id}: {str(e)}")
            return False

    # ================== 构建缓存管理 ==================

    async def get_from_cache(self, cache_key: str) -> Optional[Any]:
        """从缓存获取数据"""
        return self._build_cache.get(cache_key)

    async def store_in_cache(self, cache_key: str, data: Any, ttl: Optional[int] = None):
        """存储数据到缓存"""
        cache_entry = {
            "data": data,
            "timestamp": datetime.now(),
            "ttl": ttl
        }

        self._build_cache[cache_key] = cache_entry

    async def clear_cache(self):
        """清理缓存"""
        # 清理过期缓存项
        current_time = datetime.now()
        expired_keys = []

        for key, entry in self._build_cache.items():
            if entry.get("ttl"):
                expire_time = entry["timestamp"] + timedelta(seconds=entry["ttl"])
                if current_time > expire_time:
                    expired_keys.append(key)

        for key in expired_keys:
            del self._build_cache[key]

        self.logger.info(f"Cleared {len(expired_keys)} expired cache entries")

    # ================== 构建优化 ==================

    async def optimize_build_environment(self, task_id: str) -> Dict[str, Any]:
        """优化构建环境"""
        try:
            task = await self.get_build_task(task_id)
            if not task:
                return {}

            optimizations = {}

            # CPU优化建议
            cpu_cores = os.cpu_count() or 1
            recommended_jobs = max(1, cpu_cores - 1)
            optimizations["parallel_jobs"] = recommended_jobs

            # 内存优化建议
            if hasattr(task.config, 'build_options'):
                build_options = task.config.build_options.copy()
                build_options.update({
                    "-j": str(recommended_jobs),
                    "--define": "_smp_mflags -j{}".format(recommended_jobs)
                })
                optimizations["build_options"] = build_options

            # 缓存建议
            optimizations["enable_ccache"] = True
            optimizations["cache_dir"] = str(self._work_dir / "ccache")

            self.logger.info(f"Generated build optimizations for {task_id}")
            return optimizations

        except Exception as e:
            self.logger.error(f"Failed to optimize build environment for {task_id}: {str(e)}")
            return {}

    async def get_build_recommendations(self, task_id: str) -> Dict[str, Any]:
        """获取构建建议"""
        try:
            task = await self.get_build_task(task_id)
            if not task:
                return {}

            recommendations = {}

            # 基于历史构建数据的建议
            similar_builds = await self._find_similar_builds(task)
            if similar_builds:
                successful_builds = [b for b in similar_builds if b.status == BuildStatus.COMPLETED]
                if successful_builds:
                    avg_build_time = sum(b.build_time for b in successful_builds if b.build_time) / len(successful_builds)
                    recommendations["estimated_build_time"] = avg_build_time

                    # 常用的构建选项
                    common_options = {}
                    for build in successful_builds:
                        if build.config.build_options:
                            for key, value in build.config.build_options.items():
                                common_options[key] = common_options.get(key, 0) + 1

                    recommendations["common_build_options"] = common_options

            # 资源使用建议
            if task.status == BuildStatus.COMPLETED and task.result:
                metrics = task.result.metrics
                if metrics:
                    if metrics.memory_peak_usage > 0:
                        recommended_memory = int(metrics.memory_peak_usage * 1.2)  # 增加20%缓冲
                        recommendations["recommended_memory"] = format_size(recommended_memory)

                    if metrics.cpu_time > 0:
                        recommendations["cpu_efficiency"] = metrics.cpu_time / (task.build_time or 1)

            return recommendations

        except Exception as e:
            self.logger.error(f"Failed to get build recommendations for {task_id}: {str(e)}")
            return {}

    async def _find_similar_builds(self, task: BuildTask) -> List[BuildTask]:
        """查找相似的构建任务"""
        similar_builds = []

        for history_task in self._build_history:
            if history_task.task_id == task.task_id:
                continue

            similarity_score = 0

            # 比较源码URL
            if history_task.config.source_url == task.config.source_url:
                similarity_score += 50

            # 比较spec文件
            if history_task.config.spec_file == task.config.spec_file:
                similarity_score += 30

            # 比较构建架构
            if history_task.config.build_arch == task.config.build_arch:
                similarity_score += 20

            if similarity_score >= 70:  # 相似度阈值
                similar_builds.append(history_task)

        return similar_builds[:10]  # 返回最多10个相似构建

    # ================== 事件处理 ==================

    async def _handle_build_event(self, event: BuildEvent):
        """处理构建事件"""
        self.logger.debug(f"Handling build event: {event.event_type} for {event.task_id}")

        # 更新构建历史中的任务状态
        for task in self._build_history:
            if task.task_id == event.task_id:
                if event.event_type == "status_changed":
                    task.status = event.new_status
                elif event.event_type == "build_completed":
                    task.finished_at = datetime.now()
                    if event.result:
                        task.result = event.result
                elif event.event_type == "build_failed":
                    task.status = BuildStatus.FAILED
                    task.finished_at = datetime.now()
                    task.error_message = event.error_message

                # 更新统计信息
                self._statistics.update(task)
                break

        # 发送到外部事件处理器
        await self._emit_event("build", event)

    async def _handle_scheduler_event(self, event_type: str, data: Dict[str, Any]):
        """处理调度器事件"""
        self.logger.debug(f"Handling scheduler event: {event_type}")

        # 根据事件类型处理
        if event_type == "build_started":
            # 可以在这里添加构建开始的处理逻辑
            pass
        elif event_type == "build_completed":
            # 清理构建缓存
            await self.clear_cache()
        elif event_type == "build_failed":
            # 记录失败信息，用于后续分析
            pass

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

    def _validate_build_config(self, config: BuildConfig):
        """验证构建配置"""
        if not config.source_url:
            raise ValidationError("Source URL is required", field="source_url")

        if not config.spec_file:
            raise ValidationError("Spec file is required", field="spec_file")

        # 验证架构
        valid_archs = ["x86_64", "aarch64", "noarch"]
        if config.build_arch and config.build_arch not in valid_archs:
            raise ValidationError(
                f"Invalid build architecture: {config.build_arch}. Valid options: {valid_archs}",
                field="build_arch"
            )

    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256()
                for chunk in iter(lambda: f.read(4096), b""):
                    file_hash.update(chunk)
                return file_hash.hexdigest()
        except Exception:
            return ""

    async def _load_default_templates(self):
        """加载默认构建模板"""
        # OpenEuler RPM构建模板
        openeuler_template = BuildTemplate(
            template_id="openeuler-rpm",
            name="OpenEuler RPM构建",
            description="标准的OpenEuler RPM包构建模板",
            config=BuildConfig(
                build_arch="x86_64",
                build_options={
                    "--define": "_topdir /workspace/rpmbuild",
                    "--with": "tests",
                    "-j": "4"
                },
                environment_vars={
                    "RPM_BUILD_ROOT": "/workspace/rpmbuild",
                    "LANG": "en_US.UTF-8"
                },
                timeout=3600,  # 1小时超时
                enable_tests=True
            ),
            environment=BuildEnvironment(
                base_image="openeuler/openeuler:latest",
                packages_to_install=[
                    "rpm-build", "rpmdevtools", "gcc", "gcc-c++",
                    "make", "autoconf", "automake", "libtool"
                ],
                environment_vars={
                    "LANG": "en_US.UTF-8",
                    "LC_ALL": "en_US.UTF-8"
                }
            ),
            tags=["openeuler", "rpm", "standard"]
        )

        self._templates["openeuler-rpm"] = openeuler_template

        # 轻量级构建模板
        lightweight_template = BuildTemplate(
            template_id="lightweight-build",
            name="轻量级构建",
            description="适用于简单项目的轻量级构建模板",
            config=BuildConfig(
                build_arch="noarch",
                build_options={
                    "--define": "_topdir /workspace/rpmbuild"
                },
                timeout=1800,  # 30分钟超时
                enable_tests=False
            ),
            environment=BuildEnvironment(
                base_image="openeuler/openeuler:latest",
                packages_to_install=["rpm-build", "rpmdevtools"],
                environment_vars={
                    "LANG": "en_US.UTF-8"
                }
            ),
            tags=["lightweight", "simple", "noarch"]
        )

        self._templates["lightweight-build"] = lightweight_template

        self.logger.info("Default build templates loaded")

    # ================== 统计和报告 ==================

    async def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        queue_status = self.scheduler.get_queue_status()

        return {
            "build_statistics": self._statistics.to_dict(),
            "queue_status": queue_status,
            "templates": len(self._templates),
            "cache_entries": len(self._build_cache),
            "dependency_cache_entries": len(self._dependency_cache),
            "history_size": len(self._build_history),
            "service_healthy": await self.is_healthy()
        }

    async def get_build_summary(self) -> Dict[str, Any]:
        """获取构建总体摘要"""
        recent_builds = await self.list_build_tasks(limit=50)

        if not recent_builds:
            return {
                "recent_builds": 0,
                "success_rate": 0.0,
                "average_build_time": 0.0,
                "queue_length": self.scheduler.get_queue_status()["queue_length"]
            }

        successful = len([b for b in recent_builds if b.status == BuildStatus.COMPLETED])
        failed = len([b for b in recent_builds if b.status == BuildStatus.FAILED])

        success_rate = (successful / len(recent_builds)) * 100 if recent_builds else 0

        # 计算平均构建时间
        completed_builds = [b for b in recent_builds if b.build_time]
        avg_build_time = (
            sum(b.build_time for b in completed_builds) / len(completed_builds)
            if completed_builds else 0
        )

        return {
            "recent_builds": len(recent_builds),
            "successful_builds": successful,
            "failed_builds": failed,
            "success_rate": success_rate,
            "average_build_time": format_duration(avg_build_time),
            "queue_length": self.scheduler.get_queue_status()["queue_length"],
            "running_builds": self.scheduler.get_queue_status()["running_builds"]
        }

    async def export_build_data(self, start_date: Optional[datetime] = None,
                                end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """导出构建数据"""
        export_data = {
            "export_time": datetime.now().isoformat(),
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            },
            "builds": [],
            "templates": [],
            "statistics": self._statistics.to_dict()
        }

        # 导出构建历史
        for task in self._build_history:
            # 过滤日期范围
            if start_date and task.created_at < start_date:
                continue
            if end_date and task.created_at > end_date:
                continue

            export_data["builds"].append(task.to_dict())

        # 导出模板
        for template in self._templates.values():
            export_data["templates"].append(template.to_dict())

        return export_data