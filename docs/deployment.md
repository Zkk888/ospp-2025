# EulerMaker Docker Optimizer 部署指南

## 概述

本文档详细介绍了 EulerMaker Docker Optimizer 的部署方法，包括开发环境、测试环境和生产环境的部署配置。

## 系统要求

### 最低系统要求
- **操作系统**: Linux (推荐 EulerOS 2.0 SP8+、CentOS 7+、Ubuntu 18.04+)
- **CPU**: 2 核心 (推荐 4+ 核心)
- **内存**: 4GB RAM (推荐 8GB+)
- **磁盘**: 20GB 可用空间 (推荐 100GB+ 用于构建存储)
- **网络**: 千兆网络接口

### 推荐生产环境配置
- **CPU**: 8+ 核心
- **内存**: 16GB+ RAM
- **磁盘**: 500GB+ SSD
- **网络**: 10Gb 网络接口

### 软件依赖
- **Docker**: 20.10+ (推荐最新稳定版)
- **Docker Compose**: 1.29+ (可选，用于编排部署)
- **Python**: 3.8+ (如果从源码部署)
- **Git**: 2.0+ (用于代码管理)

## 快速开始

### 方式一：Docker Compose 部署（推荐）

1. **下载项目**
```bash
git clone https://github.com/eulermaker/docker-optimizer.git
cd eulermaker-docker-optimizer
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑配置文件
vim .env
```

3. **启动服务**
```bash
docker-compose up -d
```

4. **验证部署**
```bash
# 检查服务状态
docker-compose ps

# 检查服务健康状态
curl http://localhost:8080/health
```

### 方式二：单容器部署

1. **拉取镜像**
```bash
docker pull eulermaker/docker-optimizer:latest
```

2. **运行容器**
```bash
docker run -d \
  --name docker-optimizer \
  -p 8080:8080 \
  -p 9090:9090 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /opt/optimizer/data:/app/data \
  -v /opt/optimizer/logs:/app/logs \
  -e API_HOST=0.0.0.0 \
  -e API_PORT=8080 \
  -e RPC_PORT=9090 \
  eulermaker/docker-optimizer:latest
```

## 详细部署配置

### 环境变量配置

创建并配置 `.env` 文件：

```bash
# === 基础配置 ===
# 应用名称
APP_NAME=eulermaker-docker-optimizer

# 运行环境 (development/testing/production)
ENVIRONMENT=production

# 日志级别 (DEBUG/INFO/WARN/ERROR)
LOG_LEVEL=INFO

# === 服务端口配置 ===
# Web API 服务端口
API_HOST=0.0.0.0
API_PORT=8080

# RPC 服务端口
RPC_HOST=0.0.0.0
RPC_PORT=9090

# WebSocket 端口 (通常与API端口相同)
WS_HOST=0.0.0.0
WS_PORT=8080

# === Docker 配置 ===
# Docker Socket 路径
DOCKER_SOCKET=/var/run/docker.sock

# Docker API 版本
DOCKER_API_VERSION=auto

# 容器资源限制
MAX_CONTAINERS=50
MAX_CONCURRENT_BUILDS=10

# === 存储配置 ===
# 数据存储目录
DATA_DIR=/app/data

# 日志存储目录
LOG_DIR=/app/logs

# 构建工作目录
WORKSPACE_DIR=/app/workspace

# RPM 构建输出目录
RPM_OUTPUT_DIR=/app/rpms

# === 安全配置 ===
# API 密钥 (生产环境必须修改)
API_SECRET_KEY=your-super-secret-key-change-in-production

# JWT 密钥
JWT_SECRET_KEY=your-jwt-secret-key

# API 访问令牌有效期 (小时)
ACCESS_TOKEN_EXPIRE_HOURS=24

# === 性能调优 ===
# 工作进程数量 (0表示自动检测)
WORKER_PROCESSES=0

# 单个工作进程的线程数
WORKER_THREADS=4

# 请求超时时间 (秒)
REQUEST_TIMEOUT=300

# 构建任务超时时间 (秒)
BUILD_TIMEOUT=3600

# === 监控配置 ===
# 是否启用指标收集
ENABLE_METRICS=true

# 指标收集间隔 (秒)
METRICS_INTERVAL=30

# 是否启用健康检查
ENABLE_HEALTH_CHECK=true

# === 数据库配置 (可选，用于持久化) ===
# 数据库类型 (sqlite/postgresql/mysql)
DB_TYPE=sqlite

# SQLite 数据库文件路径 (仅当 DB_TYPE=sqlite 时使用)
DB_FILE=/app/data/optimizer.db

# PostgreSQL 配置 (仅当 DB_TYPE=postgresql 时使用)
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# POSTGRES_DB=docker_optimizer
# POSTGRES_USER=optimizer
# POSTGRES_PASSWORD=your-password

# === Redis 配置 (可选，用于缓存和队列) ===
# 是否启用 Redis
ENABLE_REDIS=false

# Redis 连接配置
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_DB=0
# REDIS_PASSWORD=

# === 通知配置 ===
# 是否启用邮件通知
ENABLE_EMAIL_NOTIFICATION=false

# SMTP 配置
# SMTP_HOST=smtp.example.com
# SMTP_PORT=587
# SMTP_USER=notification@example.com
# SMTP_PASSWORD=your-password
# SMTP_FROM=notification@example.com

# === 外部服务集成 ===
# Prometheus 监控地址 (可选)
# PROMETHEUS_URL=http://prometheus:9090

# Grafana 仪表盘地址 (可选)
# GRAFANA_URL=http://grafana:3000
```

### Docker Compose 配置

完整的 `docker-compose.yml` 配置示例：

```yaml
version: '3.8'

services:
  # 主应用服务
  docker-optimizer:
    image: eulermaker/docker-optimizer:latest
    container_name: docker-optimizer-app
    restart: unless-stopped
    ports:
      - "${API_PORT:-8080}:8080"
      - "${RPC_PORT:-9090}:9090"
    volumes:
      # Docker socket 挂载 (必需)
      - /var/run/docker.sock:/var/run/docker.sock:rw
      # 数据持久化
      - ./data:/app/data
      - ./logs:/app/logs
      - ./workspace:/app/workspace
      - ./rpms:/app/rpms
      # 配置文件挂载
      - ./config:/app/config:ro
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - API_HOST=0.0.0.0
      - API_PORT=8080
      - RPC_PORT=9090
      - DOCKER_SOCKET=/var/run/docker.sock
      - DATA_DIR=/app/data
      - LOG_DIR=/app/logs
      - WORKSPACE_DIR=/app/workspace
      - RPM_OUTPUT_DIR=/app/rpms
    env_file:
      - .env
    depends_on:
      - redis
      - postgres
    networks:
      - optimizer-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # Redis 缓存服务 (可选)
  redis:
    image: redis:7-alpine
    container_name: docker-optimizer-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    networks:
      - optimizer-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  # PostgreSQL 数据库 (可选)
  postgres:
    image: postgres:14-alpine
    container_name: docker-optimizer-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-docker_optimizer}
      POSTGRES_USER: ${POSTGRES_USER:-optimizer}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-password}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - optimizer-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-optimizer}"]
      interval: 10s
      timeout: 5s
      retries: 3

  # Prometheus 监控 (可选)
  prometheus:
    image: prom/prometheus:latest
    container_name: docker-optimizer-prometheus
    restart: unless-stopped
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    networks:
      - optimizer-network

  # Grafana 仪表盘 (可选)
  grafana:
    image: grafana/grafana:latest
    container_name: docker-optimizer-grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    networks:
      - optimizer-network
    depends_on:
      - prometheus

# 网络配置
networks:
  optimizer-network:
    driver: bridge

# 数据卷配置
volumes:
  redis-data:
    driver: local
  postgres-data:
    driver: local
  prometheus-data:
    driver: local
  grafana-data:
    driver: local
```

### 生产环境部署

#### 1. 系统准备

```bash
# 更新系统
sudo yum update -y  # CentOS/RHEL
# 或 sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable docker
sudo systemctl start docker

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 创建部署目录
sudo mkdir -p /opt/eulermaker-docker-optimizer
cd /opt/eulermaker-docker-optimizer
```

#### 2. 部署应用

```bash
# 下载部署文件
wget https://github.com/eulermaker/docker-optimizer/releases/latest/download/deployment.tar.gz
tar -xzf deployment.tar.gz

# 配置环境
cp .env.example .env
# 编辑生产环境配置
sudo vim .env

# 创建必要的目录
sudo mkdir -p data logs workspace rpms

# 设置权限
sudo chown -R 1000:1000 data logs workspace rpms

# 启动服务
sudo docker-compose up -d

# 检查服务状态
sudo docker-compose ps
sudo docker-compose logs -f
```

#### 3. 配置防火墙

```bash
# CentOS/RHEL Firewall 配置
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --permanent --add-port=9090/tcp
sudo firewall-cmd --reload

# Ubuntu UFW 配置
sudo ufw allow 8080/tcp
sudo ufw allow 9090/tcp
sudo ufw reload
```

#### 4. 配置反向代理（Nginx）

```bash
# 安装 Nginx
sudo yum install nginx -y  # CentOS/RHEL
# 或 sudo apt install nginx -y  # Ubuntu/Debian

# 配置反向代理
sudo vim /etc/nginx/conf.d/docker-optimizer.conf
```

Nginx 配置文件内容：

```nginx
upstream docker_optimizer_backend {
    least_conn;
    server 127.0.0.1:8080 max_fails=3 fail_timeout=30s;
}

upstream docker_optimizer_ws {
    server 127.0.0.1:8080;
}

server {
    listen 80;
    server_name your-domain.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 证书配置
    ssl_certificate /path/to/your/certificate.crt;
    ssl_certificate_key /path/to/your/private.key;
    
    # SSL 优化配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers EECDH+AESGCM:EDH+AESGCM;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 安全头配置
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # 日志配置
    access_log /var/log/nginx/docker-optimizer.access.log;
    error_log /var/log/nginx/docker-optimizer.error.log;

    # API 路由
    location /api/ {
        proxy_pass http://docker_optimizer_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时配置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # 请求大小限制
        client_max_body_size 100M;
    }

    # WebSocket 路由
    location /ws/ {
        proxy_pass http://docker_optimizer_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 超时配置
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }

    # 健康检查路由
    location /health {
        proxy_pass http://docker_optimizer_backend;
        access_log off;
    }

    # 静态文件服务
    location /static/ {
        proxy_pass http://docker_optimizer_backend;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # 默认路由
    location / {
        proxy_pass http://docker_optimizer_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启动 Nginx：

```bash
sudo systemctl enable nginx
sudo systemctl start nginx
sudo nginx -t  # 测试配置
```

## 监控和日志

### 1. 应用监控

使用 Prometheus + Grafana 监控应用状态：

```bash
# 启动监控服务
sudo docker-compose --profile monitoring up -d

# 访问监控面板
# Prometheus: http://your-domain:9090
# Grafana: http://your-domain:3000 (admin/admin)
```

### 2. 日志管理

配置日志轮转：

```bash
sudo vim /etc/logrotate.d/docker-optimizer
```

日志轮转配置：

```
/opt/eulermaker-docker-optimizer/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    copytruncate
    notifempty
    create 644 root root
}
```

### 3. 系统服务配置

创建系统服务文件：

```bash
sudo vim /etc/systemd/system/docker-optimizer.service
```

服务配置内容：

```ini
[Unit]
Description=EulerMaker Docker Optimizer
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/eulermaker-docker-optimizer
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable docker-optimizer
sudo systemctl start docker-optimizer
```

## 安全配置

### 1. 网络安全

```bash
# 限制对管理端口的访问
sudo iptables -A INPUT -p tcp --dport 9090 -s 10.0.0.0/8 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 9090 -j DROP

# 保存规则
sudo iptables-save > /etc/iptables/rules.v4
```

### 2. 文件权限

```bash
# 设置敏感文件权限
sudo chmod 600 .env
sudo chmod 600 config/logging.conf
sudo chown root:root .env config/logging.conf
```

### 3. 容器安全

在 `docker-compose.yml` 中添加安全配置：

```yaml
security_opt:
  - no-new-privileges:true
  - apparmor:docker-default
read_only: true
tmpfs:
  - /tmp:noexec,nosuid,size=100m
```

## 备份和恢复

### 1. 数据备份脚本

```bash
sudo vim /opt/scripts/backup.sh
```

备份脚本内容：

```bash
#!/bin/bash

BACKUP_DIR="/opt/backups/docker-optimizer"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="docker-optimizer-backup-${TIMESTAMP}.tar.gz"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 停止服务 (可选)
# sudo docker-compose -f /opt/eulermaker-docker-optimizer/docker-compose.yml stop

# 备份数据
cd /opt/eulermaker-docker-optimizer
tar -czf "$BACKUP_DIR/$BACKUP_FILE" \
    data/ \
    logs/ \
    .env \
    docker-compose.yml \
    config/

# 备份数据库 (如果使用 PostgreSQL)
if [ -f "docker-compose.yml" ] && grep -q "postgres" docker-compose.yml; then
    sudo docker-compose exec -T postgres pg_dump -U optimizer docker_optimizer > "$BACKUP_DIR/db-backup-${TIMESTAMP}.sql"
fi

# 清理老备份 (保留30天)
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.sql" -mtime +30 -delete

# 重启服务 (如果之前停止了)
# sudo docker-compose -f /opt/eulermaker-docker-optimizer/docker-compose.yml start

echo "备份完成: $BACKUP_DIR/$BACKUP_FILE"
```

设置定时备份：

```bash
sudo chmod +x /opt/scripts/backup.sh
sudo crontab -e

# 添加每日凌晨2点备份
0 2 * * * /opt/scripts/backup.sh
```

### 2. 恢复数据

```bash
# 恢复备份数据
cd /opt/eulermaker-docker-optimizer
sudo docker-compose down
tar -xzf /opt/backups/docker-optimizer/docker-optimizer-backup-2025-09_020000.tar.gz
sudo docker-compose up -d

# 恢复数据库 (如果需要)
sudo docker-compose exec -T postgres psql -U optimizer -d docker_optimizer < /opt/backups/docker-optimizer/db-backup-20250915_020000.sql
```

## 故障排除

### 常见问题和解决方案

1. **服务无法启动**
```bash
# 检查日志
sudo docker-compose logs docker-optimizer

# 检查配置
sudo docker-compose config

# 检查端口占用
sudo netstat -tlnp | grep 8080
```

2. **无法连接 Docker**
```bash
# 检查 Docker 服务状态
sudo systemctl status docker

# 检查 Docker socket 权限
ls -la /var/run/docker.sock

# 重启 Docker 服务
sudo systemctl restart docker
```

3. **内存不足**
```bash
# 检查系统资源
free -h
df -h

# 清理 Docker 缓存
sudo docker system prune -a
```

4. **网络连接问题**
```bash
# 检查防火墙状态
sudo firewall-cmd --list-all

# 测试端口连通性
telnet localhost 8080
```

## 性能优化

### 1. 系统级优化

```bash
# 增加文件描述符限制
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# 优化内核参数
echo "net.core.rmem_max = 134217728" >> /etc/sysctl.conf
echo "net.core.wmem_max = 134217728" >> /etc/sysctl.conf
echo "net.ipv4.tcp_rmem = 4096 87380 134217728" >> /etc/sysctl.conf
echo "net.ipv4.tcp_wmem = 4096 65536 134217728" >> /etc/sysctl.conf
sysctl -p
```

### 2. 应用级优化

在 `.env` 文件中调整性能参数：

```bash
# 增加工作进程数
WORKER_PROCESSES=8

# 调整超时时间
REQUEST_TIMEOUT=600
BUILD_TIMEOUT=7200

# 启用缓存
ENABLE_REDIS=true
REDIS_CACHE_TTL=3600
```

## 版本升级

### 平滑升级流程

1. **备份现有数据**
```bash
/opt/scripts/backup.sh
```

2. **拉取新版本镜像**
```bash
sudo docker-compose pull
```

3. **滚动更新**
```bash
sudo docker-compose up -d --no-deps docker-optimizer
```

4. **验证升级**
```bash
# 检查服务状态
curl http://localhost:8080/health

# 检查版本信息
curl http://localhost:8080/version
```

5. **回滚操作**（如有问题）
```bash
# 回滚到之前的版本
sudo docker-compose down
sudo docker tag eulermaker/docker-optimizer:previous eulermaker/docker-optimizer:latest
sudo docker-compose up -d
```
