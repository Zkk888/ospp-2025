#OSPP-2025-zJr
##EulerMaker构建优化-EulerMaker Docker 优化器

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-blue.svg)](https://www.docker.com/)

EulerOS/openEuler 生态系统下的Docker 容器管理和 RPM 包构建优化工具。

## 📋 主要内容

- [功能特性](#功能特性)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [安装部署](#安装部署)
- [使用指南](#使用指南)
- [API 文档](#api-文档)
- [开发指南](#开发指南)
- [测试](#测试)

## ✨ 功能特性

### 核心功能

- **容器生命周期管理**
    - 完整的容器 CRUD 操作
    - 容器状态监控和事件处理
    - 资源限制和性能优化
    - 容器网络和存储管理

- **RPM 包构建优化**
    - 自动化构建流程
    - Dockerfile 生成和优化
    - 多阶段构建支持
    - 构建缓存管理

- **Web 终端集成**
    - 基于 xterm.js 的 Web 终端
    - WebSocket 实时通信
    - 多会话管理
    - 终端录制回放

- **探针系统**
    - 容器健康检查
    - 性能指标收集
    - 自定义探针支持
    - 告警和通知

### 技术特点

- **高性能**: 异步 I/O 和并发处理
- **可扩展**: 模块化设计，易于扩展
- **可观测**: 完善的日志和监控
- **安全**: 细粒度权限控制
- **易用**: RESTful API 和 Web UI

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层 (Frontend)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Web UI    │  │  xterm.js   │  │  API Client │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      API 层 (API Layer)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Web Server │  │  WebSocket  │  │  RPC Server │         │
│  │   (Flask)   │  │   Server    │  │   (gRPC)    │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    服务层 (Service Layer)                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │   Container  │ │    Build     │ │   Terminal   │        │
│  │   Service    │ │   Service    │ │   Service    │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     核心层 (Core Layer)                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │    Docker    │ │  Container   │ │    Build     │        │
│  │   Manager    │ │  Lifecycle   │ │   Manager    │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  基础设施层 (Infrastructure)                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │    Docker    │ │    Redis     │ │  PostgreSQL  │        │
│  │    Engine    │ │    Cache     │ │   Database   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 前置要求

- Python 3.8+
- Docker 20.10+
- Redis 6.0+
- 至少 4GB 内存
- 20GB 可用磁盘空间

### 快速安装

```bash
# 克隆仓库
git clone https://github.com/your-org/eulermaker-docker-optimizer.git
cd eulermaker-docker-optimizer

# 使用 Docker Compose 快速启动
docker-compose up -d

# 访问 Web UI
open http://localhost:8080
```

### 基本使用

```python
from eulermaker import DockerOptimizer

# 初始化优化器
optimizer = DockerOptimizer()

# 创建并启动容器
container = optimizer.create_container(
    name="my-container",
    image="centos:7",
    command=["bash"]
)
container.start()

# 构建 RPM 包
build = optimizer.create_build(
    name="my-rpm-build",
    spec_file="package.spec",
    source_files=["source.tar.gz"]
)
result = build.execute()
```

## 📦 安装部署

### 方式一：使用 Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/your-org/eulermaker-docker-optimizer.git
cd eulermaker-docker-optimizer

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件配置必要的环境变量

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f

# 5. 停止服务
docker-compose down
```

### 方式二：手动安装

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境
export DOCKER_HOST=unix:///var/run/docker.sock
export REDIS_URL=redis://localhost:6379/0

# 4. 运行数据库迁移
python scripts/migrate.py

# 5. 启动服务
python src/main.py
```

### 方式三：从源码安装

```bash
# 1. 克隆并安装
git clone https://github.com/your-org/eulermaker-docker-optimizer.git
cd eulermaker-docker-optimizer
pip install -e .

# 2. 启动服务
eulermaker-optimizer start
```

## 📖 使用指南

### 容器管理

#### 创建容器

```python
from eulermaker import ContainerService

service = ContainerService()

# 基本创建
container = service.create_container(
    name="test-container",
    image="centos:7",
    command=["sleep", "3600"]
)

# 高级配置
container = service.create_container(
    name="advanced-container",
    image="centos:7",
    command=["bash"],
    environment={
        "ENV_VAR": "value"
    },
    volumes={
        "/host/path": "/container/path"
    },
    ports={
        "80/tcp": 8080
    },
    memory_limit="1g",
    cpu_limit="1.0"
)
```

#### 容器生命周期操作

```python
# 启动容器
container.start()

# 停止容器
container.stop(timeout=10)

# 重启容器
container.restart()

# 暂停/恢复
container.pause()
container.unpause()

# 删除容器
container.remove(force=True)
```

#### 监控和日志

```python
# 获取容器状态
status = container.status()
print(f"Status: {status['State']}")

# 获取统计信息
stats = container.stats()
print(f"Memory: {stats['memory_usage']} / {stats['memory_limit']}")
print(f"CPU: {stats['cpu_percent']}%")

# 获取日志
logs = container.logs(tail=100, follow=False)
print(logs)

# 流式日志
for log in container.logs_stream():
    print(log, end='')
```

### RPM 构建

#### 简单构建

```python
from eulermaker import BuildService

service = BuildService()

# 创建构建任务
build = service.create_build(
    name="my-package",
    dockerfile_content="""
FROM centos:7
RUN yum install -y rpm-build
COPY package.spec /root/rpmbuild/SPECS/
RUN rpmbuild -ba /root/rpmbuild/SPECS/package.spec
    """,
    context_files={
        "package.spec": open("package.spec").read()
    }
)

# 执行构建
result = build.execute()
print(f"Build status: {result['status']}")
print(f"Image ID: {result['image']['id']}")
```

#### 高级构建

```python
# 多阶段构建
build = service.create_build(
    name="multistage-build",
    dockerfile_content="""
# 构建阶段
FROM centos:7 as builder
RUN yum install -y rpm-build make gcc
COPY . /workspace
WORKDIR /workspace
RUN make all

# 运行阶段
FROM centos:7
COPY --from=builder /workspace/output/*.rpm /rpms/
RUN yum install -y /rpms/*.rpm
    """,
    build_args={
        "VERSION": "1.0.0"
    },
    labels={
        "maintainer": "your-email@example.com",
        "version": "1.0.0"
    }
)

# 异步执行
import asyncio

async def async_build():
    result = await build.execute_async()
    return result

result = asyncio.run(async_build())
```

### Web 终端

#### 启动终端会话

```python
from eulermaker import TerminalService

service = TerminalService()

# 创建终端会话
session = service.create_session(
    container_id="container-123",
    command="/bin/bash"
)

# 获取 WebSocket URL
ws_url = session.websocket_url
print(f"Connect to: {ws_url}")
```

#### 前端集成

```html
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="/static/css/xterm.css" />
    <script src="/static/js/xterm.js"></script>
</head>
<body>
    <div id="terminal"></div>
    <script>
        const term = new Terminal();
        term.open(document.getElementById('terminal'));
        
        const ws = new WebSocket('ws://localhost:8080/ws/terminal/session-id');
        
        ws.onmessage = (event) => {
            term.write(event.data);
        };
        
        term.onData((data) => {
            ws.send(data);
        });
    </script>
</body>
</html>
```

### 探针系统

```python
from eulermaker import ProbeService

service = ProbeService()

# 添加健康检查探针
probe = service.add_probe(
    container_id="container-123",
    probe_type="http",
    config={
        "url": "http://localhost:8080/health",
        "interval": 30,
        "timeout": 5,
        "retries": 3
    }
)

# 添加性能监控探针
perf_probe = service.add_probe(
    container_id="container-123",
    probe_type="metrics",
    config={
        "interval": 10,
        "metrics": ["cpu", "memory", "disk", "network"]
    }
)

# 获取探针结果
results = probe.get_results()
for result in results:
    print(f"{result['timestamp']}: {result['status']}")
```

## 🔌 API 文档

### RESTful API

详细的 API 文档请参见 [docs/api.md](docs/api.md)

#### 容器 API

```bash
# 创建容器
POST /api/v1/containers
{
    "name": "my-container",
    "image": "centos:7",
    "command": ["bash"]
}

# 列出容器
GET /api/v1/containers

# 获取容器详情
GET /api/v1/containers/{id}

# 启动容器
POST /api/v1/containers/{id}/start

# 停止容器
POST /api/v1/containers/{id}/stop

# 删除容器
DELETE /api/v1/containers/{id}
```

#### 构建 API

```bash
# 创建构建任务
POST /api/v1/builds
{
    "name": "my-build",
    "dockerfile_content": "FROM centos:7..."
}

# 列出构建任务
GET /api/v1/builds

# 执行构建
POST /api/v1/builds/{id}/execute

# 获取构建日志
GET /api/v1/builds/{id}/logs
```

### WebSocket API

```javascript
// 终端连接
const ws = new WebSocket('ws://localhost:8080/ws/terminal/{session_id}');

// 构建日志流
const buildWs = new WebSocket('ws://localhost:8080/ws/builds/{build_id}/logs');
```

### gRPC API

```protobuf
service ContainerService {
    rpc CreateContainer (CreateContainerRequest) returns (Container);
    rpc ListContainers (ListContainersRequest) returns (ContainerList);
    rpc GetContainer (GetContainerRequest) returns (Container);
    rpc StartContainer (StartContainerRequest) returns (ContainerStatus);
    rpc StopContainer (StopContainerRequest) returns (ContainerStatus);
}
```

## 👨‍💻 开发指南

### 开发环境设置

```bash
# 1. 克隆项目
git clone https://github.com/your-org/eulermaker-docker-optimizer.git
cd eulermaker-docker-optimizer

# 2. 创建开发环境
python -m venv venv
source venv/bin/activate

# 3. 安装开发依赖
pip install -r requirements-dev.txt

# 4. 安装 pre-commit hooks
pre-commit install

# 5. 运行开发服务器
python src/main.py --debug
```

### 代码规范

项目遵循以下代码规范：

- **Python**: PEP 8
- **文档字符串**: Google Style
- **类型提示**: 使用 Python 3.8+ 类型注解
- **导入顺序**: isort
- **代码格式化**: black
- **静态检查**: flake8, mypy, pylint

```bash
# 格式化代码
black src/ tests/

# 排序导入
isort src/ tests/

# 静态检查
flake8 src/ tests/
mypy src/
pylint src/
```

### 添加新功能

1. **创建新分支**
   ```bash
   git checkout -b feature/new-feature
   ```

2. **编写代码**
    - 在适当的模块中添加功能
    - 遵循现有的代码结构和命名约定

3. **编写测试**
   ```python
   # tests/unit/test_new_feature.py
   def test_new_feature():
       # 测试代码
       pass
   ```

4. **更新文档**
    - 更新 API 文档
    - 添加使用示例
    - 更新 README

5. **提交代码**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   git push origin feature/new-feature
   ```

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 运行特定测试文件
pytest tests/unit/test_docker_manager.py

# 运行带覆盖率的测试
pytest --cov=src --cov-report=html

# 运行性能测试
pytest tests/performance/ -v --benchmark-only
```

### 测试分类

```bash
# 按标记运行
pytest -m "unit"           # 只运行单元测试
pytest -m "integration"     # 只运行集成测试
pytest -m "slow"           # 只运行慢速测试
pytest -m "not slow"       # 跳过慢速测试
pytest -m "docker"         # 需要 Docker 的测试
```

### 编写测试

```python
import pytest
from eulermaker import ContainerService

@pytest.mark.unit
def test_container_creation():
    service = ContainerService()
    container = service.create_container(
        name="test",
        image="centos:7"
    )
    assert container.name == "test"

@pytest.mark.integration
@pytest.mark.docker
def test_container_lifecycle():
    service = ContainerService()
    container = service.create_container(
        name="integration-test",
        image="centos:7",
        command=["sleep", "10"]
    )
    
    # 启动容器
    container.start()
    assert container.is_running()
    
    # 停止容器
    container.stop()
    assert not container.is_running()
    
    # 清理
    container.remove()
```

## 📊 性能优化

### 容器性能优化

```python
# 设置资源限制
container = service.create_container(
    name="optimized-container",
    image="centos:7",
    # CPU 限制
    cpu_limit="1.0",        # 1 个 CPU 核心
    cpu_shares=1024,        # CPU 权重
    # 内存限制
    memory_limit="1g",      # 1GB 内存
    memory_swap="2g",       # 2GB 交换空间
    # I/O 限制
    blkio_weight=500,       # 块 I/O 权重
    # 网络优化
    network_mode="bridge"
)
```

### 构建优化

```python
# 使用构建缓存
build = service.create_build(
    name="cached-build",
    dockerfile_content="...",
    cache_enabled=True,
    cache_from=["previous-build:latest"]
)

# 多阶段构建
build = service.create_build(
    name="multistage",
    dockerfile_content="""
FROM golang:1.19 as builder
WORKDIR /app
COPY . .
RUN go build -o app

FROM alpine:latest
COPY --from=builder /app/app /usr/local/bin/
CMD ["app"]
    """
)
```

## 🔒 安全性

### 最佳实践

1. **容器安全**
    - 使用最小化的基础镜像
    - 不要以 root 用户运行
    - 限制容器权限
    - 定期更新镜像

2. **网络安全**
    - 使用私有网络
    - 限制端口暴露
    - 启用 TLS/SSL

3. **数据安全**
    - 加密敏感数据
    - 使用 secrets 管理
    - 定期备份

### 安全配置示例

```python
# 安全容器配置
container = service.create_container(
    name="secure-container",
    image="centos:7",
    # 用户配置
    user="1000:1000",
    # 只读根文件系统
    read_only=True,
    # 禁用特权模式
    privileged=False,
    # 限制能力
    cap_drop=["ALL"],
    cap_add=["NET_BIND_SERVICE"],
    # 安全选项
    security_opt=["no-new-privileges:true"]
)
```

## 🐛 故障排除

### 常见问题

#### Docker 连接问题

```bash
# 检查 Docker 服务状态
systemctl status docker

# 检查 Docker 套接字权限
ls -la /var/run/docker.sock

# 将用户添加到 docker 组
sudo usermod -aG docker $USER
```

#### 容器启动失败

```python
# 查看详细错误信息
try:
    container.start()
except Exception as e:
    print(f"Error: {e}")
    logs = container.logs()
    print(f"Logs: {logs}")
```

#### 构建失败

```python
# 获取构建日志
build_logs = build.get_logs()
for log in build_logs:
    print(log)

# 启用详细日志
build.execute(verbose=True)
```

### 调试技巧

```python
# 启用调试日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 使用交互式 Shell
container.exec_run(
    cmd="/bin/bash",
    stdin=True,
    tty=True
)
```

## 📈 监控和告警

### Prometheus 集成

```python
from eulermaker.monitoring import PrometheusExporter

# 启动 Prometheus 导出器
exporter = PrometheusExporter(port=9090)
exporter.start()
```

### Grafana 仪表板

导入预配置的 Grafana 仪表板：

```bash
# 导入仪表板配置
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @grafana-dashboard.json
```

## 👥 人员

- **导师**: [@wangyangdahai](https://github.com/wangyangdahai)
- **学生**: [@Zkk888](https://github.com/Zkk888)


## 🙏 致谢

感谢以下开源项目供我参考：

- [Docker](https://www.docker.com/)
- [Flask](https://flask.palletsprojects.com/)
- [xterm.js](https://xtermjs.org/)
- [Redis](https://redis.io/)
- [PostgreSQL](https://www.postgresql.org/)

## 📞 联系我

- **Email**: 3487232360@qq.com
- **Issues**: [GitHub Issues](https://github.com/Zkk888/ospp-2025/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Zkk888/ospp-2025/discussions)


---