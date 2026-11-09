#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插件流水线总控编排器 (plugins/pipeline.py)
========================================
负责协调执行三阶段工作流：
1. Cleaner (TextIn): 擦除原图手写笔记与草稿；
2. Transcriber (Gemini): 将清洗后的底图转录为无歧义几何命题 LaTeX 描述；
3. Reasoner (DeepSeek): 进行中考几何深度证明，生成辅助线、GeoGebra 指令与规范板书。
特性：
- 每个阶段完成后立即将中间产物持久化至 uploads/ 目录，并输出全量 DEBUG 日志；
- 内置基于原图 SHA256 指纹的 Stage 1 & Stage 2 智能缓存：同一张图片重试或修改讲题要求时，
  毫秒级复用已清洗底图与题干转录结果，节省 TextIn 额度与 20+ 秒等待时间。
"""

import hashlib
import time
from typing import Any, Callable, Dict, Optional
from config import UPLOADS_DIR, get_logger
from plugins.base import BaseCleaner, BaseReasoner, BaseTranscriber
from plugins.registry import create_cleaner, create_reasoner, create_transcriber

logger = get_logger()


class PipelineManager:
    """
    几何微课三阶段流水线管理器。
    """

    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
        self.pipeline_cfg = config_data.get("pipeline", {})
        self.enable_cache = bool(self.pipeline_cfg.get("enable_stage_cache", True))

        cleaner_name = self.pipeline_cfg.get("cleaner_provider", "textin")
        cleaner_cfg = config_data.get("cleaner", {}).get(cleaner_name, {})
        self.cleaner: BaseCleaner = create_cleaner(cleaner_name, cleaner_cfg)

        transcriber_name = self.pipeline_cfg.get("transcriber_provider", "gemini_rpc")
        transcriber_cfg = config_data.get("transcriber", {}).get(transcriber_name, {})
        self.transcriber: BaseTranscriber = create_transcriber(transcriber_name, transcriber_cfg)

        reasoner_name = self.pipeline_cfg.get("reasoner_provider", "deepseek")
        reasoner_cfg = config_data.get("reasoner", {}).get(reasoner_name, {})
        self.reasoner: BaseReasoner = create_reasoner(reasoner_name, reasoner_cfg)

    def validate_all(self) -> None:
        """
        验证全流程凭证。任何一个缺失都会直接抛出异常并在服务启动时提示。
        """
        logger.info("🔍 正在检查各阶段模型与 API 凭证配置...")
        self.cleaner.validate_credentials()
        logger.info("  ✅ 阶段 1: Cleaner (%s) 凭证校验通过", self.cleaner.__class__.__name__)
        self.transcriber.validate_credentials()
        logger.info("  ✅ 阶段 2: Transcriber (%s) 状态校验通过", self.transcriber.__class__.__name__)
        self.reasoner.validate_credentials()
        logger.info("  ✅ 阶段 3: Reasoner (%s) 凭证校验通过", self.reasoner.__class__.__name__)
        logger.info("🎉 全部三阶段模型插件配置就绪！")

    def run_pipeline(
        self,
        raw_image_bytes: bytes,
        mime_type: str = "image/png",
        extra_note: str = "",
        model_override: Optional[str] = None,
        enable_transcription: bool = True,
        transcription_model: Optional[str] = None,
        progress_cb: Optional[Callable[[int, str, str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """
        端到端执行微课推演：
        - 若 enable_transcription 为 False：跳过 TextIn 清洗与 Gemini 转录，直接调用 Gemini 原生多模态看图解题；
        - 若 enable_transcription 为 True：执行完整三阶段流水线（TextIn ➔ Gemini 空间转录 ➔ 推理大模型证明）。
        """
        def notify(stage: int, title: str, text: str, log_type: str = "info"):
            if cancel_check and cancel_check():
                raise RuntimeError("用户已取消推演")
            if progress_cb:
                try:
                    progress_cb(stage, title, text, log_type)
                except Exception as e:
                    logger.debug("progress_cb error: %s", e)

        start_time = time.time()
        ts = int(start_time)
        img_hash = hashlib.sha256(raw_image_bytes).hexdigest()[:16]

        # ==========================================
        # 分支 A: 原生多模态直接解题（跳过清洗与转录）
        # ==========================================
        if not enable_transcription:
            model_disp = model_override or "Gemini"
            notify(3, "极速原生看图推演", f"🚀 正在调用 {model_disp} 进行原生多模态几何推演与交互板书生成...", "info")
            logger.info(
                "⚡ [极速直连解题] 用户未开启图转文字，跳过 TextIn 与转录，直接调用 %s (model=%s) 进行原生多模态看图推演...",
                self.reasoner.__class__.__name__,
                model_override,
            )
            t_start = time.time()
            lesson_data = self.reasoner.solve(
                problem_description="",
                extra_note=extra_note,
                model_override=model_override,
                image_bytes=raw_image_bytes,
                mime_type=mime_type,
            )
            total_cost = round(time.time() - start_time, 1)
            reason_cost = round(time.time() - t_start, 2)
            logger.info("🎉 [极速直连解题] 原生多模态推演完成！耗时 %s 秒", reason_cost)
            notify(3, "推演完成", f"🎉 原生视觉几何证明与板书生成完毕！（耗时 {reason_cost} 秒）", "success")
            return {
                "lessonData": lesson_data,
                "problemDescription": "",
                "cleanImageBytes": raw_image_bytes,
                "elapsed": total_cost,
                "stageElapsed": {
                    "reasoner": reason_cost,
                },
            }

        # ==========================================
        # 分支 B: 完整三阶段高精度流水线
        # ==========================================
        trans_slug = transcription_model or "gemini-3.8-flash-medium"
        cache_clean_path = UPLOADS_DIR / f"cache_{img_hash}_clean.png"
        cache_desc_path = UPLOADS_DIR / f"cache_{img_hash}_{trans_slug}_transcription.txt"

        # ==========================================
        # 阶段 1: 底图物理清洗（TextIn）
        # ==========================================
        notify(1, "底图去笔迹", "🧹 正在物理擦除试卷笔迹、手写草稿与干扰红线...", "info")
        t1 = time.time()
        if self.enable_cache and cache_clean_path.exists() and cache_clean_path.stat().st_size > 100:
            clean_image_bytes = cache_clean_path.read_bytes()
            t1_cost = round(time.time() - t1, 2)
            logger.info(
                "⚡ [Stage 1/3] 命中原图指纹缓存 (hash=%s)，直接复用已擦除底图 (%d 字节, 耗时 %ss)",
                img_hash,
                len(clean_image_bytes),
                t1_cost,
            )
            notify(1, "底图去笔迹", f"⚡ 命中试卷底图缓存，已毫秒级复用去笔迹高清图（耗时 {t1_cost} 秒）", "success")
        else:
            logger.info(
                "🧹 [Stage 1/3] 正在调用 %s 擦除试卷笔迹与手写草稿 (原始大小=%d bytes, hash=%s)...",
                self.cleaner.__class__.__name__,
                len(raw_image_bytes),
                img_hash,
            )
            clean_image_bytes = self.cleaner.clean_image(raw_image_bytes, mime_type)
            t1_cost = round(time.time() - t1, 2)

            clean_path = UPLOADS_DIR / f"clean_{ts}.png"
            try:
                clean_path.write_bytes(clean_image_bytes)
                cache_clean_path.write_bytes(clean_image_bytes)
                logger.debug("💾 [Stage 1/3] 清洗后底图已落盘保存至: %s (及缓存 %s)", clean_path, cache_clean_path.name)
            except Exception as e:
                logger.warning("⚠️ 保存清洗后底图异常: %s", e)

            logger.info(
                "✨ [Stage 1/3] 笔迹擦除完成！耗时 %s 秒，生成纯净底图 (%d 字节 -> %s)",
                t1_cost,
                len(clean_image_bytes),
                clean_path.name,
            )
            notify(1, "底图去笔迹", f"✨ 试卷笔迹擦除完毕！已生成纯净印刷底图（耗时 {t1_cost} 秒）", "success")

        # ==========================================
        # 阶段 2: 空间视觉与题设转录（Gemini）
        # ==========================================
        notify(2, "空间题设转录", f"📐 正在精准提取试题题设 LaTeX 公式与几何空间拓扑结构...", "info")
        t2 = time.time()
        hit_cache_path = None
        if self.enable_cache and cache_desc_path.exists() and cache_desc_path.stat().st_size > 40:
            hit_cache_path = cache_desc_path

        if hit_cache_path:
            problem_description = hit_cache_path.read_text(encoding="utf-8")
            t2_cost = round(time.time() - t2, 2)
            logger.info(
                "⚡ [Stage 2/3] 命中原图指纹缓存 (hash=%s, model=%s)，直接复用已转录题干描述 (%d 字符, 耗时 %ss)",
                img_hash,
                trans_slug,
                len(problem_description),
                t2_cost,
            )
            notify(2, "空间题设转录", f"⚡ 命中题设描述缓存，已秒级复用几何命题与空间拓扑描述（耗时 {t2_cost} 秒）", "success")
        else:
            logger.info(
                "📝 [Stage 2/3] 正在调用 %s (model=%s) 转录题干与图形拓扑结构（严禁解题）...",
                self.transcriber.__class__.__name__,
                trans_slug,
            )
            problem_description = self.transcriber.transcribe(
                clean_image_bytes,
                mime_type,
                model_override=trans_slug,
            )
            t2_cost = round(time.time() - t2, 2)

            desc_path = UPLOADS_DIR / f"transcription_{ts}.txt"
            try:
                desc_path.write_text(problem_description, encoding="utf-8")
                cache_desc_path.write_text(problem_description, encoding="utf-8")
                logger.debug("💾 [Stage 2/3] 题设转录文本已落盘保存至: %s (及缓存 %s)", desc_path, cache_desc_path.name)
            except Exception as e:
                logger.warning("⚠️ 保存题设转录文本异常: %s", e)

            logger.info(
                "📐 [Stage 2/3] 题设转录完成！耗时 %s 秒，提取命题描述 (%d 字符 -> %s)",
                t2_cost,
                len(problem_description),
                desc_path.name,
            )
            notify(2, "空间题设转录", f"📐 题设 LaTeX 公式与几何空间拓扑提取完成（耗时 {t2_cost} 秒）", "success")

        # ==========================================
        # 阶段 3: 深度证明与绘图架构（DeepSeek / Gemini）
        # ==========================================
        t3 = time.time()
        reasoner_name_disp = "DeepSeek R1" if "deepseek" in (model_override or "").lower() else (model_override or "推理大模型")
        notify(3, "深度几何推演", f"🧠 正在调用 {reasoner_name_disp} 进行深度逻辑证明、构造辅助线与 GeoGebra 交互板书...", "info")
        logger.info(
            "🧠 [Stage 3/3] 正在调用 %s (model_override=%s) 进行深度几何证明与 GeoGebra 板书架构...",
            self.reasoner.__class__.__name__,
            model_override,
        )
        lesson_data = self.reasoner.solve(
            problem_description=problem_description,
            extra_note=extra_note,
            model_override=model_override,
        )
        t3_cost = round(time.time() - t3, 2)
        total_cost = round(time.time() - start_time, 1)
        logger.info(
            "🎉 [Stage 3/3] 几何推演与板书生成完毕！Stage3耗时 %s 秒 (全链路总耗时 %s 秒)",
            t3_cost,
            total_cost,
        )
        notify(3, "推演完成", f"🎉 几何证明、讲解分步板书与 GeoGebra 交互动态图已全部生成！（总耗时 {total_cost} 秒）", "success")

        return {
            "lessonData": lesson_data,
            "problemDescription": problem_description,
            "cleanImageBytes": clean_image_bytes,
            "elapsed": total_cost,
            "stageElapsed": {
                "cleaner": t1_cost,
                "transcriber": t2_cost,
                "reasoner": t3_cost,
            },
        }
