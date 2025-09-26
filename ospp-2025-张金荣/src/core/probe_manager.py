"""
探针管理器 - eulermaker-docker-optimizer的监控和探针系统核心

******OSPP-2025-张金荣******

提供完整的容器监控和健康检查功能，包括：
- 多类型探针管理（健康、性能、资源、日志等）
- 实时指标收集和处理
- 告警规则管理和触发
- 监控数据存储和查询
- 自动化监控任务调度
- 探针扩展机制
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable, Set, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json
import psutil
import aiohttp
import socket
from abc import ABC, abstractmethod

from config.settings import get_probe_settings
from utils.logger import get_logger, LoggerMixin, log_performance, log_errors
from utils.exceptions import ProbeError, ContainerError
from utils.helpers import (
    generate_uuid, format_timestamp, retry_async, timeout_async,
    generate_short_uuid
)
from models.probe_model import (
    ProbeType, ProbeStatus, ProbeConfig, ProbeResult, ProbeMetric,
    HealthCheck, PerformanceMetric, ResourceMetric, AlertRule, AlertEvent
)
from models.container_model import ContainerInfo
from .docker_manager import DockerManager
from .container_lifecycle import ContainerLifecycleManager, LifecycleEvent


class ProbeExecutor(ABC):
    """探针执行器抽象基类"""

    def __init__(self, probe_config: ProbeConfig):
        self.config = probe_config
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def execute(self) -> ProbeResult:
        """执行探针检查"""
        pass

    @abstractmethod
    def get_probe_type(self) -> ProbeType:
        """获取探针类型"""
        pass


class HealthProbeExecutor(ProbeExecutor):
    """健康检查探针执行器"""

    def __init__(self, probe_config: ProbeConfig, docker_manager: DockerManager):
        super().__init__(probe_config)
        self.docker_manager = docker_manager

    def get_probe_type(self) -> ProbeType:
        return ProbeType.HEALTH

    async def execute(self) -> ProbeResult:
        """执行健康检查"""
        start_time = datetime.now()

        try:
            # 获取容器信息
            container_info = await self.docker_manager.get_container_info(self.config.target)

            # 执行健康检查
            health_results = {}
            overall_status = ProbeStatus.HEALTHY
            messages = []

            for health_check in self.config.health_checks:
                result = await self._execute_health_check(health_check, container_info)
                health_results[health_check.name] = result

                if not result:
                    overall_status = ProbeStatus.CRITICAL
                    messages.append(f"健康检查失败: {health_check.name}")

            if not health_results:
                # 默认健康检查：检查容器是否运行
                is_running = container_info.is_running()
                health_results["container_running"] = is_running

                if not is_running:
                    overall_status = ProbeStatus.CRITICAL
                    messages.append("容器未运行")

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            result = ProbeResult(
                probe_id=self.config.probe_id,
                target=self.config.target,
                status=overall_status,
                message="; ".join(messages) if messages else "所有健康检查通过",
                health_check_results=health_results,
                execution_time=execution_time
            )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return ProbeResult(
                probe_id=self.config.probe_id,
                target=self.config.target,
                status=ProbeStatus.FAILED,
                message=f"健康检查执行失败: {str(e)}",
                execution_time=execution_time,
                error_message=str(e)
            )

    async def _execute_health_check(self, health_check: HealthCheck,
                                    container_info: ContainerInfo) -> bool:
        """执行单个健康检查"""
        try:
            if health_check.command:
                return await self._check_command(health_check, container_info)
            elif health_check.http_url:
                return await self._check_http(health_check)
            elif health_check.tcp_port:
                return await self._check_tcp(health_check, container_info)
            else:
                # 默认检查：容器是否运行
                return container_info.is_running()

        except Exception as e:
            self.logger.debug(f"Health check {health_check.name} failed: {str(e)}")
            return False

    async def _check_command(self, health_check: HealthCheck,
                             container_info: ContainerInfo) -> bool:
        """执行命令健康检查"""
        try:
            result = await self.docker_manager.execute_command(
                container_info.id,
                health_check.command,
                stream=False
            )

            return result.get("exit_code", 1) == 0

        except Exception:
            return False

    @timeout_async(30.0)
    async def _check_http(self, health_check: HealthCheck) -> bool:
        """执行HTTP健康检查"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        health_check.http_url,
                        timeout=aiohttp.ClientTimeout(total=health_check.timeout)
                ) as response:
                    return 200 <= response.status < 400

        except Exception:
            return False

    async def _check_tcp(self, health_check: HealthCheck,
                         container_info: ContainerInfo) -> bool:
        """执行TCP端口检查"""
        try:
            host = container_info.ip_address or "localhost"
            port = health_check.tcp_port

            # 创建TCP连接测试
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=health_check.timeout
            )

            writer.close()
            await writer.wait_closed()
            return True

        except Exception:
            return False


class ResourceProbeExecutor(ProbeExecutor):
    """资源监控探针执行器"""

    def __init__(self, probe_config: ProbeConfig, docker_manager: DockerManager):
        super().__init__(probe_config)
        self.docker_manager = docker_manager

    def get_probe_type(self) -> ProbeType:
        return ProbeType.RESOURCE

    async def execute(self) -> ProbeResult:
        """执行资源监控"""
        start_time = datetime.now()

        try:
            # 获取容器统计信息
            container_stats = await self.docker_manager.get_container_stats(self.config.target)

            # 获取系统资源信息
            system_metrics = await self._get_system_metrics()

            # 构建资源指标
            resource_metrics = ResourceMetric(
                cpu_usage_percent=container_stats.cpu_usage,
                cpu_load_1m=system_metrics.get("load_1m", 0.0),
                cpu_load_5m=system_metrics.get("load_5m", 0.0),
                cpu_load_15m=system_metrics.get("load_15m", 0.0),
                memory_usage_bytes=container_stats.memory_usage,
                memory_total_bytes=container_stats.memory_limit,
                memory_usage_percent=container_stats.memory_usage_percent,
                memory_available_bytes=container_stats.memory_limit - container_stats.memory_usage,
                network_rx_bytes=container_stats.network_rx_bytes,
                network_tx_bytes=container_stats.network_tx_bytes,
                network_rx_packets=container_stats.network_rx_packets,
                network_tx_packets=container_stats.network_tx_packets,
                processes_total=system_metrics.get("processes_total", 0),
                processes_running=system_metrics.get("processes_running", 0),
                processes_sleeping=system_metrics.get("processes_sleeping", 0)
            )

            # 检查阈值
            status = ProbeStatus.HEALTHY
            messages = []

            if resource_metrics.is_cpu_high(self.config.cpu_threshold):
                status = ProbeStatus.WARNING
                messages.append(f"CPU使用率过高: {resource_metrics.cpu_usage_percent:.1f}%")

            if resource_metrics.is_memory_high(self.config.memory_threshold):
                status = ProbeStatus.WARNING
                messages.append(f"内存使用率过高: {resource_metrics.memory_usage_percent:.1f}%")

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            result = ProbeResult(
                probe_id=self.config.probe_id,
                target=self.config.target,
                status=status,
                message="; ".join(messages) if messages else "资源使用正常",
                resource_metrics=resource_metrics,
                execution_time=execution_time
            )

            # 添加详细指标
            result.add_metric("cpu_usage_percent", resource_metrics.cpu_usage_percent, "%")
            result.add_metric("memory_usage_percent", resource_metrics.memory_usage_percent, "%")
            result.add_metric("memory_usage_mb", resource_metrics.memory_usage_mb, "MB")
            result.add_metric("network_rx_bytes", resource_metrics.network_rx_bytes, "bytes")
            result.add_metric("network_tx_bytes", resource_metrics.network_tx_bytes, "bytes")

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return ProbeResult(
                probe_id=self.config.probe_id,
                target=self.config.target,
                status=ProbeStatus.FAILED,
                message=f"资源监控执行失败: {str(e)}",
                execution_time=execution_time,
                error_message=str(e)
            )

    async def _get_system_metrics(self) -> Dict[str, float]:
        """获取系统指标"""
        try:
            # 获取系统负载
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)

            # 获取进程信息
            processes = list(psutil.process_iter())
            processes_total = len(processes)
            processes_running = len([p for p in processes if p.status() == psutil.STATUS_RUNNING])
            processes_sleeping = len([p for p in processes if p.status() == psutil.STATUS_SLEEPING])

            return {
                "load_1m": load_avg[0],
                "load_5m": load_avg[1],
                "load_15m": load_avg[2],
                "processes_total": processes_total,
                "processes_running": processes_running,
                "processes_sleeping": processes_sleeping
            }
        except Exception as e:\
            self.logger.debug(f"Failed to get system metrics: {str(e)}")
        return {}


class PerformanceProbeExecutor(ProbeExecutor):
    """性能监控探针执行器"""

    def __init__(self, probe_config: ProbeConfig, docker_manager: DockerManager):
        super().__init__(probe_config)
        self.docker_manager = docker_manager
        self._request_history = []  # 请求历史记录

    def get_probe_type(self) -> ProbeType:
        return ProbeType.PERFORMANCE

    async def execute(self) -> ProbeResult:
        """执行性能监控"""
        start_time = datetime.now()

        try:
            # 获取容器信息
            container_info = await self.docker_manager.get_container_info(self.config.target)

            # 执行性能测试
            performance_metrics = await self._measure_performance(container_info)

            # 检查性能阈值
            status = ProbeStatus.HEALTHY
            messages = []

            if performance_metrics.is_performance_poor(
                    self.config.response_time_threshold,
                    self.config.error_rate_threshold
            ):
                status = ProbeStatus.WARNING
                messages.append(
                    f"性能指标异常: 响应时间={performance_metrics.response_time_avg:.1f}ms, "
                    f"错误率={performance_metrics.error_rate:.1f}%"
                )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            result = ProbeResult(
                probe_id=self.config.probe_id,
                target=self.config.target,
                status=status,
                message="; ".join(messages) if messages else "性能指标正常",
                performance_metrics=performance_metrics,
                execution_time=execution_time
            )

            # 添加性能指标
            result.add_metric("response_time_avg", performance_metrics.response_time_avg, "ms")
            result.add_metric("requests_per_second", performance_metrics.requests_per_second, "req/s")
            result.add_metric("error_rate", performance_metrics.error_rate, "%")
            result.add_metric("active_connections", performance_metrics.active_connections, "connections")

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return ProbeResult(
                probe_id=self.config.probe_id,
                target=self.config.target,
                status=ProbeStatus.FAILED,
                message=f"性能监控执行失败: {str(e)}",
                execution_time=execution_time,
                error_message=str(e)
            )

    async def _measure_performance(self, container_info: ContainerInfo) -> PerformanceMetric:
        """测量性能指标"""
        # 这里实现简化的性能测量逻辑
        # 实际项目中可能需要更复杂的性能测试

        current_time = datetime.now()

        # 清理过期的历史记录（保留最近5分钟的数据）
        cutoff_time = current_time - timedelta(minutes=5)
        self._request_history = [
            req for req in self._request_history
            if req.get("timestamp", current_time) > cutoff_time
        ]

        # 模拟性能数据收集
        total_requests = len(self._request_history)
        success_requests = len([req for req in self._request_history if req.get("success", True)])
        error_requests = total_requests - success_requests

        # 计算平均响应时间
        response_times = [req.get("response_time", 0) for req in self._request_history]
        response_time_avg = sum(response_times) / len(response_times) if response_times else 0

        # 计算请求速率
        if total_requests > 0 and self._request_history:
            time_span = (current_time - self._request_history[0].get("timestamp", current_time)).total_seconds()
            requests_per_second = total_requests / max(time_span, 1)
        else:
            requests_per_second = 0

        return PerformanceMetric(
            response_time_avg=response_time_avg,
            response_time_p50=response_time_avg,  # 简化实现
            response_time_p95=response_time_avg * 1.5,  # 简化实现
            response_time_p99=response_time_avg * 2.0,  # 简化实现
            response_time_max=max(response_times) if response_times else 0,
            requests_per_second=requests_per_second,
            requests_total=total_requests,
            requests_success=success_requests,
            requests_error=error_requests,
            active_connections=0,  # 需要从容器中获取
            total_connections=total_requests
        )


class LogProbeExecutor(ProbeExecutor):
    """日志监控探针执行器"""

    def __init__(self, probe_config: ProbeConfig, docker_manager: DockerManager):
        super().__init__(probe_config)
        self.docker_manager = docker_manager
        self._log_patterns = [
            {"pattern": "ERROR", "level": "error"},
            {"pattern": "WARN", "level": "warning"},
            {"pattern": "FATAL", "level": "critical"},
            {"pattern": "Exception", "level": "error"},
        ]

    def get_probe_type(self) -> ProbeType:
        return ProbeType.LOG

    async def execute(self) -> ProbeResult:
        """执行日志监控"""
        start_time = datetime.now()

        try:
            # 获取最近的容器日志
            logs = await self.docker_manager.get_container_logs(
                self.config.target,
                tail=100,
                since=(datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            )

            # 分析日志内容
            log_analysis = self._analyze_logs(logs)

            # 根据日志分析结果确定状态
            status = ProbeStatus.HEALTHY
            messages = []

            if log_analysis["critical_count"] > 0:
                status = ProbeStatus.CRITICAL
                messages.append(f"发现 {log_analysis['critical_count']} 条严重错误日志")
            elif log_analysis["error_count"] > 10:
                status = ProbeStatus.WARNING
                messages.append(f"发现 {log_analysis['error_count']} 条错误日志")
            elif log_analysis["warning_count"] > 20:
                status = ProbeStatus.WARNING
                messages.append(f"发现 {log_analysis['warning_count']} 条警告日志")

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            result = ProbeResult(
                probe_id=self.config.probe_id,
                target=self.config.target,
                status=status,
                message="; ".join(messages) if messages else "日志检查正常",
                execution_time=execution_time
            )

            # 添加日志分析指标
            result.add_metric("total_lines", log_analysis["total_lines"], "lines")
            result.add_metric("error_count", log_analysis["error_count"], "count")
            result.add_metric("warning_count", log_analysis["warning_count"], "count")
            result.add_metric("critical_count", log_analysis["critical_count"], "count")

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return ProbeResult(
                probe_id=self.config.probe_id,
                target=self.config.target,
                status=ProbeStatus.FAILED,
                message=f"日志监控执行失败: {str(e)}",
                execution_time=execution_time,
                error_message=str(e)
            )

    def _analyze_logs(self, logs: str) -> Dict[str, int]:
        """分析日志内容"""
        lines = logs.split('\n')
        analysis = {
            "total_lines": len(lines),
            "error_count": 0,
            "warning_count": 0,
            "critical_count": 0
        }

        for line in lines:
            line_upper = line.upper()

            for pattern in self._log_patterns:
                if pattern["pattern"] in line_upper:
                    level = pattern["level"]
                    if level == "critical":
                        analysis["critical_count"] += 1
                    elif level == "error":
                        analysis["error_count"] += 1
                    elif level == "warning":
                        analysis["warning_count"] += 1
                    break  # 只匹配第一个模式

        return analysis


class MonitoringService(LoggerMixin):
    """监控服务 - 管理所有监控任务"""

    def __init__(self, docker_manager: DockerManager,
                 container_manager: Optional[ContainerLifecycleManager] = None):
        super().__init__()
        self.docker_manager = docker_manager
        self.container_manager = container_manager
        self.settings = get_probe_settings()

        self._probe_configs: Dict[str, ProbeConfig] = {}
        self._probe_tasks: Dict[str, asyncio.Task] = {}
        self._probe_results: Dict[str, List[ProbeResult]] = {}  # 历史结果
        self._alert_rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, AlertEvent] = {}

        # 探针执行器工厂
        self._executor_classes = {
            ProbeType.HEALTH: HealthProbeExecutor,
            ProbeType.RESOURCE: ResourceProbeExecutor,
            ProbeType.PERFORMANCE: PerformanceProbeExecutor,
            ProbeType.LOG: LogProbeExecutor,
        }

        self._initialized = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """初始化监控服务"""
        try:
            # 注册容器生命周期事件监听器
            if self.container_manager:
                self.container_manager.add_event_handler("all", self._handle_container_event)

            # 启动数据清理任务
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            self._initialized = True
            self.logger.info("Monitoring service initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize monitoring service: {str(e)}")
            raise ProbeError(f"Monitoring service initialization failed: {str(e)}", cause=e)

    async def cleanup(self):
        """清理监控服务"""
        self._initialized = False

        # 停止所有探针任务
        for probe_id in list(self._probe_tasks.keys()):
            await self.stop_probe(probe_id)

        # 停止清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Monitoring service cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    # ================== 探针管理 ==================

    async def add_probe(self, probe_config: ProbeConfig) -> bool:
        """添加探针"""
        try:
            # 验证探针配置
            await self._validate_probe_config(probe_config)

            # 存储探针配置
            self._probe_configs[probe_config.probe_id] = probe_config

            # 如果启用，立即启动探针
            if probe_config.enabled:
                await self.start_probe(probe_config.probe_id)

            self.logger.info(f"Probe added: {probe_config.name} ({probe_config.probe_id})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add probe: {str(e)}")
            raise ProbeError(f"Failed to add probe: {str(e)}", cause=e)

    async def remove_probe(self, probe_id: str) -> bool:
        """移除探针"""
        try:
            # 停止探针任务
            await self.stop_probe(probe_id)

            # 移除配置和历史数据
            self._probe_configs.pop(probe_id, None)
            self._probe_results.pop(probe_id, None)

            self.logger.info(f"Probe removed: {probe_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to remove probe: {str(e)}")
            return False

    async def start_probe(self, probe_id: str) -> bool:
        """启动探针"""
        try:
            probe_config = self._probe_configs.get(probe_id)
            if not probe_config:
                raise ProbeError(f"Probe not found: {probe_id}")

            if not probe_config.enabled:
                raise ProbeError(f"Probe is disabled: {probe_id}")

            # 如果已经在运行，先停止
            if probe_id in self._probe_tasks:
                await self.stop_probe(probe_id)

            # 创建并启动探针任务
            task = asyncio.create_task(self._probe_loop(probe_config))
            self._probe_tasks[probe_id] = task

            self.logger.info(f"Probe started: {probe_config.name} ({probe_id})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start probe {probe_id}: {str(e)}")
            raise ProbeError(f"Failed to start probe: {str(e)}", probe_type=probe_id, cause=e)

    async def stop_probe(self, probe_id: str) -> bool:
        """停止探针"""
        try:
            if probe_id in self._probe_tasks:
                task = self._probe_tasks.pop(probe_id)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

                self.logger.info(f"Probe stopped: {probe_id}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to stop probe {probe_id}: {str(e)}")
            return False

    async def _validate_probe_config(self, probe_config: ProbeConfig):
        """验证探针配置"""
        # 检查探针类型是否支持
        if probe_config.type not in self._executor_classes:
            raise ProbeError(f"Unsupported probe type: {probe_config.type}")

        # 检查目标是否存在
        try:
            await self.docker_manager.get_container_info(probe_config.target)
        except Exception as e:
            raise ProbeError(f"Invalid probe target: {probe_config.target}", cause=e)

    async def _probe_loop(self, probe_config: ProbeConfig):
        """探针执行循环"""
        executor_class = self._executor_classes[probe_config.type]
        executor = executor_class(probe_config, self.docker_manager)

        while True:
            try:
                # 执行探针检查
                result = await executor.execute()

                # 存储结果
                await self._store_probe_result(result)

                # 检查告警规则
                await self._check_alert_rules(result)

                # 等待下次执行
                await asyncio.sleep(probe_config.interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in probe loop for {probe_config.probe_id}: {str(e)}")
                await asyncio.sleep(probe_config.interval)

    async def _store_probe_result(self, result: ProbeResult):
        """存储探针结果"""
        probe_id = result.probe_id

        # 初始化结果列表
        if probe_id not in self._probe_results:
            self._probe_results[probe_id] = []

        # 添加新结果
        self._probe_results[probe_id].append(result)

        # 限制历史记录数量
        max_results = 1000  # 保留最近1000条记录
        if len(self._probe_results[probe_id]) > max_results:
            self._probe_results[probe_id] = self._probe_results[probe_id][-max_results:]

    # ================== 告警管理 ==================

    def add_alert_rule(self, rule: AlertRule):
        """添加告警规则"""
        self._alert_rules[rule.rule_id] = rule
        self.logger.info(f"Alert rule added: {rule.name} ({rule.rule_id})")

    def remove_alert_rule(self, rule_id: str):
        """移除告警规则"""
        self._alert_rules.pop(rule_id, None)
        self.logger.info(f"Alert rule removed: {rule_id}")

    async def _check_alert_rules(self, result: ProbeResult):
        """检查告警规则"""
        for rule in self._alert_rules.values():
            if not rule.enabled:
                continue

            # 简化的规则匹配逻辑
            should_alert = await self._evaluate_alert_rule(rule, result)

            if should_alert:
                await self._trigger_alert(rule, result)

    async def _evaluate_alert_rule(self, rule: AlertRule, result: ProbeResult) -> bool:
        """评估告警规则"""
        # 根据规则条件评估是否应该触发告警
        # 这里实现简化的规则评估逻辑

        if rule.condition == "probe_status":
            if rule.operator == "==" and result.status.value == rule.threshold:
                return rule.should_trigger(1.0)
            elif rule.operator == "!=" and result.status.value != rule.threshold:
                return rule.should_trigger(1.0)

        # 检查指标值
        for metric in result.metrics:
            if metric.name in rule.condition:
                if isinstance(metric.value, (int, float)):
                    return rule.should_trigger(float(metric.value))

        return False

    async def _trigger_alert(self, rule: AlertRule, result: ProbeResult):
        """触发告警"""
        # 创建告警事件
        alert_event = AlertEvent(
            event_id=generate_uuid(),
            rule_id=rule.rule_id,
            rule_name=rule.name,
            target=result.target,
            severity=rule.severity,
            message=f"告警触发: {rule.name} - {result.message}",
            value=0.0,  # 需要根据具体规则设置
            threshold=rule.threshold
        )

        # 存储活跃告警
        self._active_alerts[alert_event.event_id] = alert_event

        # 触发规则
        rule.trigger()

        self.logger.warning(f"Alert triggered: {rule.name} for {result.target}")

        # 发送通知（如果配置了通知渠道）
        await self._send_alert_notification(alert_event)

    async def _send_alert_notification(self, alert_event: AlertEvent):
        """发送告警通知"""
        # 这里可以实现各种通知方式：邮件、webhook、钉钉等
        # 暂时只记录日志
        self.logger.info(f"Alert notification: {alert_event.message}")

    # ================== 查询接口 ==================

    def get_probe_configs(self) -> List[ProbeConfig]:
        """获取所有探针配置"""
        return list(self._probe_configs.values())

    def get_probe_config(self, probe_id: str) -> Optional[ProbeConfig]:
        """获取指定探针配置"""
        return self._probe_configs.get(probe_id)

    def get_probe_results(self, probe_id: str, limit: int = 100) -> List[ProbeResult]:
        """获取探针结果"""
        results = self._probe_results.get(probe_id, [])
        return results[-limit:]

    def get_latest_result(self, probe_id: str) -> Optional[ProbeResult]:
        """获取最新的探针结果"""
        results = self._probe_results.get(probe_id, [])
        return results[-1] if results else None

    def get_active_alerts(self) -> List[AlertEvent]:
        """获取活跃告警"""
        return [alert for alert in self._active_alerts.values() if alert.status == "active"]

    async def get_stats(self) -> Dict[str, Any]:
        """获取监控服务统计信息"""
        total_probes = len(self._probe_configs)
        active_probes = len(self._probe_tasks)
        total_alerts = len(self._alert_rules)
        active_alerts = len(self.get_active_alerts())

        return {
            "probes": {
                "total": total_probes,
                "active": active_probes,
                "healthy": len([p for p in self._probe_configs.values() if p.enabled]),
                "unhealthy": 0  # 需要统计
            },
            "alerts": {
                "rules": total_alerts,
                "active": active_alerts
            },
            "results": {
                "total": sum(len(results) for results in self._probe_results.values())
            }
        }

    # ================== 事件处理 ==================

    async def _handle_container_event(self, event: LifecycleEvent):
        """处理容器生命周期事件"""
        container_id = event.container_id

        # 根据容器事件自动管理探针
        if event.event_type == "state_change":
            if event.new_state and event.new_state.value == "running":
                # 容器启动时，自动为其创建基础监控探针
                await self._auto_create_probes_for_container(container_id)
            elif event.new_state and event.new_state.value in ["stopped", "removed"]:
                # 容器停止或删除时，停止相关探针
                await self._stop_probes_for_container(container_id)

    async def _auto_create_probes_for_container(self, container_id: str):
        """为容器自动创建探针"""
        try:
            container_info = await self.docker_manager.get_container_info(container_id)

            # 创建健康检查探针
            health_probe = ProbeConfig(
                probe_id=f"health-{generate_short_uuid()}",
                name=f"Health Check - {container_info.name}",
                type=ProbeType.HEALTH,
                target=container_id,
                description=f"自动创建的健康检查探针 - {container_info.name}"
            )

            await self.add_probe(health_probe)

            # 创建资源监控探针
            resource_probe = ProbeConfig(
                probe_id=f"resource-{generate_short_uuid()}",
                name=f"Resource Monitor - {container_info.name}",
                type=ProbeType.RESOURCE,
                target=container_id,
                description=f"自动创建的资源监控探针 - {container_info.name}"
            )

            await self.add_probe(resource_probe)

            self.logger.info(f"Auto-created probes for container: {container_info.name}")

        except Exception as e:
            self.logger.warning(f"Failed to auto-create probes for container {container_id}: {str(e)}")

    async def _stop_probes_for_container(self, container_id: str):
        """停止容器相关的探针"""
        probes_to_stop = []

        for probe_id, probe_config in self._probe_configs.items():
            if probe_config.target == container_id:
                probes_to_stop.append(probe_id)

        for probe_id in probes_to_stop:
            await self.stop_probe(probe_id)
            self.logger.info(f"Stopped probe {probe_id} for removed container {container_id}")

    # ================== 数据清理 ==================

    async def _cleanup_loop(self):
        """数据清理循环"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                await self._cleanup_old_data()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {str(e)}")

    async def _cleanup_old_data(self):
        """清理过期数据"""
        cutoff_time = datetime.now() - timedelta(days=self.settings.data_retention_days)

        # 清理过期的探针结果
        for probe_id in self._probe_results:
            original_count = len(self._probe_results[probe_id])
            self._probe_results[probe_id] = [
                result for result in self._probe_results[probe_id]
                if result.timestamp > cutoff_time
            ]
            cleaned_count = original_count - len(self._probe_results[probe_id])

            if cleaned_count > 0:
                self.logger.debug(f"Cleaned {cleaned_count} old results for probe {probe_id}")

        # 清理已解决的告警事件
        resolved_alerts = []
        for event_id, alert in self._active_alerts.items():
            if alert.status == "resolved" and alert.resolved_at and alert.resolved_at < cutoff_time:
                resolved_alerts.append(event_id)

        for event_id in resolved_alerts:
            self._active_alerts.pop(event_id, None)

        if resolved_alerts:
            self.logger.info(f"Cleaned {len(resolved_alerts)} old resolved alerts")


class ProbeManager(LoggerMixin):
    """探针管理器 - 统一的探针管理接口"""

    def __init__(self, docker_manager: DockerManager,
                 container_manager: Optional[ContainerLifecycleManager] = None):
        super().__init__()
        self.docker_manager = docker_manager
        self.container_manager = container_manager
        self.monitoring_service = MonitoringService(docker_manager, container_manager)
        self._initialized = False

    async def initialize(self):
        """初始化探针管理器"""
        try:
            await self.monitoring_service.initialize()
            self._initialized = True
            self.logger.info("Probe manager initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize probe manager: {str(e)}")
            raise ProbeError(f"Probe manager initialization failed: {str(e)}", cause=e)

    async def cleanup(self):
        """清理探针管理器"""
        await self.monitoring_service.cleanup()
        self._initialized = False
        self.logger.info("Probe manager cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    async def is_healthy(self) -> bool:
        """检查探针管理器健康状态"""
        if not self._initialized:
            return False

        return self.monitoring_service.is_initialized

    # ================== 代理方法 ==================

    async def add_probe(self, probe_config: ProbeConfig) -> bool:
        """添加探针"""
        return await self.monitoring_service.add_probe(probe_config)

    async def remove_probe(self, probe_id: str) -> bool:
        """移除探针"""
        return await self.monitoring_service.remove_probe(probe_id)

    async def start_probe(self, probe_id: str) -> bool:
        """启动探针"""
        return await self.monitoring_service.start_probe(probe_id)

    async def stop_probe(self, probe_id: str) -> bool:
        """停止探针"""
        return await self.monitoring_service.stop_probe(probe_id)

    def get_probe_configs(self) -> List[ProbeConfig]:
        """获取所有探针配置"""
        return self.monitoring_service.get_probe_configs()

    def get_probe_config(self, probe_id: str) -> Optional[ProbeConfig]:
        """获取指定探针配置"""
        return self.monitoring_service.get_probe_config(probe_id)

    def get_probe_results(self, probe_id: str, limit: int = 100) -> List[ProbeResult]:
        """获取探针结果"""
        return self.monitoring_service.get_probe_results(probe_id, limit)

    def get_latest_result(self, probe_id: str) -> Optional[ProbeResult]:
        """获取最新的探针结果"""
        return self.monitoring_service.get_latest_result(probe_id)

    def add_alert_rule(self, rule: AlertRule):
        """添加告警规则"""
        self.monitoring_service.add_alert_rule(rule)

    def remove_alert_rule(self, rule_id: str):
        """移除告警规则"""
        self.monitoring_service.remove_alert_rule(rule_id)

    def get_active_alerts(self) -> List[AlertEvent]:
        """获取活跃告警"""
        return self.monitoring_service.get_active_alerts()

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return await self.monitoring_service.get_stats()

    # ================== 批量操作 ==================

    async def create_default_probes_for_container(self, container_id: str) -> List[str]:
        """为容器创建默认探针"""
        try:
            container_info = await self.docker_manager.get_container_info(container_id)

            probe_ids = []

            # 创建健康检查探针
            health_probe = ProbeConfig(
                probe_id=f"health-{container_info.name}-{generate_short_uuid()}",
                name=f"Health Check - {container_info.name}",
                type=ProbeType.HEALTH,
                target=container_id,
                description=f"健康检查探针 - {container_info.name}",
                interval=30
            )

            if await self.add_probe(health_probe):
                probe_ids.append(health_probe.probe_id)

            # 创建资源监控探针
            resource_probe = ProbeConfig(
                probe_id=f"resource-{container_info.name}-{generate_short_uuid()}",
                name=f"Resource Monitor - {container_info.name}",
                type=ProbeType.RESOURCE,
                target=container_id,
                description=f"资源监控探针 - {container_info.name}",
                interval=10
            )

            if await self.add_probe(resource_probe):
                probe_ids.append(resource_probe.probe_id)

            # 创建日志监控探针
            log_probe = ProbeConfig(
                probe_id=f"log-{container_info.name}-{generate_short_uuid()}",
                name=f"Log Monitor - {container_info.name}",
                type=ProbeType.LOG,
                target=container_id,
                description=f"日志监控探针 - {container_info.name}",
                interval=60
            )

            if await self.add_probe(log_probe):
                probe_ids.append(log_probe.probe_id)

            self.logger.info(f"Created {len(probe_ids)} default probes for container {container_info.name}")
            return probe_ids

        except Exception as e:
            self.logger.error(f"Failed to create default probes for container {container_id}: {str(e)}")
            raise ProbeError(f"Failed to create default probes: {str(e)}", cause=e)

    async def remove_all_probes_for_container(self, container_id: str) -> int:
        """移除容器的所有探针"""
        probe_configs = self.get_probe_configs()
        removed_count = 0

        for probe_config in probe_configs:
            if probe_config.target == container_id:
                if await self.remove_probe(probe_config.probe_id):
                    removed_count += 1

        self.logger.info(f"Removed {removed_count} probes for container {container_id}")
        return removed_count

    async def start_all_probes(self) -> Dict[str, bool]:
        """启动所有探针"""
        results = {}
        probe_configs = self.get_probe_configs()

        for probe_config in probe_configs:
            if probe_config.enabled:
                try:
                    result = await self.start_probe(probe_config.probe_id)
                    results[probe_config.probe_id] = result
                except Exception as e:
                    self.logger.error(f"Failed to start probe {probe_config.probe_id}: {str(e)}")
                    results[probe_config.probe_id] = False

        return results

    async def stop_all_probes(self) -> Dict[str, bool]:
        """停止所有探针"""
        results = {}
        probe_configs = self.get_probe_configs()

        for probe_config in probe_configs:
            try:
                result = await self.stop_probe(probe_config.probe_id)
                results[probe_config.probe_id] = result
            except Exception as e:
                self.logger.error(f"Failed to stop probe {probe_config.probe_id}: {str(e)}")
                results[probe_config.probe_id] = False

        return results

    def get_probe_summary(self) -> Dict[str, Any]:
        """获取探针摘要信息"""
        probe_configs = self.get_probe_configs()

        summary = {
            "total_probes": len(probe_configs),
            "enabled_probes": len([p for p in probe_configs if p.enabled]),
            "disabled_probes": len([p for p in probe_configs if not p.enabled]),
            "by_type": {},
            "by_target": {},
            "recent_alerts": len(self.get_active_alerts())
        }

        # 按类型统计
        for probe_config in probe_configs:
            probe_type = probe_config.type.value
            if probe_type not in summary["by_type"]:
                summary["by_type"][probe_type] = 0
            summary["by_type"][probe_type] += 1

        # 按目标统计
        for probe_config in probe_configs:
            target = probe_config.target
            if target not in summary["by_target"]:
                summary["by_target"][target] = 0
            summary["by_target"][target] += 1

        return summary
    # 便捷函数
async def create_probe_manager(docker_manager: DockerManager,
                               container_manager: Optional[ContainerLifecycleManager] = None) -> ProbeManager:
    """创建并初始化探针管理器"""
    manager = ProbeManager(docker_manager, container_manager)
    await manager.initialize()
    return manager