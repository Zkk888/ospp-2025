# OSPP2025-EulerMaker
OSPP 2025 OpenEuler EulerMaker
###目录结构
```text
eulermaker-docker-optimizer/
├── README.md
├── requirements.txt
├── setup.py
├── Dockerfile
├── docker-compose.yml
├── config/
│   ├── __init__.py
│   ├── settings.py                 # 全局配置
│   └── logging.conf               # 日志配置
├── src/
│   ├── __init__.py
│   ├── main.py                    # 主入口文件
│   ├── core/                      # 核心模块
│   │   ├── __init__.py
│   │   ├── docker_manager.py      # Docker API封装管理器
│   │   ├── container_lifecycle.py # 容器生命周期管理
│   │   ├── build_manager.py       # RPM构建管理器
│   │   └── probe_manager.py       # 探针管理器
│   ├── api/                       # API接口层
│   │   ├── __init__.py
│   │   ├── rpc_server.py          # RPC接口服务器
│   │   ├── web_server.py          # Web API服务器
│   │   ├── websocket_server.py    # WebSocket服务器(xterm.js)
│   │   └── routes/                # API路由
│   │       ├── __init__.py
│   │       ├── container_routes.py
│   │       ├── build_routes.py
│   │       └── terminal_routes.py
│   ├── services/                  # 业务服务层
│   │   ├── __init__.py
│   │   ├── container_service.py   # 容器服务
│   │   ├── build_service.py       # 构建服务
│   │   ├── terminal_service.py    # 终端服务
│   │   └── probe_service.py       # 探针服务
│   ├── models/                    # 数据模型
│   │   ├── __init__.py
│   │   ├── container_model.py     # 容器模型
│   │   ├── build_model.py         # 构建任务模型
│   │   └── probe_model.py         # 探针模型
│   ├── utils/                     # 工具类
│   │   ├── __init__.py
│   │   ├── logger.py              # 日志工具
│   │   ├── exceptions.py          # 自定义异常
│   │   ├── helpers.py             # 辅助函数
│   │   └── validators.py          # 验证器
│   └── static/                    # 静态文件
│       ├── css/
│       ├── js/
│       │   └── xterm-integration.js  # xterm.js集成
│       └── templates/
│           └── terminal.html      # 终端页面模板
├── tests/                         # 测试目录
│   ├── __init__.py
│   ├── conftest.py               # pytest配置
│   ├── unit/                     # 单元测试
│   │   ├── __init__.py
│   │   ├── test_docker_manager.py
│   │   ├── test_container_service.py
│   │   └── test_build_service.py
│   ├── integration/              # 集成测试
│   │   ├── __init__.py
│   │   ├── test_api_endpoints.py
│   │   └── test_container_lifecycle.py
│   └── fixtures/                 # 测试数据
│       ├── __init__.py
│       └── sample_configs.py
├── scripts/                      # 脚本目录
│   ├── start.sh                  # 启动脚本
│   ├── stop.sh                   # 停止脚本
│   ├── setup_env.sh              # 环境设置脚本
│   └── migrate.py                # 数据迁移脚本
├── docs/                         # 文档目录
│   ├── api.md                    # API文档
│   ├── architecture.md           # 架构文档
│   └── deployment.md             # 部署文档
└── examples/                     # 示例代码
    ├── __init__.py
    ├── basic_usage.py            # 基本使用示例
        └── advanced_usage.py         # 高级使用示例
```
###模块说明
```text
核心模块说明
1. src/core/ - 核心模块

docker_manager.py: Docker Engine API的异步封装，基于aiodocker
container_lifecycle.py: 容器完整生命周期管理
build_manager.py: RPM包构建流程管理
probe_manager.py: 环境探针和监控功能

2. src/api/ - API接口层

rpc_server.py: 统一RPC接口服务器
web_server.py: HTTP REST API服务器
websocket_server.py: WebSocket服务器，支持xterm.js终端接入
routes/: API路由模块化管理

3. src/services/ - 业务服务层

container_service.py: 容器相关业务逻辑
build_service.py: 构建任务业务逻辑
terminal_service.py: 终端交互业务逻辑
probe_service.py: 探针和监控业务逻辑

4. src/models/ - 数据模型

定义容器、构建任务、探针等数据结构
提供数据验证和序列化功能

5. src/utils/ - 工具模块

logger.py: 统一日志管理
exceptions.py: 自定义异常类
helpers.py: 通用辅助函数
validators.py: 数据验证器

技术如下
异步架构: 全面使用Python asyncio，配合aiohttp和aiodocker
模块化设计: 分层架构，便于维护和扩展
RPC统一接口: 提供一致的调用接口
Web终端集成: 支持xterm.js的Web终端功能
容器生命周期管理: 完整容器创建、运行、监控、销毁流程
探针扩展: 灵活环境探针和监控机制
```
###开源编写阶段
```text
第一阶段：基础设施层
1. config/__init__.py
2. config/settings.py           # 全局配置，其他模块都会用到
3. src/utils/__init__.py
4. src/utils/exceptions.py      # 自定义异常，优先定义
5. src/utils/logger.py          # 日志工具，调试必需
6. src/utils/helpers.py         # 辅助函数
7. src/utils/validators.py      # 验证器
8. config/logging.conf          # 日志配置文件

第二阶段：数据模型层
9. src/models/__init__.py
10. src/models/container_model.py   # 容器数据模型
11. src/models/build_model.py       # 构建任务数据模型
12. src/models/probe_model.py       # 探针数据模型

第三阶段：核心功能层
13. src/core/__init__.py 
14. src/core/docker_manager.py      # Docker API封装，最基础的核心
15. src/core/container_lifecycle.py # 容器生命周期，依赖docker_manager
16. src/core/probe_manager.py       # 探针管理，依赖docker_manager
17. src/core/build_manager.py       # 构建管理，依赖上述所有核心模块

第四阶段：业务服务层
18. src/services/__init__.py
19. src/services/container_service.py  # 容器服务，封装容器业务逻辑
20. src/services/probe_service.py      # 探针服务
21. src/services/build_service.py      # 构建服务，可能依赖其他服务
22. src/services/terminal_service.py   # 终端服务，比较独立

第五阶段：API接口层
23. src/api/__init__.py
24. src/api/routes/__init__.py
25. src/api/routes/container_routes.py  # 容器相关API路由
26. src/api/routes/build_routes.py      # 构建相关API路由
27. src/api/routes/terminal_routes.py **  # 终端相关API路由
28. src/api/web_server.py              # Web服务器，集成所有路由
29. src/api/websocket_server.py        # WebSocket服务器，用于xterm.js
30. src/api/rpc_server.py              # RPC服务器，统一接口

第六阶段：主程序和项目配置
31. src/__init__.py
32. src/main.py                     # 主入口文件，整合所有服务
33. requirements.txt                # 依赖包列表
34. setup.py                       # 项目安装配置
35. Dockerfile                     # Docker容器配置
36. docker-compose.yml             # Docker编排配置

第七阶段：前端静态文件
37. src/static/templates/terminal.html    # 终端页面模板
38. src/static/js/xterm-integration.js    # xterm.js集成脚本
39. src/static/css/terminal.css           # 样式文件

第八阶段：脚本和工具
40. scripts/setup_env.sh           # 环境设置脚本
41. scripts/start.sh               # 启动脚本
42. scripts/stop.sh                # 停止脚本
43. scripts/migrate.py             # 数据迁移脚本

第九阶段：测试代码
44. tests/__init__.py
45. tests/conftest.py              # pytest配置
46. tests/fixtures/__init__.py
47. tests/fixtures/sample_configs.py
48. tests/unit/__init__.py
49. tests/unit/test_docker_manager.py
50. tests/unit/test_container_service.py
51. tests/unit/test_build_service.py
52. tests/integration/__init__.py
53. tests/integration/test_api_endpoints.py
54. tests/integration/test_container_lifecycle.py

第十阶段：文档和示例
55. README.md                      # 项目说明文档
56. docs/architecture.md           # 架构文档
57. docs/api.md                   # API文档
58. docs/deployment.md            # 部署文档
59. examples/__init__.py
60. examples/basic_usage.py       # 基本使用示例
61. examples/advanced_usage.py    # 高级使用示例


从基础设施开始，逐步构建上层功能
先写被依赖的模块，后写依赖其他模块的代码
核心功能模块优先于业务逻辑模块
功能代码完成后再编写测试，确保有具体实现可测试
代码稳定后编写文档，避免频繁更新

导师建议：
每完成一个阶段，都应该进行简单的单元测试验证
在第五阶段完成后，就可以启动基本服务进行功能测试
可以在第六阶段完成后就开始集成测试
```