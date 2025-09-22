# 22. src/services/terminal_service.py
"""
终端服务 - eulermaker-docker-optimizer的Web终端业务服务

******OSPP-2025-张金荣******

提供Web终端的高级业务逻辑封装，包括：
- 终端会话管理和生命周期
- WebSocket连接处理和消息转发
- 容器终端连接和执行
- 终端权限控制和认证
- 会话历史记录和回放
- 终端窗口大小调整
- 多用户终端会话管理
- 终端命令记录和审计
"""

import asyncio
import json
import time
import weakref
from typing import Dict, List, Optional, Any, Callable, Set, Union, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict, deque
import struct
import base64
import uuid
import pty
import os
import signal
import subprocess

from config.settings import get_docker_settings
from utils.logger import get_logger, LoggerMixin, log_performance, log_errors
from utils.exceptions import TerminalError, ContainerError, ValidationError
from utils.helpers import (
    generate_uuid, format_timestamp, sanitize_name,
    format_duration, ensure_directory
)
from models.container_model import ContainerInfo, ContainerStatus
from core.docker_manager import DockerManager
from core.container_lifecycle import ContainerLifecycleManager


class TerminalType(Enum):
    """终端类型"""
    CONTAINER = "container"     # 容器终端
    HOST = "host"              # 主机终端
    EXEC = "exec"              # 执行命令


class SessionStatus(Enum):
    """会话状态"""
    CONNECTING = "connecting"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISCONNECTED = "disconnected"
    TERMINATED = "terminated"
    ERROR = "error"


class TerminalCommand(Enum):
    """终端命令"""
    INPUT = "input"           # 用户输入
    OUTPUT = "output"         # 终端输出
    RESIZE = "resize"         # 调整大小
    PING = "ping"            # 心跳检测
    PONG = "pong"            # 心跳响应
    CLOSE = "close"          # 关闭会话
    ERROR = "error"          # 错误信息


@dataclass
class TerminalMessage:
    """终端消息"""
    command: TerminalCommand
    data: Any = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "command": self.command.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat()
        }

    def to_json(self) -> str:
        """转换为JSON格式"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> 'TerminalMessage':
        """从JSON创建实例"""
        data = json.loads(json_str)
        return cls(
            command=TerminalCommand(data['command']),
            data=data.get('data'),
            timestamp=datetime.fromisoformat(data['timestamp']) if 'timestamp' in data else datetime.now()
        )


@dataclass
class TerminalSize:
    """终端尺寸"""
    rows: int = 24
    cols: int = 80

    def to_dict(self) -> Dict[str, int]:
        """转换为字典格式"""
        return {"rows": self.rows, "cols": self.cols}


@dataclass
class TerminalConfig:
    """终端配置"""
    terminal_type: TerminalType
    container_id: Optional[str] = None
    command: Optional[str] = None
    working_dir: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    user: Optional[str] = None
    size: TerminalSize = field(default_factory=TerminalSize)
    timeout: int = 3600  # 1小时超时
    record_session: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "terminal_type": self.terminal_type.value,
            "container_id": self.container_id,
            "command": self.command,
            "working_dir": self.working_dir,
            "environment": self.environment,
            "user": self.user,
            "size": self.size.to_dict(),
            "timeout": self.timeout,
            "record_session": self.record_session
        }


@dataclass
class SessionRecord:
    """会话记录"""
    session_id: str
    user_id: str
    terminal_type: TerminalType
    container_id: Optional[str]
    command: Optional[str]
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    commands_executed: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    status: SessionStatus = SessionStatus.ACTIVE

    def finish(self):
        """结束会话"""
        self.end_time = datetime.now()
        if self.start_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
        self.status = SessionStatus.TERMINATED

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "terminal_type": self.terminal_type.value,
            "container_id": self.container_id,
            "command": self.command,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "commands_executed": self.commands_executed,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "status": self.status.value
        }


class TerminalSession:
    """终端会话 - 管理单个终端会话的状态和操作"""

    def __init__(self, session_id: str, config: TerminalConfig, user_id: str = "anonymous"):
        self.session_id = session_id
        self.config = config
        self.user_id = user_id
        self.logger = get_logger(__name__)

        # 会话状态
        self.status = SessionStatus.CONNECTING
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

        # WebSocket连接
        self.websockets: Set[Any] = set()  # WebSocket连接集合

        # 终端进程相关
        self.process: Optional[subprocess.Popen] = None
        self.exec_id: Optional[str] = None  # Docker exec ID

        # 消息队列和缓冲区
        self.output_buffer: deque[bytes] = deque(maxlen=1000)
        self.input_queue: asyncio.Queue = asyncio.Queue()

        # 任务管理
        self._tasks: Set[asyncio.Task] = set()
        self._cleanup_done = False

        # 会话记录
        self.record = SessionRecord(
            session_id=session_id,
            user_id=user_id,
            terminal_type=config.terminal_type,
            container_id=config.container_id,
            command=config.command,
            start_time=self.created_at
        )

        # 心跳检测
        self._last_ping = datetime.now()
        self._ping_task: Optional[asyncio.Task] = None

    async def start(self, docker_manager: DockerManager, container_manager: ContainerLifecycleManager):
        """启动终端会话"""
        try:
            self.logger.info(f"Starting terminal session: {self.session_id}")

            if self.config.terminal_type == TerminalType.CONTAINER:
                await self._start_container_terminal(docker_manager)
            elif self.config.terminal_type == TerminalType.HOST:
                await self._start_host_terminal()
            elif self.config.terminal_type == TerminalType.EXEC:
                await self._start_exec_terminal(docker_manager)

            self.status = SessionStatus.ACTIVE

            # 启动心跳检测
            self._ping_task = asyncio.create_task(self._ping_loop())
            self._tasks.add(self._ping_task)

            self.logger.info(f"Terminal session started: {self.session_id}")

        except Exception as e:
            self.logger.error(f"Failed to start terminal session {self.session_id}: {str(e)}")
            self.status = SessionStatus.ERROR
            raise TerminalError(f"Failed to start terminal session: {str(e)}", session_id=self.session_id, cause=e)

    async def _start_container_terminal(self, docker_manager: DockerManager):
        """启动容器终端"""
        if not self.config.container_id:
            raise TerminalError("Container ID is required for container terminal", session_id=self.session_id)

        # 检查容器状态
        container_info = await docker_manager.get_container_info(self.config.container_id)
        if not container_info or not container_info.is_running():
            raise TerminalError("Container is not running", session_id=self.session_id, container_id=self.config.container_id)

        # 创建exec实例
        exec_command = self.config.command or "/bin/bash"

        exec_config = {
            "Cmd": [exec_command],
            "AttachStdin": True,
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": True,
            "Env": [f"{k}={v}" for k, v in self.config.environment.items()],
            "WorkingDir": self.config.working_dir or "/",
            "User": self.config.user or ""
        }

        self.exec_id = await docker_manager.create_exec(self.config.container_id, exec_config)

        # 启动exec并获取输出流
        exec_socket = await docker_manager.start_exec(self.exec_id, tty=True)

        # 启动输入输出处理任务
        input_task = asyncio.create_task(self._handle_input(exec_socket))
        output_task = asyncio.create_task(self._handle_output(exec_socket))

        self._tasks.add(input_task)
        self._tasks.add(output_task)

    async def _start_host_terminal(self):
        """启动主机终端"""
        # 创建伪终端
        master_fd, slave_fd = pty.openpty()

        # 设置终端大小
        self._resize_terminal(master_fd, self.config.size)

        # 启动shell进程
        shell_command = self.config.command or os.environ.get('SHELL', '/bin/bash')

        env = os.environ.copy()
        env.update(self.config.environment)

        self.process = subprocess.Popen(
            shell_command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            cwd=self.config.working_dir or os.getcwd(),
            preexec_fn=os.setsid
        )

        os.close(slave_fd)  # 关闭从设备文件描述符

        # 启动输入输出处理任务
        input_task = asyncio.create_task(self._handle_host_input(master_fd))
        output_task = asyncio.create_task(self._handle_host_output(master_fd))

        self._tasks.add(input_task)
        self._tasks.add(output_task)

    async def _start_exec_terminal(self, docker_manager: DockerManager):
        """启动执行终端（单次命令执行）"""
        if not self.config.container_id or not self.config.command:
            raise TerminalError("Container ID and command are required for exec terminal", session_id=self.session_id)

        # 检查容器状态
        container_info = await docker_manager.get_container_info(self.config.container_id)
        if not container_info or not container_info.is_running():
            raise TerminalError("Container is not running", session_id=self.session_id, container_id=self.config.container_id)

        # 创建并执行命令
        exec_config = {
            "Cmd": self.config.command.split(),
            "AttachStdin": False,
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": False,
            "Env": [f"{k}={v}" for k, v in self.config.environment.items()],
            "WorkingDir": self.config.working_dir or "/",
            "User": self.config.user or ""
        }

        self.exec_id = await docker_manager.create_exec(self.config.container_id, exec_config)

        # 启动exec并获取输出
        result = await docker_manager.start_exec(self.exec_id, tty=False)

        # 发送输出到WebSocket
        await self._broadcast_message(TerminalMessage(
            command=TerminalCommand.OUTPUT,
            data=result
        ))

        # exec类型的会话执行完毕后自动结束
        await self.close()

    async def _handle_input(self, exec_socket):
        """处理输入（容器终端）"""
        try:
            while self.status == SessionStatus.ACTIVE:
                try:
                    input_data = await asyncio.wait_for(self.input_queue.get(), timeout=1.0)
                    if input_data:
                        exec_socket.send(input_data)
                        self.record.bytes_sent += len(input_data)
                        self.record.commands_executed += 1
                        self.last_activity = datetime.now()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.logger.error(f"Error in input handler: {str(e)}")
                    break
        except Exception as e:
            self.logger.error(f"Input handler error: {str(e)}")
        finally:
            if exec_socket:
                exec_socket.close()

    async def _handle_output(self, exec_socket):
        """处理输出（容器终端）"""
        try:
            while self.status == SessionStatus.ACTIVE:
                try:
                    output_data = exec_socket.recv(4096)
                    if not output_data:
                        break

                    self.output_buffer.append(output_data)
                    self.record.bytes_received += len(output_data)
                    self.last_activity = datetime.now()

                    # 广播输出到所有WebSocket连接
                    await self._broadcast_message(TerminalMessage(
                        command=TerminalCommand.OUTPUT,
                        data=base64.b64encode(output_data).decode('utf-8')
                    ))

                except Exception as e:
                    self.logger.error(f"Error in output handler: {str(e)}")
                    break
        except Exception as e:
            self.logger.error(f"Output handler error: {str(e)}")
        finally:
            if exec_socket:
                exec_socket.close()

    async def _handle_host_input(self, master_fd):
        """处理输入（主机终端）"""
        try:
            while self.status == SessionStatus.ACTIVE and self.process and self.process.poll() is None:
                try:
                    input_data = await asyncio.wait_for(self.input_queue.get(), timeout=1.0)
                    if input_data:
                        os.write(master_fd, input_data)
                        self.record.bytes_sent += len(input_data)
                        self.record.commands_executed += 1
                        self.last_activity = datetime.now()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.logger.error(f"Error in host input handler: {str(e)}")
                    break
        except Exception as e:
            self.logger.error(f"Host input handler error: {str(e)}")
        finally:
            try:
                os.close(master_fd)
            except:
                pass

    async def _handle_host_output(self, master_fd):
        """处理输出（主机终端）"""
        try:
            while self.status == SessionStatus.ACTIVE and self.process and self.process.poll() is None:
                try:
                    # 使用非阻塞读取
                    output_data = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: os.read(master_fd, 4096)
                    )

                    if not output_data:
                        break

                    self.output_buffer.append(output_data)
                    self.record.bytes_received += len(output_data)
                    self.last_activity = datetime.now()

                    # 广播输出到所有WebSocket连接
                    await self._broadcast_message(TerminalMessage(
                        command=TerminalCommand.OUTPUT,
                        data=base64.b64encode(output_data).decode('utf-8')
                    ))

                except Exception as e:
                    self.logger.error(f"Error in host output handler: {str(e)}")
                    break
        except Exception as e:
            self.logger.error(f"Host output handler error: {str(e)}")
        finally:
            try:
                os.close(master_fd)
            except:
                pass

    def add_websocket(self, websocket):
        """添加WebSocket连接"""
        self.websockets.add(websocket)
        self.logger.debug(f"WebSocket connected to session {self.session_id}")

    def remove_websocket(self, websocket):
        """移除WebSocket连接"""
        self.websockets.discard(websocket)
        self.logger.debug(f"WebSocket disconnected from session {self.session_id}")

        # 如果没有WebSocket连接且会话类型不是exec，标记为非活跃
        if not self.websockets and self.config.terminal_type != TerminalType.EXEC:
            self.status = SessionStatus.INACTIVE

    async def send_input(self, data: Union[str, bytes]):
        """发送输入数据"""
        if isinstance(data, str):
            data = data.encode('utf-8')

        await self.input_queue.put(data)
        self.last_activity = datetime.now()

    async def resize_terminal(self, size: TerminalSize):
        """调整终端大小"""
        self.config.size = size

        if self.config.terminal_type == TerminalType.HOST and self.process:
            # 主机终端调整大小
            try:
                os.system(f"stty -F /proc/{self.process.pid}/fd/0 rows {size.rows} cols {size.cols}")
            except Exception as e:
                self.logger.warning(f"Failed to resize host terminal: {str(e)}")

        # 通知客户端终端大小已调整
        await self._broadcast_message(TerminalMessage(
            command=TerminalCommand.RESIZE,
            data=size.to_dict()
        ))

    def _resize_terminal(self, fd, size: TerminalSize):
        """设置终端大小（内部方法）"""
        try:
            import fcntl
            import termios
            # 设置终端窗口大小
            s = struct.pack("HHHH", size.rows, size.cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, s)
        except Exception as e:
            self.logger.warning(f"Failed to set terminal size: {str(e)}")

    async def _broadcast_message(self, message: TerminalMessage):
        """广播消息到所有WebSocket连接"""
        if not self.websockets:
            return

        message_json = message.to_json()
        disconnected_websockets = set()

        for websocket in self.websockets:
            try:
                await websocket.send(message_json)
            except Exception as e:
                self.logger.warning(f"Failed to send message to WebSocket: {str(e)}")
                disconnected_websockets.add(websocket)

        # 清理断开的连接
        for websocket in disconnected_websockets:
            self.websockets.discard(websocket)

    async def _ping_loop(self):
        """心跳检测循环"""
        while self.status == SessionStatus.ACTIVE:
            try:
                # 检查最后活动时间
                if (datetime.now() - self.last_activity).total_seconds() > self.config.timeout:
                    self.logger.info(f"Session {self.session_id} timed out")
                    await self.close()
                    break

                # 发送ping
                await self._broadcast_message(TerminalMessage(command=TerminalCommand.PING))
                self._last_ping = datetime.now()

                await asyncio.sleep(30)  # 每30秒ping一次

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in ping loop: {str(e)}")
                await asyncio.sleep(10)

    async def handle_pong(self):
        """处理pong响应"""
        self.last_activity = datetime.now()

    async def close(self):
        """关闭终端会话"""
        if self._cleanup_done:
            return

        self._cleanup_done = True
        self.status = SessionStatus.TERMINATED

        self.logger.info(f"Closing terminal session: {self.session_id}")

        # 通知所有WebSocket连接
        await self._broadcast_message(TerminalMessage(command=TerminalCommand.CLOSE))

        # 关闭所有WebSocket连接
        for websocket in self.websockets.copy():
            try:
                await websocket.close()
            except Exception:
                pass
        self.websockets.clear()

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # 终止进程
        if self.process:
            try:
                self.process.terminate()
                await asyncio.sleep(1)
                if self.process.poll() is None:
                    self.process.kill()
            except Exception as e:
                self.logger.warning(f"Error terminating process: {str(e)}")

        # 完成会话记录
        self.record.finish()

        self.logger.info(f"Terminal session closed: {self.session_id}")

    def get_session_info(self) -> Dict[str, Any]:
        """获取会话信息"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "config": self.config.to_dict(),
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "websocket_count": len(self.websockets),
            "record": self.record.to_dict()
        }


class TerminalWebSocketHandler:
    """终端WebSocket处理器 - 处理WebSocket消息和连接"""

    def __init__(self, session: TerminalSession):
        self.session = session
        self.logger = get_logger(__name__)

    async def handle_connection(self, websocket):
        """处理WebSocket连接"""
        try:
            # 添加到会话
            self.session.add_websocket(websocket)

            # 发送会话信息
            await websocket.send(json.dumps({
                "command": "session_info",
                "data": self.session.get_session_info()
            }))

            # 处理消息
            async for message in websocket:
                await self.handle_message(websocket, message)

        except Exception as e:
            self.logger.error(f"WebSocket handler error: {str(e)}")
        finally:
            self.session.remove_websocket(websocket)

    async def handle_message(self, websocket, message: str):
        """处理WebSocket消息"""
        try:
            terminal_message = TerminalMessage.from_json(message)

            if terminal_message.command == TerminalCommand.INPUT:
                # 处理用户输入
                input_data = terminal_message.data
                if isinstance(input_data, str):
                    # 如果是base64编码的数据，先解码
                    try:
                        decoded_data = base64.b64decode(input_data)
                        await self.session.send_input(decoded_data)
                    except Exception:
                        # 如果不是base64，直接作为文本处理
                        await self.session.send_input(input_data)
                else:
                    await self.session.send_input(input_data)

            elif terminal_message.command == TerminalCommand.RESIZE:
                # 处理终端大小调整
                if isinstance(terminal_message.data, dict):
                    size = TerminalSize(
                        rows=terminal_message.data.get('rows', 24),
                        cols=terminal_message.data.get('cols', 80)
                    )
                    await self.session.resize_terminal(size)

            elif terminal_message.command == TerminalCommand.PONG:
                # 处理pong响应
                await self.session.handle_pong()

            elif terminal_message.command == TerminalCommand.CLOSE:
                # 处理关闭请求
                await self.session.close()
                await websocket.close()

        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {str(e)}")
            await websocket.send(json.dumps({
                "command": "error",
                "data": f"Error processing message: {str(e)}"
            }))


class TerminalService(LoggerMixin):
    """终端服务 - 提供高级Web终端管理功能"""

    def __init__(self, docker_manager: DockerManager, container_manager: ContainerLifecycleManager):
        super().__init__()
        self.docker_manager = docker_manager
        self.container_manager = container_manager
        self.settings = get_docker_settings()

        # 活跃会话
        self._sessions: Dict[str, TerminalSession] = {}

        # 会话历史记录
        self._session_history: deque[SessionRecord] = deque(maxlen=1000)

        # 用户会话映射
        self._user_sessions: Dict[str, Set[str]] = defaultdict(set)

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None

        # 统计信息
        self._stats = {
            "total_sessions": 0,
            "active_sessions": 0,
            "sessions_by_type": defaultdict(int),
            "total_bytes_transferred": 0,
            "last_reset": datetime.now()
        }

        self._initialized = False

    async def initialize(self):
        """初始化终端服务"""
        try:
            # 启动清理任务
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            self._initialized = True
            self.logger.info("Terminal service initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize terminal service: {str(e)}")
            raise TerminalError(f"Terminal service initialization failed: {str(e)}", cause=e)

    async def cleanup(self):
        """清理终端服务"""
        self._initialized = False

        # 停止清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # 关闭所有活跃会话
        sessions = list(self._sessions.values())
        if sessions:
            self.logger.info(f"Closing {len(sessions)} active terminal sessions")
            await asyncio.gather(
                *[session.close() for session in sessions],
                return_exceptions=True
            )

        self._sessions.clear()
        self._user_sessions.clear()

        self.logger.info("Terminal service cleaned up")

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    async def is_healthy(self) -> bool:
        """检查服务健康状态"""
        if not self._initialized:
            return False

        try:
            return await self.docker_manager.is_healthy()
        except Exception:
            return False

    # ================== 会话管理 ==================

    @log_performance("create_session")
    async def create_session(self, config: TerminalConfig, user_id: str = "anonymous") -> str:
        """创建终端会话"""
        try:
            session_id = generate_uuid()

            # 创建会话
            session = TerminalSession(session_id, config, user_id)

            # 启动会话
            await session.start(self.docker_manager, self.container_manager)

            # 添加到活跃会话
            self._sessions[session_id] = session
            self._user_sessions[user_id].add(session_id)

            # 更新统计
            self._stats["total_sessions"] += 1
            self._stats["active_sessions"] += 1
            self._stats["sessions_by_type"][config.terminal_type.value] += 1

            self.logger.info(f"Terminal session created: {session_id} for user {user_id}")
            return session_id

        except Exception as e:
            raise TerminalError(
                f"Failed to create terminal session: {str(e)}",
                config=config.to_dict(),
                user_id=user_id,
                cause=e
            )

    async def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """获取终端会话"""
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        """关闭终端会话"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        try:
            await session.close()

            # 从活跃会话中移除
            self._sessions.pop(session_id, None)

            # 从用户会话中移除
            for user_id, session_ids in self._user_sessions.items():
                session_ids.discard(session_id)

            # 添加到历史记录
            self._session_history.append(session.record)

            # 更新统计
            self._stats["active_sessions"] -= 1
            self._stats["total_bytes_transferred"] += session.record.bytes_sent + session.record.bytes_received

            self.logger.info(f"Terminal session closed: {session_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error closing terminal session {session_id}: {str(e)}")
            return False

    async def list_sessions(self, user_id: Optional[str] = None,
                            status_filter: Optional[SessionStatus] = None) -> List[Dict[str, Any]]:
        """列出终端会话"""
        sessions = []

        for session in self._sessions.values():
            # 用户过滤
            if user_id and session.user_id != user_id:
                continue

            # 状态过滤
            if status_filter and session.status != status_filter:
                continue

            sessions.append(session.get_session_info())

        return sessions

    async def get_user_sessions(self, user_id: str) -> List[str]:
        """获取用户的所有会话"""
        return list(self._user_sessions.get(user_id, set()))

    async def close_user_sessions(self, user_id: str) -> int:
        """关闭用户的所有会话"""
        session_ids = self._user_sessions.get(user_id, set()).copy()
        closed_count = 0

        for session_id in session_ids:
            if await self.close_session(session_id):
                closed_count += 1

        return closed_count

    # ================== WebSocket处理 ==================

    async def handle_websocket(self, websocket, session_id: str):
        """处理WebSocket连接"""
        session = await self.get_session(session_id)
        if not session:
            await websocket.close(code=4004, reason="Session not found")
            return

        if session.status != SessionStatus.ACTIVE:
            await websocket.close(code=4005, reason="Session not active")
            return

        # 创建WebSocket处理器
        handler = TerminalWebSocketHandler(session)
        await handler.handle_connection(websocket)

    # ================== 容器终端快捷方法 ==================

    async def create_container_terminal(self, container_id: str, user_id: str = "anonymous",
                                        command: str = None, working_dir: str = None) -> str:
        """创建容器终端（快捷方法）"""
        config = TerminalConfig(
            terminal_type=TerminalType.CONTAINER,
            container_id=container_id,
            command=command or "/bin/bash",
            working_dir=working_dir,
            environment={"TERM": "xterm-256color", "LC_ALL": "C.UTF-8"}
        )

        return await self.create_session(config, user_id)

    async def create_host_terminal(self, user_id: str = "anonymous",
                                   command: str = None, working_dir: str = None) -> str:
        """创建主机终端（快捷方法）"""
        config = TerminalConfig(
            terminal_type=TerminalType.HOST,
            command=command or "/bin/bash",
            working_dir=working_dir,
            environment={"TERM": "xterm-256color"}
        )

        return await self.create_session(config, user_id)

    async def execute_command(self, container_id: str, command: str,
                              user_id: str = "anonymous", working_dir: str = None) -> str:
        """执行单次命令（快捷方法）"""
        config = TerminalConfig(
            terminal_type=TerminalType.EXEC,
            container_id=container_id,
            command=command,
            working_dir=working_dir,
            record_session=False  # 单次命令不需要长期记录
        )

        return await self.create_session(config, user_id)

    # ================== 会话历史和审计 ==================

    async def get_session_history(self, limit: int = 100,
                                  user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取会话历史"""
        history = list(self._session_history)

        if user_id:
            history = [record for record in history if record.user_id == user_id]

        # 按开始时间倒序排序
        history.sort(key=lambda r: r.start_time, reverse=True)

        return [record.to_dict() for record in history[:limit]]

    async def get_session_statistics(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        active_sessions = len(self._sessions)

        # 按类型统计活跃会话
        active_by_type = defaultdict(int)
        for session in self._sessions.values():
            active_by_type[session.config.terminal_type.value] += 1

        # 按用户统计
        users_with_sessions = len([user_sessions for user_sessions in self._user_sessions.values() if user_sessions])

        return {
            "active_sessions": active_sessions,
            "active_by_type": dict(active_by_type),
            "users_with_sessions": users_with_sessions,
            "total_users": len(self._user_sessions),
            "session_history_size": len(self._session_history),
            **self._stats
        }

    # ================== 清理和维护 ==================

    async def _cleanup_loop(self):
        """清理循环 - 定期清理非活跃和过期的会话"""
        while True:
            try:
                current_time = datetime.now()
                sessions_to_close = []

                for session_id, session in self._sessions.items():
                    # 检查会话超时
                    inactive_time = (current_time - session.last_activity).total_seconds()
                    if inactive_time > session.config.timeout:
                        sessions_to_close.append(session_id)
                        continue

                    # 检查无WebSocket连接的非活跃会话
                    if (session.status == SessionStatus.INACTIVE and
                            not session.websockets and
                            inactive_time > 300):  # 5分钟无连接则关闭
                        sessions_to_close.append(session_id)
                        continue

                    # 检查错误状态的会话
                    if session.status == SessionStatus.ERROR:
                        sessions_to_close.append(session_id)

                # 关闭需要清理的会话
                for session_id in sessions_to_close:
                    await self.close_session(session_id)

                if sessions_to_close:
                    self.logger.info(f"Cleaned up {len(sessions_to_close)} terminal sessions")

                await asyncio.sleep(60)  # 每分钟检查一次

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {str(e)}")
                await asyncio.sleep(30)

    # ================== 统计和报告 ==================

    async def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        return await self.get_session_statistics()

    async def get_service_summary(self) -> Dict[str, Any]:
        """获取服务摘要"""
        stats = await self.get_session_statistics()

        return {
            "service_healthy": await self.is_healthy(),
            "active_sessions": stats["active_sessions"],
            "total_sessions_created": stats["total_sessions"],
            "users_with_active_sessions": stats["users_with_sessions"],
            "most_used_terminal_type": max(stats["sessions_by_type"].items(), key=lambda x: x[1])[0] if stats["sessions_by_type"] else "none",
            "total_data_transferred": format_size(stats["total_bytes_transferred"])
        }

    async def export_session_data(self, start_date: Optional[datetime] = None,
                                  end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """导出会话数据"""
        export_data = {
            "export_time": datetime.now().isoformat(),
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            },
            "sessions": [],
            "statistics": await self.get_session_statistics()
        }

        # 导出会话历史
        for record in self._session_history:
            # 过滤日期范围
            if start_date and record.start_time < start_date:
                continue
            if end_date and record.start_time > end_date:
                continue

            export_data["sessions"].append(record.to_dict())

        return export_data