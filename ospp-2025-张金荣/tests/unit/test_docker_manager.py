"""
Docker管理器单元测试

******OSPP-2025-张金荣******

测试core.docker_manager模块的功能，包括：
- Docker客户端连接管理
- 容器生命周期操作
- 镜像管理
- 网络管理
- 卷管理
- 错误处理和异常情况
- 资源清理

版本: 1.0.0
作者: 张金荣
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch, call
from typing import Dict, List, Any, Optional
import docker
from docker.errors import DockerException, APIError, ImageNotFound, NotFound

# 导入测试工具
from tests.unit import (
    BaseUnitTest,
    create_mock_docker_client,
    create_mock_container,
    create_mock_image,
    create_mock_network,
    create_mock_volume,
    generate_test_container_data,
    assert_dict_subset,
    parametrize_with_cases
)

# 导入被测试的模块
try:
    from core.docker_manager import DockerManager, DockerClientPool
    from utils.exceptions import DockerError, ContainerNotFoundError
    from utils.logger import get_logger
    from config.settings import get_settings
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入被测试模块: {e}")
    IMPORTS_AVAILABLE = False

# 跳过测试如果导入失败
pytestmark = pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="被测试模块不可用")

# ====================================
# Docker管理器基础测试
# ====================================

@pytest.mark.unit
class TestDockerManager(BaseUnitTest):
    """Docker管理器测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建mock Docker客户端
        self.mock_docker_client = create_mock_docker_client()

        # Mock docker.from_env函数
        self.mock_from_env = self.create_patch('docker.from_env')
        self.mock_from_env.return_value = self.mock_docker_client

        # Mock 设置
        self.mock_settings = self.create_patch('core.docker_manager.get_settings')
        self.mock_settings.return_value = Mock(
            DOCKER_HOST="unix:///var/run/docker.sock",
            DOCKER_TIMEOUT=30,
            DOCKER_POOL_SIZE=5
        )

        # 创建Docker管理器实例
        self.docker_manager = DockerManager()

    def test_docker_manager_initialization(self):
        """测试Docker管理器初始化"""
        # 验证客户端已创建
        assert self.docker_manager.client is not None

        # 验证from_env被调用
        self.mock_from_env.assert_called_once()

        # 验证连接测试
        self.mock_docker_client.ping.assert_called_once()

    def test_docker_manager_initialization_failure(self):
        """测试Docker管理器初始化失败"""
        # 模拟Docker连接失败
        self.mock_from_env.side_effect = DockerException("Connection failed")

        # 验证抛出DockerError异常
        with pytest.raises(DockerError, match="Failed to connect to Docker"):
            DockerManager()

    def test_get_client_info(self):
        """测试获取Docker客户端信息"""
        # 设置返回值
        expected_info = {
            "Version": "20.10.21",
            "ApiVersion": "1.41",
            "Containers": 5,
            "Images": 10
        }
        self.mock_docker_client.version.return_value = {"Version": "20.10.21", "ApiVersion": "1.41"}
        self.mock_docker_client.info.return_value = {"Containers": 5, "Images": 10}

        # 调用方法
        info = self.docker_manager.get_client_info()

        # 验证结果
        assert_dict_subset(info, expected_info)
        self.mock_docker_client.version.assert_called_once()
        self.mock_docker_client.info.assert_called_once()

    def test_is_connected(self):
        """测试连接状态检查"""
        # 测试连接正常
        self.mock_docker_client.ping.return_value = True
        assert self.docker_manager.is_connected() is True

        # 测试连接失败
        self.mock_docker_client.ping.side_effect = DockerException("Connection lost")
        assert self.docker_manager.is_connected() is False

    def test_reconnect(self):
        """测试重新连接"""
        # 创建新的mock客户端
        new_mock_client = create_mock_docker_client()
        self.mock_from_env.return_value = new_mock_client

        # 调用重新连接
        result = self.docker_manager.reconnect()

        # 验证结果
        assert result is True
        assert self.docker_manager.client == new_mock_client
        new_mock_client.ping.assert_called_once()

    def test_reconnect_failure(self):
        """测试重新连接失败"""
        # 模拟重连失败
        self.mock_from_env.side_effect = DockerException("Reconnection failed")

        # 调用重新连接
        result = self.docker_manager.reconnect()

        # 验证结果
        assert result is False

# ====================================
# 容器管理测试
# ====================================

@pytest.mark.unit
class TestDockerManagerContainers(BaseUnitTest):
    """Docker管理器容器操作测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建Docker管理器
        self.mock_docker_client = create_mock_docker_client()
        self.mock_from_env = self.create_patch('docker.from_env')
        self.mock_from_env.return_value = self.mock_docker_client

        self.mock_settings = self.create_patch('core.docker_manager.get_settings')
        self.mock_settings.return_value = Mock(
            DOCKER_HOST="unix:///var/run/docker.sock",
            DOCKER_TIMEOUT=30
        )

        self.docker_manager = DockerManager()

        # 测试数据
        self.container_config = {
            "image": "centos:7",
            "name": "test-container",
            "command": ["bash"],
            "environment": {"ENV": "test"},
            "ports": {"80/tcp": 8080},
            "volumes": {"/host": "/container"},
            "working_dir": "/workspace",
            "user": "root"
        }

    def test_list_containers_all(self):
        """测试列出所有容器"""
        # 准备测试数据
        mock_containers = [
            create_mock_container("container_1", "test1", "running"),
            create_mock_container("container_2", "test2", "stopped")
        ]
        self.mock_docker_client.containers.list.return_value = mock_containers

        # 调用方法
        containers = self.docker_manager.list_containers(all=True)

        # 验证结果
        assert len(containers) == 2
        assert containers[0]["name"] == "test1"
        assert containers[1]["name"] == "test2"
        self.mock_docker_client.containers.list.assert_called_once_with(all=True)

    def test_list_containers_running_only(self):
        """测试列出运行中的容器"""
        # 准备测试数据
        mock_containers = [create_mock_container("container_1", "test1", "running")]
        self.mock_docker_client.containers.list.return_value = mock_containers

        # 调用方法
        containers = self.docker_manager.list_containers(all=False)

        # 验证结果
        assert len(containers) == 1
        assert containers[0]["status"] == "running"
        self.mock_docker_client.containers.list.assert_called_once_with(all=False)

    def test_get_container_by_id(self):
        """测试通过ID获取容器"""
        # 准备测试数据
        container_id = "test_container_123"
        mock_container = create_mock_container(container_id, "test-container", "running")
        self.mock_docker_client.containers.get.return_value = mock_container

        # 调用方法
        container = self.docker_manager.get_container(container_id)

        # 验证结果
        assert container["id"] == container_id
        assert container["name"] == "test-container"
        self.mock_docker_client.containers.get.assert_called_once_with(container_id)

    def test_get_container_not_found(self):
        """测试获取不存在的容器"""
        # 模拟容器不存在
        self.mock_docker_client.containers.get.side_effect = NotFound("Container not found")

        # 验证抛出异常
        with pytest.raises(ContainerNotFoundError):
            self.docker_manager.get_container("nonexistent")

    def test_create_container_success(self):
        """测试成功创建容器"""
        # 准备返回值
        mock_container = create_mock_container("new_container", "test-container", "created")
        self.mock_docker_client.containers.create.return_value = mock_container

        # 调用方法
        container = self.docker_manager.create_container(self.container_config)

        # 验证结果
        assert container["id"] == "new_container"
        assert container["name"] == "test-container"
        assert container["status"] == "created"

        # 验证调用参数
        self.mock_docker_client.containers.create.assert_called_once()
        call_kwargs = self.mock_docker_client.containers.create.call_args.kwargs

        assert call_kwargs["image"] == "centos:7"
        assert call_kwargs["name"] == "test-container"
        assert call_kwargs["command"] == ["bash"]
        assert call_kwargs["environment"] == {"ENV": "test"}
        assert call_kwargs["ports"] == {"80/tcp": 8080}
        assert call_kwargs["volumes"] == {"/host": {"bind": "/container", "mode": "rw"}}

    @parametrize_with_cases([
        {"config_key": "image", "config_value": "", "error_pattern": "Image name cannot be empty"},
        {"config_key": "name", "config_value": "Invalid Name", "error_pattern": "Invalid container name"},
        {"config_key": "ports", "config_value": {"invalid": 8080}, "error_pattern": "Invalid port format"},
        {"config_key": "memory_limit", "config_value": "invalid", "error_pattern": "Invalid memory limit"},
    ])
    def test_create_container_validation_errors(self, config_key, config_value, error_pattern):
        """测试创建容器时的验证错误"""
        # 修改配置引入错误
        invalid_config = self.container_config.copy()
        invalid_config[config_key] = config_value

        # 验证抛出DockerError异常
        with pytest.raises(DockerError, match=error_pattern):
            self.docker_manager.create_container(invalid_config)

    def test_create_container_docker_api_error(self):
        """测试创建容器时的Docker API错误"""
        # 模拟Docker API错误
        self.mock_docker_client.containers.create.side_effect = APIError("API Error")

        # 验证抛出DockerError异常
        with pytest.raises(DockerError, match="Failed to create container"):
            self.docker_manager.create_container(self.container_config)

    def test_start_container_success(self):
        """测试成功启动容器"""
        # 准备mock容器
        mock_container = create_mock_container("test_container", "test", "created")
        self.mock_docker_client.containers.get.return_value = mock_container

        # 调用方法
        result = self.docker_manager.start_container("test_container")

        # 验证结果
        assert result is True
        mock_container.start.assert_called_once()
        mock_container.reload.assert_called_once()

    def test_start_container_not_found(self):
        """测试启动不存在的容器"""
        # 模拟容器不存在
        self.mock_docker_client.containers.get.side_effect = NotFound("Container not found")

        # 验证抛出异常
        with pytest.raises(ContainerNotFoundError):
            self.docker_manager.start_container("nonexistent")

    def test_stop_container_success(self):
        """测试成功停止容器"""
        # 准备mock容器
        mock_container = create_mock_container("test_container", "test", "running")
        self.mock_docker_client.containers.get.return_value = mock_container

        # 调用方法
        result = self.docker_manager.stop_container("test_container", timeout=10)

        # 验证结果
        assert result is True
        mock_container.stop.assert_called_once_with(timeout=10)
        mock_container.reload.assert_called_once()

    def test_restart_container_success(self):
        """测试成功重启容器"""
        # 准备mock容器
        mock_container = create_mock_container("test_container", "test", "running")
        self.mock_docker_client.containers.get.return_value = mock_container

        # 调用方法
        result = self.docker_manager.restart_container("test_container", timeout=10)

        # 验证结果
        assert result is True
        mock_container.restart.assert_called_once_with(timeout=10)
        mock_container.reload.assert_called_once()

    def test_remove_container_success(self):
        """测试成功删除容器"""
        # 准备mock容器
        mock_container = create_mock_container("test_container", "test", "stopped")
        self.mock_docker_client.containers.get.return_value = mock_container

        # 调用方法
        result = self.docker_manager.remove_container("test_container", force=True)

        # 验证结果
        assert result is True
        mock_container.remove.assert_called_once_with(force=True)

    def test_pause_unpause_container(self):
        """测试暂停和恢复容器"""
        # 准备mock容器
        mock_container = create_mock_container("test_container", "test", "running")
        self.mock_docker_client.containers.get.return_value = mock_container

        # 测试暂停
        result = self.docker_manager.pause_container("test_container")
        assert result is True
        mock_container.pause.assert_called_once()

        # 测试恢复
        result = self.docker_manager.unpause_container("test_container")
        assert result is True
        mock_container.unpause.assert_called_once()

    def test_get_container_logs(self):
        """测试获取容器日志"""
        # 准备mock容器和日志
        mock_container = create_mock_container("test_container", "test", "running")
        mock_container.logs.return_value = b"test log line 1\ntest log line 2"
        self.mock_docker_client.containers.get.return_value = mock_container

        # 调用方法
        logs = self.docker_manager.get_container_logs(
            "test_container",
            tail=100,
            follow=False,
            timestamps=True
        )

        # 验证结果
        assert logs == "test log line 1\ntest log line 2"
        mock_container.logs.assert_called_once_with(
            tail=100,
            follow=False,
            timestamps=True
        )

    def test_get_container_stats(self):
        """测试获取容器统计信息"""
        # 准备mock容器和统计数据
        mock_container = create_mock_container("test_container", "test", "running")
        mock_stats = {
            "memory": {"usage": 1024*1024*100, "limit": 1024*1024*512},
            "cpu_stats": {"cpu_usage": {"total_usage": 1000000000}},
            "networks": {"eth0": {"rx_bytes": 1024, "tx_bytes": 512}}
        }
        mock_container.stats.return_value = mock_stats
        self.mock_docker_client.containers.get.return_value = mock_container

        # 调用方法
        stats = self.docker_manager.get_container_stats("test_container")

        # 验证结果
        assert "memory_usage" in stats
        assert "memory_limit" in stats
        assert "cpu_usage" in stats
        assert "network_rx" in stats
        assert "network_tx" in stats

        mock_container.stats.assert_called_once_with(stream=False)

    def test_exec_in_container(self):
        """测试在容器中执行命令"""
        # 准备mock容器
        mock_container = create_mock_container("test_container", "test", "running")
        mock_container.exec_run.return_value = (0, b"command output")
        self.mock_docker_client.containers.get.return_value = mock_container

        # 调用方法
        exit_code, output = self.docker_manager.exec_in_container(
            "test_container",
            ["echo", "hello"],
            workdir="/tmp",
            user="root"
        )

        # 验证结果
        assert exit_code == 0
        assert output == "command output"
        mock_container.exec_run.assert_called_once_with(
            ["echo", "hello"],
            workdir="/tmp",
            user="root"
        )

# ====================================
# 镜像管理测试
# ====================================

@pytest.mark.unit
class TestDockerManagerImages(BaseUnitTest):
    """Docker管理器镜像操作测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建Docker管理器
        self.mock_docker_client = create_mock_docker_client()
        self.mock_from_env = self.create_patch('docker.from_env')
        self.mock_from_env.return_value = self.mock_docker_client

        self.mock_settings = self.create_patch('core.docker_manager.get_settings')
        self.mock_settings.return_value = Mock(DOCKER_HOST="unix:///var/run/docker.sock")

        self.docker_manager = DockerManager()

    def test_list_images(self):
        """测试列出镜像"""
        # 准备测试数据
        mock_images = [
            create_mock_image("image_1", ["centos:7"]),
            create_mock_image("image_2", ["ubuntu:20.04"])
        ]
        self.mock_docker_client.images.list.return_value = mock_images

        # 调用方法
        images = self.docker_manager.list_images()

        # 验证结果
        assert len(images) == 2
        assert images[0]["tags"] == ["centos:7"]
        assert images[1]["tags"] == ["ubuntu:20.04"]
        self.mock_docker_client.images.list.assert_called_once()

    def test_get_image_by_tag(self):
        """测试通过标签获取镜像"""
        # 准备测试数据
        mock_image = create_mock_image("image_123", ["centos:7"])
        self.mock_docker_client.images.get.return_value = mock_image

        # 调用方法
        image = self.docker_manager.get_image("centos:7")

        # 验证结果
        assert image["id"] == "image_123"
        assert "centos:7" in image["tags"]
        self.mock_docker_client.images.get.assert_called_once_with("centos:7")

    def test_get_image_not_found(self):
        """测试获取不存在的镜像"""
        # 模拟镜像不存在
        self.mock_docker_client.images.get.side_effect = ImageNotFound("Image not found")

        # 验证抛出异常
        with pytest.raises(DockerError, match="Image .* not found"):
            self.docker_manager.get_image("nonexistent:latest")

    def test_pull_image_success(self):
        """测试成功拉取镜像"""
        # 准备返回值
        mock_image = create_mock_image("pulled_image", ["centos:7"])
        self.mock_docker_client.images.pull.return_value = mock_image

        # 调用方法
        image = self.docker_manager.pull_image("centos:7")

        # 验证结果
        assert image["id"] == "pulled_image"
        assert "centos:7" in image["tags"]
        self.mock_docker_client.images.pull.assert_called_once_with("centos:7", tag=None)

    def test_pull_image_with_tag(self):
        """测试拉取指定标签的镜像"""
        # 准备返回值
        mock_image = create_mock_image("pulled_image", ["centos:8"])
        self.mock_docker_client.images.pull.return_value = mock_image

        # 调用方法
        image = self.docker_manager.pull_image("centos", tag="8")

        # 验证结果
        assert "centos:8" in image["tags"]
        self.mock_docker_client.images.pull.assert_called_once_with("centos", tag="8")

    def test_build_image_success(self):
        """测试成功构建镜像"""
        # 准备返回值
        mock_image = create_mock_image("built_image", ["test:latest"])
        build_logs = [
            {"stream": "Step 1/2 : FROM centos:7\n"},
            {"stream": "Step 2/2 : RUN echo hello\n"},
            {"stream": "Successfully built built_image\n"}
        ]
        self.mock_docker_client.images.build.return_value = (mock_image, iter(build_logs))

        # 调用方法
        image, logs = self.docker_manager.build_image(
            path="/build/context",
            tag="test:latest",
            dockerfile="Dockerfile"
        )

        # 验证结果
        assert image["id"] == "built_image"
        assert "test:latest" in image["tags"]
        assert len(logs) == 3

        # 验证调用参数
        self.mock_docker_client.images.build.assert_called_once()
        call_kwargs = self.mock_docker_client.images.build.call_args.kwargs
        assert call_kwargs["path"] == "/build/context"
        assert call_kwargs["tag"] == "test:latest"
        assert call_kwargs["dockerfile"] == "Dockerfile"

    def test_build_image_with_build_args(self):
        """测试使用构建参数构建镜像"""
        # 准备返回值
        mock_image = create_mock_image("built_image", ["test:latest"])
        self.mock_docker_client.images.build.return_value = (mock_image, iter([]))

        # 调用方法
        build_args = {"ARG1": "value1", "ARG2": "value2"}
        image, logs = self.docker_manager.build_image(
            path="/build/context",
            tag="test:latest",
            build_args=build_args,
            no_cache=True
        )

        # 验证调用参数
        call_kwargs = self.mock_docker_client.images.build.call_args.kwargs
        assert call_kwargs["buildargs"] == build_args
        assert call_kwargs["nocache"] is True

    def test_remove_image_success(self):
        """测试成功删除镜像"""
        # 准备mock镜像
        mock_image = create_mock_image("image_123", ["test:latest"])
        self.mock_docker_client.images.get.return_value = mock_image

        # 调用方法
        result = self.docker_manager.remove_image("test:latest", force=True)

        # 验证结果
        assert result is True
        mock_image.remove.assert_called_once_with(force=True)

    def test_tag_image_success(self):
        """测试成功给镜像打标签"""
        # 准备mock镜像
        mock_image = create_mock_image("image_123", ["test:v1.0"])
        mock_image.tag.return_value = True
        self.mock_docker_client.images.get.return_value = mock_image

        # 调用方法
        result = self.docker_manager.tag_image("test:v1.0", "test:latest")

        # 验证结果
        assert result is True
        mock_image.tag.assert_called_once_with("test", "latest")

    def test_save_image(self):
        """测试保存镜像"""
        # 准备mock镜像
        mock_image = create_mock_image("image_123", ["test:latest"])
        mock_image.save.return_value = iter([b"image chunk 1", b"image chunk 2"])
        self.mock_docker_client.images.get.return_value = mock_image

        # 调用方法
        chunks = list(self.docker_manager.save_image("test:latest"))

        # 验证结果
        assert len(chunks) == 2
        assert chunks[0] == b"image chunk 1"
        assert chunks[1] == b"image chunk 2"
        mock_image.save.assert_called_once()

# ====================================
# 网络管理测试
# ====================================

@pytest.mark.unit
class TestDockerManagerNetworks(BaseUnitTest):
    """Docker管理器网络操作测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建Docker管理器
        self.mock_docker_client = create_mock_docker_client()
        self.mock_from_env = self.create_patch('docker.from_env')
        self.mock_from_env.return_value = self.mock_docker_client

        self.mock_settings = self.create_patch('core.docker_manager.get_settings')
        self.mock_settings.return_value = Mock(DOCKER_HOST="unix:///var/run/docker.sock")

        self.docker_manager = DockerManager()

    def test_list_networks(self):
        """测试列出网络"""
        # 准备测试数据
        mock_networks = [
            create_mock_network("network_1", "bridge"),
            create_mock_network("network_2", "custom-network")
        ]
        self.mock_docker_client.networks.list.return_value = mock_networks

        # 调用方法
        networks = self.docker_manager.list_networks()

        # 验证结果
        assert len(networks) == 2
        assert networks[0]["name"] == "bridge"
        assert networks[1]["name"] == "custom-network"
        self.mock_docker_client.networks.list.assert_called_once()

    def test_get_network_by_name(self):
        """测试通过名称获取网络"""
        # 准备测试数据
        mock_network = create_mock_network("network_123", "test-network")
        self.mock_docker_client.networks.get.return_value = mock_network

        # 调用方法
        network = self.docker_manager.get_network("test-network")

        # 验证结果
        assert network["id"] == "network_123"
        assert network["name"] == "test-network"
        self.mock_docker_client.networks.get.assert_called_once_with("test-network")

    def test_create_network_success(self):
        """测试成功创建网络"""
        # 准备返回值
        mock_network = create_mock_network("new_network", "test-network")
        self.mock_docker_client.networks.create.return_value = mock_network

        # 网络配置
        network_config = {
            "name": "test-network",
            "driver": "bridge",
            "options": {"com.docker.network.bridge.name": "test-br0"},
            "ipam": {
                "driver": "default",
                "config": [{"subnet": "172.20.0.0/16"}]
            }
        }

        # 调用方法
        network = self.docker_manager.create_network(network_config)

        # 验证结果
        assert network["name"] == "test-network"

        # 验证调用参数
        self.mock_docker_client.networks.create.assert_called_once()
        call_kwargs = self.mock_docker_client.networks.create.call_args.kwargs
        assert call_kwargs["name"] == "test-network"
        assert call_kwargs["driver"] == "bridge"

    def test_remove_network_success(self):
        """测试成功删除网络"""
        # 准备mock网络
        mock_network = create_mock_network("network_123", "test-network")
        self.mock_docker_client.networks.get.return_value = mock_network

        # 调用方法
        result = self.docker_manager.remove_network("test-network")

        # 验证结果
        assert result is True
        mock_network.remove.assert_called_once()

    def test_connect_container_to_network(self):
        """测试连接容器到网络"""
        # 准备mock网络
        mock_network = create_mock_network("network_123", "test-network")
        self.mock_docker_client.networks.get.return_value = mock_network

        # 调用方法
        result = self.docker_manager.connect_container_to_network(
            "container_123",
            "test-network",
            aliases=["app"]
        )

        # 验证结果
        assert result is True
        mock_network.connect.assert_called_once_with("container_123", aliases=["app"])

    def test_disconnect_container_from_network(self):
        """测试从网络断开容器"""
        # 准备mock网络
        mock_network = create_mock_network("network_123", "test-network")
        self.mock_docker_client.networks.get.return_value = mock_network

        # 调用方法
        result = self.docker_manager.disconnect_container_from_network(
            "container_123",
            "test-network"
        )

        # 验证结果
        assert result is True
        mock_network.disconnect.assert_called_once_with("container_123")

# ====================================
# 卷管理测试
# ====================================

@pytest.mark.unit
class TestDockerManagerVolumes(BaseUnitTest):
    """Docker管理器卷操作测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建Docker管理器
        self.mock_docker_client = create_mock_docker_client()
        self.mock_from_env = self.create_patch('docker.from_env')
        self.mock_from_env.return_value = self.mock_docker_client

        self.mock_settings = self.create_patch('core.docker_manager.get_settings')
        self.mock_settings.return_value = Mock(DOCKER_HOST="unix:///var/run/docker.sock")

        self.docker_manager = DockerManager()

    def test_list_volumes(self):
        """测试列出卷"""
        # 准备测试数据
        mock_volumes = [
            create_mock_volume("volume_1"),
            create_mock_volume("volume_2")
        ]
        self.mock_docker_client.volumes.list.return_value = mock_volumes

        # 调用方法
        volumes = self.docker_manager.list_volumes()

        # 验证结果
        assert len(volumes) == 2
        assert volumes[0]["name"] == "volume_1"
        assert volumes[1]["name"] == "volume_2"
        self.mock_docker_client.volumes.list.assert_called_once()

    def test_get_volume_by_name(self):
        """测试通过名称获取卷"""
        # 准备测试数据
        mock_volume = create_mock_volume("test-volume")
        self.mock_docker_client.volumes.get.return_value = mock_volume

        # 调用方法
        volume = self.docker_manager.get_volume("test-volume")

        # 验证结果
        assert volume["name"] == "test-volume"
        self.mock_docker_client.volumes.get.assert_called_once_with("test-volume")

    def test_create_volume_success(self):
        """测试成功创建卷"""
        # 准备返回值
        mock_volume = create_mock_volume("new-volume")
        self.mock_docker_client.volumes.create.return_value = mock_volume

        # 调用方法
        volume = self.docker_manager.create_volume(
            "new-volume",
            driver="local",
            labels={"project": "test"}
        )

        # 验证结果
        assert volume["name"] == "new-volume"

        # 验证调用参数
        self.mock_docker_client.volumes.create.assert_called_once()
        call_kwargs = self.mock_docker_client.volumes.create.call_args.kwargs
        assert call_kwargs["name"] == "new-volume"
        assert call_kwargs["driver"] == "local"
        assert call_kwargs["labels"] == {"project": "test"}

    def test_remove_volume_success(self):
        """测试成功删除卷"""
        # 准备mock卷
        mock_volume = create_mock_volume("test-volume")
        self.mock_docker_client.volumes.get.return_value = mock_volume

        # 调用方法
        result = self.docker_manager.remove_volume("test-volume", force=True)

        # 验证结果
        assert result is True
        mock_volume.remove.assert_called_once_with(force=True)

# ====================================
# 客户端池测试
# ====================================

@pytest.mark.unit
class TestDockerClientPool(BaseUnitTest):
    """Docker客户端池测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # Mock docker.from_env
        self.mock_from_env = self.create_patch('docker.from_env')
        self.mock_from_env.return_value = create_mock_docker_client()

        # Mock 设置
        self.mock_settings = self.create_patch('core.docker_manager.get_settings')
        self.mock_settings.return_value = Mock(
            DOCKER_HOST="unix:///var/run/docker.sock",
            DOCKER_POOL_SIZE=3
        )

    def test_client_pool_initialization(self):
        """测试客户端池初始化"""
        # 创建客户端池
        pool = DockerClientPool(pool_size=3)

        # 验证池大小
        assert pool.pool_size == 3
        assert len(pool._pool) == 3
        assert pool._pool.qsize() == 3

        # 验证所有客户端都已创建
        assert self.mock_from_env.call_count == 3

    def test_get_client_from_pool(self):
        """测试从池中获取客户端"""
        # 创建客户端池
        pool = DockerClientPool(pool_size=2)

        # 获取客户端
        with pool.get_client() as client:
            assert client is not None
            # 池中应该少了一个客户端
            assert pool._pool.qsize() == 1

        # 客户端应该归还到池中
        assert pool._pool.qsize() == 2

    def test_client_pool_concurrent_access(self):
        """测试客户端池并发访问"""
        import threading
        import time

        # 创建客户端池
        pool = DockerClientPool(pool_size=2)
        results = []

        def get_client_task():
            with pool.get_client() as client:
                results.append(client)
                time.sleep(0.1)  # 模拟使用客户端

        # 启动多个线程
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=get_client_task)
            threads.append(thread)
            thread.start()

        # 等待所有线程完成
        for thread in threads:
            thread.join()

        # 验证结果
        assert len(results) == 3
        assert pool._pool.qsize() == 2  # 所有客户端都已归还

    def test_client_pool_cleanup(self):
        """测试客户端池清理"""
        # 创建客户端池
        pool = DockerClientPool(pool_size=2)

        # 获取客户端引用
        clients = []
        while not pool._pool.empty():
            clients.append(pool._pool.get())

        # 清理池
        pool.cleanup()

        # 验证所有客户端的close方法被调用
        for client in clients:
            client.close.assert_called_once()

# ====================================
# 错误处理和边界情况测试
# ====================================

@pytest.mark.unit
class TestDockerManagerErrorHandling(BaseUnitTest):
    """Docker管理器错误处理测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建Docker管理器
        self.mock_docker_client = create_mock_docker_client()
        self.mock_from_env = self.create_patch('docker.from_env')
        self.mock_from_env.return_value = self.mock_docker_client

        self.mock_settings = self.create_patch('core.docker_manager.get_settings')
        self.mock_settings.return_value = Mock(DOCKER_HOST="unix:///var/run/docker.sock")

        self.docker_manager = DockerManager()

    def test_container_operation_with_connection_loss(self):
        """测试连接丢失时的容器操作"""
        # 模拟连接丢失
        self.mock_docker_client.containers.get.side_effect = DockerException("Connection lost")

        # 验证抛出DockerError异常
        with pytest.raises(DockerError, match="Docker operation failed"):
            self.docker_manager.get_container("test_container")

    def test_image_operation_with_permission_error(self):
        """测试权限错误时的镜像操作"""
        # 模拟权限错误
        error_response = Mock()
        error_response.status_code = 403
        self.mock_docker_client.images.build.side_effect = APIError("Permission denied", response=error_response)

        # 验证抛出DockerError异常
        with pytest.raises(DockerError, match="Permission denied"):
            self.docker_manager.build_image(path="/build/context")

    def test_network_operation_with_conflict_error(self):
        """测试冲突错误时的网络操作"""
        # 模拟网络名称冲突
        error_response = Mock()
        error_response.status_code = 409
        self.mock_docker_client.networks.create.side_effect = APIError("Network already exists", response=error_response)

        # 验证抛出DockerError异常
        with pytest.raises(DockerError, match="Network already exists"):
            self.docker_manager.create_network({"name": "existing-network"})

    def test_volume_operation_with_in_use_error(self):
        """测试卷被使用时的删除操作"""
        # 准备mock卷
        mock_volume = create_mock_volume("test-volume")
        mock_volume.remove.side_effect = APIError("Volume in use")
        self.mock_docker_client.volumes.get.return_value = mock_volume

        # 验证抛出DockerError异常
        with pytest.raises(DockerError, match="Volume in use"):
            self.docker_manager.remove_volume("test-volume")

    def test_retry_mechanism_on_temporary_failure(self):
        """测试临时失败时的重试机制"""
        # 模拟临时失败然后成功
        mock_container = create_mock_container("test_container", "test", "running")
        self.mock_docker_client.containers.get.side_effect = [
            DockerException("Temporary failure"),  # 第一次失败
            mock_container  # 第二次成功
        ]

        # 启用重试的获取容器方法
        container = self.docker_manager.get_container("test_container", retry=True, max_retries=2)

        # 验证最终成功获取容器
        assert container["name"] == "test"
        assert self.mock_docker_client.containers.get.call_count == 2

    def test_timeout_handling(self):
        """测试超时处理"""
        import time

        # 模拟超时操作
        def slow_operation(*args, **kwargs):
            time.sleep(0.2)  # 模拟慢操作
            return create_mock_container("test_container", "test", "running")

        self.mock_docker_client.containers.get.side_effect = slow_operation

        # 设置短超时时间
        with pytest.raises(DockerError, match="Operation timed out"):
            self.docker_manager.get_container("test_container", timeout=0.1)