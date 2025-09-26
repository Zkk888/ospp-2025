"""
******OSPP-2025-张金荣******

Eulermaker-docker-optimizer 的数据模型包

此软件包包含整个应用程序中使用的所有数据模型和模式：
• 用于 Docker 容器管理的容器模型
• 用于 RPM 构建任务的构建模型
• 用于监控和健康检查的探针模型
• 包含通用功能的基础模型
"""

from .container_model import (
    ContainerStatus,
    ContainerConfig,
    ContainerInfo,
    ContainerStats,
    ContainerEvent,
    PortMapping,
    VolumeMount,
    NetworkConfig,
    ResourceLimits,
)

from .build_model import (
    BuildStatus,
    BuildConfig,
    BuildTask,
    BuildResult,
    BuildEvent,
    BuildArtifact,
    BuildDependency,
    RPMSpec,
)

from .probe_model import (
    ProbeType,
    ProbeStatus,
    ProbeConfig,
    ProbeResult,
    ProbeMetric,
    HealthCheck,
    PerformanceMetric,
    ResourceMetric,
    AlertRule,
    AlertEvent,
)

# 版本信息
__version__ = "1.0.0"

# 导出所有模型类
__all__ = [
    # Container models
    "ContainerStatus",
    "ContainerConfig",
    "ContainerInfo",
    "ContainerStats",
    "ContainerEvent",
    "PortMapping",
    "VolumeMount",
    "NetworkConfig",
    "ResourceLimits",

    # Build models
    "BuildStatus",
    "BuildConfig",
    "BuildTask",
    "BuildResult",
    "BuildEvent",
    "BuildArtifact",
    "BuildDependency",
    "RPMSpec",

    # Probe models
    "ProbeType",
    "ProbeStatus",
    "ProbeConfig",
    "ProbeResult",
    "ProbeMetric",
    "HealthCheck",
    "PerformanceMetric",
    "ResourceMetric",
    "AlertRule",
    "AlertEvent",
]

# 模型注册表（用于序列化/反序列化）
MODEL_REGISTRY = {
    # Container models
    'ContainerConfig': ContainerConfig,
    'ContainerInfo': ContainerInfo,
    'ContainerStats': ContainerStats,
    'ContainerEvent': ContainerEvent,

    # Build models
    'BuildConfig': BuildConfig,
    'BuildTask': BuildTask,
    'BuildResult': BuildResult,
    'BuildEvent': BuildEvent,
    'BuildArtifact': BuildArtifact,

    # Probe models
    'ProbeConfig': ProbeConfig,
    'ProbeResult': ProbeResult,
    'ProbeMetric': ProbeMetric,
    'HealthCheck': HealthCheck,
    'PerformanceMetric': PerformanceMetric,
    'AlertEvent': AlertEvent,
}


def get_model_class(model_name: str):
    """
    根据模型名称获取模型类

    Args:
        model_name: 模型名称

    Returns:
        模型类

    Raises:
        KeyError: 如果模型不存在
    """
    if model_name not in MODEL_REGISTRY:
        raise KeyError(f"Unknown model: {model_name}")
    return MODEL_REGISTRY[model_name]


def serialize_model(model_instance) -> dict:
    """
    序列化模型实例为字典

    Args:
        model_instance: 模型实例

    Returns:
        序列化后的字典
    """
    if hasattr(model_instance, 'to_dict'):
        return {
            '_model_type': model_instance.__class__.__name__,
            **model_instance.to_dict()
        }
    elif hasattr(model_instance, '__dict__'):
        return {
            '_model_type': model_instance.__class__.__name__,
            **model_instance.__dict__
        }
    else:
        return {'_model_type': model_instance.__class__.__name__, 'value': model_instance}


def deserialize_model(data: dict):
    """
    从字典反序列化模型实例

    Args:
        data: 包含模型数据的字典

    Returns:
        模型实例
    """
    if not isinstance(data, dict) or '_model_type' not in data:
        return data

    model_type = data.pop('_model_type')
    model_class = get_model_class(model_type)

    if hasattr(model_class, 'from_dict'):
        return model_class.from_dict(data)
    else:
        return model_class(**data)