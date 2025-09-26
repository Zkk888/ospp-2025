"""
API端点集成测试

******OSPP-2025-张金荣******

测试所有API端点的完整功能，包括：
- 容器管理API的CRUD操作
- 构建管理API的完整流程
- API响应格式和错误处理
- API之间的数据流和状态同步
- API性能和并发处理
- 认证和授权（如果有）
- WebSocket连接和实时通信
- API版本兼容性

版本: 1.0.0
作者: 张金荣
"""

import pytest
import asyncio
import json
import time
from typing import Dict, Any, List, Optional
from pathlib import Path

# 导入集成测试工具
from tests.integration import (
    IntegrationTestMarkers,
    IntegrationTestHTTPClient,
    integration_test_environment,
    temporary_service,
    wait_for_condition_async,
    generate_integration_test_data,
    skip_if_no_docker,
    skip_if_no_redis
)

# 导入被测试的API服务
try:
    from api.web_server import WebServer
    from api.websocket_server import WebSocketServer
    from api.rpc_server import RPCServer
    from services.container_service import ContainerService
    from services.build_service import BuildService
    from core.docker_manager import DockerManager
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入API模块: {e}")
    IMPORTS_AVAILABLE = False

# 跳过测试如果导入失败
pytestmark = pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="API模块不可用")

# ====================================
# API端点基础测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.API
class TestAPIBasics:
    """API基础功能测试类"""

    @pytest.mark.asyncio
    async def test_api_server_startup_and_health(self):
        """测试API服务器启动和健康检查"""
        with integration_test_environment() as helper:
            # 创建Web服务器
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                # 获取实际端口
                server_port = web_server.get_port()
                assert server_port > 0

                # 创建HTTP客户端
                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    # 等待服务就绪
                    await client.wait_for_service("/health")

                    # 测试健康检查端点
                    response = await client.get("/health")
                    assert response.status_code == 200

                    health_data = response.json()
                    assert health_data["status"] == "healthy"
                    assert "timestamp" in health_data
                    assert "version" in health_data

    @pytest.mark.asyncio
    async def test_api_info_endpoint(self):
        """测试API信息端点"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 测试API信息
                    response = await client.get("/api/v1/info")
                    assert response.status_code == 200

                    info_data = response.json()
                    assert info_data["name"] == "EulerMaker Docker Optimizer"
                    assert "version" in info_data
                    assert "api_version" in info_data
                    assert "docker_info" in info_data

    @pytest.mark.asyncio
    async def test_api_cors_headers(self):
        """测试API CORS头设置"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 发送CORS预检请求
                    response = await client.request(
                        "OPTIONS",
                        "/api/v1/containers",
                        headers={
                            "Origin": "http://localhost:3000",
                            "Access-Control-Request-Method": "POST",
                            "Access-Control-Request-Headers": "Content-Type"
                        }
                    )

                    assert response.status_code == 200
                    assert "Access-Control-Allow-Origin" in response.headers
                    assert "Access-Control-Allow-Methods" in response.headers

# ====================================
# 容器API集成测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.API
@IntegrationTestMarkers.DOCKER
@skip_if_no_docker
class TestContainerAPI:
    """容器API集成测试类"""

    @pytest.mark.asyncio
    async def test_container_crud_operations(self):
        """测试容器CRUD操作完整流程"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 1. 创建容器
                    container_config = {
                        "name": "integration-test-container",
                        "image": "hello-world",
                        "command": ["echo", "integration test"],
                        "auto_remove": True
                    }

                    create_response = await client.post(
                        "/api/v1/containers",
                        json=container_config
                    )
                    assert create_response.status_code == 201

                    create_data = create_response.json()
                    assert create_data["success"] is True
                    container_id = create_data["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 2. 获取容器详情
                    get_response = await client.get(f"/api/v1/containers/{container_id}")
                    assert get_response.status_code == 200

                    get_data = get_response.json()
                    assert get_data["data"]["container"]["id"] == container_id
                    assert get_data["data"]["container"]["name"] == container_config["name"]

                    # 3. 列出容器
                    list_response = await client.get("/api/v1/containers")
                    assert list_response.status_code == 200

                    list_data = list_response.json()
                    container_ids = [c["id"] for c in list_data["data"]["containers"]]
                    assert container_id in container_ids

                    # 4. 启动容器
                    start_response = await client.post(f"/api/v1/containers/{container_id}/start")
                    assert start_response.status_code == 200

                    # 5. 等待容器完成（hello-world会自动退出）
                    async def container_exited():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        if response.status_code == 200:
                            data = response.json()
                            return data["data"]["container"]["status"] == "exited"
                        return False

                    await wait_for_condition_async(container_exited, timeout=30, description="容器退出")

                    # 6. 获取容器日志
                    logs_response = await client.get(f"/api/v1/containers/{container_id}/logs")
                    assert logs_response.status_code == 200

                    logs_data = logs_response.json()
                    assert "integration test" in logs_data["data"]["logs"]

    @pytest.mark.asyncio
    async def test_container_lifecycle_operations(self):
        """测试容器生命周期操作"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建长期运行的容器
                    container_config = {
                        "name": "lifecycle-test-container",
                        "image": "alpine:latest",
                        "command": ["sleep", "300"],
                        "auto_remove": True
                    }

                    create_response = await client.post("/api/v1/containers", json=container_config)
                    container_id = create_response.json()["data"]["container"]["id"]
                    helper.register_container(container_id)

                    # 启动容器
                    start_response = await client.post(f"/api/v1/containers/{container_id}/start")
                    assert start_response.status_code == 200

                    # 等待容器运行
                    async def container_running():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        if response.status_code == 200:
                            data = response.json()
                            return data["data"]["container"]["status"] == "running"
                        return False

                    await wait_for_condition_async(container_running, description="容器启动")

                    # 暂停容器
                    pause_response = await client.post(f"/api/v1/containers/{container_id}/pause")
                    assert pause_response.status_code == 200

                    # 检查暂停状态
                    async def container_paused():
                        response = await client.get(f"/api/v1/containers/{container_id}")
                        if response.status_code == 200:
                            data = response.json()
                            return data["data"]["container"]["status"] == "paused"
                        return False

                    await wait_for_condition_async(container_paused, description="容器暂停")

                    # 恢复容器
                    unpause_response = await client.post(f"/api/v1/containers/{container_id}/unpause")
                    assert unpause_response.status_code == 200

                    # 停止容器
                    stop_response = await client.post(f"/api/v1/containers/{container_id}/stop")
                    assert stop_response.status_code == 200

                    # 删除容器
                    delete_response = await client.delete(f"/api/v1/containers/{container_id}")
                    assert delete_response.status_code == 200

    @pytest.mark.asyncio
    async def test_container_stats_and_monitoring(self):
        """测试容器统计和监控API"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建运行容器
                    container_config = {
                        "name": "stats-test-container",
                        "image": "alpine:latest",
                        "command": ["sh", "-c", "while true; do sleep 1; done"]
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

                    stats_data = stats_response.json()
                    assert "memory_usage" in stats_data["data"]["stats"]
                    assert "cpu_usage" in stats_data["data"]["stats"]

                    # 获取容器进程信息
                    processes_response = await client.get(f"/api/v1/containers/{container_id}/processes")
                    assert processes_response.status_code == 200

                    processes_data = processes_response.json()
                    assert len(processes_data["data"]["processes"]) > 0

# ====================================
# 构建API集成测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.API
@IntegrationTestMarkers.DOCKER
@skip_if_no_docker
class TestBuildAPI:
    """构建API集成测试类"""

    @pytest.mark.asyncio
    async def test_build_task_crud_operations(self):
        """测试构建任务CRUD操作"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建构建任务
                    build_config = {
                        "name": "integration-test-build",
                        "dockerfile_content": """
FROM alpine:latest
RUN echo "Integration test build"
CMD ["echo", "Build completed"]
                        """.strip()
                    }

                    create_response = await client.post("/api/v1/builds", json=build_config)
                    assert create_response.status_code == 201

                    create_data = create_response.json()
                    build_id = create_data["data"]["build"]["id"]

                    # 获取构建任务详情
                    get_response = await client.get(f"/api/v1/builds/{build_id}")
                    assert get_response.status_code == 200

                    get_data = get_response.json()
                    assert get_data["data"]["build"]["id"] == build_id
                    assert get_data["data"]["build"]["status"] == "pending"

                    # 列出构建任务
                    list_response = await client.get("/api/v1/builds")
                    assert list_response.status_code == 200

                    list_data = list_response.json()
                    build_ids = [b["id"] for b in list_data["data"]["builds"]]
                    assert build_id in build_ids

                    # 删除构建任务
                    delete_response = await client.delete(f"/api/v1/builds/{build_id}")
                    assert delete_response.status_code == 200

    @pytest.mark.asyncio
    async def test_build_execution_flow(self):
        """测试构建执行完整流程"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建简单的构建任务
                    build_config = {
                        "name": "execution-test-build",
                        "dockerfile_content": """
FROM hello-world
                        """.strip()
                    }

                    create_response = await client.post("/api/v1/builds", json=build_config)
                    build_id = create_response.json()["data"]["build"]["id"]

                    # 执行构建
                    execute_response = await client.post(f"/api/v1/builds/{build_id}/execute")
                    assert execute_response.status_code == 200

                    # 等待构建完成
                    async def build_completed():
                        response = await client.get(f"/api/v1/builds/{build_id}")
                        if response.status_code == 200:
                            data = response.json()
                            status = data["data"]["build"]["status"]
                            return status in ["completed", "failed"]
                        return False

                    await wait_for_condition_async(build_completed, timeout=120, description="构建完成")

                    # 获取构建结果
                    result_response = await client.get(f"/api/v1/builds/{build_id}")
                    result_data = result_response.json()

                    # 验证构建成功
                    assert result_data["data"]["build"]["status"] == "completed"
                    assert "image" in result_data["data"]["build"]

                    # 注册生成的镜像用于清理
                    if "image" in result_data["data"]["build"]:
                        image_id = result_data["data"]["build"]["image"]["id"]
                        helper.register_image(image_id)

                    # 获取构建日志
                    logs_response = await client.get(f"/api/v1/builds/{build_id}/logs")
                    assert logs_response.status_code == 200

                    logs_data = logs_response.json()
                    assert len(logs_data["data"]["logs"]) > 0

    @pytest.mark.asyncio
    async def test_build_with_context_files(self):
        """测试包含上下文文件的构建"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 创建包含上下文文件的构建
                    build_config = {
                        "name": "context-test-build",
                        "dockerfile_content": """
FROM alpine:latest
COPY test.txt /test.txt
RUN cat /test.txt
                        """.strip(),
                        "context_files": {
                            "test.txt": "Hello from context file!"
                        }
                    }

                    create_response = await client.post("/api/v1/builds", json=build_config)
                    build_id = create_response.json()["data"]["build"]["id"]

                    # 执行构建
                    execute_response = await client.post(f"/api/v1/builds/{build_id}/execute")
                    assert execute_response.status_code == 200

                    # 等待构建完成
                    async def build_completed():
                        response = await client.get(f"/api/v1/builds/{build_id}")
                        return response.json()["data"]["build"]["status"] in ["completed", "failed"]

                    await wait_for_condition_async(build_completed, timeout=120, description="构建完成")

                    # 验证构建成功
                    result_response = await client.get(f"/api/v1/builds/{build_id}")
                    result_data = result_response.json()
                    assert result_data["data"]["build"]["status"] == "completed"

                    # 验证日志包含上下文文件内容
                    logs_response = await client.get(f"/api/v1/builds/{build_id}/logs")
                    logs_data = logs_response.json()
                    logs_text = "\n".join(logs_data["data"]["logs"])
                    assert "Hello from context file!" in logs_text

# ====================================
# WebSocket API集成测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.API
class TestWebSocketAPI:
    """WebSocket API集成测试类"""

    @pytest.mark.asyncio
    async def test_websocket_connection_and_messages(self):
        """测试WebSocket连接和消息传递"""
        with integration_test_environment() as helper:
            # 启动WebSocket服务器
            ws_server = WebSocketServer(host="127.0.0.1", port=0)

            with temporary_service(ws_server):
                ws_port = ws_server.get_port()

                # 使用websockets库进行连接测试
                try:
                    import websockets

                    async with websockets.connect(f"ws://127.0.0.1:{ws_port}/ws") as websocket:
                        # 发送ping消息
                        ping_message = {"type": "ping", "timestamp": time.time()}
                        await websocket.send(json.dumps(ping_message))

                        # 接收pong响应
                        response = await websocket.recv()
                        response_data = json.loads(response)

                        assert response_data["type"] == "pong"

                except ImportError:
                    pytest.skip("websockets库不可用，跳过WebSocket测试")

    @pytest.mark.asyncio
    async def test_websocket_real_time_logs(self):
        """测试WebSocket实时日志推送"""
        with integration_test_environment() as helper:
            # 启动Web服务器和WebSocket服务器
            web_server = WebServer(host="127.0.0.1", port=0)
            ws_server = WebSocketServer(host="127.0.0.1", port=0)

            with temporary_service(web_server), temporary_service(ws_server):
                web_port = web_server.get_port()
                ws_port = ws_server.get_port()

                try:
                    import websockets

                    # 建立WebSocket连接
                    async with websockets.connect(f"ws://127.0.0.1:{ws_port}/ws") as websocket:
                        # 订阅实时日志
                        subscribe_message = {
                            "type": "subscribe",
                            "channel": "build_logs",
                            "build_id": "test_build_123"
                        }
                        await websocket.send(json.dumps(subscribe_message))

                        # 通过HTTP API创建构建任务
                        async with IntegrationTestHTTPClient(f"http://127.0.0.1:{web_port}") as client:
                            await client.wait_for_service()

                            build_config = {
                                "name": "websocket-logs-test",
                                "dockerfile_content": "FROM hello-world"
                            }

                            create_response = await client.post("/api/v1/builds", json=build_config)
                            build_id = create_response.json()["data"]["build"]["id"]

                            # 执行构建
                            await client.post(f"/api/v1/builds/{build_id}/execute")

                            # 接收WebSocket日志消息
                            log_messages = []
                            for _ in range(5):  # 最多接收5条消息
                                try:
                                    message = await asyncio.wait_for(websocket.recv(), timeout=10)
                                    message_data = json.loads(message)

                                    if message_data.get("type") == "build_log":
                                        log_messages.append(message_data)

                                        if "completed" in message_data.get("log", "").lower():
                                            break

                                except asyncio.TimeoutError:
                                    break

                            # 验证接收到日志消息
                            assert len(log_messages) > 0

                except ImportError:
                    pytest.skip("websockets库不可用，跳过WebSocket测试")

# ====================================
# API错误处理集成测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.API
class TestAPIErrorHandling:
    """API错误处理集成测试类"""

    @pytest.mark.asyncio
    async def test_api_validation_errors(self):
        """测试API参数验证错误"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 测试无效的容器配置
                    invalid_container_config = {
                        "name": "",  # 空名称
                        "image": "centos:7"
                    }

                    response = await client.post("/api/v1/containers", json=invalid_container_config)
                    assert response.status_code == 400

                    error_data = response.json()
                    assert error_data["success"] is False
                    assert "validation" in error_data["error"]["message"].lower()

                    # 测试无效的构建配置
                    invalid_build_config = {
                        "name": "test",
                        "dockerfile_content": ""  # 空Dockerfile
                    }

                    response = await client.post("/api/v1/builds", json=invalid_build_config)
                    assert response.status_code == 400

                    error_data = response.json()
                    assert error_data["success"] is False

    @pytest.mark.asyncio
    async def test_api_resource_not_found_errors(self):
        """测试API资源未找到错误"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 测试获取不存在的容器
                    response = await client.get("/api/v1/containers/nonexistent")
                    assert response.status_code == 404

                    error_data = response.json()
                    assert error_data["success"] is False
                    assert "not found" in error_data["error"]["message"].lower()

                    # 测试获取不存在的构建任务
                    response = await client.get("/api/v1/builds/nonexistent")
                    assert response.status_code == 404

                    error_data = response.json()
                    assert error_data["success"] is False

    @pytest.mark.asyncio
    async def test_api_rate_limiting(self):
        """测试API速率限制"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0, enable_rate_limiting=True)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 快速发送多个请求
                    responses = []
                    for i in range(20):
                        response = await client.get("/api/v1/containers")
                        responses.append(response.status_code)

                        if response.status_code == 429:  # Too Many Requests
                            break

                    # 验证至少有一些请求被限制
                    rate_limited_count = responses.count(429)
                    if web_server.rate_limiting_enabled:
                        assert rate_limited_count > 0

# ====================================
# API性能集成测试
# ====================================

@pytest.mark.integration
@IntegrationTestMarkers.API
@IntegrationTestMarkers.PERFORMANCE
class TestAPIPerformance:
    """API性能集成测试类"""

    @pytest.mark.asyncio
    async def test_api_response_times(self):
        """测试API响应时间"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 测试健康检查端点响应时间
                    start_time = time.time()
                    response = await client.get("/health")
                    end_time = time.time()

                    response_time = end_time - start_time
                    assert response.status_code == 200
                    assert response_time < 1.0  # 1秒内响应

                    # 测试容器列表端点响应时间
                    start_time = time.time()
                    response = await client.get("/api/v1/containers")
                    end_time = time.time()

                    response_time = end_time - start_time
                    assert response.status_code == 200
                    assert response_time < 5.0  # 5秒内响应

    @pytest.mark.asyncio
    async def test_api_concurrent_requests(self):
        """测试API并发请求处理"""
        with integration_test_environment() as helper:
            web_server = WebServer(host="127.0.0.1", port=0)

            with temporary_service(web_server):
                server_port = web_server.get_port()

                async with IntegrationTestHTTPClient(f"http://127.0.0.1:{server_port}") as client:
                    await client.wait_for_service()

                    # 并发发送多个请求
                    async def make_request():
                        response = await client.get("/api/v1/containers")
                        return response.status_code

                    tasks = [make_request() for _ in range(10)]
                    status_codes = await asyncio.gather(*tasks)

                    # 验证所有请求都成功处理
                    assert all(code == 200 for code in status_codes)