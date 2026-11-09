#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - 全局配置与日志定义模块 (config.py)
=====================================================
功能说明：
1. 提供全局 DEBUG 级别日志器 (get_logger)，同时输出到控制台 (stdout) 与 uploads/debug.log；
2. 自动解析与加载根目录 .env 文件，提取敏感凭证（TEXTIN_APP_ID, DEEPSEEK_API_KEY 等）；
3. 读取外部 JSON 配置文件 (config.json) 中的服务监听、流水线插件和各模型超参数；
4. 维护工作区路径与向后兼容的模型常量。
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

# ==========================================
# 1. 路径配置（严格沙箱隔离锁定当前工作区）
# ==========================================
WORKSPACE_DIR: Path = Path("/Users/dean/Documents/math-tutor-workspace").resolve()

# 用户上传题目图片与原始模型响应日志目录
UPLOADS_DIR: Path = WORKSPACE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 调试日志持久化文件路径
DEBUG_LOG_PATH: Path = UPLOADS_DIR / "debug.log"

# 外部全局配置文件路径
CONFIG_JSON_PATH: Path = WORKSPACE_DIR / "config.json"

# 敏感凭证 .env 文件路径
ENV_FILE_PATH: Path = WORKSPACE_DIR / ".env"

# Antigravity 智能体规范准则文档路径
AGENTS_MD_PATH: Path = WORKSPACE_DIR / ".antigravity" / "AGENTS.md"

# 持久化前端微课数据源 JavaScript 文件路径
LESSON_JS_PATH: Path = WORKSPACE_DIR / "lesson.js"


# ==========================================
# 2. 全局 DEBUG 日志系统初始化
# ==========================================
def setup_logger(level_str: str = "DEBUG") -> logging.Logger:
    """
    初始化并返回全局 Logger，默认开启 DEBUG 级别，同时输出至终端与 uploads/debug.log。
    """
    logger = logging.getLogger("math_tutor")
    level = getattr(logging, level_str.upper(), logging.DEBUG)
    logger.setLevel(level)

    if not logger.handlers:
        fmt = logging.Formatter(
            fmt="[%(asctime)s.%(msecs)03d] [%(levelname)-5s] [%(filename)s:%(lineno)d] %(message)s",
            datefmt="%H:%M:%S",
        )
        # 1. 终端控制台 Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)

        # 2. 本地文件 Handler (uploads/debug.log)
        try:
            file_handler = logging.FileHandler(DEBUG_LOG_PATH, mode="a", encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"⚠️ 创建 debug.log 文件处理器失败: {e}", file=sys.stderr)

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    """
    获取全局统一 logger。
    """
    return logging.getLogger("math_tutor")


def mask_secret(val: str) -> str:
    """
    对敏感凭证进行脱敏显示，便于在 DEBUG 日志中安全核对是否加载成功。
    """
    if not val:
        return "<EMPTY>"
    if len(val) <= 8:
        return f"{val[:2]}***(len={len(val)})"
    return f"{val[:4]}...{val[-4:]}(len={len(val)})"


# 先以 DEBUG 级别初始化日志器
logger = setup_logger("DEBUG")


# ==========================================
# 3. .env 环境变量自动加载机制
# ==========================================
def load_env_file() -> Dict[str, str]:
    """
    轻量原生解析 .env 文件并注入到 os.environ 中，无需额外第三方依赖。
    若 .env 不存在则自动创建一个空模板。
    """
    env_vars: Dict[str, str] = {}
    if not ENV_FILE_PATH.exists():
        logger.warning(".env 文件不存在，正在生成默认空模板: %s", ENV_FILE_PATH)
        template = (
            "# ==========================================\n"
            "# 初中几何微课 - 敏感凭证配置文件 (.env)\n"
            "# 此文件已加入 .gitignore，严禁提交到版本库！\n"
            "# ==========================================\n\n"
            "# 1. TextIn 试卷/习题去手写笔迹 API 凭证 (https://www.textin.com/document/text_auto_removal)\n"
            "TEXTIN_APP_ID=\n"
            "TEXTIN_SECRET_CODE=\n\n"
            "# 2. DeepSeek 旗舰深度推理 API Key (https://platform.deepseek.com)\n"
            "DEEPSEEK_API_KEY=\n"
        )
        ENV_FILE_PATH.write_text(template, encoding="utf-8")
        return env_vars

    try:
        content = ENV_FILE_PATH.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("'\"")
                if val:
                    env_vars[key] = val
                    os.environ[key] = val
        logger.debug(
            "已加载 .env 文件 (%s): TEXTIN_APP_ID=%s, TEXTIN_SECRET_CODE=%s, DEEPSEEK_API_KEY=%s",
            ENV_FILE_PATH,
            mask_secret(os.environ.get("TEXTIN_APP_ID", "")),
            mask_secret(os.environ.get("TEXTIN_SECRET_CODE", "")),
            mask_secret(os.environ.get("DEEPSEEK_API_KEY", "")),
        )
    except Exception as e:
        logger.error("解析 .env 文件异常: %s", e, exc_info=True)

    return env_vars


# ==========================================
# 4. 读取或生成外部 config.json 配置
# ==========================================
DEFAULT_CONFIG: Dict[str, Any] = {
    "_comment": "初中几何微课 - 多模型插件流水线全局配置文件。凭证类敏感数据请在 .env 中配置，此文件管理模型插件、URL及可调超参数。",
    "log_level": "DEBUG",
    "server": {
        "host": "0.0.0.0",
        "port": 8765
    },
    "pipeline": {
        "cleaner_provider": "textin",
        "transcriber_provider": "gemini_rpc",
        "reasoner_provider": "gemini_rpc"
    },
    "cleaner": {
        "textin": {
            "api_url": "https://api.textin.com/ai/service/v1/handwritten_erase",
            "timeout": 60,
            "use_proxy": False
        }
    },
    "transcriber": {
        "gemini_rpc": {
            "model_slug": "gemini-3.8-flash-medium",
            "timeout": 300,
            "poll_interval": 1.5
        }
    },
    "reasoner": {
        "gemini_rpc": {
            "model_slug": "gemini-3.8-flash-high",
            "timeout": 600,
            "poll_interval": 2.0
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-pro",
            "temperature": 0.3,
            "timeout": 600,
            "use_proxy": False
        }
    }
}


def load_app_config() -> Dict[str, Any]:
    """
    加载 config.json 配置，若缺失或损坏则返回默认并写入。
    """
    load_env_file()

    if not CONFIG_JSON_PATH.exists():
        logger.warning("config.json 不存在，正在生成默认配置: %s", CONFIG_JSON_PATH)
        CONFIG_JSON_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG.copy()

    try:
        data = json.loads(CONFIG_JSON_PATH.read_text(encoding="utf-8"))
        for k, v in DEFAULT_CONFIG.items():
            if k not in data:
                data[k] = v
        log_level = data.get("log_level", "DEBUG")
        setup_logger(log_level)
        logger.debug("成功加载 config.json: pipeline=%s, log_level=%s", data.get("pipeline"), log_level)
        return data
    except Exception as e:
        logger.error("解析 config.json 异常: %s，使用默认配置", e, exc_info=True)
        return DEFAULT_CONFIG.copy()


APP_CONFIG: Dict[str, Any] = load_app_config()


# ==========================================
# 5. 常用常量快捷导出
# ==========================================
SERVER_HOST: str = APP_CONFIG.get("server", {}).get("host", "0.0.0.0")
SERVER_PORT: int = APP_CONFIG.get("server", {}).get("port", 8765)

DEFAULT_MODEL_SLUG: str = "gemini-3.8-flash-high"

MODEL_MAP: dict[str, str] = {
    "gemini-3.8-flash-high": "MODEL_PLACEHOLDER_M318",
    "gemini-3.8-flash-medium": "MODEL_PLACEHOLDER_M319",
    "gemini-3.8-flash-low": "MODEL_PLACEHOLDER_M320",
    "gemini-4-argon-high": "MODEL_PLACEHOLDER_M417",
    "gemini-4-argon-medium": "MODEL_PLACEHOLDER_M418",
}


def get_model_id(model_slug: str) -> str:
    """
    根据前端传入的模型友好标识解析出 Antigravity 底层 RPC 所需的模型枚举字符串。
    """
    return MODEL_MAP.get(model_slug, MODEL_MAP[DEFAULT_MODEL_SLUG])
