#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EulerMaker Docker Optimizer 基本使用示例

******OSPP-2025-张金荣******

本文件演示如何使用 Docker Optimizer 的基本功能，包括：
1. 连接到服务
2. 容器管理基本操作
3. 构建任务管理
4. 终端交互
5. 基础监控

使用前请确保 Docker Optimizer 服务已启动。

作者: 张金荣
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional

import requests
import websocket
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DockerOptimizerClient:
    """Docker Optimizer 客户端类"""

    def __init__(self, base_url: str = "http://localhost:8080",
                 api_key: Optional[str] = None):
        """
        初始化客户端

        Args:
            base_url: API服务地址
            api_key: API密钥（可选）
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api/v1"
        self.ws_url = base_url.replace('http', 'ws')

        # 创建会话
        self.session = requests.Session()

        # 设置重试策略
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # 设置认证头
        if api_key:
            self.session.headers.update({
                'X-API-Key': api_key,
                'Content-Type': 'application/json'
            })

    def health_check(self) -> Dict:
        """健康检查"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {"status": "error", "message": str(e)}

    # === 容器管理方法 ===

    def list_containers(self, status: Optional[str] = None) -> List[Dict]:
        """
        获取容器列表

        Args:
            status: 容器状态筛选 (running/stopped/all)

        Returns:
            容器列表
        """
        params = {}
        if status:
            params['status'] = status

        try:
            response = self.session.get(f"{self.api_url}/containers", params=params)
            response.raise_for_status()
            result = response.json()
            return result.get('data', {}).get('containers', [])
        except Exception as e:
            logger.error(f"获取容器列表失败: {e}")
            return []

    def create_container(self, container_config: Dict) -> Optional[Dict]:
        """
        创建容器

        Args:
            container_config: 容器配置信息

        Returns:
            创建结果
        """
        try:
            response = self.session.post(
                f"{self.api_url}/containers",
                json=container_config
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"创建容器失败: {e}")
            return None

    def start_container(self, container_id: str) -> bool:
        """启动容器"""
        try:
            response = self.session.post(f"{self.api_url}/containers/{container_id}/start")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"启动容器失败: {e}")
            return False

    def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """停止容器"""
        try:
            params = {"timeout": timeout}
            response = self.session.post(
                f"{self.api_url}/containers/{container_id}/stop",
                params=params
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"停止容器失败: {e}")
            return False

    def delete_container(self, container_id: str, force: bool = False) -> bool:
        """删除容器"""
        try:
            params = {"force": force}
            response = self.session.delete(
                f"{self.api_url}/containers/{container_id}",
                params=params
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"删除容器失败: {e}")
            return False

    def get_container_logs(self, container_id: str, tail: int = 100) -> List[Dict]:
        """获取容器日志"""
        try:
            params = {"tail": tail}
            response = self.session.get(
                f"{self.api_url}/containers/{container_id}/logs",
                params=params
            )
            response.raise_for_status()
            result = response.json()
            return result.get('data', {}).get('logs', [])
        except Exception as e:
            logger.error(f"获取容器日志失败: {e}")
            return []

    # === 构建任务管理方法 ===

    def create_build(self, build_config: Dict) -> Optional[Dict]:
        """创建构建任务"""
        try:
            response = self.session.post(f"{self.api_url}/builds", json=build_config)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"创建构建任务失败: {e}")
            return None

    def get_build_status(self, build_id: str) -> Optional[Dict]:
        """获取构建任务状态"""
        try:
            response = self.session.get(f"{self.api_url}/builds/{build_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取构建状态失败: {e}")
            return None

    def list_builds(self, status: Optional[str] = None) -> List[Dict]:
        """获取构建任务列表"""
        params = {}
        if status:
            params['status'] = status

        try:
            response = self.session.get(f"{self.api_url}/builds", params=params)
            response.raise_for_status()
            result = response.json()
            return result.get('data', {}).get('builds', [])
        except Exception as e:
            logger.error(f"获取构建列表失败: {e}")
            return []

    def cancel_build(self, build_id: str) -> bool:
        """取消构建任务"""
        try:
            response = self.session.post(f"{self.api_url}/builds/{build_id}/cancel")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"取消构建任务失败: {e}")
            return False

def demo_container_management():
    """演示容器管理功能"""
    logger.info("=== 容器管理演示 ===")

    # 创建客户端
    client = DockerOptimizerClient()

    # 健康检查
    health = client.health_check()
    logger.info(f"服务健康状态: {health}")

    # 获取现有容器列表
    logger.info("获取现有容器列表...")
    containers = client.list_containers()
    logger.info(f"当前容器数量: {len(containers)}")

    for container in containers:
        logger.info(f"- 容器: {container.get('name')} (状态: {container.get('status')})")

    # 创建新容器
    logger.info("创建新容器...")
    container_config = {
        "name": "demo-builder",
        "image": "euleros:latest",
        "command": ["/bin/bash", "-c", "while true; do sleep 30; done"],
        "environment": {
            "BUILD_TYPE": "demo",
            "ENVIRONMENT": "development"
        },
        "ports": {
            "8888": 8080
        },
        "volumes": {
            "/tmp/demo-workspace": "/workspace"
        },
        "labels": {
            "purpose": "demo",
            "created_by": "basic_usage_example"
        },
        "resource_limits": {
            "memory": "512m",
            "cpu": "1.0"
        }
    }

    create_result = client.create_container(container_config)
    if create_result and create_result.get('success'):
        container_id = create_result['data']['container_id']
        logger.info(f"容器创建成功: {container_id}")

        # 启动容器
        logger.info("启动容器...")
        if client.start_container(container_id):
            logger.info("容器启动成功")

            # 等待容器完全启动
            time.sleep(2)

            # 获取容器日志
            logger.info("获取容器日志...")
            logs = client.get_container_logs(container_id, tail=10)
            for log in logs:
                logger.info(f"日志: {log.get('message', '')}")

            # 演示完成后停止和删除容器
            logger.info("停止并删除演示容器...")
            client.stop_container(container_id)
            client.delete_container(container_id, force=True)
            logger.info("演示容器已清理")
        else:
            logger.error("容器启动失败")
    else:
        logger.error("容器创建失败")

def demo_build_management():
    """演示构建任务管理功能"""
    logger.info("=== 构建任务管理演示 ===")

    client = DockerOptimizerClient()

    # 首先创建一个容器用于构建
    logger.info("创建构建容器...")
    container_config = {
        "name": "build-container",
        "image": "euleros:latest",
        "command": ["/bin/bash"],
        "environment": {
            "BUILD_TYPE": "rpm"
        },
        "volumes": {
            "/tmp/build-workspace": "/workspace",
            "/tmp/rpmbuild": "/root/rpmbuild"
        },
        "labels": {
            "purpose": "build",
            "type": "rpm-builder"
        }
    }

    container_result = client.create_container(container_config)
    if not container_result or not container_result.get('success'):
        logger.error("构建容器创建失败，跳过构建演示")
        return

    container_id = container_result['data']['container_id']

    # 启动构建容器
    if not client.start_container(container_id):
        logger.error("构建容器启动失败")
        client.delete_container(container_id, force=True)
        return

    try:
        # 创建构建任务
        logger.info("创建构建任务...")
        build_config = {
            "name": "demo-package-build",
            "container_id": container_id,
            "source_url": "https://github.com/example/demo-package.git",
            "spec_file": "demo-package.spec",
            "build_type": "rpm",
            "target_arch": "x86_64",
            "environment": {
                "BUILD_VERSION": "1.0.0",
                "RELEASE": "1.el8"
            },
            "priority": "normal"
        }

        build_result = client.create_build(build_config)
        if build_result and build_result.get('success'):
            build_id = build_result['data']['build_id']
            logger.info(f"构建任务创建成功: {build_id}")

            # 监控构建状态
            logger.info("监控构建任务状态...")
            for i in range(10):  # 最多监控10次
                status_info = client.get_build_status(build_id)
                if status_info and status_info.get('success'):
                    build_data = status_info['data']
                    status = build_data.get('status', 'unknown')
                    progress = build_data.get('progress', 0)

                    logger.info(f"构建状态: {status}, 进度: {progress}%")

                    if status in ['completed', 'failed', 'cancelled']:
                        break

                time.sleep(3)

            # 如果构建还在进行中，取消它
            final_status = client.get_build_status(build_id)
            if final_status and final_status.get('success'):
                status = final_status['data'].get('status')
                if status in ['queued', 'building']:
                    logger.info("取消构建任务...")
                    client.cancel_build(build_id)

        else:
            logger.error("构建任务创建失败")

    finally:
        # 清理构建容器
        logger.info("清理构建容器...")
        client.stop_container(container_id)
        client.delete_container(container_id, force=True)

    # 获取所有构建任务
    logger.info("获取构建任务列表...")
    builds = client.list_builds()
    logger.info(f"总构建任务数: {len(builds)}")

    for build in builds[-3:]:  # 显示最近3个任务
        logger.info(f"- 任务: {build.get('name')} (状态: {build.get('status')})")

def demo_terminal_session():
    """演示终端会话功能（简化版）"""
    logger.info("=== 终端会话演示 ===")

    client = DockerOptimizerClient()

    # 创建一个临时容器用于终端演示
    logger.info("创建终端容器...")
    container_config = {
        "name": "terminal-demo",
        "image": "euleros:latest",
        "command": ["/bin/bash"],
        "labels": {
            "purpose": "terminal-demo"
        }
    }

    container_result = client.create_container(container_config)
    if not container_result or not container_result.get('success'):
        logger.error("终端容器创建失败")
        return

    container_id = container_result['data']['container_id']

    if not client.start_container(container_id):
        logger.error("终端容器启动失败")
        client.delete_container(container_id, force=True)
        return

    try:
        # 创建终端会话
        logger.info("创建终端会话...")
        session_data = {
            "container_id": container_id,
            "shell": "/bin/bash",
            "working_dir": "/",
            "environment": {
                "TERM": "xterm-256color"
            }
        }

        response = client.session.post(
            f"{client.api_url}/terminal/sessions",
            json=session_data
        )

        if response.status_code == 200:
            session_result = response.json()
            if session_result.get('success'):
                session_id = session_result['data']['session_id']
                ws_url = session_result['data']['websocket_url']
                logger.info(f"终端会话创建成功: {session_id}")
                logger.info(f"WebSocket URL: {ws_url}")
                logger.info("注意: 实际的终端交互需要WebSocket客户端支持")
            else:
                logger.error("终端会话创建失败")
        else:
            logger.error(f"终端会话请求失败: {response.status_code}")

    finally:
        # 清理容器
        logger.info("清理终端容器...")
        client.stop_container(container_id)
        client.delete_container(container_id, force=True)

def demo_monitoring_basics():
    """演示基础监控功能"""
    logger.info("=== 基础监控演示 ===")

    client = DockerOptimizerClient()

    # 获取系统状态
    logger.info("检查系统整体状态...")

    # 统计容器状态
    all_containers = client.list_containers(status='all')
    running_containers = client.list_containers(status='running')
    stopped_containers = client.list_containers(status='stopped')

    logger.info(f"容器统计:")
    logger.info(f"- 总数: {len(all_containers)}")
    logger.info(f"- 运行中: {len(running_containers)}")
    logger.info(f"- 已停止: {len(stopped_containers)}")

    # 统计构建任务状态
    all_builds = client.list_builds()
    completed_builds = client.list_builds(status='completed')
    failed_builds = client.list_builds(status='failed')

    logger.info(f"构建任务统计:")
    logger.info(f"- 总数: {len(all_builds)}")
    logger.info(f"- 已完成: {len(completed_builds)}")
    logger.info(f"- 失败: {len(failed_builds)}")

    # 显示最近的活动
    logger.info("最近容器活动:")
    for container in running_containers[:3]:
        logger.info(f"- {container.get('name')}: {container.get('status')}")

    logger.info("最近构建活动:")
    for build in all_builds[:3]:
        logger.info(f"- {build.get('name')}: {build.get('status')}")

def main():
    """主函数 - 运行所有演示"""
    logger.info("开始 EulerMaker Docker Optimizer 基本功能演示")
    logger.info("=" * 60)

    try:
        # 演示各个功能模块
        demo_container_management()
        print()

        demo_build_management()
        print()

        demo_terminal_session()
        print()

        demo_monitoring_basics()

        logger.info("=" * 60)
        logger.info("所有演示完成！")

    except KeyboardInterrupt:
        logger.info("演示被用户中断")
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()