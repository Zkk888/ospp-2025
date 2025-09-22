"""
集成测试包

******OSPP-2025-张金荣******

包含项目各模块间的集成测试，专注于测试：
- API端点的完整功能和交互
- 各服务模块之间的协作
- 端到端的业务流程
- 真实环境下的系统行为
- 跨模块的数据流和状态同步
- 外部依赖的集成（Docker、Redis等）
- 系统性能和稳定性测试

集成测试特点：
1. 使用真实或接近真实的外部依赖
2. 测试完整的业务场景和用户旅程
3. 验证模块间接口的正确性
4. 检测系统集成问题和边界条件
5. 确保系统在真实环境下的可靠性

测试组织结构：
- test_api_endpoints.py：API接口集成测试
- test_container_lifecycle.py：容器生命周期集成测试
- test_build_integration.py：构建流程集成测试
- test_system_integration.py：系统整体集成测试
- test_performance_integration.py：性能集成测试

使用方式：
    # 运行所有集成测试
    pytest tests/integration/

    # 运行特定集成测试文件
    pytest tests/integration/test_api_endpoints.py

    # 运行带标记的集成测试
    pytest tests/integration/ -m "api"

    # 运行慢速集成测试
    pytest tests/integration/ -m "slow"

    # 跳过需要Docker的测试
    pytest tests/integration/ -m "not docker"

环境要求：
- Docker服务运行
- Redis服务运行
- 足够的系统资源
- 网络连接（如果需要）

版本: 1.0.0
作者: 张金荣
"""

import pytest
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import contextmanager

# 集成测试配置
INTEGRATION_TEST_CONFIG = {
    "TESTING": True,
    "INTEGRATION_TESTING": True,
    "DATABASE_URL": "sqlite:///./test_integration.db",
    "REDIS_URL": "redis://localhost:6379/14",  # 集成测试专用数据库
    "API_HOST": "127.0.0.1",
    "API_PORT": 0,  # 使用随机端口
    "RPC_PORT": 0,
    "DOCKER_HOST": "unix:///var/run/docker.sock",
    "BUILD_PATH": "./integration_test_builds",
    "UPLOAD_PATH": "./integration_test_uploads",
    "LOG_PATH": "./integration_test_logs",
    "CACHE_PATH": "./integration_test_cache",
    "TEST_TIMEOUT": 300,  # 5分钟超时
    "MAX_CONCURRENT_BUILDS": 2,
    "CLEANUP_AFTER_TESTS": True,
}

# 测试数据目录
INTEGRATION_TESTS_DIR = Path(__file__).parent
TEST_DATA_DIR = INTEGRATION_TESTS_DIR / "test_data"
TEST_FIXTURES_DIR = INTEGRATION_TESTS_DIR / "fixtures"

# 确保测试数据目录存在
TEST_DATA_DIR.mkdir(exist_ok=True)
TEST_FIXTURES_DIR.mkdir(exist_ok=True)

# ====================================
# 集成测试工具类
# ====================================

class IntegrationTestHelper:
    """集成测试辅助类"""

    def __init__(self):
        self.temp_dirs = []
        self.created_containers = []
        self.created_images = []
        self.test_resources = []

    def create_temp_dir(self, prefix: str = "integration_test_") -> Path:
        """创建临时目录"""
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.temp_dirs.append(temp_dir)
        return temp_dir

    def register_container(self, container_id: str):
        """注册创建的容器，用于测试后清理"""
        if container_id not in self.created_containers:
            self.created_containers.append(container_id)

    def register_image(self, image_id: str):
        """注册创建的镜像，用于测试后清理"""
        if image_id not in self.created_images:
            self.created_images.append(image_id)

    def register_resource(self, resource: Any):
        """注册测试资源，用于测试后清理"""
        self.test_resources.append(resource)

    def cleanup(self):
        """清理所有测试资源"""
        # 清理容器
        self._cleanup_containers()

        # 清理镜像
        self._cleanup_images()

        # 清理临时目录
        self._cleanup_temp_dirs()

        # 清理其他资源
        self._cleanup_resources()

    def _cleanup_containers(self):
        """清理测试容器"""
        try:
            import docker
            client = docker.from_env()

            for container_id in self.created_containers:
                try:
                    container = client.containers.get(container_id)
                    container.stop()
                    container.remove()
                except Exception:
                    pass  # 忽略清理错误
        except Exception:
            pass

    def _cleanup_images(self):
        """清理测试镜像"""
        try:
            import docker
            client = docker.from_env()

            for image_id in self.created_images:
                try:
                    client.images.remove(image_id, force=True)
                except Exception:
                    pass  # 忽略清理错误
        except Exception:
            pass

    def _cleanup_temp_dirs(self):
        """清理临时目录"""
        import shutil

        for temp_dir in self.temp_dirs:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass  # 忽略清理错误

    def _cleanup_resources(self):
        """清理其他资源"""
        for resource in self.test_resources:
            try:
                if hasattr(resource, 'close'):
                    resource.close()
                elif hasattr(resource, 'cleanup'):
                    resource.cleanup()
            except Exception:
                pass  # 忽略清理错误

# ====================================
# 环境检查工具
# ====================================

def check_docker_available() -> bool:
    """检查Docker是否可用"""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False

def check_redis_available() -> bool:
    """检查Redis是否可用"""
    try:
        import redis
        r = redis.Redis.from_url(INTEGRATION_TEST_CONFIG["REDIS_URL"])
        r.ping()
        return True
    except Exception:
        return False

def check_network_available() -> bool:
    """检查网络连接是否可用"""
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except Exception:
        return False

def get_system_resources() -> Dict[str, Any]:
    """获取系统资源信息"""
    try:
        import psutil
        return {
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "disk_free": psutil.disk_usage('/').free,
            "docker_available": check_docker_available(),
            "redis_available": check_redis_available(),
            "network_available": check_network_available(),
        }
    except ImportError:
        return {
            "docker_available": check_docker_available(),
            "redis_available": check_redis_available(),
            "network_available": check_network_available(),
        }

# ====================================
# 跳过条件
# ====================================

# 跳过条件定义
skip_if_no_docker = pytest.mark.skipif(
    not check_docker_available(),
    reason="Docker不可用，跳过需要Docker的集成测试"
)

skip_if_no_redis = pytest.mark.skipif(
    not check_redis_available(),
    reason="Redis不可用，跳过需要Redis的集成测试"
)

skip_if_no_network = pytest.mark.skipif(
    not check_network_available(),
    reason="网络不可用，跳过需要网络的集成测试"
)

# 资源需求检查
skip_if_low_resources = pytest.mark.skipif(
    False,  # 默认不跳过，可以根据实际需求调整
    reason="系统资源不足，跳过资源密集型测试"
)

# ====================================
# 测试标记
# ====================================

class IntegrationTestMarkers:
    """集成测试标记"""
    API = pytest.mark.api
    DOCKER = pytest.mark.docker
    REDIS = pytest.mark.redis
    NETWORK = pytest.mark.network
    SLOW = pytest.mark.slow
    PERFORMANCE = pytest.mark.performance
    SYSTEM = pytest.mark.system
    E2E = pytest.mark.e2e  # end-to-end

# ====================================
# 数据生成工具
# ====================================

def generate_integration_test_data():
    """生成集成测试数据"""
    return {
        "containers": {
            "basic_centos": {
                "name": "integration-test-centos",
                "image": "centos:7",
                "command": ["sleep", "3600"],
                "labels": {"test": "integration"}
            },
            "web_service": {
                "name": "integration-test-nginx",
                "image": "nginx:alpine",
                "ports": {"80/tcp": None},  # 随机端口
                "labels": {"test": "integration", "service": "web"}
            }
        },
        "builds": {
            "simple_build": {
                "name": "integration-test-build",
                "dockerfile_content": """
FROM centos:7
RUN echo "Integration test build"
RUN yum install -y which
CMD ["echo", "Hello Integration Test"]
                """.strip(),
                "labels": {"test": "integration"}
            },
            "rpm_build": {
                "name": "integration-rpm-build",
                "dockerfile_content": """
FROM centos:7
RUN yum update -y && yum install -y rpm-build make gcc
RUN useradd -m builder
USER builder
WORKDIR /home/builder
CMD ["/bin/bash"]
                """.strip(),
                "context_files": {
                    "test.spec": """
Name:           integration-test
Version:        1.0.0  
Release:        1%{?dist}
Summary:        Integration test package

License:        MIT
Source0:        %{name}-%{version}.tar.gz

%description
Integration test package for EulerMaker Docker Optimizer.

%files

%changelog
* Mon Dec 01 2025 Test <test@example.com> - 1.0.0-1
- Initial integration test package
                    """.strip()
                },
                "labels": {"test": "integration", "build": "rpm"}
            }
        },
        "api_test_cases": {
            "container_crud": [
                {"method": "POST", "path": "/api/v1/containers", "description": "创建容器"},
                {"method": "GET", "path": "/api/v1/containers", "description": "列出容器"},
                {"method": "GET", "path": "/api/v1/containers/{id}", "description": "获取容器详情"},
                {"method": "POST", "path": "/api/v1/containers/{id}/start", "description": "启动容器"},
                {"method": "POST", "path": "/api/v1/containers/{id}/stop", "description": "停止容器"},
                {"method": "DELETE", "path": "/api/v1/containers/{id}", "description": "删除容器"}
            ],
            "build_crud": [
                {"method": "POST", "path": "/api/v1/builds", "description": "创建构建任务"},
                {"method": "GET", "path": "/api/v1/builds", "description": "列出构建任务"},
                {"method": "GET", "path": "/api/v1/builds/{id}", "description": "获取构建详情"},
                {"method": "POST", "path": "/api/v1/builds/{id}/execute", "description": "执行构建"},
                {"method": "GET", "path": "/api/v1/builds/{id}/logs", "description": "获取构建日志"},
                {"method": "DELETE", "path": "/api/v1/builds/{id}", "description": "删除构建任务"}
            ]
        }
    }

# ====================================
# 上下文管理器
# ====================================

@contextmanager
def integration_test_environment():
    """集成测试环境上下文管理器"""
    helper = IntegrationTestHelper()

    try:
        # 设置环境变量
        original_env = dict(os.environ)
        for key, value in INTEGRATION_TEST_CONFIG.items():
            os.environ[key] = str(value)

        # 创建必要的目录
        for path_key in ["BUILD_PATH", "UPLOAD_PATH", "LOG_PATH", "CACHE_PATH"]:
            path = Path(INTEGRATION_TEST_CONFIG[path_key])
            path.mkdir(parents=True, exist_ok=True)

        yield helper

    finally:
        # 清理测试资源
        if INTEGRATION_TEST_CONFIG.get("CLEANUP_AFTER_TESTS", True):
            helper.cleanup()

        # 恢复环境变量
        os.environ.clear()
        os.environ.update(original_env)

@contextmanager
def temporary_service(service_class, *args, **kwargs):
    """临时服务上下文管理器"""
    service = None
    try:
        service = service_class(*args, **kwargs)
        if hasattr(service, 'start'):
            service.start()
        yield service
    finally:
        if service and hasattr(service, 'stop'):
            try:
                service.stop()
            except Exception:
                pass
        if service and hasattr(service, 'cleanup'):
            try:
                service.cleanup()
            except Exception:
                pass

# ====================================
# 等待工具
# ====================================

async def wait_for_condition_async(
        condition_func,
        timeout: int = 30,
        interval: float = 0.5,
        description: str = "condition"
) -> bool:
    """异步等待条件满足"""
    import time
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            if asyncio.iscoroutinefunction(condition_func):
                result = await condition_func()
            else:
                result = condition_func()

            if result:
                return True
        except Exception:
            pass  # 忽略检查过程中的异常

        await asyncio.sleep(interval)

    raise TimeoutError(f"等待{description}超时 ({timeout}秒)")

def wait_for_condition(
        condition_func,
        timeout: int = 30,
        interval: float = 0.5,
        description: str = "condition"
) -> bool:
    """同步等待条件满足"""
    import time
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            if condition_func():
                return True
        except Exception:
            pass  # 忽略检查过程中的异常

        time.sleep(interval)

    raise TimeoutError(f"等待{description}超时 ({timeout}秒)")

# ====================================
# HTTP客户端工具
# ====================================

class IntegrationTestHTTPClient:
    """集成测试HTTP客户端"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = None

    async def __aenter__(self):
        import httpx
        self.session = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()

    async def get(self, path: str, **kwargs):
        """发送GET请求"""
        return await self.session.get(path, **kwargs)

    async def post(self, path: str, **kwargs):
        """发送POST请求"""
        return await self.session.post(path, **kwargs)

    async def put(self, path: str, **kwargs):
        """发送PUT请求"""
        return await self.session.put(path, **kwargs)

    async def delete(self, path: str, **kwargs):
        """发送DELETE请求"""
        return await self.session.delete(path, **kwargs)

    async def wait_for_service(self, health_path: str = "/health", timeout: int = 30):
        """等待服务就绪"""
        async def check_health():
            try:
                response = await self.get(health_path)
                return response.status_code == 200
            except Exception:
                return False

        await wait_for_condition_async(
            check_health,
            timeout=timeout,
            description=f"服务在{self.base_url}上启动"
        )

# ====================================
# 导出的测试工具
# ====================================

__all__ = [
    # 配置
    "INTEGRATION_TEST_CONFIG",
    "INTEGRATION_TESTS_DIR",
    "TEST_DATA_DIR",
    "TEST_FIXTURES_DIR",

    # 工具类
    "IntegrationTestHelper",
    "IntegrationTestHTTPClient",

    # 环境检查
    "check_docker_available",
    "check_redis_available",
    "check_network_available",
    "get_system_resources",

    # 跳过条件
    "skip_if_no_docker",
    "skip_if_no_redis",
    "skip_if_no_network",
    "skip_if_low_resources",

    # 测试标记
    "IntegrationTestMarkers",

    # 数据生成
    "generate_integration_test_data",

    # 上下文管理器
    "integration_test_environment",
    "temporary_service",

    # 等待工具
    "wait_for_condition",
    "wait_for_condition_async",
]