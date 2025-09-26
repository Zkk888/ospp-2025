# 34. setup.py
"""
******OSPP-2025-张金荣******

EulerMaker Docker Optimizer 项目安装配置文件

定义项目的元数据、依赖关系、安装选项等信息，
使得项目可以通过 pip install 进行安装和分发。

支持的安装方式：
- pip install eulermaker-docker-optimizer
- pip install -e .  # 开发模式安装
- python setup.py install
- python setup.py develop

特性：
- 自动读取README.md作为长描述
- 从__init__.py读取版本信息
- 支持可选依赖组合
- 定义命令行入口点
- 支持不同平台的特定依赖
"""

import os
import sys
from pathlib import Path
from setuptools import setup, find_packages

# 获取项目根目录
HERE = Path(__file__).parent.resolve()
SRC_DIR = HERE / "src"

# 读取README.md作为长描述
def get_long_description():
    """读取README.md文件作为长描述"""
    readme_path = HERE / "README.md"
    if readme_path.exists():
        with open(readme_path, "r", encoding="utf-8") as f:
            return f.read()
    return "EulerMaker Docker Optimizer - 高性能Docker容器和RPM构建管理系统"

# 从源代码读取版本信息
def get_version():
    """从src/__init__.py读取版本信息"""
    try:
        # 添加src目录到路径以便导入
        sys.path.insert(0, str(SRC_DIR))
        from src import __version__
        return __version__
    except ImportError:
        # 如果无法导入，尝试直接读取文件
        init_file = SRC_DIR / "__init__.py"
        if init_file.exists():
            with open(init_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("__version__"):
                        return line.split("=")[1].strip().strip('"\'')
        return "1.0.0"  # 默认版本

# 读取requirements.txt中的依赖
def get_requirements():
    """读取requirements.txt中的生产依赖"""
    requirements_file = HERE / "requirements.txt"
    if not requirements_file.exists():
        return []

    requirements = []
    with open(requirements_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过注释、空行和开发依赖
            if (line and
                    not line.startswith("#") and
                    not line.startswith("-") and
                    "pytest" not in line and
                    "black" not in line and
                    "isort" not in line and
                    "flake8" not in line and
                    "mypy" not in line and
                    "pre-commit" not in line and
                    "mkdocs" not in line and
                    "memory-profiler" not in line and
                    "line-profiler" not in line and
                    "py-spy" not in line):

                # 处理条件依赖
                if ";" in line:
                    requirements.append(line)
                else:
                    requirements.append(line)

    return requirements

# 定义可选依赖组合
def get_extras_require():
    """定义可选依赖组合"""
    return {
        # 开发依赖
        "dev": [
            "pytest>=7.4.0,<8.0.0",
            "pytest-asyncio>=0.21.0,<0.22.0",
            "pytest-cov>=4.1.0,<5.0.0",
            "pytest-mock>=3.12.0,<4.0.0",
            "black>=23.9.0,<24.0.0",
            "isort>=5.12.0,<6.0.0",
            "flake8>=6.1.0,<7.0.0",
            "mypy>=1.6.0,<1.7.0",
            "pre-commit>=3.5.0,<4.0.0",
        ],

        # 测试依赖
        "test": [
            "pytest>=7.4.0,<8.0.0",
            "pytest-asyncio>=0.21.0,<0.22.0",
            "pytest-cov>=4.1.0,<5.0.0",
            "pytest-mock>=3.12.0,<4.0.0",
            "httpx>=0.25.0,<0.26.0",
        ],

        # 文档依赖
        "docs": [
            "mkdocs>=1.5.0,<2.0.0",
            "mkdocs-material>=9.4.0,<10.0.0",
            "mkdocs-swagger-ui-tag>=0.6.0",
        ],

        # 性能分析依赖
        "profiling": [
            "memory-profiler>=0.61.0,<1.0.0",
            "line-profiler>=4.1.0,<5.0.0",
            "py-spy>=0.3.14,<1.0.0",
        ],

        # 监控依赖
        "monitoring": [
            "prometheus-client>=0.19.0,<0.20.0",
            "opentelemetry-api>=1.21.0,<1.22.0",
            "structlog>=23.2.0,<24.0.0",
        ],

        # Kubernetes支持
        "k8s": [
            "kubernetes>=28.1.0,<29.0.0",
        ],

        # 数据库支持
        "database": [
            "redis>=5.0.0,<6.0.0",
            "aiosqlite>=0.19.0,<0.20.0",
            "sqlalchemy>=2.0.0,<2.1.0",
        ],

        # 邮件通知支持
        "email": [
            "aiosmtplib>=3.0.0,<4.0.0",
        ],

        # 图像处理支持
        "imaging": [
            "Pillow>=10.0.0,<11.0.0",
        ],

        # 性能优化
        "performance": [
            "ujson>=5.8.0,<6.0.0",
            "orjson>=3.9.0,<3.10.0",
            "cython>=3.0.0,<4.0.0",
        ],

        # 完整功能（所有可选依赖）
        "all": [
            # 这里会在后面自动生成
        ],
    }

# 获取所有可选依赖
def get_all_extras():
    """获取所有可选依赖的组合"""
    extras = get_extras_require()
    all_deps = []
    for key, deps in extras.items():
        if key != "all":
            all_deps.extend(deps)
    # 去重
    return list(set(all_deps))

# 定义项目分类器
def get_classifiers():
    """项目分类器"""
    return [
        # 开发状态
        "Development Status :: 4 - Beta",

        # 目标受众
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Information Technology",

        # 主题分类
        "Topic :: Software Development :: Build Tools",
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Containers",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Software Development :: Libraries :: Python Modules",

        # 许可证
        "License :: OSI Approved :: MIT License",

        # 编程语言
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3 :: Only",

        # 操作系统
        "Operating System :: OS Independent",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",

        # 框架
        "Framework :: AsyncIO",
        "Framework :: FastAPI",

        # 环境
        "Environment :: Web Environment",
        "Environment :: Console",
        "Environment :: No Input/Output (Daemon)",

        # 自然语言
        "Natural Language :: Chinese (Simplified)",
        "Natural Language :: English",
    ]

# 定义入口点
def get_entry_points():
    """定义命令行入口点"""
    return {
        "console_scripts": [
            # 主程序入口
            "eulermaker-optimizer=src.main:run_sync",
            "emo=src.main:run_sync",  # 简短别名

            # 服务管理命令
            "emo-server=src.main:run_sync",
            "emo-web=src.api.web_server:dev_server",
            "emo-rpc=src.api.rpc_server:start_rpc_server",

            # 工具命令
            "emo-docker=src.core.docker_manager:main",
            "emo-build=src.core.build_manager:main",
            "emo-probe=src.core.probe_manager:main",
        ],

        # 插件入口点（用于扩展）
        "eulermaker.optimizer.plugins": [
            # 预留插件入口
        ],

        # API扩展入口点
        "eulermaker.optimizer.api": [
            # 预留API扩展入口
        ],
    }

# 获取项目关键词
def get_keywords():
    """项目关键词"""
    return [
        "docker", "container", "rpm", "build", "automation",
        "devops", "ci-cd", "fastapi", "websocket", "rpc",
        "monitoring", "linux", "eulermaker", "optimization",
        "web-terminal", "xterm", "async", "python3"
    ]

# 主安装配置
def main():
    """主安装函数"""
    # 生成完整的可选依赖
    extras_require = get_extras_require()
    extras_require["all"] = get_all_extras()

    setup(
        # 基本信息
        name="eulermaker-docker-optimizer",
        version=get_version(),
        author="张金荣",
        author_email="3487232360@qq.com",
        maintainer="张金荣",
        maintainer_email="3487232360@qq.com",

        # 描述信息
        description="高性能Docker容器和RPM构建管理系统",
        long_description=get_long_description(),
        long_description_content_type="text/markdown",

        # 项目链接
        url="https://github.com/eulermaker/docker-optimizer",
        project_urls={
            "Homepage": "https://github.com/eulermaker/docker-optimizer",
            "Documentation": "https://eulermaker.github.io/docker-optimizer",
            "Repository": "https://github.com/eulermaker/docker-optimizer.git",
            "Bug Tracker": "https://github.com/eulermaker/docker-optimizer/issues",
            "Changelog": "https://github.com/eulermaker/docker-optimizer/blob/main/CHANGELOG.md",
        },

        # 许可证
        license="MIT",

        # 分类和关键词
        classifiers=get_classifiers(),
        keywords=get_keywords(),

        # Python版本要求
        python_requires=">=3.8",

        # 包发现和配置
        packages=find_packages(where="src"),
        package_dir={"": "src"},

        # 包含额外文件
        include_package_data=True,
        package_data={
            "": [
                "*.txt", "*.md", "*.yml", "*.yaml", "*.json", "*.conf",
                "static/**/*", "templates/**/*", "config/**/*"
            ],
        },

        # 依赖管理
        install_requires=get_requirements(),
        extras_require=extras_require,

        # 入口点
        entry_points=get_entry_points(),

        # 平台和环境
        platforms=["any"],

        # 压缩和分发选项
        zip_safe=False,  # 不使用zip格式，便于调试

        # 数据文件
        data_files=[
            ("etc/eulermaker-optimizer", ["config/settings.py", "config/logging.conf"]),
            ("share/doc/eulermaker-optimizer", ["README.md"]),
        ] if os.path.exists("config/settings.py") else [],

        # 命令类扩展
        cmdclass={
            # 可以在这里添加自定义安装命令
        },

        # 测试配置
        test_suite="tests",
        tests_require=extras_require["test"],
    )

if __name__ == "__main__":
    main()