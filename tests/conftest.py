"""
pytest配置文件

******OSPP-2025-张金荣******


包含pytest的全局配置、fixtures和钩子函数，为所有测试提供：
- 测试环境设置和清理
- 模拟对象和测试数据
- 数据库和外部服务的fixture
- 测试标记和过滤器
- 测试报告和日志配置

版本: 1.0.0
作者: 张金荣
"""

import os
import sys
import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, Generator, AsyncGenerator

# 添加项目路径
TEST_DIR = Path(__file__).parent
PROJECT_ROOT = TEST_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

# 导入项目模块
try:
    from config.settings import get_settings
    from utils.logger import get_logger
    from utils.exceptions import APIError, DockerError, BuildError
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入项目模块: {e}")
    IMPORTS_AVAILABLE = False

# ====================================
# pytest配置
# ====================================

def pytest_configure(config):
    """pytest配置钩子"""
    # 注册自定义标记
    config.addinivalue_line(
        "markers", "unit: 单元测试标记"
    )
    config.addinivalue_line(
        "markers", "integration: 集成测试标记"
    )
    config.addinivalue_line(
        "markers", "slow: 慢测试标记（耗时较长的测试）"
    )
    config.addinivalue_line(
        "markers", "docker: 需要Docker环境的测试"
    )
    config.addinivalue_line(
        "markers", "network: 需要网络连接的测试"
    )
    config.addinivalue_line(
        "markers", "database: 需要数据库的测试"
    )
    config.addinivalue_line(
        "markers", "redis: 需要Redis的测试"
    )
    config.addinivalue_line(
        "markers", "filesystem: 需要文件系统的测试"
    )

def pytest_collection_modifyitems(config, items):
    """修改测试项目的钩子"""
    # 为没有标记的测试添加默认标记
    for item in items:
        # 根据文件路径自动添加标记
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # 为包含特定关键字的测试添加标记
        if "docker" in item.name.lower():
            item.add_marker(pytest.mark.docker)
        if "redis" in item.name.lower():
            item.add_marker(pytest.mark.redis)
        if "slow" in item.name.lower() or "performance" in item.name.lower():
            item.add_marker(pytest.mark.slow)

def pytest_runtest_setup(item):
    """测试运行前的设置钩子"""
    # 检查Docker标记的测试
    if "docker" in item.keywords:
        try:
            import docker
            client = docker.from_env()
            client.ping()
        except Exception:
            pytest.skip("Docker不可用")

    # 检查Redis标记的测试
    if "redis" in item.keywords:
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=15)
            r.ping()
        except Exception:
            pytest.skip("Redis不可用")

# ====================================
# 事件循环Fixtures
# ====================================

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环for异步测试"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# ====================================
# 测试环境Fixtures
# ====================================

@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """测试配置fixture"""
    return {
        "TESTING": True,
        "DEBUG": True,
        "LOG_LEVEL": "DEBUG",
        "DATABASE_URL": "sqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379/15",
        "API_HOST": "127.0.0.1",
        "API_PORT": 0,
        "RPC_PORT": 0,
        "DOCKER_HOST": "unix:///var/run/docker.sock",
        "BUILD_PATH": "/tmp/eulermaker_test_builds",
        "UPLOAD_PATH": "/tmp/eulermaker_test_uploads",
        "LOG_PATH": "/tmp/eulermaker_test_logs",
        "CACHE_PATH": "/tmp/eulermaker_test_cache",
    }

@pytest.fixture(scope="session")
def test_temp_dir():
    """测试临时目录fixture"""
    temp_dir = tempfile.mkdtemp(prefix="eulermaker_test_")
    temp_path = Path(temp_dir)

    # 创建子目录
    (temp_path / "builds").mkdir()
    (temp_path / "uploads").mkdir()
    (temp_path / "logs").mkdir()
    (temp_path / "cache").mkdir()
    (temp_path / "data").mkdir()

    yield temp_path

    # 清理临时目录
    if temp_path.exists():
        shutil.rmtree(temp_path, ignore_errors=True)

@pytest.fixture(autouse=True)
def setup_test_environment(test_config, test_temp_dir):
    """自动设置测试环境"""
    # 保存原始环境变量
    original_env = dict(os.environ)

    # 设置测试环境变量
    test_env = test_config.copy()
    test_env.update({
        "BUILD_PATH": str(test_temp_dir / "builds"),
        "UPLOAD_PATH": str(test_temp_dir / "uploads"),
        "LOG_PATH": str(test_temp_dir / "logs"),
        "CACHE_PATH": str(test_temp_dir / "cache"),
    })

    for key, value in test_env.items():
        os.environ[key] = str(value)

    yield

    # 恢复原始环境变量
    os.environ.clear()
    os.environ.update(original_env)

# ====================================
# 日志Fixtures
# ====================================

@pytest.fixture
def test_logger():
    """测试日志器fixture"""
    if IMPORTS_AVAILABLE:
        return get_logger("test")
    else:
        import logging
        logger = logging.getLogger("test")
        logger.setLevel(logging.DEBUG)
        return logger

@pytest.fixture
def capture_logs(caplog):
    """捕获日志输出fixture"""
    import logging
    caplog.set_level(logging.DEBUG)
    yield caplog

# ====================================
# Mock Fixtures
# ====================================

@pytest.fixture
def mock_docker_client():
    """模拟Docker客户端fixture"""
    mock_client = MagicMock()

    # 模拟基本方法
    mock_client.ping.return_value = True
    mock_client.version.return_value = {"Version": "20.10.0"}
    mock_client.info.return_value = {"ID": "test", "Containers": 0}

    # 模拟容器管理
    mock_container = MagicMock()
    mock_container.id = "test_container_id"
    mock_container.name = "test_container"
    mock_container.status = "running"
    mock_container.attrs = {
        "Id": "test_container_id",
        "Name": "/test_container",
        "State": {"Status": "running", "Running": True},
        "Config": {"Image": "test_image:latest"},
    }

    mock_client.containers.list.return_value = [mock_container]
    mock_client.containers.get.return_value = mock_container
    mock_client.containers.run.return_value = mock_container

    # 模拟镜像管理
    mock_image = MagicMock()
    mock_image.id = "test_image_id"
    mock_image.tags = ["test_image:latest"]
    mock_image.attrs = {"Id": "test_image_id", "RepoTags": ["test_image:latest"]}

    mock_client.images.list.return_value = [mock_image]
    mock_client.images.get.return_value = mock_image
    mock_client.images.build.return_value = (mock_image, iter([]))

    return mock_client

@pytest.fixture
def mock_redis_client():
    """模拟Redis客户端fixture"""
    mock_redis = MagicMock()

    # 模拟基本Redis操作
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.exists.return_value = 0
    mock_redis.keys.return_value = []
    mock_redis.hget.return_value = None
    mock_redis.hset.return_value = True
    mock_redis.hgetall.return_value = {}

    return mock_redis

@pytest.fixture
def mock_settings():
    """模拟设置fixture"""
    if IMPORTS_AVAILABLE:
        with patch('config.settings.get_settings') as mock:
            mock_settings_obj = MagicMock()
            mock_settings_obj.DEBUG = True
            mock_settings_obj.TESTING = True
            mock_settings_obj.LOG_LEVEL = "DEBUG"
            mock_settings_obj.DATABASE_URL = "sqlite:///:memory:"
            mock_settings_obj.REDIS_URL = "redis://localhost:6379/15"
            mock_settings_obj.API_HOST = "127.0.0.1"
            mock_settings_obj.API_PORT = 8000
            mock_settings_obj.RPC_PORT = 9000
            mock_settings_obj.DOCKER_HOST = "unix:///var/run/docker.sock"
            mock.return_value = mock_settings_obj
            yield mock_settings_obj
    else:
        # 如果无法导入，返回基本的mock对象
        mock_settings_obj = MagicMock()
        mock_settings_obj.DEBUG = True
        mock_settings_obj.TESTING = True
        yield mock_settings_obj

# ====================================
# 数据库Fixtures
# ====================================

@pytest.fixture
def mock_database():
    """模拟数据库fixture"""
    import sqlite3

    # 创建内存数据库
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # 创建测试表（如果需要）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS containers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            image TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS builds (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    yield conn

    conn.close()

# ====================================
# 测试数据Fixtures
# ====================================

@pytest.fixture
def sample_container_data():
    """示例容器数据fixture"""
    return {
        "id": "test_container_123",
        "name": "test_container",
        "image": "centos:7",
        "command": ["bash"],
        "environment": {"ENV": "test"},
        "ports": {"80/tcp": 8080},
        "volumes": {"/host/path": "/container/path"},
        "labels": {"test": "true"},
        "network": "bridge",
        "status": "running",
    }

@pytest.fixture
def sample_build_data():
    """示例构建数据fixture"""
    return {
        "id": "test_build_123",
        "name": "test_build",
        "dockerfile_content": """
FROM centos:7
RUN yum update -y
RUN yum install -y rpm-build
CMD ["/bin/bash"]
        """.strip(),
        "context_files": {
            "test.spec": "Name: test\nVersion: 1.0\nRelease: 1",
            "test.txt": "This is a test file",
        },
        "build_args": {"ARG1": "value1"},
        "labels": {"build": "test"},
        "target_stage": None,
        "status": "pending",
    }

@pytest.fixture
def sample_probe_data():
    """示例探针数据fixture"""
    return {
        "id": "test_probe_123",
        "container_id": "test_container_123",
        "type": "http",
        "config": {
            "url": "http://localhost:8080/health",
            "method": "GET",
            "timeout": 5,
            "interval": 10,
            "retries": 3,
        },
        "status": "healthy",
        "last_check": "2025-07-01T10:00:00Z",
        "failure_count": 0,
    }

# ====================================
# HTTP客户端Fixtures
# ====================================

@pytest.fixture
async def test_client():
    """测试HTTP客户端fixture"""
    try:
        from httpx import AsyncClient
        async with AsyncClient() as client:
            yield client
    except ImportError:
        # 如果没有httpx，使用mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_client.get.return_value = mock_response
        mock_client.post.return_value = mock_response
        mock_client.put.return_value = mock_response
        mock_client.delete.return_value = mock_response
        yield mock_client

# ====================================
# WebSocket Fixtures
# ====================================

@pytest.fixture
def mock_websocket():
    """模拟WebSocket连接fixture"""
    mock_ws = MagicMock()
    mock_ws.accept = MagicMock()
    mock_ws.send_text = MagicMock()
    mock_ws.send_bytes = MagicMock()
    mock_ws.receive_text = MagicMock(return_value="test message")
    mock_ws.receive_bytes = MagicMock(return_value=b"test bytes")
    mock_ws.close = MagicMock()
    return mock_ws

# ====================================
# 文件系统Fixtures
# ====================================

@pytest.fixture
def test_dockerfile_content():
    """测试Dockerfile内容fixture"""
    return """
FROM centos:7

# 安装基本工具
RUN yum update -y && \
    yum install -y \
        rpm-build \
        make \
        gcc \
        gcc-c++ \
        git \
        wget && \
    yum clean all

# 设置工作目录
WORKDIR /workspace

# 复制构建文件
COPY . .

# 默认命令
CMD ["/bin/bash"]
    """.strip()

@pytest.fixture
def test_spec_file_content():
    """测试RPM spec文件内容fixture"""
    return """
Name:           test-package
Version:        1.0.0
Release:        1%{?dist}
Summary:        A test package

License:        MIT
URL:            https://github.com/eulermaker/test-package
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  gcc
Requires:       glibc

%description
This is a test package for EulerMaker Docker Optimizer.

%prep
%autosetup

%build
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}

%files
/usr/bin/test-binary
/usr/share/doc/%{name}/*

%changelog
* Fri Dec 01 2025 EulerMaker <3487232360@qq.com> - 1.0.0-1
- Initial package
    """.strip()

# ====================================
# 性能测试Fixtures
# ====================================

@pytest.fixture
def performance_monitor():
    """性能监控fixture"""
    import time
    import psutil

    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.start_memory = None
            self.start_cpu = None

        def start(self):
            """开始监控"""
            self.start_time = time.time()
            self.start_memory = psutil.virtual_memory().used
            self.start_cpu = psutil.cpu_percent()

        def stop(self):
            """停止监控并返回结果"""
            if self.start_time is None:
                return None

            end_time = time.time()
            end_memory = psutil.virtual_memory().used
            end_cpu = psutil.cpu_percent()

            return {
                "duration": end_time - self.start_time,
                "memory_delta": end_memory - self.start_memory,
                "cpu_usage": (self.start_cpu + end_cpu) / 2,
            }

    return PerformanceMonitor()

# ====================================
# 工具函数Fixtures
# ====================================

@pytest.fixture
def assert_eventually():
    """最终断言工具fixture"""
    import time

    def _assert_eventually(condition_func, timeout=5, interval=0.1, message="Condition was not met"):
        """
        等待条件最终为真

        Args:
            condition_func: 条件函数，返回布尔值
            timeout: 超时时间（秒）
            interval: 检查间隔（秒）
            message: 失败时的消息
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition_func():
                return True
            time.sleep(interval)

        raise AssertionError(f"{message} (timeout after {timeout}s)")

    return _assert_eventually

@pytest.fixture
def wait_for_condition():
    """等待条件工具fixture"""
    import asyncio

    async def _wait_for_condition(condition_func, timeout=5, interval=0.1):
        """
        异步等待条件为真

        Args:
            condition_func: 条件函数，可以是同步或异步
            timeout: 超时时间（秒）
            interval: 检查间隔（秒）
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            if asyncio.iscoroutinefunction(condition_func):
                result = await condition_func()
            else:
                result = condition_func()

            if result:
                return True

            if asyncio.get_event_loop().time() - start_time >= timeout:
                return False

            await asyncio.sleep(interval)

    return _wait_for_condition

# ====================================
# 清理Fixtures
# ====================================

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """测试后自动清理fixture"""
    yield

    # 清理可能创建的临时文件
    temp_patterns = [
        "/tmp/eulermaker_*",
        "/tmp/test_*",
    ]

    import glob
    for pattern in temp_patterns:
        for path in glob.glob(pattern):
            try:
                if Path(path).is_file():
                    Path(path).unlink()
                elif Path(path).is_dir():
                    shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass  # 忽略清理错误