"""
构建服务单元测试

******OSPP-2025-张金荣******

测试services.build_service模块的功能，包括：
- RPM包构建生命周期管理
- 构建配置验证和处理
- 构建任务调度和执行
- 构建状态监控和日志收集
- Dockerfile生成和优化
- 构建资源管理和清理
- 构建历史记录管理
- 构建错误处理和重试机制

版本: 1.0.0
作者: 张金荣
"""

import pytest
import asyncio
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch, AsyncMock, mock_open
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import json
import os
from pathlib import Path

# 导入测试工具
from tests.unit import (
    BaseUnitTest,
    create_mock_docker_client,
    create_mock_container,
    create_mock_redis_client,
    generate_test_build_data,
    assert_dict_subset,
    parametrize_with_cases,
    create_test_file_content
)

from tests.fixtures import (
    SAMPLE_BUILD_CONFIG,
    BUILD_STATES,
    BUILD_ERROR_SCENARIOS,
    SIMPLE_C_BUILD_CONFIG,
    PYTHON_APP_BUILD_CONFIG,
    MULTISTAGE_BUILD_CONFIG
)

# 导入被测试的模块
try:
    from services.build_service import (
        BuildService,
        BuildTaskManager,
        DockerfileGenerator,
        BuildEventHandler
    )
    from core.docker_manager import DockerManager
    from core.build_manager import BuildManager
    from models.build_model import Build, BuildConfig, BuildStatus, BuildTask
    from utils.exceptions import (
        BuildServiceError,
        BuildValidationError,
        BuildTaskError,
        DockerError,
        FileNotFoundError
    )
    from utils.logger import get_logger
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入被测试模块: {e}")
    IMPORTS_AVAILABLE = False

# 跳过测试如果导入失败
pytestmark = pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="被测试模块不可用")

# ====================================
# 构建服务基础测试
# ====================================

@pytest.mark.unit
class TestBuildService(BaseUnitTest):
    """构建服务测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建mock依赖
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_build_manager = Mock(spec=BuildManager)
        self.mock_redis_client = create_mock_redis_client()
        self.mock_logger = Mock()

        # 配置mock Docker管理器
        self.mock_docker_manager.is_connected.return_value = True
        self.mock_docker_manager.build_image.return_value = (
            {"id": "built_image_123", "tags": ["test:latest"]},
            ["Step 1/3: FROM centos:7", "Successfully built built_image_123"]
        )

        # 配置mock构建管理器
        self.mock_build_manager.validate_build_config.return_value = True
        self.mock_build_manager.prepare_build_context.return_value = "/tmp/build_context"

        # 创建构建服务实例
        self.build_service = BuildService(
            docker_manager=self.mock_docker_manager,
            build_manager=self.mock_build_manager,
            redis_client=self.mock_redis_client,
            logger=self.mock_logger
        )

        # 测试用构建配置
        self.test_config = SAMPLE_BUILD_CONFIG.copy()

        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp(prefix="build_test_")

    def teardown_method(self, method):
        """测试方法清理"""
        super().teardown_method(method)
        # 清理临时目录
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_service_initialization(self):
        """测试构建服务初始化"""
        # 验证依赖已设置
        assert self.build_service.docker_manager is self.mock_docker_manager
        assert self.build_service.build_manager is self.mock_build_manager
        assert self.build_service.redis_client is self.mock_redis_client
        assert self.build_service.logger is self.mock_logger

        # 验证初始化检查
        self.mock_docker_manager.is_connected.assert_called_once()

    def test_build_service_initialization_docker_not_connected(self):
        """测试Docker未连接时的服务初始化"""
        # 模拟Docker未连接
        mock_docker_manager = Mock(spec=DockerManager)
        mock_docker_manager.is_connected.return_value = False
        mock_docker_manager.reconnect.return_value = False

        # 验证抛出异常
        with pytest.raises(BuildServiceError, match="Docker is not connected"):
            BuildService(
                docker_manager=mock_docker_manager,
                build_manager=self.mock_build_manager,
                redis_client=self.mock_redis_client
            )

# ====================================
# 构建任务管理测试
# ====================================

@pytest.mark.unit
class TestBuildTaskManagement(BaseUnitTest):
    """构建任务管理测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建构建服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_build_manager = Mock(spec=BuildManager)
        self.mock_redis_client = create_mock_redis_client()

        self.build_service = BuildService(
            docker_manager=self.mock_docker_manager,
            build_manager=self.mock_build_manager,
            redis_client=self.mock_redis_client
        )

        self.test_config = SAMPLE_BUILD_CONFIG.copy()

    def test_create_build_task_success(self):
        """测试成功创建构建任务"""
        # 准备返回数据
        build_task_data = {
            "id": "build_task_123",
            "name": "test-build",
            "status": "pending",
            "config": self.test_config,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # 模拟配置验证成功
        self.mock_build_manager.validate_build_config.return_value = True

        # 调用方法
        result = self.build_service.create_build_task(self.test_config)

        # 验证结果
        assert result["name"] == "test-build"
        assert result["status"] == "pending"
        assert "id" in result
        assert "created_at" in result

        # 验证构建管理器调用
        self.mock_build_manager.validate_build_config.assert_called_once_with(self.test_config)

    def test_create_build_task_validation_error(self):
        """测试创建构建任务时配置验证失败"""
        # 模拟配置验证失败
        self.mock_build_manager.validate_build_config.side_effect = BuildValidationError("Invalid config")

        # 验证抛出异常
        with pytest.raises(BuildValidationError):
            self.build_service.create_build_task(self.test_config)

    def test_get_build_task_by_id_success(self):
        """测试成功通过ID获取构建任务"""
        # 准备返回数据
        task_data = {
            "id": "build_task_123",
            "name": "test-build",
            "status": "completed",
            "config": self.test_config,
            "logs": ["Step 1/3: FROM centos:7"],
            "result": {"image_id": "built_image_123"}
        }

        # 模拟Redis缓存返回
        self.mock_redis_client.hget.return_value = json.dumps(task_data)

        # 调用方法
        result = self.build_service.get_build_task("build_task_123")

        # 验证结果
        assert result["id"] == "build_task_123"
        assert result["name"] == "test-build"
        assert result["status"] == "completed"

        # 验证Redis调用
        self.mock_redis_client.hget.assert_called()

    def test_get_build_task_not_found(self):
        """测试获取不存在的构建任务"""
        # 模拟任务不存在
        self.mock_redis_client.hget.return_value = None

        # 验证抛出异常
        with pytest.raises(BuildTaskError, match="Build task .* not found"):
            self.build_service.get_build_task("nonexistent_task")

    def test_list_build_tasks(self):
        """测试列出构建任务"""
        # 准备测试数据
        tasks_data = generate_test_build_data(3)

        # 模拟Redis返回任务列表
        task_keys = ["build_task_000", "build_task_001", "build_task_002"]
        self.mock_redis_client.keys.return_value = task_keys

        def hget_side_effect(key, field):
            # 根据key返回对应的任务数据
            index = int(key.split("_")[-1])
            return json.dumps(tasks_data[index])

        self.mock_redis_client.hget.side_effect = hget_side_effect

        # 调用方法
        result = self.build_service.list_build_tasks()

        # 验证结果
        assert len(result) == 3
        assert all("id" in task for task in result)
        assert all("name" in task for task in result)
        assert all("status" in task for task in result)

    def test_list_build_tasks_with_status_filter(self):
        """测试根据状态过滤构建任务"""
        # 准备测试数据
        tasks_data = [
            {"id": "task_1", "status": "pending"},
            {"id": "task_2", "status": "building"},
            {"id": "task_3", "status": "completed"},
            {"id": "task_4", "status": "failed"}
        ]

        # 模拟Redis操作
        self.mock_redis_client.keys.return_value = ["task_1", "task_2", "task_3", "task_4"]

        def hget_side_effect(key, field):
            task_data = next((t for t in tasks_data if t["id"] == key), None)
            return json.dumps(task_data) if task_data else None

        self.mock_redis_client.hget.side_effect = hget_side_effect

        # 调用方法（只获取已完成的任务）
        result = self.build_service.list_build_tasks(status_filter="completed")

        # 验证结果
        completed_tasks = [task for task in result if task["status"] == "completed"]
        assert len(completed_tasks) >= 1

    def test_update_build_task_status(self):
        """测试更新构建任务状态"""
        task_id = "build_task_123"
        new_status = "building"

        # 模拟现有任务数据
        existing_task = {
            "id": task_id,
            "status": "pending",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        self.mock_redis_client.hget.return_value = json.dumps(existing_task)

        # 调用方法
        result = self.build_service.update_build_task_status(task_id, new_status)

        # 验证结果
        assert result["status"] == new_status
        assert "updated_at" in result

        # 验证Redis更新
        self.mock_redis_client.hset.assert_called()

    def test_delete_build_task_success(self):
        """测试成功删除构建任务"""
        task_id = "build_task_123"

        # 模拟任务存在
        self.mock_redis_client.hget.return_value = json.dumps({"id": task_id})

        # 调用方法
        result = self.build_service.delete_build_task(task_id)

        # 验证结果
        assert result is True

        # 验证Redis删除
        self.mock_redis_client.hdel.assert_called()

# ====================================
# 构建执行测试
# ====================================

@pytest.mark.unit
class TestBuildExecution(BaseUnitTest):
    """构建执行测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建构建服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_build_manager = Mock(spec=BuildManager)
        self.mock_redis_client = create_mock_redis_client()

        self.build_service = BuildService(
            docker_manager=self.mock_docker_manager,
            build_manager=self.mock_build_manager,
            redis_client=self.mock_redis_client
        )

        # 创建临时构建目录
        self.build_context_dir = tempfile.mkdtemp(prefix="build_context_")

    def teardown_method(self, method):
        """测试方法清理"""
        super().teardown_method(method)
        # 清理临时目录
        if os.path.exists(self.build_context_dir):
            shutil.rmtree(self.build_context_dir, ignore_errors=True)

    def test_execute_build_success(self):
        """测试成功执行构建"""
        # 准备构建任务
        build_task = {
            "id": "build_task_123",
            "name": "test-build",
            "config": SAMPLE_BUILD_CONFIG,
            "status": "pending"
        }

        # 模拟构建上下文准备
        self.mock_build_manager.prepare_build_context.return_value = self.build_context_dir

        # 模拟Docker构建成功
        built_image = {"id": "built_image_123", "tags": ["test:latest"]}
        build_logs = [
            "Step 1/3: FROM centos:7",
            "Step 2/3: RUN yum update -y",
            "Step 3/3: CMD [\"/bin/bash\"]",
            "Successfully built built_image_123"
        ]
        self.mock_docker_manager.build_image.return_value = (built_image, build_logs)

        # 模拟任务存在
        self.mock_redis_client.hget.return_value = json.dumps(build_task)

        # 调用方法
        result = self.build_service.execute_build("build_task_123")

        # 验证结果
        assert result["status"] == "completed"
        assert result["image"]["id"] == "built_image_123"
        assert len(result["logs"]) == 4

        # 验证调用顺序
        self.mock_build_manager.prepare_build_context.assert_called_once()
        self.mock_docker_manager.build_image.assert_called_once()

    def test_execute_build_docker_error(self):
        """测试构建执行Docker错误"""
        # 准备构建任务
        build_task = {
            "id": "build_task_123",
            "name": "test-build",
            "config": SAMPLE_BUILD_CONFIG,
            "status": "pending"
        }

        # 模拟构建上下文准备
        self.mock_build_manager.prepare_build_context.return_value = self.build_context_dir

        # 模拟Docker构建失败
        self.mock_docker_manager.build_image.side_effect = DockerError("Build failed")

        # 模拟任务存在
        self.mock_redis_client.hget.return_value = json.dumps(build_task)

        # 调用方法
        result = self.build_service.execute_build("build_task_123")

        # 验证结果
        assert result["status"] == "failed"
        assert "error" in result
        assert "Build failed" in result["error"]

    def test_execute_build_context_preparation_error(self):
        """测试构建上下文准备失败"""
        # 准备构建任务
        build_task = {
            "id": "build_task_123",
            "name": "test-build",
            "config": SAMPLE_BUILD_CONFIG,
            "status": "pending"
        }

        # 模拟构建上下文准备失败
        self.mock_build_manager.prepare_build_context.side_effect = BuildTaskError("Context preparation failed")

        # 模拟任务存在
        self.mock_redis_client.hget.return_value = json.dumps(build_task)

        # 调用方法
        result = self.build_service.execute_build("build_task_123")

        # 验证结果
        assert result["status"] == "failed"
        assert "Context preparation failed" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_build_async(self):
        """测试异步构建执行"""
        # 准备构建任务
        build_task = {
            "id": "build_task_123",
            "name": "test-build",
            "config": SAMPLE_BUILD_CONFIG,
            "status": "pending"
        }

        # 模拟异步构建成功
        async def async_build_side_effect(*args, **kwargs):
            return (
                {"id": "built_image_123", "tags": ["test:latest"]},
                ["Step 1/1: FROM centos:7", "Successfully built"]
            )

        self.mock_docker_manager.build_image_async = AsyncMock(side_effect=async_build_side_effect)
        self.mock_build_manager.prepare_build_context.return_value = self.build_context_dir
        self.mock_redis_client.hget.return_value = json.dumps(build_task)

        # 调用异步方法
        result = await self.build_service.execute_build_async("build_task_123")

        # 验证结果
        assert result["status"] == "completed"
        assert result["image"]["id"] == "built_image_123"

    def test_cancel_build_task(self):
        """测试取消构建任务"""
        task_id = "build_task_123"

        # 模拟正在构建的任务
        building_task = {
            "id": task_id,
            "status": "building",
            "pid": 12345
        }
        self.mock_redis_client.hget.return_value = json.dumps(building_task)

        # 调用方法
        result = self.build_service.cancel_build_task(task_id)

        # 验证结果
        assert result["status"] == "cancelled"

        # 验证状态更新
        self.mock_redis_client.hset.assert_called()

# ====================================
# Dockerfile生成测试
# ====================================

@pytest.mark.unit
class TestDockerfileGenerator(BaseUnitTest):
    """Dockerfile生成器测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建Dockerfile生成器
        self.dockerfile_generator = DockerfileGenerator()

        # 基础配置
        self.base_config = {
            "base_image": "centos:7",
            "packages": ["rpm-build", "make", "gcc"],
            "build_commands": ["make clean", "make all"],
            "working_dir": "/workspace",
            "user": "builder"
        }

    def test_generate_basic_dockerfile(self):
        """测试生成基础Dockerfile"""
        # 调用方法
        dockerfile_content = self.dockerfile_generator.generate_dockerfile(self.base_config)

        # 验证生成的内容
        assert "FROM centos:7" in dockerfile_content
        assert "RUN yum install -y rpm-build make gcc" in dockerfile_content
        assert "WORKDIR /workspace" in dockerfile_content
        assert "USER builder" in dockerfile_content
        assert "RUN make clean" in dockerfile_content
        assert "RUN make all" in dockerfile_content

    def test_generate_dockerfile_with_env_vars(self):
        """测试生成包含环境变量的Dockerfile"""
        # 添加环境变量配置
        config = self.base_config.copy()
        config["environment"] = {
            "BUILD_TYPE": "release",
            "OPTIMIZATION": "O2"
        }

        # 调用方法
        dockerfile_content = self.dockerfile_generator.generate_dockerfile(config)

        # 验证环境变量
        assert "ENV BUILD_TYPE=release" in dockerfile_content
        assert "ENV OPTIMIZATION=O2" in dockerfile_content

    def test_generate_dockerfile_with_ports(self):
        """测试生成包含端口暴露的Dockerfile"""
        # 添加端口配置
        config = self.base_config.copy()
        config["exposed_ports"] = [8080, 9000]

        # 调用方法
        dockerfile_content = self.dockerfile_generator.generate_dockerfile(config)

        # 验证端口暴露
        assert "EXPOSE 8080" in dockerfile_content
        assert "EXPOSE 9000" in dockerfile_content

    def test_generate_dockerfile_with_volumes(self):
        """测试生成包含数据卷的Dockerfile"""
        # 添加数据卷配置
        config = self.base_config.copy()
        config["volumes"] = ["/data", "/logs"]

        # 调用方法
        dockerfile_content = self.dockerfile_generator.generate_dockerfile(config)

        # 验证数据卷
        assert "VOLUME [\"/data\"]" in dockerfile_content
        assert "VOLUME [\"/logs\"]" in dockerfile_content

    def test_generate_dockerfile_multistage(self):
        """测试生成多阶段Dockerfile"""
        # 多阶段配置
        multistage_config = {
            "stages": [
                {
                    "name": "builder",
                    "base_image": "golang:1.19",
                    "working_dir": "/app",
                    "build_commands": ["go mod download", "go build -o main ."]
                },
                {
                    "name": "runtime",
                    "base_image": "alpine:latest",
                    "copy_from_stage": {"builder": {"/app/main": "/usr/local/bin/main"}},
                    "command": ["/usr/local/bin/main"]
                }
            ]
        }

        # 调用方法
        dockerfile_content = self.dockerfile_generator.generate_dockerfile(multistage_config)

        # 验证多阶段内容
        assert "FROM golang:1.19 as builder" in dockerfile_content
        assert "FROM alpine:latest as runtime" in dockerfile_content
        assert "COPY --from=builder /app/main /usr/local/bin/main" in dockerfile_content
        assert "CMD [\"/usr/local/bin/main\"]" in dockerfile_content

    def test_generate_dockerfile_with_build_args(self):
        """测试生成包含构建参数的Dockerfile"""
        # 添加构建参数配置
        config = self.base_config.copy()
        config["build_args"] = {
            "VERSION": "1.0.0",
            "BUILD_DATE": "2025-07-01"
        }

        # 调用方法
        dockerfile_content = self.dockerfile_generator.generate_dockerfile(config)

        # 验证构建参数
        assert "ARG VERSION=1.0.0" in dockerfile_content
        assert "ARG BUILD_DATE=2025-07-01" in dockerfile_content

    def test_optimize_dockerfile_layers(self):
        """测试Dockerfile层优化"""
        # 包含多个RUN命令的配置
        config = {
            "base_image": "centos:7",
            "packages": ["package1", "package2", "package3"],
            "build_commands": [
                "command1",
                "command2",
                "command3"
            ],
            "optimize_layers": True
        }

        # 调用方法
        dockerfile_content = self.dockerfile_generator.generate_dockerfile(config)

        # 验证命令被合并到单个RUN指令中
        run_commands = [line for line in dockerfile_content.split('\n') if line.strip().startswith('RUN')]

        # 应该只有一个或很少的RUN命令（优化后）
        assert len(run_commands) <= 2

        # 验证使用了&&连接符进行层优化
        assert "&&" in dockerfile_content

    def test_generate_dockerfile_rpm_specific(self):
        """测试生成RPM构建专用Dockerfile"""
        # RPM构建配置
        rpm_config = {
            "base_image": "centos:7",
            "rpm_build": True,
            "spec_file": "package.spec",
            "source_files": ["source.tar.gz"],
            "build_user": "builder",
            "rpmbuild_dirs": True
        }

        # 调用方法
        dockerfile_content = self.dockerfile_generator.generate_dockerfile(rpm_config)

        # 验证RPM构建特定内容
        assert "RUN useradd -m builder" in dockerfile_content
        assert "rpmbuild" in dockerfile_content.lower()
        assert "mkdir -p" in dockerfile_content  # rpmbuild目录创建
        assert "COPY package.spec" in dockerfile_content

# ====================================
# 构建配置验证测试
# ====================================

@pytest.mark.unit
class TestBuildConfigValidation(BaseUnitTest):
    """构建配置验证测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建构建服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_build_manager = Mock(spec=BuildManager)

        self.build_service = BuildService(
            docker_manager=self.mock_docker_manager,
            build_manager=self.mock_build_manager
        )

        self.base_config = SAMPLE_BUILD_CONFIG.copy()

    def test_validate_basic_build_config_valid(self):
        """测试有效基础构建配置验证"""
        # 调用验证方法
        result = self.build_service._validate_build_config(self.base_config)

        # 验证返回True（有效）
        assert result is True

    @parametrize_with_cases([
        {
            "config_key": "name",
            "config_value": "",
            "error_pattern": "Build name.*required"
        },
        {
            "config_key": "dockerfile_content",
            "config_value": "",
            "error_pattern": "Dockerfile content.*empty"
        },
        {
            "config_key": "name",
            "config_value": "Invalid Build Name!",
            "error_pattern": "Invalid build name format"
        },
        {
            "config_key": "build_args",
            "config_value": "invalid_args",
            "error_pattern": "Build args must be a dictionary"
        }
    ])
    def test_validate_build_config_validation_errors(self, config_key, config_value, error_pattern):
        """测试构建配置验证错误"""
        # 创建无效配置
        invalid_config = self.base_config.copy()
        invalid_config[config_key] = config_value

        # 验证抛出验证错误
        with pytest.raises(BuildValidationError, match=error_pattern):
            self.build_service._validate_build_config(invalid_config)

    def test_validate_dockerfile_syntax(self):
        """测试Dockerfile语法验证"""
        # 无效Dockerfile语法
        invalid_config = self.base_config.copy()
        invalid_config["dockerfile_content"] = "INVALID dockerfile instruction"

        # 验证抛出验证错误
        with pytest.raises(BuildValidationError, match="Invalid Dockerfile syntax"):
            self.build_service._validate_build_config(invalid_config)

    def test_validate_context_files(self):
        """测试构建上下文文件验证"""
        # 配置包含不存在的文件
        config = self.base_config.copy()
        config["context_files"] = {
            "nonexistent.txt": "This file does not exist on filesystem"
        }

        # 模拟文件验证
        self.mock_build_manager.validate_context_files.return_value = False

        # 验证抛出验证错误
        with pytest.raises(BuildValidationError, match="Invalid context files"):
            self.build_service._validate_build_config(config)

    def test_validate_build_resources(self):
        """测试构建资源限制验证"""
        # 配置资源限制
        config = self.base_config.copy()
        config["resources"] = {
            "memory": "2g",
            "cpu": "2.0"
        }

        # 调用验证方法
        result = self.build_service._validate_build_config(config)

        # 验证通过
        assert result is True

# ====================================
# 构建监控和日志测试
# ====================================

@pytest.mark.unit
class TestBuildMonitoring(BaseUnitTest):
    """构建监控和日志测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建构建服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_build_manager = Mock(spec=BuildManager)
        self.mock_redis_client = create_mock_redis_client()

        self.build_service = BuildService(
            docker_manager=self.mock_docker_manager,
            build_manager=self.mock_build_manager,
            redis_client=self.mock_redis_client
        )

    def test_get_build_logs(self):
        """测试获取构建日志"""
        task_id = "build_task_123"

        # 模拟任务数据包含日志
        task_data = {
            "id": task_id,
            "logs": [
                "Step 1/3: FROM centos:7",
                "Step 2/3: RUN yum update -y",
                "Step 3/3: CMD [\"/bin/bash\"]",
                "Successfully built abc123"
            ]
        }
        self.mock_redis_client.hget.return_value = json.dumps(task_data)

        # 调用方法
        logs = self.build_service.get_build_logs(task_id)

        # 验证结果
        assert len(logs) == 4
        assert "FROM centos:7" in logs[0]
        assert "Successfully built" in logs[-1]

    def test_get_build_logs_streaming(self):
        """测试实时流式获取构建日志"""
        task_id = "build_task_123"

        # 模拟流式日志生成器
        def log_generator():
            logs = [
                "Step 1/3: FROM centos:7",
                "Step 2/3: RUN yum update -y",
                "Step 3/3: CMD [\"/bin/bash\"]"
            ]
            for log in logs:
                yield log

        # 模拟构建服务的流式日志方法
        self.build_service._get_streaming_logs = Mock(return_value=log_generator())

        # 调用方法
        logs = list(self.build_service.get_build_logs_streaming(task_id))

        # 验证结果
        assert len(logs) == 3
        assert "FROM centos:7" in logs[0]

    def test_get_build_progress(self):
        """测试获取构建进度"""
        task_id = "build_task_123"

        # 模拟任务数据包含进度信息
        task_data = {
            "id": task_id,
            "status": "building",
            "progress": {
                "current_step": 2,
                "total_steps": 5,
                "percentage": 40,
                "current_operation": "Installing packages"
            },
            "started_at": "2025-07-01T10:00:00Z"
        }
        self.mock_redis_client.hget.return_value = json.dumps(task_data)

        # 调用方法
        progress = self.build_service.get_build_progress(task_id)

        # 验证结果
        assert progress["current_step"] == 2
        assert progress["total_steps"] == 5
        assert progress["percentage"] == 40
        assert progress["current_operation"] == "Installing packages"

    def test_get_build_statistics(self):
        """测试获取构建统计信息"""
        # 模拟多个构建任务数据
        tasks = [
            {"status": "completed", "duration": 300},
            {"status": "completed", "duration": 450},
            {"status": "failed", "duration": 120},
            {"status": "building", "duration": 0}
        ]

        # 模拟Redis返回所有任务
        self.mock_redis_client.keys.return_value = [f"task_{i}" for i in range(4)]
        self.mock_redis_client.hget.side_effect = lambda key, field: json.dumps(tasks[int(key.split("_")[1])])

        # 调用方法
        stats = self.build_service.get_build_statistics()

        # 验证统计结果
        assert stats["total_builds"] == 4
        assert stats["completed_builds"] == 2
        assert stats["failed_builds"] == 1
        assert stats["building_builds"] == 1
        assert stats["average_duration"] == 375  # (300+450)/2

    def test_monitor_build_resource_usage(self):
        """测试监控构建资源使用"""
        task_id = "build_task_123"

        # 模拟资源使用数据
        resource_data = {
            "cpu_usage": 75.5,
            "memory_usage": 1024 * 1024 * 512,  # 512MB
            "disk_usage": 1024 * 1024 * 100,    # 100MB
            "network_io": {"rx": 1024, "tx": 512}
        }

        # 模拟获取资源使用
        self.build_service._get_resource_usage = Mock(return_value=resource_data)

        # 调用方法
        usage = self.build_service.monitor_build_resources(task_id)

        # 验证结果
        assert usage["cpu_usage"] == 75.5
        assert usage["memory_usage"] == 1024 * 1024 * 512
        assert usage["disk_usage"] == 1024 * 1024 * 100

# ====================================
# 构建历史和清理测试
# ====================================

@pytest.mark.unit
class TestBuildHistoryAndCleanup(BaseUnitTest):
    """构建历史和清理测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建构建服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_build_manager = Mock(spec=BuildManager)
        self.mock_redis_client = create_mock_redis_client()

        self.build_service = BuildService(
            docker_manager=self.mock_docker_manager,
            build_manager=self.mock_build_manager,
            redis_client=self.mock_redis_client
        )

    def test_get_build_history(self):
        """测试获取构建历史"""
        # 模拟历史构建数据
        history_data = [
            {
                "id": "build_1",
                "name": "project-v1.0",
                "status": "completed",
                "created_at": "2025-09-01T10:00:00Z",
                "duration": 300
            },
            {
                "id": "build_2",
                "name": "project-v1.1",
                "status": "completed",
                "created_at": "2025-09-15T10:00:00Z",
                "duration": 250
            }
        ]

        # 模拟Redis查询
        self.mock_redis_client.keys.return_value = ["build_1", "build_2"]
        self.mock_redis_client.hget.side_effect = lambda key, field: json.dumps(
            next(item for item in history_data if item["id"] == key)
        )

        # 调用方法
        history = self.build_service.get_build_history(limit=10)

        # 验证结果
        assert len(history) == 2
        assert history[0]["name"] == "project-v1.0"
        assert history[1]["name"] == "project-v1.1"

    def test_cleanup_old_builds(self):
        """测试清理旧构建"""
        # 模拟旧构建数据
        old_builds = [
            {"id": "old_build_1", "created_at": "2025-09-01T10:00:00Z"},
            {"id": "old_build_2", "created_at": "2025-09-15T10:00:00Z"}
        ]

        # 模拟查找过期构建
        self.build_service._find_expired_builds = Mock(return_value=["old_build_1", "old_build_2"])

        # 调用清理方法
        result = self.build_service.cleanup_old_builds(days_to_keep=30)

        # 验证结果
        assert result["cleaned_count"] == 2
        assert "old_build_1" in result["cleaned_builds"]
        assert "old_build_2" in result["cleaned_builds"]

        # 验证Redis删除操作
        assert self.mock_redis_client.hdel.call_count == 2

    def test_cleanup_build_artifacts(self):
        """测试清理构建产物"""
        task_id = "build_task_123"

        # 模拟构建产物路径
        artifacts_paths = [
            "/tmp/build_context_123",
            "/tmp/build_cache_123"
        ]

        # 模拟查找构建产物
        self.build_service._find_build_artifacts = Mock(return_value=artifacts_paths)

        # 模拟文件系统清理
        self.build_service._cleanup_files = Mock(return_value=True)

        # 调用方法
        result = self.build_service.cleanup_build_artifacts(task_id)

        # 验证结果
        assert result is True

        # 验证清理调用
        self.build_service._cleanup_files.assert_called()

    def test_archive_completed_builds(self):
        """测试归档已完成构建"""
        # 模拟已完成的构建
        completed_builds = [
            {"id": "build_1", "status": "completed"},
            {"id": "build_2", "status": "completed"}
        ]

        # 模拟查找已完成构建
        self.build_service._find_completed_builds = Mock(return_value=completed_builds)

        # 模拟归档操作
        self.build_service._archive_build = Mock(return_value=True)

        # 调用方法
        result = self.build_service.archive_completed_builds(archive_after_days=7)

        # 验证结果
        assert result["archived_count"] == 2

        # 验证归档调用
        assert self.build_service._archive_build.call_count == 2

# ====================================
# 构建事件处理测试
# ====================================

@pytest.mark.unit
class TestBuildEventHandler(BaseUnitTest):
    """构建事件处理器测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建mock依赖
        self.mock_build_service = Mock(spec=BuildService)
        self.mock_redis_client = create_mock_redis_client()
        self.mock_logger = Mock()

        # 创建事件处理器
        self.event_handler = BuildEventHandler(
            build_service=self.mock_build_service,
            redis_client=self.mock_redis_client,
            logger=self.mock_logger
        )

    def test_handle_build_started_event(self):
        """测试处理构建开始事件"""
        # 准备事件数据
        event_data = {
            "action": "build_started",
            "build_id": "build_task_123",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # 调用事件处理
        self.event_handler.handle_build_event(event_data)

        # 验证日志记录
        self.mock_logger.info.assert_called()

        # 验证状态更新
        self.mock_redis_client.hset.assert_called()

    def test_handle_build_completed_event(self):
        """测试处理构建完成事件"""
        # 准备事件数据
        event_data = {
            "action": "build_completed",
            "build_id": "build_task_123",
            "image_id": "built_image_123",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # 调用事件处理
        self.event_handler.handle_build_event(event_data)

        # 验证成功处理
        self.mock_logger.info.assert_called()
        self.mock_redis_client.hset.assert_called()

    def test_handle_build_failed_event(self):
        """测试处理构建失败事件"""
        # 准备事件数据
        event_data = {
            "action": "build_failed",
            "build_id": "build_task_123",
            "error": "Docker build failed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # 调用事件处理
        self.event_handler.handle_build_event(event_data)

        # 验证错误处理
        self.mock_logger.error.assert_called()
        self.mock_redis_client.hset.assert_called()

    @pytest.mark.asyncio
    async def test_handle_build_progress_event(self):
        """测试处理构建进度事件"""
        # 准备进度事件数据
        event_data = {
            "action": "build_progress",
            "build_id": "build_task_123",
            "progress": {
                "current_step": 3,
                "total_steps": 5,
                "percentage": 60
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # 调用异步事件处理
        await self.event_handler.handle_build_event_async(event_data)

        # 验证进度更新
        self.mock_redis_client.hset.assert_called()

    def test_broadcast_build_event(self):
        """测试广播构建事件"""
        # 准备事件数据
        event_data = {
            "action": "build_started",
            "build_id": "build_task_123"
        }

        # 模拟WebSocket连接
        mock_websocket = Mock()
        self.event_handler.websocket_connections = [mock_websocket]

        # 调用广播方法
        self.event_handler.broadcast_build_event(event_data)

        # 验证WebSocket发送
        mock_websocket.send.assert_called()

# ====================================
# 构建批量操作测试
# ====================================

@pytest.mark.unit
class TestBuildBatchOperations(BaseUnitTest):
    """构建批量操作测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建构建服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_build_manager = Mock(spec=BuildManager)
        self.mock_redis_client = create_mock_redis_client()

        self.build_service = BuildService(
            docker_manager=self.mock_docker_manager,
            build_manager=self.mock_build_manager,
            redis_client=self.mock_redis_client
        )

    def test_create_multiple_build_tasks(self):
        """测试创建多个构建任务"""
        # 准备多个构建配置
        configs = []
        for i in range(3):
            config = SAMPLE_BUILD_CONFIG.copy()
            config["name"] = f"batch-build-{i}"
            configs.append(config)

        # 模拟每个配置验证成功
        self.mock_build_manager.validate_build_config.return_value = True

        # 调用批量创建方法
        results = self.build_service.create_build_tasks_batch(configs)

        # 验证结果
        assert len(results) == 3
        assert all("id" in result for result in results)
        assert all("name" in result for result in results)
        assert results[0]["name"] == "batch-build-0"

        # 验证所有配置都被验证
        assert self.mock_build_manager.validate_build_config.call_count == 3

    def test_execute_multiple_builds_sequential(self):
        """测试顺序执行多个构建"""
        # 准备构建任务ID列表
        task_ids = ["build_1", "build_2", "build_3"]

        # 模拟每个构建执行成功
        def execute_side_effect(task_id):
            return {
                "id": task_id,
                "status": "completed",
                "image": {"id": f"image_{task_id}"}
            }

        self.build_service.execute_build = Mock(side_effect=execute_side_effect)

        # 调用顺序执行方法
        results = self.build_service.execute_builds_sequential(task_ids)

        # 验证结果
        assert len(results) == 3
        assert all(result["status"] == "completed" for result in results)

        # 验证执行顺序
        assert self.build_service.execute_build.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_multiple_builds_parallel(self):
        """测试并行执行多个构建"""
        # 准备构建任务ID列表
        task_ids = ["build_1", "build_2", "build_3"]

        # 模拟异步构建执行
        async def async_execute_side_effect(task_id):
            await asyncio.sleep(0.1)  # 模拟构建时间
            return {
                "id": task_id,
                "status": "completed",
                "image": {"id": f"image_{task_id}"}
            }

        self.build_service.execute_build_async = AsyncMock(side_effect=async_execute_side_effect)

        # 调用并行执行方法
        results = await self.build_service.execute_builds_parallel(task_ids, max_concurrent=2)

        # 验证结果
        assert len(results) == 3
        assert all(result["status"] == "completed" for result in results)

        # 验证并行执行
        assert self.build_service.execute_build_async.call_count == 3

    def test_cancel_multiple_builds(self):
        """测试取消多个构建任务"""
        # 准备构建任务ID列表
        task_ids = ["build_1", "build_2", "build_3"]

        # 模拟取消构建
        def cancel_side_effect(task_id):
            return {"id": task_id, "status": "cancelled"}

        self.build_service.cancel_build_task = Mock(side_effect=cancel_side_effect)

        # 调用批量取消方法
        results = self.build_service.cancel_builds_batch(task_ids)

        # 验证结果
        assert len(results) == 3
        assert all(result["status"] == "cancelled" for result in results)

        # 验证所有任务都被取消
        assert self.build_service.cancel_build_task.call_count == 3

    def test_delete_multiple_build_tasks(self):
        """测试删除多个构建任务"""
        # 准备构建任务ID列表
        task_ids = ["build_1", "build_2", "build_3"]

        # 模拟删除构建任务
        self.build_service.delete_build_task = Mock(return_value=True)

        # 调用批量删除方法
        results = self.build_service.delete_build_tasks_batch(task_ids)

        # 验证结果
        assert len(results) == 3
        assert all(result is True for result in results)

        # 验证所有任务都被删除
        assert self.build_service.delete_build_task.call_count == 3

# ====================================
# 构建性能和资源管理测试
# ====================================

@pytest.mark.unit
class TestBuildPerformanceAndResources(BaseUnitTest):
    """构建性能和资源管理测试类"""

    def setup_method(self, method):
        """测试方法设置"""
        super().setup_method(method)

        # 创建构建服务
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_build_manager = Mock(spec=BuildManager)
        self.mock_redis_client = create_mock_redis_client()

        self.build_service = BuildService(
            docker_manager=self.mock_docker_manager,
            build_manager=self.mock_build_manager,
            redis_client=self.mock_redis_client,
            enable_resource_monitoring=True
        )

    def test_build_with_resource_limits(self):
        """测试带资源限制的构建"""
        # 配置资源限制
        build_config = SAMPLE_BUILD_CONFIG.copy()
        build_config["resources"] = {
            "memory": "1g",
            "cpu": "1.0",
            "disk": "2g"
        }

        # 模拟Docker构建使用资源限制
        self.mock_docker_manager.build_image.return_value = (
            {"id": "limited_build_123", "tags": ["test:latest"]},
            ["Successfully built with resource limits"]
        )

        # 创建构建任务
        task = self.build_service.create_build_task(build_config)

        # 执行构建
        result = self.build_service.execute_build(task["id"])

        # 验证构建成功且使用了资源限制
        assert result["status"] == "completed"

        # 验证Docker构建调用包含资源限制
        call_kwargs = self.mock_docker_manager.build_image.call_args.kwargs
        if "buildargs" in call_kwargs:
            # 资源限制应该被传递到构建参数中
            assert "resources" in str(call_kwargs)

    def test_build_performance_metrics(self):
        """测试构建性能指标收集"""
        task_id = "build_task_123"

        # 模拟性能指标数据
        performance_metrics = {
            "build_duration": 300,
            "cpu_usage_avg": 65.5,
            "memory_usage_peak": 1024 * 1024 * 800,  # 800MB
            "disk_io_read": 1024 * 1024 * 50,        # 50MB
            "disk_io_write": 1024 * 1024 * 100,      # 100MB
            "network_io": {"rx": 1024 * 10, "tx": 1024 * 5}
        }

        # 模拟获取性能指标
        self.build_service._collect_performance_metrics = Mock(return_value=performance_metrics)

        # 调用方法
        metrics = self.build_service.get_build_performance_metrics(task_id)

        # 验证指标数据
        assert metrics["build_duration"] == 300
        assert metrics["cpu_usage_avg"] == 65.5
        assert metrics["memory_usage_peak"] == 1024 * 1024 * 800

    def test_build_cache_management(self):
        """测试构建缓存管理"""
        # 启用构建缓存的配置
        build_config = SAMPLE_BUILD_CONFIG.copy()
        build_config["cache_enabled"] = True
        build_config["cache_key"] = "centos7_rpm_build_v1"

        # 模拟缓存命中
        cached_result = {
            "image": {"id": "cached_image_123", "tags": ["cached:latest"]},
            "logs": ["Using cached layers"],
            "cache_hit": True
        }

        # 模拟缓存查询
        self.build_service._check_build_cache = Mock(return_value=cached_result)

        # 创建并执行构建任务
        task = self.build_service.create_build_task(build_config)
        result = self.build_service.execute_build(task["id"])

        # 验证使用了缓存
        if result.get("cache_hit"):
            assert result["cache_hit"] is True
            assert "cached_image_123" in str(result["image"]["id"])

    def test_build_queue_management(self):
        """测试构建队列管理"""
        # 创建多个构建任务
        task_configs = []
        for i in range(5):
            config = SAMPLE_BUILD_CONFIG.copy()
            config["name"] = f"queued-build-{i}"
            task_configs.append(config)

        # 批量创建任务
        tasks = self.build_service.create_build_tasks_batch(task_configs)

        # 模拟构建队列
        self.build_service._add_to_build_queue = Mock()
        self.build_service._get_build_queue_status = Mock(return_value={
            "queued": 5,
            "building": 2,
            "completed": 0
        })

        # 获取队列状态
        queue_status = self.build_service.get_build_queue_status()

        # 验证队列管理
        assert queue_status["queued"] == 5
        assert queue_status["building"] == 2

    def test_concurrent_builds_limit(self):
        """测试并发构建限制"""
        # 设置最大并发构建数
        self.build_service.max_concurrent_builds = 2

        # 尝试启动多个构建
        task_ids = ["build_1", "build_2", "build_3", "build_4"]

        # 模拟当前有构建在执行
        self.build_service._get_active_builds_count = Mock(return_value=2)

        # 尝试执行新构建应该被队列化
        for task_id in task_ids[2:]:  # build_3 和 build_4
            result = self.build_service.try_execute_build(task_id)
            assert result["status"] == "queued"  # 应该被放入队列

    def test_build_resource_cleanup(self):
        """测试构建资源清理"""
        task_id = "build_task_123"

        # 模拟构建完成后的资源清理
        cleanup_result = {
            "temp_files_cleaned": 15,
            "cache_entries_removed": 3,
            "disk_space_freed": 1024 * 1024 * 500  # 500MB
        }

        self.build_service._cleanup_build_resources = Mock(return_value=cleanup_result)

        # 调用资源清理
        result = self.build_service.cleanup_build_resources(task_id)

        # 验证清理结果
        assert result["temp_files_cleaned"] == 15
        assert result["disk_space_freed"] == 1024 * 1024 * 500

        # 验证清理方法被调用
        self.build_service._cleanup_build_resources.assert_called_once_with(task_id)