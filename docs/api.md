# EulerMaker Docker 优化器 - API 文档

## 目录

- [概述](#概述)
- [认证](#认证)
- [容器 API](#容器-api)
- [构建 API](#构建-api)
- [终端 API](#终端-api)
- [探针 API](#探针-api)
- [系统 API](#系统-api)
- [WebSocket API](#websocket-api)
- [错误处理](#错误处理)
- [API 限流](#api-限流)

## 概述

### 基础信息

- **Base URL**: `http://localhost:8080/api/v1`
- **协议**: HTTP/HTTPS
- **数据格式**: JSON
- **认证方式**: JWT Token
- **API 版本**: v1

### 通用响应格式

#### 成功响应

```json
{
    "success": true,
    "data": {
        // 具体数据
    },
    "message": "操作成功",
    "timestamp": "2025-08-01T12:00:00Z"
}
```

#### 错误响应

```json
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "错误描述",
        "details": {}
    },
    "timestamp": "2025-08-01T12:00:00Z"
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 201 | 资源创建成功 |
| 204 | 请求成功，无返回内容 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |

## 认证

### 获取 Token

**请求**

```http
POST /api/v1/auth/login
Content-Type: application/json

{
    "username": "admin",
    "password": "password123"
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "expires_in": 3600,
        "token_type": "Bearer"
    }
}
```

### 使用 Token

在请求头中添加：

```http
Authorization: Bearer <token>
```

### 刷新 Token

**请求**

```http
POST /api/v1/auth/refresh
Authorization: Bearer <old_token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "token": "new_token_here",
        "expires_in": 3600
    }
}
```

## 容器 API

### 创建容器

**请求**

```http
POST /api/v1/containers
Content-Type: application/json
Authorization: Bearer <token>

{
    "name": "my-container",
    "image": "centos:7",
    "command": ["bash"],
    "environment": {
        "ENV_VAR": "value"
    },
    "volumes": {
        "/host/path": "/container/path"
    },
    "ports": {
        "80/tcp": 8080
    },
    "memory_limit": "1g",
    "cpu_limit": "1.0",
    "working_dir": "/app",
    "user": "1000:1000",
    "network_mode": "bridge",
    "restart_policy": "unless-stopped",
    "labels": {
        "project": "test"
    }
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "container_123456",
        "name": "my-container",
        "image": "centos:7",
        "status": "created",
        "created_at": "2025-08-01T12:00:00Z",
        "config": {
            "command": ["bash"],
            "environment": {
                "ENV_VAR": "value"
            },
            "volumes": {
                "/host/path": "/container/path"
            },
            "ports": {
                "80/tcp": 8080
            },
            "memory_limit": "1g",
            "cpu_limit": "1.0"
        }
    },
    "message": "容器创建成功"
}
```

### 列出容器

**请求**

```http
GET /api/v1/containers?status=running&limit=10&offset=0
Authorization: Bearer <token>
```

**参数说明**

| 参数 | 类型 | 可选 | 默认值 | 说明 |
|------|------|------|--------|------|
| status | string | 是 | all | 容器状态过滤(running, stopped, created, all) |
| limit | integer | 是 | 20 | 每页数量 |
| offset | integer | 是 | 0 | 偏移量 |
| name | string | 是 | - | 按名称过滤 |
| image | string | 是 | - | 按镜像过滤 |

**响应**

```json
{
    "success": true,
    "data": {
        "containers": [
            {
                "id": "container_123456",
                "name": "my-container",
                "image": "centos:7",
                "status": "running",
                "created_at": "2025-08-01T12:00:00Z",
                "started_at": "2025-08-01T12:01:00Z",
                "ports": ["8080:80/tcp"],
                "labels": {
                    "project": "test"
                }
            }
        ],
        "total": 1,
        "limit": 10,
        "offset": 0
    }
}
```

### 获取容器详情

**请求**

```http
GET /api/v1/containers/{id}
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "container_123456",
        "name": "my-container",
        "image": "centos:7",
        "status": "running",
        "created_at": "2025-08-01T12:00:00Z",
        "started_at": "2025-08-01T12:01:00Z",
        "config": {
            "command": ["bash"],
            "environment": {"ENV_VAR": "value"},
            "volumes": {"/host/path": "/container/path"},
            "ports": {"80/tcp": 8080},
            "memory_limit": "1g",
            "cpu_limit": "1.0"
        },
        "state": {
            "status": "running",
            "running": true,
            "paused": false,
            "restarting": false,
            "exit_code": 0,
            "error": ""
        },
        "network": {
            "ip_address": "172.17.0.2",
            "ports": {
                "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]
            }
        }
    }
}
```

### 启动容器

**请求**

```http
POST /api/v1/containers/{id}/start
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "container_123456",
        "status": "running",
        "started_at": "2025-08-01T12:01:00Z"
    },
    "message": "容器启动成功"
}
```

### 停止容器

**请求**

```http
POST /api/v1/containers/{id}/stop
Content-Type: application/json
Authorization: Bearer <token>

{
    "timeout": 10
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "container_123456",
        "status": "stopped",
        "stopped_at": "2025-08-01T12:05:00Z"
    },
    "message": "容器停止成功"
}
```

### 重启容器

**请求**

```http
POST /api/v1/containers/{id}/restart
Content-Type: application/json
Authorization: Bearer <token>

{
    "timeout": 10
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "container_123456",
        "status": "running",
        "restarted_at": "2025-08-01T12:06:00Z"
    },
    "message": "容器重启成功"
}
```

### 暂停/恢复容器

**暂停容器**

```http
POST /api/v1/containers/{id}/pause
Authorization: Bearer <token>
```

**恢复容器**

```http
POST /api/v1/containers/{id}/unpause
Authorization: Bearer <token>
```

### 删除容器

**请求**

```http
DELETE /api/v1/containers/{id}?force=true
Authorization: Bearer <token>
```

**参数说明**

| 参数 | 类型 | 可选 | 默认值 | 说明 |
|------|------|------|--------|------|
| force | boolean | 是 | false | 强制删除运行中的容器 |

**响应**

```json
{
    "success": true,
    "message": "容器删除成功"
}
```

### 获取容器日志

**请求**

```http
GET /api/v1/containers/{id}/logs?tail=100&follow=false&timestamps=true
Authorization: Bearer <token>
```

**参数说明**

| 参数 | 类型 | 可选 | 默认值 | 说明 |
|------|------|------|--------|------|
| tail | integer | 是 | 100 | 显示最后N行 |
| follow | boolean | 是 | false | 是否跟踪日志 |
| timestamps | boolean | 是 | false | 是否显示时间戳 |
| since | string | 是 | - | 从某个时间开始(RFC3339格式) |
| until | string | 是 | - | 到某个时间结束(RFC3339格式) |

**响应**

```json
{
    "success": true,
    "data": {
        "logs": [
            "2025-08-01T12:00:00Z [INFO] Container started",
            "2025-08-01T12:00:01Z [INFO] Application initialized"
        ]
    }
}
```

### 获取容器统计信息

**请求**

```http
GET /api/v1/containers/{id}/stats?stream=false
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "cpu_usage": {
            "total_usage": 1234567890,
            "usage_percent": 15.5
        },
        "memory_usage": {
            "usage": 134217728,
            "limit": 1073741824,
            "usage_percent": 12.5
        },
        "network_io": {
            "rx_bytes": 1024,
            "tx_bytes": 2048
        },
        "block_io": {
            "read_bytes": 4096,
            "write_bytes": 8192
        },
        "timestamp": "2025-08-01T12:00:00Z"
    }
}
```

### 在容器中执行命令

**请求**

```http
POST /api/v1/containers/{id}/exec
Content-Type: application/json
Authorization: Bearer <token>

{
    "command": ["ls", "-la"],
    "working_dir": "/app",
    "user": "root",
    "environment": {
        "TERM": "xterm"
    },
    "attach_stdout": true,
    "attach_stderr": true,
    "tty": false
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "exec_id": "exec_123456",
        "output": "total 8\ndrwxr-xr-x 2 root root 4096 Jan  1 12:00 .\n",
        "exit_code": 0
    }
}
```

## 构建 API

### 创建构建任务

**请求**

```http
POST /api/v1/builds
Content-Type: application/json
Authorization: Bearer <token>

{
    "name": "my-rpm-build",
    "dockerfile_content": "FROM centos:7\nRUN yum install -y rpm-build\nCOPY package.spec /root/rpmbuild/SPECS/\nRUN rpmbuild -ba /root/rpmbuild/SPECS/package.spec",
    "context_files": {
        "package.spec": "Name: my-package\nVersion: 1.0.0\n...",
        "source.tar.gz": "<base64_encoded_content>"
    },
    "build_args": {
        "VERSION": "1.0.0"
    },
    "labels": {
        "maintainer": "admin@example.com"
    },
    "target": "production",
    "cache_enabled": true,
    "cache_from": ["my-rpm-build:latest"]
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "build_123456",
        "name": "my-rpm-build",
        "status": "pending",
        "created_at": "2025-08-01T12:00:00Z",
        "dockerfile_path": "/tmp/build_123456/Dockerfile",
        "context_path": "/tmp/build_123456/context"
    },
    "message": "构建任务创建成功"
}
```

### 列出构建任务

**请求**

```http
GET /api/v1/builds?status=success&limit=10&offset=0
Authorization: Bearer <token>
```

**参数说明**

| 参数 | 类型 | 可选 | 默认值 | 说明 |
|------|------|------|--------|------|
| status | string | 是 | all | 构建状态(pending,running,success,failed,all) |
| limit | integer | 是 | 20 | 每页数量 |
| offset | integer | 是 | 0 | 偏移量 |
| name | string | 是 | - | 按名称过滤 |

**响应**

```json
{
    "success": true,
    "data": {
        "builds": [
            {
                "id": "build_123456",
                "name": "my-rpm-build",
                "status": "success",
                "created_at": "2025-08-01T12:00:00Z",
                "started_at": "2025-08-01T12:01:00Z",
                "finished_at": "2025-08-01T12:05:00Z",
                "image_id": "sha256:abcdef123456...",
                "image_tag": "my-rpm-build:latest"
            }
        ],
        "total": 1,
        "limit": 10,
        "offset": 0
    }
}
```

### 获取构建详情

**请求**

```http
GET /api/v1/builds/{id}
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "build_123456",
        "name": "my-rpm-build",
        "status": "success",
        "created_at": "2025-08-01T12:00:00Z",
        "started_at": "2025-08-01T12:01:00Z",
        "finished_at": "2025-08-01T12:05:00Z",
        "duration": 240,
        "dockerfile_content": "FROM centos:7\n...",
        "build_args": {"VERSION": "1.0.0"},
        "labels": {"maintainer": "admin@example.com"},
        "image": {
            "id": "sha256:abcdef123456...",
            "tag": "my-rpm-build:latest",
            "size": 524288000,
            "layers": 8
        },
        "artifacts": [
            {
                "name": "my-package-1.0.0-1.x86_64.rpm",
                "size": 1048576,
                "path": "/output/my-package-1.0.0-1.x86_64.rpm"
            }
        ]
    }
}
```

### 执行构建

**请求**

```http
POST /api/v1/builds/{id}/execute
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "build_123456",
        "status": "running",
        "started_at": "2025-08-01T12:01:00Z",
        "log_stream_url": "ws://localhost:8080/ws/builds/build_123456/logs"
    },
    "message": "构建开始执行"
}
```

### 获取构建日志

**请求**

```http
GET /api/v1/builds/{id}/logs?follow=false&tail=100
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "logs": [
            "Step 1/4 : FROM centos:7",
            " ---> 5e35e350aded",
            "Step 2/4 : RUN yum install -y rpm-build",
            " ---> Running in abc123def456",
            "Loaded plugins: fastestmirror, ovl"
        ]
    }
}
```

### 取消构建

**请求**

```http
POST /api/v1/builds/{id}/cancel
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "build_123456",
        "status": "cancelled",
        "cancelled_at": "2025-08-01T12:03:00Z"
    },
    "message": "构建已取消"
}
```

### 删除构建

**请求**

```http
DELETE /api/v1/builds/{id}?clean_image=true
Authorization: Bearer <token>
```

**参数说明**

| 参数 | 类型 | 可选 | 默认值 | 说明 |
|------|------|------|--------|------|
| clean_image | boolean | 是 | false | 是否同时删除构建产生的镜像 |

**响应**

```json
{
    "success": true,
    "message": "构建任务删除成功"
}
```

## 终端 API

### 创建终端会话

**请求**

```http
POST /api/v1/terminals
Content-Type: application/json
Authorization: Bearer <token>

{
    "container_id": "container_123456",
    "command": "/bin/bash",
    "user": "root",
    "working_dir": "/app",
    "environment": {
        "TERM": "xterm-256color",
        "SHELL": "/bin/bash"
    },
    "tty": true,
    "stdin": true
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "session_id": "terminal_session_123456",
        "container_id": "container_123456",
        "command": "/bin/bash",
        "status": "active",
        "created_at": "2025-08-01T12:00:00Z",
        "websocket_url": "ws://localhost:8080/ws/terminals/terminal_session_123456",
        "dimensions": {
            "cols": 80,
            "rows": 24
        }
    },
    "message": "终端会话创建成功"
}
```

### 列出终端会话

**请求**

```http
GET /api/v1/terminals?container_id=container_123456&status=active
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "sessions": [
            {
                "session_id": "terminal_session_123456",
                "container_id": "container_123456",
                "command": "/bin/bash",
                "status": "active",
                "created_at": "2025-08-01T12:00:00Z",
                "last_activity": "2025-08-01T12:05:00Z"
            }
        ],
        "total": 1
    }
}
```

### 获取终端会话详情

**请求**

```http
GET /api/v1/terminals/{session_id}
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "session_id": "terminal_session_123456",
        "container_id": "container_123456",
        "command": "/bin/bash",
        "status": "active",
        "created_at": "2025-08-01T12:00:00Z",
        "last_activity": "2025-08-01T12:05:00Z",
        "dimensions": {
            "cols": 80,
            "rows": 24
        },
        "environment": {
            "TERM": "xterm-256color",
            "SHELL": "/bin/bash"
        }
    }
}
```

### 调整终端尺寸

**请求**

```http
POST /api/v1/terminals/{session_id}/resize
Content-Type: application/json
Authorization: Bearer <token>

{
    "cols": 120,
    "rows": 30
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "session_id": "terminal_session_123456",
        "dimensions": {
            "cols": 120,
            "rows": 30
        }
    },
    "message": "终端尺寸调整成功"
}
```

### 关闭终端会话

**请求**

```http
DELETE /api/v1/terminals/{session_id}
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "message": "终端会话已关闭"
}
```

## 探针 API

### 添加探针

**请求**

```http
POST /api/v1/probes
Content-Type: application/json
Authorization: Bearer <token>

{
    "container_id": "container_123456",
    "probe_type": "http",
    "name": "health-check",
    "config": {
        "url": "http://localhost:8080/health",
        "method": "GET",
        "timeout": 5,
        "interval": 30,
        "retries": 3,
        "success_threshold": 1,
        "failure_threshold": 3,
        "headers": {
            "User-Agent": "EulerMaker-Probe"
        }
    },
    "enabled": true
}
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "probe_123456",
        "container_id": "container_123456",
        "probe_type": "http",
        "name": "health-check",
        "status": "active",
        "created_at": "2025-08-01T12:00:00Z",
        "config": {
            "url": "http://localhost:8080/health",
            "method": "GET",
            "timeout": 5,
            "interval": 30,
            "retries": 3
        }
    },
    "message": "探针添加成功"
}
```

### 探针类型

支持的探针类型：

1. **HTTP 探针**
   ```json
   {
       "probe_type": "http",
       "config": {
           "url": "http://localhost:8080/health",
           "method": "GET",
           "timeout": 5,
           "expected_status": 200
       }
   }
   ```

2. **TCP 探针**
   ```json
   {
       "probe_type": "tcp",
       "config": {
           "host": "localhost",
           "port": 3306,
           "timeout": 5
       }
   }
   ```

3. **命令执行探针**
   ```json
   {
       "probe_type": "exec",
       "config": {
           "command": ["cat", "/tmp/healthy"],
           "timeout": 10
       }
   }
   ```

4. **性能监控探针**
   ```json
   {
       "probe_type": "metrics",
       "config": {
           "metrics": ["cpu", "memory", "disk", "network"],
           "interval": 10
       }
   }
   ```

### 列出探针

**请求**

```http
GET /api/v1/probes?container_id=container_123456&probe_type=http
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "probes": [
            {
                "id": "probe_123456",
                "container_id": "container_123456",
                "probe_type": "http",
                "name": "health-check",
                "status": "active",
                "last_check": "2025-08-01T12:05:00Z",
                "last_result": "success"
            }
        ],
        "total": 1
    }
}
```

### 获取探针详情

**请求**

```http
GET /api/v1/probes/{id}
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "id": "probe_123456",
        "container_id": "container_123456",
        "probe_type": "http",
        "name": "health-check",
        "status": "active",
        "created_at": "2025-08-01T12:00:00Z",
        "last_check": "2025-08-01T12:05:00Z",
        "last_result": "success",
        "config": {
            "url": "http://localhost:8080/health",
            "method": "GET",
            "timeout": 5,
            "interval": 30
        },
        "statistics": {
            "total_checks": 100,
            "success_count": 98,
            "failure_count": 2,
            "success_rate": 98.0
        }
    }
}
```

### 获取探针结果

**请求**

```http
GET /api/v1/probes/{id}/results?limit=50&start_time=2025-08-01T00:00:00Z
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "results": [
            {
                "timestamp": "2025-08-01T12:05:00Z",
                "status": "success",
                "response_time": 45,
                "details": {
                    "status_code": 200,
                    "response_body": "OK"
                }
            },
            {
                "timestamp": "2025-08-01T12:04:30Z",
                "status": "failure",
                "response_time": 5000,
                "details": {
                    "error": "timeout"
                }
            }
        ],
        "total": 2
    }
}
```

### 更新探针

**请求**

```http
PUT /api/v1/probes/{id}
Content-Type: application/json
Authorization: Bearer <token>

{
    "name": "updated-health-check",
    "config": {
        "url": "http://localhost:8080/healthz",
        "interval": 60
    },
    "enabled": true
}
```

### 删除探针

**请求**

```http
DELETE /api/v1/probes/{id}
Authorization: Bearer <token>
```

## 系统 API

### 系统信息

**请求**

```http
GET /api/v1/system/info
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "version": "1.0.0",
        "docker_version": "20.10.17",
        "platform": "linux/amd64",
        "uptime": 86400,
        "containers": {
            "total": 10,
            "running": 8,
            "stopped": 2
        },
        "images": {
            "total": 15,
            "size": "2.5GB"
        },
        "builds": {
            "total": 25,
            "success": 23,
            "failed": 2
        }
    }
}
```

### 系统资源

**请求**

```http
GET /api/v1/system/resources
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "cpu": {
            "usage_percent": 15.5,
            "cores": 4
        },
        "memory": {
            "total": 8589934592,
            "used": 2147483648,
            "available": 6442450944,
            "usage_percent": 25.0
        },
        "disk": {
            "total": 107374182400,
            "used": 32212254720,
            "available": 75161927680,
            "usage_percent": 30.0
        },
        "network": {
            "rx_bytes": 1048576,
            "tx_bytes": 2097152
        }
    }
}
```

### 系统健康检查

**请求**

```http
GET /api/v1/system/health
```

**响应**

```json
{
    "success": true,
    "data": {
        "status": "healthy",
        "checks": {
            "docker": {
                "status": "healthy",
                "message": "Docker daemon is running"
            },
            "redis": {
                "status": "healthy",
                "message": "Redis connection successful"
            },
            "database": {
                "status": "healthy",
                "message": "PostgreSQL connection successful"
            }
        },
        "timestamp": "2025-08-01T12:00:00Z"
    }
}
```

### 系统配置

**请求**

```http
GET /api/v1/system/config
Authorization: Bearer <token>
```

**响应**

```json
{
    "success": true,
    "data": {
        "api": {
            "version": "v1",
            "rate_limit": {
                "enabled": true,
                "requests_per_minute": 100
            }
        },
        "docker": {
            "host": "unix:///var/run/docker.sock",
            "version": "1.41"
        },
        "build": {
            "max_concurrent": 3,
            "cache_enabled": true,
            "default_timeout": 1800
        }
    }
}
```

## WebSocket API

### 终端连接

**连接 URL**

```
ws://localhost:8080/ws/terminals/{session_id}
```

**消息格式**

```json
// 输入消息（客户端 -> 服务器）
{
    "type": "input",
    "data": "ls -la\n"
}

// 输出消息（服务器 -> 客户端）
{
    "type": "output",
    "data": "total 8\ndrwxr-xr-x 2 root root 4096 Jan  1 12:00 ."
}

// 控制消息
{
    "type": "resize",
    "data": {
        "cols": 120,
        "rows": 30
    }
}
```

### 构建日志流

**连接 URL**

```
ws://localhost:8080/ws/builds/{build_id}/logs
```

**消息格式**

```json
{
    "type": "log",
    "timestamp": "2025-08-01T12:00:00Z",
    "data": "Step 1/4 : FROM centos:7"
}
```

### 容器事件流

**连接 URL**

```
ws://localhost:8080/ws/containers/events
```

**消息格式**

```json
{
    "type": "container_event",
    "event": "start",
    "container_id": "container_123456",
    "timestamp": "2025-08-01T12:00:00Z",
    "details": {
        "name": "my-container",
        "image": "centos:7"
    }
}
```

### 探针通知

**连接 URL**

```
ws://localhost:8080/ws/probes/notifications
```

**消息格式**

```json
{
    "type": "probe_result",
    "probe_id": "probe_123456",
    "container_id": "container_123456",
    "status": "failure",
    "timestamp": "2025-08-01T12:00:00Z",
    "details": {
        "error": "Connection timeout"
    }
}
```

## 错误处理

### 错误码列表

| 错误码 | HTTP状态码 | 说明 |
|--------|------------|------|
| INVALID_REQUEST | 400 | 请求参数无效 |
| UNAUTHORIZED | 401 | 未授权访问 |
| FORBIDDEN | 403 | 权限不足 |
| RESOURCE_NOT_FOUND | 404 | 资源不存在 |
| RESOURCE_CONFLICT | 409 | 资源冲突 |
| RATE_LIMIT_EXCEEDED | 429 | 请求频率超限 |
| DOCKER_ERROR | 500 | Docker 操作错误 |
| BUILD_ERROR | 500 | 构建错误 |
| TERMINAL_ERROR | 500 | 终端操作错误 |
| INTERNAL_ERROR | 500 | 内部服务器错误 |

### 错误响应示例

```json
{
    "success": false,
    "error": {
        "code": "RESOURCE_NOT_FOUND",
        "message": "容器不存在",
        "details": {
            "container_id": "container_123456",
            "resource_type": "container"
        }
    },
    "timestamp": "2025-08-01T12:00:00Z",
    "trace_id": "abc123def456"
}
```

### 输入验证错误

```json
{
    "success": false,
    "error": {
        "code": "INVALID_REQUEST",
        "message": "请求参数验证失败",
        "details": {
            "field_errors": {
                "name": "容器名称不能为空",
                "image": "镜像名称格式无效",
                "memory_limit": "内存限制必须是正整数"
            }
        }
    },
    "timestamp": "2025-08-01T12:00:00Z"
}
```

## API 限流

### 限流规则

| API 类型 | 限制 | 时间窗口 |
|----------|------|----------|
| 认证相关 | 10 次/分钟 | 1 分钟 |
| 容器操作 | 100 次/分钟 | 1 分钟 |
| 构建操作 | 20 次/分钟 | 1 分钟 |
| 查询操作 | 200 次/分钟 | 1 分钟 |
| WebSocket | 50 连接/用户 | 持续 |

### 限流响应

```json
{
    "success": false,
    "error": {
        "code": "RATE_LIMIT_EXCEEDED",
        "message": "请求频率超过限制",
        "details": {
            "limit": 100,
            "remaining": 0,
            "reset_time": "2025-08-01T12:01:00Z"
        }
    },
    "timestamp": "2025-08-01T12:00:00Z"
}
```

### 限流头部信息

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 2025-08-01T12:01:00Z
```

---

**API 版本**: v1.0.0  
**最后更新**: 2025-09  
**维护者**: 张金荣