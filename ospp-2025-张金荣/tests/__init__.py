"""
EulerMaker Docker Optimizer 测试包

******OSPP-2025-张金荣******

包含项目的所有测试代码，包括：
- 单元测试：测试单个模块和类的功能
- 集成测试：测试模块间的交互和端到端流程
- 测试数据和配置：提供测试所需的固定数据和配置
- 测试工具：辅助测试的工具函数和类

测试结构：
- unit/：单元测试，测试单个组件的功能
- integration/：集成测试，测试组件间的协作
- fixtures/：测试数据和固定配置
- conftest.py：pytest配置和共享fixtures

测试规范：
1. 所有测试文件以test_开头
2. 测试类以Test开头
3. 测试方法以test_开头
4. 使用pytest框架进行测试
5. 使用mock模拟外部依赖
6. 确保测试的独立性和可重复性

使用方式：
    # 运行所有测试
    pytest tests/

    # 运行单元测试
    pytest tests/unit/

    # 运行集成测试
    pytest tests/integration/

    # 运行特定测试文件
    pytest tests/unit/test_docker_manager.py

    # 运行带覆盖率报告的测试
    pytest tests/ --cov=src --cov-report=html

    # 运行详细输出的测试
    pytest tests/ -v

    # 运行失败时停止的测试
    pytest tests/ -x

版本: 1.0.0
作者: 张金荣
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径，确保测试可以导入src模块
TEST_DIR = Path(__file__).parent
PROJECT_ROOT = TEST_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 测试配置常量
TEST_CONFIG = {
    "DB_URL": "sqlite:///:memory:",  # 使用内存数据库进行测试
    "REDIS_URL": "redis://localhost:6379/15",  # 使用测试专用Redis数据库
    "LOG_LEVEL": "DEBUG",
    "TESTING": True,
    "API_HOST": "127.0.0.1",
    "API_PORT": 0,  # 使用随机端口进行测试
    "RPC_PORT": 0,
    "DOCKER_SOCKET": "/var/run/docker.sock",
    "TEST_DATA_DIR": str(TEST_DIR / "fixtures" / "data"),
    "TEST_TEMP_DIR": "/tmp/eulermaker_tests",
}

# 测试环境设置
def setup_test_environment():
    """设置测试环境"""
    # 设置环境变量
    for key, value in TEST_CONFIG.items():
        os.environ[key] = str(value)

    # 创建测试临时目录
    test_temp_dir = Path(TEST_CONFIG["TEST_TEMP_DIR"])
    test_temp_dir.mkdir(parents=True, exist_ok=True)

    # 设置测试数据目录
    test_data_dir = Path(TEST_CONFIG["TEST_DATA_DIR"])
    test_data_dir.mkdir(parents=True, exist_ok=True)

def cleanup_test_environment():
    """清理测试环境"""
    import shutil

    # 清理测试临时目录
    test_temp_dir = Path(TEST_CONFIG["TEST_TEMP_DIR"])
    if test_temp_dir.exists():
        shutil.rmtree(test_temp_dir, ignore_errors=True)

# 测试标记
class TestMarkers:
    """测试标记常量"""
    UNIT = "unit"           # 单元测试
    INTEGRATION = "integration"  # 集成测试
    SLOW = "slow"           # 慢测试
    DOCKER = "docker"       # 需要Docker的测试
    NETWORK = "network"     # 需要网络的测试
    DATABASE = "database"   # 需要数据库的测试
    REDIS = "redis"         # 需要Redis的测试
    FILESYSTEM = "filesystem"  # 需要文件系统的测试

# 测试工具函数
def skip_if_no_docker():
    """如果没有Docker则跳过测试的装饰器"""
    import pytest
    import docker

    try:
        client = docker.from_env()
        client.ping()
        return pytest.mark.skipif(False, reason="")
    except Exception:
        return pytest.mark.skipif(True, reason="Docker不可用")

def skip_if_no_redis():
    """如果没有Redis则跳过测试的装饰器"""
    import pytest

    try:
        import redis
        r = redis.Redis.from_url(TEST_CONFIG["REDIS_URL"])
        r.ping()
        return pytest.mark.skipif(False, reason="")
    except Exception:
        return pytest.mark.skipif(True, reason="Redis不可用")

# 自动设置测试环境
setup_test_environment()

# 测试版本信息
__version__ = "1.0.0"
__author__ = "张金荣"
__email__ = "3487232360@qq.com"

# 导出测试相关的常量和函数
__all__ = [
    "TEST_CONFIG",
    "TestMarkers",
    "setup_test_environment",
    "cleanup_test_environment",
    "skip_if_no_docker",
    "skip_if_no_redis",
    "TEST_DIR",
    "PROJECT_ROOT",
    "SRC_DIR",
]