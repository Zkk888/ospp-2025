#!/bin/bash
# 42. scripts/stop.sh
# EulerMaker Docker Optimizer 停止脚本
#
# ******OSPP-2025-张金荣******
#
# 脚本用于停止EulerMaker Docker Optimizer应用程序，支持：
# - 优雅停止和强制停止
# - 多进程管理
# - 清理临时文件和资源
# - 服务状态检查
# - 超时处理
# - 详细的停止日志
#
# 使用方式：
#   ./scripts/stop.sh [OPTIONS]
#   ./scripts/stop.sh              # 优雅停止
#   ./scripts/stop.sh --force      # 强制停止
#   ./scripts/stop.sh --all        # 停止所有相关进程
#   ./scripts/stop.sh --timeout 30 # 设置停止超时时间

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

# 停止选项
FORCE_STOP=false         # 强制停止
STOP_ALL=false           # 停止所有相关进程
TIMEOUT=30               # 优雅停止超时时间（秒）
VERBOSE=false            # 详细输出
QUIET=false              # 静默模式
CLEANUP=true             # 清理临时文件

# 进程管理文件
MAIN_PID_FILE="$PROJECT_ROOT/tmp/optimizer.pid"
WORKERS_PID_FILE="$PROJECT_ROOT/tmp/workers.pid"
MONITOR_PID_FILE="$PROJECT_ROOT/tmp/monitor.pid"
LOG_FILE="$PROJECT_ROOT/logs/optimizer.log"

# 信号定义
TERM_SIGNAL="TERM"       # 优雅停止信号
KILL_SIGNAL="KILL"       # 强制终止信号

# ====================================
# 工具函数
# ====================================
log_info() {
    if [[ "$QUIET" != "true" ]]; then
        echo -e "${CYAN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
    fi
}

log_success() {
    if [[ "$QUIET" != "true" ]]; then
        echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
    fi
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1" >&2
}

log_debug() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${PURPLE}[DEBUG]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
    fi
}

print_banner() {
    if [[ "$QUIET" != "true" ]]; then
        echo -e "${RED}"
        cat << "EOF"
    ╔═══════════════════════════════════════════════╗
    ║                                               ║
    ║    EulerMaker Docker Optimizer                ║
    ║                                               ║
    ║    正在停止服务...                             ║
    ║                                               ║
    ╚═══════════════════════════════════════════════╝
EOF
        echo -e "${NC}"
        echo "版本: $SCRIPT_VERSION"
        echo "停止超时: ${TIMEOUT}s"
        echo ""
    fi
}

show_help() {
    cat << EOF
EulerMaker Docker Optimizer 停止脚本

使用方式:
    $0 [选项]

选项:
    --force             强制停止，立即终止所有进程
    --all               停止所有相关进程（包括监控、工作进程等）
    --timeout SECONDS   设置优雅停止超时时间 (默认: 30秒)
    --no-cleanup        不清理临时文件和PID文件

    --verbose, -v       详细输出
    --quiet, -q         静默模式，只输出错误信息
    --help, -h          显示此帮助信息

停止策略:
    1. 优雅停止: 发送TERM信号，等待进程自然退出
    2. 强制停止: 如果优雅停止超时，发送KILL信号强制终止
    3. 清理资源: 删除PID文件，清理临时文件

示例:
    $0                  # 优雅停止主服务
    $0 --force          # 强制停止所有进程
    $0 --all --timeout 60  # 停止所有进程，超时60秒
    $0 --quiet          # 静默停止

EOF
}

# ====================================
# 进程管理函数
# ====================================
get_running_processes() {
    log_debug "检查正在运行的进程..."

    local running_processes=()

    # 检查主进程
    if [[ -f "$MAIN_PID_FILE" ]]; then
        local pid
        pid=$(cat "$MAIN_PID_FILE" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            running_processes+=("main:$pid")
            log_debug "发现运行中的主进程: $pid"
        else
            log_debug "主进程PID文件已过期，将清理"
            rm -f "$MAIN_PID_FILE" 2>/dev/null || true
        fi
    fi

    # 检查工作进程
    if [[ -f "$WORKERS_PID_FILE" ]]; then
        local active_workers=()
        while IFS= read -r pid; do
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                running_processes+=("worker:$pid")
                active_workers+=("$pid")
                log_debug "发现运行中的工作进程: $pid"
            fi
        done < "$WORKERS_PID_FILE"

        # 更新工作进程PID文件，移除已停止的进程
        if [[ ${#active_workers[@]} -gt 0 ]]; then
            printf "%s\n" "${active_workers[@]}" > "$WORKERS_PID_FILE"
        else
            log_debug "所有工作进程已停止，清理PID文件"
            rm -f "$WORKERS_PID_FILE" 2>/dev/null || true
        fi
    fi

    # 检查监控进程
    if [[ -f "$MONITOR_PID_FILE" ]]; then
        local pid
        pid=$(cat "$MONITOR_PID_FILE" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            running_processes+=("monitor:$pid")
            log_debug "发现运行中的监控进程: $pid"
        else
            log_debug "监控进程PID文件已过期，将清理"
            rm -f "$MONITOR_PID_FILE" 2>/dev/null || true
        fi
    fi

    # 如果启用了--all选项，查找其他相关进程
    if [[ "$STOP_ALL" == "true" ]]; then
        # 通过进程名查找
        local extra_pids
        extra_pids=$(pgrep -f "$PROJECT_NAME" 2>/dev/null || true)
        if [[ -n "$extra_pids" ]]; then
            while IFS= read -r pid; do
                # 避免重复添加
                local already_added=false
                for proc in "${running_processes[@]}"; do
                    if [[ "$proc" == *":$pid" ]]; then
                        already_added=true
                        break
                    fi
                done
                if [[ "$already_added" == "false" ]]; then
                    running_processes+=("other:$pid")
                    log_debug "发现其他相关进程: $pid"
                fi
            done <<< "$extra_pids"
        fi
    fi

    # 输出结果
    printf "%s\n" "${running_processes[@]}"
}

stop_process() {
    local process_type=$1
    local pid=$2
    local timeout=${3:-$TIMEOUT}

    log_info "停止${process_type}进程 (PID: $pid)..."

    # 检查进程是否还在运行
    if ! kill -0 "$pid" 2>/dev/null; then
        log_debug "进程 $pid 已经停止"
        return 0
    fi

    # 获取进程信息
    local process_info
    process_info=$(ps -p "$pid" -o pid,ppid,command --no-headers 2>/dev/null || echo "Unknown process")
    log_debug "进程信息: $process_info"

    if [[ "$FORCE_STOP" == "true" ]]; then
        # 强制停止
        log_warning "强制终止进程 $pid"
        if kill -$KILL_SIGNAL "$pid" 2>/dev/null; then
            log_success "进程 $pid 已强制终止"
            return 0
        else
            log_error "无法强制终止进程 $pid"
            return 1
        fi
    else
        # 优雅停止
        log_debug "向进程 $pid 发送 $TERM_SIGNAL 信号"
        if kill -$TERM_SIGNAL "$pid" 2>/dev/null; then
            # 等待进程退出
            local count=0
            while kill -0 "$pid" 2>/dev/null && [[ $count -lt $timeout ]]; do
                sleep 1
                ((count++))
                if [[ $((count % 5)) -eq 0 ]]; then
                    log_debug "等待进程 $pid 退出... (${count}/${timeout}s)"
                fi
            done

            if kill -0 "$pid" 2>/dev/null; then
                # 超时，强制终止
                log_warning "进程 $pid 优雅停止超时，强制终止"
                if kill -$KILL_SIGNAL "$pid" 2>/dev/null; then
                    sleep 1
                    if kill -0 "$pid" 2>/dev/null; then
                        log_error "无法终止进程 $pid"
                        return 1
                    else
                        log_success "进程 $pid 已强制终止"
                        return 0
                    fi
                else
                    log_error "无法强制终止进程 $pid"
                    return 1
                fi
            else
                log_success "进程 $pid 已优雅停止"
                return 0
            fi
        else
            log_error "无法向进程 $pid 发送停止信号"
            return 1
        fi
    fi
}

stop_all_processes() {
    log_info "开始停止所有服务进程..."

    local processes
    readarray -t processes < <(get_running_processes)

    if [[ ${#processes[@]} -eq 0 ]]; then
        log_info "没有发现正在运行的进程"
        return 0
    fi

    log_info "发现 ${#processes[@]} 个运行中的进程"

    local failed_processes=()
    local success_count=0

    # 按类型分组停止（主进程最后停止）
    local main_processes=()
    local other_processes=()

    for process in "${processes[@]}"; do
        local type="${process%%:*}"
        if [[ "$type" == "main" ]]; then
            main_processes+=("$process")
        else
            other_processes+=("$process")
        fi
    done

    # 先停止非主进程
    for process in "${other_processes[@]}"; do
        local type="${process%%:*}"
        local pid="${process##*:}"

        if stop_process "$type" "$pid"; then
            ((success_count++))
        else
            failed_processes+=("$process")
        fi
    done

    # 最后停止主进程
    for process in "${main_processes[@]}"; do
        local type="${process%%:*}"
        local pid="${process##*:}"

        # 给主进程更多时间优雅退出
        local main_timeout=$((TIMEOUT + 10))
        if stop_process "$type" "$pid" "$main_timeout"; then
            ((success_count++))
        else
            failed_processes+=("$process")
        fi
    done

    # 报告结果
    if [[ ${#failed_processes[@]} -eq 0 ]]; then
        log_success "所有进程已成功停止 ($success_count/${#processes[@]})"
        return 0
    else
        log_error "部分进程停止失败 ($success_count/${#processes[@]})"
        for failed in "${failed_processes[@]}"; do
            local type="${failed%%:*}"
            local pid="${failed##*:}"
            log_error "失败: ${type}进程 (PID: $pid)"
        done
        return 1
    fi
}

# ====================================
# 资源清理函数
# ====================================
cleanup_resources() {
    if [[ "$CLEANUP" != "true" ]]; then
        log_info "跳过资源清理"
        return 0
    fi

    log_info "清理系统资源..."

    local cleanup_items=()

    # 清理PID文件
    for pid_file in "$MAIN_PID_FILE" "$WORKERS_PID_FILE" "$MONITOR_PID_FILE"; do
        if [[ -f "$pid_file" ]]; then
            cleanup_items+=("PID文件: $pid_file")
            rm -f "$pid_file" 2>/dev/null || log_warning "无法删除 $pid_file"
        fi
    done

    # 清理临时文件
    local temp_patterns=(
        "$PROJECT_ROOT/tmp/daemon_start.sh"
        "$PROJECT_ROOT/tmp/*.tmp"
        "$PROJECT_ROOT/tmp/*.lock"
        "$PROJECT_ROOT/tmp/optimizer_*.socket"
    )

    for pattern in "${temp_patterns[@]}"; do
        local files
        files=$(ls $pattern 2>/dev/null || true)
        if [[ -n "$files" ]]; then
            for file in $files; do
                cleanup_items+=("临时文件: $file")
                rm -f "$file" 2>/dev/null || log_warning "无法删除 $file"
            done
        fi
    done

    # 清理Unix socket文件
    local socket_files
    socket_files=$(find "$PROJECT_ROOT/tmp" -name "*.sock" -type s 2>/dev/null || true)
    if [[ -n "$socket_files" ]]; then
        while IFS= read -r socket_file; do
            cleanup_items+=("Socket文件: $socket_file")
            rm -f "$socket_file" 2>/dev/null || log_warning "无法删除 $socket_file"
        done <<< "$socket_files"
    fi

    # 清理共享内存
    local shm_files
    shm_files=$(find /dev/shm -name "*${PROJECT_NAME}*" 2>/dev/null || true)
    if [[ -n "$shm_files" ]]; then
        while IFS= read -r shm_file; do
            cleanup_items+=("共享内存: $shm_file")
            rm -f "$shm_file" 2>/dev/null || log_warning "无法删除 $shm_file"
        done <<< "$shm_files"
    fi

    if [[ ${#cleanup_items[@]} -gt 0 ]]; then
        log_success "清理完成，共清理 ${#cleanup_items[@]} 项资源"
        if [[ "$VERBOSE" == "true" ]]; then
            for item in "${cleanup_items[@]}"; do
                log_debug "已清理: $item"
            done
        fi
    else
        log_info "没有需要清理的资源"
    fi
}

check_docker_containers() {
    log_debug "检查相关的Docker容器..."

    # 查找项目相关的Docker容器
    local containers
    containers=$(docker ps -a --format "table {{.ID}}\t{{.Names}}\t{{.Status}}" \
                 --filter "label=project=$PROJECT_NAME" 2>/dev/null || true)

    if [[ -n "$containers" && "$containers" != *"CONTAINER ID"* ]]; then
        log_info "发现相关的Docker容器："
        echo "$containers"

        if [[ "$STOP_ALL" == "true" ]]; then
            log_info "停止相关Docker容器..."
            docker stop $(docker ps -q --filter "label=project=$PROJECT_NAME") 2>/dev/null || true
            docker rm $(docker ps -aq --filter "label=project=$PROJECT_NAME") 2>/dev/null || true
            log_success "Docker容器已停止并删除"
        else
            log_info "使用 --all 选项可同时停止Docker容器"
        fi
    fi
}

# ====================================
# 状态检查函数
# ====================================
verify_stop_status() {
    log_debug "验证停止状态..."

    local remaining_processes
    readarray -t remaining_processes < <(get_running_processes)

    if [[ ${#remaining_processes[@]} -eq 0 ]]; then
        log_success "所有服务进程已成功停止"
        return 0
    else
        log_warning "仍有 ${#remaining_processes[@]} 个进程在运行："
        for process in "${remaining_processes[@]}"; do
            local type="${process%%:*}"
            local pid="${process##*:}"
            log_warning "  ${type}进程 (PID: $pid)"
        done
        return 1
    fi
}

show_stop_summary() {
    if [[ "$QUIET" == "true" ]]; then
        return 0
    fi

    echo ""
    log_success "EulerMaker Docker Optimizer 停止完成！"
    echo ""

    # 显示停止统计
    echo -e "${GREEN}停止摘要:${NC}"
    echo "  停止方式: $([[ "$FORCE_STOP" == "true" ]] && echo "强制停止" || echo "优雅停止")"
    echo "  超时时间: ${TIMEOUT}秒"
    echo "  清理资源: $([[ "$CLEANUP" == "true" ]] && echo "已清理" || echo "跳过")"

    # 显示日志文件位置
    if [[ -f "$LOG_FILE" ]]; then
        echo ""
        echo -e "${BLUE}日志文件:${NC}"
        echo "  主日志: $LOG_FILE"
        echo "  查看日志: tail -f $LOG_FILE"
    fi

    echo ""
    echo -e "${CYAN}管理命令:${NC}"
    echo "  启动服务: ./scripts/start.sh"
    echo "  检查状态: ./scripts/status.sh"
    echo "  重启服务: ./scripts/restart.sh"
    echo ""
}

# ====================================
# 主函数
# ====================================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force|-f)
                FORCE_STOP=true
                shift
                ;;
            --all|-a)
                STOP_ALL=true
                shift
                ;;
            --timeout|-t)
                TIMEOUT="$2"
                if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || [[ "$TIMEOUT" -lt 1 ]]; then
                    log_error "超时时间必须是正整数"
                    exit 1
                fi
                shift 2
                ;;
            --no-cleanup)
                CLEANUP=false
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --quiet|-q)
                QUIET=true
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

    # 验证参数组合
    if [[ "$VERBOSE" == "true" && "$QUIET" == "true" ]]; then
        log_error "--verbose 和 --quiet 选项不能同时使用"
        exit 1
    fi
}

main() {
    # 解析命令行参数
    parse_args "$@"

    # 显示停止横幅
    print_banner

    # 检查是否有进程需要停止
    local processes
    readarray -t processes < <(get_running_processes)

    if [[ ${#processes[@]} -eq 0 ]]; then
        log_info "没有发现正在运行的服务进程"

        # 仍然执行清理，以防有残留文件
        cleanup_resources

        if [[ "$STOP_ALL" == "true" ]]; then
            check_docker_containers
        fi

        show_stop_summary
        exit 0
    fi

    # 停止所有进程
    log_info "开始停止服务..."

    local stop_success=true
    if ! stop_all_processes; then
        stop_success=false
    fi

    # 检查Docker容器
    if [[ "$STOP_ALL" == "true" ]]; then
        check_docker_containers
    fi

    # 清理资源
    cleanup_resources

    # 验证停止状态
    if ! verify_stop_status; then
        stop_success=false
    fi

    # 显示停止摘要
    show_stop_summary

    # 退出状态
    if [[ "$stop_success" == "true" ]]; then
        exit 0
    else
        log_error "部分服务停止失败，请检查日志"
        exit 1
    fi
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi