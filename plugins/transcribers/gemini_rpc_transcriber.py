#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemini 本地 Antigravity RPC 题设转录插件 (plugins/transcribers/gemini_rpc_transcriber.py)
===================================================================================
通过本地 Antigravity RPC 通道（免外部 API Key，复用用户 Pro/Flash 权益），
将去除笔迹后的干净底图转录为严谨、毫无歧义的几何命题纯文本描述（包含标准 LaTeX）。
【核心铁律】：只负责录入题干与识别图形拓扑，严禁解题，严禁输出任何证明步骤或辅助线！
"""

import base64
import time
from typing import Any, Dict, Optional
from config import WORKSPACE_DIR, get_logger, get_model_id
from plugins.base import BaseTranscriber
from prompts import build_transcription_prompt
from utils import agy_rpc, discover_local_antigravity_server

logger = get_logger()


class GeminiRpcTranscriber(BaseTranscriber):
    """
    基于本地 Antigravity RPC 管道的 Gemini 转录器（带全链路 DEBUG 日志与三重完成判定）。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_slug = config.get("model_slug", "gemini-3.8-flash-high")
        self.timeout = config.get("timeout", 300)
        self.poll_interval = config.get("poll_interval", 1.5)

    def validate_credentials(self) -> None:
        """
        验证本机 Antigravity 服务进程是否存活并开启 RPC。
        """
        srv = discover_local_antigravity_server()
        logger.debug("[GeminiRpcTranscriber] 校验本地 RPC 状态: srv=%s", srv)
        if not srv:
            raise RuntimeError(
                "【Gemini 转录器启动失败】未检测到本机正在运行的 Antigravity 客户端！\n"
                "请确认 Antigravity 软件已打开并保持登录状态。"
            )

    def transcribe(
        self,
        clean_image_bytes: bytes,
        mime_type: str = "image/png",
        model_override: Optional[str] = None,
    ) -> str:
        """
        调用本地 Antigravity 发起视觉识别转录，输出详细 DEBUG 轨迹日志。
        """
        server_info = discover_local_antigravity_server()
        if not server_info:
            raise RuntimeError("未检测到本地 Antigravity 客户端，请保持客户端打开。")

        chosen_slug = model_override or self.model_slug
        plan_model = get_model_id(chosen_slug)
        cascade_id = None

        logger.debug(
            "➡️ [GeminiRpcTranscriber] 开始视觉转录 | model_slug=%s (%s) | image_size=%d bytes | mime=%s | port=%s",
            chosen_slug,
            plan_model,
            len(clean_image_bytes),
            mime_type,
            server_info.get("port"),
        )

        try:
            start_res = agy_rpc(
                server_info,
                "StartCascade",
                {
                    "source": "CORTEX_TRAJECTORY_SOURCE_CASCADE_CLIENT",
                    "trajectoryType": "CORTEX_TRAJECTORY_TYPE_INTERACTIVE_CASCADE",
                    "workspaceUris": [f"file://{WORKSPACE_DIR}"],
                },
            )
            cascade_id = start_res.get("cascadeId")
            logger.debug("[GeminiRpcTranscriber] StartCascade 成功: cascade_id=%s", cascade_id)
            if not cascade_id:
                raise RuntimeError(f"创建 Antigravity 转录会话失败，返回: {start_res}")

            b64_img = base64.b64encode(clean_image_bytes).decode("utf-8")
            prompt = build_transcription_prompt()

            send_res = agy_rpc(
                server_info,
                "SendUserCascadeMessage",
                {
                    "cascadeId": cascade_id,
                    "items": [{"text": prompt}],
                    "media": [
                        {
                            "mimeType": mime_type,
                            "inlineData": b64_img,
                            "description": "clean_geometry.png",
                        }
                    ],
                    "blocking": False,
                    "cascadeConfig": {
                        "plannerConfig": {
                            "planModel": plan_model,
                        }
                    },
                },
                timeout=30,
            )
            logger.debug("[GeminiRpcTranscriber] SendUserCascadeMessage 响应: %s", send_res)

            start_time = time.time()
            transcription_text = ""
            poll_count = 0
            last_candidate_text = ""
            stable_ticks = 0

            while time.time() - start_time < self.timeout:
                time.sleep(self.poll_interval)
                poll_count += 1
                elapsed = round(time.time() - start_time, 1)

                steps_res = None
                try:
                    steps_res = agy_rpc(
                        server_info,
                        "GetCascadeTrajectorySteps",
                        {"cascadeId": cascade_id},
                        timeout=15,
                    )
                except Exception as ep:
                    logger.warning(
                        "⚠️ [GeminiRpcTranscriber] Poll #%d (耗时 %ss) GetCascadeTrajectorySteps 异常: %s",
                        poll_count,
                        elapsed,
                        ep,
                    )
                    continue

                steps = steps_res.get("steps", []) if steps_res else []

                # 收集当前所有 step 的摘要用于 DEBUG 观察
                step_summaries = []
                latest_resp_text = ""
                latest_status = ""
                latest_finish_reason = ""

                for idx, st in enumerate(steps):
                    st_type = st.get("type", "")
                    status = st.get("status", "")
                    pr = st.get("plannerResponse", {}) if isinstance(st.get("plannerResponse"), dict) else {}
                    finish_reason = pr.get("finishReason", "")
                    resp_text = pr.get("response", "") or st.get("content", "")
                    thinking_text = pr.get("thinking", "") or st.get("thinking", "")
                    tool_calls = pr.get("toolCalls", []) or st.get("toolCalls", [])

                    step_summaries.append(
                        f"#{idx}[type={st_type}, status={status}, finish={finish_reason}, "
                        f"think_len={len(thinking_text)}, resp_len={len(resp_text)}, tools={len(tool_calls)}]"
                    )

                    if st_type in ("CORTEX_STEP_TYPE_PLANNER_RESPONSE", "PLANNER_RESPONSE") and resp_text.strip():
                        latest_resp_text = resp_text.strip()
                        latest_status = status
                        latest_finish_reason = finish_reason

                logger.debug(
                    "🔄 [GeminiRpcTranscriber] Poll #%d (耗时 %ss) | steps(%d): %s",
                    poll_count,
                    elapsed,
                    len(steps),
                    " ; ".join(step_summaries) if step_summaries else "<EMPTY>",
                )

                if latest_resp_text:
                    preview = latest_resp_text[-80:].replace("\n", "\\n")
                    logger.debug(
                        "📝 [GeminiRpcTranscriber] 当前捕获文本 (len=%d, status=%s, finish=%s) 尾部预览: ...%s",
                        len(latest_resp_text),
                        latest_status,
                        latest_finish_reason,
                        preview,
                    )

                    # 判定条件 1：出现显式结束标记 ===END_OF_TRANSCRIPTION===
                    if "===END_OF_TRANSCRIPTION===" in latest_resp_text:
                        logger.debug("✅ [GeminiRpcTranscriber] 命中结束标记 ===END_OF_TRANSCRIPTION===，立即完成！")
                        transcription_text = latest_resp_text.replace("===END_OF_TRANSCRIPTION===", "").strip()
                        break

                    # 判定条件 2：状态枚举表明已完成
                    if (
                        latest_status in (
                            "CORTEX_STEP_STATUS_DONE",
                            "DONE",
                            "SUCCESS",
                            "CORTEX_STEP_STATUS_COMPLETED",
                            "COMPLETED",
                            "CORTEX_STEP_STATUS_SUCCEEDED",
                        )
                        or latest_finish_reason
                    ):
                        logger.debug(
                            "✅ [GeminiRpcTranscriber] 命中完成状态 (status=%s, finishReason=%s)，立即完成！",
                            latest_status,
                            latest_finish_reason,
                        )
                        transcription_text = latest_resp_text.replace("===END_OF_TRANSCRIPTION===", "").strip()
                        break

                    # 判定条件 3：文本已具备实质长度且连续 3 次轮询（约 4.5 秒）内容不再增长
                    if len(latest_resp_text) >= 40:
                        if latest_resp_text == last_candidate_text:
                            stable_ticks += 1
                            logger.debug(
                                "⏱️ [GeminiRpcTranscriber] 文本稳定计数 stable_ticks=%d/3 (len=%d)",
                                stable_ticks,
                                len(latest_resp_text),
                            )
                            if stable_ticks >= 3:
                                logger.debug("✅ [GeminiRpcTranscriber] 文本连续 3 次轮询稳定无变化，判定生成完毕！")
                                transcription_text = latest_resp_text.replace("===END_OF_TRANSCRIPTION===", "").strip()
                                break
                        else:
                            last_candidate_text = latest_resp_text
                            stable_ticks = 0

            # 如果超时退出时已经有捕获到的非空文本，也直接采用并告警，避免白白丢弃成果
            if not transcription_text and last_candidate_text:
                logger.warning(
                    "⚠️ [GeminiRpcTranscriber] 达到超时上限但已捕获到非空转录文本 (%d 字符)，直接采用该文本！",
                    len(last_candidate_text),
                )
                transcription_text = last_candidate_text.replace("===END_OF_TRANSCRIPTION===", "").strip()

            if not transcription_text:
                raise RuntimeError(f"Gemini 视觉转录在 {self.timeout} 秒内未完成，请查看控制台 DEBUG 日志排查。")

            logger.debug(
                "🎉 [GeminiRpcTranscriber] 转录全文结果 (%d 字符):\n%s",
                len(transcription_text),
                transcription_text,
            )
            return transcription_text

        finally:
            if cascade_id and server_info:
                try:
                    logger.debug("[GeminiRpcTranscriber] 正在清理临时会话 cascade_id=%s", cascade_id)
                    agy_rpc(server_info, "DeleteCascadeTrajectory", {"cascadeId": cascade_id}, timeout=10)
                except Exception as e:
                    logger.debug("[GeminiRpcTranscriber] 清理临时会话忽略异常: %s", e)
