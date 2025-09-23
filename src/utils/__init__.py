"""
Eulermaker-docker-optimizer 实用工具包


******OSPP-2025-张金荣******

包含在整个应用程序中使用的实用函数和类，主要包括：
•   自定义异常
•   日志记录实用工具
•   辅助函数
•   验证器
"""

from .exceptions import (
    EulerMakerError,
    DockerError,
    ContainerError,
    BuildError,
    ProbeError,
    TerminalError,
    ValidationError,
    ConfigurationError,
)

from .logger import (
    get_logger,
    setup_logging,
    LoggerMixin,
)

from .helpers import (
    generate_uuid,
    format_timestamp,
    parse_timestamp,
    format_size,
    parse_size,
    safe_json_dumps,
    safe_json_loads,
    retry_async,
    timeout_async,
    ensure_path,
    cleanup_path,
)

from .validators import (
    validate_container_name,
    validate_image_name,
    validate_port,
    validate_memory_size,
    validate_cpu_limit,
    validate_environment_vars,
    validate_volume_mount,
    ContainerValidator,
    BuildValidator,
    ProbeValidator,
)

# 版本信息
__version__ = "1.0.0"

# 导出所有公共接口
__all__ = [
    # Exceptions
    "EulerMakerError",
    "DockerError",
    "ContainerError",
    "BuildError",
    "ProbeError",
    "TerminalError",
    "ValidationError",
    "ConfigurationError",

    # Logger
    "get_logger",
    "setup_logging",
    "LoggerMixin",

    # Helpers
    "generate_uuid",
    "format_timestamp",
    "parse_timestamp",
    "format_size",
    "parse_size",
    "safe_json_dumps",
    "safe_json_loads",
    "retry_async",
    "timeout_async",
    "ensure_path",
    "cleanup_path",

    # Validators
    "validate_container_name",
    "validate_image_name",
    "validate_port",
    "validate_memory_size",
    "validate_cpu_limit",
    "validate_environment_vars",
    "validate_volume_mount",
    "ContainerValidator",
    "BuildValidator",
    "ProbeValidator",
]