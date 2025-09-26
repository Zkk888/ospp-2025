#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EulerMaker Docker Optimizer 示例代码包

******OSPP-2025-张金荣******

包含各种使用 EulerMaker Docker Optimizer 的示例代码，
帮助用户快速了解和使用系统的各种功能。

示例包括：
- basic_usage.py: 基本功能使用示例
- advanced_usage.py: 高级功能和最佳实践示例

作者: 张金荣
版本: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "张金荣"
__email__ = "3487232360@qq.com"

# 示例模块导出
__all__ = [
    'basic_usage',
    'advanced_usage'
]

# 版本信息
VERSION_INFO = {
    "major": 1,
    "minor": 0,
    "micro": 0,
    "releaselevel": "final",
    "serial": 0
}

def get_version():
    """获取版本信息字符串"""
    return __version__

def get_examples_info():
    """获取示例包信息"""
    return {
        "version": __version__,
        "author": __author__,
        "email": __email__,
        "description": "EulerMaker Docker Optimizer 示例代码包",
        "examples": [
            {
                "name": "basic_usage.py",
                "description": "基本功能使用示例，包括容器管理、构建任务等基础操作"
            },
            {
                "name": "advanced_usage.py",
                "description": "高级功能示例，包括批量操作、监控集成、自动化流程等"
            }
        ]
    }

# 示例使用说明
USAGE_INSTRUCTIONS = """
使用方法:

1. 基本示例:
   python examples/basic_usage.py

2. 高级示例:
   python examples/advanced_usage.py

3. 在代码中导入:
   from examples import basic_usage
   from examples import advanced_usage

注意: 运行示例前请确保 Docker Optimizer 服务已启动
"""

if __name__ == "__main__":
    print("EulerMaker Docker Optimizer 示例代码包")
    print(f"版本: {__version__}")
    print(f"作者: {__author__}")
    print()
    print(USAGE_INSTRUCTIONS)