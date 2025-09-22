#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EulerMaker Docker Optimizer 高级使用示例

******OSPP-2025-张金荣******

本文件演示 Docker Optimizer 的高级功能，包括：
1. 批量容器管理和操作
2. 自动化构建流水线
3. 高级监控和告警集成
4. 集群管理和负载均衡
5. 自动化运维脚本
6. 性能优化和资源管理
7. 故障恢复和高可用

作者: 张金荣
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
import yaml

import requests
import websocket
from dataclasses import dataclass, asdict
from enum import Enum

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BuildStatus(Enum):
    """构建状态枚举"""
    QUEUED = "queued"
    BUILDING = "building"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ContainerStatus(Enum):
    """容器状态枚举"""
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    EXITED = "exited"

@dataclass
class BuildJob:
    """构建任务数据类"""
    name: str
    container_id: str
    source_url: str
    spec_file: str
    build_type: str = "rpm"
    target_arch: str = "x86_64"
    environment: Dict = None
    priority: str = "normal"
    timeout: int = 3600
    retry_count: int = 3

@dataclass
class ContainerTemplate:
    """容器模板数据类"""
    name_prefix: str
    image: str
    command: List[str]
    environment: Dict = None
    ports: Dict = None
    volumes: Dict = None
    labels: Dict = None
    resource_limits: Dict = None

class AdvancedDockerOptimizerClient:
    """高级 Docker Optimizer 客户端类"""

    def __init__(self, base_url: str = "http://localhost:8080",
                 api_key: Optional[str] = None,
                 max_workers: int = 10,
                 request_timeout: int = 30):
        """初始化高级客户端"""
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api/v1"
        self.session = requests.Session()
        self.max_workers = max_workers
        self.request_timeout = request_timeout

        if api_key:
            self.session.headers.update({
                'X-API-Key': api_key,
                'Content-Type': 'application/json'
            })

        # 线程池执行器
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # 监控回调函数
        self.monitoring_callbacks: List[Callable] = []

        # 缓存
        self._container_cache = {}
        self._build_cache = {}
        self._cache_ttl = 60  # 缓存60秒

    def add_monitoring_callback(self, callback: Callable):
        """添加监控回调函数"""
        self.monitoring_callbacks.append(callback)

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """统一请求方法"""
        url = f"{self.api_url}{endpoint}"
        try:
            response = self.session.request(
                method, url, timeout=self.request_timeout, **kwargs
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"请求失败 {method} {url}: {e}")
            return None

    # === 批量操作方法 ===

    def batch_create_containers(self, templates: List[ContainerTemplate],
                                count_per_template: int = 1) -> Dict[str, List[str]]:
        """
        批量创建容器

        Args:
            templates: 容器模板列表
            count_per_template: 每个模板创建的容器数量

        Returns:
            创建结果字典 {"template_name": ["container_id1", "container_id2"]}
        """
        logger.info(f"开始批量创建容器，{len(templates)}个模板，每个创建{count_per_template}个实例")

        results = {}
        futures = []

        for template in templates:
            for i in range(count_per_template):
                container_name = f"{template.name_prefix}-{i+1:03d}"

                container_config = {
                    "name": container_name,
                    "image": template.image,
                    "command": template.command,
                    "environment": template.environment or {},
                    "ports": template.ports or {},
                    "volumes": template.volumes or {},
                    "labels": {
                        **(template.labels or {}),
                        "template": template.name_prefix,
                        "batch_created": "true",
                        "created_at": datetime.now().isoformat()
                    },
                    "resource_limits": template.resource_limits or {}
                }

                future = self.executor.submit(
                    self._make_request, 'POST', '/containers', json=container_config
                )
                futures.append((template.name_prefix, future))

        # 收集结果
        for template_name, future in futures:
            try:
                result = future.result(timeout=60)
                if result and result.get('success'):
                    container_id = result['data']['container_id']
                    if template_name not in results:
                        results[template_name] = []
                    results[template_name].append(container_id)
                    logger.info(f"容器创建成功: {container_id}")
                else:
                    logger.error(f"容器创建失败: {template_name}")
            except Exception as e:
                logger.error(f"批量创建容器异常: {e}")

        return results

    def batch_start_containers(self, container_ids: List[str]) -> Dict[str, bool]:
        """批量启动容器"""
        logger.info(f"批量启动 {len(container_ids)} 个容器")

        futures = []
        for container_id in container_ids:
            future = self.executor.submit(
                self._make_request, 'POST', f'/containers/{container_id}/start'
            )
            futures.append((container_id, future))

        results = {}
        for container_id, future in futures:
            try:
                result = future.result(timeout=30)
                results[container_id] = result and result.get('success', False)
            except Exception as e:
                logger.error(f"启动容器 {container_id} 失败: {e}")
                results[container_id] = False

        success_count = sum(1 for v in results.values() if v)
        logger.info(f"批量启动完成: 成功 {success_count}/{len(container_ids)}")

        return results

    def batch_cleanup_containers(self, label_filter: Dict[str, str]) -> int:
        """
        根据标签批量清理容器

        Args:
            label_filter: 标签筛选条件

        Returns:
            清理的容器数量
        """
        logger.info(f"开始批量清理容器，标签筛选: {label_filter}")

        # 获取匹配的容器
        containers = self._make_request('GET', '/containers', params={'status': 'all'})
        if not containers or not containers.get('success'):
            logger.error("获取容器列表失败")
            return 0

        container_list = containers['data']['containers']
        matching_containers = []

        for container in container_list:
            container_labels = container.get('labels', {})
            if all(container_labels.get(k) == v for k, v in label_filter.items()):
                matching_containers.append(container['id'])

        logger.info(f"找到 {len(matching_containers)} 个匹配的容器")

        # 批量停止和删除
        cleanup_count = 0
        for container_id in matching_containers:
            try:
                # 停止容器
                stop_result = self._make_request('POST', f'/containers/{container_id}/stop')
                if stop_result and stop_result.get('success'):
                    # 删除容器
                    delete_result = self._make_request(
                        'DELETE', f'/containers/{container_id}', params={'force': True}
                    )
                    if delete_result and delete_result.get('success'):
                        cleanup_count += 1
                        logger.info(f"容器清理成功: {container_id}")
            except Exception as e:
                logger.error(f"清理容器 {container_id} 失败: {e}")

        logger.info(f"批量清理完成: {cleanup_count}/{len(matching_containers)}")
        return cleanup_count

    # === 自动化构建流水线 ===

    def create_build_pipeline(self, pipeline_config: Dict) -> str:
        """
        创建构建流水线

        Args:
            pipeline_config: 流水线配置

        Returns:
            流水线ID
        """
        pipeline_id = f"pipeline_{int(time.time())}"
        logger.info(f"创建构建流水线: {pipeline_id}")

        # 解析流水线阶段
        stages = pipeline_config.get('stages', [])
        parallel_jobs = pipeline_config.get('parallel_jobs', 1)

        # 准备构建容器
        container_template = ContainerTemplate(
            name_prefix=f"pipeline-{pipeline_id}",
            image=pipeline_config.get('builder_image', 'euleros:latest'),
            command=["/bin/bash"],
            environment={
                "PIPELINE_ID": pipeline_id,
                "BUILD_ENV": pipeline_config.get('environment', 'production')
            },
            volumes={
                f"/tmp/{pipeline_id}": "/workspace"
            },
            labels={
                "type": "pipeline-builder",
                "pipeline_id": pipeline_id
            }
        )

        # 创建构建容器池
        container_results = self.batch_create_containers([container_template], parallel_jobs)
        container_ids = container_results.get(container_template.name_prefix, [])

        if not container_ids:
            logger.error("构建容器创建失败")
            return None

        # 启动容器池
        start_results = self.batch_start_containers(container_ids)
        active_containers = [cid for cid, success in start_results.items() if success]

        if not active_containers:
            logger.error("构建容器启动失败")
            return None

        # 执行流水线阶段
        try:
            for stage_idx, stage in enumerate(stages):
                logger.info(f"执行阶段 {stage_idx + 1}: {stage.get('name', f'Stage-{stage_idx + 1}')}")

                stage_jobs = stage.get('jobs', [])
                if not stage_jobs:
                    continue

                # 并行执行阶段任务
                self._execute_pipeline_stage(stage_jobs, active_containers, pipeline_id)

            logger.info(f"流水线 {pipeline_id} 执行完成")

        finally:
            # 清理构建容器
            self.batch_cleanup_containers({"pipeline_id": pipeline_id})

        return pipeline_id

    def _execute_pipeline_stage(self, jobs: List[Dict], containers: List[str], pipeline_id: str):
        """执行流水线阶段"""
        futures = []

        for job_idx, job in enumerate(jobs):
            container_id = containers[job_idx % len(containers)]

            build_job = BuildJob(
                name=f"{pipeline_id}-{job.get('name', f'job-{job_idx}')}",
                container_id=container_id,
                source_url=job.get('source_url', ''),
                spec_file=job.get('spec_file', ''),
                build_type=job.get('build_type', 'rpm'),
                environment=job.get('environment', {}),
                timeout=job.get('timeout', 3600)
            )

            future = self.executor.submit(self._execute_build_job, build_job)
            futures.append(future)

        # 等待所有任务完成
        for future in as_completed(futures, timeout=7200):  # 2小时超时
            try:
                result = future.result()
                logger.info(f"构建任务完成: {result}")
            except Exception as e:
                logger.error(f"构建任务失败: {e}")

    def _execute_build_job(self, build_job: BuildJob) -> Dict:
        """执行单个构建任务"""
        # 创建构建任务
        build_config = asdict(build_job)
        result = self._make_request('POST', '/builds', json=build_config)

        if not result or not result.get('success'):
            raise Exception(f"构建任务创建失败: {build_job.name}")

        build_id = result['data']['build_id']

        # 监控构建进度
        start_time = time.time()
        while time.time() - start_time < build_job.timeout:
            status_result = self._make_request('GET', f'/builds/{build_id}')
            if status_result and status_result.get('success'):
                build_status = status_result['data']['status']

                if build_status in ['completed', 'failed', 'cancelled']:
                    return {
                        "build_id": build_id,
                        "status": build_status,
                        "duration": time.time() - start_time
                    }

            time.sleep(10)

        # 超时取消构建
        self._make_request('POST', f'/builds/{build_id}/cancel')
        raise Exception(f"构建任务超时: {build_job.name}")

    # === 高级监控功能 ===

    def start_continuous_monitoring(self, interval: int = 60):
        """启动连续监控"""
        logger.info(f"启动连续监控，间隔: {interval}秒")

        def monitoring_loop():
            while True:
                try:
                    metrics = self.collect_system_metrics()
                    self._process_monitoring_data(metrics)
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"监控异常: {e}")
                    time.sleep(10)

        monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitoring_thread.start()
        return monitoring_thread

    def collect_system_metrics(self) -> Dict:
        """收集系统指标"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "containers": {},
            "builds": {},
            "system": {}
        }

        # 收集容器指标
        containers = self._make_request('GET', '/containers', params={'status': 'all'})
        if containers and containers.get('success'):
            container_list = containers['data']['containers']

            status_counts = {}
            for container in container_list:
                status = container.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1

            metrics['containers'] = {
                "total": len(container_list),
                "by_status": status_counts
            }

        # 收集构建任务指标
        builds = self._make_request('GET', '/builds')
        if builds and builds.get('success'):
            build_list = builds['data']['builds']

            status_counts = {}
            for build in build_list:
                status = build.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1

            metrics['builds'] = {
                "total": len(build_list),
                "by_status": status_counts
            }

        return metrics

    def _process_monitoring_data(self, metrics: Dict):
        """处理监控数据"""
        # 触发监控回调
        for callback in self.monitoring_callbacks:
            try:
                callback(metrics)
            except Exception as e:
                logger.error(f"监控回调异常: {e}")

        # 检查告警条件
        self._check_alerts(metrics)

    def _check_alerts(self, metrics: Dict):
        """检查告警条件"""
        containers = metrics.get('containers', {})
        builds = metrics.get('builds', {})

        # 容器异常告警
        failed_containers = containers.get('by_status', {}).get('failed', 0)
        if failed_containers > 5:
            logger.warning(f"容器异常告警: {failed_containers}个容器处于失败状态")

        # 构建失败告警
        failed_builds = builds.get('by_status', {}).get('failed', 0)
        if failed_builds > 3:
            logger.warning(f"构建失败告警: {failed_builds}个构建任务失败")

        # 资源使用告警（示例）
        running_containers = containers.get('by_status', {}).get('running', 0)
        if running_containers > 40:
            logger.warning(f"资源使用告警: {running_containers}个容器正在运行，接近限制")

    # === 集群管理功能 ===

    def setup_build_cluster(self, cluster_config: Dict) -> Dict[str, List[str]]:
        """
        设置构建集群

        Args:
            cluster_config: 集群配置

        Returns:
            集群节点信息
        """
        logger.info("设置构建集群")

        node_types = cluster_config.get('node_types', {})
        cluster_nodes = {}

        for node_type, config in node_types.items():
            node_count = config.get('count', 1)
            node_spec = config.get('spec', {})

            template = ContainerTemplate(
                name_prefix=f"cluster-{node_type}",
                image=node_spec.get('image', 'euleros:latest'),
                command=node_spec.get('command', ["/bin/bash"]),
                environment={
                    **node_spec.get('environment', {}),
                    "NODE_TYPE": node_type,
                    "CLUSTER_NAME": cluster_config.get('name', 'default')
                },
                volumes=node_spec.get('volumes', {}),
                labels={
                    **node_spec.get('labels', {}),
                    "cluster": cluster_config.get('name', 'default'),
                    "node_type": node_type
                },
                resource_limits=node_spec.get('resource_limits', {})
            )

            # 创建集群节点
            node_results = self.batch_create_containers([template], node_count)
            if template.name_prefix in node_results:
                cluster_nodes[node_type] = node_results[template.name_prefix]

                # 启动节点
                self.batch_start_containers(cluster_nodes[node_type])
                logger.info(f"集群节点类型 {node_type} 创建完成: {len(cluster_nodes[node_type])}个节点")

        return cluster_nodes

    def balance_workload(self, cluster_nodes: Dict[str, List[str]],
                         jobs: List[Dict]) -> Dict[str, List[str]]:
        """
        负载均衡分配任务

        Args:
            cluster_nodes: 集群节点
            jobs: 待分配的任务列表

        Returns:
            任务分配结果
        """
        logger.info(f"负载均衡分配 {len(jobs)} 个任务")

        # 获取所有可用节点
        all_nodes = []
        for node_type, nodes in cluster_nodes.items():
            for node_id in nodes:
                all_nodes.append((node_type, node_id))

        if not all_nodes:
            logger.error("没有可用的集群节点")
            return {}

        # 简单轮询分配策略
        allocation = {}
        for i, job in enumerate(jobs):
            node_type, node_id = all_nodes[i % len(all_nodes)]

            if node_id not in allocation:
                allocation[node_id] = []
            allocation[node_id].append(job)

        logger.info(f"任务分配完成: {len(allocation)}个节点")
        return allocation

    # === 自动化运维脚本 ===

    def automated_maintenance(self):
        """自动化维护任务"""
        logger.info("开始自动化维护任务")

        # 1. 清理过期容器
        logger.info("清理过期容器...")
        expired_labels = {
            "auto_cleanup": "true"
        }
        cleaned_count = self.batch_cleanup_containers(expired_labels)
        logger.info(f"清理过期容器: {cleaned_count}个")

        # 2. 清理失败的构建任务
        logger.info("检查失败的构建任务...")
        failed_builds = self._make_request('GET', '/builds', params={'status': 'failed'})
        if failed_builds and failed_builds.get('success'):
            build_list = failed_builds['data']['builds']
            logger.info(f"发现 {len(build_list)} 个失败的构建任务")

            # 可以在这里添加失败任务的重试逻辑

        # 3. 系统健康检查
        logger.info("执行系统健康检查...")
        health = self._make_request('GET', '/health', endpoint_override=True)
        if health:
            logger.info(f"系统健康状态: {health.get('status', 'unknown')}")

        # 4. 资源使用报告
        metrics = self.collect_system_metrics()
        logger.info("当前系统状态:")
        logger.info(f"- 容器总数: {metrics.get('containers', {}).get('total', 0)}")
        logger.info(f"- 构建任务总数: {metrics.get('builds', {}).get('total', 0)}")

        logger.info("自动化维护任务完成")

    def setup_auto_scaling(self, scaling_config: Dict):
        """设置自动扩缩容"""
        logger.info("设置自动扩缩容策略")

        def scaling_monitor():
            while True:
                try:
                    metrics = self.collect_system_metrics()
                    self._check_scaling_conditions(metrics, scaling_config)
                    time.sleep(scaling_config.get('check_interval', 300))  # 默认5分钟检查一次
                except Exception as e:
                    logger.error(f"扩缩容监控异常: {e}")
                    time.sleep(60)

        scaling_thread = threading.Thread(target=scaling_monitor, daemon=True)
        scaling_thread.start()
        return scaling_thread

    def _check_scaling_conditions(self, metrics: Dict, config: Dict):
        """检查扩缩容条件"""
        containers = metrics.get('containers', {})
        running_count = containers.get('by_status', {}).get('running', 0)

        max_containers = config.get('max_containers', 50)
        min_containers = config.get('min_containers', 5)
        scale_up_threshold = config.get('scale_up_threshold', 0.8)
        scale_down_threshold = config.get('scale_down_threshold', 0.3)

        utilization = running_count / max_containers

        if utilization > scale_up_threshold and running_count < max_containers:
            logger.info(f"触发扩容条件: 利用率 {utilization:.2f}")
            self._scale_up(config)
        elif utilization < scale_down_threshold and running_count > min_containers:
            logger.info(f"触发缩容条件: 利用率 {utilization:.2f}")
            self._scale_down(config)

    def _scale_up(self, config: Dict):
        """扩容操作"""
        logger.info("执行扩容操作")

        template_config = config.get('scale_template', {})
        template = ContainerTemplate(
            name_prefix="auto-scale",
            image=template_config.get('image', 'euleros:latest'),
            command=template_config.get('command', ["/bin/bash"]),
            labels={
                **template_config.get('labels', {}),
                "auto_scale": "true",
                "auto_cleanup": "true"
            }
        )

        scale_count = config.get('scale_step', 2)
        results = self.batch_create_containers([template], scale_count)

        if template.name_prefix in results:
            container_ids = results[template.name_prefix]
            self.batch_start_containers(container_ids)
            logger.info(f"扩容完成: 新增 {len(container_ids)} 个容器")

    def _scale_down(self, config: Dict):
        """缩容操作"""
        logger.info("执行缩容操作")

        # 找到可以缩容的容器
        containers = self._make_request('GET', '/containers', params={'status': 'running'})
        if not containers or not containers.get('success'):
            return

        auto_scale_containers = []
        for container in containers['data']['containers']:
            labels = container.get('labels', {})
            if labels.get('auto_scale') == 'true':
                auto_scale_containers.append(container['id'])

        scale_count = min(config.get('scale_step', 2), len(auto_scale_containers))
        if scale_count > 0:
            containers_to_remove = auto_scale_containers[:scale_count]

            # 停止并删除容器
            for container_id in containers_to_remove:
                self._make_request('POST', f'/containers/{container_id}/stop')
                self._make_request('DELETE', f'/containers/{container_id}', params={'force': True})

            logger.info(f"缩容完成: 移除 {scale_count} 个容器")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.executor.shutdown(wait=True)

# === 示例演示函数 ===

def demo_batch_operations():
    """演示批量操作"""
    logger.info("=== 批量操作演示 ===")

    with AdvancedDockerOptimizerClient() as client:
        # 定义容器模板
        templates = [
            ContainerTemplate(
                name_prefix="batch-worker",
                image="euleros:latest",
                command=["/bin/bash", "-c", "while true; do sleep 30; done"],
                environment={"WORKER_TYPE": "general"},
                labels={"purpose": "batch-demo", "auto_cleanup": "true"}
            ),
            ContainerTemplate(
                name_prefix="batch-builder",
                image="euleros:latest",
                command=["/bin/bash"],
                environment={"WORKER_TYPE": "builder"},
                volumes={"/tmp/build": "/workspace"},
                labels={"purpose": "batch-demo", "auto_cleanup": "true"}
            )
        ]

        # 批量创建容器
        results = client.batch_create_containers(templates, count_per_template=3)
        logger.info(f"批量创建结果: {results}")

        # 获取所有创建的容器ID
        all_container_ids = []
        for container_list in results.values():
            all_container_ids.extend(container_list)

        # 批量启动
        start_results = client.batch_start_containers(all_container_ids)
        success_count = sum(1 for success in start_results.values() if success)
        logger.info(f"批量启动结果: {success_count}/{len(all_container_ids)} 成功")

        # 等待一段时间模拟工作
        time.sleep(5)

        # 批量清理
        cleanup_count = client.batch_cleanup_containers({"purpose": "batch-demo"})
        logger.info(f"批量清理完成: {cleanup_count}个容器")

def demo_automated_pipeline():
    """演示自动化构建流水线"""
    logger.info("=== 自动化构建流水线演示 ===")

    with AdvancedDockerOptimizerClient() as client:
        # 流水线配置
        pipeline_config = {
            "name": "demo-pipeline",
            "builder_image": "euleros:latest",
            "environment": "development",
            "parallel_jobs": 2,
            "stages": [
                {
                    "name": "build-stage",
                    "jobs": [
                        {
                            "name": "package-a",
                            "source_url": "https://github.com/example/package-a.git",
                            "spec_file": "package-a.spec",
                            "build_type": "rpm"
                        },
                        {
                            "name": "package-b",
                            "source_url": "https://github.com/example/package-b.git",
                            "spec_file": "package-b.spec",
                            "build_type": "rpm"
                        }
                    ]
                },
                {
                    "name": "test-stage",
                    "jobs": [
                        {
                            "name": "integration-test",
                            "source_url": "https://github.com/example/tests.git",
                            "spec_file": "test.spec",
                            "build_type": "test"
                        }
                    ]
                }
            ]
        }

        # 执行流水线
        pipeline_id = client.create_build_pipeline(pipeline_config)
        if pipeline_id:
            logger.info(f"流水线执行完成: {pipeline_id}")
        else:
            logger.error("流水线执行失败")

def demo_advanced_monitoring():
    """演示高级监控功能"""
    logger.info("=== 高级监控演示 ===")

    with AdvancedDockerOptimizerClient() as client:
        # 添加监控回调
        def alert_callback(metrics):
            containers = metrics.get('containers', {})
            total_containers = containers.get('total', 0)
            if total_containers > 10:
                logger.warning(f"容器数量告警: 当前 {total_containers} 个容器")

        def metrics_logger(metrics):
            logger.info(f"监控指标: {json.dumps(metrics, indent=2)}")

        client.add_monitoring_callback(alert_callback)
        client.add_monitoring_callback(metrics_logger)

        # 启动持续监控
        monitoring_thread = client.start_continuous_monitoring(interval=30)

        # 运行一段时间观察监控
        time.sleep(90)
        logger.info("监控演示完成")

def demo_cluster_management():
    """演示集群管理"""
    logger.info("=== 集群管理演示 ===")

    with AdvancedDockerOptimizerClient() as client:
        # 集群配置
        cluster_config = {
            "name": "demo-cluster",
            "node_types": {
                "worker": {
                    "count": 3,
                    "spec": {
                        "image": "euleros:latest",
                        "command": ["/bin/bash", "-c", "while true; do sleep 30; done"],
                        "environment": {"NODE_ROLE": "worker"},
                        "labels": {"cluster_role": "worker"},
                        "resource_limits": {"memory": "1024m", "cpu": "1.0"}
                    }
                },
                "builder": {
                    "count": 2,
                    "spec": {
                        "image": "euleros:latest",
                        "command": ["/bin/bash"],
                        "environment": {"NODE_ROLE": "builder"},
                        "volumes": {"/tmp/cluster-build": "/workspace"},
                        "labels": {"cluster_role": "builder"},
                        "resource_limits": {"memory": "2048m", "cpu": "2.0"}
                    }
                }
            }
        }

        # 设置集群
        cluster_nodes = client.setup_build_cluster(cluster_config)
        logger.info(f"集群节点: {cluster_nodes}")

        # 模拟任务负载均衡
        jobs = [
            {"name": f"job-{i}", "type": "build"} for i in range(10)
        ]

        allocation = client.balance_workload(cluster_nodes, jobs)
        logger.info(f"任务分配: {len(allocation)}个节点")

        # 清理集群
        time.sleep(10)
        cleanup_count = client.batch_cleanup_containers({"cluster": "demo-cluster"})
        logger.info(f"集群清理完成: {cleanup_count}个节点")

def demo_auto_maintenance():
    """演示自动化运维"""
    logger.info("=== 自动化运维演示 ===")

    with AdvancedDockerOptimizerClient() as client:
        # 执行自动化维护
        client.automated_maintenance()

        # 设置自动扩缩容
        scaling_config = {
            "max_containers": 20,
            "min_containers": 3,
            "scale_up_threshold": 0.7,
            "scale_down_threshold": 0.3,
            "scale_step": 2,
            "check_interval": 60,  # 1分钟检查一次
            "scale_template": {
                "image": "euleros:latest",
                "command": ["/bin/bash", "-c", "while true; do sleep 30; done"],
                "labels": {"purpose": "auto-scale"}
            }
        }

        scaling_thread = client.setup_auto_scaling(scaling_config)
        logger.info("自动扩缩容已启动")

        # 运行一段时间观察扩缩容
        time.sleep(120)
        logger.info("自动化运维演示完成")

def main():
    """主函数 - 运行高级功能演示"""
    logger.info("开始 EulerMaker Docker Optimizer 高级功能演示")
    logger.info("=" * 70)

    try:
        # 运行各种高级功能演示
        demo_batch_operations()
        print()

        demo_automated_pipeline()
        print()

        demo_advanced_monitoring()
        print()

        demo_cluster_management()
        print()

        demo_auto_maintenance()

        logger.info("=" * 70)
        logger.info("所有高级功能演示完成！")

    except KeyboardInterrupt:
        logger.info("演示被用户中断")
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

    logger.info("程序结束")

if __name__ == "__main__":
    main()