"""
******OSPP-2025-张金荣******

Eulermaker-docker-optimizer 的构建数据模型

此模块定义了用于 RPM 构建管理的数据模型，包括：
• 构建配置与规范

• 构建任务状态与进度跟踪

• 构建结果与产物

• 依赖关系与需求
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import json


class BuildStatus(Enum):
    """构建状态枚举"""
    PENDING = "pending"          # 等待中
    PREPARING = "preparing"      # 准备中
    DOWNLOADING = "downloading"  # 下载依赖中
    BUILDING = "building"        # 构建中
    TESTING = "testing"          # 测试中
    PACKAGING = "packaging"      # 打包中
    SUCCESS = "success"          # 成功
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消
    TIMEOUT = "timeout"          # 超时

    def is_active(self) -> bool:
        """判断构建是否处于活动状态"""
        return self in [self.PENDING, self.PREPARING, self.DOWNLOADING,
                        self.BUILDING, self.TESTING, self.PACKAGING]

    def is_finished(self) -> bool:
        """判断构建是否已完成"""
        return self in [self.SUCCESS, self.FAILED, self.CANCELLED, self.TIMEOUT]

    def is_successful(self) -> bool:
        """判断构建是否成功"""
        return self == self.SUCCESS


@dataclass
class BuildDependency:
    """构建依赖"""
    name: str                           # 依赖名称
    version: Optional[str] = None       # 版本要求
    type: str = "package"               # 依赖类型 (package, source, build)
    source: Optional[str] = None        # 依赖来源
    optional: bool = False              # 是否可选依赖

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "version": self.version,
            "type": self.type,
            "source": self.source,
            "optional": self.optional
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BuildDependency':
        """从字典创建实例"""
        return cls(**data)

    def __str__(self) -> str:
        """字符串表示"""
        if self.version:
            return f"{self.name}-{self.version}"
        return self.name


@dataclass
class RPMSpec:
    """RPM规格文件信息"""
    name: str                           # 包名
    version: str                        # 版本
    release: str                        # 发布号
    summary: str                        # 摘要
    description: str                    # 描述
    license: str                        # 许可证
    group: Optional[str] = None         # 组
    url: Optional[str] = None           # 项目URL
    source: List[str] = field(default_factory=list)  # 源码文件
    patch: List[str] = field(default_factory=list)   # 补丁文件
    build_requires: List[str] = field(default_factory=list)  # 构建依赖
    requires: List[str] = field(default_factory=list)        # 运行时依赖
    provides: List[str] = field(default_factory=list)        # 提供的功能
    conflicts: List[str] = field(default_factory=list)       # 冲突包
    obsoletes: List[str] = field(default_factory=list)       # 废弃包
    build_arch: str = "x86_64"          # 构建架构

    @property
    def full_name(self) -> str:
        """获取完整包名"""
        return f"{self.name}-{self.version}-{self.release}"

    @property
    def nvr(self) -> str:
        """获取Name-Version-Release格式"""
        return f"{self.name}-{self.version}-{self.release}"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "version": self.version,
            "release": self.release,
            "summary": self.summary,
            "description": self.description,
            "license": self.license,
            "group": self.group,
            "url": self.url,
            "source": self.source,
            "patch": self.patch,
            "build_requires": self.build_requires,
            "requires": self.requires,
            "provides": self.provides,
            "conflicts": self.conflicts,
            "obsoletes": self.obsoletes,
            "build_arch": self.build_arch
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPMSpec':
        """从字典创建实例"""
        return cls(**data)

    @classmethod
    def from_spec_file(cls, spec_path: Union[str, Path]) -> 'RPMSpec':
        """从spec文件解析创建实例"""
        # 这里简化实现，实际应该解析spec文件内容
        spec_path = Path(spec_path)
        if not spec_path.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_path}")

        # 基本信息提取（简化版）
        name = spec_path.stem
        return cls(
            name=name,
            version="1.0.0",
            release="1",
            summary=f"Package {name}",
            description=f"Description for {name}",
            license="Unknown"
        )


@dataclass
class BuildArtifact:
    """构建产物"""
    name: str                           # 产物名称
    type: str                           # 产物类型 (rpm, srpm, debuginfo, log)
    path: str                           # 文件路径
    size: int                           # 文件大小（字节）
    checksum: Optional[str] = None      # 校验和
    checksum_type: str = "sha256"       # 校验和类型
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def size_human(self) -> str:
        """人类可读的文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.size < 1024.0:
                return f"{self.size:.1f} {unit}"
            self.size /= 1024.0
        return f"{self.size:.1f} TB"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "type": self.type,
            "path": self.path,
            "size": self.size,
            "checksum": self.checksum,
            "checksum_type": self.checksum_type,
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BuildArtifact':
        """从字典创建实例"""
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


@dataclass
class BuildConfig:
    """构建配置"""
    # 基本信息
    build_id: str                       # 构建ID
    project_name: str                   # 项目名称
    spec_file: str                      # spec文件路径
    source_url: Optional[str] = None    # 源码URL

    # 构建环境
    base_image: str = "openeuler/openeuler:latest"  # 基础镜像
    architecture: str = "x86_64"        # 目标架构
    container_name: Optional[str] = None # 容器名称

    # 构建参数
    build_flags: List[str] = field(default_factory=list)  # 构建标志
    environment_vars: Dict[str, str] = field(default_factory=dict)  # 环境变量
    timeout: int = 3600                 # 超时时间（秒）
    parallel_jobs: int = 1              # 并行任务数

    # 依赖管理
    dependencies: List[BuildDependency] = field(default_factory=list)  # 依赖列表
    repositories: List[str] = field(default_factory=list)  # 软件源列表

    # 输出配置
    output_dir: str = "/tmp/build-output"  # 输出目录
    keep_build_dir: bool = False        # 保持构建目录
    save_logs: bool = True              # 保存日志

    # 通知配置
    notification_webhook: Optional[str] = None  # 通知webhook

    def __post_init__(self):
        """初始化后处理"""
        if not self.container_name:
            self.container_name = f"build-{self.build_id}"

    def add_dependency(self, name: str, version: Optional[str] = None,
                       dep_type: str = "package", optional: bool = False):
        """添加依赖"""
        dep = BuildDependency(
            name=name,
            version=version,
            type=dep_type,
            optional=optional
        )
        self.dependencies.append(dep)

    def get_required_dependencies(self) -> List[BuildDependency]:
        """获取必需依赖"""
        return [dep for dep in self.dependencies if not dep.optional]

    def get_optional_dependencies(self) -> List[BuildDependency]:
        """获取可选依赖"""
        return [dep for dep in self.dependencies if dep.optional]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "build_id": self.build_id,
            "project_name": self.project_name,
            "spec_file": self.spec_file,
            "source_url": self.source_url,
            "base_image": self.base_image,
            "architecture": self.architecture,
            "container_name": self.container_name,
            "build_flags": self.build_flags,
            "environment_vars": self.environment_vars,
            "timeout": self.timeout,
            "parallel_jobs": self.parallel_jobs,
            "dependencies": [dep.to_dict() for dep in self.dependencies],
            "repositories": self.repositories,
            "output_dir": self.output_dir,
            "keep_build_dir": self.keep_build_dir,
            "save_logs": self.save_logs,
            "notification_webhook": self.notification_webhook
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BuildConfig':
        """从字典创建实例"""
        # 处理依赖列表
        if 'dependencies' in data:
            data['dependencies'] = [
                BuildDependency.from_dict(dep) for dep in data['dependencies']
            ]
        return cls(**data)


@dataclass
class BuildResult:
    """构建结果"""
    build_id: str                       # 构建ID
    status: BuildStatus                 # 构建状态
    exit_code: Optional[int] = None     # 退出码
    message: Optional[str] = None       # 结果消息
    error_message: Optional[str] = None # 错误消息

    # 时间信息
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    duration: Optional[float] = None    # 持续时间（秒）

    # 产物信息
    artifacts: List[BuildArtifact] = field(default_factory=list)  # 构建产物
    log_file: Optional[str] = None      # 日志文件路径

    # 统计信息
    rpm_count: int = 0                  # RPM包数量
    srpm_count: int = 0                 # 源码包数量
    total_size: int = 0                 # 总大小

    def finish(self, status: BuildStatus, message: Optional[str] = None,
               error_message: Optional[str] = None, exit_code: Optional[int] = None):
        """完成构建"""
        self.status = status
        self.finished_at = datetime.now()
        self.duration = (self.finished_at - self.started_at).total_seconds()

        if message:
            self.message = message
        if error_message:
            self.error_message = error_message
        if exit_code is not None:
            self.exit_code = exit_code

    def add_artifact(self, artifact: BuildArtifact):
        """添加构建产物"""
        self.artifacts.append(artifact)
        self.total_size += artifact.size

        if artifact.type == "rpm":
            self.rpm_count += 1
        elif artifact.type == "srpm":
            self.srpm_count += 1

    def get_artifacts_by_type(self, artifact_type: str) -> List[BuildArtifact]:
        """按类型获取产物"""
        return [artifact for artifact in self.artifacts if artifact.type == artifact_type]

    def get_main_packages(self) -> List[BuildArtifact]:
        """获取主要包（非debug包）"""
        return [
            artifact for artifact in self.artifacts
            if artifact.type == "rpm" and "-debuginfo" not in artifact.name
        ]

    @property
    def duration_human(self) -> str:
        """人类可读的持续时间"""
        if not self.duration:
            return "Unknown"

        if self.duration < 60:
            return f"{self.duration:.1f}s"
        elif self.duration < 3600:
            minutes = int(self.duration // 60)
            seconds = int(self.duration % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(self.duration // 3600)
            minutes = int((self.duration % 3600) // 60)
            return f"{hours}h {minutes}m"

    @property
    def total_size_human(self) -> str:
        """人类可读的总大小"""
        size = self.total_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "build_id": self.build_id,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "message": self.message,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "duration": self.duration,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "log_file": self.log_file,
            "rpm_count": self.rpm_count,
            "srpm_count": self.srpm_count,
            "total_size": self.total_size
        }

        if self.finished_at:
            data["finished_at"] = self.finished_at.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BuildResult':
        """从字典创建实例"""
        # 处理时间字段
        if isinstance(data.get('started_at'), str):
            data['started_at'] = datetime.fromisoformat(data['started_at'])
        if isinstance(data.get('finished_at'), str):
            data['finished_at'] = datetime.fromisoformat(data['finished_at'])

        # 处理状态字段
        if isinstance(data.get('status'), str):
            data['status'] = BuildStatus(data['status'])

        # 处理产物列表
        if 'artifacts' in data:
            data['artifacts'] = [
                BuildArtifact.from_dict(artifact) for artifact in data['artifacts']
            ]

        return cls(**data)


@dataclass
class BuildTask:
    """构建任务"""
    # 基本信息
    task_id: str                        # 任务ID
    config: BuildConfig                 # 构建配置
    result: Optional[BuildResult] = None # 构建结果

    # 执行信息
    container_id: Optional[str] = None  # 容器ID
    worker_id: Optional[str] = None     # 工作节点ID
    priority: int = 0                   # 优先级

    # 时间信息
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # 状态追踪
    current_stage: Optional[str] = None # 当前阶段
    progress: float = 0.0               # 进度 (0-100)

    def __post_init__(self):
        """初始化后处理"""
        if not self.result:
            self.result = BuildResult(
                build_id=self.config.build_id,
                status=BuildStatus.PENDING
            )

    @property
    def status(self) -> BuildStatus:
        """获取任务状态"""
        return self.result.status if self.result else BuildStatus.PENDING

    @property
    def build_id(self) -> str:
        """获取构建ID"""
        return self.config.build_id

    def start(self, container_id: Optional[str] = None):
        """开始执行任务"""
        self.started_at = datetime.now()
        self.container_id = container_id
        if self.result:
            self.result.status = BuildStatus.PREPARING
            self.result.started_at = self.started_at

    def update_progress(self, stage: str, progress: float):
        """更新进度"""
        self.current_stage = stage
        self.progress = max(0, min(100, progress))

    def finish(self, status: BuildStatus, message: Optional[str] = None,
               error_message: Optional[str] = None, exit_code: Optional[int] = None):
        """完成任务"""
        self.finished_at = datetime.now()
        if self.result:
            self.result.finish(status, message, error_message, exit_code)

    def get_estimated_time_remaining(self) -> Optional[timedelta]:
        """获取预估剩余时间"""
        if not self.started_at or self.progress <= 0:
            return None

        elapsed = datetime.now() - self.started_at
        if self.progress >= 100:
            return timedelta(0)

        estimated_total = elapsed * (100 / self.progress)
        remaining = estimated_total - elapsed
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "task_id": self.task_id,
            "config": self.config.to_dict(),
            "container_id": self.container_id,
            "worker_id": self.worker_id,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "current_stage": self.current_stage,
            "progress": self.progress
        }

        if self.result:
            data["result"] = self.result.to_dict()
        if self.scheduled_at:
            data["scheduled_at"] = self.scheduled_at.isoformat()
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.finished_at:
            data["finished_at"] = self.finished_at.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BuildTask':
        """从字典创建实例"""
        # 处理时间字段
        time_fields = ['created_at', 'scheduled_at', 'started_at', 'finished_at']
        for field in time_fields:
            if isinstance(data.get(field), str):
                data[field] = datetime.fromisoformat(data[field])

        # 处理嵌套对象
        if 'config' in data:
            data['config'] = BuildConfig.from_dict(data['config'])
        if 'result' in data and data['result']:
            data['result'] = BuildResult.from_dict(data['result'])

        return cls(**data)


@dataclass
class BuildEvent:
    """构建事件"""
    build_id: str                       # 构建ID
    event_type: str                     # 事件类型
    message: str                        # 事件消息
    timestamp: datetime = field(default_factory=datetime.now)
    level: str = "info"                 # 日志级别 (debug, info, warning, error)
    stage: Optional[str] = None         # 构建阶段
    details: Dict[str, Any] = field(default_factory=dict)  # 详细信息

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "build_id": self.build_id,
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "stage": self.stage,
            "details": self.details
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BuildEvent':
        """从字典创建实例"""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)