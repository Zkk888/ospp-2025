"""
测试fixtures包

******OSPP-2025-张金荣******

包含测试所需的固定数据、配置和辅助工具，包括：
- 示例配置数据：用于测试各种配置场景
- 模拟数据：模拟API响应、数据库记录等
- 测试文件内容：Dockerfile、RPM spec文件等
- 测试用例数据：覆盖各种边界条件和异常情况

使用方式：
    from tests.fixtures import sample_container_config
    from tests.fixtures import mock_docker_response
    from tests.fixtures import test_dockerfile_templates

版本: 1.0.0
作者: 张金荣
"""

from pathlib import Path
from typing import Dict, List, Any, Optional
import json
import yaml

# 当前目录
FIXTURES_DIR = Path(__file__).parent
DATA_DIR = FIXTURES_DIR / "data"

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)

# ====================================
# 容器相关测试数据
# ====================================

# 标准容器配置
SAMPLE_CONTAINER_CONFIG = {
    "name": "test-container",
    "image": "centos:7",
    "command": ["bash", "-c", "while true; do sleep 1; done"],
    "environment": {
        "ENV": "test",
        "DEBUG": "true",
        "LANG": "zh_CN.UTF-8"
    },
    "ports": {
        "80/tcp": 8080,
        "443/tcp": 8443
    },
    "volumes": {
        "/host/data": "/container/data",
        "/host/logs": "/container/logs"
    },
    "labels": {
        "project": "eulermaker",
        "component": "optimizer",
        "version": "1.0.0"
    },
    "network": "bridge",
    "restart_policy": {"Name": "always"},
    "memory_limit": "512m",
    "cpu_limit": "1.0",
    "working_dir": "/workspace",
    "user": "root",
    "privileged": False,
    "auto_remove": False,
}

# 容器状态变化的测试数据
CONTAINER_STATES = [
    "created",
    "running",
    "paused",
    "restarting",
    "removing",
    "exited",
    "dead"
]

# 容器错误状态数据
CONTAINER_ERROR_SCENARIOS = [
    {
        "name": "port_conflict",
        "error": "Port 8080 is already in use",
        "config": {**SAMPLE_CONTAINER_CONFIG, "ports": {"8080/tcp": 8080}}
    },
    {
        "name": "image_not_found",
        "error": "Image 'nonexistent:latest' not found",
        "config": {**SAMPLE_CONTAINER_CONFIG, "image": "nonexistent:latest"}
    },
    {
        "name": "invalid_memory",
        "error": "Invalid memory limit format",
        "config": {**SAMPLE_CONTAINER_CONFIG, "memory_limit": "invalid"}
    },
    {
        "name": "network_not_found",
        "error": "Network 'nonexistent' not found",
        "config": {**SAMPLE_CONTAINER_CONFIG, "network": "nonexistent"}
    }
]

# ====================================
# 构建相关测试数据
# ====================================

# 标准构建配置
SAMPLE_BUILD_CONFIG = {
    "name": "test-build",
    "dockerfile_content": """
FROM centos:7

# 更新系统
RUN yum update -y

# 安装构建工具
RUN yum install -y \\
    rpm-build \\
    make \\
    gcc \\
    gcc-c++ \\
    git \\
    wget \\
    tar \\
    gzip

# 创建构建用户
RUN useradd -m builder

# 设置工作目录
WORKDIR /workspace
USER builder

# 默认命令
CMD ["/bin/bash"]
    """.strip(),
    "context_files": {
        "test.spec": """
Name:           test-package
Version:        1.0.0
Release:        1%{?dist}
Summary:        A test package for EulerMaker

License:        MIT
URL:            https://github.com/eulermaker/test-package
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  gcc make
Requires:       glibc

%description
This is a test package created by EulerMaker Docker Optimizer.

%prep
%autosetup

%build
make %{?_smp_mflags}

%install
rm -rf %{buildroot}
make install DESTDIR=%{buildroot}

%files
%{_bindir}/test-binary
%{_datadir}/test-package/*

%changelog
* Fri Dec 01 2025 EulerMaker <3487232360@qq.com> - 1.0.0-1
- Initial package
        """.strip(),
        "Makefile": """
CC = gcc
CFLAGS = -Wall -O2
TARGET = test-binary
SOURCES = main.c

PREFIX = /usr
BINDIR = $(PREFIX)/bin
DATADIR = $(PREFIX)/share/test-package

all: $(TARGET)

$(TARGET): $(SOURCES)
\t$(CC) $(CFLAGS) -o $@ $<

install: $(TARGET)
\tmkdir -p $(DESTDIR)$(BINDIR)
\tmkdir -p $(DESTDIR)$(DATADIR)
\tinstall -m 755 $(TARGET) $(DESTDIR)$(BINDIR)
\tinstall -m 644 README.md $(DESTDIR)$(DATADIR)

clean:
\trm -f $(TARGET)

.PHONY: all install clean
        """.strip(),
        "main.c": """
#include <stdio.h>

int main() {
    printf("Hello from EulerMaker test package!\\n");
    return 0;
}
        """.strip(),
        "README.md": """
# Test Package

这是一个由EulerMaker Docker Optimizer创建的测试包。

## 功能

- 演示基本的C程序编译
- 展示RPM包构建流程
- 提供测试用例参考

## 构建

```bash
make
```

## 安装

```bash
make install
```
        """.strip()
    },
    "build_args": {
        "BUILD_DATE": "2025-07-01",
        "VERSION": "1.0.0"
    },
    "labels": {
        "build.type": "rpm",
        "build.target": "centos7",
        "build.version": "1.0.0"
    },
    "target_stage": None,
    "no_cache": False,
    "pull": True
}

# 构建状态测试数据
BUILD_STATES = [
    "pending",
    "building",
    "completed",
    "failed",
    "cancelled"
]

# 构建错误场景
BUILD_ERROR_SCENARIOS = [
    {
        "name": "dockerfile_syntax_error",
        "error": "Dockerfile syntax error at line 5",
        "dockerfile": "FROM centos:7\nRUN invalid-command"
    },
    {
        "name": "build_command_failed",
        "error": "Build command failed with exit code 1",
        "dockerfile": "FROM centos:7\nRUN exit 1"
    },
    {
        "name": "missing_dependency",
        "error": "Package 'nonexistent-package' not found",
        "dockerfile": "FROM centos:7\nRUN yum install -y nonexistent-package"
    }
]

# ====================================
# 探针相关测试数据
# ====================================

# HTTP探针配置
SAMPLE_HTTP_PROBE_CONFIG = {
    "type": "http",
    "config": {
        "url": "http://localhost:8080/health",
        "method": "GET",
        "headers": {
            "User-Agent": "EulerMaker-Probe/1.0",
            "Accept": "application/json"
        },
        "timeout": 5,
        "interval": 10,
        "retries": 3,
        "expected_status": [200, 201],
        "expected_body_contains": "OK"
    }
}

# TCP探针配置
SAMPLE_TCP_PROBE_CONFIG = {
    "type": "tcp",
    "config": {
        "host": "localhost",
        "port": 22,
        "timeout": 3,
        "interval": 5,
        "retries": 2
    }
}

# 命令探针配置
SAMPLE_COMMAND_PROBE_CONFIG = {
    "type": "command",
    "config": {
        "command": ["ps", "aux"],
        "expected_exit_code": 0,
        "expected_output_contains": "bash",
        "timeout": 10,
        "interval": 30,
        "retries": 1
    }
}

# 探针状态
PROBE_STATES = [
    "healthy",
    "unhealthy",
    "unknown"
]

# ====================================
# API响应模拟数据
# ====================================

# 成功响应模板
SUCCESS_RESPONSE_TEMPLATE = {
    "success": True,
    "message": "Operation completed successfully",
    "data": {},
    "timestamp": "2025-07-01T10:00:00Z"
}

# 错误响应模板
ERROR_RESPONSE_TEMPLATE = {
    "success": False,
    "error": {
        "code": "UNKNOWN_ERROR",
        "message": "An error occurred",
        "details": {}
    },
    "timestamp": "2025-07-01T10:00:00Z"
}

# API端点测试数据
API_ENDPOINTS = {
    "containers": {
        "list": {
            "method": "GET",
            "path": "/api/v1/containers",
            "response": {
                **SUCCESS_RESPONSE_TEMPLATE,
                "data": {
                    "containers": [
                        {
                            "id": "container_123",
                            "name": "test-container",
                            "image": "centos:7",
                            "status": "running",
                            "created_at": "2025-07-01T09:00:00Z"
                        }
                    ]
                }
            }
        },
        "create": {
            "method": "POST",
            "path": "/api/v1/containers",
            "request": SAMPLE_CONTAINER_CONFIG,
            "response": {
                **SUCCESS_RESPONSE_TEMPLATE,
                "data": {
                    "container": {
                        "id": "container_123",
                        "name": "test-container",
                        "status": "created"
                    }
                }
            }
        },
        "get": {
            "method": "GET",
            "path": "/api/v1/containers/container_123",
            "response": {
                **SUCCESS_RESPONSE_TEMPLATE,
                "data": {
                    "container": {
                        "id": "container_123",
                        "name": "test-container",
                        "image": "centos:7",
                        "status": "running",
                        "config": SAMPLE_CONTAINER_CONFIG
                    }
                }
            }
        }
    },
    "builds": {
        "list": {
            "method": "GET",
            "path": "/api/v1/builds",
            "response": {
                **SUCCESS_RESPONSE_TEMPLATE,
                "data": {
                    "builds": [
                        {
                            "id": "build_123",
                            "name": "test-build",
                            "status": "completed",
                            "created_at": "2025-07-01T09:00:00Z"
                        }
                    ]
                }
            }
        },
        "create": {
            "method": "POST",
            "path": "/api/v1/builds",
            "request": SAMPLE_BUILD_CONFIG,
            "response": {
                **SUCCESS_RESPONSE_TEMPLATE,
                "data": {
                    "build": {
                        "id": "build_123",
                        "name": "test-build",
                        "status": "pending"
                    }
                }
            }
        }
    }
}

# ====================================
# Docker API响应模拟数据
# ====================================

DOCKER_API_RESPONSES = {
    "version": {
        "Version": "20.10.21",
        "ApiVersion": "1.41",
        "MinAPIVersion": "1.12",
        "GitCommit": "baeda1f",
        "GoVersion": "go1.17.13",
        "Os": "linux",
        "Arch": "amd64",
        "BuildTime": "2025-09-01T18:17:02.000000000+00:00"
    },
    "info": {
        "ID": "test-docker-daemon",
        "Containers": 5,
        "ContainersRunning": 2,
        "ContainersPaused": 0,
        "ContainersStopped": 3,
        "Images": 10,
        "Driver": "overlay2",
        "MemoryLimit": True,
        "SwapLimit": True,
        "KernelVersion": "5.4.0-74-generic",
        "OperatingSystem": "CentOS Linux 7 (Core)",
        "OSType": "linux",
        "Architecture": "x86_64",
        "NCPU": 4,
        "MemTotal": 8589934592
    },
    "container_inspect": {
        "Id": "container_123456789abcdef",
        "Created": "2025-07-01T09:00:00Z",
        "Path": "/bin/bash",
        "Args": ["-c", "while true; do sleep 1; done"],
        "State": {
            "Status": "running",
            "Running": True,
            "Paused": False,
            "Restarting": False,
            "OOMKilled": False,
            "Dead": False,
            "Pid": 12345,
            "ExitCode": 0,
            "StartedAt": "2025-07-01T09:00:05Z"
        },
        "Image": "sha256:eeb6ee3f44bd0b5103bb561b4c16bcb82328cfe5809ab675bb17ab3a16c517c9",
        "Name": "/test-container",
        "Config": {
            "Hostname": "container123",
            "User": "root",
            "WorkingDir": "/workspace",
            "Env": [
                "ENV=test",
                "DEBUG=true",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ],
            "Cmd": ["bash", "-c", "while true; do sleep 1; done"],
            "Image": "centos:7",
            "Labels": {
                "project": "eulermaker",
                "component": "optimizer"
            }
        },
        "NetworkSettings": {
            "IPAddress": "172.17.0.2",
            "Ports": {
                "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]
            }
        }
    }
}

# ====================================
# 测试用例边界条件数据
# ====================================

# 边界值测试数据
BOUNDARY_TEST_DATA = {
    "container_names": {
        "valid": [
            "test",
            "test-container",
            "test_container_123",
            "a" * 63  # 最大长度
        ],
        "invalid": [
            "",  # 空名称
            "a" * 64,  # 超过最大长度
            "Test",  # 大写字母
            "test container",  # 包含空格
            "-test",  # 以连字符开始
            "test-",  # 以连字符结尾
            "test..container"  # 连续点号
        ]
    },
    "port_numbers": {
        "valid": [1, 80, 443, 8080, 65535],
        "invalid": [0, -1, 65536, 99999, "invalid"]
    },
    "memory_limits": {
        "valid": ["128m", "1g", "2.5g", "512M", "1024MB"],
        "invalid": ["", "invalid", "-1g", "128", "1x"]
    },
    "cpu_limits": {
        "valid": [0.1, 0.5, 1.0, 2.0, 4.0],
        "invalid": [-1, 0, "invalid", 999]
    }
}

# 性能测试数据
PERFORMANCE_TEST_DATA = {
    "large_file_content": "A" * 1024 * 1024,  # 1MB文件内容
    "many_environment_vars": {f"VAR_{i}": f"value_{i}" for i in range(1000)},  # 大量环境变量
    "long_command": ["echo"] + [f"arg_{i}" for i in range(1000)]  # 长命令
}

# ====================================
# 工具函数
# ====================================

def load_test_data(filename: str) -> Any:
    """
    从文件加载测试数据

    Args:
        filename: 数据文件名

    Returns:
        加载的数据
    """
    file_path = DATA_DIR / filename

    if not file_path.exists():
        return None

    suffix = file_path.suffix.lower()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            if suffix == '.json':
                return json.load(f)
            elif suffix in ['.yml', '.yaml']:
                return yaml.safe_load(f)
            else:
                return f.read()
    except Exception as e:
        print(f"加载测试数据失败 {filename}: {e}")
        return None

def save_test_data(filename: str, data: Any) -> bool:
    """
    保存测试数据到文件

    Args:
        filename: 数据文件名
        data: 要保存的数据

    Returns:
        是否保存成功
    """
    file_path = DATA_DIR / filename
    suffix = file_path.suffix.lower()

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            if suffix == '.json':
                json.dump(data, f, indent=2, ensure_ascii=False)
            elif suffix in ['.yml', '.yaml']:
                yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
            else:
                f.write(str(data))
        return True
    except Exception as e:
        print(f"保存测试数据失败 {filename}: {e}")
        return False

def get_test_dockerfile(template_name: str = "basic") -> str:
    """
    获取测试用Dockerfile模板

    Args:
        template_name: 模板名称

    Returns:
        Dockerfile内容
    """
    templates = {
        "basic": """
FROM centos:7
RUN yum update -y
CMD ["/bin/bash"]
        """.strip(),

        "rpm_build": SAMPLE_BUILD_CONFIG["dockerfile_content"],

        "multi_stage": """
FROM centos:7 as builder
RUN yum install -y gcc make
COPY . /src
WORKDIR /src
RUN make

FROM centos:7 as runtime
COPY --from=builder /src/app /usr/local/bin/
CMD ["/usr/local/bin/app"]
        """.strip(),

        "error": """
FROM centos:7
RUN invalid-command-that-will-fail
        """.strip()
    }

    return templates.get(template_name, templates["basic"])

# ====================================
# 导出的测试数据
# ====================================

__all__ = [
    # 配置数据
    "SAMPLE_CONTAINER_CONFIG",
    "SAMPLE_BUILD_CONFIG",
    "SAMPLE_HTTP_PROBE_CONFIG",
    "SAMPLE_TCP_PROBE_CONFIG",
    "SAMPLE_COMMAND_PROBE_CONFIG",

    # 状态数据
    "CONTAINER_STATES",
    "BUILD_STATES",
    "PROBE_STATES",

    # 错误场景
    "CONTAINER_ERROR_SCENARIOS",
    "BUILD_ERROR_SCENARIOS",

    # API数据
    "SUCCESS_RESPONSE_TEMPLATE",
    "ERROR_RESPONSE_TEMPLATE",
    "API_ENDPOINTS",
    "DOCKER_API_RESPONSES",

    # 测试边界数据
    "BOUNDARY_TEST_DATA",
    "PERFORMANCE_TEST_DATA",

    # 工具函数
    "load_test_data",
    "save_test_data",
    "get_test_dockerfile",

    # 目录常量
    "FIXTURES_DIR",
    "DATA_DIR",
]