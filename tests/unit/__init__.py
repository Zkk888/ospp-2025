
"""
单元测试包

******OSPP-2025-张金荣******

包含项目各个模块的单元测试，专注于测试：
- 单个函数和方法的功能
- 类的行为和状态变化
- 边界条件和错误处理
- 数据验证和转换
- 业务逻辑的正确性

单元测试原则：
1. 每个测试只测试一个功能点
2. 测试应该是独立的，不依赖其他测试
3. 使用mock隔离外部依赖
4. 测试名称应该清楚描述测试内容
5. 包含正常情况、边界情况和异常情况测试

测试组织结构：
- test_docker_manager.py：Docker管理器单元测试
- test_container_service.py：容器服务单元测试
- test_build_service.py：构建服务单元测试
- test_probe_service.py：探针服务单元测试
- test_utils.py：工具函数单元测试
- test_models.py：数据模型单元测试

使用方式：
    # 运行所有单元测试
    pytest tests/unit/

    # 运行特定测试文件
    pytest tests/unit/test_docker_manager.py

    # 运行特定测试类
    pytest tests/unit/test_docker_manager.py::TestDockerManager

    # 运行特定测试方法
    pytest tests/unit/test_docker_manager.py::TestDockerManager::test_create_container

版本: 1.0.0
作者: 张金荣
"""

import pytest
import unittest.mock as mock
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path

# 测试标记
pytestmark = pytest.mark.unit

# 当前目录
UNIT_TESTS_DIR = Path(__file__).parent

# ====================================
# 单元测试基类
# ====================================

class BaseUnitTest:
    """单元测试基类，提供通用的测试工具和方法"""

    def setup_method(self, method):
        """每个测试方法执行前的设置"""
        self.patches = []  # 存储patch对象，用于清理
        self.test_data = {}  # 存储测试数据

    def teardown_method(self, method):
        """每个测试方法执行后的清理"""
        # 停止所有patch
        for patch_obj in self.patches:
            if hasattr(patch_obj, 'stop'):
                patch_obj.stop()
        self.patches.clear()

    def create_patch(self, target: str, **kwargs) -> mock.Mock:
        """
        创建并启动patch，会自动在测试结束时清理

        Args:
            target: 要patch的目标
            **kwargs: patch的参数

        Returns:
            Mock对象
        """
        patcher = mock.patch(target, **kwargs)
        mock_obj = patcher.start()
        self.patches.append(patcher)
        return mock_obj

    def assert_called_with_subset(self, mock_obj: mock.Mock, **expected_kwargs):
        """
        断言mock对象被调用时包含指定的参数子集

        Args:
            mock_obj: Mock对象
            **expected_kwargs: 期望的参数子集
        """
        assert mock_obj.called, "Mock对象未被调用"
        call_kwargs = mock_obj.call_args.kwargs if mock_obj.call_args else {}

        for key, expected_value in expected_kwargs.items():
            assert key in call_kwargs, f"参数 '{key}' 不在调用参数中"
            assert call_kwargs[key] == expected_value, \
                f"参数 '{key}' 的值不匹配：期望 {expected_value}，实际 {call_kwargs[key]}"

# ====================================
# Mock工厂函数
# ====================================

def create_mock_docker_client() -> mock.Mock:
    """创建模拟的Docker客户端"""
    mock_client = mock.Mock()

    # 基本方法
    mock_client.ping.return_value = True
    mock_client.version.return_value = {
        "Version": "20.10.21",
        "ApiVersion": "1.41"
    }
    mock_client.info.return_value = {
        "ID": "test-daemon",
        "Containers": 5,
        "Images": 10
    }

    # 容器管理
    mock_container = create_mock_container()
    mock_client.containers.list.return_value = [mock_container]
    mock_client.containers.get.return_value = mock_container
    mock_client.containers.run.return_value = mock_container
    mock_client.containers.create.return_value = mock_container

    # 镜像管理
    mock_image = create_mock_image()
    mock_client.images.list.return_value = [mock_image]
    mock_client.images.get.return_value = mock_image
    mock_client.images.build.return_value = (mock_image, [])
    mock_client.images.pull.return_value = mock_image

    # 网络管理
    mock_network = create_mock_network()
    mock_client.networks.list.return_value = [mock_network]
    mock_client.networks.get.return_value = mock_network
    mock_client.networks.create.return_value = mock_network

    # 卷管理
    mock_volume = create_mock_volume()
    mock_client.volumes.list.return_value = [mock_volume]
    mock_client.volumes.get.return_value = mock_volume
    mock_client.volumes.create.return_value = mock_volume

    return mock_client

def create_mock_container(
        container_id: str = "test_container_123",
        name: str = "test_container",
        status: str = "running"
) -> mock.Mock:
    """创建模拟的Docker容器"""
    mock_container = mock.Mock()

    # 基本属性
    mock_container.id = container_id
    mock_container.name = name
    mock_container.status = status
    mock_container.short_id = container_id[:12]

    # 容器属性字典
    mock_container.attrs = {
        "Id": container_id,
        "Name": f"/{name}",
        "State": {
            "Status": status,
            "Running": status == "running",
            "Paused": status == "paused",
            "Dead": status == "dead",
            "ExitCode": 0 if status == "running" else 1,
            "StartedAt": "2025-07-01T10:00:00Z",
            "FinishedAt": "0001-01-01T00:00:00Z" if status == "running" else "2025-09-01T11:00:00Z"
        },
        "Config": {
            "Image": "centos:7",
            "Cmd": ["/bin/bash"],
            "Env": ["PATH=/usr/bin:/bin"],
            "Labels": {"test": "true"},
            "WorkingDir": "/",
            "User": "root"
        },
        "NetworkSettings": {
            "IPAddress": "172.17.0.2",
            "Ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}
        },
        "Mounts": []
    }

    # 容器方法
    mock_container.start.return_value = None
    mock_container.stop.return_value = None
    mock_container.restart.return_value = None
    mock_container.pause.return_value = None
    mock_container.unpause.return_value = None
    mock_container.remove.return_value = None
    mock_container.kill.return_value = None
    mock_container.reload.return_value = None
    mock_container.logs.return_value = b"container logs"
    mock_container.stats.return_value = {
        "memory": {"usage": 1024*1024*100},  # 100MB
        "cpu_stats": {"cpu_usage": {"total_usage": 1000000000}}
    }

    # exec方法
    mock_exec = mock.Mock()
    mock_exec.start.return_value = None
    mock_container.exec_run.return_value = (0, b"exec output")

    return mock_container

def create_mock_image(
        image_id: str = "test_image_123",
        tags: List[str] = None
) -> mock.Mock:
    """创建模拟的Docker镜像"""
    mock_image = mock.Mock()

    if tags is None:
        tags = ["test:latest"]

    # 基本属性
    mock_image.id = image_id
    mock_image.short_id = image_id[:12]
    mock_image.tags = tags

    # 镜像属性字典
    mock_image.attrs = {
        "Id": image_id,
        "RepoTags": tags,
        "Size": 1024*1024*200,  # 200MB
        "Created": "2025-07-01T10:00:00Z",
        "Config": {
            "Cmd": ["/bin/bash"],
            "Env": ["PATH=/usr/bin:/bin"],
            "Labels": {"build": "test"}
        }
    }

    # 镜像方法
    mock_image.save.return_value = iter([b"image data chunk"])
    mock_image.remove.return_value = None
    mock_image.tag.return_value = True
    mock_image.reload.return_value = None

    return mock_image

def create_mock_network(
        network_id: str = "test_network_123",
        name: str = "test_network"
) -> mock.Mock:
    """创建模拟的Docker网络"""
    mock_network = mock.Mock()

    # 基本属性
    mock_network.id = network_id
    mock_network.name = name
    mock_network.short_id = network_id[:12]

    # 网络属性字典
    mock_network.attrs = {
        "Id": network_id,
        "Name": name,
        "Driver": "bridge",
        "Scope": "local",
        "IPAM": {
            "Driver": "default",
            "Config": [{"Subnet": "172.18.0.0/16"}]
        },
        "Containers": {}
    }

    # 网络方法
    mock_network.connect.return_value = None
    mock_network.disconnect.return_value = None
    mock_network.remove.return_value = None
    mock_network.reload.return_value = None

    return mock_network

def create_mock_volume(
        volume_name: str = "test_volume"
) -> mock.Mock:
    """创建模拟的Docker卷"""
    mock_volume = mock.Mock()

    # 基本属性
    mock_volume.name = volume_name
    mock_volume.id = volume_name

    # 卷属性字典
    mock_volume.attrs = {
        "Name": volume_name,
        "Driver": "local",
        "Mountpoint": f"/var/lib/docker/volumes/{volume_name}/_data",
        "Labels": {},
        "Scope": "local"
    }

    # 卷方法
    mock_volume.remove.return_value = None
    mock_volume.reload.return_value = None

    return mock_volume

def create_mock_redis_client() -> mock.Mock:
    """创建模拟的Redis客户端"""
    mock_redis = mock.Mock()

    # 连接方法
    mock_redis.ping.return_value = True
    mock_redis.echo.return_value = b"test"

    # 基本操作
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.exists.return_value = 0
    mock_redis.expire.return_value = True
    mock_redis.ttl.return_value = -1

    # 列表操作
    mock_redis.lpush.return_value = 1
    mock_redis.rpush.return_value = 1
    mock_redis.lpop.return_value = None
    mock_redis.rpop.return_value = None
    mock_redis.llen.return_value = 0
    mock_redis.lrange.return_value = []

    # 哈希操作
    mock_redis.hget.return_value = None
    mock_redis.hset.return_value = True
    mock_redis.hgetall.return_value = {}
    mock_redis.hdel.return_value = 1
    mock_redis.hexists.return_value = False

    # 集合操作
    mock_redis.sadd.return_value = 1
    mock_redis.srem.return_value = 1
    mock_redis.smembers.return_value = set()
    mock_redis.sismember.return_value = False

    # 发布订阅
    mock_pubsub = mock.Mock()
    mock_pubsub.subscribe.return_value = None
    mock_pubsub.unsubscribe.return_value = None
    mock_pubsub.get_message.return_value = None
    mock_redis.pubsub.return_value = mock_pubsub

    return mock_redis

def create_mock_database_connection() -> mock.Mock:
    """创建模拟的数据库连接"""
    mock_conn = mock.Mock()

    # 连接方法
    mock_conn.ping.return_value = True
    mock_conn.close.return_value = None
    mock_conn.commit.return_value = None
    mock_conn.rollback.return_value = None

    # 游标
    mock_cursor = mock.Mock()
    mock_cursor.execute.return_value = None
    mock_cursor.executemany.return_value = None
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchmany.return_value = []
    mock_cursor.fetchall.return_value = []
    mock_cursor.close.return_value = None
    mock_cursor.rowcount = 0
    mock_cursor.description = []

    mock_conn.cursor.return_value = mock_cursor
    mock_conn.execute.return_value = mock_cursor

    return mock_conn

# ====================================
# 测试数据生成函数
# ====================================

def generate_test_container_data(count: int = 1) -> List[Dict[str, Any]]:
    """生成测试用容器数据"""
    containers = []
    for i in range(count):
        container = {
            "id": f"container_{i:03d}",
            "name": f"test-container-{i:03d}",
            "image": "centos:7",
            "status": "running" if i % 2 == 0 else "stopped",
            "created_at": "2025-07-01T10:00:00Z",
            "config": {
                "environment": {"INDEX": str(i)},
                "ports": {"80/tcp": 8080 + i} if i % 3 == 0 else {},
                "volumes": {f"/host/data{i}": f"/container/data{i}"} if i % 4 == 0 else {}
            }
        }
        containers.append(container)
    return containers

def generate_test_build_data(count: int = 1) -> List[Dict[str, Any]]:
    """生成测试用构建数据"""
    builds = []
    statuses = ["pending", "building", "completed", "failed"]

    for i in range(count):
        build = {
            "id": f"build_{i:03d}",
            "name": f"test-build-{i:03d}",
            "status": statuses[i % len(statuses)],
            "dockerfile_content": f"FROM centos:7\nRUN echo 'Build {i}'\n",
            "created_at": "2025-07-01T10:00:00Z",
            "build_args": {"BUILD_ID": str(i)},
            "labels": {"batch": "test", "index": str(i)}
        }
        builds.append(build)
    return builds

def generate_test_probe_data(count: int = 1) -> List[Dict[str, Any]]:
    """生成测试用探针数据"""
    probes = []
    probe_types = ["http", "tcp", "command"]
    statuses = ["healthy", "unhealthy", "unknown"]

    for i in range(count):
        probe_type = probe_types[i % len(probe_types)]
        probe = {
            "id": f"probe_{i:03d}",
            "container_id": f"container_{i:03d}",
            "type": probe_type,
            "status": statuses[i % len(statuses)],
            "config": _generate_probe_config(probe_type, i),
            "last_check": "2025-07-01T10:00:00Z",
            "failure_count": i % 3
        }
        probes.append(probe)
    return probes

def _generate_probe_config(probe_type: str, index: int) -> Dict[str, Any]:
    """生成探针配置"""
    if probe_type == "http":
        return {
            "url": f"http://localhost:{8080 + index}/health",
            "method": "GET",
            "timeout": 5,
            "interval": 10,
            "retries": 3
        }
    elif probe_type == "tcp":
        return {
            "host": "localhost",
            "port": 22 + index,
            "timeout": 3,
            "interval": 5,
            "retries": 2
        }
    elif probe_type == "command":
        return {
            "command": ["echo", f"probe-{index}"],
            "expected_exit_code": 0,
            "timeout": 10,
            "interval": 30,
            "retries": 1
        }
    else:
        return {}

# ====================================
# 测试辅助函数
# ====================================

def assert_dict_subset(actual: Dict[str, Any], expected: Dict[str, Any], message: str = ""):
    """
    断言实际字典包含期望的键值对子集

    Args:
        actual: 实际字典
        expected: 期望的子集
        message: 断言失败时的消息
    """
    prefix = f"{message}: " if message else ""

    for key, expected_value in expected.items():
        assert key in actual, f"{prefix}缺少键 '{key}'"

        if isinstance(expected_value, dict) and isinstance(actual[key], dict):
            assert_dict_subset(actual[key], expected_value, f"{prefix}键 '{key}' 的值")
        else:
            assert actual[key] == expected_value, \
                f"{prefix}键 '{key}' 的值不匹配：期望 {expected_value}，实际 {actual[key]}"

def assert_list_contains_dict(actual_list: List[Dict], expected_dict: Dict[str, Any], message: str = ""):
    """
    断言列表包含具有指定键值对的字典

    Args:
        actual_list: 实际列表
        expected_dict: 期望包含的字典键值对
        message: 断言失败时的消息
    """
    prefix = f"{message}: " if message else ""

    found = False
    for item in actual_list:
        if isinstance(item, dict):
            try:
                assert_dict_subset(item, expected_dict)
                found = True
                break
            except AssertionError:
                continue

    assert found, f"{prefix}列表中未找到包含 {expected_dict} 的字典"

def create_test_file_content(file_type: str, content: str = None) -> str:
    """
    创建测试文件内容

    Args:
        file_type: 文件类型 (dockerfile, spec, makefile等)
        content: 自定义内容，如果为None则使用默认内容

    Returns:
        文件内容字符串
    """
    if content:
        return content

    templates = {
        "dockerfile": """
FROM centos:7
RUN yum update -y
RUN yum install -y rpm-build
WORKDIR /workspace
CMD ["/bin/bash"]
        """.strip(),

        "spec": """
Name:           test-package
Version:        1.0.0
Release:        1%{?dist}
Summary:        Test package
License:        MIT
%description
Test package for unit tests
%files
        """.strip(),

        "makefile": """
CC = gcc
CFLAGS = -Wall -O2
TARGET = test
SOURCES = main.c

all: $(TARGET)

$(TARGET): $(SOURCES)
\t$(CC) $(CFLAGS) -o $@ $<

clean:
\trm -f $(TARGET)
        """.strip(),

        "c": """
#include <stdio.h>

int main() {
    printf("Hello, World!\\n");
    return 0;
}
        """.strip(),

        "python": """
#!/usr/bin/env python3

def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
        """.strip()
    }

    return templates.get(file_type, "# Test file content")

# ====================================
# 异常测试辅助函数
# ====================================

def assert_raises_with_message(exception_class, message_pattern: str, callable_obj: Callable, *args, **kwargs):
    """
    断言抛出指定异常并且异常消息匹配指定模式

    Args:
        exception_class: 期望的异常类
        message_pattern: 异常消息应匹配的模式
        callable_obj: 要调用的函数
        *args: 函数参数
        **kwargs: 函数关键字参数
    """
    import re

    with pytest.raises(exception_class) as exc_info:
        callable_obj(*args, **kwargs)

    actual_message = str(exc_info.value)
    assert re.search(message_pattern, actual_message), \
        f"异常消息 '{actual_message}' 不匹配模式 '{message_pattern}'"

# ====================================
# 参数化测试辅助函数
# ====================================

def parametrize_with_cases(test_cases: List[Dict[str, Any]], ids: Optional[List[str]] = None):
    """
    为测试用例创建参数化装饰器

    Args:
        test_cases: 测试用例列表，每个用例是一个字典
        ids: 测试用例的标识符列表

    Returns:
        pytest.mark.parametrize装饰器
    """
    if not test_cases:
        return pytest.mark.parametrize("", [])

    # 获取所有键
    all_keys = set()
    for case in test_cases:
        all_keys.update(case.keys())

    # 构建参数列表
    param_names = sorted(all_keys)
    param_values = []

    for case in test_cases:
        values = []
        for key in param_names:
            values.append(case.get(key))
        param_values.append(tuple(values))

    return pytest.mark.parametrize(",".join(param_names), param_values, ids=ids)

# ====================================
# 导出的测试工具
# ====================================

__all__ = [
    # 基类
    "BaseUnitTest",

    # Mock工厂
    "create_mock_docker_client",
    "create_mock_container",
    "create_mock_image",
    "create_mock_network",
    "create_mock_volume",
    "create_mock_redis_client",
    "create_mock_database_connection",

    # 数据生成
    "generate_test_container_data",
    "generate_test_build_data",
    "generate_test_probe_data",

    # 断言工具
    "assert_dict_subset",
    "assert_list_contains_dict",
    "assert_raises_with_message",

    # 文件工具
    "create_test_file_content",

    # 参数化工具
    "parametrize_with_cases",

    # 常量
    "UNIT_TESTS_DIR",
]