#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - 核心推演与解题调度模块 (solver.py)
=====================================================
功能说明：
1. 封装 Antigravity LanguageServerService 本地 RPC 通信管道 (agy_rpc)；
2. 调度多模态视觉推理：在当前沙箱工作区独立创建 Cascade 推演会话；
3. 执行非阻塞发送与秒级轮询，绕过语言服务网关 300 秒连接截断限制；
4. 捕获模型原始输出，调用自愈管线提取微课数据并覆写 `lesson.js`；
5. 在 finally 块中自动清理临时推演会话，保持 Antigravity 界面干净无污染。
"""

import base64
import json
import time
import urllib.request
from config import (
    DEFAULT_MODEL_SLUG,
    LESSON_JS_PATH,
    MAX_POLL_TIMEOUT_SECONDS,
    POLL_INTERVAL_SECONDS,
    WORKSPACE_DIR,
    get_model_id,
)
from prompts import build_strict_json_prompt
from utils import discover_local_antigravity_server, extract_json_from_text


def agy_rpc(server_info: dict, method: str, payload: dict, timeout: int = 600) -> dict:
    """
    向本地 Antigravity LanguageServerService 发起 RPC 请求。

    Args:
        server_info (dict): 包含 'port' 和 'csrf_token' 等连接信息的字典。
        method (str): RPC 方法名，例如 'StartCascade'、'SendUserCascadeMessage' 等。
        payload (dict): 请求载荷字典，将被序列化为 JSON 提交。
        timeout (int, optional): 请求单次 HTTP 超时时间（秒），默认为 600。

    Returns:
        dict: 服务端反序列化后的 JSON 响应字典。

    Raises:
        urllib.error.URLError: 当网络通信受阻或端口不可达时抛出。
        json.JSONDecodeError: 当服务端返回非法 JSON 时抛出。
    """
    url = f"http://127.0.0.1:{server_info['port']}/exa.language_server_pb.LanguageServerService/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-codeium-csrf-token": server_info["csrf_token"],
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def solve_problem_automatically(
    image_bytes: bytes,
    mime_type: str,
    extra_note: str = "",
    model_slug: str = DEFAULT_MODEL_SLUG,
) -> dict:
    """
    全自动调度本机 Antigravity Pro 会员通道识别几何题并生成交互微课数据。

    工作流程：
    1. 自动探测本地 language_server 端口与 CSRF Token；
    2. 创建限定在当前工作区路径的临时 Cascade 交互会话；
    3. 构建含教学规则与 JSON 契约的强约束 Prompt，绑定图片 Base64 异步提交；
    4. 采用非阻塞轮询架构持续获取推演进度（上限 900 秒），防止网关强制断开；
    5. 调用四级自愈引擎提取结构化 JSON 数据并持久化写入 `lesson.js`；
    6. 自动调用 DeleteCascadeTrajectory 销毁临时推演会话。

    Args:
        image_bytes (bytes): 用户上传的原始图片二进制数据。
        mime_type (str): 图片的 MIME 类型（如 'image/png', 'image/jpeg'）。
        extra_note (str, optional): 用户补充的讲题要求（如“禁止使用三角函数”）。默认为空字符串。
        model_slug (str, optional): 前端选定的模型标识。默认为 DEFAULT_MODEL_SLUG。

    Returns:
        dict: 包含以下字段的结果字典：
            - 'lessonData' (dict): 结构化微课全量数据；
            - 'model' (str): 实际使用的模型 slug；
            - 'user' (str): 当前连接的 Antigravity 用户名；
            - 'elapsed' (float): 本次推演计算耗时秒数。

    Raises:
        RuntimeError: 当 Antigravity 未启动、会话创建失败或推演超时时抛出。
        ValueError: 当模型回复无法解析为有效微课 JSON 时抛出。
    """
    server_info = discover_local_antigravity_server()
    if not server_info:
        raise RuntimeError("未检测到正在运行的 Antigravity 客户端进程，请确认 Antigravity 已打开。")

    plan_model = get_model_id(model_slug)
    cascade_id: str | None = None

    try:
        # 1. 创建隔离在当前 math-tutor-workspace 的临时会话
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
            raise RuntimeError("创建 Antigravity 推演会话失败，未获取到 cascadeId。")

        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        prompt = build_strict_json_prompt(extra_note)

        # 2. 发送图片 + 强约束 Prompt（非阻塞方式发送，通过轮询避免单个 HTTP 长连接触发网关 300 秒超时）
        agy_rpc(
            server_info,
            "SendUserCascadeMessage",
            {
                "cascadeId": cascade_id,
                "items": [{"text": prompt}],
                "media": [
                    {
                        "mimeType": mime_type,
                        "inlineData": b64_img,
                        "description": "geometry_problem.png",
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

        # 3. 轮询读取模型响应（最长等待 MAX_POLL_TIMEOUT_SECONDS，每 POLL_INTERVAL_SECONDS 轮询一次）
        start_time = time.time()
        model_reply: str = ""
        poll_count: int = 0
        print(f"[{time.strftime('%H:%M:%S')}] 🚀 已发起模型推演请求 (模型: {model_slug})，开始轮询等待结果...", flush=True)

        while time.time() - start_time < MAX_POLL_TIMEOUT_SECONDS:
            time.sleep(POLL_INTERVAL_SECONDS)
            poll_count += 1
            if poll_count % 10 == 0:
                print(
                    f"[{time.strftime('%H:%M:%S')}] ⏳ 模型正在深度思考与排版板书... (已耗时 {int(time.time() - start_time)} 秒)",
                    flush=True,
                )

            steps_res: dict | None = None
            try:
                steps_res = agy_rpc(
                    server_info,
                    "GetCascadeTrajectorySteps",
                    {"cascadeId": cascade_id},
                    timeout=15,
                )
            except Exception as ep:
                if poll_count % 10 == 0:
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 轮询暂未就绪 ({ep})，继续等待...", flush=True)
                continue

            steps = steps_res.get("steps", []) if steps_res else []
            for st in reversed(steps):
                st_type = st.get("type", "")
                if st_type in ("CORTEX_STEP_TYPE_PLANNER_RESPONSE", "PLANNER_RESPONSE"):
                    status = st.get("status", "")
                    resp_text = (
                        st.get("plannerResponse", {}).get("response", "")
                        or st.get("content", "")
                    )
                    # 当且仅当生成完毕且有实质内容时接收
                    if resp_text.strip():
                        if status in ("CORTEX_STEP_STATUS_DONE", "DONE", "SUCCESS") or st.get("plannerResponse", {}).get("finishReason"):
                            model_reply = resp_text
                            break
                        # 若已出现完整 JSON 闭合也判定完成
                        elif resp_text.strip().endswith("}") or resp_text.strip().endswith("```"):
                            model_reply = resp_text
                            break

            if model_reply:
                print(
                    f"[{time.strftime('%H:%M:%S')}] 🎉 模型推演完成！耗时 {int(time.time() - start_time)} 秒，输出 {len(model_reply)} 字符",
                    flush=True,
                )
                break

        if not model_reply:
            raise RuntimeError(
                f"模型在 {int(time.time() - start_time)} 秒内未完成推演，请重试或切换为 Flash-Medium 模式。"
            )

        lesson_data = extract_json_from_text(model_reply)

        # 4. 覆写到工作区的 lesson.js 中持久化
        js_content = "window.LESSON_DATA = " + json.dumps(lesson_data, ensure_ascii=False, indent=2) + ";\n"
        LESSON_JS_PATH.write_text(js_content, encoding="utf-8")

        elapsed_seconds = round(time.time() - start_time, 1)
        return {
            "lessonData": lesson_data,
            "model": model_slug,
            "user": server_info.get("user", "Pro User"),
            "elapsed": elapsed_seconds,
        }
    finally:
        # 5. 自动清理临时会话，保持用户的 Antigravity 聊天列表干净无污染
        if cascade_id and server_info:
            try:
                agy_rpc(server_info, "DeleteCascadeTrajectory", {"cascadeId": cascade_id}, timeout=10)
            except Exception:
                pass
