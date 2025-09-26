"""
测试用示例配置数据

******OSPP-2025-张金荣******

包含各种测试场景所需的配置数据，涵盖：
- 不同环境的配置（开发、测试、生产）
- 各种容器配置场景
- 构建任务配置示例
- 探针配置组合
- 错误和边界情况配置
- 性能测试配置

版本: 1.0.0
作者: 张金荣
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
import os

# ====================================
# 基础配置模板
# ====================================
# 开发环境配置
DEV_CONFIG = {
    "DEBUG": True,
    "TESTING": False,
    "LOG_LEVEL": "DEBUG",
    "DATABASE_URL": "sqlite:///./data/dev.db",  # 修正：添加了键名
    "REDIS_URL": "redis://localhost:6379/0",
    "API_HOST": "0.0.0.0",
    "API_PORT": 8000,
    "RPC_PORT": 9000,
    "DOCKER_HOST": "unix:///var/run/docker.sock",
    "UPLOAD_PATH": "./uploads",
    "BUILD_PATH": "./builds",
    "LOG_PATH": "./logs",
    "CACHE_PATH": "./cache",
    "SECRET_KEY": "dev-secret-key-change-me",
    "ALLOWED_HOSTS": ["*"],
    "CORS_ORIGINS": ["http://localhost:3000", "http://127.0.0.1:3000"],
    "PROMETHEUS_ENABLED": True,
    "METRICS_PORT": 8001,
    "WORKER_PROCESSES": 1,
    "WORKER_THREADS": 4,
    "REQUEST_TIMEOUT": 30,
    "KEEPALIVE_TIMEOUT": 5,
}

# 测试环境配置
TEST_CONFIG = {
    **DEV_CONFIG,
    "TESTING": True,
    "DATABASE_URL": "sqlite:///:memory:",
    "REDIS_URL": "redis://localhost:6379/15",
    "API_PORT": 0,  # 随机端口
    "RPC_PORT": 0,
    "UPLOAD_PATH": "/tmp/test_uploads",
    "BUILD_PATH": "/tmp/test_builds",
    "LOG_PATH": "/tmp/test_logs",
    "CACHE_PATH": "/tmp/test_cache",
    "SECRET_KEY": "test-secret-key",
    "PROMETHEUS_ENABLED": False,
    "WORKER_PROCESSES": 1,
    "REQUEST_TIMEOUT": 5,
}

# 生产环境配置
PROD_CONFIG = {
    "DEBUG": False,
    "TESTING": False,
    "LOG_LEVEL": "INFO",
    "DATABASE_URL": "postgresql://user:pass@localhost/eulermaker",
    "REDIS_URL": "redis://redis:6379/0",
    "API_HOST": "0.0.0.0",
    "API_PORT": 80,
    "RPC_PORT": 9000,
    "DOCKER_HOST": "unix:///var/run/docker.sock",
    "UPLOAD_PATH": "/app/data/uploads",
    "BUILD_PATH": "/app/data/builds",
    "LOG_PATH": "/app/logs",
    "CACHE_PATH": "/app/cache",
    "SECRET_KEY": "${SECRET_KEY}",  # 从环境变量读取
    "ALLOWED_HOSTS": ["api.eulermaker.com", "*.eulermaker.com"],
    "CORS_ORIGINS": ["https://eulermaker.com"],
    "PROMETHEUS_ENABLED": True,
    "METRICS_PORT": 8001,
    "WORKER_PROCESSES": 4,
    "WORKER_THREADS": 8,
    "REQUEST_TIMEOUT": 60,
    "KEEPALIVE_TIMEOUT": 2,
    "SSL_ENABLED": True,
    "SSL_CERT_PATH": "/app/ssl/cert.pem",
    "SSL_KEY_PATH": "/app/ssl/key.pem",
}

# ====================================
# 容器配置示例
# ====================================

# 基础CentOS容器配置
CENTOS_CONTAINER_CONFIG = {
    "name": "centos-basic",
    "image": "centos:7",
    "command": ["bash"],
    "environment": {
        "LANG": "zh_CN.UTF-8",
        "TZ": "Asia/Shanghai"
    },
    "volumes": {
        "/host/workspace": "/workspace"
    },
    "working_dir": "/workspace",
    "user": "root",
    "tty": True,
    "stdin_open": True,
    "auto_remove": False,
    "restart_policy": {"Name": "no"},
}

# RPM构建容器配置
RPM_BUILD_CONTAINER_CONFIG = {
    "name": "rpm-builder",
    "image": "centos:7",
    "command": ["bash", "-c", """
        yum update -y && 
        yum install -y rpm-build make gcc gcc-c++ git wget tar gzip &&
        useradd -m builder &&
        su - builder
    """],
    "environment": {
        "LANG": "zh_CN.UTF-8",
        "BUILDER_UID": "1000",
        "BUILDER_GID": "1000"
    },
    "volumes": {
        "/host/rpmbuild": "/home/builder/rpmbuild",
        "/host/sources": "/home/builder/rpmbuild/SOURCES"
    },
    "working_dir": "/home/builder/rpmbuild",
    "user": "builder",
    "memory_limit": "2g",
    "cpu_limit": "2.0",
    "ulimits": [
        {"Name": "nofile", "Soft": 65536, "Hard": 65536}
    ],
    "labels": {
        "purpose": "rpm-build",
        "version": "1.0"
    }
}

# Web服务容器配置
WEB_SERVICE_CONTAINER_CONFIG = {
    "name": "web-service",
    "image": "nginx:alpine",
    "ports": {
        "80/tcp": 8080,
        "443/tcp": 8443
    },
    "volumes": {
        "/host/www": "/usr/share/nginx/html",
        "/host/nginx.conf": "/etc/nginx/nginx.conf"
    },
    "environment": {
        "NGINX_HOST": "localhost",
        "NGINX_PORT": "80"
    },
    "restart_policy": {"Name": "always"},
    "health_check": {
        "test": ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"],
        "interval": "30s",
        "timeout": "3s",
        "start_period": "5s",
        "retries": 3
    },
    "labels": {
        "traefik.enable": "true",
        "traefik.http.routers.web.rule": "Host(`example.com`)"
    }
}

# 数据库容器配置
DATABASE_CONTAINER_CONFIG = {
    "name": "postgres-db",
    "image": "postgres:13",
    "environment": {
        "POSTGRES_DB": "eulermaker",
        "POSTGRES_USER": "admin",
        "POSTGRES_PASSWORD": "secure-password-123",
        "PGDATA": "/var/lib/postgresql/data/pgdata"
    },
    "volumes": {
        "/host/pgdata": "/var/lib/postgresql/data/pgdata",
        "/host/backups": "/backups"
    },
    "ports": {
        "5432/tcp": 5432
    },
    "restart_policy": {"Name": "always"},
    "memory_limit": "1g",
    "shm_size": "256m",
    "ulimits": [
        {"Name": "memlock", "Soft": -1, "Hard": -1},
        {"Name": "nofile", "Soft": 65536, "Hard": 65536}
    ]
}

# ====================================
# 网络配置示例
# ====================================

# 自定义网络配置
CUSTOM_NETWORK_CONFIGS = {
    "bridge_network": {
        "name": "app-network",
        "driver": "bridge",
        "options": {
            "com.docker.network.bridge.name": "app-br0",
            "com.docker.network.driver.mtu": "1500"
        },
        "ipam": {
            "driver": "default",
            "config": [
                {
                    "subnet": "172.20.0.0/16",
                    "gateway": "172.20.0.1"
                }
            ]
        },
        "labels": {
            "project": "eulermaker",
            "environment": "development"
        }
    },
    "overlay_network": {
        "name": "cluster-network",
        "driver": "overlay",
        "options": {
            "encrypted": "true"
        },
        "attachable": True,
        "labels": {
            "project": "eulermaker",
            "type": "cluster"
        }
    }
}

# ====================================
# 构建配置示例
# ====================================

# 简单C程序构建
SIMPLE_C_BUILD_CONFIG = {
    "name": "hello-world-c",
    "dockerfile_content": """
FROM centos:7

# 安装构建工具
RUN yum update -y && yum install -y gcc make

# 设置工作目录
WORKDIR /workspace

# 复制源码
COPY . .

# 编译程序
RUN gcc -o hello hello.c

# 运行程序
CMD ["./hello"]
    """.strip(),
    "context_files": {
        "hello.c": """
#include <stdio.h>

int main() {
    printf("Hello, EulerMaker!\\n");
    return 0;
}
        """.strip(),
        "Makefile": """
CC = gcc
CFLAGS = -Wall -O2
TARGET = hello
SOURCE = hello.c

$(TARGET): $(SOURCE)
\t$(CC) $(CFLAGS) -o $@ $<

clean:
\trm -f $(TARGET)

.PHONY: clean
        """.strip()
    },
    "build_args": {
        "BUILD_DATE": "2025-07-01"
    },
    "labels": {
        "build.type": "c-program",
        "build.version": "1.0"
    }
}

# Python应用构建
PYTHON_APP_BUILD_CONFIG = {
    "name": "python-flask-app",
    "dockerfile_content": """
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# 启动应用
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
    """.strip(),
    "context_files": {
        "requirements.txt": """
Flask==2.3.3
gunicorn==21.2.0
redis==5.0.1
psycopg2-binary==2.9.7
        """.strip(),
        "app.py": """
from flask import Flask, jsonify
import redis
import os

app = Flask(__name__)

# Redis连接
redis_client = redis.Redis.from_url(
    os.environ.get('REDIS_URL', 'redis://localhost:6379')
)

@app.route('/health')
def health():
    try:
        redis_client.ping()
        return jsonify({'status': 'healthy', 'redis': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/')
def hello():
    return jsonify({'message': 'Hello from EulerMaker Python App!'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
        """.strip(),
        "gunicorn.conf.py": """
bind = "0.0.0.0:5000"
workers = 4
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 2
        """.strip()
    },
    "build_args": {
        "PYTHON_VERSION": "3.9",
        "APP_VERSION": "1.0.0"
    },
    "target_stage": None,
    "labels": {
        "build.type": "python-app",
        "app.name": "flask-demo",
        "app.version": "1.0.0"
    }
}

# 多阶段构建配置
MULTISTAGE_BUILD_CONFIG = {
    "name": "go-app-multistage",
    "dockerfile_content": """
# 构建阶段
FROM golang:1.19-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

# 运行阶段
FROM alpine:latest AS runtime

RUN apk --no-cache add ca-certificates
WORKDIR /root/

# 复制二进制文件
COPY --from=builder /app/main .

# 暴露端口
EXPOSE 8080

CMD ["./main"]
    """.strip(),
    "context_files": {
        "go.mod": """
module github.com/eulermaker/demo-app

go 1.19

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/go-redis/redis/v8 v8.11.5
)
        """.strip(),
        "main.go": """
package main

import (
    "net/http"
    "github.com/gin-gonic/gin"
)

func main() {
    r := gin.Default()
    
    r.GET("/health", func(c *gin.Context) {
        c.JSON(http.StatusOK, gin.H{
            "status": "healthy",
        })
    })
    
    r.GET("/", func(c *gin.Context) {
        c.JSON(http.StatusOK, gin.H{
            "message": "Hello from EulerMaker Go App!",
        })
    })
    
    r.Run(":8080")
}
        """.strip()
    },
    "target_stage": "runtime",
    "build_args": {
        "GO_VERSION": "1.19"
    }
}

# ====================================
# 探针配置示例
# ====================================

# HTTP健康检查探针
HTTP_HEALTH_PROBE_CONFIGS = {
    "basic_http": {
        "type": "http",
        "config": {
            "url": "http://localhost:8080/health",
            "method": "GET",
            "timeout": 5,
            "interval": 10,
            "retries": 3,
            "expected_status": [200]
        }
    },
    "advanced_http": {
        "type": "http",
        "config": {
            "url": "https://api.example.com/health",
            "method": "POST",
            "headers": {
                "Authorization": "Bearer token123",
                "Content-Type": "application/json",
                "User-Agent": "EulerMaker-Probe/1.0"
            },
            "body": '{"probe": true}',
            "timeout": 10,
            "interval": 30,
            "retries": 2,
            "expected_status": [200, 201],
            "expected_body_contains": "healthy",
            "expected_headers": {
                "content-type": "application/json"
            },
            "ssl_verify": False
        }
    }
}

# TCP连接探针
TCP_PROBE_CONFIGS = {
    "database_tcp": {
        "type": "tcp",
        "config": {
            "host": "localhost",
            "port": 5432,
            "timeout": 3,
            "interval": 15,
            "retries": 2
        }
    },
    "redis_tcp": {
        "type": "tcp",
        "config": {
            "host": "redis",
            "port": 6379,
            "timeout": 2,
            "interval": 10,
            "retries": 3
        }
    }
}

# 命令执行探针
COMMAND_PROBE_CONFIGS = {
    "process_check": {
        "type": "command",
        "config": {
            "command": ["pgrep", "-f", "nginx"],
            "expected_exit_code": 0,
            "timeout": 5,
            "interval": 20,
            "retries": 1
        }
    },
    "disk_space": {
        "type": "command",
        "config": {
            "command": ["df", "-h", "/"],
            "expected_exit_code": 0,
            "expected_output_regex": r"(\d+)%",
            "timeout": 10,
            "interval": 60,
            "retries": 1
        }
    },
    "custom_script": {
        "type": "command",
        "config": {
            "command": ["/usr/local/bin/custom-check.sh"],
            "expected_exit_code": 0,
            "expected_output_contains": "OK",
            "timeout": 30,
            "interval": 300,
            "retries": 2,
            "environment": {
                "CHECK_MODE": "production",
                "THRESHOLD": "80"
            }
        }
    }
}

# ====================================
# 错误配置示例（用于测试错误处理）
# ====================================

# 无效的容器配置
INVALID_CONTAINER_CONFIGS = {
    "invalid_image": {
        **CENTOS_CONTAINER_CONFIG,
        "image": ""  # 空镜像名
    },
    "invalid_port": {
        **CENTOS_CONTAINER_CONFIG,
        "ports": {"invalid": 8080}  # 无效端口格式
    },
    "invalid_memory": {
        **CENTOS_CONTAINER_CONFIG,
        "memory_limit": "invalid"  # 无效内存限制
    },
    "invalid_volume": {
        **CENTOS_CONTAINER_CONFIG,
        "volumes": {"/invalid": ""}  # 空的容器路径
    },
    "circular_dependency": {
        **CENTOS_CONTAINER_CONFIG,
        "depends_on": ["invalid_container"]  # 依赖不存在的容器
    }
}

# 无效的构建配置
INVALID_BUILD_CONFIGS = {
    "empty_dockerfile": {
        **SIMPLE_C_BUILD_CONFIG,
        "dockerfile_content": ""  # 空Dockerfile
    },
    "invalid_dockerfile": {
        **SIMPLE_C_BUILD_CONFIG,
        "dockerfile_content": "INVALID dockerfile content"  # 无效语法
    },
    "missing_context": {
        **SIMPLE_C_BUILD_CONFIG,
        "context_files": {}  # 缺少上下文文件
    }
}

# 无效的探针配置
INVALID_PROBE_CONFIGS = {
    "invalid_url": {
        "type": "http",
        "config": {
            "url": "invalid-url",  # 无效URL
            "timeout": 5
        }
    },
    "invalid_port": {
        "type": "tcp",
        "config": {
            "host": "localhost",
            "port": -1,  # 无效端口
            "timeout": 5
        }
    },
    "invalid_command": {
        "type": "command",
        "config": {
            "command": [],  # 空命令
            "timeout": 5
        }
    }
}

# ====================================
# 性能测试配置
# ====================================

# 大量容器配置
BULK_CONTAINER_CONFIGS = []
for i in range(100):
    config = {
        **CENTOS_CONTAINER_CONFIG,
        "name": f"bulk-container-{i:03d}",
        "environment": {
            **CENTOS_CONTAINER_CONFIG["environment"],
            "CONTAINER_ID": str(i),
            "BATCH_SIZE": "100"
        }
    }
    BULK_CONTAINER_CONFIGS.append(config)

# 高负载构建配置
STRESS_BUILD_CONFIG = {
    "name": "stress-build",
    "dockerfile_content": """
FROM centos:7

# 模拟CPU密集型任务
RUN for i in {1..1000}; do \
        echo "Building component $i..." && \
        sleep 0.01; \
    done

# 模拟内存使用
RUN dd if=/dev/zero of=/tmp/largefile bs=1M count=100

# 模拟网络IO
RUN for i in {1..10}; do \
        wget -q -O /tmp/file$i.txt http://httpbin.org/get; \
    done

CMD ["echo", "Stress build completed"]
    """.strip(),
    "build_args": {
        "STRESS_LEVEL": "high",
        "ITERATIONS": "1000"
    },
    "no_cache": True
}

# ====================================
# Docker Compose配置示例
# ====================================

DOCKER_COMPOSE_CONFIGS = {
    "simple_app": {
        "version": "3.8",
        "services": {
            "web": {
                "build": ".",
                "ports": ["8000:8000"],
                "environment": {
                    "DATABASE_URL": "postgresql://postgres:password@db:5432/app",
                    "REDIS_URL": "redis://redis:6379/0"
                },
                "depends_on": ["db", "redis"],
                "restart": "unless-stopped"
            },
            "db": {
                "image": "postgres:13",
                "environment": {
                    "POSTGRES_DB": "app",
                    "POSTGRES_USER": "postgres",
                    "POSTGRES_PASSWORD": "password"
                },
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
                "restart": "unless-stopped"
            },
            "redis": {
                "image": "redis:7-alpine",
                "restart": "unless-stopped"
            }
        },
        "volumes": {
            "postgres_data": {}
        },
        "networks": {
            "default": {
                "driver": "bridge"
            }
        }
    },
    "microservices": {
        "version": "3.8",
        "services": {
            "nginx": {
                "image": "nginx:alpine",
                "ports": ["80:80", "443:443"],
                "volumes": [
                    "./nginx.conf:/etc/nginx/nginx.conf",
                    "./ssl:/etc/nginx/ssl"
                ],
                "depends_on": ["api", "frontend"]
            },
            "api": {
                "build": "./api",
                "environment": {
                    "NODE_ENV": "production"
                },
                "depends_on": ["db", "redis"],
                "deploy": {
                    "replicas": 3,
                    "resources": {
                        "limits": {
                            "cpus": "0.5",
                            "memory": "512M"
                        }
                    }
                }
            },
            "frontend": {
                "build": "./frontend",
                "environment": {
                    "API_URL": "http://api:3000"
                }
            },
            "db": {
                "image": "postgres:13",
                "environment": {
                    "POSTGRES_DB": "microservices",
                    "POSTGRES_USER": "admin",
                    "POSTGRES_PASSWORD": "${DB_PASSWORD}"
                },
                "volumes": ["db_data:/var/lib/postgresql/data"]
            },
            "redis": {
                "image": "redis:7-alpine",
                "volumes": ["redis_data:/data"]
            }
        },
        "volumes": {
            "db_data": {},
            "redis_data": {}
        }
    }
}

# ====================================
# 导出配置
# ====================================

__all__ = [
    # 环境配置
    "DEV_CONFIG",
    "TEST_CONFIG",
    "PROD_CONFIG",

    # 容器配置
    "CENTOS_CONTAINER_CONFIG",
    "RPM_BUILD_CONTAINER_CONFIG",
    "WEB_SERVICE_CONTAINER_CONFIG",
    "DATABASE_CONTAINER_CONFIG",

    # 网络配置
    "CUSTOM_NETWORK_CONFIGS",

    # 构建配置
    "SIMPLE_C_BUILD_CONFIG",
    "PYTHON_APP_BUILD_CONFIG",
    "MULTISTAGE_BUILD_CONFIG",

    # 探针配置
    "HTTP_HEALTH_PROBE_CONFIGS",
    "TCP_PROBE_CONFIGS",
    "COMMAND_PROBE_CONFIGS",

    # 错误配置
    "INVALID_CONTAINER_CONFIGS",
    "INVALID_BUILD_CONFIGS",
    "INVALID_PROBE_CONFIGS",

    # 性能测试配置
    "BULK_CONTAINER_CONFIGS",
    "STRESS_BUILD_CONFIG",

    # Docker Compose配置
    "DOCKER_COMPOSE_CONFIGS",
]