#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemini 本地 Antigravity RPC 证明与绘图架构师插件 (plugins/reasoners/gemini_rpc_reasoner.py)
=============================================================================
纯文本输入，通过本地 Antigravity RPC 管道调度 Gemini 3.8 Flash / 4 Argon 等顶级模型
执行初中几何深度证明，识别经典几何模型，构造辅助线，
并输出 GeoGebra 辅助线绘制指令及符合前端契约的 JSON 数据结构。
"""

import base64
import time
from typing import Any, Dict, Optional
from config import UPLOADS_DIR, WORKSPACE_DIR, get_logger, get_model_id
from plugins.base import BaseReasoner
from prompts import build_reasoner_prompt, build_strict_json_prompt
from utils import agy_rpc, discover_local_antigravity_server, extract_json_from_text

logger = get_logger()


class GeminiRpcReasoner(BaseReasoner):
    """
    基于本地 Antigravity RPC 管道的纯文本几何证明架构师。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_slug = config.get("model_slug", "gemini-3.8-flash-high")
        self.timeout = config.get("timeout", 600)
        self.poll_interval = config.get("poll_interval", 2.0)

    def validate_credentials(self) -> None:
        srv = discover_local_antigravity_server()
        logger.debug("[GeminiRpcReasoner] 校验本地 RPC 状态: srv=%s", srv)
        if not srv:
            raise RuntimeError(
                "【Gemini 推理器启动失败】未检测到本机正在运行的 Antigravity 客户端！\n"
                "请确认 Antigravity 软件已打开并保持登录状态。"
            )

    def solve(
        self,
        problem_description: str = "",
        extra_note: str = "",
        model_override: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/png",
    ) -> Dict[str, Any]:
        """
        调度本地 Antigravity 进行几何深度证明与板书生成。
        支持双模：
        1. 纯文本模式：接收阶段 2 转录的几何命题纯文本描述；
        2. 原生多模态模式（当提供 image_bytes 时）：跳过清洗与转录，直接识图解题。
        """
        server_info = discover_local_antigravity_server()
        if not server_info:
            raise RuntimeError("未检测到本地 Antigravity 客户端，请保持客户端打开。")

        chosen_slug = model_override or self.model_slug
        plan_model = get_model_id(chosen_slug)
        cascade_id = None
        is_multimodal = bool(image_bytes and len(image_bytes) > 0)

        logger.debug(
            "➡️ [GeminiRpcReasoner] 开始推演 | mode=%s | model_slug=%s (%s) | prompt_chars=%d | port=%s",
            "原生多模态直接识图" if is_multimodal else "纯文本命题推演",
            chosen_slug,
            plan_model,
            len(problem_description) if not is_multimodal else len(image_bytes),
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
            if not cascade_id:
                raise RuntimeError(f"创建 Antigravity 会话失败: {start_res}")

            if is_multimodal:
                prompt = build_strict_json_prompt(extra_note)
                b64_img = base64.b64encode(image_bytes).decode("utf-8")
                media_payload = [
                    {
                        "mimeType": mime_type,
                        "inlineData": b64_img,
                        "description": "geometry_problem.png",
                    }
                ]
            else:
                prompt = build_reasoner_prompt(problem_description, extra_note)
                media_payload = []

            send_body = {
                "cascadeId": cascade_id,
                "items": [{"text": prompt}],
                "blocking": False,
                "cascadeConfig": {
                    "plannerConfig": {
                        "planModel": plan_model,
                    }
                },
            }
            if media_payload:
                send_body["media"] = media_payload

            agy_rpc(server_info, "SendUserCascadeMessage", send_body, timeout=30)

            start_time = time.time()
            model_reply = ""
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
                    logger.debug("⚠️ [GeminiRpcReasoner] 轮询第 %d 次暂未就绪 (%s)", poll_count, ep)
                    continue

                steps = steps_res.get("steps", []) if steps_res else []
                latest_resp_text = ""
                latest_status = ""
                latest_finish_reason = ""
                latest_think_len = 0

                for idx, st in enumerate(steps):
                    st_type = st.get("type", "")
                    status = st.get("status", "")
                    pr = st.get("plannerResponse", {}) if isinstance(st.get("plannerResponse"), dict) else {}
                    finish_reason = pr.get("finishReason", "")
                    resp_text = pr.get("response", "") or st.get("content", "")
                    thinking_text = pr.get("thinking", "") or st.get("thinking", "")

                    if st_type in ("CORTEX_STEP_TYPE_PLANNER_RESPONSE", "PLANNER_RESPONSE") and resp_text.strip():
                        latest_resp_text = resp_text.strip()
                        latest_status = status
                        latest_finish_reason = finish_reason
                        latest_think_len = len(thinking_text)

                if poll_count % 5 == 0 or (latest_resp_text and poll_count % 2 == 0):
                    logger.debug(
                        "⏳ [Gemini 推演中] Poll #%d (耗时 %ss) | steps=%d | think_len=%d | resp_len=%d | status=%s | finish=%s",
                        poll_count,
                        elapsed,
                        len(steps),
                        latest_think_len,
                        len(latest_resp_text),
                        latest_status,
                        latest_finish_reason,
                    )

                if latest_resp_text:
                    # 判定条件 1：出现显式结束信标 ===END_OF_LESSON===
                    if "===END_OF_LESSON===" in latest_resp_text:
                        logger.info("✅ [GeminiRpcReasoner] 命中结束标记 ===END_OF_LESSON===，推演完毕！")
                        model_reply = latest_resp_text.replace("===END_OF_LESSON===", "").strip()
                        break

                    # 判定条件 2：JSON 已经完整自然闭合（以 } 或 ``` 结尾）
                    if latest_resp_text.endswith("}") or latest_resp_text.endswith("```"):
                        if "{" in latest_resp_text and ("\"questions\"" in latest_resp_text or "'questions'" in latest_resp_text):
                            logger.info("✅ [GeminiRpcReasoner] 命中 JSON 自然闭合（以 } 结尾），推演完毕！")
                            model_reply = latest_resp_text
                            break

                    # 判定条件 3：底层明确标记完成状态或明确停机原因
                    is_status_done = latest_status in (
                        "CORTEX_STEP_STATUS_DONE",
                        "DONE",
                        "SUCCESS",
                        "CORTEX_STEP_STATUS_COMPLETED",
                        "COMPLETED",
                        "CORTEX_STEP_STATUS_SUCCEEDED",
                    )
                    is_finish_stopped = latest_finish_reason in ("STOP", "END_TURN", "FINISH_REASON_STOP", "MAX_TOKENS")

                    if is_status_done or is_finish_stopped:
                        if latest_resp_text == last_candidate_text or is_finish_stopped:
                            logger.info(
                                "✅ [GeminiRpcReasoner] 命中完成状态 (status=%s, finish=%s, len=%d)，推演完毕！",
                                latest_status,
                                latest_finish_reason,
                                len(latest_resp_text),
                            )
                            model_reply = latest_resp_text
                            break

                    # 判定条件 4：文本稳定检测（防止某些模型 status 滞后，但流已彻底停更）
                    if latest_resp_text == last_candidate_text and len(latest_resp_text) > 100:
                        stable_ticks += 1
                        if stable_ticks >= 4:
                            logger.info("✅ [GeminiRpcReasoner] 内容已连续 4 次轮询稳定无变化，判定推演完毕！")
                            model_reply = latest_resp_text
                            break
                    else:
                        stable_ticks = 0
                        last_candidate_text = latest_resp_text

            if not model_reply and latest_resp_text:
                logger.warning("⚠️ [GeminiRpcReasoner] 轮询超时但捕获到了部分文本 (len=%d)，尝试提交自愈解析", len(latest_resp_text))
                model_reply = latest_resp_text

            if not model_reply:
                raise RuntimeError(f"Gemini 几何推演在 {self.timeout} 秒内未完成。")

            try:
                (UPLOADS_DIR / "last_raw_model_reply.txt").write_text(model_reply, encoding="utf-8")
            except Exception as ew:
                logger.debug("写入 last_raw_model_reply.txt 异常: %s", ew)

            lesson_data = extract_json_from_text(model_reply)
            return lesson_data

        finally:
            if cascade_id and server_info:
                try:
                    agy_rpc(server_info, "DeleteCascadeTrajectory", {"cascadeId": cascade_id}, timeout=10)
                except Exception:
                    pass
