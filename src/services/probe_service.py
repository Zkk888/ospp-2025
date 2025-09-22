# 20. src/services/probe_service.py
"""
探针服务 - eulermaker-docker-optimizer的监控探针业务服务

******OSPP-2025-张金荣******

提供监控探针的高级业务逻辑封装，包括：
- 容器监控探针管理
- 系统性能监控
- 资源使用监控和告警
- 自定义监控指标
- 监控数据聚合和分析
- 告警规则管理和通知
- 监控调度和任务管理
- 监控数据历史存储
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable, Set, Union, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json
from collections import defaultdict, deque
import statistics
import time

from config.settings import get_docker_settings
from utils.logger import get_logger, LoggerMixin, log_performance, log_errors
from utils.exceptions import ProbeError, DockerError, ValidationError
from utils.helpers import (
    generate_uuid, format_timestamp, sanitize_name,
    format_size, format_duration, calculate_percentage
)
from models.probe_model import (
    ProbeConfig, ProbeType, ProbeStatus, ProbeData, AlertRule, AlertLevel,
    MonitoringTarget, MetricType, TimeSeriesData
)
from core.probe_manager import ProbeManager, ProbeEvent


class MonitoringInterval(Enum):
    """监控间隔"""
    REALTIME = 1        # 1秒
    FREQUENT = 5        # 5秒
    NORMAL = 15         # 15秒
    SLOW = 30           # 30秒
    PERIODIC = 60       # 1分钟
    HOURLY = 3600       # 1小时


class AlertSeverity(Enum):
    """告警严重级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AggregationType(Enum):
    """数据聚合类型"""
    AVERAGE = "average"
    SUM = "sum"
    MAX = "max"
    MIN = "min"
    COUNT = "count"
    PERCENTILE_95 = "p95"
    PERCENTILE_99 = "p99"


@dataclass
class MonitoringSchedule:
    """监控调度配置"""
    schedule_id: str
    target_id: str
    probe_configs: List[ProbeConfig]
    interval: MonitoringInterval
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    failure_count: int = 0

    def calculate_next_run(self) -> datetime:
        """计算下次运行时间"""
        if self.last_run:
            return self.last_run + timedelta(seconds=self.interval.value)
        return datetime.now() + timedelta(seconds=self.interval.value)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "schedule_id": self.schedule_id,
            "target_id": self.target_id,
            "probe_configs": [config.to_dict() for config in self.probe_configs],
            "interval": self.interval.value,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "failure_count": self.failure_count
        }


@dataclass
class AlertNotification:
    """告警通知"""
    notification_id: str
    alert_rule_id: str
    target_id: str
    severity: AlertSeverity
    message: str
    data: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    def acknowledge(self, user: str = "system"):
        """确认告警"""
        self.acknowledged = True
        self.acknowledged_at = datetime.now()
        self.acknowledged_by = user

    def resolve(self):
        """解决告警"""
        self.resolved = True
        self.resolved_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "notification_id": self.notification_id,
            "alert_rule_id": self.alert_rule_id,
            "target_id": self.target_id,
            "severity": self.severity.value,
            "message": self.message,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


@dataclass
class MetricHistory:
    """指标历史数据"""
    metric_name: str
    target_id: str
    data_points: deque = field(default_factory=lambda: deque(maxlen=1000))  # 最多保存1000个数据点

    def add_data_point(self, value: float, timestamp: datetime = None):
        """添加数据点"""
        if timestamp is None:
            timestamp = datetime.now()

        self.data_points.append({
            "value": value,
            "timestamp": timestamp
        })

    def get_recent_data(self, duration: timedelta) -> List[Dict[str, Any]]:
        """获取最近一段时间的数据"""
        cutoff_time = datetime.now() - duration
        return [
            point for point in self.data_points
            if point["timestamp"] >= cutoff_time
        ]

    def get_aggregated_value(self, aggregation: AggregationType,
                             duration: Optional[timedelta] = None) -> Optional[float]:
        """获取聚合值"""
        data_points = (
            self.get_recent_data(duration) if duration
            else list(self.data_points)
        )

        if not data_points:
            return None

        values = [point["value"] for point in data_points]

        if aggregation == AggregationType.AVERAGE:
            return statistics.mean(values)
        elif aggregation == AggregationType.SUM:
            return sum(values)
        elif aggregation == AggregationType.MAX:
            return max(values)
        elif aggregation == AggregationType.MIN:
            return min(values)
        elif aggregation == AggregationType.COUNT:
            return len(values)
        elif aggregation == AggregationType.PERCENTILE_95:
            return statistics.quantiles(values, n=20)[18] if len(values) >= 20 else statistics.median(values)
        elif aggregation == AggregationType.PERCENTILE_99:
            return statistics.quantiles(values, n=100)[98] if len(values) >= 100 else statistics.median(values)

        return None


class MonitoringScheduler:
    """监控调度器 - 管理监控任务的调度和执行"""

    def __init__(self, probe_manager: ProbeManager):
        self.probe_manager = probe_manager
        self.logger = get_logger(__name__)

        # 调度任务
        self._schedules: Dict[str, MonitoringSchedule] = {}
        self._scheduler_task: Optional[asyncio.Task] = None

        # 执行状态
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._is_running = False

    async def start(self):
        """启动调度器"""
        if self._is_running:
            return

        self._is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        self.logger.info("Monitoring scheduler started")

    async def stop(self):
        """停止调度器"""
        self._is_running = False

        # 停止调度任务
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # 停止所有执行中的任务
        for task in list(self._running_tasks.values()):
            task.cancel()

        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

        self._running_tasks.clear()
        self.logger.info("Monitoring scheduler stopped")

    def add_schedule(self, schedule: MonitoringSchedule):
        """添加监控调度"""
        schedule.next_run = schedule.calculate_next_run()
        self._schedules[schedule.schedule_id] = schedule

        self.logger.info(f"Added monitoring schedule: {schedule.schedule_id}")

    def remove_schedule(self, schedule_id: str) -> bool:
        """移除监控调度"""
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]

            # 取消正在执行的任务
            if schedule_id in self._running_tasks:
                self._running_tasks[schedule_id].cancel()
                del self._running_tasks[schedule_id]

            self.logger.info(f"Removed monitoring schedule: {schedule_id}")
            return True
        return False

    def get_schedule(self, schedule_id: str) -> Optional[MonitoringSchedule]:
        """获取监控调度"""
        return self._schedules.get(schedule_id)

    def list_schedules(self) -> List[MonitoringSchedule]:
        """列出所有监控调度"""
        return list(self._schedules.values())

    async def _scheduler_loop(self):
        """调度器主循环"""
        while self._is_running:
            try:
                current_time = datetime.now()

                # 检查需要执行的调度任务
                for schedule in list(self._schedules.values()):
                    if not schedule.enabled:
                        continue

                    if schedule.next_run and current_time >= schedule.next_run:
                        # 如果任务还在执行中，跳过这次调度
                        if schedule.schedule_id in self._running_tasks:
                            self.logger.warning(f"Schedule {schedule.schedule_id} still running, skipping")
                            continue

                        # 启动监控任务
                        task = asyncio.create_task(self._execute_schedule(schedule))
                        self._running_tasks[schedule.schedule_id] = task

                # 清理已完成的任务
                completed_tasks = []
                for schedule_id, task in self._running_tasks.items():
                    if task.done():
                        completed_tasks.append(schedule_id)

                for schedule_id in completed_tasks:
                    del self._running_tasks[schedule_id]

                await asyncio.sleep(1)  # 每秒检查一次

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {str(e)}")
                await asyncio.sleep(5)

    async def _execute_schedule(self, schedule: MonitoringSchedule):
        """执行监控调度"""
        try:
            self.logger.debug(f"Executing schedule: {schedule.schedule_id}")

            # 更新执行时间
            schedule.last_run = datetime.now()
            schedule.next_run = schedule.calculate_next_run()

            # 执行所有探针
            for probe_config in schedule.probe_configs:
                try:
                    await self.probe_manager.execute_probe(
                        schedule.target_id, probe_config
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to execute probe {probe_config.probe_type.value} "
                        f"for target {schedule.target_id}: {str(e)}"
                    )
                    schedule.failure_count += 1

            # 重置失败计数
            if schedule.failure_count > 0:
                schedule.failure_count = max(0, schedule.failure_count - 1)

        except Exception as e:
            self.logger.error(f"Failed to execute schedule {schedule.schedule_id}: {str(e)}")
            schedule.failure_count += 1

    def get_scheduler_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        return {
            "total_schedules": len(self._schedules),
            "enabled_schedules": len([s for s in self._schedules.values() if s.enabled]),
            "running_tasks": len(self._running_tasks),
            "is_running": self._is_running,
            "schedules": [schedule.to_dict() for schedule in self._schedules.values()]
        }


class AlertManager:
    """告警管理器 - 管理告警规则和通知"""

    def __init__(self):
        self.logger = get_logger(__name__)

        # 告警规则
        self._alert_rules: Dict[str, AlertRule] = {}

        # 告警通知
        self._notifications: List[AlertNotification] = []

        # 通知处理器
        self._notification_handlers: List[Callable] = []

        # 告警状态跟踪
        self._alert_states: Dict[str, Dict[str, Any]] = {}

    def add_alert_rule(self, rule: AlertRule):
        """添加告警规则"""
        self._alert_rules[rule.rule_id] = rule
        self.logger.info(f"Added alert rule: {rule.rule_id}")

    def remove_alert_rule(self, rule_id: str) -> bool:
        """移除告警规则"""
        if rule_id in self._alert_rules:
            del self._alert_rules[rule_id]

            # 清理相关状态
            self._alert_states.pop(rule_id, None)

            self.logger.info(f"Removed alert rule: {rule_id}")
            return True
        return False

    def get_alert_rule(self, rule_id: str) -> Optional[AlertRule]:
        """获取告警规则"""
        return self._alert_rules.get(rule_id)

    def list_alert_rules(self) -> List[AlertRule]:
        """列出所有告警规则"""
        return list(self._alert_rules.values())

    def add_notification_handler(self, handler: Callable):
        """添加通知处理器"""
        self._notification_handlers.append(handler)

    async def check_alerts(self, target_id: str, probe_data: ProbeData):
        """检查告警条件"""
        for rule in self._alert_rules.values():
            if not rule.enabled:
                continue

            # 检查目标是否匹配
            if rule.target_pattern and target_id not in rule.target_pattern:
                continue

            try:
                await self._evaluate_rule(rule, target_id, probe_data)
            except Exception as e:
                self.logger.error(f"Error evaluating alert rule {rule.rule_id}: {str(e)}")

    async def _evaluate_rule(self, rule: AlertRule, target_id: str, probe_data: ProbeData):
        """评估告警规则"""
        # 检查指标类型是否匹配
        if rule.metric_name != probe_data.metric_name:
            return

        rule_key = f"{rule.rule_id}:{target_id}"

        # 获取当前状态
        current_state = self._alert_states.get(rule_key, {
            "triggered": False,
            "trigger_count": 0,
            "last_trigger_time": None,
            "last_notification_time": None
        })

        # 评估条件
        triggered = self._evaluate_condition(rule, probe_data.value)

        if triggered:
            current_state["trigger_count"] += 1
            current_state["last_trigger_time"] = datetime.now()

            # 检查是否需要触发告警
            if (current_state["trigger_count"] >= rule.consecutive_count and
                    not current_state["triggered"]):

                current_state["triggered"] = True
                await self._trigger_alert(rule, target_id, probe_data, current_state)
        else:
            # 重置状态
            if current_state["triggered"]:
                current_state["triggered"] = False
                current_state["trigger_count"] = 0
                await self._resolve_alert(rule, target_id)

        # 更新状态
        self._alert_states[rule_key] = current_state

    def _evaluate_condition(self, rule: AlertRule, value: float) -> bool:
        """评估告警条件"""
        if rule.operator == "gt":
            return value > rule.threshold
        elif rule.operator == "lt":
            return value < rule.threshold
        elif rule.operator == "eq":
            return value == rule.threshold
        elif rule.operator == "gte":
            return value >= rule.threshold
        elif rule.operator == "lte":
            return value <= rule.threshold
        elif rule.operator == "ne":
            return value != rule.threshold

        return False

    async def _trigger_alert(self, rule: AlertRule, target_id: str,
                             probe_data: ProbeData, state: Dict[str, Any]):
        """触发告警"""
        notification = AlertNotification(
            notification_id=generate_uuid(),
            alert_rule_id=rule.rule_id,
            target_id=target_id,
            severity=AlertSeverity(rule.level.value),
            message=f"{rule.description}: {probe_data.metric_name}={probe_data.value}",
            data={
                "metric_name": probe_data.metric_name,
                "value": probe_data.value,
                "threshold": rule.threshold,
                "operator": rule.operator,
                "probe_data": probe_data.to_dict()
            }
        )

        self._notifications.append(notification)
        state["last_notification_time"] = datetime.now()

        # 调用通知处理器
        for handler in self._notification_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(notification)
                else:
                    handler(notification)
            except Exception as e:
                self.logger.error(f"Error in notification handler: {str(e)}")

        self.logger.warning(f"Alert triggered: {notification.message}")

    async def _resolve_alert(self, rule: AlertRule, target_id: str):
        """解决告警"""
        # 查找相关的未解决告警
        for notification in self._notifications:
            if (notification.alert_rule_id == rule.rule_id and
                    notification.target_id == target_id and
                    not notification.resolved):

                notification.resolve()
                self.logger.info(f"Alert resolved: {notification.message}")

    def get_active_notifications(self) -> List[AlertNotification]:
        """获取活跃的告警通知"""
        return [n for n in self._notifications if not n.resolved]

    def get_notification_history(self, limit: int = 100) -> List[AlertNotification]:
        """获取告警通知历史"""
        return self._notifications[-limit:]

    def acknowledge_notification(self, notification_id: str, user: str = "system") -> bool:
        """确认告警通知"""
        for notification in self._notifications:
            if notification.notification_id == notification_id:
                notification.acknowledge(user)
                return True
        return False

    def get_alert_stats(self) -> Dict[str, Any]:
        """获取告警统计信息"""
        active_notifications = self.get_active_notifications()

        severity_counts = defaultdict(int)
        for notification in active_notifications:
            severity_counts[notification.severity.value] += 1

        return {
            "total_rules": len(self._alert_rules),
            "enabled_rules": len([r for r in self._alert_rules.values() if r.enabled]),
            "total_notifications": len(self._notifications),
            "active_notifications": len(active_notifications),
            "severity_distribution": dict(severity_counts),
            "alert_states": len(self._alert_states)
        }


class ProbeService(LoggerMixin):
    """探针服务 - 提供高级监控探针管理功能"""

    def __init__(self, probe_manager: ProbeManager):
        super().__init__()
        self.probe_manager = probe_manager
        self.settings = get_docker_settings()

        # 监控调度器
        self.scheduler = MonitoringScheduler(probe_manager)

        # 告警管理器
        self.alert_manager = AlertManager()

        # 指标历史数据
        self._metric_histories: Dict[str, MetricHistory] = {}

        # 监控目标
        self._monitoring_targets: Dict[str, MonitoringTarget] = {}

        # 自定义探针配置
        self._custom_probes: Dict[str, ProbeConfig] = {}

        # 事件处理器
        self._event_handlers: Dict[str, List[Callable]] = {}

        # 统计信息
        self._stats = {
            "probes_executed": 0,
            "alerts_triggered": 0,
            "monitoring_targets": 0,
            "last_reset": datetime.now()
        }

        self._initialized = False

    async def initialize(self):
        """初始化探针服务"""
        try:
            # 注册探针事件监听器
            self.probe_manager.add_event_handler("all", self._handle_probe_event)

            # 启动监控调度器
            await self.scheduler.start()

            # 设置默认告警通知处理器
            self.alert_manager.add_notification_handler(self._default_notification_handler)

            # 加载默认监控配置
            await self._load_default_monitoring_configs()

            self._initialized = True
            self.logger.info("Probe service initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize probe service: {str(e)}")
            raise ProbeError(f"Probe service initialization failed: {str(e)}", cause=e)

    async def cleanup(self):
        """清理探针服务"""
        self._initialized = False

        # 停止监控调度器
        await self.scheduler.stop()

        self.logger.info("Probe service cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    async def is_healthy(self) -> bool:
        """检查服务健康状态"""
        if not self._initialized:
            return False

        try:
            return await self.probe_manager.is_healthy()
        except Exception:
            return False

    # ================== 监控目标管理 ==================

    async def add_monitoring_target(self, target: MonitoringTarget) -> str:
        """添加监控目标"""
        self._monitoring_targets[target.target_id] = target
        self._stats["monitoring_targets"] += 1

        self.logger.info(f"Added monitoring target: {target.target_id}")
        return target.target_id

    async def remove_monitoring_target(self, target_id: str) -> bool:
        """移除监控目标"""
        if target_id in self._monitoring_targets:
            del self._monitoring_targets[target_id]

            # 移除相关的监控调度
            schedules_to_remove = [
                schedule.schedule_id for schedule in self.scheduler.list_schedules()
                if schedule.target_id == target_id
            ]

            for schedule_id in schedules_to_remove:
                self.scheduler.remove_schedule(schedule_id)

            # 清理指标历史
            histories_to_remove = [
                key for key in self._metric_histories.keys()
                if key.startswith(f"{target_id}:")
            ]

            for key in histories_to_remove:
                del self._metric_histories[key]

            self._stats["monitoring_targets"] -= 1

            self.logger.info(f"Removed monitoring target: {target_id}")
            return True
        return False

    async def get_monitoring_target(self, target_id: str) -> Optional[MonitoringTarget]:
        """获取监控目标"""
        return self._monitoring_targets.get(target_id)

    async def list_monitoring_targets(self) -> List[MonitoringTarget]:
        """列出所有监控目标"""
        return list(self._monitoring_targets.values())

    # ================== 探针配置管理 ==================

    async def create_custom_probe(self, probe_config: ProbeConfig) -> str:
        """创建自定义探针配置"""
        probe_id = generate_uuid()
        probe_config.probe_id = probe_id

        self._custom_probes[probe_id] = probe_config

        self.logger.info(f"Created custom probe: {probe_id}")
        return probe_id

    async def get_custom_probe(self, probe_id: str) -> Optional[ProbeConfig]:
        """获取自定义探针配置"""
        return self._custom_probes.get(probe_id)

    async def list_custom_probes(self) -> List[ProbeConfig]:
        """列出所有自定义探针配置"""
        return list(self._custom_probes.values())

    async def delete_custom_probe(self, probe_id: str) -> bool:
        """删除自定义探针配置"""
        if probe_id in self._custom_probes:
            del self._custom_probes[probe_id]
            self.logger.info(f"Deleted custom probe: {probe_id}")
            return True
        return False

    # ================== 监控调度管理 ==================

    async def create_monitoring_schedule(self, target_id: str,
                                         probe_configs: List[ProbeConfig],
                                         interval: MonitoringInterval) -> str:
        """创建监控调度"""
        schedule_id = generate_uuid()

        schedule = MonitoringSchedule(
            schedule_id=schedule_id,
            target_id=target_id,
            probe_configs=probe_configs,
            interval=interval
        )

        self.scheduler.add_schedule(schedule)

        self.logger.info(f"Created monitoring schedule: {schedule_id}")
        return schedule_id

    async def update_monitoring_schedule(self, schedule_id: str,
                                         **kwargs) -> bool:
        """更新监控调度"""
        schedule = self.scheduler.get_schedule(schedule_id)
        if not schedule:
            return False

        # 更新配置
        for key, value in kwargs.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)

        # 重新计算下次运行时间
        if 'interval' in kwargs:
            schedule.next_run = schedule.calculate_next_run()

        self.logger.info(f"Updated monitoring schedule: {schedule_id}")
        return True

    async def delete_monitoring_schedule(self, schedule_id: str) -> bool:
        """删除监控调度"""
        return self.scheduler.remove_schedule(schedule_id)

    async def get_monitoring_schedule(self, schedule_id: str) -> Optional[MonitoringSchedule]:
        """获取监控调度"""
        return self.scheduler.get_schedule(schedule_id)

    async def list_monitoring_schedules(self) -> List[MonitoringSchedule]:
        """列出所有监控调度"""
        return self.scheduler.list_schedules()

    # ================== 告警管理 ==================

    async def create_alert_rule(self, rule: AlertRule) -> str:
        """创建告警规则"""
        self.alert_manager.add_alert_rule(rule)
        return rule.rule_id

    async def update_alert_rule(self, rule_id: str, **kwargs) -> bool:
        """更新告警规则"""
        rule = self.alert_manager.get_alert_rule(rule_id)
        if not rule:
            return False

        # 更新规则属性
        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        return True

    async def delete_alert_rule(self, rule_id: str) -> bool:
        """删除告警规则"""
        return self.alert_manager.remove_alert_rule(rule_id)

    async def get_alert_rule(self, rule_id: str) -> Optional[AlertRule]:
        """获取告警规则"""
        return self.alert_manager.get_alert_rule(rule_id)

    async def list_alert_rules(self) -> List[AlertRule]:
        """列出所有告警规则"""
        return self.alert_manager.list_alert_rules()

    async def get_active_alerts(self) -> List[AlertNotification]:
        """获取活跃告警"""
        return self.alert_manager.get_active_notifications()

    async def acknowledge_alert(self, notification_id: str, user: str = "system") -> bool:
        """确认告警"""
        return self.alert_manager.acknowledge_notification(notification_id, user)

    # ================== 指标数据管理 ==================

    async def get_metric_history(self, target_id: str, metric_name: str,
                                 duration: Optional[timedelta] = None) -> Optional[List[Dict[str, Any]]]:
        """获取指标历史数据"""
        history_key = f"{target_id}:{metric_name}"
        metric_history = self._metric_histories.get(history_key)

        if not metric_history:
            return None

        if duration:
            return metric_history.get_recent_data(duration)
        else:
            return list(metric_history.data_points)

    async def get_metric_aggregation(self, target_id: str, metric_name: str,
                                     aggregation: AggregationType,
                                     duration: Optional[timedelta] = None) -> Optional[float]:
        """获取指标聚合值"""
        history_key = f"{target_id}:{metric_name}"
        metric_history = self._metric_histories.get(history_key)

        if not metric_history:
            return None

        return metric_history.get_aggregated_value(aggregation, duration)

    async def get_target_metrics(self, target_id: str) -> Dict[str, Any]:
        """获取目标的所有指标"""
        metrics = {}

        for history_key, metric_history in self._metric_histories.items():
            if history_key.startswith(f"{target_id}:"):
                metric_name = history_key.split(":", 1)[1]

                # 获取最新值
                if metric_history.data_points:
                    latest_point = metric_history.data_points[-1]
                    metrics[metric_name] = {
                        "latest_value": latest_point["value"],
                        "latest_timestamp": latest_point["timestamp"].isoformat(),
                        "data_points_count": len(metric_history.data_points)
                    }

        return metrics

    # ================== 事件处理 ==================

    async def _handle_probe_event(self, event: ProbeEvent):
        """处理探针事件"""
        self.logger.debug(f"Handling probe event: {event.event_type} for {event.target_id}")

        # 如果是数据事件，保存历史数据
        if event.event_type == "data_collected" and event.data:
            await self._store_metric_data(event.target_id, event.data)

            # 检查告警条件
            await self.alert_manager.check_alerts(event.target_id, event.data)

        # 更新统计
        if event.event_type == "probe_executed":
            self._stats["probes_executed"] += 1

        # 调用事件处理器
        await self._emit_event("probe", event)

    async def _store_metric_data(self, target_id: str, probe_data: ProbeData):
        """存储指标数据"""
        history_key = f"{target_id}:{probe_data.metric_name}"

        if history_key not in self._metric_histories:
            self._metric_histories[history_key] = MetricHistory(
                metric_name=probe_data.metric_name,
                target_id=target_id
            )

        metric_history = self._metric_histories[history_key]
        metric_history.add_data_point(probe_data.value, probe_data.timestamp)

    async def _default_notification_handler(self, notification: AlertNotification):
        """默认告警通知处理器"""
        self.logger.warning(f"ALERT [{notification.severity.value.upper()}]: {notification.message}")
        self._stats["alerts_triggered"] += 1

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

    async def _load_default_monitoring_configs(self):
        """加载默认监控配置"""
        # 默认容器监控探针配置
        default_probes = [
            ProbeConfig(
                probe_id="cpu_usage",
                probe_type=ProbeType.SYSTEM_METRICS,
                enabled=True,
                config={"metric": "cpu_usage"}
            ),
            ProbeConfig(
                probe_id="memory_usage",
                probe_type=ProbeType.SYSTEM_METRICS,
                enabled=True,
                config={"metric": "memory_usage"}
            ),
            ProbeConfig(
                probe_id="disk_usage",
                probe_type=ProbeType.SYSTEM_METRICS,
                enabled=True,
                config={"metric": "disk_usage"}
            )
        ]

        # 默认告警规则
        default_rules = [
            AlertRule(
                rule_id="high_cpu_usage",
                description="CPU使用率过高",
                metric_name="cpu_usage",
                operator="gt",
                threshold=80.0,
                level=AlertLevel.WARNING,
                consecutive_count=3,
                enabled=True
            ),
            AlertRule(
                rule_id="high_memory_usage",
                description="内存使用率过高",
                metric_name="memory_usage",
                operator="gt",
                threshold=90.0,
                level=AlertLevel.ERROR,
                consecutive_count=2,
                enabled=True
            ),
            AlertRule(
                rule_id="critical_memory_usage",
                description="内存使用率严重过高",
                metric_name="memory_usage",
                operator="gt",
                threshold=95.0,
                level=AlertLevel.CRITICAL,
                consecutive_count=1,
                enabled=True
            )
        ]

        # 添加默认告警规则
        for rule in default_rules:
            self.alert_manager.add_alert_rule(rule)

        self.logger.info("Default monitoring configurations loaded")

    # ================== 统计和报告 ==================

    async def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        scheduler_stats = self.scheduler.get_scheduler_stats()
        alert_stats = self.alert_manager.get_alert_stats()

        return {
            "probes_executed": self._stats["probes_executed"],
            "alerts_triggered": self._stats["alerts_triggered"],
            "monitoring_targets": self._stats["monitoring_targets"],
            "custom_probes": len(self._custom_probes),
            "metric_histories": len(self._metric_histories),
            "scheduler": scheduler_stats,
            "alerts": alert_stats,
            "last_reset": self._stats["last_reset"].isoformat()
        }

    async def get_monitoring_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        active_alerts = await self.get_active_alerts()
        critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]

        return {
            "total_targets": len(self._monitoring_targets),
            "active_schedules": len([s for s in self.scheduler.list_schedules() if s.enabled]),
            "total_probes": len(self._custom_probes),
            "active_alerts": len(active_alerts),
            "critical_alerts": len(critical_alerts),
            "metric_histories": len(self._metric_histories),
            "service_healthy": await self.is_healthy()
        }

    async def export_monitoring_data(self, target_id: Optional[str] = None,
                                     start_time: Optional[datetime] = None,
                                     end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """导出监控数据"""
        export_data = {
            "export_time": datetime.now().isoformat(),
            "time_range": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None
            },
            "targets": {},
            "alerts": []
        }

        # 导出指标数据
        for history_key, metric_history in self._metric_histories.items():
            hist_target_id, metric_name = history_key.split(":", 1)

            # 过滤目标
            if target_id and hist_target_id != target_id:
                continue

            if hist_target_id not in export_data["targets"]:
                export_data["targets"][hist_target_id] = {}

            # 获取时间范围内的数据
            data_points = list(metric_history.data_points)
            if start_time or end_time:
                filtered_points = []
                for point in data_points:
                    if start_time and point["timestamp"] < start_time:
                        continue
                    if end_time and point["timestamp"] > end_time:
                        continue
                    filtered_points.append({
                        "value": point["value"],
                        "timestamp": point["timestamp"].isoformat()
                    })
                data_points = filtered_points
            else:
                data_points = [
                    {
                        "value": point["value"],
                        "timestamp": point["timestamp"].isoformat()
                    }
                    for point in data_points
                ]

            export_data["targets"][hist_target_id][metric_name] = data_points

        # 导出告警数据
        for notification in self._notifications:
            # 过滤时间范围
            if start_time and notification.created_at < start_time:
                continue
            if end_time and notification.created_at > end_time:
                continue

            # 过滤目标
            if target_id and notification.target_id != target_id:
                continue

            export_data["alerts"].append(notification.to_dict())

        return export_data