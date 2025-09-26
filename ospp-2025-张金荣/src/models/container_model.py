"""
******OSPP-2025-张金荣******

Eulermaker-docker-optimizer 的容器数据模型

此模块定义了用于 Docker 容器管理的数据模型，包括：
• 容器配置与状态
• 资源限制与统计
• 网络与存储卷配置
• 容器事件与生命周期跟踪
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum, IntEnum
import json


class ContainerStatus(Enum):
    """容器状态枚举"""
    CREATED = "created"      # 已创建但未启动
    RUNNING = "running"      # 运行中
    PAUSED = "paused"        # 暂停
    RESTARTING = "restarting"  # 重启中
    REMOVING = "removing"    # 删除中
    EXITED = "exited"        # 已退出
    DEAD = "dead"            # 死亡状态

    def is_active(self) -> bool:
        """判断容器是否处于活动状态"""
        return self in [self.RUNNING, self.PAUSED, self.RESTARTING]

    def is_stopped(self) -> bool:
        """判断容器是否已停止"""
        return self in [self.EXITED, self.DEAD]


@dataclass
class PortMapping:
    """端口映射配置"""
    container_port: int                    # 容器端口
    host_port: Optional[int] = None        # 主机端口
    protocol: str = "tcp"                  # 协议类型 (tcp/udp)
    host_ip: str = "0.0.0.0"              # 绑定的主机IP

    def __post_init__(self):
        if self.host_port is None:
            self.host_port = self.container_port

    def to_docker_format(self) -> str:
        """转换为Docker端口映射格式"""
        return f"{self.host_ip}:{self.host_port}:{self.container_port}/{self.protocol}"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "container_port": self.container_port,
            "host_port": self.host_port,
            "protocol": self.protocol,
            "host_ip": self.host_ip
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PortMapping':
        """从字典创建实例"""
        return cls(**data)


@dataclass
class VolumeMount:
    """数据卷挂载配置"""
    source: str                            # 源路径（主机路径或数据卷名称）
    target: str                            # 目标路径（容器内路径）
    type: str = "bind"                     # 挂载类型 (bind/volume/tmpfs)
    read_only: bool = False                # 是否只读
    bind_options: Optional[Dict[str, Any]] = None  # bind挂载选项
    volume_options: Optional[Dict[str, Any]] = None  # volume挂载选项
    tmpfs_options: Optional[Dict[str, Any]] = None  # tmpfs挂载选项

    def to_docker_format(self) -> Dict[str, Any]:
        """转换为Docker挂载格式"""
        mount_config = {
            "Target": self.target,
            "Source": self.source,
            "Type": self.type,
            "ReadOnly": self.read_only
        }

        if self.type == "bind" and self.bind_options:
            mount_config["BindOptions"] = self.bind_options
        elif self.type == "volume" and self.volume_options:
            mount_config["VolumeOptions"] = self.volume_options
        elif self.type == "tmpfs" and self.tmpfs_options:
            mount_config["TmpfsOptions"] = self.tmpfs_options

        return mount_config

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "read_only": self.read_only,
            "bind_options": self.bind_options,
            "volume_options": self.volume_options,
            "tmpfs_options": self.tmpfs_options
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VolumeMount':
        """从字典创建实例"""
        return cls(**data)


@dataclass
class ResourceLimits:
    """资源限制配置"""
    # 内存限制
    memory: Optional[str] = None           # 内存限制 (如 "512m", "1g")
    memory_swap: Optional[str] = None      # 内存+交换分区限制
    memory_reservation: Optional[str] = None  # 内存预留
    memory_swappiness: Optional[int] = None   # 交换分区使用倾向 (0-100)

    # CPU限制
    cpu_shares: Optional[int] = None       # CPU共享权重
    cpu_period: Optional[int] = None       # CPU调度周期
    cpu_quota: Optional[int] = None        # CPU配额
    cpuset_cpus: Optional[str] = None      # 允许使用的CPU核心
    cpuset_mems: Optional[str] = None      # 允许使用的内存节点

    # 其他资源限制
    pids_limit: Optional[int] = None       # 进程数限制
    ulimits: Optional[List[Dict[str, Any]]] = None  # ulimit配置

    def to_docker_format(self) -> Dict[str, Any]:
        """转换为Docker资源限制格式"""
        host_config = {}

        if self.memory:
            host_config["Memory"] = self._parse_memory_size(self.memory)
        if self.memory_swap:
            host_config["MemorySwap"] = self._parse_memory_size(self.memory_swap)
        if self.memory_reservation:
            host_config["MemoryReservation"] = self._parse_memory_size(self.memory_reservation)
        if self.memory_swappiness is not None:
            host_config["MemorySwappiness"] = self.memory_swappiness

        if self.cpu_shares:
            host_config["CpuShares"] = self.cpu_shares
        if self.cpu_period:
            host_config["CpuPeriod"] = self.cpu_period
        if self.cpu_quota:
            host_config["CpuQuota"] = self.cpu_quota
        if self.cpuset_cpus:
            host_config["CpusetCpus"] = self.cpuset_cpus
        if self.cpuset_mems:
            host_config["CpusetMems"] = self.cpuset_mems

        if self.pids_limit:
            host_config["PidsLimit"] = self.pids_limit
        if self.ulimits:
            host_config["Ulimits"] = self.ulimits

        return host_config

    def _parse_memory_size(self, size_str: str) -> int:
        """解析内存大小字符串为字节数"""
        size_str = size_str.upper().strip()
        multipliers = {
            'B': 1,
            'K': 1024,
            'KB': 1024,
            'M': 1024**2,
            'MB': 1024**2,
            'G': 1024**3,
            'GB': 1024**3,
            'T': 1024**4,
            'TB': 1024**4
        }

        for unit, multiplier in multipliers.items():
            if size_str.endswith(unit):
                size_num = float(size_str[:-len(unit)])
                return int(size_num * multiplier)

        return int(size_str)  # 假设是字节数

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "memory": self.memory,
            "memory_swap": self.memory_swap,
            "memory_reservation": self.memory_reservation,
            "memory_swappiness": self.memory_swappiness,
            "cpu_shares": self.cpu_shares,
            "cpu_period": self.cpu_period,
            "cpu_quota": self.cpu_quota,
            "cpuset_cpus": self.cpuset_cpus,
            "cpuset_mems": self.cpuset_mems,
            "pids_limit": self.pids_limit,
            "ulimits": self.ulimits
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceLimits':
        """从字典创建实例"""
        return cls(**data)


@dataclass
class NetworkConfig:
    """网络配置"""
    network_mode: str = "bridge"          # 网络模式
    networks: Optional[Dict[str, Any]] = None  # 网络配置
    hostname: Optional[str] = None         # 主机名
    domain_name: Optional[str] = None      # 域名
    dns: Optional[List[str]] = None        # DNS服务器
    dns_search: Optional[List[str]] = None # DNS搜索域
    extra_hosts: Optional[List[str]] = None # 额外的主机映射

    def to_docker_format(self) -> Dict[str, Any]:
        """转换为Docker网络配置格式"""
        config = {
            "NetworkMode": self.network_mode
        }

        if self.hostname:
            config["Hostname"] = self.hostname
        if self.domain_name:
            config["Domainname"] = self.domain_name
        if self.dns:
            config["Dns"] = self.dns
        if self.dns_search:
            config["DnsSearch"] = self.dns_search
        if self.extra_hosts:
            config["ExtraHosts"] = self.extra_hosts

        return config

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "network_mode": self.network_mode,
            "networks": self.networks,
            "hostname": self.hostname,
            "domain_name": self.domain_name,
            "dns": self.dns,
            "dns_search": self.dns_search,
            "extra_hosts": self.extra_hosts
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NetworkConfig':
        """从字典创建实例"""
        return cls(**data)


@dataclass
class ContainerConfig:
    """容器完整配置"""
    # 基本配置
    name: str                              # 容器名称
    image: str                             # 镜像名称
    command: Optional[List[str]] = None    # 启动命令
    entrypoint: Optional[List[str]] = None # 入口点
    working_dir: Optional[str] = None      # 工作目录
    environment: Optional[Dict[str, str]] = None  # 环境变量
    labels: Optional[Dict[str, str]] = None       # 标签

    # 网络和端口配置
    ports: List[PortMapping] = field(default_factory=list)  # 端口映射
    network: NetworkConfig = field(default_factory=NetworkConfig)  # 网络配置

    # 存储配置
    volumes: List[VolumeMount] = field(default_factory=list)  # 数据卷挂载

    # 资源限制
    resources: ResourceLimits = field(default_factory=ResourceLimits)  # 资源限制

    # 运行时配置
    privileged: bool = False               # 特权模式
    user: Optional[str] = None             # 运行用户
    restart_policy: str = "no"             # 重启策略
    auto_remove: bool = False              # 自动删除
    detach: bool = True                    # 后台运行
    stdin_open: bool = False               # 保持STDIN开启
    tty: bool = False                      # 分配伪TTY

    # 安全配置
    security_opt: List[str] = field(default_factory=list)  # 安全选项
    cap_add: List[str] = field(default_factory=list)       # 添加的权限
    cap_drop: List[str] = field(default_factory=list)      # 移除的权限

    def to_docker_config(self) -> Dict[str, Any]:
        """转换为Docker API配置格式"""
        # 容器配置
        container_config = {
            "Image": self.image,
            "Labels": self.labels or {},
            "Env": [f"{k}={v}" for k, v in (self.environment or {}).items()],
            "WorkingDir": self.working_dir,
            "OpenStdin": self.stdin_open,
            "Tty": self.tty
        }

        if self.command:
            container_config["Cmd"] = self.command
        if self.entrypoint:
            container_config["Entrypoint"] = self.entrypoint

        # 主机配置
        host_config = {
            "AutoRemove": self.auto_remove,
            "Privileged": self.privileged,
            "RestartPolicy": {"Name": self.restart_policy},
            "SecurityOpt": self.security_opt,
            "CapAdd": self.cap_add,
            "CapDrop": self.cap_drop
        }

        if self.user:
            host_config["User"] = self.user

        # 端口绑定
        if self.ports:
            port_bindings = {}
            exposed_ports = {}
            for port in self.ports:
                port_key = f"{port.container_port}/{port.protocol}"
                exposed_ports[port_key] = {}
                port_bindings[port_key] = [{
                    "HostIp": port.host_ip,
                    "HostPort": str(port.host_port)
                }]
            container_config["ExposedPorts"] = exposed_ports
            host_config["PortBindings"] = port_bindings

        # 数据卷挂载
        if self.volumes:
            mounts = []
            for volume in self.volumes:
                mounts.append(volume.to_docker_format())
            host_config["Mounts"] = mounts

        # 资源限制
        host_config.update(self.resources.to_docker_format())

        # 网络配置
        host_config.update(self.network.to_docker_format())

        return {
            "name": self.name,
            "config": container_config,
            "host_config": host_config
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "image": self.image,
            "command": self.command,
            "entrypoint": self.entrypoint,
            "working_dir": self.working_dir,
            "environment": self.environment,
            "labels": self.labels,
            "ports": [port.to_dict() for port in self.ports],
            "network": self.network.to_dict(),
            "volumes": [volume.to_dict() for volume in self.volumes],
            "resources": self.resources.to_dict(),
            "privileged": self.privileged,
            "user": self.user,
            "restart_policy": self.restart_policy,
            "auto_remove": self.auto_remove,
            "detach": self.detach,
            "stdin_open": self.stdin_open,
            "tty": self.tty,
            "security_opt": self.security_opt,
            "cap_add": self.cap_add,
            "cap_drop": self.cap_drop
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContainerConfig':
        """从字典创建实例"""
        # 处理嵌套对象
        if 'ports' in data:
            data['ports'] = [PortMapping.from_dict(port) for port in data['ports']]
        if 'network' in data:
            data['network'] = NetworkConfig.from_dict(data['network'])
        if 'volumes' in data:
            data['volumes'] = [VolumeMount.from_dict(volume) for volume in data['volumes']]
        if 'resources' in data:
            data['resources'] = ResourceLimits.from_dict(data['resources'])

        return cls(**data)


@dataclass
class ContainerStats:
    """容器统计信息"""
    # CPU统计
    cpu_usage: float = 0.0                 # CPU使用率 (%)
    cpu_usage_total: int = 0               # CPU总使用时间 (纳秒)
    cpu_system_usage: int = 0              # 系统CPU使用时间

    # 内存统计
    memory_usage: int = 0                  # 内存使用量 (字节)
    memory_limit: int = 0                  # 内存限制 (字节)
    memory_usage_percent: float = 0.0      # 内存使用率 (%)

    # 网络统计
    network_rx_bytes: int = 0              # 网络接收字节数
    network_tx_bytes: int = 0              # 网络发送字节数
    network_rx_packets: int = 0            # 网络接收包数
    network_tx_packets: int = 0            # 网络发送包数

    # 磁盘I/O统计
    block_read_bytes: int = 0              # 磁盘读取字节数
    block_write_bytes: int = 0             # 磁盘写入字节数

    # PIDs统计
    pids_current: int = 0                  # 当前进程数
    pids_limit: int = 0                    # 进程数限制

    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "cpu_usage": self.cpu_usage,
            "cpu_usage_total": self.cpu_usage_total,
            "cpu_system_usage": self.cpu_system_usage,
            "memory_usage": self.memory_usage,
            "memory_limit": self.memory_limit,
            "memory_usage_percent": self.memory_usage_percent,
            "network_rx_bytes": self.network_rx_bytes,
            "network_tx_bytes": self.network_tx_bytes,
            "network_rx_packets": self.network_rx_packets,
            "network_tx_packets": self.network_tx_packets,
            "block_read_bytes": self.block_read_bytes,
            "block_write_bytes": self.block_write_bytes,
            "pids_current": self.pids_current,
            "pids_limit": self.pids_limit,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContainerStats':
        """从字典创建实例"""
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class ContainerInfo:
    """容器信息"""
    # 基本信息
    id: str                                # 容器ID
    name: str                              # 容器名称
    image: str                             # 镜像名称
    image_id: str                          # 镜像ID
    status: ContainerStatus                # 容器状态
    state: str                             # 状态描述

    # 时间信息
    created_at: datetime                   # 创建时间
    started_at: Optional[datetime] = None  # 启动时间
    finished_at: Optional[datetime] = None # 结束时间

    # 配置信息
    config: Optional[ContainerConfig] = None  # 容器配置

    # 运行时信息
    exit_code: Optional[int] = None        # 退出码
    pid: Optional[int] = None              # 主进程PID

    # 网络信息
    ip_address: Optional[str] = None       # IP地址
    ports: Optional[Dict[str, Any]] = None # 端口映射信息

    # 资源使用
    stats: Optional[ContainerStats] = None # 统计信息

    def is_running(self) -> bool:
        """判断容器是否正在运行"""
        return self.status == ContainerStatus.RUNNING

    def is_healthy(self) -> bool:
        """判断容器是否健康"""
        return self.status.is_active() and self.exit_code != 0

    def get_uptime(self) -> Optional[float]:
        """获取运行时间（秒）"""
        if self.started_at and self.status == ContainerStatus.RUNNING:
            return (datetime.now() - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "id": self.id,
            "name": self.name,
            "image": self.image,
            "image_id": self.image_id,
            "status": self.status.value,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "exit_code": self.exit_code,
            "pid": self.pid,
            "ip_address": self.ip_address,
            "ports": self.ports
        }

        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.finished_at:
            data["finished_at"] = self.finished_at.isoformat()
        if self.config:
            data["config"] = self.config.to_dict()
        if self.stats:
            data["stats"] = self.stats.to_dict()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContainerInfo':
        """从字典创建实例"""
        # 处理时间字段
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('started_at'), str):
            data['started_at'] = datetime.fromisoformat(data['started_at'])
        if isinstance(data.get('finished_at'), str):
            data['finished_at'] = datetime.fromisoformat(data['finished_at'])

        # 处理状态字段
        if isinstance(data.get('status'), str):
            data['status'] = ContainerStatus(data['status'])

        # 处理嵌套对象
        if 'config' in data and data['config']:
            data['config'] = ContainerConfig.from_dict(data['config'])
        if 'stats' in data and data['stats']:
            data['stats'] = ContainerStats.from_dict(data['stats'])

        return cls(**data)


@dataclass
class ContainerEvent:
    """容器事件"""
    container_id: str                      # 容器ID
    container_name: str                    # 容器名称
    event_type: str                        # 事件类型 (start, stop, die, etc.)
    action: str                            # 动作描述
    timestamp: datetime                    # 事件时间
    actor: Dict[str, Any] = field(default_factory=dict)  # 事件执行者信息
    attributes: Dict[str, Any] = field(default_factory=dict)  # 事件属性

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "container_id": self.container_id,
            "container_name": self.container_name,
            "event_type": self.event_type,
            "action": self.action,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "attributes": self.attributes
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContainerEvent':
        """从字典创建实例"""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

    @classmethod
    def from_docker_event(cls, event: Dict[str, Any]) -> 'ContainerEvent':
        """从Docker事件创建实例"""
        return cls(
            container_id=event.get('Actor', {}).get('ID', ''),
            container_name=event.get('Actor', {}).get('Attributes', {}).get('name', ''),
            event_type=event.get('Type', ''),
            action=event.get('Action', ''),
            timestamp=datetime.fromtimestamp(event.get('time', 0)),
            actor=event.get('Actor', {}),
            attributes=event.get('Actor', {}).get('Attributes', {})
        )