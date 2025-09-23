# Dockerfile
#  ******OSPP-2025-张金荣******
#
# EulerMaker Docker Optimizer 容器构建文件
#
# 用于构建EulerMaker Docker Optimizer的容器镜像
# 支持多阶段构建，优化镜像大小和安全性
#
# 构建方式：
#   docker build -t eulermaker/docker-optimizer:latest .
#   docker build --target development -t eulermaker/docker-optimizer:dev .
#   docker build --target production -t eulermaker/docker-optimizer:prod .
#
# 运行方式：
#   docker run -d -p 8000:8000 -v /var/run/docker.sock:/var/run/docker.sock eulermaker/docker-optimizer:latest

# =================================
# 阶段1：基础镜像和系统依赖
# =================================
FROM python:3.11-slim as base

# 设置标签信息
LABEL maintainer="张金荣 <3487232360@qq.com>" \
      version="1.0.0" \
      description="EulerMaker Docker Optimizer - 高性能Docker容器和RPM构建管理系统" \
      org.opencontainers.image.title="EulerMaker Docker Optimizer" \
      org.opencontainers.image.description="高性能Docker容器和RPM构建管理系统" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.authors="张金荣" \
      org.opencontainers.image.source="https://github.com/eulermaker/docker-optimizer" \
      org.opencontainers.image.documentation="https://eulermaker.github.io/docker-optimizer" \
      org.opencontainers.image.licenses="MIT"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Shanghai

# 创建非root用户
RUN groupadd -r eulermaker --gid=999 \
    && useradd -r -g eulermaker --uid=999 --shell=/bin/bash --create-home eulermaker

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    curl \
    wget \
    git \
    ca-certificates \
    gnupg \
    lsb-release \
    # 编译工具
    build-essential \
    gcc \
    g++ \
    make \
    cmake \
    # Python构建依赖
    python3-dev \
    python3-pip \
    # 系统库
    libssl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    # Docker CLI（用于容器管理）
    apt-transport-https \
    # RPM构建工具
    rpm \
    rpm2cpio \
    # 其他工具
    procps \
    htop \
    tree \
    vim-tiny \
    && rm -rf /var/lib/apt/lists/*

# 安装Docker CLI
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# 升级pip和安装基础Python包
RUN pip install --upgrade pip setuptools wheel

# =================================
# 阶段2：Python依赖安装
# =================================
FROM base as dependencies

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt setup.py ./
COPY src/__init__.py src/

# 创建pip缓存目录
RUN mkdir -p /root/.cache/pip

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 清理编译依赖（保留运行时需要的）
RUN apt-get purge -y --auto-remove \
    build-essential \
    gcc \
    g++ \
    make \
    cmake \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# =================================
# 阶段3：开发环境构建
# =================================
FROM dependencies as development

# 安装开发依赖
RUN pip install --no-cache-dir \
    pytest>=7.4.0 \
    pytest-asyncio>=0.21.0 \
    pytest-cov>=4.1.0 \
    black>=23.9.0 \
    isort>=5.12.0 \
    flake8>=6.1.0 \
    mypy>=1.6.0 \
    ipython \
    jupyter

# 复制源代码
COPY . /app/

# 修改所有权
RUN chown -R eulermaker:eulermaker /app

# 切换到非root用户
USER eulermaker

# 创建必要的目录
RUN mkdir -p /app/logs /app/data /app/tmp

# 暴露端口
EXPOSE 8000 9000

# 设置健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# 开发环境启动命令
CMD ["python", "-m", "src.main", "--debug", "--reload"]

# =================================
# 阶段4：生产环境构建
# =================================
FROM dependencies as production

# 复制源代码
COPY src/ /app/src/
COPY config/ /app/config/
COPY scripts/ /app/scripts/
COPY static/ /app/static/ 2>/dev/null || echo "Static directory not found, skipping"

# 复制配置文件
COPY docker-compose.yml /app/ 2>/dev/null || echo "Docker compose file not found, skipping"

# 创建应用目录结构
RUN mkdir -p /app/logs \
             /app/data \
             /app/tmp \
             /app/uploads \
             /app/builds \
             /app/cache

# 修改所有权
RUN chown -R eulermaker:eulermaker /app

# 切换到非root用户
USER eulermaker

# 设置工作目录
WORKDIR /app

# 暴露端口
EXPOSE 8000 9000

# 设置数据卷
VOLUME ["/app/logs", "/app/data", "/app/builds", "/var/run/docker.sock"]

# 设置健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/v1/health', timeout=5)" || exit 1

# 生产环境启动命令
CMD ["python", "-m", "src.main", "--host", "0.0.0.0", "--port", "8000"]

# =================================
# 阶段5：最小化生产镜像
# =================================
FROM python:3.11-slim as minimal

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Shanghai

# 创建非root用户
RUN groupadd -r eulermaker --gid=999 \
    && useradd -r -g eulermaker --uid=999 --shell=/bin/bash --create-home eulermaker

# 只安装运行时必需的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 从dependencies阶段复制Python环境
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# 复制应用代码
COPY --chown=eulermaker:eulermaker src/ /app/src/
COPY --chown=eulermaker:eulermaker config/ /app/config/

# 创建必要目录
RUN mkdir -p /app/logs /app/data /app/tmp \
    && chown -R eulermaker:eulermaker /app

# 切换到非root用户
USER eulermaker

# 设置工作目录
WORKDIR /app

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/ping || exit 1

# 启动命令
CMD ["python", "-m", "src.main"]

# =================================
# 默认构建阶段设置
# =================================
# 默认构建生产环境
FROM production

# 添加构建信息
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION

LABEL build_date=$BUILD_DATE \
      vcs_ref=$VCS_REF \
      version=$VERSION

# 显示构建信息
RUN echo "Build Date: $BUILD_DATE" && \
    echo "VCS Ref: $VCS_REF" && \
    echo "Version: $VERSION"

# =================================
# 多架构支持声明
# =================================
# 支持的架构：linux/amd64, linux/arm64, linux/arm/v7

# =================================
# 使用说明
# =================================
# 构建开发镜像：
#   docker build --target development -t eulermaker/docker-optimizer:dev .
#
# 构建生产镜像：
#   docker build --target production -t eulermaker/docker-optimizer:latest .
#
# 构建最小镜像：
#   docker build --target minimal -t eulermaker/docker-optimizer:minimal .
#
# 多架构构建：
#   docker buildx build --platform linux/amd64,linux/arm64 -t eulermaker/docker-optimizer:latest .
#
# 运行容器：
#   docker run -d \
#     --name eulermaker-optimizer \
#     -p 8000:8000 \
#     -p 9000:9000 \
#     -v /var/run/docker.sock:/var/run/docker.sock \
#     -v $(pwd)/logs:/app/logs \
#     -v $(pwd)/data:/app/data \
#     eulermaker/docker-optimizer:latest
#
# 开发模式运行：
#   docker run -it --rm \
#     -p 8000:8000 \
#     -v $(pwd):/app \
#     -v /var/run/docker.sock:/var/run/docker.sock \
#     eulermaker/docker-optimizer:dev