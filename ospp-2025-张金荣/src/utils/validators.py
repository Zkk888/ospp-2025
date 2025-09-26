"""
Eulermaker-docker-optimizer 的验证实用工具


******OSPP-2025-张金荣******

为整个应用程序中使用的各种数据类型和格式
提供了验证函数和类，包括：
• 容器名称和配置
• Docker 镜像名称
• 构建规范
• 网络配置
• 资源限制
"""

import re
import os
from typing import Any, Dict, List, Optional, Union, Tuple
from pathlib import Path

from .exceptions import ValidationError
from .helpers import parse_size


class BaseValidator:
    """基础验证器类"""

    def __init__(self, strict: bool = True):
        self.strict = strict

    def validate(self, value: Any, field_name: str = "value") -> Any:
        """
        验证值

        Args:
            value: 要验证的值
            field_name: 字段名称（用于错误消息）

        Returns:
            验证通过的值

        Raises:
            ValidationError: 验证失败时抛出
        """
        raise NotImplementedError("Subclasses must implement validate method")

    def _raise_error(self, message: str, field: str, value: Any, expected: str = None):
        """抛出验证错误"""
        raise ValidationError(
            message=message,
            field=field,
            value=value,
            expected=expected
        )


# Docker相关验证
def validate_container_name(name: str) -> str:
    """
    验证容器名称

    Docker容器名称规则：
    - 只能包含小写字母、数字、点号、连字符和下划线
    - 不能以点号或连字符开头
    - 长度不超过64个字符

    Args:
        name: 容器名称

    Returns:
        验证通过的容器名称

    Raises:
        ValidationError: 验证失败时抛出
    """
    if not isinstance(name, str):
        raise ValidationError("Container name must be a string", field="name", value=name)

    if not name:
        raise ValidationError("Container name cannot be empty", field="name", value=name)

    if len(name) > 64:
        raise ValidationError(
            "Container name cannot exceed 64 characters",
            field="name",
            value=name,
            expected="length <= 64"
        )

    # 检查字符规则
    pattern = r'^[a-z0-9._-]+$'
    if not re.match(pattern, name):
        raise ValidationError(
            "Container name can only contain lowercase letters, numbers, dots, hyphens and underscores",
            field="name",
            value=name,
            expected="lowercase alphanumeric with ._- allowed"
        )

    # 检查开头字符
    if name.startswith('.') or name.startswith('-'):
        raise ValidationError(
            "Container name cannot start with dot or hyphen",
            field="name",
            value=name,
            expected="cannot start with . or -"
        )

    return name


def validate_image_name(image: str) -> str:
    """
    验证Docker镜像名称

    Docker镜像名称格式：
    - [registry/]namespace/repository[:tag]
    - repository名称规则与容器名称类似

    Args:
        image: 镜像名称

    Returns:
        验证通过的镜像名称
    """
    if not isinstance(image, str):
        raise ValidationError("Image name must be a string", field="image", value=image)

    if not image:
        raise ValidationError("Image name cannot be empty", field="image", value=image)

    # 简单的镜像名称格式检查
    # 支持格式: repo:tag, registry/repo:tag, registry:port/repo:tag
    pattern = r'^(?:(?:[a-z0-9._-]+(?:\.[a-z0-9._-]+)*(?:[:/](?:\d+/)?)?)?[a-z0-9._-]+/)*[a-z0-9._-]+(?::[a-z0-9._-]+)?$'

    if not re.match(pattern, image, re.IGNORECASE):
        raise ValidationError(
            "Invalid image name format",
            field="image",
            value=image,
            expected="valid Docker image format"
        )

    return image


def validate_port(port: Union[int, str], field_name: str = "port") -> int:
    """
    验证端口号

    Args:
        port: 端口号
        field_name: 字段名称

    Returns:
        验证通过的端口号
    """
    try:
        port_int = int(port)
    except (ValueError, TypeError):
        raise ValidationError(
            "Port must be a valid integer",
            field=field_name,
            value=port,
            expected="integer"
        )

    if not (1 <= port_int <= 65535):
        raise ValidationError(
            "Port must be between 1 and 65535",
            field=field_name,
            value=port_int,
            expected="1-65535"
        )

    return port_int


def validate_memory_size(memory: str, field_name: str = "memory") -> str:
    """
    验证内存大小

    Args:
        memory: 内存大小字符串，如 "512MB", "2G"
        field_name: 字段名称

    Returns:
        验证通过的内存大小
    """
    if not isinstance(memory, str):
        raise ValidationError(
            "Memory size must be a string",
            field=field_name,
            value=memory,
            expected="string"
        )

    # 支持的内存单位
    pattern = r'^\d+(\.\d+)?[KMGT]?[Bb]?$'

    if not re.match(pattern, memory):
        raise ValidationError(
            "Invalid memory size format",
            field=field_name,
            value=memory,
            expected="format like '512MB', '2GB'"
        )

    # 尝试解析以确保有效
    try:
        parse_size(memory)
    except Exception as e:
        raise ValidationError(
            f"Invalid memory size: {str(e)}",
            field=field_name,
            value=memory
        )

    return memory


def validate_cpu_limit(cpu: Union[str, int, float], field_name: str = "cpu") -> str:
    """
    验证CPU限制

    Args:
        cpu: CPU限制，如 "0.5", "2", "1000m"
        field_name: 字段名称

    Returns:
        验证通过的CPU限制字符串
    """
    if isinstance(cpu, (int, float)):
        if cpu <= 0:
            raise ValidationError(
                "CPU limit must be positive",
                field=field_name,
                value=cpu,
                expected="positive number"
            )
        return str(cpu)

    if isinstance(cpu, str):
        # 支持 millicores 格式（如 "500m"）
        if cpu.endswith('m'):
            try:
                millicores = int(cpu[:-1])
                if millicores <= 0:
                    raise ValueError("Negative millicores")
                return cpu
            except ValueError:
                raise ValidationError(
                    "Invalid millicores format",
                    field=field_name,
                    value=cpu,
                    expected="positive integer with 'm' suffix"
                )

        # 支持浮点数格式
        try:
            cpu_float = float(cpu)
            if cpu_float <= 0:
                raise ValueError("Negative CPU")
            return cpu
        except ValueError:
            raise ValidationError(
                "Invalid CPU limit format",
                field=field_name,
                value=cpu,
                expected="number or millicores (e.g., '1000m')"
            )

    raise ValidationError(
        "CPU limit must be string, int, or float",
        field=field_name,
        value=cpu,
        expected="string, int, or float"
    )


def validate_environment_vars(env_vars: Dict[str, str], field_name: str = "environment") -> Dict[str, str]:
    """
    验证环境变量

    Args:
        env_vars: 环境变量字典
        field_name: 字段名称

    Returns:
        验证通过的环境变量字典
    """
    if not isinstance(env_vars, dict):
        raise ValidationError(
            "Environment variables must be a dictionary",
            field=field_name,
            value=type(env_vars).__name__,
            expected="dict"
        )

    validated_vars = {}

    for key, value in env_vars.items():
        # 验证键
        if not isinstance(key, str):
            raise ValidationError(
                f"Environment variable key must be string: {key}",
                field=f"{field_name}.{key}",
                value=type(key).__name__,
                expected="string"
            )

        if not key:
            raise ValidationError(
                "Environment variable key cannot be empty",
                field=f"{field_name}.{key}",
                value=key
            )

        # 验证环境变量名称格式
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', key):
            raise ValidationError(
                "Environment variable key must contain only uppercase letters, numbers and underscores, and start with letter or underscore",
                field=f"{field_name}.{key}",
                value=key,
                expected="uppercase letters, numbers, underscores"
            )

        # 验证值
        if not isinstance(value, str):
            value = str(value)

        validated_vars[key] = value

    return validated_vars


def validate_volume_mount(mount: str, field_name: str = "volume") -> Tuple[str, str, str]:
    """
    验证数据卷挂载配置

    Args:
        mount: 挂载字符串，格式为 "host_path:container_path[:mode]"
        field_name: 字段名称

    Returns:
        (host_path, container_path, mode) 元组
    """
    if not isinstance(mount, str):
        raise ValidationError(
            "Volume mount must be a string",
            field=field_name,
            value=type(mount).__name__,
            expected="string"
        )

    parts = mount.split(':')

    if len(parts) < 2 or len(parts) > 3:
        raise ValidationError(
            "Volume mount format should be 'host_path:container_path[:mode]'",
            field=field_name,
            value=mount,
            expected="host_path:container_path[:mode]"
        )

    host_path, container_path = parts[0], parts[1]
    mode = parts[2] if len(parts) == 3 else "rw"

    # 验证主机路径
    if not host_path:
        raise ValidationError(
            "Host path cannot be empty",
            field=f"{field_name}.host_path",
            value=host_path
        )

    # 验证容器路径
    if not container_path:
        raise ValidationError(
            "Container path cannot be empty",
            field=f"{field_name}.container_path",
            value=container_path
        )

    if not container_path.startswith('/'):
        raise ValidationError(
            "Container path must be absolute",
            field=f"{field_name}.container_path",
            value=container_path,
            expected="absolute path starting with /"
        )

    # 验证模式
    valid_modes = ['rw', 'ro', 'z', 'Z', 'shared', 'rshared', 'slave', 'rslave', 'private', 'rprivate']
    mode_parts = mode.split(',')

    for mode_part in mode_parts:
        if mode_part not in valid_modes:
            raise ValidationError(
                f"Invalid volume mode: {mode_part}",
                field=f"{field_name}.mode",
                value=mode_part,
                expected=f"one of {valid_modes}"
            )

    return host_path, container_path, mode


# 验证器类
class ContainerValidator(BaseValidator):
    """容器配置验证器"""

    def validate(self, config: Dict[str, Any], field_name: str = "container") -> Dict[str, Any]:
        """验证容器配置"""
        if not isinstance(config, dict):
            self._raise_error(
                "Container configuration must be a dictionary",
                field_name,
                type(config).__name__,
                "dict"
            )

        validated = {}

        # 验证必需字段
        if 'name' in config:
            validated['name'] = validate_container_name(config['name'])

        if 'image' in config:
            validated['image'] = validate_image_name(config['image'])

        # 验证可选字段
        if 'ports' in config:
            validated['ports'] = self._validate_ports(config['ports'])

        if 'environment' in config:
            validated['environment'] = validate_environment_vars(config['environment'])

        if 'volumes' in config:
            validated['volumes'] = self._validate_volumes(config['volumes'])

        if 'memory' in config:
            validated['memory'] = validate_memory_size(config['memory'])

        if 'cpu' in config:
            validated['cpu'] = validate_cpu_limit(config['cpu'])

        # 复制其他字段
        for key, value in config.items():
            if key not in validated:
                validated[key] = value

        return validated

    def _validate_ports(self, ports: Union[List, Dict]) -> Dict[str, int]:
        """验证端口配置"""
        if isinstance(ports, list):
            # 端口列表格式
            port_dict = {}
            for port in ports:
                if isinstance(port, str) and ':' in port:
                    host_port, container_port = port.split(':', 1)
                    port_dict[validate_port(container_port)] = validate_port(host_port)
                else:
                    port_num = validate_port(port)
                    port_dict[port_num] = port_num
            return port_dict

        elif isinstance(ports, dict):
            # 端口字典格式
            validated_ports = {}
            for container_port, host_port in ports.items():
                validated_ports[validate_port(container_port)] = validate_port(host_port)
            return validated_ports

        else:
            self._raise_error(
                "Ports must be list or dict",
                "ports",
                type(ports).__name__,
                "list or dict"
            )

    def _validate_volumes(self, volumes: List[str]) -> List[Tuple[str, str, str]]:
        """验证数据卷配置"""
        if not isinstance(volumes, list):
            self._raise_error(
                "Volumes must be a list",
                "volumes",
                type(volumes).__name__,
                "list"
            )

        validated_volumes = []
        for i, volume in enumerate(volumes):
            try:
                host_path, container_path, mode = validate_volume_mount(volume)
                validated_volumes.append((host_path, container_path, mode))
            except ValidationError as e:
                e.field = f"volumes[{i}]"
                raise

        return validated_volumes


class BuildValidator(BaseValidator):
    """构建配置验证器"""

    def validate(self, config: Dict[str, Any], field_name: str = "build") -> Dict[str, Any]:
        """验证构建配置"""
        if not isinstance(config, dict):
            self._raise_error(
                "Build configuration must be a dictionary",
                field_name,
                type(config).__name__,
                "dict"
            )

        validated = {}

        # 验证spec文件
        if 'spec_file' in config:
            spec_file = config['spec_file']
            if not isinstance(spec_file, str):
                self._raise_error(
                    "Spec file must be a string",
                    f"{field_name}.spec_file",
                    type(spec_file).__name__,
                    "string"
                )

            if not spec_file.endswith('.spec'):
                self._raise_error(
                    "Spec file must have .spec extension",
                    f"{field_name}.spec_file",
                    spec_file,
                    ".spec extension"
                )

            validated['spec_file'] = spec_file

        # 验证架构
        if 'architecture' in config:
            arch = config['architecture']
            valid_archs = ['x86_64', 'aarch64', 'riscv64', 'i386', 'armv7hl']

            if arch not in valid_archs:
                self._raise_error(
                    f"Unsupported architecture: {arch}",
                    f"{field_name}.architecture",
                    arch,
                    f"one of {valid_archs}"
                )

            validated['architecture'] = arch

        # 验证超时时间
        if 'timeout' in config:
            timeout = config['timeout']
            try:
                timeout_int = int(timeout)
                if timeout_int <= 0:
                    raise ValueError("Negative timeout")
                validated['timeout'] = timeout_int
            except (ValueError, TypeError):
                self._raise_error(
                    "Timeout must be a positive integer",
                    f"{field_name}.timeout",
                    timeout,
                    "positive integer"
                )

        # 验证并行任务数
        if 'parallel_jobs' in config:
            jobs = config['parallel_jobs']
            try:
                jobs_int = int(jobs)
                if jobs_int <= 0:
                    raise ValueError("Negative jobs")
                validated['parallel_jobs'] = jobs_int
            except (ValueError, TypeError):
                self._raise_error(
                    "Parallel jobs must be a positive integer",
                    f"{field_name}.parallel_jobs",
                    jobs,
                    "positive integer"
                )

        # 复制其他字段
        for key, value in config.items():
            if key not in validated:
                validated[key] = value

        return validated


class ProbeValidator(BaseValidator):
    """探针配置验证器"""

    def validate(self, config: Dict[str, Any], field_name: str = "probe") -> Dict[str, Any]:
        """验证探针配置"""
        if not isinstance(config, dict):
            self._raise_error(
                "Probe configuration must be a dictionary",
                field_name,
                type(config).__name__,
                "dict"
            )

        validated = {}

        # 验证探针类型
        if 'type' in config:
            probe_type = config['type']
            valid_types = ['health', 'performance', 'log', 'resource']

            if probe_type not in valid_types:
                self._raise_error(
                    f"Invalid probe type: {probe_type}",
                    f"{field_name}.type",
                    probe_type,
                    f"one of {valid_types}"
                )

            validated['type'] = probe_type

        # 验证间隔时间
        if 'interval' in config:
            interval = config['interval']
            try:
                interval_int = int(interval)
                if interval_int <= 0:
                    raise ValueError("Negative interval")
                validated['interval'] = interval_int
            except (ValueError, TypeError):
                self._raise_error(
                    "Interval must be a positive integer",
                    f"{field_name}.interval",
                    interval,
                    "positive integer (seconds)"
                )

        # 验证阈值
        if 'threshold' in config:
            threshold = config['threshold']
            try:
                threshold_float = float(threshold)
                if not (0 <= threshold_float <= 100):
                    raise ValueError("Threshold out of range")
                validated['threshold'] = threshold_float
            except (ValueError, TypeError):
                self._raise_error(
                    "Threshold must be a number between 0 and 100",
                    f"{field_name}.threshold",
                    threshold,
                    "0-100"
                )

        # 复制其他字段
        for key, value in config.items():
            if key not in validated:
                validated[key] = value

        return validated


# 便捷验证函数
def validate_required_fields(data: Dict[str, Any], required_fields: List[str], data_name: str = "data"):
    """验证必需字段"""
    missing_fields = []

    for field in required_fields:
        if field not in data or data[field] is None:
            missing_fields.append(field)

    if missing_fields:
        raise ValidationError(
            f"Missing required fields: {', '.join(missing_fields)}",
            field=data_name,
            value=missing_fields,
            expected=f"all required fields: {required_fields}"
        )


def validate_file_path(file_path: Union[str, Path], must_exist: bool = True, field_name: str = "file_path") -> Path:
    """验证文件路径"""
    if isinstance(file_path, str):
        path = Path(file_path)
    elif isinstance(file_path, Path):
        path = file_path
    else:
        raise ValidationError(
            "File path must be string or Path object",
            field=field_name,
            value=type(file_path).__name__,
            expected="string or Path"
        )

    if must_exist and not path.exists():
        raise ValidationError(
            f"File does not exist: {path}",
            field=field_name,
            value=str(path),
            expected="existing file"
        )

    return path


def validate_network_address(address: str, field_name: str = "address") -> str:
    """验证网络地址"""
    if not isinstance(address, str):
        raise ValidationError(
            "Network address must be a string",
            field=field_name,
            value=type(address).__name__,
            expected="string"
        )

    # 简单的IP地址或主机名验证
    # 支持IPv4、IPv6和主机名
    ipv4_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    hostname_pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$'

    if not (re.match(ipv4_pattern, address) or re.match(hostname_pattern, address) or address in ['localhost', '0.0.0.0']):
        raise ValidationError(
            "Invalid network address format",
            field=field_name,
            value=address,
            expected="valid IP address or hostname"
        )

    return address