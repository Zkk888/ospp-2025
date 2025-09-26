# 27. src/api/routes/terminal_routes.py (修正版)
"""
终端服务路由 - eulermaker-docker-optimizer的终端访问API路由

******OSPP-2025-张金荣******

提供完整的Web终端访问和管理API端点：
- Web终端会话管理
- 容器内终端连接
- 终端命令执行和历史记录
- 多用户终端会话支持
- 终端会话录制和回放

路由规划：
- GET /api/v1/terminals - 获取终端会话列表
- POST /api/v1/terminals - 创建新的终端会话
- GET /api/v1/terminals/{session_id} - 获取终端会话详情
- DELETE /api/v1/terminals/{session_id} - 关闭终端会话
- POST /api/v1/terminals/{session_id}/exec - 执行终端命令
- GET /api/v1/terminals/{session_id}/history - 获取命令历史
- GET /api/v1/terminals/{session_id}/recording - 获取会话录制
- POST /api/v1/terminals/{session_id}/resize - 调整终端大小
- GET /api/v1/terminals/{session_id}/page - 获取终端页面
"""
from services.container_service import ContainerService
from typing import Dict, List, Optional, Any, Union
import asyncio
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, validator

from fastapi import HTTPException, Query, Path, Body, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates  # 修正：使用正确的导入

from utils.logger import get_logger
from utils.exceptions import APIError, ValidationError
from api import (
    APIStatus, APIErrorCode, create_error_response,
    create_success_response, create_paginated_response
)
from api.routes import BaseRouter, RouteDecorators
from services.terminal_service import TerminalService
from models.container_model import ContainerStatus

logger = get_logger(__name__)

# 初始化模板引擎
templates = Jinja2Templates(directory="src/static/templates")

# Pydantic模型定义 - 请求和响应数据结构
class TerminalCreateRequest(BaseModel):
    """创建终端会话请求模型"""
    container_id: str = Field(..., description="容器ID或名称")
    command: str = Field("/bin/bash", description="启动命令")
    working_dir: Optional[str] = Field(None, description="工作目录")
    environment: Optional[Dict[str, str]] = Field(None, description="环境变量")
    user: Optional[str] = Field(None, description="运行用户")
    width: int = Field(80, ge=20, le=200, description="终端宽度(列)")
    height: int = Field(24, ge=10, le=100, description="终端高度(行)")
    enable_recording: bool = Field(True, description="是否启用会话录制")
    auto_close: bool = Field(True, description="命令结束时是否自动关闭会话")
    timeout_minutes: int = Field(30, ge=1, le=1440, description="会话超时时间(分钟)")

class TerminalExecRequest(BaseModel):
    """执行终端命令请求模型"""
    command: str = Field(..., min_length=1, description="要执行的命令")
    interactive: bool = Field(False, description="是否交互模式")
    timeout_seconds: int = Field(30, ge=1, le=300, description="命令执行超时时间(秒)")

class TerminalResizeRequest(BaseModel):
    """调整终端大小请求模型"""
    width: int = Field(..., ge=20, le=200, description="终端宽度(列)")
    height: int = Field(..., ge=10, le=100, description="终端高度(行)")

class TerminalResponse(BaseModel):
    """终端会话响应模型"""
    session_id: str = Field(..., description="会话ID")
    container_id: str = Field(..., description="容器ID")
    container_name: str = Field(..., description="容器名称")
    command: str = Field(..., description="启动命令")
    status: str = Field(..., description="会话状态")
    created_at: datetime = Field(..., description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    ended_at: Optional[datetime] = Field(None, description="结束时间")
    width: int = Field(..., description="终端宽度")
    height: int = Field(..., description="终端高度")
    user: Optional[str] = Field(None, description="运行用户")
    working_dir: Optional[str] = Field(None, description="工作目录")
    pid: Optional[int] = Field(None, description="进程ID")
    exit_code: Optional[int] = Field(None, description="退出代码")
    enable_recording: bool = Field(..., description="是否启用录制")

class TerminalHistoryResponse(BaseModel):
    """终端历史响应模型"""
    session_id: str = Field(..., description="会话ID")
    commands: List[Dict[str, Any]] = Field(..., description="命令历史列表")
    total_commands: int = Field(..., description="总命令数")

class TerminalRecordingResponse(BaseModel):
    """终端录制响应模型"""
    session_id: str = Field(..., description="会话ID")
    recording_data: str = Field(..., description="录制数据(base64编码)")
    duration_seconds: int = Field(..., description="录制时长(秒)")
    file_size: int = Field(..., description="文件大小(字节)")

def create_terminal_router() -> BaseRouter:
    """创建终端服务路由器"""
    terminal_router = BaseRouter("/terminals", ["终端服务"])

    # 注入终端服务依赖
    def get_terminal_service() -> TerminalService:
        """获取终端服务实例"""
        return TerminalService()

    @terminal_router.router.get("/",
                                summary="获取终端会话列表",
                                description="获取当前系统中的终端会话列表",
                                response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    @RouteDecorators.rate_limit(requests_per_minute=100)
    async def list_terminal_sessions(
            page: int = Query(1, ge=1, description="页码"),
            per_page: int = Query(20, ge=1, le=100, description="每页数量"),
            container_id: Optional[str] = Query(None, description="按容器ID过滤"),
            status: Optional[str] = Query(None, description="按状态过滤: active, inactive, expired"),
            user_filter: Optional[str] = Query(None, alias="user", description="按用户过滤"),
            terminal_service: TerminalService = Depends(get_terminal_service)
    ):
        """获取终端会话列表"""
        try:
            logger.info(f"Getting terminal sessions - page: {page}, per_page: {per_page}")

            # 构建过滤条件
            filters = {}
            if container_id:
                filters["container_id"] = container_id
            if status:
                filters["status"] = status
            if user_filter:
                filters["user"] = user_filter

            # 获取终端会话列表
            sessions, total = await terminal_service.list_sessions(
                page=page,
                per_page=per_page,
                filters=filters
            )

            # 转换为响应格式
            session_responses = []
            for session in sessions:
                session_responses.append(TerminalResponse(
                    session_id=session.session_id,
                    container_id=session.container_id,
                    container_name=session.container_name,
                    command=session.command,
                    status=session.status,
                    created_at=session.created_at,
                    started_at=session.started_at,
                    ended_at=session.ended_at,
                    width=session.width,
                    height=session.height,
                    user=session.user,
                    working_dir=session.working_dir,
                    pid=session.pid,
                    exit_code=session.exit_code,
                    enable_recording=session.enable_recording
                ).dict())

            return create_paginated_response(
                items=session_responses,
                total=total,
                page=page,
                per_page=per_page,
                message="终端会话列表获取成功"
            )

        except Exception as e:
            logger.error(f"Failed to list terminal sessions: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取终端会话列表失败"
            )

    @terminal_router.router.post("/",
                                 summary="创建终端会话",
                                 description="为指定容器创建新的终端会话",
                                 response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["terminal:create"])
    @RouteDecorators.rate_limit(requests_per_minute=20)
    async def create_terminal_session(
            request: TerminalCreateRequest,
            terminal_service: TerminalService = Depends(get_terminal_service)
    ):
        """创建终端会话"""
        try:
            logger.info(f"Creating terminal session for container: {request.container_id}")

            # 验证容器状态

            container_service = ContainerService()
            container = await container_service.get_container(request.container_id)

            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{request.container_id}' 不存在"
                )

            if container.status != ContainerStatus.RUNNING:
                raise HTTPException(
                    status_code=APIStatus.BAD_REQUEST,
                    detail="只能为运行中的容器创建终端会话"
                )

            # 创建终端会话配置
            session_config = {
                "container_id": request.container_id,
                "command": request.command,
                "working_dir": request.working_dir,
                "environment": request.environment or {},
                "user": request.user,
                "width": request.width,
                "height": request.height,
                "enable_recording": request.enable_recording,
                "auto_close": request.auto_close,
                "timeout_minutes": request.timeout_minutes
            }

            # 创建终端会话
            session = await terminal_service.create_session(session_config)

            response_data = TerminalResponse(
                session_id=session.session_id,
                container_id=session.container_id,
                container_name=session.container_name,
                command=session.command,
                status=session.status,
                created_at=session.created_at,
                started_at=session.started_at,
                ended_at=session.ended_at,
                width=session.width,
                height=session.height,
                user=session.user,
                working_dir=session.working_dir,
                pid=session.pid,
                exit_code=session.exit_code,
                enable_recording=session.enable_recording
            ).dict()

            # 添加 WebSocket连接信息
            response_data["websocket_url"] = f"/ws/terminals/{session.session_id}"
            response_data["web_terminal_url"] = f"/api/v1/terminals/{session.session_id}/page"

            return create_success_response(
                data=response_data,
                message="终端会话创建成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create terminal session: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail=f"创建终端会话失败: {str(e)}"
            )

    @terminal_router.router.get("/{session_id}",
                                summary="获取终端会话详情",
                                description="获取指定终端会话的详细信息",
                                response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_terminal_session(
            session_id: str = Path(..., description="终端会话ID"),
            terminal_service: TerminalService = Depends(get_terminal_service)
    ):
        """获取终端会话详情"""
        try:
            logger.info(f"Getting terminal session: {session_id}")

            session = await terminal_service.get_session(session_id)
            if not session:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"终端会话 '{session_id}' 不存在"
                )

            response_data = TerminalResponse(
                session_id=session.session_id,
                container_id=session.container_id,
                container_name=session.container_name,
                command=session.command,
                status=session.status,
                created_at=session.created_at,
                started_at=session.started_at,
                ended_at=session.ended_at,
                width=session.width,
                height=session.height,
                user=session.user,
                working_dir=session.working_dir,
                pid=session.pid,
                exit_code=session.exit_code,
                enable_recording=session.enable_recording
            ).dict()

            return create_success_response(
                data=response_data,
                message="终端会话详情获取成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get terminal session {session_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取终端会话详情失败"
            )

    @terminal_router.router.delete("/{session_id}",
                                   summary="关闭终端会话",
                                   description="关闭指定的终端会话",
                                   response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["terminal:delete"])
    async def close_terminal_session(
            session_id: str = Path(..., description="终端会话ID"),
            force: bool = Query(False, description="是否强制关闭"),
            terminal_service: TerminalService = Depends(get_terminal_service)
    ):
        """关闭终端会话"""
        try:
            logger.info(f"Closing terminal session: {session_id}, force: {force}")

            result = await terminal_service.close_session(session_id, force=force)
            if not result:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"终端会话 '{session_id}' 不存在"
                )

            return create_success_response(
                data={"session_id": session_id, "closed": True},
                message="终端会话关闭成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to close terminal session {session_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="关闭终端会话失败"
            )

    @terminal_router.router.post("/{session_id}/exec",
                                 summary="执行终端命令",
                                 description="在指定终端会话中执行命令",
                                 response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["terminal:exec"])
    @RouteDecorators.rate_limit(requests_per_minute=60)
    async def execute_terminal_command(
            session_id: str = Path(..., description="终端会话ID"),
            request: TerminalExecRequest = Body(...),
            terminal_service: TerminalService = Depends(get_terminal_service)
    ):
        """执行终端命令"""
        try:
            logger.info(f"Executing command in session {session_id}: {request.command}")

            # 检查会话是否存在
            session = await terminal_service.get_session(session_id)
            if not session:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"终端会话 '{session_id}' 不存在"
                )

            if session.status not in ["active", "running"]:
                raise HTTPException(
                    status_code=APIStatus.BAD_REQUEST,
                    detail="只能在活跃的终端会话中执行命令"
                )

            # 执行命令
            result = await terminal_service.execute_command(
                session_id,
                request.command,
                interactive=request.interactive,
                timeout_seconds=request.timeout_seconds
            )

            return create_success_response(
                data=result,
                message="命令执行成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to execute command in session {session_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="命令执行失败"
            )

    @terminal_router.router.get("/{session_id}/history",
                                summary="获取命令历史",
                                description="获取指定终端会话的命令执行历史",
                                response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_terminal_history(
            session_id: str = Path(..., description="终端会话ID"),
            limit: int = Query(50, ge=1, le=1000, description="返回记录数量限制"),
            offset: int = Query(0, ge=0, description="记录偏移量"),
            terminal_service: TerminalService = Depends(get_terminal_service)
    ):
        """获取命令历史"""
        try:
            logger.info(f"Getting history for session {session_id}")

            # 检查会话是否存在
            session = await terminal_service.get_session(session_id)
            if not session:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"终端会话 '{session_id}' 不存在"
                )

            # 获取命令历史
            commands, total = await terminal_service.get_command_history(
                session_id, limit=limit, offset=offset
            )

            response_data = TerminalHistoryResponse(
                session_id=session_id,
                commands=commands,
                total_commands=total
            ).dict()

            return create_success_response(
                data=response_data,
                message="命令历史获取成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get history for session {session_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取命令历史失败"
            )

    @terminal_router.router.post("/{session_id}/resize",
                                 summary="调整终端大小",
                                 description="调整指定终端会话的窗口大小",
                                 response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def resize_terminal(
            session_id: str = Path(..., description="终端会话ID"),
            request: TerminalResizeRequest = Body(...),
            terminal_service: TerminalService = Depends(get_terminal_service)
    ):
        """调整终端大小"""
        try:
            logger.info(f"Resizing terminal session {session_id}: {request.width}x{request.height}")

            # 检查会话是否存在
            session = await terminal_service.get_session(session_id)
            if not session:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"终端会话 '{session_id}' 不存在"
                )

            # 调整大小
            result = await terminal_service.resize_terminal(
                session_id, request.width, request.height
            )

            return create_success_response(
                data={
                    "session_id": session_id,
                    "width": request.width,
                    "height": request.height,
                    "resized": result
                },
                message="终端大小调整成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to resize terminal session {session_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="调整终端大小失败"
            )

    @terminal_router.router.get("/{session_id}/recording",
                                summary="获取会话录制",
                                description="获取指定终端会话的录制数据",
                                response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_terminal_recording(
            session_id: str = Path(..., description="终端会话ID"),
            format: str = Query("base64", description="录制数据格式: base64, raw"),
            terminal_service: TerminalService = Depends(get_terminal_service)
    ):
        """获取会话录制"""
        try:
            logger.info(f"Getting recording for session {session_id}")

            # 检查会话是否存在
            session = await terminal_service.get_session(session_id)
            if not session:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"终端会话 '{session_id}' 不存在"
                )

            if not session.enable_recording:
                raise HTTPException(
                    status_code=APIStatus.BAD_REQUEST,
                    detail="该会话未启用录制功能"
                )

            # 获取录制数据
            recording_data = await terminal_service.get_session_recording(
                session_id, format=format
            )

            if not recording_data:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail="未找到录制数据"
                )

            if format == "raw":
                # 返回原始数据流
                return StreamingResponse(
                    recording_data["stream"],
                    media_type="application/octet-stream",
                    headers={
                        "Content-Disposition": f"attachment; filename=terminal_{session_id}.cast"
                    }
                )
            else:
                # 返回base64编码数据
                response_data = TerminalRecordingResponse(
                    session_id=session_id,
                    recording_data=recording_data["data"],
                    duration_seconds=recording_data["duration"],
                    file_size=recording_data["size"]
                ).dict()

                return create_success_response(
                    data=response_data,
                    message="会话录制获取成功"
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get recording for session {session_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取会话录制失败"
            )

    @terminal_router.router.get("/{session_id}/page",
                                summary="获取终端页面",
                                description="获取Web终端访问页面",
                                response_class=HTMLResponse)
    @RouteDecorators.require_auth()
    async def get_terminal_page(
            request: Request,  # 没有默认值的参数放在前面
            session_id: str = Path(..., description="终端会话ID"),  # 有默认值的参数
            terminal_service: TerminalService = Depends(get_terminal_service)  # 有默认值的参数
    ):
        """获取终端页面"""
        try:
            # 检查会话是否存在
            session = await terminal_service.get_session(session_id)
            if not session:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"终端会话 '{session_id}' 不存在"
                )

            # 构建WebSocket URL
            ws_scheme = "wss" if request.url.scheme == "https" else "ws"
            ws_url = f"{ws_scheme}://{request.url.netloc}/ws/terminals/{session_id}"

            # 渲染终端页面
            return templates.TemplateResponse(
                "terminal.html",
                {
                    "request": request,
                    "session_id": session_id,
                    "container_name": session.container_name,
                    "websocket_url": ws_url,
                    "terminal_width": session.width,
                    "terminal_height": session.height
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get terminal page for session {session_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取终端页面失败"
            )

    # 注意：WebSocket相关路由已移至websocket_server.py中处理

    return terminal_router

# 导出路由创建函数
__all__ = [
    "create_terminal_router",
    "TerminalCreateRequest",
    "TerminalExecRequest",
    "TerminalResizeRequest",
    "TerminalResponse",
    "TerminalHistoryResponse",
    "TerminalRecordingResponse"
]