# 26. src/api/routes/build_routes.py
"""
构建管理路由 - eulermaker-docker-optimizer的RPM构建API路由

******OSPP-2025-张金荣******

提供完整的RPM包构建管理API端点：
- 构建任务的创建、监控和管理
- 构建进度实时跟踪
- 构建结果下载和管理
- 构建历史查询和统计
- 多种构建模式支持（单包构建、批量构建等）

路由规划：
- GET /api/v1/builds - 获取构建任务列表
- POST /api/v1/builds - 创建新的构建任务
- GET /api/v1/builds/{build_id} - 获取构建任务详情
- PUT /api/v1/builds/{build_id} - 更新构建任务配置
- DELETE /api/v1/builds/{build_id} - 删除构建任务
- POST /api/v1/builds/{build_id}/start - 启动构建任务
- POST /api/v1/builds/{build_id}/cancel - 取消构建任务
- GET /api/v1/builds/{build_id}/logs - 获取构建日志
- GET /api/v1/builds/{build_id}/artifacts - 获取构建产物
- GET /api/v1/builds/{build_id}/download - 下载构建结果
- POST /api/v1/builds/batch - 批量构建任务
- GET /api/v1/builds/stats - 构建统计信息
"""

from typing import Dict, List, Optional, Any, Union
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from pydantic import BaseModel, Field, validator

from fastapi import HTTPException, Query, Path, Body, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse

from utils.logger import get_logger
from utils.exceptions import APIError, ValidationError
from utils.validators import validate_package_name, validate_version_string
from api import (
    APIStatus, APIErrorCode, create_error_response,
    create_success_response, create_paginated_response
)
from api.routes import BaseRouter, RouteDecorators
from services.build_service import BuildService
from models.build_model import BuildModel, BuildStatus, BuildConfig, BuildType

logger = get_logger(__name__)

# Pydantic模型定义 - 请求和响应数据结构
class BuildCreateRequest(BaseModel):
    """创建构建任务请求模型"""
    name: str = Field(..., min_length=1, max_length=128, description="构建任务名称")
    package_name: str = Field(..., min_length=1, description="RPM包名称")
    package_version: str = Field(..., description="包版本号")
    build_type: str = Field("rpm", description="构建类型: rpm, srpm, container")
    source_type: str = Field("spec", description="源码类型: spec, git, tar")
    source_url: Optional[str] = Field(None, description="源码URL (git仓库或tar包)")
    git_branch: Optional[str] = Field("master", description="Git分支名称")
    git_commit: Optional[str] = Field(None, description="Git提交哈希 (可选)")
    build_arch: List[str] = Field(["x86_64"], description="构建架构列表")
    build_environment: Dict[str, str] = Field(default_factory=dict, description="构建环境变量")
    build_dependencies: List[str] = Field(default_factory=list, description="构建依赖包列表")
    mock_config: Optional[str] = Field(None, description="Mock配置名称")
    priority: int = Field(5, ge=1, le=10, description="构建优先级 (1-10, 10最高)")
    timeout_minutes: int = Field(60, ge=5, le=1440, description="构建超时时间(分钟)")
    enable_tests: bool = Field(True, description="是否启用测试")
    clean_build: bool = Field(False, description="是否清理构建")
    tags: List[str] = Field(default_factory=list, description="构建标签")

    @validator('package_name')
    def validate_package_name(cls, v):
        if not validate_package_name(v):
            raise ValueError("包名称格式无效")
        return v

    @validator('package_version')
    def validate_version(cls, v):
        if not validate_version_string(v):
            raise ValueError("版本号格式无效")
        return v

    @validator('build_type')
    def validate_build_type(cls, v):
        valid_types = ['rpm', 'srpm', 'container', 'deb']
        if v not in valid_types:
            raise ValueError(f"构建类型必须是: {', '.join(valid_types)}")
        return v

    @validator('source_type')
    def validate_source_type(cls, v):
        valid_types = ['spec', 'git', 'tar', 'upload']
        if v not in valid_types:
            raise ValueError(f"源码类型必须是: {', '.join(valid_types)}")
        return v

class BuildUpdateRequest(BaseModel):
    """更新构建任务请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=128, description="构建任务名称")
    priority: Optional[int] = Field(None, ge=1, le=10, description="构建优先级")
    timeout_minutes: Optional[int] = Field(None, ge=5, le=1440, description="构建超时时间")
    build_environment: Optional[Dict[str, str]] = Field(None, description="构建环境变量")
    tags: Optional[List[str]] = Field(None, description="构建标签")

class BuildResponse(BaseModel):
    """构建任务响应模型"""
    id: str = Field(..., description="构建任务ID")
    name: str = Field(..., description="构建任务名称")
    package_name: str = Field(..., description="RPM包名称")
    package_version: str = Field(..., description="包版本号")
    build_type: str = Field(..., description="构建类型")
    status: str = Field(..., description="构建状态")
    progress: int = Field(..., ge=0, le=100, description="构建进度百分比")
    created_at: datetime = Field(..., description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    finished_at: Optional[datetime] = Field(None, description="完成时间")
    duration: Optional[int] = Field(None, description="构建耗时(秒)")
    build_arch: List[str] = Field(..., description="构建架构")
    priority: int = Field(..., description="构建优先级")
    tags: List[str] = Field(..., description="构建标签")

class BuildArtifactResponse(BaseModel):
    """构建产物响应模型"""
    filename: str = Field(..., description="文件名")
    filepath: str = Field(..., description="文件路径")
    filesize: int = Field(..., description="文件大小(字节)")
    checksum: str = Field(..., description="文件校验和")
    architecture: str = Field(..., description="架构类型")
    created_at: datetime = Field(..., description="创建时间")

class BuildStatsResponse(BaseModel):
    """构建统计信息响应模型"""
    total_builds: int = Field(..., description="总构建数")
    successful_builds: int = Field(..., description="成功构建数")
    failed_builds: int = Field(..., description="失败构建数")
    running_builds: int = Field(..., description="运行中构建数")
    pending_builds: int = Field(..., description="等待中构建数")
    success_rate: float = Field(..., description="成功率")
    average_build_time: float = Field(..., description="平均构建时间(秒)")
    builds_by_status: Dict[str, int] = Field(..., description="按状态分组统计")
    builds_by_architecture: Dict[str, int] = Field(..., description="按架构分组统计")
    recent_builds: List[BuildResponse] = Field(..., description="最近构建列表")

class BatchBuildRequest(BaseModel):
    """批量构建请求模型"""
    builds: List[BuildCreateRequest] = Field(..., min_items=1, max_items=20, description="构建任务列表")
    parallel_limit: int = Field(3, ge=1, le=10, description="并行构建限制")
    wait_for_completion: bool = Field(False, description="是否等待全部完成")

def create_build_router() -> BaseRouter:
    """创建构建管理路由器"""
    build_router = BaseRouter("/api/v1/builds", ["构建管理"])

    # 注入构建服务依赖
    def get_build_service() -> BuildService:
        """获取构建服务实例"""
        return BuildService()

    @build_router.router.get("/",
                             summary="获取构建任务列表",
                             description="获取系统中的构建任务列表，支持分页和过滤",
                             response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    @RouteDecorators.rate_limit(requests_per_minute=100)
    async def list_builds(
            page: int = Query(1, ge=1, description="页码"),
            per_page: int = Query(20, ge=1, le=100, description="每页数量"),
            status: Optional[str] = Query(None, description="过滤状态: all, pending, running, success, failed"),
            package_name: Optional[str] = Query(None, description="按包名过滤"),
            build_type: Optional[str] = Query(None, description="按构建类型过滤"),
            architecture: Optional[str] = Query(None, description="按架构过滤"),
            tag: Optional[str] = Query(None, description="按标签过滤"),
            date_from: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
            date_to: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
            sort_by: str = Query("created_at", description="排序字段"),
            sort_order: str = Query("desc", description="排序方向: asc, desc"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """获取构建任务列表"""
        try:
            logger.info(f"Getting build list - page: {page}, per_page: {per_page}")

            # 构建过滤条件
            filters = {}
            if status and status != "all":
                filters["status"] = status
            if package_name:
                filters["package_name"] = package_name
            if build_type:
                filters["build_type"] = build_type
            if architecture:
                filters["architecture"] = architecture
            if tag:
                filters["tag"] = tag
            if date_from:
                filters["date_from"] = date_from
            if date_to:
                filters["date_to"] = date_to

            # 构建排序参数
            sort_params = {
                "field": sort_by,
                "order": sort_order
            }

            # 获取构建任务列表
            builds, total = await build_service.list_builds(
                page=page,
                per_page=per_page,
                filters=filters,
                sort=sort_params
            )

            # 转换为响应格式
            build_responses = []
            for build in builds:
                build_responses.append(BuildResponse(
                    id=build.id,
                    name=build.name,
                    package_name=build.package_name,
                    package_version=build.package_version,
                    build_type=build.build_type.value,
                    status=build.status.value,
                    progress=build.progress,
                    created_at=build.created_at,
                    started_at=build.started_at,
                    finished_at=build.finished_at,
                    duration=build.duration,
                    build_arch=build.build_arch,
                    priority=build.priority,
                    tags=build.tags
                ).dict())

            return create_paginated_response(
                items=build_responses,
                total=total,
                page=page,
                per_page=per_page,
                message="构建任务列表获取成功"
            )

        except Exception as e:
            logger.error(f"Failed to list builds: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取构建任务列表失败"
            )

    @build_router.router.post("/",
                              summary="创建构建任务",
                              description="创建新的RPM包构建任务",
                              response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["build:create"])
    @RouteDecorators.rate_limit(requests_per_minute=30)
    async def create_build(
            request: BuildCreateRequest,
            auto_start: bool = Query(False, description="是否自动启动构建"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """创建构建任务"""
        try:
            logger.info(f"Creating build task: {request.name}")

            # 检查构建任务名称是否已存在
            if await build_service.build_exists(request.name):
                raise HTTPException(
                    status_code=APIStatus.CONFLICT,
                    detail=f"构建任务名称 '{request.name}' 已存在"
                )

            # 构建配置对象
            build_config = BuildConfig(
                name=request.name,
                package_name=request.package_name,
                package_version=request.package_version,
                build_type=BuildType(request.build_type),
                source_type=request.source_type,
                source_url=request.source_url,
                git_branch=request.git_branch,
                git_commit=request.git_commit,
                build_arch=request.build_arch,
                build_environment=request.build_environment,
                build_dependencies=request.build_dependencies,
                mock_config=request.mock_config,
                priority=request.priority,
                timeout_minutes=request.timeout_minutes,
                enable_tests=request.enable_tests,
                clean_build=request.clean_build,
                tags=request.tags
            )

            # 创建构建任务
            build = await build_service.create_build(build_config)

            # 如果需要自动启动
            if auto_start:
                await build_service.start_build(build.id)
                build = await build_service.get_build(build.id)

            response_data = BuildResponse(
                id=build.id,
                name=build.name,
                package_name=build.package_name,
                package_version=build.package_version,
                build_type=build.build_type.value,
                status=build.status.value,
                progress=build.progress,
                created_at=build.created_at,
                started_at=build.started_at,
                finished_at=build.finished_at,
                duration=build.duration,
                build_arch=build.build_arch,
                priority=build.priority,
                tags=build.tags
            ).dict()

            return create_success_response(
                data=response_data,
                message=f"构建任务 '{request.name}' 创建成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create build: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail=f"创建构建任务失败: {str(e)}"
            )

    @build_router.router.post("/upload",
                              summary="上传源码文件创建构建任务",
                              description="通过上传源码文件创建构建任务",
                              response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["build:create"])
    @RouteDecorators.rate_limit(requests_per_minute=10)
    async def create_build_with_upload(
            file: UploadFile = File(..., description="源码文件 (.tar.gz, .spec等)"),
            name: str = Form(..., description="构建任务名称"),
            package_name: str = Form(..., description="RPM包名称"),
            package_version: str = Form(..., description="包版本号"),
            build_type: str = Form("rpm", description="构建类型"),
            build_arch: str = Form("x86_64", description="构建架构，多个用逗号分隔"),
            priority: int = Form(5, description="构建优先级"),
            auto_start: bool = Form(False, description="是否自动启动构建"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """通过上传文件创建构建任务"""
        try:
            logger.info(f"Creating build with uploaded file: {file.filename}")

            # 验证文件类型
            allowed_extensions = ['.tar.gz', '.tgz', '.tar', '.spec', '.zip']
            file_ext = ''.join(Path(file.filename).suffixes)
            if not any(file.filename.endswith(ext) for ext in allowed_extensions):
                raise HTTPException(
                    status_code=APIStatus.BAD_REQUEST,
                    detail=f"不支持的文件类型，支持的格式: {', '.join(allowed_extensions)}"
                )

            # 保存上传的文件
            uploaded_file_path = await build_service.save_uploaded_file(file)

            # 创建构建配置
            build_config = BuildConfig(
                name=name,
                package_name=package_name,
                package_version=package_version,
                build_type=BuildType(build_type),
                source_type="upload",
                source_url=uploaded_file_path,
                build_arch=build_arch.split(','),
                priority=priority,
                tags=["uploaded"]
            )

            # 创建构建任务
            build = await build_service.create_build(build_config)

            # 如果需要自动启动
            if auto_start:
                await build_service.start_build(build.id)
                build = await build_service.get_build(build.id)

            response_data = BuildResponse(
                id=build.id,
                name=build.name,
                package_name=build.package_name,
                package_version=build.package_version,
                build_type=build.build_type.value,
                status=build.status.value,
                progress=build.progress,
                created_at=build.created_at,
                started_at=build.started_at,
                finished_at=build.finished_at,
                duration=build.duration,
                build_arch=build.build_arch,
                priority=build.priority,
                tags=build.tags
            ).dict()

            return create_success_response(
                data=response_data,
                message=f"构建任务 '{name}' 创建成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create build with upload: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail=f"上传文件创建构建任务失败: {str(e)}"
            )

    @build_router.router.get("/{build_id}",
                             summary="获取构建任务详情",
                             description="获取指定构建任务的详细信息",
                             response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_build(
            build_id: str = Path(..., description="构建任务ID"),
            include_logs: bool = Query(False, description="是否包含构建日志"),
            include_artifacts: bool = Query(False, description="是否包含构建产物信息"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """获取构建任务详情"""
        try:
            logger.info(f"Getting build details: {build_id}")

            # 获取构建任务信息
            build = await build_service.get_build(build_id)
            if not build:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"构建任务 '{build_id}' 不存在"
                )

            # 构建响应数据
            response_data = BuildResponse(
                id=build.id,
                name=build.name,
                package_name=build.package_name,
                package_version=build.package_version,
                build_type=build.build_type.value,
                status=build.status.value,
                progress=build.progress,
                created_at=build.created_at,
                started_at=build.started_at,
                finished_at=build.finished_at,
                duration=build.duration,
                build_arch=build.build_arch,
                priority=build.priority,
                tags=build.tags
            ).dict()

            # 添加详细信息
            response_data.update({
                "source_type": build.source_type,
                "source_url": build.source_url,
                "git_branch": build.git_branch,
                "git_commit": build.git_commit,
                "build_environment": build.build_environment,
                "build_dependencies": build.build_dependencies,
                "mock_config": build.mock_config,
                "timeout_minutes": build.timeout_minutes,
                "enable_tests": build.enable_tests,
                "clean_build": build.clean_build
            })

            # 如果需要包含构建日志
            if include_logs:
                try:
                    logs = await build_service.get_build_logs(build_id)
                    response_data["logs"] = logs
                except Exception as e:
                    logger.warning(f"Failed to get logs for build {build_id}: {e}")
                    response_data["logs"] = None

            # 如果需要包含构建产物信息
            if include_artifacts:
                try:
                    artifacts = await build_service.get_build_artifacts(build_id)
                    artifact_responses = []
                    for artifact in artifacts:
                        artifact_responses.append(BuildArtifactResponse(
                            filename=artifact.filename,
                            filepath=artifact.filepath,
                            filesize=artifact.filesize,
                            checksum=artifact.checksum,
                            architecture=artifact.architecture,
                            created_at=artifact.created_at
                        ).dict())
                    response_data["artifacts"] = artifact_responses
                except Exception as e:
                    logger.warning(f"Failed to get artifacts for build {build_id}: {e}")
                    response_data["artifacts"] = []

            return create_success_response(
                data=response_data,
                message="构建任务详情获取成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get build {build_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取构建任务详情失败"
            )

    @build_router.router.put("/{build_id}",
                             summary="更新构建任务配置",
                             description="更新构建任务的可修改配置项",
                             response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["build:update"])
    async def update_build(
            build_id: str = Path(..., description="构建任务ID"),
            request: BuildUpdateRequest = Body(...),
            build_service: BuildService = Depends(get_build_service)
    ):
        """更新构建任务配置"""
        try:
            logger.info(f"Updating build: {build_id}")

            # 检查构建任务是否存在
            build = await build_service.get_build(build_id)
            if not build:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"构建任务 '{build_id}' 不存在"
                )

            # 检查是否可以更新（只有pending状态的任务可以更新）
            if build.status not in [BuildStatus.PENDING, BuildStatus.FAILED, BuildStatus.CANCELLED]:
                raise HTTPException(
                    status_code=APIStatus.BAD_REQUEST,
                    detail="只能更新待执行、失败或已取消的构建任务"
                )

            # 更新构建任务配置
            update_data = request.dict(exclude_unset=True)
            updated_build = await build_service.update_build(build_id, update_data)

            response_data = BuildResponse(
                id=updated_build.id,
                name=updated_build.name,
                package_name=updated_build.package_name,
                package_version=updated_build.package_version,
                build_type=updated_build.build_type.value,
                status=updated_build.status.value,
                progress=updated_build.progress,
                created_at=updated_build.created_at,
                started_at=updated_build.started_at,
                finished_at=updated_build.finished_at,
                duration=updated_build.duration,
                build_arch=updated_build.build_arch,
                priority=updated_build.priority,
                tags=updated_build.tags
            ).dict()

            return create_success_response(
                data=response_data,
                message="构建任务配置更新成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update build {build_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="更新构建任务配置失败"
            )

    @build_router.router.delete("/{build_id}",
                                summary="删除构建任务",
                                description="删除指定的构建任务及其相关文件",
                                response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["build:delete"])
    async def delete_build(
            build_id: str = Path(..., description="构建任务ID"),
            force: bool = Query(False, description="是否强制删除（即使正在构建）"),
            remove_artifacts: bool = Query(True, description="是否删除构建产物"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """删除构建任务"""
        try:
            logger.info(f"Deleting build: {build_id}")

            # 检查构建任务是否存在
            build = await build_service.get_build(build_id)
            if not build:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"构建任务 '{build_id}' 不存在"
                )

            # 如果构建正在运行且未强制删除，先取消构建
            if build.status == BuildStatus.RUNNING and not force:
                await build_service.cancel_build(build_id)

            # 删除构建任务
            await build_service.delete_build(
                build_id,
                force=force,
                remove_artifacts=remove_artifacts
            )

            return create_success_response(
                message=f"构建任务 '{build.name}' 删除成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete build {build_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="删除构建任务失败"
            )

    @build_router.router.post("/{build_id}/start",
                              summary="启动构建任务",
                              description="启动指定的构建任务",
                              response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["build:control"])
    async def start_build(
            build_id: str = Path(..., description="构建任务ID"),
            force_rebuild: bool = Query(False, description="是否强制重新构建"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """启动构建任务"""
        try:
            logger.info(f"Starting build: {build_id}")

            # 检查构建任务是否存在
            build = await build_service.get_build(build_id)
            if not build:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"构建任务 '{build_id}' 不存在"
                )

            # 检查构建状态
            if build.status == BuildStatus.RUNNING:
                return create_success_response(
                    message=f"构建任务 '{build.name}' 已经在运行中"
                )

            if build.status == BuildStatus.SUCCESS and not force_rebuild:
                return create_success_response(
                    message=f"构建任务 '{build.name}' 已经成功完成，使用 force_rebuild=true 强制重新构建"
                )

            # 启动构建任务
            await build_service.start_build(build_id, force_rebuild=force_rebuild)

            # 获取更新后的构建信息
            updated_build = await build_service.get_build(build_id)

            response_data = BuildResponse(
                id=updated_build.id,
                name=updated_build.name,
                package_name=updated_build.package_name,
                package_version=updated_build.package_version,
                build_type=updated_build.build_type.value,
                status=updated_build.status.value,
                progress=updated_build.progress,
                created_at=updated_build.created_at,
                started_at=updated_build.started_at,
                finished_at=updated_build.finished_at,
                duration=updated_build.duration,
                build_arch=updated_build.build_arch,
                priority=updated_build.priority,
                tags=updated_build.tags
            ).dict()

            return create_success_response(
                data=response_data,
                message=f"构建任务 '{build.name}' 启动成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to start build {build_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="启动构建任务失败"
            )

    @build_router.router.post("/{build_id}/cancel",
                              summary="取消构建任务",
                              description="取消正在运行的构建任务",
                              response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["build:control"])
    async def cancel_build(
            build_id: str = Path(..., description="构建任务ID"),
            reason: str = Query("用户取消", description="取消原因"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """取消构建任务"""
        try:
            logger.info(f"Cancelling build: {build_id}")

            # 检查构建任务是否存在
            build = await build_service.get_build(build_id)
            if not build:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"构建任务 '{build_id}' 不存在"
                )

            # 检查构建状态
            if build.status not in [BuildStatus.PENDING, BuildStatus.RUNNING]:
                return create_success_response(
                    message=f"构建任务 '{build.name}' 不在可取消状态"
                )

            # 取消构建任务
            await build_service.cancel_build(build_id, reason=reason)

            # 获取更新后的构建信息
            updated_build = await build_service.get_build(build_id)

            response_data = BuildResponse(
                id=updated_build.id,
                name=updated_build.name,
                package_name=updated_build.package_name,
                package_version=updated_build.package_version,
                build_type=updated_build.build_type.value,
                status=updated_build.status.value,
                progress=updated_build.progress,
                created_at=updated_build.created_at,
                started_at=updated_build.started_at,
                finished_at=updated_build.finished_at,
                duration=updated_build.duration,
                build_arch=updated_build.build_arch,
                priority=updated_build.priority,
                tags=updated_build.tags
            ).dict()

            return create_success_response(
                data=response_data,
                message=f"构建任务 '{build.name}' 取消成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel build {build_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="取消构建任务失败"
            )

    @build_router.router.get("/{build_id}/logs",
                             summary="获取构建日志",
                             description="获取构建任务的日志输出",
                             response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_build_logs(
            build_id: str = Path(..., description="构建任务ID"),
            lines: int = Query(500, ge=1, le=10000, description="日志行数"),
            follow: bool = Query(False, description="是否持续跟踪日志"),
            level: Optional[str] = Query(None, description="日志级别过滤: debug, info, warning, error"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """获取构建日志"""
        try:
            logger.info(f"Getting logs for build: {build_id}")

            # 检查构建任务是否存在
            build = await build_service.get_build(build_id)
            if not build:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"构建任务 '{build_id}' 不存在"
                )

            # 如果是跟踪模式，返回流式响应
            if follow:
                async def log_generator():
                    async for log_line in build_service.follow_build_logs(
                            build_id, level=level
                    ):
                        yield f"data: {log_line}\n\n"

                return StreamingResponse(
                    log_generator(),
                    media_type="text/plain",
                    headers={"Cache-Control": "no-cache"}
                )

            # 获取日志内容
            logs = await build_service.get_build_logs(build_id, lines=lines, level=level)

            return create_success_response(
                data={
                    "build_id": build.id,
                    "build_name": build.name,
                    "logs": logs,
                    "lines_count": len(logs.split('\n')) if logs else 0,
                    "level_filter": level
                },
                message="构建日志获取成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get logs for build {build_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取构建日志失败"
            )

    @build_router.router.get("/{build_id}/artifacts",
                             summary="获取构建产物列表",
                             description="获取构建任务的产物文件列表",
                             response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_build_artifacts(
            build_id: str = Path(..., description="构建任务ID"),
            architecture: Optional[str] = Query(None, description="按架构过滤"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """获取构建产物列表"""
        try:
            logger.info(f"Getting artifacts for build: {build_id}")

            # 检查构建任务是否存在
            build = await build_service.get_build(build_id)
            if not build:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"构建任务 '{build_id}' 不存在"
                )

            # 获取构建产物
            artifacts = await build_service.get_build_artifacts(build_id, architecture=architecture)

            # 转换为响应格式
            artifact_responses = []
            for artifact in artifacts:
                artifact_responses.append(BuildArtifactResponse(
                    filename=artifact.filename,
                    filepath=artifact.filepath,
                    filesize=artifact.filesize,
                    checksum=artifact.checksum,
                    architecture=artifact.architecture,
                    created_at=artifact.created_at
                ).dict())

            return create_success_response(
                data={
                    "build_id": build.id,
                    "build_name": build.name,
                    "artifacts": artifact_responses,
                    "total_count": len(artifact_responses),
                    "total_size": sum(a.filesize for a in artifacts),
                    "architecture_filter": architecture
                },
                message="构建产物列表获取成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get artifacts for build {build_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取构建产物列表失败"
            )

    @build_router.router.get("/{build_id}/download",
                             summary="下载构建结果",
                             description="下载构建任务的结果文件")
    @RouteDecorators.require_auth()
    async def download_build_result(
            build_id: str = Path(..., description="构建任务ID"),
            filename: Optional[str] = Query(None, description="指定下载的文件名"),
            format: str = Query("tar.gz", description="下载格式: tar.gz, zip"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """下载构建结果"""
        try:
            logger.info(f"Downloading build result: {build_id}")

            # 检查构建任务是否存在
            build = await build_service.get_build(build_id)
            if not build:
                raise HTTPException(
                    status_code=APIStatus.NOT_FOUND,
                    detail=f"构建任务 '{build_id}' 不存在"
                )

            # 检查构建是否成功完成
            if build.status != BuildStatus.SUCCESS:
                raise HTTPException(
                    status_code=APIStatus.BAD_REQUEST,
                    detail="只能下载成功完成的构建结果"
                )

            # 如果指定了文件名，下载单个文件
            if filename:
                file_path = await build_service.get_artifact_file_path(build_id, filename)
                if not file_path or not os.path.exists(file_path):
                    raise HTTPException(
                        status_code=APIStatus.NOT_FOUND,
                        detail=f"文件 '{filename}' 不存在"
                    )

                return FileResponse(
                    path=file_path,
                    filename=filename,
                    media_type='application/octet-stream'
                )

            # 下载打包的构建结果
            archive_path = await build_service.create_build_archive(build_id, format=format)

            archive_filename = f"{build.package_name}-{build.package_version}-{build_id}.{format}"

            return FileResponse(
                path=archive_path,
                filename=archive_filename,
                media_type='application/octet-stream'
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to download build result {build_id}: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="下载构建结果失败"
            )

    @build_router.router.post("/batch",
                              summary="批量构建任务",
                              description="创建并执行多个构建任务",
                              response_model=Dict[str, Any])
    @RouteDecorators.require_auth(required_permissions=["build:batch"])
    @RouteDecorators.rate_limit(requests_per_minute=5)
    async def batch_build(
            request: BatchBuildRequest,
            build_service: BuildService = Depends(get_build_service)
    ):
        """批量构建任务"""
        try:
            logger.info(f"Batch build: {len(request.builds)} tasks")

            # 执行批量构建
            results = await build_service.batch_build(
                builds=request.builds,
                parallel_limit=request.parallel_limit,
                wait_for_completion=request.wait_for_completion
            )

            # 统计结果
            created_count = len([r for r in results if r["success"]])
            failed_count = len([r for r in results if not r["success"]])

            return create_success_response(
                data={
                    "total_builds": len(request.builds),
                    "created_count": created_count,
                    "failed_count": failed_count,
                    "parallel_limit": request.parallel_limit,
                    "results": results
                },
                message=f"批量构建完成: {created_count}个成功创建, {failed_count}个失败"
            )

        except Exception as e:
            logger.error(f"Batch build failed: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="批量构建失败"
            )

    @build_router.router.get("/stats",
                             summary="获取构建统计信息",
                             description="获取系统构建任务的统计信息",
                             response_model=Dict[str, Any])
    @RouteDecorators.require_auth()
    async def get_build_stats(
            days: int = Query(30, ge=1, le=365, description="统计天数"),
            build_service: BuildService = Depends(get_build_service)
    ):
        """获取构建统计信息"""
        try:
            logger.info(f"Getting build stats for {days} days")

            # 获取统计信息
            stats = await build_service.get_build_stats(days=days)

            # 获取最近构建列表
            recent_builds, _ = await build_service.list_builds(
                page=1, per_page=10, sort={"field": "created_at", "order": "desc"}
            )

            # 转换最近构建为响应格式
            recent_build_responses = []
            for build in recent_builds:
                recent_build_responses.append(BuildResponse(
                    id=build.id,
                    name=build.name,
                    package_name=build.package_name,
                    package_version=build.package_version,
                    build_type=build.build_type.value,
                    status=build.status.value,
                    progress=build.progress,
                    created_at=build.created_at,
                    started_at=build.started_at,
                    finished_at=build.finished_at,
                    duration=build.duration,
                    build_arch=build.build_arch,
                    priority=build.priority,
                    tags=build.tags
                ).dict())

            stats_response = BuildStatsResponse(
                total_builds=stats.total_builds,
                successful_builds=stats.successful_builds,
                failed_builds=stats.failed_builds,
                running_builds=stats.running_builds,
                pending_builds=stats.pending_builds,
                success_rate=stats.success_rate,
                average_build_time=stats.average_build_time,
                builds_by_status=stats.builds_by_status,
                builds_by_architecture=stats.builds_by_architecture,
                recent_builds=recent_build_responses
            )

            return create_success_response(
                data=stats_response.dict(),
                message="构建统计信息获取成功"
            )

        except Exception as e:
            logger.error(f"Failed to get build stats: {e}")
            raise HTTPException(
                status_code=APIStatus.INTERNAL_SERVER_ERROR,
                detail="获取构建统计信息失败"
            )

    return build_router

# 导出路由创建函数
__all__ = [
    "create_build_router",
    "BuildCreateRequest",
    "BuildUpdateRequest",
    "BuildResponse",
    "BuildArtifactResponse",
    "BuildStatsResponse",
    "BatchBuildRequest"
]