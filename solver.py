#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - 核心推演与解题调度模块 (solver.py)
=====================================================
功能说明：
1. 封装三阶段流水线执行调度（TextIn 擦除笔记 -> Gemini 空间题设转录 -> DeepSeek/Gemini 证明与绘图架构）；
2. 通过 PipelineManager 统一管理多阶段插件生命周期、进度回调与取消检测；
3. 将推演成功后的数据持久化写入 `lesson.js`。
"""

import json
from typing import Any, Callable, Dict, Optional
from config import (
    DEFAULT_MODEL_SLUG,
    LESSON_JS_PATH,
    get_logger,
    load_app_config,
)
from plugins.pipeline import PipelineManager

logger = get_logger()


def solve_problem_automatically(
    image_bytes: bytes,
    mime_type: str,
    extra_note: str = "",
    model_slug: str = DEFAULT_MODEL_SLUG,
    enable_transcription: bool = True,
    transcription_model: str = "gemini-3.8-flash-medium",
    progress_cb: Optional[Callable[[int, str, str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """
    调度解题流程：
    - 若选择 DeepSeek 模型：强制开启图转文字，走 TextIn ➔ Gemini转录 ➔ DeepSeek深度证明；
    - 若选择 Gemini 模型且勾选图转文字：走 TextIn ➔ Gemini转录 ➔ Gemini深度证明；
    - 若选择 Gemini 模型且未勾选图转文字：跳过 TextIn 与转录，直接 Gemini 原生多模态看图解题。
    """
    cfg = load_app_config()

    is_deepseek = model_slug.startswith("deepseek")
    if is_deepseek:
        cfg["pipeline"]["reasoner_provider"] = "deepseek"
        # DeepSeek 仅接收纯文本，强制要求开启图转文字
        enable_transcription = True
    else:
        cfg["pipeline"]["reasoner_provider"] = "gemini_rpc"

    pipeline = PipelineManager(cfg)

    logger.debug(
        "[solver] 启动解题调度 | mime=%s | img_bytes=%d | reasoner=%s (%s) | transcribe=%s (%s) | note=%s",
        mime_type,
        len(image_bytes),
        model_slug,
        cfg["pipeline"]["reasoner_provider"],
        enable_transcription,
        transcription_model,
        extra_note,
    )

    pipe_res = pipeline.run_pipeline(
        raw_image_bytes=image_bytes,
        mime_type=mime_type,
        extra_note=extra_note,
        model_override=model_slug,
        enable_transcription=enable_transcription,
        transcription_model=transcription_model,
        progress_cb=progress_cb,
        cancel_check=cancel_check,
    )

    lesson_data = pipe_res["lessonData"]

    # 覆写到工作区的 lesson.js 中持久化
    js_content = "window.LESSON_DATA = " + json.dumps(lesson_data, ensure_ascii=False, indent=2) + ";\n"
    LESSON_JS_PATH.write_text(js_content, encoding="utf-8")
    logger.debug("💾 [solver] 成功覆写更新 lesson.js (%d 字符)", len(js_content))

    return {
        "lessonData": lesson_data,
        "model": model_slug,
        "user": "Pro Pipeline User",
        "elapsed": pipe_res["elapsed"],
        "stageElapsed": pipe_res["stageElapsed"],
    }
