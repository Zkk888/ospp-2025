"""
******OSPP-2025-张金荣******


Eulermaker-docker-optimizer 的配置包

包含所有与配置相关的模块，包括：
• 全局设置
• 日志记录配置
• 环境相关的配置


"""

from .settings import Settings, get_settings

__version__ = "1.0.0"
__author__ = "OSPP-2025"

# 导出常用的配置对象
__all__ = [
    "Settings",
    "get_settings",
]