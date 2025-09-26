"""
******OSPP-2025-张金荣******


Eulermaker-docker-optimizer 的全局设置

包含应用程序的所有配置设置，
包括 Docker 设置、服务器配置、构建设置等。
"""

import os
from typing import List, Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class DockerSettings:
    """Docker相关配置"""
    # Docker API连接设置
    base_url: str = "unix://var/run/docker.sock"  # Docker daemon socket
    api_version: str = "auto"  # Docker API版本
    timeout: int = 30  # 连接超时时间(秒)

    # 容器默认设置
    default_image: str = "openeuler/openeuler:latest"  # 默认基础镜像
    default_workdir: str = "/workspace"  # 默认工作目录
    default_shell: str = "/bin/bash"  # 默认shell

    # 资源限制
    memory_limit: str = "2g"  # 默认内存限制
    cpu_limit: str = "2"  # 默认CPU限制

    # 网络设置
    network_mode: str = "bridge"  # 网络模式

    # 存储设置
    volumes_base_path: str = "/tmp/eulermaker-volumes"  # 卷挂载基础路径


@dataclass
class ServerSettings:
    """服务器相关配置"""
    # HTTP服务器设置
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    # WebSocket设置
    ws_host: str = "0.0.0.0"
    ws_port: int = 8081

    # RPC服务器设置
    rpc_host: str = "0.0.0.0"
    rpc_port: int = 8082

    # CORS设置
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    cors_credentials: bool = True
    cors_methods: List[str] = field(default_factory=lambda: ["*"])
    cors_headers: List[str] = field(default_factory=lambda: ["*"])


@dataclass
class BuildSettings:
    """RPM构建相关配置"""
    # 构建环境设置
    build_base_image: str = "openeuler/openeuler:latest"  # RPM构建基础镜像
    build_tools_packages: List[str] = field(default_factory=lambda: [
        "rpm-build", "rpmdevtools", "gcc", "gcc-c++",
        "make", "automake", "autoconf", "libtool", "git"
    ])

    # 构建路径设置
    rpmbuild_base: str = "/root/rpmbuild"
    sources_dir: str = "/root/rpmbuild/SOURCES"
    specs_dir: str = "/root/rpmbuild/SPECS"
    rpms_dir: str = "/root/rpmbuild/RPMS"
    srpms_dir: str = "/root/rpmbuild/SRPMS"

    # 构建配置
    parallel_jobs: int = 2  # 并行编译任务数
    build_timeout: int = 3600  # 构建超时时间(秒)

    # 支持的架构
    supported_architectures: List[str] = field(default_factory=lambda: [
        "x86_64", "aarch64", "riscv64"
    ])


@dataclass
class ProbeSettings:
    """探针相关配置"""
    # 探针检测间隔
    health_check_interval: int = 30  # 健康检查间隔(秒)
    performance_check_interval: int = 10  # 性能检查间隔(秒)

    # 探针阈值
    cpu_threshold: float = 80.0  # CPU使用率阈值(%)
    memory_threshold: float = 85.0  # 内存使用率阈值(%)
    disk_threshold: float = 90.0  # 磁盘使用率阈值(%)

    # 探针存储
    metrics_retention_days: int = 7  # 指标保留天数

    # 告警设置
    alert_enabled: bool = True
    alert_cooldown: int = 300  # 告警冷却时间(秒)


@dataclass
class TerminalSettings:
    """终端相关配置"""
    # xterm.js设置
    terminal_rows: int = 24
    terminal_cols: int = 80
    terminal_scrollback: int = 1000

    # 终端会话设置
    session_timeout: int = 1800  # 会话超时时间(秒)
    max_sessions: int = 10  # 最大并发会话数

    # 终端主题
    terminal_theme: Dict[str, str] = field(default_factory=lambda: {
        "foreground": "#ffffff",
        "background": "#000000",
        "cursor": "#ffffff",
    })


@dataclass
class LoggingSettings:
    """日志相关配置"""
    # 日志级别
    log_level: str = "INFO"

    # 日志文件设置
    log_dir: str = "logs"
    log_file: str = "eulermaker.log"
    log_max_size: str = "100MB"
    log_backup_count: int = 5

    # 日志格式
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_date_format: str = "%Y-%m-%d %H:%M:%S"


@dataclass
class SecuritySettings:
    """安全相关配置"""
    # API密钥设置
    api_key_enabled: bool = False
    api_key: Optional[str] = None

    # JWT设置
    jwt_secret_key: str = "your-secret-key-change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    # 容器安全设置
    container_security_opt: List[str] = field(default_factory=lambda: [
        "no-new-privileges:true"
    ])
    container_read_only: bool = False


@dataclass
class Settings:
    """全局设置类，聚合所有配置"""
    # 基本信息
    app_name: str = "eulermaker-docker-optimizer"
    app_version: str = "1.0.0"
    environment: str = "development"  # development, production, testing

    # 各模块设置
    docker: DockerSettings = field(default_factory=DockerSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    build: BuildSettings = field(default_factory=BuildSettings)
    probe: ProbeSettings = field(default_factory=ProbeSettings)
    terminal: TerminalSettings = field(default_factory=TerminalSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)

    # 项目路径
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)

    def __post_init__(self):
        """初始化后的处理"""
        # 确保日志目录存在
        log_dir_path = self.project_root / self.logging.log_dir
        log_dir_path.mkdir(exist_ok=True)

        # 确保卷挂载目录存在
        volumes_path = Path(self.docker.volumes_base_path)
        volumes_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> 'Settings':
        """从环境变量创建设置"""
        settings = cls()

        # Docker设置
        if os.getenv("DOCKER_HOST"):
            settings.docker.base_url = os.getenv("DOCKER_HOST")

        # 服务器设置
        if os.getenv("SERVER_HOST"):
            settings.server.host = os.getenv("SERVER_HOST")
        if os.getenv("SERVER_PORT"):
            settings.server.port = int(os.getenv("SERVER_PORT"))
        if os.getenv("DEBUG"):
            settings.server.debug = os.getenv("DEBUG").lower() == "true"

        # 日志设置
        if os.getenv("LOG_LEVEL"):
            settings.logging.log_level = os.getenv("LOG_LEVEL")

        # 环境设置
        if os.getenv("ENVIRONMENT"):
            settings.environment = os.getenv("ENVIRONMENT")

        return settings

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {}
        for field_name, field_value in self.__dict__.items():
            if hasattr(field_value, '__dict__'):
                result[field_name] = field_value.__dict__
            else:
                result[field_name] = field_value
        return result


# 全局设置实例
_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局设置实例"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings.from_env()
    return _settings_instance


def update_settings(**kwargs) -> Settings:
    """更新设置"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings.from_env()

    for key, value in kwargs.items():
        if hasattr(_settings_instance, key):
            setattr(_settings_instance, key, value)

    return _settings_instance


# 常用设置别名
def get_docker_settings() -> DockerSettings:
    """获取Docker设置"""
    return get_settings().docker


def get_server_settings() -> ServerSettings:
    """获取服务器设置"""
    return get_settings().server


def get_build_settings() -> BuildSettings:
    """获取构建设置"""
    return get_settings().build


def get_probe_settings() -> ProbeSettings:
    """获取探针设置"""
    return get_settings().probe


def get_terminal_settings() -> TerminalSettings:
    """获取终端设置"""
    return get_settings().terminal


def get_logging_settings() -> LoggingSettings:
    """获取日志设置"""
    return get_settings().logging


def get_security_settings() -> SecuritySettings:
    """获取安全设置"""
    return get_settings().security