#!/bin/bash
# 41. scripts/start.sh
# EulerMaker Docker Optimizer 启动脚本
#
# ******OSPP-2025-张金荣******
#
# 脚本用于启动EulerMaker Docker Optimizer应用程序，支持：
# - 多种启动模式（开发、生产、Docker）
# - 进程管理和监控
# - 健康检查和自动重启
# - 日志管理
# - 服务依赖检查
# - 优雅启动和关闭
#
# 使用方式：
#   ./scripts/start.sh [OPTIONS]
#   ./scripts/start.sh --dev         # 开发模式
#   ./scripts/start.sh --prod        # 生产模式
#   ./scripts/start.sh --docker      # Docker模式
#   ./scripts/start.sh --daemon      # 守护进程模式

set -euo pipefail

# ====================================
# 全局变量和配置
# ====================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="eulermaker-docker-optimizer"

# 版本信息
SCRIPT_VERSION="1.0.0"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# 配置选项
MODE="dev"                    # 运行模式：dev, prod, docker
DAEMON=false                  # 是否以守护进程方式运行
VERBOSE=false                 # 详细输出
FORCE_START=false             # 强制启动（忽略运行中的进程）
CHECK_DEPS=true               # 检查依赖
ENABLE_MONITORING=false       # 启用监控
WORKERS=1                     # 工作进程数（生产模式）

# 服务配置
WEB_HOST="0.0.0.0"
WEB_PORT="8000"
RPC_PORT="9000"
METRICS_PORT="8001"

# 进程管理
MAIN_PID_FILE="$PROJECT_ROOT/tmp/optimizer.pid"
WORKERS_PID_FILE="$PROJECT_ROOT/tmp/workers.pid"
LOG_FILE="$PROJECT_ROOT/logs/optimizer.log"
ERROR_LOG="$PROJECT_ROOT/logs/optimizer.error.log"

# Python环境
PYTHON_CMD=""
VENV_PATH="$PROJECT_ROOT/venv"

# ====================================
# 工具函数
# ====================================
log_info() {
    echo -e "${CYAN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_debug() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${PURPLE}[DEBUG]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
    fi
}

print_banner() {
    echo -e "${GREEN}"
    cat << "EOF"
    ╔═══════════════════════════════════════════════╗
    ║                                               ║
    ║    EulerMaker Docker Optimizer                ║
    ║                                               ║
    ║    正在启动服务...                             ║
    ║                                               ║
    ╚═══════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    echo "版本: $SCRIPT_VERSION"
    echo "模式: $MODE"
    echo "项目根目录: $PROJECT_ROOT"
    echo ""
}

show_help() {
    cat << EOF
EulerMaker Docker Optimizer 启动脚本

使用方式:
    $0 [选项]

选项:
    --dev               开发模式启动 (默认)
    --prod              生产模式启动
    --docker            Docker容器模式

    --daemon, -d        以守护进程方式运行
    --workers N         设置工作进程数 (生产模式, 默认: 1)
    --port PORT         设置Web服务端口 (默认: 8000)
    --host HOST         设置监听地址 (默认: 0.0.0.0)

    --force             强制启动，忽略已运行的进程
    --no-deps           跳过依赖检查
    --monitoring        启用监控服务

    --verbose, -v       详细输出
    --help, -h          显示此帮助信息

示例:
    $0                      # 开发模式启动
    $0 --prod --daemon      # 生产模式后台启动
    $0 --dev --verbose      # 开发模式详细输出
    $0 --docker             # Docker容器启动

启动后可以通过以下方式访问:
    Web界面: http://localhost:8000
    API文档: http://localhost:8000/api/v1/docs
    监控指标: http://localhost:8001/metrics (如果启用监控)

EOF
}

# ====================================
# 环境检查函数
# ====================================
find_python() {
    log_debug "查找Python解释器..."

    # 优先使用虚拟环境中的Python
    if [[ -f "$VENV_PATH/bin/python" ]]; then
        PYTHON_CMD="$VENV_PATH/bin/python"
        log_debug "使用虚拟环境Python: $PYTHON_CMD"
        return 0
    fi

    # 尝试系统Python
    for cmd in python3.11 python3.10 python3.9 python3.8 python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            PYTHON_CMD="$cmd"
            log_debug "使用系统Python: $PYTHON_CMD"
            return 0
        fi
    done

    log_error "未找到Python解释器"
    return 1
}

check_python_version() {
    log_debug "检查Python版本..."

    local python_version
    python_version=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')

    log_debug "Python版本: $python_version"

    # 检查最低版本要求（3.8+）
    local major minor
    major=$(echo "$python_version" | cut -d. -f1)
    minor=$(echo "$python_version" | cut -d. -f2)

    if [[ $major -lt 3 || ($major -eq 3 && $minor -lt 8) ]]; then
        log_error "Python版本过低: $python_version，要求3.8+"
        return 1
    fi

    log_success "Python版本符合要求: $python_version"
    return 0
}

check_dependencies() {
    if [[ "$CHECK_DEPS" != "true" ]]; then
        log_info "跳过依赖检查"
        return 0
    fi

    log_info "检查系统依赖..."

    # 检查Python环境
    if ! find_python; then
        log_error "Python环境检查失败"
        return 1
    fi

    if ! check_python_version; then
        return 1
    fi

    # 检查必要的Python包
    log_debug "检查Python包..."
    local required_packages=(
        "fastapi"
        "uvicorn"
        "docker"
        "pydantic"
        "aiofiles"
    )

    for package in "${required_packages[@]}"; do
        if ! $PYTHON_CMD -c "import $package" >/dev/null 2>&1; then
            log_error "缺少Python包: $package"
            log_info "请运行: $PYTHON_CMD -m pip install -r requirements.txt"
            return 1
        fi
        log_debug "Python包检查通过: $package"
    done

    # 检查Docker连接（如果不是Docker模式）
    if [[ "$MODE" != "docker" ]]; then
        log_debug "检查Docker连接..."
        if ! docker info >/dev/null 2>&1; then
            log_error "无法连接到Docker守护进程"
            log_info "请确保Docker服务正在运行，且当前用户有权限访问Docker"
            return 1
        fi
        log_debug "Docker连接检查通过"
    fi

    # 检查网络端口
    check_port_availability

    log_success "依赖检查完成"
    return 0
}

check_port_availability() {
    log_debug "检查端口可用性..."

    local ports=("$WEB_PORT" "$RPC_PORT")
    if [[ "$ENABLE_MONITORING" == "true" ]]; then
        ports+=("$METRICS_PORT")
    fi

    for port in "${ports[@]}"; do
        if netstat -ln 2>/dev/null | grep -q ":$port "; then
            log_error "端口 $port 已被占用"
            log_info "请使用其他端口或停止占用此端口的进程"
            return 1
        fi
        log_debug "端口可用: $port"
    done

    return 0
}

check_running_processes() {
    log_debug "检查正在运行的进程..."

    local running=false

    # 检查PID文件
    if [[ -f "$MAIN_PID_FILE" ]]; then
        local pid
        pid=$(cat "$MAIN_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_warning "检测到正在运行的主进程 (PID: $pid)"
            running=true
        else
            log_debug "清理过期的PID文件: $MAIN_PID_FILE"
            rm -f "$MAIN_PID_FILE"
        fi
    fi

    if [[ -f "$WORKERS_PID_FILE" ]]; then
        while IFS= read -r pid; do
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                log_warning "检测到正在运行的工作进程 (PID: $pid)"
                running=true
            fi
        done < "$WORKERS_PID_FILE"

        # 如果没有活跃的工作进程，清理PID文件
        if [[ "$running" != "true" ]]; then
            log_debug "清理过期的工作进程PID文件: $WORKERS_PID_FILE"
            rm -f "$WORKERS_PID_FILE"
        fi
    fi

    if [[ "$running" == "true" && "$FORCE_START" != "true" ]]; then
        log_error "检测到正在运行的进程，使用 --force 强制启动或先停止现有进程"
        log_info "停止现有进程: ./scripts/stop.sh"
        return 1
    elif [[ "$running" == "true" && "$FORCE_START" == "true" ]]; then
        log_warning "强制启动模式，将停止现有进程..."
        "$SCRIPT_DIR/stop.sh" --force
        sleep 2
    fi

    return 0
}

# ====================================
# 服务启动函数
# ====================================
setup_environment() {
    log_info "设置运行环境..."

    # 创建必要的目录
    mkdir -p "$PROJECT_ROOT/logs" \
             "$PROJECT_ROOT/tmp" \
             "$PROJECT_ROOT/data" \
             "$PROJECT_ROOT/uploads" \
             "$PROJECT_ROOT/builds" \
             "$PROJECT_ROOT/cache"

    # 导出环境变量
    export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"
    export PYTHONUNBUFFERED=1

    # 加载.env文件（如果存在）
    local env_file="$PROJECT_ROOT/.env"
    if [[ -f "$env_file" ]]; then
        log_debug "加载环境变量文件: $env_file"
        set -o allexport
        source "$env_file"
        set +o allexport
    fi

    # 根据模式设置特定环境变量
    case "$MODE" in
        "dev")
            export DEBUG=true
            export LOG_LEVEL=DEBUG
            export RELOAD=true
            ;;
        "prod")
            export DEBUG=false
            export LOG_LEVEL=INFO
            export RELOAD=false
            ;;
        "docker")
            export DEBUG=false
            export LOG_LEVEL=INFO
            export RELOAD=false
            ;;
    esac

    # 设置服务器配置
    export API_HOST="$WEB_HOST"
    export API_PORT="$WEB_PORT"
    export RPC_PORT="$RPC_PORT"
    export METRICS_PORT="$METRICS_PORT"

    log_success "环境设置完成"
}

start_main_service() {
    log_info "启动主服务..."

    local start_cmd=(
        "$PYTHON_CMD" "-m" "src.main"
        "--host" "$WEB_HOST"
        "--port" "$WEB_PORT"
        "--rpc-port" "$RPC_PORT"
    )

    # 根据模式添加参数
    case "$MODE" in
        "dev")
            start_cmd+=("--debug" "--reload")
            ;;
        "prod")
            start_cmd+=("--workers" "$WORKERS")
            ;;
        "docker")
            start_cmd+=("--workers" "1")
            ;;
    esac

    if [[ "$VERBOSE" == "true" ]]; then
        start_cmd+=("--log-level" "DEBUG")
    fi

    if [[ "$ENABLE_MONITORING" == "true" ]]; then
        log_info "启用监控服务..."
        # 启动监控相关服务的逻辑可以在这里添加
    fi

    log_debug "启动命令: ${start_cmd[*]}"

    if [[ "$DAEMON" == "true" ]]; then
        # 守护进程模式
        start_daemon "${start_cmd[@]}"
    else
        # 前台模式
        start_foreground "${start_cmd[@]}"
    fi
}

start_foreground() {
    log_info "前台模式启动..."

    # 设置信号处理
    trap 'handle_signal TERM' TERM
    trap 'handle_signal INT' INT
    trap 'handle_signal HUP' HUP

    # 启动主进程
    exec "$@"
}

start_daemon() {
    log_info "守护进程模式启动..."

    # 创建启动脚本
    local daemon_script="$PROJECT_ROOT/tmp/daemon_start.sh"
    cat > "$daemon_script" << EOF
#!/bin/bash
cd "$PROJECT_ROOT"
export PYTHONPATH="$PYTHONPATH"
export PYTHONUNBUFFERED=1

# 重定向输出到日志文件
exec "$@" > "$LOG_FILE" 2> "$ERROR_LOG"
EOF
    chmod +x "$daemon_script"

    # 使用nohup启动守护进程
    nohup "$daemon_script" >/dev/null 2>&1 &
    local main_pid=$!

    # 保存PID
    echo "$main_pid" > "$MAIN_PID_FILE"
    log_success "主服务已启动 (PID: $main_pid)"

    # 等待服务启动
    wait_for_service_ready

    # 清理临时脚本
    rm -f "$daemon_script"
}

wait_for_service_ready() {
    log_info "等待服务就绪..."

    local max_attempts=30
    local attempt=1
    local health_url="http://$WEB_HOST:$WEB_PORT/api/v1/health"

    while [[ $attempt -le $max_attempts ]]; do
        log_debug "健康检查尝试 $attempt/$max_attempts"

        if curl -s -f "$health_url" >/dev/null 2>&1; then
            log_success "服务已就绪"
            return 0
        fi

        sleep 2
        ((attempt++))
    done

    log_error "服务启动超时"
    return 1
}

handle_signal() {
    local signal=$1
    log_info "接收到信号: $signal"

    case "$signal" in
        "TERM"|"INT")
            log_info "开始优雅关闭..."
            cleanup_and_exit
            ;;
        "HUP")
            log_info "重新加载配置..."
            reload_service
            ;;
    esac
}

reload_service() {
    log_info "重新加载服务配置..."

    if [[ -f "$MAIN_PID_FILE" ]]; then
        local pid
        pid=$(cat "$MAIN_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill -HUP "$pid"
            log_success "配置重新加载完成"
        else
            log_error "主进程未运行"
        fi
    else
        log_error "未找到PID文件"
    fi
}

cleanup_and_exit() {
    log_info "清理资源并退出..."

    # 停止所有相关进程
    if [[ -f "$MAIN_PID_FILE" ]]; then
        local pid
        pid=$(cat "$MAIN_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "停止主进程 (PID: $pid)..."
            kill -TERM "$pid"

            # 等待进程退出
            local count=0
            while kill -0 "$pid" 2>/dev/null && [[ $count -lt 30 ]]; do
                sleep 1
                ((count++))
            done

            # 强制终止（如果还在运行）
            if kill -0 "$pid" 2>/dev/null; then
                log_warning "强制终止进程 (PID: $pid)"
                kill -KILL "$pid"
            fi
        fi
        rm -f "$MAIN_PID_FILE"
    fi

    # 清理工作进程
    if [[ -f "$WORKERS_PID_FILE" ]]; then
        while IFS= read -r pid; do
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                log_info "停止工作进程 (PID: $pid)..."
                kill -TERM "$pid"
            fi
        done < "$WORKERS_PID_FILE"
        rm -f "$WORKERS_PID_FILE"
    fi

    log_success "清理完成"
    exit 0
}

# ====================================
# 服务状态和监控
# ====================================
show_service_info() {
    echo ""
    log_success "EulerMaker Docker Optimizer 启动完成！"
    echo ""
    echo -e "${GREEN}服务访问地址:${NC}"
    echo "  Web界面:    http://$WEB_HOST:$WEB_PORT"
    echo "  API文档:    http://$WEB_HOST:$WEB_PORT/api/v1/docs"
    echo "  RPC接口:    http://$WEB_HOST:$RPC_PORT/rpc"

    if [[ "$ENABLE_MONITORING" == "true" ]]; then
        echo "  监控指标:   http://$WEB_HOST:$METRICS_PORT/metrics"
    fi

    echo ""
    echo -e "${YELLOW}管理命令:${NC}"
    echo "  查看状态:   ./scripts/status.sh"
    echo "  查看日志:   tail -f $LOG_FILE"
    echo "  停止服务:   ./scripts/stop.sh"
    echo "  重启服务:   ./scripts/restart.sh"
    echo ""

    if [[ -f "$MAIN_PID_FILE" ]]; then
        local pid
        pid=$(cat "$MAIN_PID_FILE")
        echo -e "${BLUE}进程信息:${NC}"
        echo "  主进程PID:  $pid"
        echo "  日志文件:   $LOG_FILE"
        echo "  错误日志:   $ERROR_LOG"
        echo ""
    fi
}

# ====================================
# 主函数
# ====================================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dev)
                MODE="dev"
                shift
                ;;
            --prod)
                MODE="prod"
                WORKERS=4  # 生产环境默认4个工作进程
                shift
                ;;
            --docker)
                MODE="docker"
                shift
                ;;
            --daemon|-d)
                DAEMON=true
                shift
                ;;
            --workers)
                WORKERS="$2"
                shift 2
                ;;
            --port)
                WEB_PORT="$2"
                shift 2
                ;;
            --host)
                WEB_HOST="$2"
                shift 2
                ;;
            --force)
                FORCE_START=true
                shift
                ;;
            --no-deps)
                CHECK_DEPS=false
                shift
                ;;
            --monitoring)
                ENABLE_MONITORING=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
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
    # 解析命令行参数
    parse_args "$@"

    # 显示启动横幅
    print_banner

    # 环境检查
    log_info "开始启动准备..."

    if ! check_running_processes; then
        exit 1
    fi

    if ! check_dependencies; then
        exit 1
    fi

    # 设置运行环境
    setup_environment

    # 启动主服务
    start_main_service

    # 如果是守护进程模式，显示服务信息后退出
    if [[ "$DAEMON" == "true" ]]; then
        show_service_info
    fi
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi