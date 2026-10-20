#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - 全局配置与常量定义模块 (config.py)
=====================================================
功能说明：
1. 集中定义和管理工作区路径（根目录、上传目录、规则文件路径、板书数据文件路径）；
2. 维护模型友好名称与底层 Antigravity RPC 内部模型标识枚举的映射表；
3. 定义 HTTP 服务监听地址、端口号以及长轮询超时等网络推演参数；
4. 提供统一的模型标识解析辅助函数。
"""

from pathlib import Path

# ==========================================
# 1. 路径配置（严格沙箱隔离锁定当前工作区）
# ==========================================
# 工作区根目录：锁定在此目录，严禁越界访问
WORKSPACE_DIR: Path = Path("/Users/dean/Documents/math-tutor-workspace").resolve()

# 用户上传题目图片与原始模型响应日志目录
UPLOADS_DIR: Path = WORKSPACE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Antigravity 智能体规范准则文档路径
AGENTS_MD_PATH: Path = WORKSPACE_DIR / ".antigravity" / "AGENTS.md"

# 持久化前端微课数据源 JavaScript 文件路径
LESSON_JS_PATH: Path = WORKSPACE_DIR / "lesson.js"


# ==========================================
# 2. 网络服务与推演超时配置
# ==========================================
# 服务监听 IP（0.0.0.0 允许局域网内同一 Wi-Fi 设备访问）
SERVER_HOST: str = "0.0.0.0"

# 服务监听端口
SERVER_PORT: int = 8765

# 轮询获取模型推演结果的最大超时时间（秒，最长等待 15 分钟，应对复杂压轴题深度推演）
MAX_POLL_TIMEOUT_SECONDS: int = 900

# 轮询间隔时间（秒）
POLL_INTERVAL_SECONDS: float = 2.0

# 默认选用的几何推演模型标识
DEFAULT_MODEL_SLUG: str = "gemini-3.8-flash-high"


# ==========================================
# 3. 模型名称与 Antigravity 底层模型枚举映射
# ==========================================
MODEL_MAP: dict[str, str] = {
    "gemini-3.8-flash-high": "MODEL_PLACEHOLDER_M318",
    "gemini-3.8-flash-medium": "MODEL_PLACEHOLDER_M319",
    "gemini-3.8-flash-low": "MODEL_PLACEHOLDER_M320",
    "gemini-4-argon-high": "MODEL_PLACEHOLDER_M417",
    "gemini-4-argon-medium": "MODEL_PLACEHOLDER_M418",
    "claude-sonnet-5-5-medium": "MODEL_PLACEHOLDER_M404",
}


def get_model_id(model_slug: str) -> str:
    """
    根据前端传入的模型友好标识解析出 Antigravity 底层 RPC 所需的模型枚举字符串。

    Args:
        model_slug (str): 前端选择的模型标识字符串，例如 'gemini-3.8-flash-high'。

    Returns:
        str: 对应的 Antigravity 底层枚举字符串；若未找到匹配项，默认返回高精度推演模型 (MODEL_PLACEHOLDER_M318)。
    """
    return MODEL_MAP.get(model_slug, MODEL_MAP[DEFAULT_MODEL_SLUG])
