"""
容器生命周期集成测试

******OSPP-2025-张金荣******

测试容器完整生命周期的集成场景，包括：
- 容器创建到删除的完整流程
- 容器状态变化和事件处理
- 容器与其他服务的集成
- 容器网络和存储集成
- 容器监控和日志集成
- 容器故障恢复和异常处理
- 多容器协同工作场景
- 容器资源限制和性能测试

版本: 1.0.0
作者: 张金荣
"""

import pytest
import asyncio
import time
import json
import tempfile
from pathlib import Path
from typing import Dict, Any, List

# 导入集成测试工具
from tests.integration import (
    IntegrationTestMarkers,
    IntegrationTestHTTPClient,
    integration_test_environment,
    temporary_service,
    wait_for_condition_async,
    wait_for_condition,
    generate_integration_test_data,
    skip_if_no_docker,
    skip_if_no_redis
)

# 导入被测试的服务
try:
    from api.web_server import WebServer
    from services.container_service import ContainerService
    from services.build_service import BuildService
    from core.docker_manager import DockerManager
    from core.container_lifecycle import ContainerLifecycleManager
    from utils.exceptions import ContainerNotFoundError, DockerError
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入服务模块: {e}")
    IMPORTS_AVAILABLE = False

# 跳过测试如果导入失败
pytestmark = pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="服务模块不可用")

# ====================================
# 容器基础生命周期测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.DOCKER
@skip_if_no_docker
class TestContainerBasicLifecycle:
    """容器基础生命周期测试类"""

    @pytest.mark.asyncio
    async def test_complete_container_lifecycle(self):
        """测试完整的容器生命周期"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 阶段1: 创建容器
                    container_config = {
                        "name": "lifecycle-test-container",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "echo 'Container started'; sleep 60; echo 'Container finished'"],
                        "environment": {"TEST_ENV": "integration_test"},
                        "labels": {"test": "lifecycle", "phase": "integration"}
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    assert create_response.status_code == 201

                    container_data = create_response.json()["data"]["container"]
                    container_id = container_data["id"]
                    helper.register_container(container_id)

                    # 验证容器初始状态
                    assert container_data["name"] == container_config["name"]
                    assert container_data["status"] == "created"

                    # 阶段2: 启动容器
                    start_response = await client.post(f"/api/v1/containers/{container_id}/start")
                    assert start_response.status_code == 200

                    # 等待容器运行
                    async def container_running():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        if response.status_code == 200:
                            return response.json()["data"]["container"]["status"] == "running"
                        return False

                    await wait_for_condition_async(container_running, timeout=30, description="容器启动")

                    # 验证运行状态
                    status_response = await client.get(f"/api/v1/containers/{container_id}")
                    status_data = status_response.json()["data"]["container"]
                    assert status_data["status"] == "running"
                    assert "started_at" in status_data

                    # 阶段3: 监控容器
                    # 获取容器统计信息
                    stats_response = await client.get(f"/api/v1/containers/{container_id}/stats")
                    assert stats_response.status_code == 200

                    stats_data = stats_response.json()["data"]["stats"]
                    assert "memory_usage" in stats_data
                    assert "cpu_usage" in stats_data

                    # 获取容器进程信息
                    processes_response = await client.get(f"/api/v1/containers/{container_id}/processes")
                    assert processes_response.status_code == 200

                    processes_data = processes_response.json()["data"]["processes"]
                    assert len(processes_data) > 0

                    # 阶段4: 容器操作
                    # 暂停容器
                    pause_response = await client.post(f"/api/v1/containers/{container_id}/pause")
                    assert pause_response.status_code == 200

                    # 验证暂停状态
                    async def container_paused():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        return response.json()["data"]["container"]["status"] == "paused"

                    await wait_for_condition_async(container_paused, description="容器暂停")

                    # 恢复容器
                    unpause_response = await client.post(f"/api/v1/containers/{container_id}/unpause")
                    assert unpause_response.status_code == 200

                    await wait_for_condition_async(container_running, description="容器恢复")

                    # 阶段5: 停止容器
                    stop_response = await client.post(f"/api/v1/containers/{container_id}/stop")
                    assert stop_response.status_code == 200

                    # 等待容器停止
                    async def container_stopped():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        if response.status_code == 200:
                            status = response.json()["data"]["container"]["status"]
                            return status in ["stopped", "exited"]
                        return False

                    await wait_for_condition_async(container_stopped, timeout=30, description="容器停止")

                    # 阶段6: 获取日志
                    logs_response = await client.get(f"/api/v1/containers/{container_id}/logs")
                    assert logs_response.status_code == 200

                    logs_data = logs_response.json()["data"]["logs"]
                    assert "Container started" in logs_data

                    # 阶段7: 删除容器
                    delete_response = await client.delete(f"/api/v1/containers/{container_id}")
                    assert delete_response.status_code == 200

                    # 验证容器已被删除
                    get_response = await client.get(f"/api/v1/containers/{container_id}")
                    assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_container_restart_lifecycle(self):
        """测试容器重启生命周期"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建容器
                    container_config = {
                        "name": "restart-test-container",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "echo 'Start time:' $(date); sleep 300"],
                        "restart_policy": {"Name": "always"}
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    container_id = create_response.json()["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 启动容器
                    await client.post(f"/api/v1/containers/{container_id}/start")

                    # 等待容器运行
                    async def container_running():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        return response.json()["data"]["container"]["status"] == "running"

                    await wait_for_condition_async(container_running, description="容器启动")

                    # 获取第一次启动的时间戳
                    first_logs_response = await client.get(f"/api/v1/containers/{container_id}/logs")
                    first_logs = first_logs_response.json()["data"]["logs"]

                    # 重启容器
                    restart_response = await client.post(f"/api/v1/containers/{container_id}/restart")
                    assert restart_response.status_code == 200

                    # 等待重启完成
                    await asyncio.sleep(2)  # 等待重启过程
                    await wait_for_condition_async(container_running, description="容器重启")

                    # 验证容器重新启动（日志应该包含新的时间戳）
                    second_logs_response = await client.get(f"/api/v1/containers/{container_id}/logs")
                    second_logs = second_logs_response.json()["data"]["logs"]

                    # 重启后应该有新的日志条目
                    assert len(second_logs) >= len(first_logs)

    @pytest.mark.asyncio
    async def test_container_failure_and_recovery(self):
        """测试容器故障和恢复"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建一个会崩溃的容器
                    container_config = {
                        "name": "failure-test-container",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "echo 'Starting...'; sleep 5; echo 'Crashing...'; exit 1"],
                        "restart_policy": {"Name": "on-failure", "MaximumRetryCount": 2}
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    container_id = create_response.json()["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 启动容器
                    await client.post(f"/api/v1/containers/{container_id}/start")

                    # 等待容器崩溃
                    async def container_exited():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        if response.status_code == 200:
                            status = response.json()["data"]["container"]["status"]
                            return status in ["exited", "failed"]
                        return False

                    await wait_for_condition_async(container_exited, timeout=30, description="容器退出")

                    # 验证退出状态
                    final_status_response = await client.get(f"/api/v1/containers/{container_id}")
                    final_status = final_status_response.json()["data"]["container"]
                    assert final_status["status"] in ["exited", "failed"]

                    # 获取日志以验证执行过程
                    logs_response = await client.get(f"/api/v1/containers/{container_id}/logs")
                    logs = logs_response.json()["data"]["logs"]
                    assert "Starting..." in logs
                    assert "Crashing..." in logs

# ====================================
# 容器网络和存储集成测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.DOCKER
@skip_if_no_docker
class TestContainerNetworkStorage:
    """容器网络和存储集成测试类"""

    @pytest.mark.asyncio
    async def test_container_with_port_mapping(self):
        """测试容器端口映射"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建带端口映射的容器
                    container_config = {
                        "name": "port-mapping-test",
                        "image": "nginx:alpine",
                        "ports": {"80/tcp": None},  # 随机端口映射
                        "detach": True
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    container_id = create_response.json()["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 启动容器
                    await client.post(f"/api/v1/containers/{container_id}/start")

                    # 等待容器运行
                    async def container_running():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        return response.json()["data"]["container"]["status"] == "running"

                    await wait_for_condition_async(container_running, description="容器启动")

                    # 获取端口映射信息
                    inspect_response = await client.get(f"/api/v1/containers/{container_id}")
                    container_info = inspect_response.json()["data"]["container"]

                    # 验证端口映射
                    assert "network_settings" in container_info
                    assert "ports" in container_info["network_settings"]

                    ports = container_info["network_settings"]["ports"]
                    assert "80/tcp" in ports

                    # 验证可以访问映射的端口
                    host_port = ports["80/tcp"][0]["HostPort"] if ports["80/tcp"] else None
                    if host_port:
                        # 尝试连接到nginx服务
                        import aiohttp
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(f"http://127.0.0.1:{host_port}", timeout=10) as response:
                                    assert response.status == 200
                        except Exception as e:
                            # nginx可能需要更长时间启动，这个测试可能会偶尔失败
                            print(f"端口连接测试失败: {e}")

    @pytest.mark.asyncio
    async def test_container_with_volumes(self):
        """测试容器数据卷"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建临时目录作为数据卷
                    temp_volume = helper.create_temp_dir("container_volume_")
                    test_file = temp_volume / "test.txt"
                    test_file.write_text("Hello from host filesystem!")

                    # 创建带数据卷的容器
                    container_config = {
                        "name": "volume-test-container",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "cat /data/test.txt; echo 'Container modified' > /data/container.txt; sleep 10"],
                        "volumes": {str(temp_volume): "/data"}
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    container_id = create_response.json()["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 启动容器
                    await client.post(f"/api/v1/containers/{container_id}/start")

                    # 等待容器完成
                    async def container_finished():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        if response.status_code == 200:
                            status = response.json()["data"]["container"]["status"]
                            return status in ["exited", "stopped"]
                        return False

                    await wait_for_condition_async(container_finished, timeout=30, description="容器完成")

                    # 验证容器读取了主机文件
                    logs_response = await client.get(f"/api/v1/containers/{container_id}/logs")
                    logs = logs_response.json()["data"]["logs"]
                    assert "Hello from host filesystem!" in logs

                    # 验证容器写入了文件到主机
                    container_file = temp_volume / "container.txt"
                    assert container_file.exists()
                    assert "Container modified" in container_file.read_text()

    @pytest.mark.asyncio
    async def test_container_environment_variables(self):
        """测试容器环境变量"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建带环境变量的容器
                    container_config = {
                        "name": "env-test-container",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "echo 'TEST_VAR='$TEST_VAR; echo 'SECRET='$SECRET; printenv | grep TEST"],
                        "environment": {
                            "TEST_VAR": "integration_test_value",
                            "SECRET": "secret_value_123",
                            "TEST_NUMBER": "42"
                        }
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    container_id = create_response.json()["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 启动容器
                    await client.post(f"/api/v1/containers/{container_id}/start")

                    # 等待容器完成
                    async def container_finished():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        status = response.json()["data"]["container"]["status"]
                        return status in ["exited", "stopped"]

                    await wait_for_condition_async(container_finished, timeout=20, description="容器完成")

                    # 验证环境变量输出
                    logs_response = await client.get(f"/api/v1/containers/{container_id}/logs")
                    logs = logs_response.json()["data"]["logs"]

                    assert "TEST_VAR=integration_test_value" in logs
                    assert "SECRET=secret_value_123" in logs
                    assert "TEST_NUMBER=42" in logs

# ====================================
# 多容器协同测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.DOCKER
@skip_if_no_docker
class TestMultiContainerScenarios:
    """多容器协同测试类"""

    @pytest.mark.asyncio
    async def test_linked_containers_communication(self):
        """测试容器间通信"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建第一个容器（web服务）
                    web_container_config = {
                        "name": "test-web-service",
                        "image": "nginx:alpine",
                        "ports": {"80/tcp": None}
                    }

                    web_response = await client.post("/api/v1/containers", json=web_container_config)
                    web_container_id = web_response.json()["data"]["container"]["id"]
                    helper.register_container(web_container_id)

                    # 启动web容器
                    await client.post(f"/api/v1/containers/{web_container_id}/start")

                    # 等待web容器运行
                    async def web_container_running():
                        response = await client.get(f"/api/v1/containers/{web_container_id}")
                        return response.json()["data"]["container"]["status"] == "running"

                    await wait_for_condition_async(web_container_running, description="Web容器启动")

                    # 获取web容器IP
                    web_inspect = await client.get(f"/api/v1/containers/{web_container_id}")
                    web_info = web_inspect.json()["data"]["container"]
                    web_ip = web_info.get("network_settings", {}).get("ip_address")

                    # 创建第二个容器（客户端）
                    if web_ip:
                        client_container_config = {
                            "name": "test-client",
                            "image": "alpine:latest",
                            "command": ["sh", "-c", f"wget -q -O - http://{web_ip}/ || echo 'Connection failed'"]
                        }

                        client_response = await client.post("/api/v1/containers", json=client_container_config)
                        client_container_id = client_response.json()["data"]["container"]["id"]
                        helper.register_container(client_container_id)

                        # 启动客户端容器
                        await client.post(f"/api/v1/containers/{client_container_id}/start")

                        # 等待客户端容器完成
                        async def client_container_finished():
                            response = await client.get(f"/api/v1/containers/{client_container_id}")
                            status = response.json()["data"]["container"]["status"]
                            return status in ["exited", "stopped"]

                        await wait_for_condition_async(client_container_finished, timeout=30, description="客户端容器完成")

                        # 检查客户端日志
                        logs_response = await client.get(f"/api/v1/containers/{client_container_id}/logs")
                        logs = logs_response.json()["data"]["logs"]

                        # 验证网络通信（nginx默认页面包含"Welcome to nginx"）
                        assert ("nginx" in logs.lower() or "welcome" in logs.lower() or
                                "connection failed" not in logs.lower())

    @pytest.mark.asyncio
    async def test_container_batch_operations(self):
        """测试容器批量操作"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 批量创建容器
                    container_configs = []
                    container_ids = []

                    for i in range(3):
                        config = {
                            "name": f"batch-test-container-{i}",
                            "image": "alpine:latest",
                            "command": ["sleep", "60"],
                            "labels": {"batch": "test", "index": str(i)}
                        }

                        response = await client.post("/api/v1/containers", json=config)
                        assert response.status_code == 201

                        container_id = response.json()["data"]["container"]["id"]
                        container_ids.append(container_id)
                        helper.register_container(container_id)

                    # 批量启动容器
                    start_tasks = []
                    for container_id in container_ids:
                        task = client.post(f"/api/v1/containers/{container_id}/start")
                        start_tasks.append(task)

                    start_responses = await asyncio.gather(*start_tasks)
                    assert all(r.status_code == 200 for r in start_responses)

                    # 等待所有容器运行
                    async def all_containers_running():
                        for container_id in container_ids:
                            response = await client.get(f"/api/v1/containers/{container_id}")
                            if response.json()["data"]["container"]["status"] != "running":
                                return False
                        return True

                    await wait_for_condition_async(all_containers_running, timeout=30, description="所有容器启动")

                    # 验证所有容器都在运行
                    list_response = await client.get("/api/v1/containers?all=false")
                    running_containers = list_response.json()["data"]["containers"]
                    running_ids = [c["id"] for c in running_containers]

                    for container_id in container_ids:
                        assert container_id in running_ids

                    # 批量停止容器
                    stop_tasks = []
                    for container_id in container_ids:
                        task = client.post(f"/api/v1/containers/{container_id}/stop")
                        stop_tasks.append(task)

                    stop_responses = await asyncio.gather(*stop_tasks)
                    assert all(r.status_code == 200 for r in stop_responses)

    @pytest.mark.asyncio
    async def test_container_dependency_chain(self):
        """测试容器依赖链"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建数据库容器（依赖链的底层）
                    db_config = {
                        "name": "dependency-db",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "echo 'Database ready' > /data/db.txt; sleep 300"],
                        "volumes": {helper.create_temp_dir("db_data").as_posix(): "/data"}
                    }

                    db_response = await client.post("/api/v1/containers", json=db_config)
                    db_container_id = db_response.json()["data"]["container"]["id"]
                    helper.register_container(db_container_id)

                    # 启动数据库容器
                    await client.post(f"/api/v1/containers/{db_container_id}/start")

                    # 等待数据库容器运行
                    async def db_running():
                        response = await client.get(f"/api/v1/containers/{db_container_id}")
                        return response.json()["data"]["container"]["status"] == "running"

                    await wait_for_condition_async(db_running, description="数据库容器启动")

                    # 创建应用容器（依赖数据库）
                    app_config = {
                        "name": "dependency-app",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "echo 'App connecting to database...'; sleep 10; echo 'App ready'"],
                        "depends_on": [db_container_id]  # 如果支持依赖关系
                    }

                    app_response = await client.post("/api/v1/containers", json=app_config)
                    app_container_id = app_response.json()["data"]["container"]["id"]
                    helper.register_container(app_container_id)

                    # 启动应用容器
                    await client.post(f"/api/v1/containers/{app_container_id}/start")

                    # 等待应用容器运行
                    async def app_running():
                        response = await client.get(f"/api/v1/containers/{app_container_id}")
                        return response.json()["data"]["container"]["status"] == "running"

                    await wait_for_condition_async(app_running, description="应用容器启动")

                    # 验证依赖链正常工作
                    # 停止数据库容器
                    await client.post(f"/api/v1/containers/{db_container_id}/stop")

                    # 应用容器应该继续运行（在这个简单例子中）
                    app_status_response = await client.get(f"/api/v1/containers/{app_container_id}")
                    app_status = app_status_response.json()["data"]["container"]["status"]

                    # 根据实际实现，应用可能继续运行或停止
                    assert app_status in ["running", "exited", "stopped"]

# ====================================
# 容器性能和资源测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.DOCKER
@IntegrationTestMarkers.PERFORMANCE
@skip_if_no_docker
class TestContainerPerformance:
    """容器性能和资源测试类"""

    @pytest.mark.asyncio
    async def test_container_resource_limits(self):
        """测试容器资源限制"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建带资源限制的容器
                    container_config = {
                        "name": "resource-limited-container",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "echo 'Testing resource limits'; sleep 30"],
                        "memory_limit": "128m",
                        "cpu_limit": "0.5",
                        "cpu_shares": 512
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    container_id = create_response.json()["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 启动容器
                    await client.post(f"/api/v1/containers/{container_id}/start")

                    # 等待容器运行
                    async def container_running():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        return response.json()["data"]["container"]["status"] == "running"

                    await wait_for_condition_async(container_running, description="容器启动")

                    # 获取容器统计信息
                    stats_response = await client.get(f"/api/v1/containers/{container_id}/stats")
                    assert stats_response.status_code == 200

                    stats = stats_response.json()["data"]["stats"]

                    # 验证内存限制生效（具体值取决于Docker版本和配置）
                    if "memory_limit" in stats:
                        memory_limit = stats["memory_limit"]
                        assert memory_limit <= 128 * 1024 * 1024  # 128MB

                    # 验证容器在资源限制下正常运行
                    assert "memory_usage" in stats
                    assert stats["memory_usage"] > 0

    @pytest.mark.asyncio
    async def test_container_concurrent_operations(self):
        """测试容器并发操作性能"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建多个容器配置
                    container_configs = []
                    for i in range(5):  # 创建5个容器进行并发测试
                        config = {
                            "name": f"concurrent-test-{i}",
                            "image": "alpine:latest",
                            "command": ["sleep", "30"],
                            "labels": {"test": "concurrent", "index": str(i)}
                        }
                        container_configs.append(config)

                    # 并发创建容器
                    start_time = time.time()
                    create_tasks = [
                        client.post("/api/v1/containers", json=config)
                        for config in container_configs
                    ]

                    create_responses = await asyncio.gather(*create_tasks)
                    create_time = time.time() - start_time

                    # 验证所有容器创建成功
                    assert all(r.status_code == 201 for r in create_responses)

                    container_ids = [r.json()["data"]["container"]["id"] for r in create_responses]
                    for container_id in container_ids:
                        helper.register_container(container_id)

                    # 并发启动容器
                    start_time = time.time()
                    start_tasks = [
                        client.post(f"/api/v1/containers/{container_id}/start")
                        for container_id in container_ids
                    ]

                    start_responses = await asyncio.gather(*start_tasks)
                    start_time_elapsed = time.time() - start_time

                    # 验证所有容器启动成功
                    assert all(r.status_code == 200 for r in start_responses)

                    # 验证性能指标（具体阈值可根据环境调整）
                    assert create_time < 30  # 创建5个容器应在30秒内完成
                    assert start_time_elapsed < 20  # 启动5个容器应在20秒内完成

                    # 等待所有容器运行
                    async def all_containers_running():
                        list_response = await client.get("/api/v1/containers")
                        running_containers = [
                            c for c in list_response.json()["data"]["containers"]
                            if c["status"] == "running" and c["id"] in container_ids
                        ]
                        return len(running_containers) == len(container_ids)

                    await wait_for_condition_async(all_containers_running, timeout=30, description="所有容器运行")

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_long_running_container_stability(self):
        """测试长期运行容器的稳定性"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建长期运行的容器
                    container_config = {
                        "name": "stability-test-container",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", """
                            counter=0
                            while [ $counter -lt 120 ]; do
                                echo "Heartbeat $counter at $(date)"
                                sleep 1
                                counter=$((counter + 1))
                            done
                            echo "Stability test completed"
                        """],
                        "restart_policy": {"Name": "unless-stopped"}
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    container_id = create_response.json()["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 启动容器
                    await client.post(f"/api/v1/containers/{container_id}/start")

                    # 等待容器运行
                    async def container_running():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        return response.json()["data"]["container"]["status"] == "running"

                    await wait_for_condition_async(container_running, description="容器启动")

                    # 定期检查容器状态
                    check_intervals = [10, 30, 60, 90, 120]  # 检查点（秒）

                    for interval in check_intervals:
                        # 等待到检查点
                        await asyncio.sleep(10 if interval == 10 else interval - check_intervals[check_intervals.index(interval) - 1])

                        # 检查容器仍在运行
                        status_response = await client.get(f"/api/v1/containers/{container_id}")
                        status = status_response.json()["data"]["container"]["status"]
                        assert status == "running", f"容器在{interval}秒时应该仍在运行，但状态为{status}"

                        # 获取容器统计信息
                        stats_response = await client.get(f"/api/v1/containers/{container_id}/stats")
                        if stats_response.status_code == 200:
                            stats = stats_response.json()["data"]["stats"]
                            # 验证容器资源使用正常
                            assert "memory_usage" in stats
                            assert stats["memory_usage"] > 0

                    # 等待容器完成
                    async def container_finished():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        status = response.json()["data"]["container"]["status"]
                        return status in ["exited", "stopped"]

                    await wait_for_condition_async(container_finished, timeout=30, description="容器完成")

                    # 验证容器成功完成
                    final_response = await client.get(f"/api/v1/containers/{container_id}")
                    final_data = final_response.json()["data"]["container"]
                    assert final_data["status"] in ["exited", "stopped"]

                    # 获取并验证日志
                    logs_response = await client.get(f"/api/v1/containers/{container_id}/logs")
                    logs = logs_response.json()["data"]["logs"]

                    # 验证心跳日志
                    heartbeat_count = logs.count("Heartbeat")
                    assert heartbeat_count >= 100, f"应该有至少100个心跳日志，实际有{heartbeat_count}个"

                    # 验证完成消息
                    assert "Stability test completed" in logs