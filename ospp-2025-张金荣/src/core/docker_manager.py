"""
Docker API封装管理器 - eulermaker-docker-optimizer的Docker集成核心

******OSPP-2025-张金荣******

提供对Docker API的完整封装，包括：
- 异步Docker客户端管理
- 容器操作（创建、启动、停止、删除等）
- 镜像管理（拉取、构建、删除等）
- 网络和数据卷管理
- 系统信息获取和监控
- 事件流处理
"""

import asyncio
from typing import Dict, List, Optional, Any, Union, AsyncGenerator
from datetime import datetime
import aiodocker
from aiodocker import Docker
from aiodocker.exceptions import DockerError as AioDockerError

from config.settings import get_docker_settings
from utils.logger import get_logger, LoggerMixin, log_performance, log_errors
from utils.exceptions import DockerError, ContainerError, ImageError
from utils.helpers import generate_uuid, format_timestamp, retry_async, timeout_async
from models.container_model import (
    ContainerInfo, ContainerConfig, ContainerStatus, ContainerStats, ContainerEvent
)


class DockerClient:
    """Docker客户端封装类"""

    def __init__(self):
        self.logger = get_logger(f"{__name__}.DockerClient")
        self._client: Optional[Docker] = None
        self._connected = False
        self._settings = get_docker_settings()

    async def connect(self) -> bool:
        """连接到Docker守护进程"""
        try:
            if self._client:
                await self.disconnect()

            # 创建Docker客户端连接
            self._client = Docker(
                url=self._settings.base_url,
                api_version=self._settings.api_version,
                timeout=self._settings.timeout
            )

            # 测试连接
            await self._client.version()
            self._connected = True

            self.logger.info(
                f"Successfully connected to Docker daemon at {self._settings.base_url}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Docker daemon: {str(e)}")
            self._connected = False
            if self._client:
                try:
                    await self._client.close()
                except:
                    pass
                self._client = None
            raise DockerError(f"Failed to connect to Docker: {str(e)}", docker_error=e)

    async def disconnect(self):
        """断开Docker连接"""
        if self._client:
            try:
                await self._client.close()
                self.logger.info("Disconnected from Docker daemon")
            except Exception as e:
                self.logger.warning(f"Error during Docker disconnect: {str(e)}")
            finally:
                self._client = None
                self._connected = False

    @property
    def client(self) -> Docker:
        """获取Docker客户端实例"""
        if not self._client or not self._connected:
            raise DockerError("Docker client is not connected")
        return self._client

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self._client is not None

    async def ping(self) -> bool:
        """测试Docker连接"""
        try:
            if not self.is_connected:
                return False
            await self._client.version()
            return True
        except Exception:
            self._connected = False
            return False


class DockerManager(LoggerMixin):
    """Docker管理器 - 提供高级Docker操作接口"""

    def __init__(self):
        super().__init__()
        self._client = DockerClient()
        self._event_listeners = {}  # 事件监听器
        self._monitoring_task = None  # 监控任务
        self._initialized = False

    async def initialize(self) -> bool:
        """初始化Docker管理器"""
        try:
            # 连接Docker守护进程
            await self._client.connect()

            # 启动事件监控
            await self._start_event_monitoring()

            self._initialized = True
            self.logger.info("Docker manager initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize Docker manager: {str(e)}")
            raise DockerError(f"Docker manager initialization failed: {str(e)}", docker_error=e)

    async def cleanup(self):
        """清理资源"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        await self._client.disconnect()
        self._initialized = False
        self.logger.info("Docker manager cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized and self._client.is_connected

    async def is_healthy(self) -> bool:
        """检查Docker服务健康状态"""
        try:
            return await self._client.ping()
        except Exception:
            return False

    # ================== 系统信息 ==================

    @log_performance("get_docker_info")
    async def get_system_info(self) -> Dict[str, Any]:
        """获取Docker系统信息"""
        try:
            client = self._client.client
            info = await client.system.info()
            version = await client.version()

            return {
                "info": info,
                "version": version,
                "timestamp": format_timestamp()
            }
        except Exception as e:
            raise DockerError(f"Failed to get system info: {str(e)}", docker_error=e)

    async def get_system_df(self) -> Dict[str, Any]:
        """获取Docker存储使用情况"""
        try:
            client = self._client.client
            df_info = await client.system.df()
            return df_info
        except Exception as e:
            raise DockerError(f"Failed to get system df: {str(e)}", docker_error=e)

    # ================== 容器管理 ==================

    @log_performance("create_container")
    async def create_container(self, config: ContainerConfig) -> str:
        """创建容器"""
        try:
            client = self._client.client

            # 转换配置为Docker API格式
            docker_config = config.to_docker_config()

            self.logger.debug(
                f"Creating container with config: {docker_config}",
                extra={"container_name": config.name}
            )

            # 创建容器
            container = await client.containers.create(
                config=docker_config["config"],
                name=docker_config["name"],
                **docker_config["host_config"]
            )

            container_id = container.id
            self.logger.info(
                f"Container created successfully: {config.name}",
                extra={"container_id": container_id, "container_name": config.name}
            )

            return container_id

        except AioDockerError as e:
            if e.status == 409:  # 容器已存在
                raise ContainerError(
                    f"Container already exists: {config.name}",
                    container_name=config.name,
                    operation="create",
                    docker_error=e
                )
            elif e.status == 404:  # 镜像不存在
                raise ImageError(
                    f"Image not found: {config.image}",
                    image_name=config.image,
                    docker_error=e
                )
            else:
                raise ContainerError(
                    f"Failed to create container: {str(e)}",
                    container_name=config.name,
                    operation="create",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error creating container: {str(e)}",
                container_name=config.name,
                operation="create",
                cause=e
            )

    @log_performance("start_container")
    async def start_container(self, container_id: str) -> bool:
        """启动容器"""
        try:
            client = self._client.client
            container = client.containers.container(container_id)

            await container.start()

            self.logger.info(
                f"Container started successfully",
                extra={"container_id": container_id}
            )

            return True

        except AioDockerError as e:
            if e.status == 404:
                raise ContainerError(
                    f"Container not found: {container_id}",
                    container_id=container_id,
                    operation="start",
                    docker_error=e
                )
            elif e.status == 304:
                # 容器已经在运行
                self.logger.debug(f"Container already running: {container_id}")
                return True
            else:
                raise ContainerError(
                    f"Failed to start container: {str(e)}",
                    container_id=container_id,
                    operation="start",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error starting container: {str(e)}",
                container_id=container_id,
                operation="start",
                cause=e
            )

    @log_performance("stop_container")
    async def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """停止容器"""
        try:
            client = self._client.client
            container = client.containers.container(container_id)

            await container.stop(timeout=timeout)

            self.logger.info(
                f"Container stopped successfully",
                extra={"container_id": container_id, "timeout": timeout}
            )

            return True

        except AioDockerError as e:
            if e.status == 404:
                raise ContainerError(
                    f"Container not found: {container_id}",
                    container_id=container_id,
                    operation="stop",
                    docker_error=e
                )
            elif e.status == 304:
                # 容器已经停止
                self.logger.debug(f"Container already stopped: {container_id}")
                return True
            else:
                raise ContainerError(
                    f"Failed to stop container: {str(e)}",
                    container_id=container_id,
                    operation="stop",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error stopping container: {str(e)}",
                container_id=container_id,
                operation="stop",
                cause=e
            )

    @log_performance("restart_container")
    async def restart_container(self, container_id: str, timeout: int = 10) -> bool:
        """重启容器"""
        try:
            client = self._client.client
            container = client.containers.container(container_id)

            await container.restart(timeout=timeout)

            self.logger.info(
                f"Container restarted successfully",
                extra={"container_id": container_id, "timeout": timeout}
            )

            return True

        except AioDockerError as e:
            if e.status == 404:
                raise ContainerError(
                    f"Container not found: {container_id}",
                    container_id=container_id,
                    operation="restart",
                    docker_error=e
                )
            else:
                raise ContainerError(
                    f"Failed to restart container: {str(e)}",
                    container_id=container_id,
                    operation="restart",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error restarting container: {str(e)}",
                container_id=container_id,
                operation="restart",
                cause=e
            )

    @log_performance("remove_container")
    async def remove_container(self, container_id: str, force: bool = False,
                               remove_volumes: bool = False) -> bool:
        """删除容器"""
        try:
            client = self._client.client
            container = client.containers.container(container_id)

            await container.delete(force=force, v=remove_volumes)

            self.logger.info(
                f"Container removed successfully",
                extra={
                    "container_id": container_id,
                    "force": force,
                    "remove_volumes": remove_volumes
                }
            )

            return True

        except AioDockerError as e:
            if e.status == 404:
                # 容器不存在，认为删除成功
                self.logger.debug(f"Container not found (already removed): {container_id}")
                return True
            elif e.status == 409:
                if not force:
                    raise ContainerError(
                        f"Cannot remove running container (use force=True): {container_id}",
                        container_id=container_id,
                        operation="remove",
                        docker_error=e
                    )
                else:
                    raise ContainerError(
                        f"Failed to force remove container: {str(e)}",
                        container_id=container_id,
                        operation="remove",
                        docker_error=e
                    )
            else:
                raise ContainerError(
                    f"Failed to remove container: {str(e)}",
                    container_id=container_id,
                    operation="remove",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error removing container: {str(e)}",
                container_id=container_id,
                operation="remove",
                cause=e
            )

    @log_performance("get_container_info")
    async def get_container_info(self, container_id: str) -> ContainerInfo:
        """获取容器信息"""
        try:
            client = self._client.client
            container = client.containers.container(container_id)

            # 获取容器详细信息
            inspect_data = await container.show()

            # 解析容器状态
            state = inspect_data["State"]
            if state["Running"]:
                status = ContainerStatus.RUNNING
            elif state["Paused"]:
                status = ContainerStatus.PAUSED
            elif state["Restarting"]:
                status = ContainerStatus.RESTARTING
            elif state["Dead"]:
                status = ContainerStatus.DEAD
            elif state["Status"] == "removing":
                status = ContainerStatus.REMOVING
            else:
                status = ContainerStatus.EXITED

            # 解析时间信息
            created_at = datetime.fromisoformat(inspect_data["Created"].replace("Z", "+00:00"))
            started_at = None
            finished_at = None

            if state.get("StartedAt"):
                started_at = datetime.fromisoformat(state["StartedAt"].replace("Z", "+00:00"))
            if state.get("FinishedAt") and state["FinishedAt"] != "0001-01-01T00:00:00Z":
                finished_at = datetime.fromisoformat(state["FinishedAt"].replace("Z", "+00:00"))

            # 获取网络信息
            networks = inspect_data.get("NetworkSettings", {}).get("Networks", {})
            ip_address = None
            if networks:
                # 获取第一个网络的IP地址
                network = next(iter(networks.values()))
                ip_address = network.get("IPAddress")

            # 构建容器信息对象
            container_info = ContainerInfo(
                id=container_id,
                name=inspect_data["Name"].lstrip("/"),
                image=inspect_data["Config"]["Image"],
                image_id=inspect_data["Image"],
                status=status,
                state=state.get("Status", "unknown"),
                created_at=created_at,
                started_at=started_at,
                finished_at=finished_at,
                exit_code=state.get("ExitCode"),
                pid=state.get("Pid"),
                ip_address=ip_address,
                ports=inspect_data.get("NetworkSettings", {}).get("Ports", {})
            )

            return container_info

        except AioDockerError as e:
            if e.status == 404:
                raise ContainerError(
                    f"Container not found: {container_id}",
                    container_id=container_id,
                    operation="inspect",
                    docker_error=e
                )
            else:
                raise ContainerError(
                    f"Failed to get container info: {str(e)}",
                    container_id=container_id,
                    operation="inspect",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error getting container info: {str(e)}",
                container_id=container_id,
                operation="inspect",
                cause=e
            )

    @log_performance("list_containers")
    async def list_containers(self, all: bool = True,
                              filters: Optional[Dict[str, Any]] = None) -> List[ContainerInfo]:
        """列出容器"""
        try:
            client = self._client.client

            # 获取容器列表
            containers = await client.containers.list(all=all, filters=filters)

            container_infos = []
            for container_data in containers:
                try:
                    # 获取每个容器的详细信息
                    container_id = container_data["Id"]
                    container_info = await self.get_container_info(container_id)
                    container_infos.append(container_info)
                except Exception as e:
                    self.logger.warning(
                        f"Failed to get info for container {container_data.get('Id', 'unknown')}: {str(e)}"
                    )
                    continue

            return container_infos

        except Exception as e:
            raise DockerError(f"Failed to list containers: {str(e)}", docker_error=e)

    @log_performance("get_container_stats")
    async def get_container_stats(self, container_id: str) -> ContainerStats:
        """获取容器统计信息"""
        try:
            client = self._client.client
            container = client.containers.container(container_id)

            # 获取统计信息（非流模式）
            stats = await container.stats(stream=False)

            # 解析CPU使用率
            cpu_usage = 0.0
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})

            if cpu_stats and precpu_stats:
                cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - \
                            precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
                system_delta = cpu_stats.get("system_cpu_usage", 0) - \
                               precpu_stats.get("system_cpu_usage", 0)

                if system_delta > 0:
                    online_cpus = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []))
                    if online_cpus == 0:
                        online_cpus = 1
                    cpu_usage = (cpu_delta / system_delta) * online_cpus * 100.0

            # 解析内存使用
            memory_stats = stats.get("memory_stats", {})
            memory_usage = memory_stats.get("usage", 0)
            memory_limit = memory_stats.get("limit", 0)
            memory_usage_percent = 0.0

            if memory_limit > 0:
                memory_usage_percent = (memory_usage / memory_limit) * 100.0

            # 解析网络统计
            networks = stats.get("networks", {})
            network_rx_bytes = 0
            network_tx_bytes = 0
            network_rx_packets = 0
            network_tx_packets = 0

            for network in networks.values():
                network_rx_bytes += network.get("rx_bytes", 0)
                network_tx_bytes += network.get("tx_bytes", 0)
                network_rx_packets += network.get("rx_packets", 0)
                network_tx_packets += network.get("tx_packets", 0)

            # 解析磁盘I/O统计
            blkio_stats = stats.get("blkio_stats", {})
            block_read_bytes = 0
            block_write_bytes = 0

            for blkio in blkio_stats.get("io_service_bytes_recursive", []):
                if blkio.get("op") == "Read":
                    block_read_bytes += blkio.get("value", 0)
                elif blkio.get("op") == "Write":
                    block_write_bytes += blkio.get("value", 0)

            # 解析PIDs统计
            pids_stats = stats.get("pids_stats", {})
            pids_current = pids_stats.get("current", 0)
            pids_limit = pids_stats.get("limit", 0)

            return ContainerStats(
                cpu_usage=cpu_usage,
                cpu_usage_total=cpu_stats.get("cpu_usage", {}).get("total_usage", 0),
                cpu_system_usage=cpu_stats.get("system_cpu_usage", 0),
                memory_usage=memory_usage,
                memory_limit=memory_limit,
                memory_usage_percent=memory_usage_percent,
                network_rx_bytes=network_rx_bytes,
                network_tx_bytes=network_tx_bytes,
                network_rx_packets=network_rx_packets,
                network_tx_packets=network_tx_packets,
                block_read_bytes=block_read_bytes,
                block_write_bytes=block_write_bytes,
                pids_current=pids_current,
                pids_limit=pids_limit,
                timestamp=datetime.now()
            )

        except AioDockerError as e:
            if e.status == 404:
                raise ContainerError(
                    f"Container not found: {container_id}",
                    container_id=container_id,
                    operation="stats",
                    docker_error=e
                )
            else:
                raise ContainerError(
                    f"Failed to get container stats: {str(e)}",
                    container_id=container_id,
                    operation="stats",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error getting container stats: {str(e)}",
                container_id=container_id,
                operation="stats",
                cause=e
            )

    @log_performance("get_container_logs")
    async def get_container_logs(self, container_id: str,
                                 tail: Optional[int] = None,
                                 since: Optional[str] = None,
                                 follow: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """获取容器日志"""
        try:
            client = self._client.client
            container = client.containers.container(container_id)

            log_config = {
                "stdout": True,
                "stderr": True,
                "timestamps": True
            }

            if tail is not None:
                log_config["tail"] = tail
            if since is not None:
                log_config["since"] = since
            if follow:
                log_config["follow"] = True

            if follow:
                # 返回异步生成器用于流式日志
                async def log_stream():
                    async for log_line in container.log(**log_config):
                        yield log_line.decode('utf-8')
                return log_stream()
            else:
                # 返回完整日志字符串
                logs = await container.log(**log_config)
                return logs.decode('utf-8')

        except AioDockerError as e:
            if e.status == 404:
                raise ContainerError(
                    f"Container not found: {container_id}",
                    container_id=container_id,
                    operation="logs",
                    docker_error=e
                )
            else:
                raise ContainerError(
                    f"Failed to get container logs: {str(e)}",
                    container_id=container_id,
                    operation="logs",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error getting container logs: {str(e)}",
                container_id=container_id,
                operation="logs",
                cause=e
            )

    # ================== 镜像管理 ==================

    @log_performance("pull_image")
    @retry_async(max_attempts=3, delay=2.0)
    async def pull_image(self, image_name: str, tag: str = "latest") -> bool:
        """拉取镜像"""
        try:
            client = self._client.client

            full_image_name = f"{image_name}:{tag}"

            self.logger.info(f"Pulling image: {full_image_name}")

            # 拉取镜像
            await client.images.pull(image_name, tag=tag)

            self.logger.info(f"Successfully pulled image: {full_image_name}")
            return True

        except AioDockerError as e:
            if e.status == 404:
                raise ImageError(
                    f"Image not found: {image_name}:{tag}",
                    image_name=f"{image_name}:{tag}",
                    docker_error=e
                )
            else:
                raise ImageError(
                    f"Failed to pull image: {str(e)}",
                    image_name=f"{image_name}:{tag}",
                    docker_error=e
                )
        except Exception as e:
            raise ImageError(
                f"Unexpected error pulling image: {str(e)}",
                image_name=f"{image_name}:{tag}",
                cause=e
            )

    async def list_images(self) -> List[Dict[str, Any]]:
        """列出镜像"""
        try:
            client = self._client.client
            images = await client.images.list()
            return images
        except Exception as e:
            raise DockerError(f"Failed to list images: {str(e)}", docker_error=e)

    async def remove_image(self, image_id: str, force: bool = False) -> bool:
        """删除镜像"""
        try:
            client = self._client.client
            await client.images.delete(image_id, force=force)
            self.logger.info(f"Image removed: {image_id}")
            return True
        except AioDockerError as e:
            if e.status == 404:
                self.logger.debug(f"Image not found (already removed): {image_id}")
                return True
            else:
                raise ImageError(f"Failed to remove image: {str(e)}", image_name=image_id, docker_error=e)
        except Exception as e:
            raise ImageError(f"Unexpected error removing image: {str(e)}", image_name=image_id, cause=e)

    # ================== 事件处理 ==================

    async def _start_event_monitoring(self):
        """启动事件监控"""
        self._monitoring_task = asyncio.create_task(self._monitor_events())

    async def _monitor_events(self):
        """监控Docker事件"""
        try:
            client = self._client.client

            # 过滤容器事件
            filters = {"type": "container"}

            async for event in client.events.run(filters=filters):
                try:
                    container_event = ContainerEvent.from_docker_event(event)
                    await self._handle_event(container_event)
                except Exception as e:
                    self.logger.warning(f"Error processing Docker event: {str(e)}")

        except asyncio.CancelledError:
            self.logger.info("Event monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in event monitoring: {str(e)}")

    async def _handle_event(self, event: ContainerEvent):
        """处理容器事件"""
        self.logger.debug(f"Received container event: {event.action} for {event.container_name}")

        # 调用已注册的事件监听器
        for event_type, listeners in self._event_listeners.items():
            if event_type == "all" or event_type == event.action:
                for listener in listeners:
                    try:
                        if asyncio.iscoroutinefunction(listener):
                            await listener(event)
                        else:
                            listener(event)
                    except Exception as e:
                        self.logger.error(f"Error in event listener: {str(e)}")

    def add_event_listener(self, event_type: str, listener):
        """添加事件监听器"""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(listener)
        self.logger.debug(f"Added event listener for {event_type}")

    def remove_event_listener(self, event_type: str, listener):
        """移除事件监听器"""
        if event_type in self._event_listeners:
            try:
                self._event_listeners[event_type].remove(listener)
                self.logger.debug(f"Removed event listener for {event_type}")
            except ValueError:
                pass

    # ================== 执行命令 ==================

    @log_performance("execute_command")
    async def execute_command(self, container_id: str, command: Union[str, List[str]],
                              workdir: Optional[str] = None,
                              user: Optional[str] = None,
                              environment: Optional[Dict[str, str]] = None,
                              stream: bool = False) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """在容器中执行命令"""
        try:
            client = self._client.client
            container = client.containers.container(container_id)

            exec_config = {
                "cmd": command if isinstance(command, list) else command.split(),
                "stdout": True,
                "stderr": True,
                "stdin": False
            }

            if workdir:
                exec_config["workdir"] = workdir
            if user:
                exec_config["user"] = user
            if environment:
                exec_config["environment"] = [f"{k}={v}" for k, v in environment.items()]

            # 创建exec实例
            exec_instance = await container.exec(**exec_config)

            if stream:
                # 返回流式输出
                async def output_stream():
                    async for chunk in exec_instance.start(stream=True):
                        yield chunk.decode('utf-8', errors='ignore')
                return output_stream()
            else:
                # 返回完整输出
                output = await exec_instance.start(stream=False)

                # 获取退出码
                inspect_result = await exec_instance.inspect()

                return {
                    "output": output.decode('utf-8', errors='ignore'),
                    "exit_code": inspect_result.get("ExitCode", 0),
                    "running": inspect_result.get("Running", False)
                }

        except AioDockerError as e:
            if e.status == 404:
                raise ContainerError(
                    f"Container not found: {container_id}",
                    container_id=container_id,
                    operation="exec",
                    docker_error=e
                )
            else:
                raise ContainerError(
                    f"Failed to execute command: {str(e)}",
                    container_id=container_id,
                    operation="exec",
                    docker_error=e
                )
        except Exception as e:
            raise ContainerError(
                f"Unexpected error executing command: {str(e)}",
                container_id=container_id,
                operation="exec",
                cause=e
            )

    # ================== 网络管理 ==================

    async def list_networks(self) -> List[Dict[str, Any]]:
        """列出网络"""
        try:
            client = self._client.client
            networks = await client.networks.list()
            return networks
        except Exception as e:
            raise DockerError(f"Failed to list networks: {str(e)}", docker_error=e)

    async def create_network(self, name: str, driver: str = "bridge",
                             options: Optional[Dict[str, Any]] = None) -> str:
        """创建网络"""
        try:
            client = self._client.client

            network_config = {
                "Name": name,
                "Driver": driver
            }

            if options:
                network_config.update(options)

            network = await client.networks.create(network_config)
            network_id = network.id

            self.logger.info(f"Network created: {name} ({network_id})")
            return network_id

        except AioDockerError as e:
            if e.status == 409:
                raise DockerError(f"Network already exists: {name}", docker_error=e)
            else:
                raise DockerError(f"Failed to create network: {str(e)}", docker_error=e)
        except Exception as e:
            raise DockerError(f"Unexpected error creating network: {str(e)}", cause=e)

    async def remove_network(self, network_id: str) -> bool:
        """删除网络"""
        try:
            client = self._client.client
            network = client.networks.network(network_id)
            await network.delete()

            self.logger.info(f"Network removed: {network_id}")
            return True

        except AioDockerError as e:
            if e.status == 404:
                self.logger.debug(f"Network not found (already removed): {network_id}")
                return True
            else:
                raise DockerError(f"Failed to remove network: {str(e)}", docker_error=e)
        except Exception as e:
            raise DockerError(f"Unexpected error removing network: {str(e)}", cause=e)

    # ================== 数据卷管理 ==================

    async def list_volumes(self) -> List[Dict[str, Any]]:
        """列出数据卷"""
        try:
            client = self._client.client
            volumes_info = await client.volumes.list()
            return volumes_info.get("Volumes", [])
        except Exception as e:
            raise DockerError(f"Failed to list volumes: {str(e)}", docker_error=e)

    async def create_volume(self, name: str, driver: str = "local",
                            driver_opts: Optional[Dict[str, str]] = None,
                            labels: Optional[Dict[str, str]] = None) -> str:
        """创建数据卷"""
        try:
            client = self._client.client

            volume_config = {"Name": name, "Driver": driver}

            if driver_opts:
                volume_config["DriverOpts"] = driver_opts
            if labels:
                volume_config["Labels"] = labels

            volume = await client.volumes.create(volume_config)
            volume_name = volume["Name"]

            self.logger.info(f"Volume created: {volume_name}")
            return volume_name

        except AioDockerError as e:
            if e.status == 409:
                raise DockerError(f"Volume already exists: {name}", docker_error=e)
            else:
                raise DockerError(f"Failed to create volume: {str(e)}", docker_error=e)
        except Exception as e:
            raise DockerError(f"Unexpected error creating volume: {str(e)}", cause=e)

    async def remove_volume(self, volume_name: str, force: bool = False) -> bool:
        """删除数据卷"""
        try:
            client = self._client.client
            await client.volumes.delete(volume_name, force=force)

            self.logger.info(f"Volume removed: {volume_name}")
            return True

        except AioDockerError as e:
            if e.status == 404:
                self.logger.debug(f"Volume not found (already removed): {volume_name}")
                return True
            elif e.status == 409:
                raise DockerError(f"Volume is in use: {volume_name}", docker_error=e)
            else:
                raise DockerError(f"Failed to remove volume: {str(e)}", docker_error=e)
        except Exception as e:
            raise DockerError(f"Unexpected error removing volume: {str(e)}", cause=e)

    # ================== 清理操作 ==================

    @log_performance("prune_containers")
    async def prune_containers(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """清理停止的容器"""
        try:
            client = self._client.client
            result = await client.containers.prune(filters=filters)

            deleted_containers = result.get("ContainersDeleted", [])
            space_reclaimed = result.get("SpaceReclaimed", 0)

            self.logger.info(f"Pruned {len(deleted_containers)} containers, reclaimed {space_reclaimed} bytes")

            return {
                "containers_deleted": deleted_containers,
                "space_reclaimed": space_reclaimed
            }

        except Exception as e:
            raise DockerError(f"Failed to prune containers: {str(e)}", docker_error=e)

    async def prune_images(self, dangling_only: bool = True) -> Dict[str, Any]:
        """清理未使用的镜像"""
        try:
            client = self._client.client

            filters = {}
            if dangling_only:
                filters["dangling"] = True

            result = await client.images.prune(filters=filters)

            deleted_images = result.get("ImagesDeleted", [])
            space_reclaimed = result.get("SpaceReclaimed", 0)

            self.logger.info(f"Pruned {len(deleted_images)} images, reclaimed {space_reclaimed} bytes")

            return {
                "images_deleted": deleted_images,
                "space_reclaimed": space_reclaimed
            }

        except Exception as e:
            raise DockerError(f"Failed to prune images: {str(e)}", docker_error=e)

    async def prune_volumes(self) -> Dict[str, Any]:
        """清理未使用的数据卷"""
        try:
            client = self._client.client
            result = await client.volumes.prune()

            deleted_volumes = result.get("VolumesDeleted", [])
            space_reclaimed = result.get("SpaceReclaimed", 0)

            self.logger.info(f"Pruned {len(deleted_volumes)} volumes, reclaimed {space_reclaimed} bytes")

            return {
                "volumes_deleted": deleted_volumes,
                "space_reclaimed": space_reclaimed
            }

        except Exception as e:
            raise DockerError(f"Failed to prune volumes: {str(e)}", docker_error=e)

    async def prune_networks(self) -> Dict[str, Any]:
        """清理未使用的网络"""
        try:
            client = self._client.client
            result = await client.networks.prune()

            deleted_networks = result.get("NetworksDeleted", [])

            self.logger.info(f"Pruned {len(deleted_networks)} networks")

            return {
                "networks_deleted": deleted_networks
            }

        except Exception as e:
            raise DockerError(f"Failed to prune networks: {str(e)}", docker_error=e)

    async def system_prune(self, volumes: bool = False) -> Dict[str, Any]:
        """系统清理"""
        try:
            client = self._client.client
            result = await client.system.prune(volumes=volumes)

            self.logger.info(f"System prune completed, reclaimed {result.get('SpaceReclaimed', 0)} bytes")
            return result

        except Exception as e:
            raise DockerError(f"Failed to perform system prune: {str(e)}", docker_error=e)


# 便捷函数
async def create_docker_manager() -> DockerManager:
    """创建并初始化Docker管理器"""
    manager = DockerManager()
    await manager.initialize()
    return manager