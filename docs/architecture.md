# EulerMaker Docker 优化器 - 架构文档

## 目录

- [系统概述](#系统概述)
- [架构设计原则](#架构设计原则)
- [系统架构](#系统架构)
- [模块设计](#模块设计)
- [数据流](#数据流)
- [技术栈](#技术栈)
- [部署架构](#部署架构)
- [扩展性设计](#扩展性设计)
- [安全架构](#安全架构)

## 系统概述

EulerMaker Docker 优化器是一个面向 EulerOS/openEuler 生态系统的容器管理和 RPM 包构建优化平台。系统采用分层架构设计，通过模块化的方式实现容器生命周期管理、自动化构建、Web 终端集成和探针监控等核心功能。

### 核心特性

- **容器管理**: 完整的容器生命周期管理，包括创建、启动、停止、监控和销毁
- **构建优化**: 自动化的 RPM 包构建流程，支持多阶段构建和缓存优化
- **终端集成**: 基于 xterm.js 的 Web 终端，提供实时交互能力
- **监控告警**: 探针系统实时监控容器状态和性能指标
- **可扩展性**: 模块化设计，支持功能扩展和定制

## 架构设计原则

### 1. 分层架构

系统采用经典的分层架构模式，从下到上分为：

- **基础设施层**: Docker Engine、Redis、PostgreSQL 等基础服务
- **核心层**: Docker 管理、容器生命周期、构建管理等核心功能
- **服务层**: 业务逻辑封装，提供高层次的服务接口
- **API 层**: 对外接口，支持 RESTful、WebSocket、gRPC 等协议
- **前端层**: Web UI 和客户端工具

### 2. 模块化设计

每个模块具有明确的职责边界，通过接口进行交互：

- **高内聚**: 模块内部功能紧密相关
- **低耦合**: 模块间依赖最小化
- **可替换**: 模块可以独立升级和替换
- **可测试**: 每个模块都可以独立测试

### 3. 异步处理

采用异步 I/O 和事件驱动模型：

- **非阻塞**: 避免长时间阻塞操作
- **并发处理**: 支持大量并发请求
- **资源高效**: 减少线程和内存开销
- **响应快速**: 提升用户体验

### 4. 容错设计

系统具备良好的容错和恢复能力：

- **优雅降级**: 部分功能失败不影响整体
- **重试机制**: 自动重试临时性失败
- **错误隔离**: 错误不会传播扩散
- **状态恢复**: 支持从故障中恢复

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                          客户端层                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  Web UI  │  │   CLI    │  │  SDK     │  │  第三方  │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↓ ↓
┌─────────────────────────────────────────────────────────────────┐
│                          API 网关层                              │
│  ┌─────────────────────────────────────────────────────┐        │
│  │  Load Balancer (Nginx/Traefik)                     │        │
│  │  - 负载均衡  - SSL 终止  - 请求路由  - 限流        │        │
│  └─────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↓ ↓
┌─────────────────────────────────────────────────────────────────┐
│                        应用服务层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Web Server  │  │   WebSocket  │  │  RPC Server  │          │
│  │   (Flask)    │  │    Server    │  │   (gRPC)     │          │
│  │              │  │              │  │              │          │
│  │ - RESTful    │  │ - 实时通信   │  │ - 高性能     │          │
│  │ - 认证授权   │  │ - 终端连接   │  │ - 服务调用   │          │
│  │ - 请求处理   │  │ - 日志流式   │  │ - 内部通信   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↓ ↓
┌─────────────────────────────────────────────────────────────────┐
│                        业务服务层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Container   │  │    Build     │  │   Terminal   │          │
│  │   Service    │  │   Service    │  │   Service    │          │
│  │              │  │              │  │              │          │
│  │ - 容器管理   │  │ - 构建任务   │  │ - 会话管理   │          │
│  │ - 状态监控   │  │ - Dockerfile │  │ - 命令执行   │          │
│  │ - 资源控制   │  │ - 缓存优化   │  │ - I/O 处理   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Probe     │  │    Event     │  │     Auth     │          │
│  │   Service    │  │   Service    │  │   Service    │          │
│  │              │  │              │  │              │          │
│  │ - 健康检查   │  │ - 事件总线   │  │ - 用户认证   │          │
│  │ - 性能监控   │  │ - 消息队列   │  │ - 权限控制   │          │
│  │ - 告警通知   │  │ - 异步处理   │  │ - Token 管理 │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↓ ↓
┌─────────────────────────────────────────────────────────────────┐
│                          核心层                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Docker    │  │  Container   │  │    Build     │          │
│  │   Manager    │  │  Lifecycle   │  │   Manager    │          │
│  │              │  │              │  │              │          │
│  │ - API 封装   │  │ - 状态机     │  │ - 镜像构建   │          │
│  │ - 连接池     │  │ - 事件处理   │  │ - 层优化     │          │
│  │ - 错误处理   │  │ - 钩子函数   │  │ - 多阶段     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Probe     │  │    Network   │  │   Storage    │          │
│  │   Manager    │  │   Manager    │  │   Manager    │          │
│  │              │  │              │  │              │          │
│  │ - 探针调度   │  │ - 网络配置   │  │ - 卷管理     │          │
│  │ - 数据采集   │  │ - 端口映射   │  │ - 数据持久化 │          │
│  │ - 结果分析   │  │ - DNS 配置   │  │ - 备份恢复   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↓ ↓
┌─────────────────────────────────────────────────────────────────┐
│                        数据存储层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │     Redis    │  │  PostgreSQL  │  │   Object     │          │
│  │              │  │              │  │   Storage    │          │
│  │ - 缓存       │  │ - 元数据     │  │ - 构建产物   │          │
│  │ - 会话       │  │ - 配置       │  │ - 日志文件   │          │
│  │ - 队列       │  │ - 审计日志   │  │ - 镜像存储   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↓ ↓
┌─────────────────────────────────────────────────────────────────┐
│                        基础设施层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Docker    │  │  Kubernetes  │  │   Monitoring │          │
│  │    Engine    │  │  (Optional)  │  │              │          │
│  │              │  │              │  │ - Prometheus │          │
│  │ - 容器运行时 │  │ - 编排调度   │  │ - Grafana    │          │
│  │ - 镜像管理   │  │ - 服务发现   │  │ - ELK Stack  │          │
│  │ - 网络插件   │  │ - 自动扩展   │  │ - Jaeger     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 组件交互流程

#### 1. 容器创建流程

```
用户请求 → API 网关 → Web Server → Container Service 
    → Docker Manager → Docker Engine → 容器实例
                ↓
         状态更新 → Event Service → WebSocket → 用户实时通知
```

#### 2. 构建流程

```
用户提交 → Build Service → Build Manager → Dockerfile 生成
    → Docker Build → 镜像生成 → Registry 推送
         ↓                    ↓
    日志流式推送          构建缓存管理
         ↓                    ↓
    WebSocket 实时显示    优化构建速度
```

#### 3. 终端连接流程

```
用户请求 → WebSocket Server → Terminal Service 
    → 容器 Exec → PTY 分配 → 双向数据流
         ↓
    实时 I/O 传输 → xterm.js 渲染
```

## 模块设计

### 核心层模块

#### Docker Manager

负责 Docker API 的封装和管理：

```python
class DockerManager:
    """Docker API 管理器"""

    def __init__(self):
        self.client = docker.from_env()
        self.connection_pool = ConnectionPool()

    def create_container(self, config: Dict) -> Container:
        """创建容器"""
        pass

    def build_image(self, dockerfile: str, context: Dict) -> Image:
        """构建镜像"""
        pass

    def get_container(self, container_id: str) -> Container:
        """获取容器"""
        pass
```

**职责**:
- Docker API 调用封装
- 连接池管理
- 错误处理和重试
- 资源清理

**依赖**:
- Docker SDK for Python
- 连接池实现

#### Container Lifecycle Manager

容器生命周期管理器：

```python
class ContainerLifecycleManager:
    """容器生命周期管理器"""

    def __init__(self, docker_manager: DockerManager):
        self.docker_manager = docker_manager
        self.state_machine = ContainerStateMachine()
        self.event_handlers = {}

    def start_container(self, container_id: str):
        """启动容器"""
        # 状态转换
        # 事件触发
        # 钩子执行
        pass

    def register_hook(self, event: str, handler: Callable):
        """注册生命周期钩子"""
        pass
```

**职责**:
- 状态机管理
- 生命周期事件处理
- 钩子函数调度
- 异常处理和恢复

**状态机**:

```
Created → Starting → Running → Stopping → Stopped
    ↓                    ↓
  Failed            Paused → Unpaused
```

#### Build Manager

构建管理器：

```python
class BuildManager:
    """构建管理器"""

    def __init__(self):
        self.dockerfile_generator = DockerfileGenerator()
        self.cache_manager = BuildCacheManager()

    def prepare_build_context(self, config: Dict) -> str:
        """准备构建上下文"""
        pass

    def optimize_dockerfile(self, dockerfile: str) -> str:
        """优化 Dockerfile"""
        pass

    def build(self, context: str, dockerfile: str) -> BuildResult:
        """执行构建"""
        pass
```

**职责**:
- Dockerfile 生成和优化
- 构建上下文准备
- 构建缓存管理
- 多阶段构建支持

### 服务层模块

#### Container Service

容器服务：

```python
class ContainerService:
    """容器服务"""

    def __init__(self):
        self.lifecycle_manager = ContainerLifecycleManager()
        self.monitor = ContainerMonitor()
        self.validator = ContainerValidator()

    async def create_container(self, config: Dict) -> Container:
        """创建容器（异步）"""
        # 验证配置
        # 创建容器
        # 注册监控
        pass

    def get_container_stats(self, container_id: str) -> Dict:
        """获取容器统计信息"""
        pass
```

**职责**:
- 容器业务逻辑
- 配置验证
- 状态监控
- 资源管理

#### Build Service

构建服务：

```python
class BuildService:
    """构建服务"""

    def __init__(self):
        self.build_manager = BuildManager()
        self.task_queue = TaskQueue()
        self.registry_client = RegistryClient()

    async def create_build_task(self, config: Dict) -> BuildTask:
        """创建构建任务"""
        pass

    async def execute_build(self, task_id: str) -> BuildResult:
        """执行构建"""
        pass
```

**职责**:
- 构建任务管理
- 异步构建执行
- 镜像推送
- 构建历史记录

#### Terminal Service

终端服务：

```python
class TerminalService:
    """终端服务"""

    def __init__(self):
        self.session_manager = SessionManager()
        self.pty_manager = PTYManager()

    async def create_session(self, container_id: str, command: str) -> Session:
        """创建终端会话"""
        pass

    async def send_input(self, session_id: str, data: bytes):
        """发送输入"""
        pass

    async def receive_output(self, session_id: str) -> bytes:
        """接收输出"""
        pass
```

**职责**:
- 会话管理
- PTY 分配
- I/O 处理
- 会话录制

### API 层模块

#### Web Server

Web 服务器：

```python
from flask import Flask

class WebServer:
    """Web 服务器"""

    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
        self.setup_middleware()

    def setup_routes(self):
        """设置路由"""
        from api.routes import container_routes, build_routes
        self.app.register_blueprint(container_routes)
        self.app.register_blueprint(build_routes)

    def setup_middleware(self):
        """设置中间件"""
        # CORS
        # 认证
        # 限流
        # 日志
        pass
```

**特性**:
- RESTful API
- JWT 认证
- 请求限流
- CORS 支持

#### WebSocket Server

WebSocket 服务器：

```python
class WebSocketServer:
    """WebSocket 服务器"""

    def __init__(self):
        self.connections = {}
        self.handlers = {}

    async def handle_connection(self, websocket, path):
        """处理连接"""
        pass

    async def broadcast(self, channel: str, message: Dict):
        """广播消息"""
        pass
```

**用途**:
- 实时日志推送
- 终端 I/O
- 事件通知
- 状态更新

## 数据流

### 容器操作数据流

```
1. 用户发起请求
   ↓
2. API 验证和路由
   ↓
3. 服务层业务处理
   ↓
4. 核心层 Docker 操作
   ↓
5. 状态更新到数据库
   ↓
6. 事件发布到消息队列
   ↓
7. WebSocket 推送更新
   ↓
8. 用户收到响应
```

### 构建流程数据流

```
1. 提交构建配置
   ↓
2. 生成 Dockerfile
   ↓
3. 准备构建上下文
   ↓
4. 执行 Docker Build
   ↓
5. 流式推送日志
   ↓
6. 缓存构建层
   ↓
7. 推送到 Registry
   ↓
8. 更新构建状态
```

## 技术栈

### 后端技术

- **编程语言**: Python 3.8+
- **Web 框架**: Flask / FastAPI
- **异步框架**: asyncio, aiohttp
- **容器**: Docker SDK for Python
- **数据库**: PostgreSQL 13+
- **缓存**: Redis 6.0+
- **消息队列**: Redis Streams / RabbitMQ
- **RPC**: gRPC
- **监控**: Prometheus, Grafana

### 前端技术

- **终端**: xterm.js
- **实时通信**: WebSocket
- **UI 框架**: React / Vue.js
- **状态管理**: Redux / Vuex
- **构建工具**: Webpack / Vite

### 基础设施

- **容器化**: Docker, Docker Compose
- **编排**: Kubernetes (可选)
- **CI/CD**: GitLab CI, Jenkins
- **日志**: ELK Stack
- **追踪**: Jaeger

## 部署架构

### 单机部署

```
┌─────────────────────────────────┐
│      单机服务器                   │
│  ┌───────────────────────────┐  │
│  │  EulerMaker Optimizer     │  │
│  │  - Web Server             │  │
│  │  - WebSocket Server       │  │
│  │  - All Services           │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  Redis                    │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  PostgreSQL               │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  Docker Engine            │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

### 分布式部署

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  LB/Gateway  │───→│  Web Server  │───→│   Services   │
│   (Nginx)    │    │   (Flask)    │    │   (Python)   │
└──────────────┘    └──────────────┘    └──────────────┘
                            │                    │
                            ↓                    ↓
                    ┌──────────────┐    ┌──────────────┐
                    │    Redis     │    │  PostgreSQL  │
                    │   Cluster    │    │   Cluster    │
                    └──────────────┘    └──────────────┘
                                               │
                                               ↓
                                       ┌──────────────┐
                                       │    Docker    │
                                       │   Swarm/K8s  │
                                       └──────────────┘
```

### Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eulermaker-optimizer
spec:
  replicas: 3
  selector:
    matchLabels:
      app: optimizer
  template:
    metadata:
      labels:
        app: optimizer
    spec:
      containers:
        - name: optimizer
          image: eulermaker/optimizer:latest
          ports:
            - containerPort: 8080
          env:
            - name: REDIS_URL
              value: "redis://redis-service:6379"
```

## 扩展性设计

### 水平扩展

- **无状态设计**: API 服务器无状态，可任意扩展
- **会话存储**: 使用 Redis 集中存储会话
- **负载均衡**: 通过负载均衡器分发请求
- **消息队列**: 异步任务通过消息队列解耦

### 垂直扩展

- **资源配置**: 调整容器资源限制
- **连接池**: 优化数据库连接池大小
- **缓存策略**: 提高缓存命中率
- **性能调优**: JIT 编译、代码优化

### 功能扩展

- **插件系统**: 支持动态加载插件
- **钩子机制**: 在关键点注册钩子
- **接口抽象**: 核心接口可替换实现
- **配置驱动**: 通过配置启用/禁用功能

## 安全架构

### 认证授权

- **JWT Token**: 用于 API 认证
- **RBAC**: 基于角色的访问控制
- **OAuth2**: 支持第三方登录
- **API Key**: 用于服务间调用

### 网络安全

- **TLS/SSL**: 全链路加密
- **VPC**: 内部网络隔离
- **防火墙**: 端口和 IP 限制
- **DDoS 防护**: 流量清洗和限流

### 数据安全

- **加密存储**: 敏感数据加密
- **访问审计**: 记录所有操作
- **备份恢复**: 定期备份数据
- **数据脱敏**: 日志中隐藏敏感信息

### 容器安全

- **镜像扫描**: 漏洞扫描
- **最小权限**: 限制容器能力
- **资源隔离**: CPU、内存限制
- **网络隔离**: 容器网络隔离

---

**文档版本**: 1.0.0  
**最后更新**: 2025-09  
**维护者**: 张金荣