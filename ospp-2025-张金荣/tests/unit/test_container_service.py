"""
容器服务单元测试

******OSPP-2025-张金荣******

测试services.container_service模块的功能，包括：
- 容器生命周期管理服务
- 容器配置验证和处理
- 容器监控和状态管理
- 容器日志收集服务
- 容器资源管理
- 业务逻辑处理和错误处理
- 容器批量操作

版本: 1.0.0
作者: 张金荣
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import json

# 导入测试工具
from tests.unit import (
    BaseUnitTest,
    create_mock_docker_client,
    create_mock_container,
    create_mock_redis_client,
    generate_test_container_data,
    assert_dict_subset,
    parametrize_with_cases
)

from tests.fixtures import (
    SAMPLE_CONTAINER_CONFIG,
    CONTAINER_STATES,
    CONTAINER_ERROR_SCENARIOS,
    BOUNDARY_TEST_DATA
)

# 导入被测试的模块
try:
    from services.container_service import ContainerService, ContainerEventHandler
    from core.docker_manager import DockerManager
    from models.container_model import Container, ContainerConfig, ContainerStatus
    from utils.exceptions import (
        ContainerServiceError,
        ContainerNotFoundError,
        ContainerValidationError,
        DockerError
    )
    from utils.logger import get_logger
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入被测试模块: {e}")
    IMPORTS_AVAILABLE = False

# 跳过测试如果导入失败
pytestmark = pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="被测试模块不可用")

# ====================================
# 容器服务基础测试
# ====================================

@pytest.mark.unit
class TestContainerService(BaseUnitTest):
    """容器服务测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建mock依赖
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_redis_client = create_mock_redis_client()
        self.mock_logger = Mock()

        # 配置mock Docker管理器
        self.mock_docker_manager.is_connected.return_value = True
        self.mock_docker_manager.list_containers.return_value = []
        self.mock_docker_manager.get_container.return_value = {
            "id": "test_container_123",
            "name": "test-container",
            "status": "running"
        }

        # 创建容器服务实例
        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager,
            redis_client=self.mock_redis_client,
            logger=self.mock_logger
        )

        # 测试用容器配置
        self.test_config = SAMPLE_CONTAINER_CONFIG.copy()

    def test_container_service_initialization(self):
        """测试容器服务初始化"""
        # 验证依赖已设置
        assert self.container_service.docker_manager is self.mock_docker_manager
        assert self.container_service.redis_client is self.mock_redis_client
        assert self.container_service.logger is self.mock_logger

        # 验证初始化检查
        self.mock_docker_manager.is_connected.assert_called_once()

    def test_container_service_initialization_docker_not_connected(self):
        """测试Docker未连接时的服务初始化"""
        # 模拟Docker未连接
        mock_docker_manager = Mock(spec=DockerManager)
        mock_docker_manager.is_connected.return_value = False
        mock_docker_manager.reconnect.return_value = False

        # 验证抛出异常
        with pytest.raises(ContainerServiceError, match="Docker is not connected"):
            ContainerService(
                docker_manager=mock_docker_manager,
                redis_client=self.mock_redis_client
            )

# ====================================
# 容器列表和查询测试
# ====================================

@pytest.mark.unit
class TestContainerServiceListing(BaseUnitTest):
    """容器服务列表和查询功能测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建容器服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_redis_client = create_mock_redis_client()

        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager,
            redis_client=self.mock_redis_client
        )

    def test_list_all_containers(self):
        """测试列出所有容器"""
        # 准备测试数据
        test_containers = generate_test_container_data(3)
        self.mock_docker_manager.list_containers.return_value = test_containers

        # 调用方法
        result = self.container_service.list_containers(include_stopped=True)

        # 验证结果
        assert len(result) == 3
        assert all("id" in container for container in result)
        assert all("name" in container for container in result)
        assert all("status" in container for container in result)

        # 验证Docker管理器调用
        self.mock_docker_manager.list_containers.assert_called_once_with(all=True)

    def test_list_running_containers_only(self):
        """测试只列出运行中的容器"""
        # 准备测试数据
        test_containers = [
            {"id": "c1", "name": "container1", "status": "running"},
            {"id": "c2", "name": "container2", "status": "stopped"},
            {"id": "c3", "name": "container3", "status": "running"}
        ]
        self.mock_docker_manager.list_containers.return_value = test_containers

        # 调用方法
        result = self.container_service.list_containers(include_stopped=False)

        # 验证结果
        assert len(result) == 3  # Docker管理器返回所有容器，服务层过滤
        self.mock_docker_manager.list_containers.assert_called_once_with(all=False)

    def test_list_containers_with_filter(self):
        """测试使用过滤器列出容器"""
        # 准备测试数据
        test_containers = generate_test_container_data(5)
        self.mock_docker_manager.list_containers.return_value = test_containers

        # 调用方法（按名称过滤）
        result = self.container_service.list_containers(
            name_filter="container-001"
        )

        # 验证过滤逻辑会在服务层处理
        assert isinstance(result, list)
        self.mock_docker_manager.list_containers.assert_called_once()

    def test_get_container_by_id_success(self):
        """测试成功通过ID获取容器"""
        # 准备返回数据
        container_data = {
            "id": "test_container_123",
            "name": "test-container",
            "status": "running",
            "image": "centos:7",
            "config": self.test_config
        }
        self.mock_docker_manager.get_container.return_value = container_data

        # 调用方法
        result = self.container_service.get_container("test_container_123")

        # 验证结果
        assert result["id"] == "test_container_123"
        assert result["name"] == "test-container"
        assert result["status"] == "running"

        # 验证Docker管理器调用
        self.mock_docker_manager.get_container.assert_called_once_with("test_container_123")

    def test_get_container_not_found(self):
        """测试获取不存在的容器"""
        # 模拟容器不存在
        self.mock_docker_manager.get_container.side_effect = ContainerNotFoundError("Container not found")

        # 验证抛出异常
        with pytest.raises(ContainerNotFoundError):
            self.container_service.get_container("nonexistent_container")

    def test_get_container_by_name_success(self):
        """测试成功通过名称获取容器"""
        # 模拟列出容器返回匹配的容器
        matching_container = {
            "id": "test_container_123",
            "name": "target-container",
            "status": "running"
        }
        self.mock_docker_manager.list_containers.return_value = [matching_container]

        # 调用方法
        result = self.container_service.get_container_by_name("target-container")

        # 验证结果
        assert result["id"] == "test_container_123"
        assert result["name"] == "target-container"

    def test_get_container_by_name_not_found(self):
        """测试通过名称获取不存在的容器"""
        # 模拟没有匹配的容器
        self.mock_docker_manager.list_containers.return_value = []

        # 验证抛出异常
        with pytest.raises(ContainerNotFoundError, match="Container with name .* not found"):
            self.container_service.get_container_by_name("nonexistent-container")

    def test_container_exists_true(self):
        """测试容器存在检查（存在）"""
        # 模拟容器存在
        self.mock_docker_manager.get_container.return_value = {"id": "test_container"}

        # 调用方法
        result = self.container_service.container_exists("test_container")

        # 验证结果
        assert result is True
        self.mock_docker_manager.get_container.assert_called_once_with("test_container")

    def test_container_exists_false(self):
        """测试容器存在检查（不存在）"""
        # 模拟容器不存在
        self.mock_docker_manager.get_container.side_effect = ContainerNotFoundError("Not found")

        # 调用方法
        result = self.container_service.container_exists("nonexistent_container")

        # 验证结果
        assert result is False

# ====================================
# 容器创建测试
# ====================================

@pytest.mark.unit
class TestContainerServiceCreation(BaseUnitTest):
    """容器服务创建功能测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建容器服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_redis_client = create_mock_redis_client()

        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager,
            redis_client=self.mock_redis_client
        )

        # 测试配置
        self.test_config = SAMPLE_CONTAINER_CONFIG.copy()

    def test_create_container_success(self):
        """测试成功创建容器"""
        # 准备返回数据
        created_container = {
            "id": "new_container_123",
            "name": "test-container",
            "status": "created",
            "image": "centos:7"
        }
        self.mock_docker_manager.create_container.return_value = created_container

        # 调用方法
        result = self.container_service.create_container(self.test_config)

        # 验证结果
        assert result["id"] == "new_container_123"
        assert result["name"] == "test-container"
        assert result["status"] == "created"

        # 验证Docker管理器调用
        self.mock_docker_manager.create_container.assert_called_once()
        call_args = self.mock_docker_manager.create_container.call_args[0][0]
        assert call_args["image"] == "centos:7"
        assert call_args["name"] == "test-container"

    def test_create_container_with_validation(self):
        """测试创建容器时的配置验证"""
        # 准备有效配置
        valid_config = self.test_config.copy()

        # 模拟成功创建
        self.mock_docker_manager.create_container.return_value = {
            "id": "new_container",
            "name": valid_config["name"],
            "status": "created"
        }

        # 调用方法
        result = self.container_service.create_container(valid_config)

        # 验证配置被正确处理
        assert result["name"] == valid_config["name"]
        self.mock_docker_manager.create_container.assert_called_once()

    @parametrize_with_cases([
        {
            "config_key": "image",
            "config_value": "",
            "error_pattern": "Image name.*required"
        },
        {
            "config_key": "name",
            "config_value": "Invalid Container Name!",
            "error_pattern": "Invalid container name"
        },
        {
            "config_key": "memory_limit",
            "config_value": "invalid_memory",
            "error_pattern": "Invalid memory limit format"
        },
        {
            "config_key": "cpu_limit",
            "config_value": -1,
            "error_pattern": "CPU limit must be positive"
        }
    ])
    def test_create_container_validation_errors(self, config_key, config_value, error_pattern):
        """测试创建容器时的验证错误"""
        # 创建无效配置
        invalid_config = self.test_config.copy()
        invalid_config[config_key] = config_value

        # 验证抛出验证错误
        with pytest.raises(ContainerValidationError, match=error_pattern):
            self.container_service.create_container(invalid_config)

        # 验证Docker管理器未被调用
        self.mock_docker_manager.create_container.assert_not_called()

    def test_create_container_duplicate_name(self):
        """测试创建重名容器"""
        # 模拟容器名称已存在
        self.mock_docker_manager.list_containers.return_value = [
            {"id": "existing", "name": "test-container", "status": "running"}
        ]

        # 验证抛出异常
        with pytest.raises(ContainerValidationError, match="Container name .* already exists"):
            self.container_service.create_container(self.test_config)

    def test_create_container_docker_error(self):
        """测试Docker错误时的容器创建"""
        # 模拟Docker创建失败
        self.mock_docker_manager.create_container.side_effect = DockerError("Docker creation failed")

        # 验证抛出服务错误
        with pytest.raises(ContainerServiceError, match="Failed to create container"):
            self.container_service.create_container(self.test_config)

    def test_create_container_with_auto_start(self):
        """测试创建容器并自动启动"""
        # 准备返回数据
        created_container = {
            "id": "new_container_123",
            "name": "test-container",
            "status": "created"
        }
        self.mock_docker_manager.create_container.return_value = created_container
        self.mock_docker_manager.start_container.return_value = True

        # 调用方法（自动启动）
        result = self.container_service.create_container(self.test_config, auto_start=True)

        # 验证容器被创建和启动
        self.mock_docker_manager.create_container.assert_called_once()
        self.mock_docker_manager.start_container.assert_called_once_with("new_container_123")
        assert result["id"] == "new_container_123"

    def test_create_container_batch(self):
        """测试批量创建容器"""
        # 准备多个配置
        configs = []
        for i in range(3):
            config = self.test_config.copy()
            config["name"] = f"batch-container-{i}"
            configs.append(config)

        # 模拟每次创建成功
        def create_side_effect(config):
            return {
                "id": f"container_{config['name']}",
                "name": config["name"],
                "status": "created"
            }

        self.mock_docker_manager.create_container.side_effect = create_side_effect

        # 调用批量创建方法
        results = self.container_service.create_containers_batch(configs)

        # 验证结果
        assert len(results) == 3
        assert all("id" in result for result in results)
        assert self.mock_docker_manager.create_container.call_count == 3

# ====================================
# 容器生命周期管理测试
# ====================================

@pytest.mark.unit
class TestContainerServiceLifecycle(BaseUnitTest):
    """容器服务生命周期管理测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建容器服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_redis_client = create_mock_redis_client()

        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager,
            redis_client=self.mock_redis_client
        )

        # 测试容器ID
        self.test_container_id = "test_container_123"

    def test_start_container_success(self):
        """测试成功启动容器"""
        # 模拟启动成功
        self.mock_docker_manager.start_container.return_value = True

        # 模拟获取更新后的容器信息
        updated_container = {
            "id": self.test_container_id,
            "name": "test-container",
            "status": "running"
        }
        self.mock_docker_manager.get_container.return_value = updated_container

        # 调用方法
        result = self.container_service.start_container(self.test_container_id)

        # 验证结果
        assert result["status"] == "running"

        # 验证调用顺序
        self.mock_docker_manager.start_container.assert_called_once_with(self.test_container_id)
        self.mock_docker_manager.get_container.assert_called_once_with(self.test_container_id)

    def test_start_container_failure(self):
        """测试启动容器失败"""
        # 模拟启动失败
        self.mock_docker_manager.start_container.side_effect = DockerError("Start failed")

        # 验证抛出服务错误
        with pytest.raises(ContainerServiceError, match="Failed to start container"):
            self.container_service.start_container(self.test_container_id)

    def test_stop_container_success(self):
        """测试成功停止容器"""
        # 模拟停止成功
        self.mock_docker_manager.stop_container.return_value = True

        # 模拟获取更新后的容器信息
        updated_container = {
            "id": self.test_container_id,
            "name": "test-container",
            "status": "stopped"
        }
        self.mock_docker_manager.get_container.return_value = updated_container

        # 调用方法
        result = self.container_service.stop_container(self.test_container_id, timeout=30)

        # 验证结果
        assert result["status"] == "stopped"

        # 验证调用参数
        self.mock_docker_manager.stop_container.assert_called_once_with(self.test_container_id, timeout=30)

    def test_restart_container_success(self):
        """测试成功重启容器"""
        # 模拟重启成功
        self.mock_docker_manager.restart_container.return_value = True

        # 模拟获取更新后的容器信息
        updated_container = {
            "id": self.test_container_id,
            "name": "test-container",
            "status": "running"
        }
        self.mock_docker_manager.get_container.return_value = updated_container

        # 调用方法
        result = self.container_service.restart_container(self.test_container_id, timeout=30)

        # 验证结果
        assert result["status"] == "running"
        self.mock_docker_manager.restart_container.assert_called_once_with(self.test_container_id, timeout=30)

    def test_pause_unpause_container(self):
        """测试暂停和恢复容器"""
        # 测试暂停
        self.mock_docker_manager.pause_container.return_value = True
        paused_container = {
            "id": self.test_container_id,
            "status": "paused"
        }
        self.mock_docker_manager.get_container.return_value = paused_container

        result = self.container_service.pause_container(self.test_container_id)
        assert result["status"] == "paused"
        self.mock_docker_manager.pause_container.assert_called_once_with(self.test_container_id)

        # 测试恢复
        self.mock_docker_manager.unpause_container.return_value = True
        running_container = {
            "id": self.test_container_id,
            "status": "running"
        }
        self.mock_docker_manager.get_container.return_value = running_container

        result = self.container_service.unpause_container(self.test_container_id)
        assert result["status"] == "running"
        self.mock_docker_manager.unpause_container.assert_called_once_with(self.test_container_id)

    def test_remove_container_success(self):
        """测试成功删除容器"""
        # 模拟删除成功
        self.mock_docker_manager.remove_container.return_value = True

        # 调用方法
        result = self.container_service.remove_container(self.test_container_id, force=True)

        # 验证结果
        assert result is True
        self.mock_docker_manager.remove_container.assert_called_once_with(self.test_container_id, force=True)

    def test_remove_container_running_without_force(self):
        """测试删除运行中容器但不使用强制"""
        # 模拟获取运行中容器
        running_container = {
            "id": self.test_container_id,
            "status": "running"
        }
        self.mock_docker_manager.get_container.return_value = running_container

        # 验证抛出验证错误
        with pytest.raises(ContainerValidationError, match="Cannot remove running container"):
            self.container_service.remove_container(self.test_container_id, force=False)

    def test_kill_container_success(self):
        """测试成功强制终止容器"""
        # 模拟强制终止成功
        self.mock_docker_manager.kill_container.return_value = True

        # 模拟获取更新后的容器信息
        killed_container = {
            "id": self.test_container_id,
            "status": "exited"
        }
        self.mock_docker_manager.get_container.return_value = killed_container

        # 调用方法
        result = self.container_service.kill_container(self.test_container_id, signal="SIGKILL")

        # 验证结果
        assert result["status"] == "exited"
        self.mock_docker_manager.kill_container.assert_called_once_with(self.test_container_id, signal="SIGKILL")

# ====================================
# 容器监控和统计测试
# ====================================

@pytest.mark.unit
class TestContainerServiceMonitoring(BaseUnitTest):
    """容器服务监控功能测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建容器服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_redis_client = create_mock_redis_client()

        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager,
            redis_client=self.mock_redis_client
        )

        self.test_container_id = "test_container_123"

    def test_get_container_stats(self):
        """测试获取容器统计信息"""
        # 准备统计数据
        mock_stats = {
            "memory_usage": 100 * 1024 * 1024,  # 100MB
            "memory_limit": 512 * 1024 * 1024,  # 512MB
            "cpu_usage": 25.5,  # 25.5%
            "network_rx": 1024,
            "network_tx": 512,
            "disk_read": 2048,
            "disk_write": 1024
        }
        self.mock_docker_manager.get_container_stats.return_value = mock_stats

        # 调用方法
        result = self.container_service.get_container_stats(self.test_container_id)

        # 验证结果
        assert result["memory_usage"] == 100 * 1024 * 1024
        assert result["cpu_usage"] == 25.5
        assert "memory_percentage" in result  # 服务层计算的百分比

        self.mock_docker_manager.get_container_stats.assert_called_once_with(self.test_container_id)

    def test_get_container_logs(self):
        """测试获取容器日志"""
        # 准备日志数据
        mock_logs = "2025-07-01T10:00:00Z INFO Starting application\n2025-07-01T10:00:01Z INFO Application started"
        self.mock_docker_manager.get_container_logs.return_value = mock_logs

        # 调用方法
        result = self.container_service.get_container_logs(
            self.test_container_id,
            tail=100,
            since="2025-07-01T09:00:00Z",
            follow=False
        )

        # 验证结果
        assert "INFO Starting application" in result
        assert "INFO Application started" in result

        # 验证调用参数
        self.mock_docker_manager.get_container_logs.assert_called_once()
        call_kwargs = self.mock_docker_manager.get_container_logs.call_args.kwargs
        assert call_kwargs["tail"] == 100
        assert call_kwargs["since"] == "2025-07-01T09:00:00Z"
        assert call_kwargs["follow"] is False

    def test_get_container_processes(self):
        """测试获取容器进程列表"""
        # 准备进程数据
        mock_processes = [
            ["root", "1", "0", "0.0", "0.1", "bash"],
            ["root", "123", "1", "0.1", "0.2", "python", "app.py"]
        ]
        self.mock_docker_manager.get_container_processes.return_value = mock_processes

        # 调用方法
        result = self.container_service.get_container_processes(self.test_container_id)

        # 验证结果
        assert len(result) == 2
        assert result[0]["pid"] == "1"
        assert result[1]["command"] == "python app.py"

        self.mock_docker_manager.get_container_processes.assert_called_once_with(self.test_container_id)

    def test_inspect_container_detailed(self):
        """测试获取容器详细信息"""
        # 准备详细信息
        mock_inspect = {
            "id": self.test_container_id,
            "name": "test-container",
            "status": "running",
            "image": "centos:7",
            "created_at": "2025-07-01T10:00:00Z",
            "started_at": "2025-07-01T10:00:05Z",
            "config": {
                "environment": {"ENV": "test"},
                "ports": {"80/tcp": 8080},
                "volumes": {"/host": "/container"}
            },
            "network_settings": {
                "ip_address": "172.17.0.2",
                "ports": {"80/tcp": [{"HostPort": "8080"}]}
            },
            "mounts": []
        }
        self.mock_docker_manager.get_container.return_value = mock_inspect

        # 调用方法
        result = self.container_service.inspect_container(self.test_container_id)

        # 验证结果包含详细信息
        assert result["id"] == self.test_container_id
        assert result["network_settings"]["ip_address"] == "172.17.0.2"
        assert "uptime" in result  # 服务层计算的运行时间

        self.mock_docker_manager.get_container.assert_called_once_with(self.test_container_id)

    def test_get_container_health_status(self):
        """测试获取容器健康状态"""
        # 准备健康检查数据
        mock_container = {
            "id": self.test_container_id,
            "status": "running",
            "health_status": "healthy",
            "health_check": {
                "status": "healthy",
                "failing_streak": 0,
                "log": [
                    {"start": "2025-07-01T10:00:00Z", "end": "2025-09-01T10:00:01Z", "exit_code": 0}
                ]
            }
        }
        self.mock_docker_manager.get_container.return_value = mock_container

        # 调用方法
        result = self.container_service.get_container_health(self.test_container_id)

        # 验证结果
        assert result["status"] == "healthy"
        assert result["failing_streak"] == 0
        assert len(result["recent_checks"]) == 1

# ====================================
# 容器执行和交互测试
# ====================================

@pytest.mark.unit
class TestContainerServiceExecution(BaseUnitTest):
    """容器服务执行功能测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建容器服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_redis_client = create_mock_redis_client()

        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager,
            redis_client=self.mock_redis_client
        )

        self.test_container_id = "test_container_123"

    def test_exec_command_success(self):
        """测试在容器中成功执行命令"""
        # 准备执行结果
        self.mock_docker_manager.exec_in_container.return_value = (0, "Hello World")

        # 调用方法
        result = self.container_service.exec_command(
            self.test_container_id,
            ["echo", "Hello World"],
            user="root",
            workdir="/tmp"
        )

        # 验证结果
        assert result["exit_code"] == 0
        assert result["output"] == "Hello World"
        assert result["success"] is True

        # 验证调用参数
        self.mock_docker_manager.exec_in_container.assert_called_once_with(
            self.test_container_id,
            ["echo", "Hello World"],
            user="root",
            workdir="/tmp"
        )

    def test_exec_command_failure(self):
        """测试在容器中执行命令失败"""
        # 准备执行结果
        self.mock_docker_manager.exec_in_container.return_value = (1, "Command not found")

        # 调用方法
        result = self.container_service.exec_command(
            self.test_container_id,
            ["nonexistent-command"]
        )

        # 验证结果
        assert result["exit_code"] == 1
        assert result["output"] == "Command not found"
        assert result["success"] is False

    def test_copy_file_to_container(self):
        """测试复制文件到容器"""
        # 模拟复制成功
        self.mock_docker_manager.copy_to_container.return_value = True

        # 调用方法
        result = self.container_service.copy_file_to_container(
            self.test_container_id,
            "/host/source/file.txt",
            "/container/dest/file.txt"
        )

        # 验证结果
        assert result is True
        self.mock_docker_manager.copy_to_container.assert_called_once_with(
            self.test_container_id,
            "/host/source/file.txt",
            "/container/dest/file.txt"
        )

    def test_copy_file_from_container(self):
        """测试从容器复制文件"""
        # 模拟复制成功
        self.mock_docker_manager.copy_from_container.return_value = b"file content"

        # 调用方法
        result = self.container_service.copy_file_from_container(
            self.test_container_id,
            "/container/source/file.txt",
            "/host/dest/file.txt"
        )

        # 验证结果
        assert result == b"file content"
        self.mock_docker_manager.copy_from_container.assert_called_once_with(
            self.test_container_id,
            "/container/source/file.txt",
            "/host/dest/file.txt"
        )

# ====================================
# 容器批量操作测试
# ====================================

@pytest.mark.unit
class TestContainerServiceBatchOperations(BaseUnitTest):
    """容器服务批量操作测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建容器服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_redis_client = create_mock_redis_client()

        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager,
            redis_client=self.mock_redis_client
        )

    def test_start_multiple_containers_success(self):
        """测试成功启动多个容器"""
        # 准备容器ID列表
        container_ids = ["container_1", "container_2", "container_3"]

        # 模拟每次启动成功
        self.mock_docker_manager.start_container.return_value = True

        # 模拟获取容器信息
        def get_container_side_effect(container_id):
            return {"id": container_id, "status": "running"}
        self.mock_docker_manager.get_container.side_effect = get_container_side_effect

        # 调用方法
        results = self.container_service.start_containers_batch(container_ids)

        # 验证结果
        assert len(results) == 3
        assert all(result["status"] == "running" for result in results)
        assert self.mock_docker_manager.start_container.call_count == 3

    def test_stop_multiple_containers_with_partial_failure(self):
        """测试停止多个容器（部分失败）"""
        # 准备容器ID列表
        container_ids = ["container_1", "container_2", "container_3"]

        # 模拟部分成功部分失败
        def stop_side_effect(container_id, timeout=None):
            if container_id == "container_2":
                raise DockerError("Stop failed")
            return True

        self.mock_docker_manager.stop_container.side_effect = stop_side_effect

        # 模拟获取容器信息
        def get_container_side_effect(container_id):
            status = "stopped" if container_id != "container_2" else "running"
            return {"id": container_id, "status": status}
        self.mock_docker_manager.get_container.side_effect = get_container_side_effect

        # 调用方法
        results = self.container_service.stop_containers_batch(container_ids, ignore_errors=True)

        # 验证结果
        assert len(results) == 3
        success_count = sum(1 for r in results if r.get("success", True))
        assert success_count == 2  # 2个成功，1个失败

    def test_remove_multiple_containers_force(self):
        """测试强制删除多个容器"""
        # 准备容器ID列表
        container_ids = ["container_1", "container_2"]

        # 模拟删除成功
        self.mock_docker_manager.remove_container.return_value = True

        # 调用方法
        results = self.container_service.remove_containers_batch(container_ids, force=True)

        # 验证结果
        assert len(results) == 2
        assert all(result is True for result in results)

        # 验证每次调用都使用force=True
        for call in self.mock_docker_manager.remove_container.call_args_list:
            assert call.kwargs["force"] is True

# ====================================
# 容器事件处理测试
# ====================================

@pytest.mark.unit
class TestContainerEventHandler(BaseUnitTest):
    """容器事件处理器测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建mock依赖
        self.mock_container_service = Mock(spec=ContainerService)
        self.mock_redis_client = create_mock_redis_client()
        self.mock_logger = Mock()

        # 创建事件处理器
        self.event_handler = ContainerEventHandler(
            container_service=self.mock_container_service,
            redis_client=self.mock_redis_client,
            logger=self.mock_logger
        )

    def test_handle_container_created_event(self):
        """测试处理容器创建事件"""
        # 准备事件数据
        event_data = {
            "action": "create",
            "container_id": "new_container_123",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # 调用事件处理
        self.event_handler.handle_container_event(event_data)

        # 验证日志记录
        self.mock_logger.info.assert_called()

        # 验证Redis缓存更新
        self.mock_redis_client.hset.assert_called()

    def test_handle_container_started_event(self):
        """测试处理容器启动事件"""
        # 准备事件数据
        event_data = {
            "action": "start",
            "container_id": "running_container_123",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # 调用事件处理
        self.event_handler.handle_container_event(event_data)

        # 验证状态更新
        self.mock_redis_client.hset.assert_called()

    def test_handle_container_stopped_event(self):
        """测试处理容器停止事件"""
        # 准备事件数据
        event_data = {
            "action": "stop",
            "container_id": "stopped_container_123",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # 调用事件处理
        self.event_handler.handle_container_event(event_data)

        # 验证状态更新
        self.mock_redis_client.hset.assert_called()

    def test_handle_container_removed_event(self):
        """测试处理容器删除事件"""
        # 准备事件数据
        event_data = {
            "action": "destroy",
            "container_id": "removed_container_123",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # 调用事件处理
        self.event_handler.handle_container_event(event_data)

        # 验证缓存清理
        self.mock_redis_client.hdel.assert_called()

    @pytest.mark.asyncio
    async def test_async_event_processing(self):
        """测试异步事件处理"""
        # 创建异步事件处理器
        async_handler = ContainerEventHandler(
            container_service=self.mock_container_service,
            redis_client=self.mock_redis_client,
            logger=self.mock_logger
        )

        # 准备事件队列
        events = [
            {"action": "create", "container_id": "c1"},
            {"action": "start", "container_id": "c1"},
            {"action": "stop", "container_id": "c1"}
        ]

        # 模拟异步处理事件
        for event in events:
            await async_handler.handle_event_async(event)

        # 验证所有事件都被处理
        assert self.mock_logger.info.call_count == len(events)

# ====================================
# 配置验证测试
# ====================================

@pytest.mark.unit
class TestContainerConfigValidation(BaseUnitTest):
    """容器配置验证测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建容器服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager
        )

        self.base_config = SAMPLE_CONTAINER_CONFIG.copy()

    def test_validate_container_name_valid(self):
        """测试有效容器名称验证"""
        valid_names = BOUNDARY_TEST_DATA["container_names"]["valid"]

        for name in valid_names:
            config = self.base_config.copy()
            config["name"] = name
            # 应该不抛出异常
            self.container_service._validate_container_config(config)

    def test_validate_container_name_invalid(self):
        """测试无效容器名称验证"""
        invalid_names = BOUNDARY_TEST_DATA["container_names"]["invalid"]

        for name in invalid_names:
            config = self.base_config.copy()
            config["name"] = name

            with pytest.raises(ContainerValidationError):
                self.container_service._validate_container_config(config)

    def test_validate_port_mapping_valid(self):
        """测试有效端口映射验证"""
        valid_ports = BOUNDARY_TEST_DATA["port_numbers"]["valid"]

        for port in valid_ports:
            config = self.base_config.copy()
            config["ports"] = {f"{port}/tcp": port + 1000}
            # 应该不抛出异常
            self.container_service._validate_container_config(config)

    def test_validate_port_mapping_invalid(self):
        """测试无效端口映射验证"""
        invalid_ports = BOUNDARY_TEST_DATA["port_numbers"]["invalid"]

        for port in invalid_ports:
            config = self.base_config.copy()
            config["ports"] = {f"{port}/tcp": 8080}

            with pytest.raises(ContainerValidationError):
                self.container_service._validate_container_config(config)

    def test_validate_memory_limit_valid(self):
        """测试有效内存限制验证"""
        valid_limits = BOUNDARY_TEST_DATA["memory_limits"]["valid"]

        for limit in valid_limits:
            config = self.base_config.copy()
            config["memory_limit"] = limit
            # 应该不抛出异常
            self.container_service._validate_container_config(config)

    def test_validate_memory_limit_invalid(self):
        """测试无效内存限制验证"""
        invalid_limits = BOUNDARY_TEST_DATA["memory_limits"]["invalid"]

        for limit in invalid_limits:
            config = self.base_config.copy()
            config["memory_limit"] = limit

            with pytest.raises(ContainerValidationError):
                self.container_service._validate_container_config(config)

# ====================================
# 缓存和性能测试
# ====================================

@pytest.mark.unit
class TestContainerServiceCaching(BaseUnitTest):
    """容器服务缓存功能测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建容器服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_redis_client = create_mock_redis_client()

        self.container_service = ContainerService(
            docker_manager=self.mock_docker_manager,
            redis_client=self.mock_redis_client,
            enable_caching=True,
            cache_ttl=300
        )

    def test_get_container_with_cache_miss(self):
        """测试缓存未命中时获取容器"""
        # 模拟缓存未命中
        self.mock_redis_client.hget.return_value = None

        # 模拟Docker管理器返回
        container_data = {"id": "test_container", "name": "test", "status": "running"}
        self.mock_docker_manager.get_container.return_value = container_data

        # 调用方法
        result = self.container_service.get_container("test_container")

        # 验证从Docker获取数据
        self.mock_docker_manager.get_container.assert_called_once_with("test_container")

        # 验证数据被缓存
        self.mock_redis_client.hset.assert_called()

        assert result["id"] == "test_container"

    def test_get_container_with_cache_hit(self):
        """测试缓存命中时获取容器"""
        # 模拟缓存命中
        cached_data = json.dumps({"id": "test_container", "name": "test", "status": "running"})
        self.mock_redis_client.hget.return_value = cached_data

        # 调用方法
        result = self.container_service.get_container("test_container")

        # 验证未从Docker获取数据
        self.mock_docker_manager.get_container.assert_not_called()

        # 验证返回缓存数据
        assert result["id"] == "test_container"

    def test_invalidate_container_cache(self):
        """测试使容器缓存失效"""
        container_id = "test_container"

        # 调用缓存失效方法
        self.container_service.invalidate_container_cache(container_id)

        # 验证Redis删除缓存
        self.mock_redis_client.hdel.assert_called()

    def test_cache_container_list(self):
        """测试缓存容器列表"""
        # 准备容器列表数据
        containers_data = generate_test_container_data(5)
        self.mock_docker_manager.list_containers.return_value = containers_data

        # 模拟缓存未命中
        self.mock_redis_client.get.return_value = None

        # 调用方法
        result = self.container_service.list_containers(include_stopped=True)

        # 验证从Docker获取数据
        self.mock_docker_manager.list_containers.assert_called_once()

        # 验证列表被缓存
        self.mock_redis_client.setex.assert_called()

        assert len(result) == 5