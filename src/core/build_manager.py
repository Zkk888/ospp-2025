"""
构建管理器 - eulermaker-docker-optimizer的RPM构建管理核心

******OSPP-2025-张金荣******

提供完整的RPM构建管理功能，包括：
- 构建任务队列管理和调度
- 构建环境准备和清理
- 构建过程监控和日志收集
- 构建结果处理和存储
- 依赖管理和解析
- 并行构建支持
- 构建失败恢复机制
"""

import asyncio
import shutil
import tarfile
import tempfile
from typing import Dict, List, Optional, Any, Set, Callable
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
import json
import subprocess

from config.settings import get_build_settings
from utils.logger import get_logger, LoggerMixin, log_performance, log_errors
from utils.exceptions import BuildError, ContainerError, DockerError
from utils.helpers import (
    generate_uuid, format_timestamp, retry_async, timeout_async,
    generate_build_id, ensure_path, cleanup_path
)
from models.build_model import (
    BuildStatus, BuildConfig, BuildTask, BuildResult, BuildEvent,
    BuildArtifact, BuildDependency, RPMSpec
)
from models.container_model import ContainerConfig, VolumeMount, ResourceLimits
from .docker_manager import DockerManager
from .container_lifecycle import ContainerLifecycleManager


class BuildPriority(Enum):
    """构建优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


class BuildQueue:
    """构建任务队列"""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self._queue: List[BuildTask] = []
        self._running: Dict[str, BuildTask] = {}
        self._completed: Dict[str, BuildTask] = {}
        self._lock = asyncio.Lock()
        self.logger = get_logger(f"{__name__}.BuildQueue")

    async def add_task(self, task: BuildTask) -> bool:
        """添加构建任务"""
        async with self._lock:
            # 检查是否已存在相同的构建
            if self._find_task(task.build_id):
                self.logger.warning(f"Build task already exists: {task.build_id}")
                return False

            # 按优先级插入任务
            inserted = False
            for i, existing_task in enumerate(self._queue):
                if task.priority > existing_task.priority:
                    self._queue.insert(i, task)
                    inserted = True
                    break

            if not inserted:
                self._queue.append(task)

            self.logger.info(f"Added build task to queue: {task.build_id} (priority: {task.priority})")
            return True

    async def get_next_task(self) -> Optional[BuildTask]:
        """获取下一个待执行的任务"""
        async with self._lock:
            if not self._queue or len(self._running) >= self.max_concurrent:
                return None

            task = self._queue.pop(0)
            self._running[task.task_id] = task

            self.logger.debug(f"Retrieved task from queue: {task.build_id}")
            return task

    async def complete_task(self, task_id: str, task: BuildTask):
        """完成任务"""
        async with self._lock:
            self._running.pop(task_id, None)
            self._completed[task_id] = task

            self.logger.info(f"Task completed: {task.build_id} (status: {task.status.value})")

    def _find_task(self, build_id: str) -> Optional[BuildTask]:
        """查找任务"""
        # 在队列中查找
        for task in self._queue:
            if task.build_id == build_id:
                return task

        # 在运行中查找
        for task in self._running.values():
            if task.build_id == build_id:
                return task

        # 在已完成中查找
        for task in self._completed.values():
            if task.build_id == build_id:
                return task

        return None

    async def get_task(self, build_id: str) -> Optional[BuildTask]:
        """获取指定任务"""
        async with self._lock:
            return self._find_task(build_id)

    async def cancel_task(self, build_id: str) -> bool:
        """取消任务"""
        async with self._lock:
            # 从队列中移除
            for i, task in enumerate(self._queue):
                if task.build_id == build_id:
                    removed_task = self._queue.pop(i)
                    removed_task.finish(BuildStatus.CANCELLED, "任务被取消")
                    self._completed[removed_task.task_id] = removed_task
                    self.logger.info(f"Cancelled queued task: {build_id}")
                    return True

            return False

    async def get_stats(self) -> Dict[str, int]:
        """获取队列统计信息"""
        async with self._lock:
            return {
                "queued": len(self._queue),
                "running": len(self._running),
                "completed": len(self._completed)
            }

    async def get_all_tasks(self) -> Dict[str, List[BuildTask]]:
        """获取所有任务"""
        async with self._lock:
            return {
                "queued": self._queue.copy(),
                "running": list(self._running.values()),
                "completed": list(self._completed.values())
            }


class BuildExecutor(LoggerMixin):
    """构建执行器"""

    def __init__(self, docker_manager: DockerManager,
                 container_manager: ContainerLifecycleManager):
        super().__init__()
        self.docker_manager = docker_manager
        self.container_manager = container_manager
        self.settings = get_build_settings()

    @log_performance("execute_build")
    async def execute_build(self, task: BuildTask) -> BuildResult:
        """执行构建任务"""
        build_id = task.build_id
        config = task.config

        try:
            self.logger.info(f"Starting build execution: {build_id}")

            # 启动任务
            task.start()

            # 准备构建环境
            container_id = await self._prepare_build_environment(task)
            task.container_id = container_id

            # 执行构建步骤
            await self._execute_build_steps(task)

            # 收集构建结果
            await self._collect_build_artifacts(task)

            # 清理构建环境
            await self._cleanup_build_environment(task)

            # 标记任务完成
            if task.result.status == BuildStatus.BUILDING:
                task.finish(BuildStatus.SUCCESS, "构建成功完成")

            self.logger.info(f"Build completed successfully: {build_id}")
            return task.result

        except Exception as e:
            self.logger.error(f"Build failed: {build_id} - {str(e)}")

            # 清理构建环境
            try:
                await self._cleanup_build_environment(task)
            except:
                pass

            # 标记任务失败
            task.finish(BuildStatus.FAILED, f"构建失败: {str(e)}", str(e))

            raise BuildError(
                f"Build execution failed: {str(e)}",
                build_id=build_id,
                build_stage="execution",
                cause=e
            )

    async def _prepare_build_environment(self, task: BuildTask) -> str:
        """准备构建环境"""
        config = task.config

        try:
            task.update_progress("preparing", 10.0)

            # 构建容器配置
            container_config = ContainerConfig(
                name=config.container_name,
                image=config.base_image,
                working_dir="/workspace",
                environment=dict(config.environment_vars),
                command=None,  # 手动执行命令
                auto_remove=False,
                detach=True
            )

            # 配置资源限制
            container_config.resources = ResourceLimits(
                memory="4g",  # 构建需要更多内存
                cpu_shares=2048
            )

            # 配置数据卷
            workspace_mount = VolumeMount(
                source=str(Path(config.output_dir)),
                target="/workspace",
                type="bind"
            )
            container_config.volumes.append(workspace_mount)

            # 创建并启动容器
            container_id = await self.container_manager.create_and_start_container(container_config)

            self.logger.info(f"Build environment prepared: {container_id}")
            return container_id

        except Exception as e:
            raise BuildError(
                f"Failed to prepare build environment: {str(e)}",
                build_id=task.build_id,
                build_stage="prepare",
                cause=e
            )

    async def _execute_build_steps(self, task: BuildTask):
        """执行构建步骤"""
        config = task.config
        container_id = task.container_id

        if not container_id:
            raise BuildError("No container ID available", build_id=task.build_id)

        try:
            # 步骤1: 安装构建工具
            task.update_progress("installing_tools", 20.0)
            await self._install_build_tools(container_id, task)

            # 步骤2: 下载源码
            task.update_progress("downloading_sources", 30.0)
            await self._download_sources(container_id, task)

            # 步骤3: 安装依赖
            task.update_progress("installing_dependencies", 40.0)
            await self._install_dependencies(container_id, task)

            # 步骤4: 配置构建环境
            task.update_progress("configuring", 50.0)
            await self._configure_build(container_id, task)

            # 步骤5: 执行构建
            task.update_progress("building", 60.0)
            await self._run_build(container_id, task)

            # 步骤6: 运行测试
            if config.build_flags and "skip-test" not in config.build_flags:
                task.update_progress("testing", 80.0)
                await self._run_tests(container_id, task)

            # 步骤7: 打包结果
            task.update_progress("packaging", 90.0)
            await self._package_results(container_id, task)

            task.update_progress("completed", 100.0)

        except Exception as e:
            raise BuildError(
                f"Build step failed: {str(e)}",
                build_id=task.build_id,
                build_stage=task.current_stage or "unknown",
                cause=e
            )

    async def _install_build_tools(self, container_id: str, task: BuildTask):
        """安装构建工具"""
        tools_command = [
                            "dnf", "install", "-y"
                        ] + self.settings.build_tools_packages

        result = await self.docker_manager.execute_command(
            container_id,
            tools_command,
            stream=False
        )

        if result["exit_code"] != 0:
            raise BuildError(
                f"Failed to install build tools: {result['output']}",
                build_id=task.build_id,
                build_stage="install_tools"
            )

        self.logger.debug(f"Build tools installed for {task.build_id}")

    async def _download_sources(self, container_id: str, task: BuildTask):
        """下载源码"""
        config = task.config

        # 创建rpmbuild目录结构
        mkdir_commands = [
            f"mkdir -p {self.settings.sources_dir}",
            f"mkdir -p {self.settings.specs_dir}",
            f"mkdir -p {self.settings.rpms_dir}",
            f"mkdir -p {self.settings.srpms_dir}"
        ]

        for cmd in mkdir_commands:
            result = await self.docker_manager.execute_command(
                container_id,
                cmd.split(),
                stream=False
            )

            if result["exit_code"] != 0:
                raise BuildError(
                    f"Failed to create directory: {result['output']}",
                    build_id=task.build_id,
                    build_stage="download_sources"
                )

        # 复制spec文件
        if config.spec_file:
            spec_path = Path(config.spec_file)
            if spec_path.exists():
                # 简化实现：直接在容器中创建spec文件内容
                # 实际项目中应该通过数据卷或文件复制来处理
                spec_content = spec_path.read_text()

                create_spec_cmd = f"cat > {self.settings.specs_dir}/{spec_path.name} << 'EOF'\n{spec_content}\nEOF"

                result = await self.docker_manager.execute_command(
                    container_id,
                    ["bash", "-c", create_spec_cmd],
                    stream=False
                )

                if result["exit_code"] != 0:
                    raise BuildError(
                        f"Failed to create spec file: {result['output']}",
                        build_id=task.build_id,
                        build_stage="download_sources"
                    )

        # 下载源码
        if config.source_url:
            download_cmd = [
                "curl", "-L", "-o",
                f"{self.settings.sources_dir}/source.tar.gz",
                config.source_url
            ]

            result = await self.docker_manager.execute_command(
                container_id,
                download_cmd,
                stream=False
            )

            if result["exit_code"] != 0:
                raise BuildError(
                    f"Failed to download source: {result['output']}",
                    build_id=task.build_id,
                    build_stage="download_sources"
                )

        self.logger.debug(f"Sources downloaded for {task.build_id}")

    async def _install_dependencies(self, container_id: str, task: BuildTask):
        """安装构建依赖"""
        config = task.config

        if not config.dependencies:
            return

        # 安装依赖包
        for dependency in config.dependencies:
            if dependency.type == "package":
                install_cmd = ["dnf", "install", "-y", dependency.name]

                if dependency.version:
                    install_cmd[-1] = f"{dependency.name}-{dependency.version}"

                result = await self.docker_manager.execute_command(
                    container_id,
                    install_cmd,
                    stream=False
                )

                if result["exit_code"] != 0 and not dependency.optional:
                    raise BuildError(
                        f"Failed to install dependency {dependency.name}: {result['output']}",
                        build_id=task.build_id,
                        build_stage="install_dependencies"
                    )

        self.logger.debug(f"Dependencies installed for {task.build_id}")

    async def _configure_build(self, container_id: str, task: BuildTask):
        """配置构建环境"""
        config = task.config

        # 设置构建环境变量
        env_commands = []
        for key, value in config.environment_vars.items():
            env_commands.append(f"export {key}='{value}'")

        if env_commands:
            env_script = " && ".join(env_commands)
            result = await self.docker_manager.execute_command(
                container_id,
                ["bash", "-c", env_script],
                stream=False
            )

            if result["exit_code"] != 0:
                self.logger.warning(f"Failed to set environment variables: {result['output']}")

        self.logger.debug(f"Build configured for {task.build_id}")

    async def _run_build(self, container_id: str, task: BuildTask):
        """运行构建"""
        config = task.config

        # 构建rpmbuild命令
        rpmbuild_cmd = ["rpmbuild"]

        # 添加构建标志
        rpmbuild_cmd.extend(["-ba"])  # 构建二进制和源码包

        # 添加自定义构建标志
        if config.build_flags:
            rpmbuild_cmd.extend(config.build_flags)

        # 添加并行构建支持
        if config.parallel_jobs > 1:
            rpmbuild_cmd.extend([f"-j{config.parallel_jobs}"])

        # 添加spec文件
        spec_file_name = Path(config.spec_file).name if config.spec_file else "*.spec"
        rpmbuild_cmd.append(f"{self.settings.specs_dir}/{spec_file_name}")

        # 执行构建
        result = await timeout_async(config.timeout)(
            self.docker_manager.execute_command
        )(
            container_id,
            rpmbuild_cmd,
            stream=False
        )

        if result["exit_code"] != 0:
            raise BuildError(
                f"RPM build failed: {result['output']}",
                build_id=task.build_id,
                build_stage="build"
            )

        # 记录构建输出
        task.result.message = "构建成功完成"

        self.logger.info(f"Build completed for {task.build_id}")

    async def _run_tests(self, container_id: str, task: BuildTask):
        """运行测试"""
        # 简化的测试实现
        test_cmd = ["rpmlint", f"{self.settings.rpms_dir}/*.rpm"]

        result = await self.docker_manager.execute_command(
            container_id,
            test_cmd,
            stream=False
        )

        # rpmlint的非零退出码不一定表示致命错误
        if result["exit_code"] != 0:
            self.logger.warning(f"Tests completed with warnings for {task.build_id}: {result['output']}")
        else:
            self.logger.debug(f"Tests passed for {task.build_id}")

    async def _package_results(self, container_id: str, task: BuildTask):
        """打包构建结果"""
        # 创建结果目录
        result_dir = Path(task.config.output_dir) / "results"
        result_dir.mkdir(parents=True, exist_ok=True)

        # 复制RPM包到结果目录
        copy_cmd = [
            "bash", "-c",
            f"cp {self.settings.rpms_dir}/*.rpm {result_dir}/ 2>/dev/null || true"
        ]

        await self.docker_manager.execute_command(
            container_id,
            copy_cmd,
            stream=False
        )

        # 复制SRPM包
        copy_srpm_cmd = [
            "bash", "-c",
            f"cp {self.settings.srpms_dir}/*.src.rpm {result_dir}/ 2>/dev/null || true"
        ]

        await self.docker_manager.execute_command(
            container_id,
            copy_srpm_cmd,
            stream=False
        )

        self.logger.debug(f"Results packaged for {task.build_id}")

    async def _collect_build_artifacts(self, task: BuildTask):
        """收集构建产物"""
        config = task.config
        result_dir = Path(config.output_dir) / "results"

        if not result_dir.exists():
            self.logger.warning(f"Result directory not found: {result_dir}")
            return

        # 扫描构建产物
        for rpm_file in result_dir.glob("*.rpm"):
            # 判断文件类型
            if ".src.rpm" in rpm_file.name:
                artifact_type = "srpm"
                task.result.srpm_count += 1
            else:
                artifact_type = "rpm"
                task.result.rpm_count += 1

            # 创建产物对象
            artifact = BuildArtifact(
                name=rpm_file.name,
                type=artifact_type,
                path=str(rpm_file),
                size=rpm_file.stat().st_size
            )

            task.result.add_artifact(artifact)

        # 保存构建日志
        if config.save_logs:
            await self._save_build_logs(task)

        self.logger.info(
            f"Collected {task.result.rpm_count} RPM and {task.result.srpm_count} SRPM packages for {task.build_id}"
        )

    async def _save_build_logs(self, task: BuildTask):
        """保存构建日志"""
        if not task.container_id:
            return

        try:
            # 获取容器日志
            logs = await self.docker_manager.get_container_logs(task.container_id)

            # 保存到文件
            log_dir = Path(task.config.output_dir) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / f"build-{task.build_id}.log"
            log_file.write_text(logs)

            task.result.log_file = str(log_file)

            self.logger.debug(f"Build logs saved: {log_file}")

        except Exception as e:
            self.logger.warning(f"Failed to save build logs for {task.build_id}: {str(e)}")

    async def _cleanup_build_environment(self, task: BuildTask):
        """清理构建环境"""
        if not task.container_id:
            return

        try:
            # 移除构建容器
            await self.container_manager.remove_container(task.container_id, force=True)
            self.logger.debug(f"Build container cleaned up: {task.container_id}")

        except Exception as e:
            self.logger.warning(f"Failed to cleanup build container {task.container_id}: {str(e)}")

        # 清理临时文件
        if not task.config.keep_build_dir:
            try:
                build_dir = Path(task.config.output_dir) / "build"
                if build_dir.exists():
                    shutil.rmtree(build_dir)
                    self.logger.debug(f"Build directory cleaned up: {build_dir}")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup build directory: {str(e)}")


class BuildManager(LoggerMixin):
    """构建管理器 - 统一的构建管理接口"""

    def __init__(self, docker_manager: DockerManager,
                 container_manager: ContainerLifecycleManager):
        super().__init__()
        self.docker_manager = docker_manager
        self.container_manager = container_manager
        self.settings = get_build_settings()

        # 构建队列和执行器
        self.build_queue = BuildQueue(max_concurrent=3)
        self.build_executor = BuildExecutor(docker_manager, container_manager)

        # 任务管理
        self._build_tasks: Dict[str, BuildTask] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}

        # 执行任务管理
        self._worker_tasks: List[asyncio.Task] = []
        self._initialized = False
        self._shutdown_event = asyncio.Event()

    async def initialize(self):
        """初始化构建管理器"""
        try:
            # 确保构建目录存在
            ensure_path(self.settings.rpmbuild_base)
            ensure_path(self.settings.sources_dir)
            ensure_path(self.settings.specs_dir)
            ensure_path(self.settings.rpms_dir)
            ensure_path(self.settings.srpms_dir)

            # 启动工作线程
            for i in range(3):  # 启动3个工作线程
                worker_task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
                self._worker_tasks.append(worker_task)

            self._initialized = True
            self.logger.info("Build manager initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize build manager: {str(e)}")
            raise BuildError(f"Build manager initialization failed: {str(e)}", cause=e)

    async def cleanup(self):
        """清理构建管理器"""
        self._initialized = False

        # 通知所有工作线程停止
        self._shutdown_event.set()

        # 等待工作线程完成
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        self.logger.info("Build manager cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    async def is_healthy(self) -> bool:
        """检查构建管理器健康状态"""
        if not self._initialized:
            return False

        # 检查Docker和容器管理器状态
        if not await self.docker_manager.is_healthy():
            return False

        if not await self.container_manager.is_healthy():
            return False

        return True

    # ================== 构建任务管理 ==================

    async def submit_build(self, build_config: BuildConfig,
                           priority: int = BuildPriority.NORMAL.value) -> str:
        """提交构建任务"""
        try:
            # 创建构建任务
            task = BuildTask(
                task_id=generate_uuid(),
                config=build_config,
                priority=priority
            )

            # 添加到队列
            success = await self.build_queue.add_task(task)
            if not success:
                raise BuildError(f"Failed to add build task to queue: {build_config.build_id}")

            # 存储任务
            self._build_tasks[task.task_id] = task

            # 发送构建提交事件
            await self._emit_event(BuildEvent(
                build_id=build_config.build_id,
                event_type="build_submitted",
                message=f"构建任务已提交: {build_config.project_name}",
                level="info"
            ))

            self.logger.info(f"Build submitted: {build_config.build_id} (task: {task.task_id})")
            return task.task_id

        except Exception as e:
            self.logger.error(f"Failed to submit build: {str(e)}")
            raise BuildError(f"Failed to submit build: {str(e)}", cause=e)

    async def cancel_build(self, build_id: str) -> bool:
        """取消构建"""
        try:
            # 尝试从队列中取消
            if await self.build_queue.cancel_task(build_id):
                await self._emit_event(BuildEvent(
                    build_id=build_id,
                    event_type="build_cancelled",
                    message="构建任务已取消",
                    level="info"
                ))
                return True

            # 查找正在运行的任务
            for task in self._build_tasks.values():
                if task.build_id == build_id and task.status.is_active():
                    # 停止构建容器
                    if task.container_id:
                        try:
                            await self.container_manager.stop_container(task.container_id)
                            await self.container_manager.remove_container(task.container_id, force=True)
                        except:
                            pass

                    # 标记为取消
                    task.finish(BuildStatus.CANCELLED, "构建已被取消")

                    await self._emit_event(BuildEvent(
                        build_id=build_id,
                        event_type="build_cancelled",
                        message="正在运行的构建已取消",
                        level="info"
                    ))

                    return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to cancel build {build_id}: {str(e)}")
            return False

    async def get_build_status(self, build_id: str) -> Optional[BuildTask]:
        """获取构建状态"""
        # 从队列中获取
        task = await self.build_queue.get_task(build_id)
        if task:
            return task

        # 从本地存储中获取
        for task in self._build_tasks.values():
            if task.build_id == build_id:
                return task

        return None

    async def get_build_result(self, build_id: str) -> Optional[BuildResult]:
        """获取构建结果"""
        task = await self.get_build_status(build_id)
        return task.result if task else None

    async def list_builds(self, status_filter: Optional[BuildStatus] = None,
                          limit: int = 100) -> List[BuildTask]:
        """列出构建任务"""
        tasks = []

        # 从队列获取所有任务
        all_tasks = await self.build_queue.get_all_tasks()
        for task_list in all_tasks.values():
            tasks.extend(task_list)

        # 添加本地存储的任务
        for task in self._build_tasks.values():
            if task not in tasks:
                tasks.append(task)

        # 应用状态过滤
        if status_filter:
            tasks = [task for task in tasks if task.status == status_filter]

        # 按创建时间排序并限制数量
        tasks.sort(key=lambda x: x.created_at, reverse=True)
        return tasks[:limit]

    async def get_stats(self) -> Dict[str, Any]:
        """获取构建统计信息"""
        queue_stats = await self.build_queue.get_stats()

        # 计算不同状态的构建数量
        all_tasks = list(self._build_tasks.values())
        status_counts = {}
        for status in BuildStatus:
            status_counts[status.value] = len([
                task for task in all_tasks if task.status == status
            ])

        return {
            "queue": queue_stats,
            "status_counts": status_counts,
            "total_tasks": len(all_tasks),
            "worker_threads": len(self._worker_tasks)
        }

    # ================== 批量操作 ==================

    async def submit_batch_builds(self, build_configs: List[BuildConfig],
                                  priority: int = BuildPriority.NORMAL.value) -> List[str]:
        """批量提交构建任务"""
        task_ids = []

        for config in build_configs:
            try:
                task_id = await self.submit_build(config, priority)
                task_ids.append(task_id)
            except Exception as e:
                self.logger.error(f"Failed to submit build {config.build_id}: {str(e)}")

        return task_ids

    async def cancel_batch_builds(self, build_ids: List[str]) -> Dict[str, bool]:
        """批量取消构建任务"""
        results = {}

        for build_id in build_ids:
            try:
                success = await self.cancel_build(build_id)
                results[build_id] = success
            except Exception as e:
                self.logger.error(f"Failed to cancel build {build_id}: {str(e)}")
                results[build_id] = False

        return results

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

    async def _emit_event(self, event: BuildEvent):
        """发送事件"""
        self.logger.debug(f"Emitting event: {event.event_type} for {event.build_id}")

        # 调用事件处理器
        handlers = self._event_handlers.get(event.event_type, [])
        handlers.extend(self._event_handlers.get("all", []))

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                self.logger.error(f"Error in event handler: {str(e)}")

    # ================== 工作线程 ==================

    async def _worker_loop(self, worker_id: str):
        """工作线程循环"""
        self.logger.info(f"Build worker {worker_id} started")

        while not self._shutdown_event.is_set():
            try:
                # 获取下一个任务
                task = await self.build_queue.get_next_task()

                if not task:
                    # 没有任务，等待一段时间
                    await asyncio.sleep(1)
                    continue

                self.logger.info(f"Worker {worker_id} processing build: {task.build_id}")

                # 发送构建开始事件
                await self._emit_event(BuildEvent(
                    build_id=task.build_id,
                    event_type="build_started",
                    message=f"构建开始执行 (worker: {worker_id})",
                    level="info"
                ))

                # 执行构建
                try:
                    await self.build_executor.execute_build(task)

                    # 发送构建完成事件
                    await self._emit_event(BuildEvent(
                        build_id=task.build_id,
                        event_type="build_completed",
                        message="构建成功完成",
                        level="info"
                    ))

                except Exception as e:
                    # 发送构建失败事件
                    await self._emit_event(BuildEvent(
                        build_id=task.build_id,
                        event_type="build_failed",
                        message=f"构建失败: {str(e)}",
                        level="error"
                    ))

                # 标记任务完成
                await self.build_queue.complete_task(task.task_id, task)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in worker {worker_id}: {str(e)}")
                await asyncio.sleep(5)  # 出错后等待5秒

        self.logger.info(f"Build worker {worker_id} stopped")