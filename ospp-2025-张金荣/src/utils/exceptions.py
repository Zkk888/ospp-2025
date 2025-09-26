"""
Eulermaker-docker-optimizer 的自定义异常


******OSPP-2025-张金荣******

定义在整个应用程序中使用的所有自定义异常。
所有异常都继承自一个基础的 EulerMakerError 类，以实现
统一的错误处理和日志记录。

"""

from typing import Optional, Dict, Any
import traceback


class EulerMakerError(Exception):
    """
    Base exception class for all eulermaker-docker-optimizer errors.

    Provides additional context and metadata for error handling.
    """

    def __init__(
            self,
            message: str,
            error_code: Optional[str] = None,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.cause = cause
        self.traceback_str = traceback.format_exc() if cause else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary format for serialization."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "traceback": self.traceback_str
        }

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class DockerError(EulerMakerError):
    """Docker相关错误"""

    def __init__(
            self,
            message: str,
            docker_error: Optional[Exception] = None,
            container_id: Optional[str] = None,
            image_name: Optional[str] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if container_id:
            details['container_id'] = container_id
        if image_name:
            details['image_name'] = image_name

        super().__init__(
            message=message,
            error_code="DOCKER_ERROR",
            details=details,
            cause=docker_error
        )


class ContainerError(DockerError):
    """容器操作相关错误"""

    def __init__(
            self,
            message: str,
            container_id: Optional[str] = None,
            container_name: Optional[str] = None,
            operation: Optional[str] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if container_name:
            details['container_name'] = container_name
        if operation:
            details['operation'] = operation

        super().__init__(
            message=message,
            container_id=container_id,
            error_code="CONTAINER_ERROR",
            details=details,
            **kwargs
        )


class ContainerNotFoundError(ContainerError):
    """容器未找到错误"""

    def __init__(self, container_id: str, **kwargs):
        super().__init__(
            message=f"Container not found: {container_id}",
            container_id=container_id,
            error_code="CONTAINER_NOT_FOUND",
            **kwargs
        )


class ContainerNotRunningError(ContainerError):
    """容器未运行错误"""

    def __init__(self, container_id: str, **kwargs):
        super().__init__(
            message=f"Container is not running: {container_id}",
            container_id=container_id,
            error_code="CONTAINER_NOT_RUNNING",
            **kwargs
        )


class ContainerAlreadyExistsError(ContainerError):
    """容器已存在错误"""

    def __init__(self, container_name: str, **kwargs):
        super().__init__(
            message=f"Container already exists: {container_name}",
            container_name=container_name,
            error_code="CONTAINER_ALREADY_EXISTS",
            **kwargs
        )


class ImageError(DockerError):
    """镜像相关错误"""

    def __init__(
            self,
            message: str,
            image_name: Optional[str] = None,
            image_tag: Optional[str] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if image_tag:
            details['image_tag'] = image_tag

        super().__init__(
            message=message,
            image_name=image_name,
            error_code="IMAGE_ERROR",
            details=details,
            **kwargs
        )


class ImageNotFoundError(ImageError):
    """镜像未找到错误"""

    def __init__(self, image_name: str, **kwargs):
        super().__init__(
            message=f"Image not found: {image_name}",
            image_name=image_name,
            error_code="IMAGE_NOT_FOUND",
            **kwargs
        )


class BuildError(EulerMakerError):
    """构建相关错误"""

    def __init__(
            self,
            message: str,
            build_id: Optional[str] = None,
            spec_file: Optional[str] = None,
            build_stage: Optional[str] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if build_id:
            details['build_id'] = build_id
        if spec_file:
            details['spec_file'] = spec_file
        if build_stage:
            details['build_stage'] = build_stage

        super().__init__(
            message=message,
            error_code="BUILD_ERROR",
            details=details,
            **kwargs
        )


class BuildTimeoutError(BuildError):
    """构建超时错误"""

    def __init__(self, build_id: str, timeout: int, **kwargs):
        super().__init__(
            message=f"Build timeout after {timeout} seconds",
            build_id=build_id,
            error_code="BUILD_TIMEOUT",
            details={"timeout": timeout},
            **kwargs
        )


class BuildDependencyError(BuildError):
    """构建依赖错误"""

    def __init__(
            self,
            message: str,
            missing_dependencies: Optional[list] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if missing_dependencies:
            details['missing_dependencies'] = missing_dependencies

        super().__init__(
            message=message,
            error_code="BUILD_DEPENDENCY_ERROR",
            details=details,
            **kwargs
        )


class ProbeError(EulerMakerError):
    """探针相关错误"""

    def __init__(
            self,
            message: str,
            probe_type: Optional[str] = None,
            target: Optional[str] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if probe_type:
            details['probe_type'] = probe_type
        if target:
            details['target'] = target

        super().__init__(
            message=message,
            error_code="PROBE_ERROR",
            details=details,
            **kwargs
        )


class ProbeTimeoutError(ProbeError):
    """探针超时错误"""

    def __init__(self, probe_type: str, timeout: int, **kwargs):
        super().__init__(
            message=f"Probe timeout: {probe_type} after {timeout} seconds",
            probe_type=probe_type,
            error_code="PROBE_TIMEOUT",
            details={"timeout": timeout},
            **kwargs
        )


class TerminalError(EulerMakerError):
    """终端相关错误"""

    def __init__(
            self,
            message: str,
            session_id: Optional[str] = None,
            terminal_type: Optional[str] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if session_id:
            details['session_id'] = session_id
        if terminal_type:
            details['terminal_type'] = terminal_type

        super().__init__(
            message=message,
            error_code="TERMINAL_ERROR",
            details=details,
            **kwargs
        )


class TerminalSessionNotFoundError(TerminalError):
    """终端会话未找到错误"""

    def __init__(self, session_id: str, **kwargs):
        super().__init__(
            message=f"Terminal session not found: {session_id}",
            session_id=session_id,
            error_code="TERMINAL_SESSION_NOT_FOUND",
            **kwargs
        )


class TerminalSessionLimitExceededError(TerminalError):
    """终端会话数量限制错误"""

    def __init__(self, max_sessions: int, **kwargs):
        super().__init__(
            message=f"Terminal session limit exceeded: {max_sessions}",
            error_code="TERMINAL_SESSION_LIMIT_EXCEEDED",
            details={"max_sessions": max_sessions},
            **kwargs
        )


class ValidationError(EulerMakerError):
    """验证相关错误"""

    def __init__(
            self,
            message: str,
            field: Optional[str] = None,
            value: Optional[Any] = None,
            expected: Optional[str] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if field:
            details['field'] = field
        if value is not None:
            details['value'] = str(value)
        if expected:
            details['expected'] = expected

        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details,
            **kwargs
        )


class ConfigurationError(EulerMakerError):
    """配置相关错误"""

    def __init__(
            self,
            message: str,
            config_key: Optional[str] = None,
            config_value: Optional[Any] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if config_key:
            details['config_key'] = config_key
        if config_value is not None:
            details['config_value'] = str(config_value)

        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details,
            **kwargs
        )


class APIError(EulerMakerError):
    """API相关错误"""

    def __init__(
            self,
            message: str,
            status_code: int = 500,
            endpoint: Optional[str] = None,
            method: Optional[str] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        details['status_code'] = status_code
        if endpoint:
            details['endpoint'] = endpoint
        if method:
            details['method'] = method

        super().__init__(
            message=message,
            error_code="API_ERROR",
            details=details,
            **kwargs
        )


class AuthenticationError(APIError):
    """认证错误"""

    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_ERROR",
            **kwargs
        )


class AuthorizationError(APIError):
    """授权错误"""

    def __init__(self, message: str = "Access denied", **kwargs):
        super().__init__(
            message=message,
            status_code=403,
            error_code="AUTHORIZATION_ERROR",
            **kwargs
        )


class RateLimitError(APIError):
    """限流错误"""

    def __init__(
            self,
            message: str = "Rate limit exceeded",
            retry_after: Optional[int] = None,
            **kwargs
    ):
        details = kwargs.get('details', {})
        if retry_after:
            details['retry_after'] = retry_after

        super().__init__(
            message=message,
            status_code=429,
            error_code="RATE_LIMIT_ERROR",
            details=details,
            **kwargs
        )


# 异常处理装饰器
def handle_exceptions(exception_type: type = EulerMakerError):
    """
    异常处理装饰器，用于统一处理异常

    Args:
        exception_type: 要捕获的异常类型
    """
    def decorator(func):
        if hasattr(func, '__call__') and hasattr(func, '__code__'):
            # 同步函数
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except exception_type:
                    raise
                except Exception as e:
                    raise EulerMakerError(
                        message=f"Unexpected error in {func.__name__}: {str(e)}",
                        cause=e
                    ) from e
            return wrapper
        else:
            # 异步函数
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except exception_type:
                    raise
                except Exception as e:
                    raise EulerMakerError(
                        message=f"Unexpected error in {func.__name__}: {str(e)}",
                        cause=e
                    ) from e
            return async_wrapper
    return decorator