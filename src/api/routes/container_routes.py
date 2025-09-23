# 25. src/api/routes/container_routes.py
"""
容器管理路由 - eulermaker-docker-optimizer的容器API路由

******OSPP-2025-张金荣******

提供完整的容器生命周期管理API端点：
- 容器的创建、启动、停止、删除操作
- 容器信息查询和状态监控
- 容器日志和性能数据获取
- 容器网络和存储管理
- 批量操作支持

路由规划：
- GET /api/v1/containers - 获取容器列表
- POST /api/v1/containers - 创建新容器
- GET /api/v1/containers/{container_id} - 获取容器详情
- PUT /api/v1/containers/{container_id} - 更新容器配置
- DELETE /api/v1/containers/{container_id} - 删除容器
- POST /api/v1/containers/{container_id}/start - 启动容器
- POST /api/v1/containers/{container_id}/stop - 停止容器
- POST /api/v1/containers/{container_id}/restart - 重启容器
- GET /api/v1/containers/{container_id}/logs - 获取容器日志
- GET /api/v1/containers/{container_id}/stats - 获取容器统计信息
- POST /api/v1/containers/batch - 批量操作容器
"""

from typing import Dict, List, Optional, Any, Union
import asyncio
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, validator

from fastapi import HTTPException, Query, Path, Body, Depends
from fastapi.responses import StreamingResponse

from utils.logger import get_logger
from utils.exceptions import APIError, ValidationError
from utils.validators import validate_container_name, validate_image_tag
from api import (
    APIStatus, APIErrorCode, create_error_response,
    create_success_response, create_paginated_response
)
from api.routes import BaseRouter, RouteDecorators
from services.container_service import ContainerService
from models.container_model import ContainerModel, ContainerStatus, ContainerConfig

logger = get_logger(__name__)

# Pydantic模型定义 - 请求和响应数据结构
class ContainerCreateRequest(BaseModel):
    """创建容器请求模型"""
    name: str = Field(..., min_length=1, max_length=128, description="容器名称")
    image: str = Field(..., min_length=1, description="Docker镜像名称和标签")
    command: Optional[List[str]] = Field(None, description="启动命令")
    environment: Optional[Dict[str, str]] = Field(None, description="环境变量")
    ports: Optional[Dict[str, Union[int, str]]] = Field(None, description="端口映射")
    volumes: Optional[List[str]] = Field(None, description="数据卷挂载")
    working_dir: Optional[str] = Field(None, description="工作目录")
    user: Optional[str] = Field(None, description="运行用户")
    memory_limit: Optional[str] = Field(None, description="内存限制 (如: 512m, 1g)")
    cpu_limit: Optional[float] = Field(None, ge=0.1, description="CPU限制 (如: 0.5, 1.0)")
    restart_policy: Optional[str] = Field("no", description="重启策略")
    network_mode: Optional[str] = Field("bridge", description="网络模式")
    labels: Optional[Dict[str, str]] = Field(None, description="容器标签")

    @validator('name')
    def validate_name(cls, v):
        if not validate_container_name(v):
            raise ValueError("容器名称格式无效")
        return v

    @validator('image')
    def validate_image(cls, v):
        if not validate_image_tag(v):
            raise ValueError("镜像名称格式无效")
        return v

    @validator('restart_policy')
    def validate_restart_policy(cls, v):
        valid_policies = ['no', 'always', 'unless-stopped', 'on-failure']
        if v not in valid_policies:
            raise ValueError(f"重启策略必须是: {', '.join(valid_policies)}")
        return v

class ContainerUpdateRequest(BaseModel):
    """更新容器请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=128, description="新的容器名称")
    labels: Optional[Dict[str, str]] = Field(None, description="更新标签")
    restart_policy: Optional[str] = Field(None, description="重启策略")

    @validator('name')
    def validate_name(cls, v):
        if v and not validate_container_name(v):
            raise ValueError("容器名称格式无效")
        return v

class ContainerResponse(BaseModel):
    """容器响应模型"""
    id: str = Field(..., description="容器ID")
    name: str = Field(..., description="容器名称")
    image: str = Field(..., description="镜像名称")
    status: str = Field(..., description="容器状态")
    state: str = Field(..., description="运行状态")
    created_at: datetime = Field(..., description="创建时间")
    started_at: Optional[datetime] = Field(None, description="启动时间")
    ports: Optional[Dict[str, Any]] = Field(None, description="端口配置")
    labels: Optional[Dict[str, str]] = Field(None, description="标签信息")

class ContainerStatsResponse(BaseModel):
    """容器统计信息响应模型"""
    container_id: str = Field(..., description="容器ID")
    name: str = Field(..., description="容器名称")
    cpu_usage: float = Field(..., description="CPU使用率(%)")
    memory_usage: int = Field(..., description="内存使用量(字节)")
    memory_limit: int = Field(..., description="内存限制(字节)")
    network_rx: int = Field(..., description="网络接收字节数")
    network_tx: int = Field(..., description="网络发送字节数")
    block_read: int = Field(..., description="磁盘读取字节数")
    block_write: int = Field(..., description="磁盘写入字节数")
    timestamp: datetime = Field(..., description="统计时间")

class BatchOperationRequest(BaseModel):
    """批量操作请求模型"""
    operation: str = Field(..., description="操作类型: start, stop, restart, delete")
    container_ids: List[str] = Field(..., min_items=1, max_items=50, description="容器ID列表")
    force: bool = Field(False, description="是否强制执行")

    @validator('operation')
    def validate_operation(cls, v):
        valid_ops = ['start', 'stop', 'restart', 'delete']
        if v not in valid_ops:
            raise ValueError(f"操作类型必须是: {', '.join(valid_ops)}")
        return v

def create_container_router() -> BaseRouter:
    """创建容器管理路由器"""
    container_router = BaseRouter("/api/v1/containers", ["容器管理"])

    # 注入容器服务依赖
    def get_container_service() -> ContainerService:
        """获取容器服务实例"""
        return ContainerService()

    @container_router.router.get("/",
                                 summary="获取容器列表",
                                 description="获取系统中的容器列表，支持分页和过滤",
                                 response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    @RouteDecorators.rate_limit(requests_per_minute=100)
    async def list_containers(
            page: int = Query(1, ge=1, description="页码"),
            per_page: int = Query(20, ge=1, le=100, description="每页数量"),
            status: Optional[str] = Query(None, description="过滤状态: all, running, stopped, paused"),
            name_filter: Optional[str] = Query(None, alias="name", description="按名称过滤"),
            image_filter: Optional[str] = Query(None, alias="image", description="按镜像过滤"),
            label_filter: Optional[str] = Query(None, alias="labels", description="按标签过滤 (格式: key=value)"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """获取容器列表"""
        try:
            logger.info(f"Getting container list - page: {page}, per_page: {per_page}")

            # 构建过滤条件
            filters = {}
            if status and status != "all":
                filters["status"] = status
            if name_filter:
                filters["name"] = name_filter
            if image_filter:
                filters["image"] = image_filter
            if label_filter:
                # 解析标签过滤器 key=value
                if "=" in label_filter:
                    key, value = label_filter.split("=", 1)
                    filters["label"] = {key.strip(): value.strip()}

            # 获取容器列表
            containers, total = await container_service.list_containers(
                page=page,
                per_page=per_page,
                filters=filters
            )

            # 转换为响应格式
            container_responses = []
            for container in containers:
                container_responses.append(ContainerResponse(
                    id=container.id,
                    name=container.name,
                    image=container.image,
                    status=container.status.value,
                    state=container.state,
                    created_at=container.created_at,
                    started_at=container.started_at,
                    ports=container.ports,
                    labels=container.labels
                ).dict())

            return create_paginated_response(
                items=container_responses,
                total=total,
                page=page,
                per_page=per_page,
                message="容器列表获取成功"
            )

        except Exception as e:
            logger.error(f"Failed to list containers: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取容器列表失败"
            )

    @container_router.router.post("/",
                                  summary="创建新容器",
                                  description="根据提供的配置创建新的Docker容器",
                                  response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["container:create"])
    @RouteDecorators.rate_limit(requests_per_minute=30)
    async def create_container(
            request: ContainerCreateRequest,
            start_immediately: bool = Query(False, description="是否立即启动容器"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """创建新容器"""
        try:
            logger.info(f"Creating container: {request.name}")

            # 检查容器名称是否已存在
            if await container_service.container_exists(request.name):
                raise HTTPException(
                    status_code=APIStatus.CONFLICT,
                    detail=f"容器名称 '{request.name}' 已存在"
                )

            # 构建容器配置
            container_config = ContainerConfig(
                name=request.name,
                image=request.image,
                command=request.command,
                environment=request.environment or {},
                ports=request.ports or {},
                volumes=request.volumes or [],
                working_dir=request.working_dir,
                user=request.user,
                memory_limit=request.memory_limit,
                cpu_limit=request.cpu_limit,
                restart_policy=request.restart_policy,
                network_mode=request.network_mode,
                labels=request.labels or {}
            )

            # 创建容器
            container = await container_service.create_container(container_config)

            # 如果需要立即启动
            if start_immediately:
                await container_service.start_container(container.id)
                container = await container_service.get_container(container.id)

            response_data = ContainerResponse(
                id=container.id,
                name=container.name,
                image=container.image,
                status=container.status.value,
                state=container.state,
                created_at=container.created_at,
                started_at=container.started_at,
                ports=container.ports,
                labels=container.labels
            ).dict()

            return create_success_response(
                data=response_data,
                message=f"容器 '{request.name}' 创建成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create container: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail=f"创建容器失败: {str(e)}"
            )

    @container_router.router.get("/{container_id}",
                                 summary="获取容器详情",
                                 description="获取指定容器的详细信息",
                                 response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_container(
            container_id: str = Path(..., description="容器ID或名称"),
            include_stats: bool = Query(False, description="是否包含统计信息"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """获取容器详情"""
        try:
            logger.info(f"Getting container details: {container_id}")

            # 获取容器信息
            container = await container_service.get_container(container_id)
            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{container_id}' 不存在"
                )

            # 构建响应数据
            response_data = ContainerResponse(
                id=container.id,
                name=container.name,
                image=container.image,
                status=container.status.value,
                state=container.state,
                created_at=container.created_at,
                started_at=container.started_at,
                ports=container.ports,
                labels=container.labels
            ).dict()

            # 如果需要包含统计信息
            if include_stats and container.status == ContainerStatus.RUNNING:
                try:
                    stats = await container_service.get_container_stats(container_id)
                    response_data["stats"] = ContainerStatsResponse(
                        container_id=container.id,
                        name=container.name,
                        cpu_usage=stats.cpu_usage,
                        memory_usage=stats.memory_usage,
                        memory_limit=stats.memory_limit,
                        network_rx=stats.network_rx,
                        network_tx=stats.network_tx,
                        block_read=stats.block_read,
                        block_write=stats.block_write,
                        timestamp=stats.timestamp
                    ).dict()
                except Exception as e:
                    logger.warning(f"Failed to get stats for container {container_id}: {e}")
                    response_data["stats"] = None

            return create_success_response(
                data=response_data,
                message="容器详情获取成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get container {container_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取容器详情失败"
            )

    @container_router.router.put("/{container_id}",
                                 summary="更新容器配置",
                                 description="更新容器的可修改配置项",
                                 response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["container:update"])
    async def update_container(
            container_id: str = Path(..., description="容器ID或名称"),
            request: ContainerUpdateRequest = Body(...),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """更新容器配置"""
        try:
            logger.info(f"Updating container: {container_id}")

            # 检查容器是否存在
            container = await container_service.get_container(container_id)
            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{container_id}' 不存在"
                )

            # 更新容器配置
            update_data = request.dict(exclude_unset=True)
            updated_container = await container_service.update_container(container_id, update_data)

            response_data = ContainerResponse(
                id=updated_container.id,
                name=updated_container.name,
                image=updated_container.image,
                status=updated_container.status.value,
                state=updated_container.state,
                created_at=updated_container.created_at,
                started_at=updated_container.started_at,
                ports=updated_container.ports,
                labels=updated_container.labels
            ).dict()

            return create_success_response(
                data=response_data,
                message="容器配置更新成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update container {container_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="更新容器配置失败"
            )

    @container_router.router.delete("/{container_id}",
                                    summary="删除容器",
                                    description="停止并删除指定容器",
                                    response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["container:delete"])
    async def delete_container(
            container_id: str = Path(..., description="容器ID或名称"),
            force: bool = Query(False, description="是否强制删除（即使容器正在运行）"),
            remove_volumes: bool = Query(False, description="是否删除关联的数据卷"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """删除容器"""
        try:
            logger.info(f"Deleting container: {container_id}")

            # 检查容器是否存在
            container = await container_service.get_container(container_id)
            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{container_id}' 不存在"
                )

            # 如果容器正在运行且未强制删除，先停止容器
            if container.status == ContainerStatus.RUNNING and not force:
                await container_service.stop_container(container_id)

            # 删除容器
            await container_service.delete_container(
                container_id,
                force=force,
                remove_volumes=remove_volumes
            )

            return create_success_response(
                message=f"容器 '{container.name}' 删除成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete container {container_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="删除容器失败"
            )

    @container_router.router.post("/{container_id}/start",
                                  summary="启动容器",
                                  description="启动指定的容器",
                                  response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["container:control"])
    async def start_container(
            container_id: str = Path(..., description="容器ID或名称"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """启动容器"""
        try:
            logger.info(f"Starting container: {container_id}")

            # 检查容器是否存在
            container = await container_service.get_container(container_id)
            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{container_id}' 不存在"
                )

            # 检查容器状态
            if container.status == ContainerStatus.RUNNING:
                return create_success_response(
                    message=f"容器 '{container.name}' 已经在运行中"
                )

            # 启动容器
            await container_service.start_container(container_id)

            # 获取更新后的容器信息
            updated_container = await container_service.get_container(container_id)

            response_data = ContainerResponse(
                id=updated_container.id,
                name=updated_container.name,
                image=updated_container.image,
                status=updated_container.status.value,
                state=updated_container.state,
                created_at=updated_container.created_at,
                started_at=updated_container.started_at,
                ports=updated_container.ports,
                labels=updated_container.labels
            ).dict()

            return create_success_response(
                data=response_data,
                message=f"容器 '{container.name}' 启动成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to start container {container_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="启动容器失败"
            )

    @container_router.router.post("/{container_id}/stop",
                                  summary="停止容器",
                                  description="停止指定的容器",
                                  response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["container:control"])
    async def stop_container(
            container_id: str = Path(..., description="容器ID或名称"),
            timeout: int = Query(10, ge=1, le=300, description="停止超时时间(秒)"),
            force: bool = Query(False, description="是否强制停止"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """停止容器"""
        try:
            logger.info(f"Stopping container: {container_id}")

            # 检查容器是否存在
            container = await container_service.get_container(container_id)
            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{container_id}' 不存在"
                )

            # 检查容器状态
            if container.status != ContainerStatus.RUNNING:
                return create_success_response(
                    message=f"容器 '{container.name}' 已经停止"
                )

            # 停止容器
            await container_service.stop_container(container_id, timeout=timeout, force=force)

            # 获取更新后的容器信息
            updated_container = await container_service.get_container(container_id)

            response_data = ContainerResponse(
                id=updated_container.id,
                name=updated_container.name,
                image=updated_container.image,
                status=updated_container.status.value,
                state=updated_container.state,
                created_at=updated_container.created_at,
                started_at=updated_container.started_at,
                ports=updated_container.ports,
                labels=updated_container.labels
            ).dict()

            return create_success_response(
                data=response_data,
                message=f"容器 '{container.name}' 停止成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="停止容器失败"
            )

    @container_router.router.post("/{container_id}/restart",
                                  summary="重启容器",
                                  description="重启指定的容器",
                                  response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["container:control"])
    async def restart_container(
            container_id: str = Path(..., description="容器ID或名称"),
            timeout: int = Query(10, ge=1, le=300, description="停止超时时间(秒)"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """重启容器"""
        try:
            logger.info(f"Restarting container: {container_id}")

            # 检查容器是否存在
            container = await container_service.get_container(container_id)
            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{container_id}' 不存在"
                )

            # 重启容器
            await container_service.restart_container(container_id, timeout=timeout)

            # 获取更新后的容器信息
            updated_container = await container_service.get_container(container_id)

            response_data = ContainerResponse(
                id=updated_container.id,
                name=updated_container.name,
                image=updated_container.image,
                status=updated_container.status.value,
                state=updated_container.state,
                created_at=updated_container.created_at,
                started_at=updated_container.started_at,
                ports=updated_container.ports,
                labels=updated_container.labels
            ).dict()

            return create_success_response(
                data=response_data,
                message=f"容器 '{container.name}' 重启成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to restart container {container_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="重启容器失败"
            )

    @container_router.router.get("/{container_id}/logs",
                                 summary="获取容器日志",
                                 description="获取容器的日志输出",
                                 response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_container_logs(
            container_id: str = Path(..., description="容器ID或名称"),
            lines: int = Query(100, ge=1, le=10000, description="日志行数"),
            since: Optional[str] = Query(None, description="起始时间 (ISO格式或相对时间如 '1h', '30m')"),
            follow: bool = Query(False, description="是否持续跟踪日志"),
            timestamps: bool = Query(True, description="是否包含时间戳"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """获取容器日志"""
        try:
            logger.info(f"Getting logs for container: {container_id}")

            # 检查容器是否存在
            container = await container_service.get_container(container_id)
            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{container_id}' 不存在"
                )

            # 如果是跟踪模式，返回流式响应
            if follow:
                async def log_generator():
                    async for log_line in container_service.follow_container_logs(
                            container_id, since=since, timestamps=timestamps
                    ):
                        yield f"data: {log_line}\n\n"

                return StreamingResponse(
                    log_generator(),
                    media_type="text/plain",
                    headers={"Cache-Control": "no-cache"}
                )

            # 获取日志内容
            logs = await container_service.get_container_logs(
                container_id,
                lines=lines,
                since=since,
                timestamps=timestamps
            )

            return create_success_response(
                data={
                    "container_id": container.id,
                    "container_name": container.name,
                    "logs": logs,
                    "lines_count": len(logs.split('\n')) if logs else 0,
                    "timestamps": timestamps
                },
                message="日志获取成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get logs for container {container_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取容器日志失败"
            )

    @container_router.router.get("/{container_id}/stats",
                                 summary="获取容器统计信息",
                                 description="获取容器的实时统计信息",
                                 response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_container_stats(
            container_id: str = Path(..., description="容器ID或名称"),
            stream: bool = Query(False, description="是否持续流式获取统计信息"),
            container_service: ContainerService = Depends(get_container_service)
    ):
        """获取容器统计信息"""
        try:
            logger.info(f"Getting stats for container: {container_id}")

            # 检查容器是否存在且运行中
            container = await container_service.get_container(container_id)
            if not container:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"容器 '{container_id}' 不存在"
                )

            if container.status != ContainerStatus.RUNNING:
                raise HTTPException(
                    status_code=APIStatus.BAD_REQUEST,
                    detail="只能获取运行中容器的统计信息"
                )

            # 如果是流式模式
            if stream:
                async def stats_generator():
                    async for stats in container_service.stream_container_stats(container_id):
                        stats_response = ContainerStatsResponse(
                            container_id=container.id,
                            name=container.name,
                            cpu_usage=stats.cpu_usage,
                            memory_usage=stats.memory_usage,
                            memory_limit=stats.memory_limit,
                            network_rx=stats.network_rx,
                            network_tx=stats.network_tx,
                            block_read=stats.block_read,
                            block_write=stats.block_write,
                            timestamp=stats.timestamp
                        )
                        yield f"data: {stats_response.json()}\n\n"

                return StreamingResponse(
                    stats_generator(),
                    media_type="text/plain",
                    headers={"Cache-Control": "no-cache"}
                )

            # 获取一次性统计信息
            stats = await container_service.get_container_stats(container_id)

            stats_response = ContainerStatsResponse(
                container_id=container.id,
                name=container.name,
                cpu_usage=stats.cpu_usage,
                memory_usage=stats.memory_usage,
                memory_limit=stats.memory_limit,
                network_rx=stats.network_rx,
                network_tx=stats.network_tx,
                block_read=stats.block_read,
                block_write=stats.block_write,
                timestamp=stats.timestamp
            )

            return create_success_response(
                data=stats_response.dict(),
                message="统计信息获取成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get stats for container {container_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取容器统计信息失败"
            )

    @container_router.router.post("/batch",
                                  summary="批量操作容器",
                                  description="对多个容器执行批量操作",
                                  response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["container:batch"])
    @RouteDecorators.rate_limit(requests_per_minute=10)
    async def batch_operation(
            request: BatchOperationRequest,
            container_service: ContainerService = Depends(get_container_service)
    ):
        """批量操作容器"""
        try:
            logger.info(f"Batch operation: {request.operation} on {len(request.container_ids)} containers")

            # 执行批量操作
            results = await container_service.batch_operation(
                operation=request.operation,
                container_ids=request.container_ids,
                force=request.force
            )

            # 统计操作结果
            success_count = len([r for r in results if r["success"]])
            failed_count = len([r for r in results if not r["success"]])

            return create_success_response(
                data={
                    "operation": request.operation,
                    "total_containers": len(request.container_ids),
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "results": results
                },
                message=f"批量操作完成: {success_count}个成功, {failed_count}个失败"
            )

        except Exception as e:
            logger.error(f"Batch operation failed: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="批量操作失败"
            )

    return container_router

# 导出路由创建函数
__all__ = [
    "create_container_router",
    "ContainerCreateRequest",
    "ContainerUpdateRequest",
    "ContainerResponse",
    "ContainerStatsResponse",
    "BatchOperationRequest"
]