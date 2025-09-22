# 29. src/api/websocket_server.py
"""
WebSocket服务器 - eulermaker-docker-optimizer的WebSocket服务

******OSPP-2025-张金荣******

提供实时双向通信支持，主要用于：
- 终端会话的实时交互（xterm.js集成）
- 容器状态实时监控和推送
- 构建进度实时更新
- 系统监控数据实时推送
- 多客户端广播消息

主要特性：
- 基于FastAPI WebSocket实现
- 支持多种消息类型和协议
- 连接管理和心跳检测
- 消息路由和广播
- 错误处理和重连机制
- 认证和权限控制
- 连接状态监控

WebSocket端点：
- /ws/terminals/{session_id} - 终端会话连接
- /ws/containers/{container_id} - 容器监控连接
- /ws/builds/{build_id} - 构建监控连接
- /ws/system - 系统监控连接
- /ws/notifications - 通知推送连接
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Union
from enum import Enum
import weakref

from fastapi import WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from pydantic import BaseModel, Field, ValidationError

from utils.logger import get_logger
from utils.exceptions import APIError
from config.settings import get_settings
from api import create_error_response, create_success_response

logger = get_logger(__name__)
settings = get_settings()

class MessageType(str, Enum):
    """WebSocket消息类型"""
    # 通用消息
    PING = "ping"
    PONG = "pong"
    AUTH = "auth"
    ERROR = "error"
    SUCCESS = "success"

    # 终端相关
    TERMINAL_INPUT = "terminal_input"
    TERMINAL_OUTPUT = "terminal_output"
    TERMINAL_RESIZE = "terminal_resize"
    TERMINAL_STATUS = "terminal_status"

    # 容器相关
    CONTAINER_STATUS = "container_status"
    CONTAINER_STATS = "container_stats"
    CONTAINER_LOGS = "container_logs"
    CONTAINER_EVENT = "container_event"

    # 构建相关
    BUILD_STATUS = "build_status"
    BUILD_PROGRESS = "build_progress"
    BUILD_LOGS = "build_logs"
    BUILD_EVENT = "build_event"

    # 系统监控
    SYSTEM_STATS = "system_stats"
    SYSTEM_ALERT = "system_alert"

    # 通知
    NOTIFICATION = "notification"
    BROADCAST = "broadcast"

class ConnectionStatus(str, Enum):
    """连接状态"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"

class WebSocketMessage(BaseModel):
    """WebSocket消息模型"""
    type: MessageType = Field(..., description="消息类型")
    data: Optional[Dict[str, Any]] = Field(None, description="消息数据")
    timestamp: Optional[str] = Field(None, description="时间戳")
    message_id: Optional[str] = Field(None, description="消息ID")
    target: Optional[str] = Field(None, description="目标标识")

class WebSocketConnection:
    """WebSocket连接封装类"""

    def __init__(self, websocket: WebSocket, connection_id: str = None):
        self.websocket = websocket
        self.connection_id = connection_id or str(uuid.uuid4())
        self.created_at = datetime.now()
        self.last_ping = None
        self.status = ConnectionStatus.CONNECTING
        self.user_id = None
        self.permissions = []
        self.subscriptions = set()  # 订阅的主题
        self.metadata = {}  # 连接元数据

    async def accept(self):
        """接受WebSocket连接"""
        try:
            await self.websocket.accept()
            self.status = ConnectionStatus.CONNECTED
            self.last_ping = datetime.now()
            logger.info(f"WebSocket connection accepted: {self.connection_id}")

            # 发送欢迎消息
            await self.send_message(MessageType.SUCCESS, {
                "message": "连接成功",
                "connection_id": self.connection_id,
                "server_time": datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {e}")
            raise

    async def send_message(self, msg_type: MessageType, data: Any = None,
                           message_id: str = None, target: str = None):
        """发送消息到客户端"""
        try:
            message = WebSocketMessage(
                type=msg_type,
                data=data,
                timestamp=datetime.now().isoformat(),
                message_id=message_id or str(uuid.uuid4()),
                target=target
            )

            await self.websocket.send_text(message.json())
            logger.debug(f"Sent message to {self.connection_id}: {msg_type}")

        except Exception as e:
            logger.error(f"Failed to send message to {self.connection_id}: {e}")
            await self.close(1011, "Failed to send message")

    async def send_error(self, error_code: str, message: str, details: Dict[str, Any] = None):
        """发送错误消息"""
        await self.send_message(MessageType.ERROR, {
            "error_code": error_code,
            "message": message,
            "details": details or {}
        })

    async def receive_message(self) -> Optional[WebSocketMessage]:
        """接收客户端消息"""
        try:
            raw_message = await self.websocket.receive_text()
            message_data = json.loads(raw_message)

            # 验证消息格式
            message = WebSocketMessage(**message_data)
            logger.debug(f"Received message from {self.connection_id}: {message.type}")

            return message

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON from {self.connection_id}: {e}")
            await self.send_error("invalid_json", "消息格式错误")
            return None

        except ValidationError as e:
            logger.warning(f"Invalid message format from {self.connection_id}: {e}")
            await self.send_error("invalid_message", "消息结构错误", {"errors": e.errors()})
            return None

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {self.connection_id}")
            raise

        except Exception as e:
            logger.error(f"Error receiving message from {self.connection_id}: {e}")
            await self.send_error("receive_error", "接收消息错误")
            return None

    async def authenticate(self, token: str) -> bool:
        """认证连接"""
        try:
            # 这里应该实现实际的token验证逻辑
            # 简化实现，生产环境应该使用JWT或其他安全方式

            if not token:
                await self.send_error("auth_required", "需要提供认证令牌")
                return False

            # 模拟认证逻辑
            if token == "admin-token":  # 简化的认证
                self.user_id = "admin"
                self.permissions = ["*"]  # 所有权限
                self.status = ConnectionStatus.AUTHENTICATED

                await self.send_message(MessageType.SUCCESS, {
                    "message": "认证成功",
                    "user_id": self.user_id,
                    "permissions": self.permissions
                })

                logger.info(f"Connection {self.connection_id} authenticated as {self.user_id}")
                return True
            else:
                await self.send_error("auth_failed", "认证失败，无效的令牌")
                return False

        except Exception as e:
            logger.error(f"Authentication error for {self.connection_id}: {e}")
            await self.send_error("auth_error", "认证过程出错")
            return False

    def has_permission(self, permission: str) -> bool:
        """检查权限"""
        if not self.permissions:
            return False

        if "*" in self.permissions:  # 管理员权限
            return True

        return permission in self.permissions

    async def subscribe(self, topic: str):
        """订阅主题"""
        self.subscriptions.add(topic)
        logger.debug(f"Connection {self.connection_id} subscribed to {topic}")

    async def unsubscribe(self, topic: str):
        """取消订阅"""
        self.subscriptions.discard(topic)
        logger.debug(f"Connection {self.connection_id} unsubscribed from {topic}")

    async def ping(self):
        """发送ping消息"""
        await self.send_message(MessageType.PING)
        self.last_ping = datetime.now()

    async def pong(self):
        """发送pong回应"""
        await self.send_message(MessageType.PONG)

    def is_alive(self, timeout_seconds: int = 60) -> bool:
        """检查连接是否存活"""
        if not self.last_ping:
            return True  # 刚连接，还没有ping

        return (datetime.now() - self.last_ping).total_seconds() < timeout_seconds

    async def close(self, code: int = 1000, reason: str = "Normal closure"):
        """关闭连接"""
        try:
            self.status = ConnectionStatus.DISCONNECTING
            await self.websocket.close(code=code, reason=reason)
            self.status = ConnectionStatus.DISCONNECTED
            logger.info(f"WebSocket connection closed: {self.connection_id} - {reason}")

        except Exception as e:
            logger.error(f"Error closing connection {self.connection_id}: {e}")

class WebSocketManager:
    """WebSocket连接管理器"""

    def __init__(self):
        # 存储所有活跃连接
        self.connections: Dict[str, WebSocketConnection] = {}

        # 按主题分组的连接
        self.topic_connections: Dict[str, Set[str]] = {}

        # 统计信息
        self.total_connections = 0
        self.start_time = datetime.now()

        # 心跳检测任务
        self.heartbeat_task = None

        logger.info("WebSocketManager initialized")

    async def add_connection(self, connection: WebSocketConnection):
        """添加连接"""
        self.connections[connection.connection_id] = connection
        self.total_connections += 1

        logger.info(f"Connection added: {connection.connection_id} (Total: {len(self.connections)})")

    async def remove_connection(self, connection_id: str):
        """移除连接"""
        if connection_id in self.connections:
            connection = self.connections.pop(connection_id)

            # 从所有订阅主题中移除
            for topic in connection.subscriptions:
                if topic in self.topic_connections:
                    self.topic_connections[topic].discard(connection_id)
                    if not self.topic_connections[topic]:
                        del self.topic_connections[topic]

            logger.info(f"Connection removed: {connection_id} (Total: {len(self.connections)})")

    def get_connection(self, connection_id: str) -> Optional[WebSocketConnection]:
        """获取连接"""
        return self.connections.get(connection_id)

    def get_connections_by_topic(self, topic: str) -> List[WebSocketConnection]:
        """获取订阅指定主题的连接"""
        if topic not in self.topic_connections:
            return []

        connections = []
        for conn_id in self.topic_connections[topic]:
            if conn_id in self.connections:
                connections.append(self.connections[conn_id])

        return connections

    async def subscribe_to_topic(self, connection_id: str, topic: str):
        """订阅主题"""
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            await connection.subscribe(topic)

            if topic not in self.topic_connections:
                self.topic_connections[topic] = set()
            self.topic_connections[topic].add(connection_id)

    async def unsubscribe_from_topic(self, connection_id: str, topic: str):
        """取消订阅主题"""
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            await connection.unsubscribe(topic)

            if topic in self.topic_connections:
                self.topic_connections[topic].discard(connection_id)
                if not self.topic_connections[topic]:
                    del self.topic_connections[topic]

    async def broadcast_to_topic(self, topic: str, msg_type: MessageType,
                                 data: Any = None, exclude_connection: str = None):
        """向主题广播消息"""
        connections = self.get_connections_by_topic(topic)

        if not connections:
            logger.debug(f"No connections subscribed to topic: {topic}")
            return

        message_id = str(uuid.uuid4())
        failed_connections = []

        for connection in connections:
            if exclude_connection and connection.connection_id == exclude_connection:
                continue

            try:
                await connection.send_message(msg_type, data, message_id, topic)
            except Exception as e:
                logger.error(f"Failed to send message to connection {connection.connection_id}: {e}")
                failed_connections.append(connection.connection_id)

        # 清理失败的连接
        for conn_id in failed_connections:
            await self.remove_connection(conn_id)

        logger.debug(f"Broadcasted to topic {topic}: {len(connections)} connections")

    async def broadcast_to_all(self, msg_type: MessageType, data: Any = None,
                               permission_required: str = None):
        """向所有连接广播消息"""
        if not self.connections:
            logger.debug("No active connections for broadcast")
            return

        message_id = str(uuid.uuid4())
        failed_connections = []
        sent_count = 0

        for connection in self.connections.values():
            # 检查权限
            if permission_required and not connection.has_permission(permission_required):
                continue

            try:
                await connection.send_message(msg_type, data, message_id)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to connection {connection.connection_id}: {e}")
                failed_connections.append(connection.connection_id)

        # 清理失败的连接
        for conn_id in failed_connections:
            await self.remove_connection(conn_id)

        logger.info(f"Broadcast sent to {sent_count} connections")

    async def start_heartbeat(self, interval_seconds: int = 30):
        """启动心跳检测"""
        if self.heartbeat_task:
            logger.warning("Heartbeat already running")
            return

        async def heartbeat_loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)

                    # 检查所有连接的心跳
                    dead_connections = []

                    for conn_id, connection in self.connections.items():
                        if not connection.is_alive():
                            dead_connections.append(conn_id)
                        else:
                            # 发送ping
                            try:
                                await connection.ping()
                            except Exception as e:
                                logger.warning(f"Failed to ping connection {conn_id}: {e}")
                                dead_connections.append(conn_id)

                    # 清理死连接
                    for conn_id in dead_connections:
                        logger.info(f"Removing dead connection: {conn_id}")
                        await self.remove_connection(conn_id)

                    if dead_connections:
                        logger.info(f"Cleaned up {len(dead_connections)} dead connections")

                except Exception as e:
                    logger.error(f"Heartbeat error: {e}")

        self.heartbeat_task = asyncio.create_task(heartbeat_loop())
        logger.info(f"Heartbeat started with {interval_seconds}s interval")

    async def stop_heartbeat(self):
        """停止心跳检测"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None
            logger.info("Heartbeat stopped")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_connections": len(self.connections),
            "total_connections": self.total_connections,
            "topics": len(self.topic_connections),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "connections_by_status": {
                status.value: sum(1 for conn in self.connections.values()
                                  if conn.status == status)
                for status in ConnectionStatus
            },
            "topic_stats": {
                topic: len(connections)
                for topic, connections in self.topic_connections.items()
            }
        }

    async def close_all_connections(self, reason: str = "Server shutdown"):
        """关闭所有连接"""
        logger.info(f"Closing all connections: {reason}")

        # 发送关闭通知
        await self.broadcast_to_all(MessageType.SUCCESS, {
            "message": "服务器即将关闭连接",
            "reason": reason
        })

        # 等待一小段时间让消息发送完成
        await asyncio.sleep(1)

        # 关闭所有连接
        close_tasks = []
        for connection in self.connections.values():
            close_tasks.append(connection.close(1001, reason))

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        self.connections.clear()
        self.topic_connections.clear()

        logger.info("All connections closed")

# 全局WebSocket管理器实例
ws_manager = WebSocketManager()

class WebSocketServer:
    """WebSocket服务器类"""

    def __init__(self):
        self.manager = ws_manager
        self.is_running = False

    async def start(self):
        """启动WebSocket服务器"""
        if self.is_running:
            logger.warning("WebSocket server is already running")
            return

        logger.info("Starting WebSocket server...")

        # 启动心跳检测
        await self.manager.start_heartbeat()

        self.is_running = True
        logger.info("WebSocket server started")

    async def stop(self):
        """停止WebSocket服务器"""
        if not self.is_running:
            logger.warning("WebSocket server is not running")
            return

        logger.info("Stopping WebSocket server...")

        # 停止心跳检测
        await self.manager.stop_heartbeat()

        # 关闭所有连接
        await self.manager.close_all_connections("Server shutdown")

        self.is_running = False
        logger.info("WebSocket server stopped")

    def get_stats(self):
        """获取服务器统计信息"""
        return self.manager.get_stats()

# 全局WebSocket服务器实例
ws_server = WebSocketServer()

# WebSocket端点处理器
async def handle_websocket_connection(websocket: WebSocket, connection_type: str,
                                      target_id: str = None, token: str = None):
    """通用WebSocket连接处理器"""
    connection = WebSocketConnection(websocket)

    try:
        # 接受连接
        await connection.accept()
        await ws_manager.add_connection(connection)

        # 认证（如果需要）
        if token:
            if not await connection.authenticate(token):
                await connection.close(4003, "Authentication failed")
                return

        # 处理不同类型的连接
        if connection_type == "terminal":
            await handle_terminal_connection(connection, target_id)
        elif connection_type == "container":
            await handle_container_connection(connection, target_id)
        elif connection_type == "build":
            await handle_build_connection(connection, target_id)
        elif connection_type == "system":
            await handle_system_connection(connection)
        elif connection_type == "notifications":
            await handle_notification_connection(connection)
        else:
            await connection.send_error("invalid_type", f"不支持的连接类型: {connection_type}")
            await connection.close(4004, "Invalid connection type")
            return

        # 消息处理循环
        while True:
            message = await connection.receive_message()
            if message is None:
                continue

            # 处理通用消息
            if message.type == MessageType.PING:
                await connection.pong()
            elif message.type == MessageType.AUTH:
                token = message.data.get("token") if message.data else None
                await connection.authenticate(token)
            else:
                # 委托给具体的处理器
                await handle_message_by_type(connection, connection_type, target_id, message)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection.connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await ws_manager.remove_connection(connection.connection_id)

async def handle_terminal_connection(connection: WebSocketConnection, session_id: str):
    """处理终端连接"""
    try:
        from services.terminal_service import TerminalService
        terminal_service = TerminalService()

        # 验证会话是否存在
        session = await terminal_service.get_session(session_id)
        if not session:
            await connection.send_error("session_not_found", f"终端会话 {session_id} 不存在")
            await connection.close(4004, "Session not found")
            return

        # 订阅终端主题
        topic = f"terminal:{session_id}"
        await ws_manager.subscribe_to_topic(connection.connection_id, topic)

        # 建立终端连接
        await terminal_service.attach_websocket(session_id, connection)

        logger.info(f"Terminal connection established for session: {session_id}")

    except Exception as e:
        logger.error(f"Terminal connection error: {e}")
        await connection.send_error("terminal_error", str(e))

async def handle_container_connection(connection: WebSocketConnection, container_id: str):
    """处理容器监控连接"""
    try:
        # 订阅容器监控主题
        topic = f"container:{container_id}"
        await ws_manager.subscribe_to_topic(connection.connection_id, topic)

        logger.info(f"Container monitoring connection established for: {container_id}")

    except Exception as e:
        logger.error(f"Container connection error: {e}")
        await connection.send_error("container_error", str(e))

async def handle_build_connection(connection: WebSocketConnection, build_id: str):
    """处理构建监控连接"""
    try:
        # 订阅构建监控主题
        topic = f"build:{build_id}"
        await ws_manager.subscribe_to_topic(connection.connection_id, topic)

        logger.info(f"Build monitoring connection established for: {build_id}")

    except Exception as e:
        logger.error(f"Build connection error: {e}")
        await connection.send_error("build_error", str(e))

async def handle_system_connection(connection: WebSocketConnection):
    """处理系统监控连接"""
    try:
        # 订阅系统监控主题
        await ws_manager.subscribe_to_topic(connection.connection_id, "system")

        logger.info("System monitoring connection established")

    except Exception as e:
        logger.error(f"System connection error: {e}")
        await connection.send_error("system_error", str(e))

async def handle_notification_connection(connection: WebSocketConnection):
    """处理通知连接"""
    try:
        # 订阅通知主题
        await ws_manager.subscribe_to_topic(connection.connection_id, "notifications")

        logger.info("Notification connection established")

    except Exception as e:
        logger.error(f"Notification connection error: {e}")
        await connection.send_error("notification_error", str(e))

async def handle_message_by_type(connection: WebSocketConnection, connection_type: str,
                                 target_id: str, message: WebSocketMessage):
    """根据连接类型处理消息"""
    try:
        if connection_type == "terminal":
            await handle_terminal_message(connection, target_id, message)
        elif connection_type == "container":
            await handle_container_message(connection, target_id, message)
        elif connection_type == "build":
            await handle_build_message(connection, target_id, message)
        elif connection_type == "system":
            await handle_system_message(connection, message)
        elif connection_type == "notifications":
            await handle_notification_message(connection, message)
        else:
            await connection.send_error("unsupported_message",
                                        f"连接类型 {connection_type} 不支持消息: {message.type}")

    except Exception as e:
        logger.error(f"Message handling error: {e}")
        await connection.send_error("message_error", str(e))

async def handle_terminal_message(connection: WebSocketConnection, session_id: str,
                                  message: WebSocketMessage):
    """处理终端消息"""
    from services.terminal_service import TerminalService
    terminal_service = TerminalService()

    if message.type == MessageType.TERMINAL_INPUT:
        # 处理终端输入
        input_data = message.data.get("input", "") if message.data else ""
        await terminal_service.send_input(session_id, input_data)

    elif message.type == MessageType.TERMINAL_RESIZE:
        # 处理终端大小调整
        if message.data:
            width = message.data.get("width", 80)
            height = message.data.get("height", 24)
            await terminal_service.resize_terminal(session_id, width, height)

async def handle_container_message(connection: WebSocketConnection, container_id: str,
                                   message: WebSocketMessage):
    """处理容器消息"""
    # 这里可以处理容器相关的WebSocket消息
    # 例如：请求实时统计、日志流等
    pass

async def handle_build_message(connection: WebSocketConnection, build_id: str,
                               message: WebSocketMessage):
    """处理构建消息"""
    # 这里可以处理构建相关的WebSocket消息
    # 例如：请求实时日志、取消构建等
    pass

async def handle_system_message(connection: WebSocketConnection, message: WebSocketMessage):
    """处理系统消息"""
    # 这里可以处理系统相关的WebSocket消息
    pass

async def handle_notification_message(connection: WebSocketConnection, message: WebSocketMessage):
    """处理通知消息"""
    # 这里可以处理通知相关的WebSocket消息
    pass

# 便捷函数，用于发送各种类型的推送消息
async def push_terminal_output(session_id: str, output: str):
    """推送终端输出"""
    topic = f"terminal:{session_id}"
    await ws_manager.broadcast_to_topic(topic, MessageType.TERMINAL_OUTPUT, {
        "session_id": session_id,
        "output": output,
        "timestamp": datetime.now().isoformat()
    })

async def push_container_status(container_id: str, status: str, details: Dict[str, Any] = None):
    """推送容器状态更新"""
    topic = f"container:{container_id}"
    await ws_manager.broadcast_to_topic(topic, MessageType.CONTAINER_STATUS, {
        "container_id": container_id,
        "status": status,
        "details": details or {},
        "timestamp": datetime.now().isoformat()
    })

async def push_build_progress(build_id: str, progress: int, status: str, message: str = None):
    """推送构建进度"""
    topic = f"build:{build_id}"
    await ws_manager.broadcast_to_topic(topic, MessageType.BUILD_PROGRESS, {
        "build_id": build_id,
        "progress": progress,
        "status": status,
        "message": message,
        "timestamp": datetime.now().isoformat()
    })

async def push_system_alert(alert_type: str, message: str, severity: str = "info"):
    """推送系统告警"""
    await ws_manager.broadcast_to_topic("system", MessageType.SYSTEM_ALERT, {
        "alert_type": alert_type,
        "message": message,
        "severity": severity,
        "timestamp": datetime.now().isoformat()
    })

async def push_notification(message: str, notification_type: str = "info",
                            target_user: str = None, data: Dict[str, Any] = None):
    """推送通知消息"""
    notification_data = {
        "message": message,
        "type": notification_type,
        "data": data or {},
        "timestamp": datetime.now().isoformat()
    }

    if target_user:
        # 发送给特定用户（需要实现用户连接映射）
        topic = f"user:{target_user}"
        await ws_manager.broadcast_to_topic(topic, MessageType.NOTIFICATION, notification_data)
    else:
        # 广播给所有订阅通知的用户
        await ws_manager.broadcast_to_topic("notifications", MessageType.NOTIFICATION, notification_data)

# 导出主要组件
__all__ = [
    "WebSocketServer",
    "WebSocketManager",
    "WebSocketConnection",
    "WebSocketMessage",
    "MessageType",
    "ConnectionStatus",
    "ws_server",
    "ws_manager",
    "handle_websocket_connection",
    "push_terminal_output",
    "push_container_status",
    "push_build_progress",
    "push_system_alert",
    "push_notification"
]