#!/bin/bash
# 40. scripts/setup_env.sh
# EulerMaker Docker Optimizer 环境设置脚本
#
# ******OSPP-2025-张金荣******
#
# 脚本用于自动化设置开发和生产环境，包括：
# - 检查系统依赖
# - 安装Docker和必要工具
# - 创建项目目录结构
# - 生成配置文件
# - 设置权限
# - 初始化数据库（如果需要）
# - 配置系统服务
#
# 使用方式：
#   ./scripts/setup_env.sh [OPTIONS]
#   ./scripts/setup_env.sh --dev        # 开发环境
#   ./scripts/setup_env.sh --prod       # 生产环境
#   ./scripts/setup_env.sh --docker     # Docker环境
#   ./scripts/setup_env.sh --help       # 显示帮助

set -euo pipefail  # 严格错误处理

# ====================================
# 全局变量和配置
# ====================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="eulermaker-docker-optimizer"

# 版本信息
SCRIPT_VERSION="1.0.0"
MIN_PYTHON_VERSION="3.8"
MIN_DOCKER_VERSION="20.10"
MIN_DOCKER_COMPOSE_VERSION="2.0"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 环境变量
ENVIRONMENT="dev"
FORCE_INSTALL=false
SKIP_DOCKER=false
SKIP_PYTHON=false
SKIP_DEPS=false
VERBOSE=false
DRY_RUN=false

# 系统信息
OS_TYPE=""
OS_VERSION=""
ARCH=""
PYTHON_CMD=""
PIP_CMD=""

# ====================================
# 工具函数
# ====================================
log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${PURPLE}[DEBUG]${NC} $1"
    fi
}

print_banner() {
    echo -e "${CYAN}"
    cat << "EOF"
    ╔═══════════════════════════════════════════════╗
    ║                                               ║
    ║    EulerMaker Docker Optimizer Setup         ║
    ║                                               ║
    ║    自动化环境配置脚本                           ║
    ║                                               ║
    ╚═══════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    echo "版本: $SCRIPT_VERSION"
    echo "环境: $ENVIRONMENT"
    echo "项目根目录: $PROJECT_ROOT"
    echo ""
}

show_help() {
    cat << EOF
EulerMaker Docker Optimizer 环境设置脚本

使用方式:
    $0 [选项]

选项:
    --dev               设置开发环境 (默认)
    --prod              设置生产环境
    --docker            Docker容器环境

    --force             强制重新安装所有依赖
    --skip-docker       跳过Docker相关设置
    --skip-python       跳过Python相关设置
    --skip-deps         跳过依赖包安装

    --verbose, -v       详细输出
    --dry-run           演练模式，不执行实际操作
    --help, -h          显示此帮助信息

示例:
    $0                  # 设置开发环境
    $0 --prod           # 设置生产环境
    $0 --dev --verbose  # 开发环境，详细输出
    $0 --docker         # Docker环境设置

EOF
}

# ====================================
# 系统检测函数
# ====================================
detect_system() {
    log_info "检测系统信息..."

    # 检测操作系统
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS_TYPE="linux"
        if command -v lsb_release >/dev/null 2>&1; then
            OS_VERSION=$(lsb_release -d | cut -d: -f2 | xargs)
        elif [[ -f /etc/os-release ]]; then
            OS_VERSION=$(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"')
        else
            OS_VERSION="Unknown Linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS_TYPE="macos"
        OS_VERSION=$(sw_vers -productName) $(sw_vers -productVersion)
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        OS_TYPE="windows"
        OS_VERSION="Windows"
    else
        OS_TYPE="unknown"
        OS_VERSION="Unknown OS"
    fi

    # 检测架构
    ARCH=$(uname -m)
    case $ARCH in
        x86_64) ARCH="amd64" ;;
        aarch64 | arm64) ARCH="arm64" ;;
        armv7l) ARCH="armv7" ;;
        *) ARCH="unknown" ;;
    esac

    log_debug "操作系统: $OS_TYPE"
    log_debug "系统版本: $OS_VERSION"
    log_debug "系统架构: $ARCH"
}

check_root() {
    if [[ $EUID -eq 0 && "$ENVIRONMENT" != "docker" ]]; then
        log_warning "检测到以root用户运行，建议使用普通用户"
        read -p "是否继续？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# ====================================
# 依赖检查函数
# ====================================
check_command() {
    local cmd=$1
    local package=$2

    if command -v "$cmd" >/dev/null 2>&1; then
        log_debug "已找到命令: $cmd"
        return 0
    else
        log_warning "未找到命令: $cmd"
        if [[ -n "$package" ]]; then
            log_info "请安装: $package"
        fi
        return 1
    fi
}

check_python() {
    log_info "检查Python环境..."

    if [[ "$SKIP_PYTHON" == "true" ]]; then
        log_info "跳过Python检查"
        return 0
    fi

    # 尝试找到Python命令
    for cmd in python3.11 python3.10 python3.9 python3.8 python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            PYTHON_CMD="$cmd"
            break
        fi
    done

    if [[ -z "$PYTHON_CMD" ]]; then
        log_error "未找到Python，请安装Python $MIN_PYTHON_VERSION 或更高版本"
        install_python
        return $?
    fi

    # 检查Python版本
    local python_version
    python_version=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    log_debug "Python版本: $python_version"

    # 版本比较
    if version_gte "$python_version" "$MIN_PYTHON_VERSION"; then
        log_success "Python版本符合要求: $python_version"
    else
        log_error "Python版本过低: $python_version，要求: $MIN_PYTHON_VERSION+"
        install_python
        return $?
    fi

    # 检查pip
    for cmd in pip3 pip; do
        if command -v "$cmd" >/dev/null 2>&1; then
            PIP_CMD="$cmd"
            break
        fi
    done

    if [[ -z "$PIP_CMD" ]]; then
        log_warning "未找到pip，尝试安装..."
        if ! $PYTHON_CMD -m ensurepip --default-pip; then
            log_error "无法安装pip"
            return 1
        fi
        PIP_CMD="$PYTHON_CMD -m pip"
    fi

    log_success "Python环境检查完成"
    return 0
}

check_docker() {
    log_info "检查Docker环境..."

    if [[ "$SKIP_DOCKER" == "true" ]]; then
        log_info "跳过Docker检查"
        return 0
    fi

    # 检查Docker
    if ! check_command "docker" "docker.io"; then
        install_docker
        return $?
    fi

    # 检查Docker版本
    local docker_version
    if docker_version=$(docker --version 2>/dev/null); then
        docker_version=$(echo "$docker_version" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        log_debug "Docker版本: $docker_version"

        if version_gte "$docker_version" "$MIN_DOCKER_VERSION"; then
            log_success "Docker版本符合要求: $docker_version"
        else
            log_warning "Docker版本过低: $docker_version，建议升级到 $MIN_DOCKER_VERSION+"
        fi
    else
        log_error "无法获取Docker版本信息"
        return 1
    fi

    # 检查Docker服务状态
    if systemctl is-active --quiet docker 2>/dev/null; then
        log_success "Docker服务正在运行"
    else
        log_warning "Docker服务未运行，尝试启动..."
        if ! sudo systemctl start docker; then
            log_error "无法启动Docker服务"
            return 1
        fi
    fi

    # 检查Docker权限
    if ! docker ps >/dev/null 2>&1; then
        log_warning "当前用户无法访问Docker，尝试添加到docker组..."
        if ! sudo usermod -aG docker "$USER"; then
            log_error "无法将用户添加到docker组"
            return 1
        fi
        log_warning "请重新登录以生效Docker组权限"
    fi

    # 检查Docker Compose
    if ! check_command "docker-compose" && ! docker compose version >/dev/null 2>&1; then
        install_docker_compose
        return $?
    fi

    log_success "Docker环境检查完成"
    return 0
}

version_gte() {
    local version1=$1
    local version2=$2

    # 使用sort -V进行版本比较
    if [[ "$(printf '%s\n' "$version1" "$version2" | sort -V | head -n1)" == "$version2" ]]; then
        return 0
    else
        return 1
    fi
}

# ====================================
# 安装函数
# ====================================
install_python() {
    log_info "安装Python..."

    case "$OS_TYPE" in
        "linux")
            if command -v apt-get >/dev/null 2>&1; then
                # Ubuntu/Debian
                sudo apt-get update
                sudo apt-get install -y python3 python3-pip python3-dev python3-venv
            elif command -v yum >/dev/null 2>&1; then
                # CentOS/RHEL/Fedora
                sudo yum install -y python3 python3-pip python3-devel
            elif command -v dnf >/dev/null 2>&1; then
                # Fedora (newer versions)
                sudo dnf install -y python3 python3-pip python3-devel
            else
                log_error "不支持的Linux发行版，请手动安装Python"
                return 1
            fi
            ;;
        "macos")
            if command -v brew >/dev/null 2>&1; then
                brew install python@3.11
            else
                log_error "请先安装Homebrew，然后运行: brew install python@3.11"
                return 1
            fi
            ;;
        *)
            log_error "不支持的操作系统，请手动安装Python"
            return 1
            ;;
    esac

    # 重新检查Python
    check_python
}

install_docker() {
    log_info "安装Docker..."

    case "$OS_TYPE" in
        "linux")
            if command -v apt-get >/dev/null 2>&1; then
                # Ubuntu/Debian
                install_docker_ubuntu
            elif command -v yum >/dev/null 2>&1; then
                # CentOS/RHEL
                install_docker_centos
            else
                log_error "不支持的Linux发行版，请手动安装Docker"
                return 1
            fi
            ;;
        "macos")
            log_error "请从Docker官网下载Docker Desktop for Mac"
            return 1
            ;;
        *)
            log_error "不支持的操作系统，请手动安装Docker"
            return 1
            ;;
    esac
}

install_docker_ubuntu() {
    log_info "在Ubuntu/Debian上安装Docker..."

    # 卸载旧版本
    sudo apt-get remove -y docker docker-engine docker.io containerd runc || true

    # 更新包索引
    sudo apt-get update

    # 安装依赖
    sudo apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release

    # 添加Docker官方GPG密钥
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

    # 设置仓库
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # 更新包索引并安装Docker
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

    # 启动并启用Docker服务
    sudo systemctl start docker
    sudo systemctl enable docker

    log_success "Docker安装完成"
}

install_docker_centos() {
    log_info "在CentOS/RHEL上安装Docker..."

    # 卸载旧版本
    sudo yum remove -y docker \
        docker-client \
        docker-client-latest \
        docker-common \
        docker-latest \
        docker-latest-logrotate \
        docker-logrotate \
        docker-engine || true

    # 安装yum工具
    sudo yum install -y yum-utils

    # 设置仓库
    sudo yum-config-manager \
        --add-repo \
        https://download.docker.com/linux/centos/docker-ce.repo

    # 安装Docker
    sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

    # 启动并启用Docker服务
    sudo systemctl start docker
    sudo systemctl enable docker

    log_success "Docker安装完成"
}

install_docker_compose() {
    log_info "安装Docker Compose..."

    # 检查是否已经有docker compose plugin
    if docker compose version >/dev/null 2>&1; then
        log_success "Docker Compose plugin已可用"
        return 0
    fi

    # 下载并安装独立版本的docker-compose
    local compose_version="2.23.0"
    local compose_url="https://github.com/docker/compose/releases/download/v${compose_version}/docker-compose-$(uname -s)-$(uname -m)"

    sudo curl -L "$compose_url" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose

    # 创建软链接
    sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

    log_success "Docker Compose安装完成"
}

# ====================================
# 项目设置函数
# ====================================
setup_directories() {
    log_info "创建项目目录结构..."

    local dirs=(
        "$PROJECT_ROOT/logs"
        "$PROJECT_ROOT/data"
        "$PROJECT_ROOT/tmp"
        "$PROJECT_ROOT/uploads"
        "$PROJECT_ROOT/builds"
        "$PROJECT_ROOT/cache"
        "$PROJECT_ROOT/ssl"
        "$PROJECT_ROOT/secrets"
        "$PROJECT_ROOT/backups"
    )

    for dir in "${dirs[@]}"; do
        if [[ "$DRY_RUN" == "true" ]]; then
            log_debug "演练: 创建目录 $dir"
        else
            mkdir -p "$dir"
            log_debug "创建目录: $dir"
        fi
    done

    log_success "目录结构创建完成"
}

setup_python_env() {
    log_info "设置Python虚拟环境..."

    if [[ "$SKIP_PYTHON" == "true" ]]; then
        log_info "跳过Python环境设置"
        return 0
    fi

    cd "$PROJECT_ROOT"

    # 检查是否已存在虚拟环境
    if [[ -d "venv" && "$FORCE_INSTALL" != "true" ]]; then
        log_info "虚拟环境已存在，跳过创建"
    else
        if [[ "$DRY_RUN" == "true" ]]; then
            log_debug "演练: 创建Python虚拟环境"
        else
            log_info "创建Python虚拟环境..."
            $PYTHON_CMD -m venv venv
        fi
    fi

    # 激活虚拟环境
    if [[ "$DRY_RUN" != "true" ]]; then
        source venv/bin/activate

        # 升级pip
        pip install --upgrade pip setuptools wheel

        # 安装开发依赖
        if [[ "$ENVIRONMENT" == "dev" ]]; then
            pip install -e ".[dev]"
        else
            pip install -e .
        fi
    fi

    log_success "Python环境设置完成"
}

generate_config_files() {
    log_info "生成配置文件..."

    # 生成.env文件
    local env_file="$PROJECT_ROOT/.env"
    if [[ ! -f "$env_file" || "$FORCE_INSTALL" == "true" ]]; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_debug "演练: 生成.env文件"
        else
            cat > "$env_file" << EOF
# EulerMaker Docker Optimizer 环境变量配置

# 基本配置
DEBUG=$([[ "$ENVIRONMENT" == "dev" ]] && echo "true" || echo "false")
LOG_LEVEL=$([[ "$ENVIRONMENT" == "dev" ]] && echo "DEBUG" || echo "INFO")
ENVIRONMENT=$ENVIRONMENT

# API配置
API_HOST=0.0.0.0
API_PORT=8000
RPC_PORT=9000

# 数据库配置
DATABASE_URL=sqlite:///./data/optimizer.db
REDIS_URL=redis://localhost:6379/0

# 安全配置
SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || echo "your-secret-key-change-in-production")
ALLOWED_HOSTS=*

# Docker配置
DOCKER_HOST=unix:///var/run/docker.sock

# 监控配置
PROMETHEUS_ENABLED=true
METRICS_PORT=8001

# 文件路径
UPLOAD_PATH=./uploads
BUILD_PATH=./builds
LOG_PATH=./logs
CACHE_PATH=./cache
EOF
            log_debug "生成.env文件: $env_file"
        fi
    else
        log_info ".env文件已存在，跳过生成"
    fi

    # 生成nginx配置（生产环境）
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        generate_nginx_config
    fi

    # 生成systemd服务文件（Linux生产环境）
    if [[ "$ENVIRONMENT" == "prod" && "$OS_TYPE" == "linux" ]]; then
        generate_systemd_service
    fi

    log_success "配置文件生成完成"
}

generate_nginx_config() {
    log_info "生成Nginx配置文件..."

    local nginx_dir="$PROJECT_ROOT/config/nginx"
    mkdir -p "$nginx_dir/conf.d"

    if [[ "$DRY_RUN" != "true" ]]; then
        cat > "$nginx_dir/nginx.conf" << 'EOF'
user nginx;
worker_processes auto;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # 日志格式
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log;

    # Gzip压缩
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;

    include /etc/nginx/conf.d/*.conf;
}
EOF

        cat > "$nginx_dir/conf.d/optimizer.conf" << 'EOF'
upstream optimizer_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

upstream optimizer_ws {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name _;

    # 重定向到HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name _;

    # SSL配置
    ssl_certificate /app/ssl/cert.pem;
    ssl_certificate_key /app/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # 安全头
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";

    # 静态文件
    location /static/ {
        alias /app/src/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # WebSocket代理
    location /ws/ {
        proxy_pass http://optimizer_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API代理
    location / {
        proxy_pass http://optimizer_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时配置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF
    fi

    log_debug "生成Nginx配置文件完成"
}

generate_systemd_service() {
    log_info "生成systemd服务文件..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_debug "演练: 生成systemd服务文件"
        return 0
    fi

    local service_file="/tmp/eulermaker-optimizer.service"
    local current_user=$(whoami)

    cat > "$service_file" << EOF
[Unit]
Description=EulerMaker Docker Optimizer
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=$current_user
Group=$current_user
WorkingDirectory=$PROJECT_ROOT
Environment=PATH=$PROJECT_ROOT/venv/bin:/usr/bin:/bin
ExecStart=$PROJECT_ROOT/venv/bin/python -m src.main --prod
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10

# 安全设置
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$PROJECT_ROOT/logs $PROJECT_ROOT/data $PROJECT_ROOT/tmp

[Install]
WantedBy=multi-user.target
EOF

    log_warning "请手动执行以下命令安装系统服务:"
    echo "  sudo cp $service_file /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable eulermaker-optimizer"
    echo "  sudo systemctl start eulermaker-optimizer"
}

setup_permissions() {
    log_info "设置文件权限..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_debug "演练: 设置文件权限"
        return 0
    fi

    # 确保脚本可执行
    chmod +x "$PROJECT_ROOT"/scripts/*.sh

    # 设置日志目录权限
    chmod 755 "$PROJECT_ROOT/logs"

    # 设置数据目录权限
    chmod 755 "$PROJECT_ROOT/data"

    # 设置临时目录权限
    chmod 755 "$PROJECT_ROOT/tmp"

    # 设置secrets目录权限（更严格）
    chmod 700 "$PROJECT_ROOT/secrets"

    log_success "文件权限设置完成"
}

# ====================================
# 主函数
# ====================================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dev)
                ENVIRONMENT="dev"
                shift
                ;;
            --prod)
                ENVIRONMENT="prod"
                shift
                ;;
            --docker)
                ENVIRONMENT="docker"
                shift
                ;;
            --force)
                FORCE_INSTALL=true
                shift
                ;;
            --skip-docker)
                SKIP_DOCKER=true
                shift
                ;;
            --skip-python)
                SKIP_PYTHON=true
                shift
                ;;
            --skip-deps)
                SKIP_DEPS=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

main() {
    # 解析参数
    parse_args "$@"

    # 显示横幅
    print_banner

    # 系统检测
    detect_system
    check_root

    # 依赖检查
    log_info "开始环境设置..."

    if ! check_python; then
        log_error "Python环境检查失败"
        exit 1
    fi

    if ! check_docker; then
        log_error "Docker环境检查失败"
        exit 1
    fi

    # 项目设置
    setup_directories
    setup_python_env
    generate_config_files
    setup_permissions

    # 完成
    log_success "环境设置完成！"

    echo ""
    echo -e "${GREEN}接下来的步骤:${NC}"
    echo "1. 激活Python虚拟环境: source venv/bin/activate"
    echo "2. 启动服务: ./scripts/start.sh"
    echo "3. 访问Web界面: http://localhost:8000"
    echo ""

    if [[ "$ENVIRONMENT" == "prod" ]]; then
        echo -e "${YELLOW}生产环境注意事项:${NC}"
        echo "1. 修改.env文件中的SECRET_KEY"
        echo "2. 配置SSL证书"
        echo "3. 检查防火墙设置"
        echo "4. 设置监控和备份"
        echo ""
    fi
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi