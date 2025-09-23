"""
******OSPP-2025-张金荣******

Eulermaker-docker-optimizer 的探针数据模型

此模块定义了用于监控和健康检查的数据模型，包括：
• 健康检查配置与结果
• 性能指标与监控
• 资源使用跟踪
• 告警规则与通知
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from enum import Enum
import json


class ProbeType(Enum):
    """探针类型枚举"""
    HEALTH = "health"           # 健康检查
    PERFORMANCE = "performance" # 性能监控
    RESOURCE = "resource"       # 资源监控
    LOG = "log"                # 日志监控
    NETWORK = "network"        # 网络监控
    CUSTOM = "custom"          # 自定义探针


class ProbeStatus(Enum):
    """探针状态枚举"""
    UNKNOWN = "unknown"         # 未知状态
    HEALTHY = "healthy"         # 健康
    WARNING = "warning"         # 警告
    CRITICAL = "critical"       # 严重
    FAILED = "failed"          # 失败
    DISABLED = "disabled"      # 已禁用

    def is_ok(self) -> bool:
        """判断状态是否正常"""
        return self in [self.HEALTHY, self.WARNING]

    def is_problem(self) -> bool:
        """判断是否有问题"""
        return self in [self.CRITICAL, self.FAILED]


@dataclass
class ProbeMetric:
    """探针指标"""
    name: str                           # 指标名称
    value: Union[int, float, str, bool] # 指标值
    unit: Optional[str] = None          # 单位
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)  # 标签

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProbeMetric':
        """从字典创建实例"""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class ResourceMetric:
    """资源指标"""
    # CPU指标
    cpu_usage_percent: float = 0.0      # CPU使用率 (%)
    cpu_load_1m: float = 0.0            # 1分钟负载
    cpu_load_5m: float = 0.0            # 5分钟负载
    cpu_load_15m: float = 0.0           # 15分钟负载

    # 内存指标
    memory_usage_bytes: int = 0         # 内存使用量 (字节)
    memory_total_bytes: int = 0         # 总内存 (字节)
    memory_usage_percent: float = 0.0   # 内存使用率 (%)
    memory_available_bytes: int = 0     # 可用内存 (字节)

    # 磁盘指标
    disk_usage_bytes: int = 0           # 磁盘使用量 (字节)
    disk_total_bytes: int = 0           # 总磁盘空间 (字节)
    disk_usage_percent: float = 0.0     # 磁盘使用率 (%)
    disk_available_bytes: int = 0       # 可用磁盘空间 (字节)

    # 网络指标
    network_rx_bytes: int = 0           # 网络接收字节数
    network_tx_bytes: int = 0           # 网络发送字节数
    network_rx_packets: int = 0         # 网络接收包数
    network_tx_packets: int = 0         # 网络发送包数

    # 进程指标
    processes_total: int = 0            # 总进程数
    processes_running: int = 0          # 运行中进程数
    processes_sleeping: int = 0         # 睡眠进程数

    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def memory_usage_mb(self) -> float:
        """内存使用量 (MB)"""
        return self.memory_usage_bytes / (1024 * 1024)

    @property
    def disk_usage_gb(self) -> float:
        """磁盘使用量 (GB)"""
        return self.disk_usage_bytes / (1024 * 1024 * 1024)

    def is_cpu_high(self, threshold: float = 80.0) -> bool:
        """判断CPU使用率是否过高"""
        return self.cpu_usage_percent > threshold

    def is_memory_high(self, threshold: float = 85.0) -> bool:
        """判断内存使用率是否过高"""
        return self.memory_usage_percent > threshold

    def is_disk_high(self, threshold: float = 90.0) -> bool:
        """判断磁盘使用率是否过高"""
        return self.disk_usage_percent > threshold

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "cpu_usage_percent": self.cpu_usage_percent,
            "cpu_load_1m": self.cpu_load_1m,
            "cpu_load_5m": self.cpu_load_5m,
            "cpu_load_15m": self.cpu_load_15m,
            "memory_usage_bytes": self.memory_usage_bytes,
            "memory_total_bytes": self.memory_total_bytes,
            "memory_usage_percent": self.memory_usage_percent,
            "memory_available_bytes": self.memory_available_bytes,
            "disk_usage_bytes": self.disk_usage_bytes,
            "disk_total_bytes": self.disk_total_bytes,
            "disk_usage_percent": self.disk_usage_percent,
            "disk_available_bytes": self.disk_available_bytes,
            "network_rx_bytes": self.network_rx_bytes,
            "network_tx_bytes": self.network_tx_bytes,
            "network_rx_packets": self.network_rx_packets,
            "network_tx_packets": self.network_tx_packets,
            "processes_total": self.processes_total,
            "processes_running": self.processes_running,
            "processes_sleeping": self.processes_sleeping,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceMetric':
        """从字典创建实例"""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class PerformanceMetric:
    """性能指标"""
    # 响应时间指标
    response_time_avg: float = 0.0      # 平均响应时间 (ms)
    response_time_p50: float = 0.0      # 50%响应时间 (ms)
    response_time_p95: float = 0.0      # 95%响应时间 (ms)
    response_time_p99: float = 0.0      # 99%响应时间 (ms)
    response_time_max: float = 0.0      # 最大响应时间 (ms)

    # 吞吐量指标
    requests_per_second: float = 0.0    # 每秒请求数
    requests_total: int = 0             # 总请求数
    requests_success: int = 0           # 成功请求数
    requests_error: int = 0             # 错误请求数

    # 错误率指标
    error_rate: float = 0.0             # 错误率 (%)
    success_rate: float = 0.0           # 成功率 (%)

    # 连接指标
    active_connections: int = 0         # 活跃连接数
    total_connections: int = 0          # 总连接数

    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """计算衍生指标"""
        if self.requests_total > 0:
            self.error_rate = (self.requests_error / self.requests_total) * 100
            self.success_rate = (self.requests_success / self.requests_total) * 100

    def is_performance_poor(self, response_time_threshold: float = 1000.0,
                            error_rate_threshold: float = 5.0) -> bool:
        """判断性能是否较差"""
        return (self.response_time_avg > response_time_threshold or
                self.error_rate > error_rate_threshold)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "response_time_avg": self.response_time_avg,
            "response_time_p50": self.response_time_p50,
            "response_time_p95": self.response_time_p95,
            "response_time_p99": self.response_time_p99,
            "response_time_max": self.response_time_max,
            "requests_per_second": self.requests_per_second,
            "requests_total": self.requests_total,
            "requests_success": self.requests_success,
            "requests_error": self.requests_error,
            "error_rate": self.error_rate,
            "success_rate": self.success_rate,
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerformanceMetric':
        """从字典创建实例"""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class HealthCheck:
    """健康检查"""
    name: str                           # 检查名称
    description: str                    # 检查描述
    command: Optional[str] = None       # 检查命令
    http_url: Optional[str] = None      # HTTP检查URL
    tcp_port: Optional[int] = None      # TCP端口检查

    # 检查配置
    interval: int = 30                  # 检查间隔 (秒)
    timeout: int = 10                   # 超时时间 (秒)
    retries: int = 3                    # 重试次数

    # 状态
    status: ProbeStatus = ProbeStatus.UNKNOWN
    last_check: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    failure_count: int = 0
    success_count: int = 0

    # 结果
    last_result: Optional[str] = None   # 最后检查结果
    last_error: Optional[str] = None    # 最后错误信息
    response_time: Optional[float] = None  # 响应时间 (ms)

    def update_result(self, success: bool, result: Optional[str] = None,
                      error: Optional[str] = None, response_time: Optional[float] = None):
        """更新检查结果"""
        self.last_check = datetime.now()
        self.last_result = result
        self.last_error = error
        self.response_time = response_time

        if success:
            self.last_success = self.last_check
            self.success_count += 1
            self.failure_count = 0  # 重置失败计数
            self.status = ProbeStatus.HEALTHY
        else:
            self.last_failure = self.last_check
            self.failure_count += 1

            # 根据失败次数设置状态
            if self.failure_count >= self.retries:
                self.status = ProbeStatus.CRITICAL
            else:
                self.status = ProbeStatus.WARNING

    def is_overdue(self) -> bool:
        """判断检查是否过期"""
        if not self.last_check:
            return True

        now = datetime.now()
        overdue_threshold = self.last_check + timedelta(seconds=self.interval * 2)
        return now > overdue_threshold

    def get_uptime_percentage(self, period_hours: int = 24) -> float:
        """获取指定时间段的可用率"""
        # 这里简化实现，实际应该查询历史记录
        if self.success_count == 0:
            return 0.0

        total_checks = self.success_count + self.failure_count
        if total_checks == 0:
            return 0.0

        return (self.success_count / total_checks) * 100

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "name": self.name,
            "description": self.description,
            "command": self.command,
            "http_url": self.http_url,
            "tcp_port": self.tcp_port,
            "interval": self.interval,
            "timeout": self.timeout,
            "retries": self.retries,
            "status": self.status.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "response_time": self.response_time
        }

        if self.last_check:
            data["last_check"] = self.last_check.isoformat()
        if self.last_success:
            data["last_success"] = self.last_success.isoformat()
        if self.last_failure:
            data["last_failure"] = self.last_failure.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HealthCheck':
        """从字典创建实例"""
        # 处理时间字段
        time_fields = ['last_check', 'last_success', 'last_failure']
        for field in time_fields:
            if isinstance(data.get(field), str):
                data[field] = datetime.fromisoformat(data[field])

        # 处理状态字段
        if isinstance(data.get('status'), str):
            data['status'] = ProbeStatus(data['status'])

        return cls(**data)


@dataclass
class ProbeConfig:
    """探针配置"""
    # 基本信息
    probe_id: str                       # 探针ID
    name: str                           # 探针名称
    type: ProbeType                     # 探针类型
    target: str                         # 监控目标 (容器ID/名称)
    description: str = ""               # 描述

    # 检查配置
    enabled: bool = True                # 是否启用
    interval: int = 30                  # 检查间隔 (秒)
    timeout: int = 10                   # 超时时间 (秒)

    # 健康检查配置
    health_checks: List[HealthCheck] = field(default_factory=list)

    # 阈值配置
    cpu_threshold: float = 80.0         # CPU阈值 (%)
    memory_threshold: float = 85.0      # 内存阈值 (%)
    disk_threshold: float = 90.0        # 磁盘阈值 (%)
    response_time_threshold: float = 1000.0  # 响应时间阈值 (ms)
    error_rate_threshold: float = 5.0   # 错误率阈值 (%)

    # 告警配置
    alert_enabled: bool = True          # 是否启用告警
    alert_cooldown: int = 300           # 告警冷却时间 (秒)
    notification_webhook: Optional[str] = None  # 通知webhook

    # 数据保留
    data_retention_days: int = 7        # 数据保留天数

    def add_health_check(self, health_check: HealthCheck):
        """添加健康检查"""
        self.health_checks.append(health_check)

    def get_enabled_health_checks(self) -> List[HealthCheck]:
        """获取启用的健康检查"""
        return [check for check in self.health_checks if check.status != ProbeStatus.DISABLED]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "probe_id": self.probe_id,
            "name": self.name,
            "type": self.type.value,
            "target": self.target,
            "description": self.description,
            "enabled": self.enabled,
            "interval": self.interval,
            "timeout": self.timeout,
            "health_checks": [check.to_dict() for check in self.health_checks],
            "cpu_threshold": self.cpu_threshold,
            "memory_threshold": self.memory_threshold,
            "disk_threshold": self.disk_threshold,
            "response_time_threshold": self.response_time_threshold,
            "error_rate_threshold": self.error_rate_threshold,
            "alert_enabled": self.alert_enabled,
            "alert_cooldown": self.alert_cooldown,
            "notification_webhook": self.notification_webhook,
            "data_retention_days": self.data_retention_days
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProbeConfig':
        """从字典创建实例"""
        # 处理类型字段
        if isinstance(data.get('type'), str):
            data['type'] = ProbeType(data['type'])

        # 处理健康检查列表
        if 'health_checks' in data:
            data['health_checks'] = [
                HealthCheck.from_dict(check) for check in data['health_checks']
            ]

        return cls(**data)


@dataclass
class ProbeResult:
    """探针检查结果"""
    probe_id: str                       # 探针ID
    target: str                         # 监控目标
    status: ProbeStatus                 # 状态
    message: str                        # 结果消息
    timestamp: datetime = field(default_factory=datetime.now)

    # 指标数据
    metrics: List[ProbeMetric] = field(default_factory=list)
    resource_metrics: Optional[ResourceMetric] = None
    performance_metrics: Optional[PerformanceMetric] = None

    # 健康检查结果
    health_check_results: Dict[str, bool] = field(default_factory=dict)

    # 执行信息
    execution_time: Optional[float] = None  # 执行时间 (ms)
    error_message: Optional[str] = None     # 错误消息

    def add_metric(self, name: str, value: Union[int, float, str, bool],
                   unit: Optional[str] = None, labels: Optional[Dict[str, str]] = None):
        """添加指标"""
        metric = ProbeMetric(
            name=name,
            value=value,
            unit=unit,
            labels=labels or {}
        )
        self.metrics.append(metric)

    def get_metric_value(self, name: str) -> Optional[Union[int, float, str, bool]]:
        """获取指标值"""
        for metric in self.metrics:
            if metric.name == name:
                return metric.value
        return None

    def is_healthy(self) -> bool:
        """判断是否健康"""
        return self.status.is_ok()

    def has_alerts(self) -> bool:
        """判断是否有告警"""
        return self.status.is_problem()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "probe_id": self.probe_id,
            "target": self.target,
            "status": self.status.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metrics": [metric.to_dict() for metric in self.metrics],
            "health_check_results": self.health_check_results,
            "execution_time": self.execution_time,
            "error_message": self.error_message
        }

        if self.resource_metrics:
            data["resource_metrics"] = self.resource_metrics.to_dict()
        if self.performance_metrics:
            data["performance_metrics"] = self.performance_metrics.to_dict()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProbeResult':
        """从字典创建实例"""
        # 处理时间字段
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])

        # 处理状态字段
        if isinstance(data.get('status'), str):
            data['status'] = ProbeStatus(data['status'])

        # 处理指标列表
        if 'metrics' in data:
            data['metrics'] = [
                ProbeMetric.from_dict(metric) for metric in data['metrics']
            ]

        # 处理嵌套对象
        if 'resource_metrics' in data and data['resource_metrics']:
            data['resource_metrics'] = ResourceMetric.from_dict(data['resource_metrics'])
        if 'performance_metrics' in data and data['performance_metrics']:
            data['performance_metrics'] = PerformanceMetric.from_dict(data['performance_metrics'])

        return cls(**data)


@dataclass
class AlertRule:
    """告警规则"""
    rule_id: str                        # 规则ID
    name: str                           # 规则名称
    description: str                    # 描述
    condition: str                      # 条件表达式
    threshold: float                    # 阈值
    operator: str = ">"                 # 操作符 (>, <, >=, <=, ==, !=)
    severity: str = "warning"           # 严重级别 (info, warning, critical)

    # 配置
    enabled: bool = True                # 是否启用
    cooldown: int = 300                 # 冷却时间 (秒)
    max_alerts: int = 10                # 最大告警次数

    # 通知配置
    notification_channels: List[str] = field(default_factory=list)  # 通知渠道

    # 状态
    last_triggered: Optional[datetime] = None  # 最后触发时间
    trigger_count: int = 0              # 触发次数

    def should_trigger(self, value: float) -> bool:
        """判断是否应该触发告警"""
        if not self.enabled:
            return False

        # 检查冷却时间
        if self.last_triggered:
            cooldown_until = self.last_triggered + timedelta(seconds=self.cooldown)
            if datetime.now() < cooldown_until:
                return False

        # 检查最大告警次数
        if self.trigger_count >= self.max_alerts:
            return False

        # 检查条件
        if self.operator == ">":
            return value > self.threshold
        elif self.operator == "<":
            return value < self.threshold
        elif self.operator == ">=":
            return value >= self.threshold
        elif self.operator == "<=":
            return value <= self.threshold
        elif self.operator == "==":
            return value == self.threshold
        elif self.operator == "!=":
            return value != self.threshold

        return False

    def trigger(self):
        """触发告警"""
        self.last_triggered = datetime.now()
        self.trigger_count += 1

    def reset(self):
        """重置告警状态"""
        self.trigger_count = 0
        self.last_triggered = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "condition": self.condition,
            "threshold": self.threshold,
            "operator": self.operator,
            "severity": self.severity,
            "enabled": self.enabled,
            "cooldown": self.cooldown,
            "max_alerts": self.max_alerts,
            "notification_channels": self.notification_channels,
            "trigger_count": self.trigger_count
        }

        if self.last_triggered:
            data["last_triggered"] = self.last_triggered.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlertRule':
        """从字典创建实例"""
        if isinstance(data.get('last_triggered'), str):
            data['last_triggered'] = datetime.fromisoformat(data['last_triggered'])

        return cls(**data)


@dataclass
class AlertEvent:
    """告警事件"""
    event_id: str                       # 事件ID
    rule_id: str                        # 规则ID
    rule_name: str                      # 规则名称
    target: str                         # 告警目标
    severity: str                       # 严重级别
    message: str                        # 告警消息
    value: float                        # 触发值
    threshold: float                    # 阈值
    timestamp: datetime = field(default_factory=datetime.now)

    # 状态
    status: str = "active"              # 状态 (active, resolved, acknowledged)
    resolved_at: Optional[datetime] = None  # 解决时间
    acknowledged_at: Optional[datetime] = None  # 确认时间
    acknowledged_by: Optional[str] = None      # 确认人

    # 详细信息
    details: Dict[str, Any] = field(default_factory=dict)  # 详细信息
    tags: List[str] = field(default_factory=list)          # 标签

    def acknowledge(self, user: str):
        """确认告警"""
        self.status = "acknowledged"
        self.acknowledged_at = datetime.now()
        self.acknowledged_by = user

    def resolve(self):
        """解决告警"""
        self.status = "resolved"
        self.resolved_at = datetime.now()

    def get_duration(self) -> Optional[timedelta]:
        """获取告警持续时间"""
        end_time = self.resolved_at or datetime.now()
        return end_time - self.timestamp

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "event_id": self.event_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "target": self.target,
            "severity": self.severity,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
            "acknowledged_by": self.acknowledged_by,
            "details": self.details,
            "tags": self.tags
        }

        if self.resolved_at:
            data["resolved_at"] = self.resolved_at.isoformat()
        if self.acknowledged_at:
            data["acknowledged_at"] = self.acknowledged_at.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlertEvent':
        """从字典创建实例"""
        # 处理时间字段
        time_fields = ['timestamp', 'resolved_at', 'acknowledged_at']
        for field in time_fields:
            if isinstance(data.get(field), str):
                data[field] = datetime.fromisoformat(data[field])

        return cls(**data)