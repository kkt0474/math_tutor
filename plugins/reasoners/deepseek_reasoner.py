#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek 旗舰推理版证明与绘图架构师插件 (plugins/reasoners/deepseek_reasoner.py)
========================================================================
负责纯文本输入，调用 DeepSeek OpenAI 兼容接口（如 deepseek-v4-pro / deepseek-reasoner / deepseek-flash），
开启深度思维链（Thinking），进行初中几何深度证明，识别经典几何模型，
输出 GeoGebra 辅助线绘制指令及符合前端契约的 JSON 数据结构。

核心工程特性：
1. 采用 SSE 流式传输 (stream=True)：1~2 秒内即可收到 HTTP 200 响应头并持续接收 Token，
   彻底杜绝非流式 (stream=False) 模式下长达数分钟无响应导致的控制台假死与 NAT/网关断连；
2. 实时控制台心跳打印：每 3 秒输出一次 DeepSeek 正在进行的深度思考链 (reasoning_content) 与板书生成进度；
3. 智能 DNS 探测与 15 秒快速连接切换：自动检测域名是否解析为代理 Fake-IP (198.18.x.x)，
   若直连在 15 秒内未建立流式响应则立即自动切换系统代理模式，不再傻等 600 秒；
4. 模型名自动容错：若账号不支持 deepseek-v4-pro 自动无缝回退至 deepseek-reasoner。
"""

import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from config import get_logger, mask_secret
from plugins.base import BaseReasoner
from prompts import build_reasoner_prompt
from utils import build_http_opener, create_ssl_context, extract_json_from_text

logger = get_logger()


class DeepSeekReasoner(BaseReasoner):
    """
    DeepSeek 推理大模型插件实现（基于 SSE 流式 OpenAI 兼容 Chat Completions REST API）。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = (
            os.environ.get("DEEPSEEK_API_KEY", "").strip()
            or config.get("api_key", "").strip()
        )
        self.base_url = config.get("base_url", "https://api.deepseek.com").rstrip("/")
        self.model = config.get("model", "deepseek-v4-pro")
        # 建立连接与首包响应超时（秒）：流式模式下正常 1~5 秒即返回 HTTP 200，设为 20 秒可快速发现假死并切换代理
        self.connect_timeout = config.get("connect_timeout", 20)
        # 流式单次读取块超时（秒）
        self.chunk_timeout = config.get("chunk_timeout", 60)
        # 整体推理最大总时长（秒）
        self.timeout = config.get("timeout", 600)
        self.temperature = config.get("temperature", 0.3)
        self.use_proxy = bool(config.get("use_proxy", False))

    def validate_credentials(self) -> None:
        """
        校验 DeepSeek 凭据是否配置。
        """
        if not self.api_key:
            self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

        logger.debug(
            "[DeepSeekReasoner] 校验凭证: api_key=%s, base_url=%s, default_model=%s, connect_timeout=%ds, total_timeout=%ds, use_proxy=%s",
            mask_secret(self.api_key),
            self.base_url,
            self.model,
            self.connect_timeout,
            self.timeout,
            self.use_proxy,
        )

        if not self.api_key:
            raise ValueError(
                "【DeepSeek 凭据未配置】未检测到有效的 DeepSeek API Key！\n"
                "👉 请打开根目录下的 .env 文件，填写 DEEPSEEK_API_KEY。\n"
                "（如未创建可参考 .env.example 模板，填好后重新启动服务）"
            )

    def _determine_proxy_modes(self, req_url: str) -> List[bool]:
        """
        智能探测目标域名 DNS 与系统代理状态，决定尝试连接模式的先后顺序：
        - 如果域名被 Clash/Surge Enhanced Mode 解析成了 198.18.x.x (Fake-IP)，
          无代理直连必会卡死超时，此时优先使用系统代理模式 (True)！
        """
        sys_proxies = urllib.request.getproxies()
        parsed = urllib.parse.urlparse(req_url)
        host = parsed.hostname or "api.deepseek.com"
        resolved_ip = "unknown"
        try:
            resolved_ip = socket.gethostbyname(host)
        except Exception as e:
            logger.debug("[DeepSeekReasoner] DNS 解析 %s 异常: %s", host, e)

        logger.debug(
            "🌐 [DeepSeekReasoner] 网络环境诊断 | host=%s -> IP=%s | sys_proxies=%s | configured_use_proxy=%s",
            host,
            resolved_ip,
            sys_proxies,
            self.use_proxy,
        )

        # 若命中 Fake-IP (198.18.x.x)，必须走系统代理才能连通
        if resolved_ip.startswith("198.18.") and sys_proxies:
            logger.info("⚡ [DeepSeekReasoner] 检测到域名 %s 解析为代理虚拟 IP (%s)，自动优先使用系统代理模式！", host, resolved_ip)
            return [True, False]

        modes = [self.use_proxy]
        if sys_proxies and not self.use_proxy:
            modes.append(True)
        elif not sys_proxies and self.use_proxy:
            modes.append(False)
        return modes

    def _stream_chat_completion(
        self,
        opener: urllib.request.OpenerDirector,
        req_url: str,
        body_bytes: bytes,
        actual_model: str,
        mode_label: str,
    ) -> Tuple[str, str]:
        """
        发起流式 (SSE) 请求并实时读取、打印 DeepSeek 的思考链与正文输出。
        返回 (reasoning_text, content_text)。
        """
        req = urllib.request.Request(
            req_url,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "MathTutorWorkspace/2.0",
            },
            method="POST",
        )

        t_start = time.time()
        # 使用较短的 connect_timeout (默认 20s) 打开连接，若网络不通可迅速暴露而不卡死 10 分钟
        with opener.open(req, timeout=self.connect_timeout) as resp:
            conn_cost = round(time.time() - t_start, 2)
            content_type = resp.headers.get("Content-Type", "")
            logger.info(
                "🟢 [DeepSeekReasoner] 已成功建立连接 (%s) | HTTP %s | Content-Type=%s | 握手耗时=%ss，开始接收流式数据...",
                mode_label,
                resp.status,
                content_type,
                conn_cost,
            )

            # 连接建立后，将底层 socket 读超时调整为 chunk_timeout (60s)
            try:
                if hasattr(resp, "fp") and hasattr(resp.fp, "raw") and hasattr(resp.fp.raw, "_sock"):
                    resp.fp.raw._sock.settimeout(self.chunk_timeout)
            except Exception:
                pass

            # 如果服务端返回的不是 event-stream 而是普通 JSON
            if "text/event-stream" not in content_type.lower():
                raw_data = resp.read().decode("utf-8", errors="replace")
                logger.debug("[DeepSeekReasoner] 收到非流式完整 JSON (%d chars)", len(raw_data))
                res_obj = json.loads(raw_data)
                choices = res_obj.get("choices", [])
                if not choices:
                    raise RuntimeError(f"DeepSeek 返回结果为空 choices: {raw_data[:200]}")
                msg_obj = choices[0].get("message", {})
                return msg_obj.get("reasoning_content", "") or "", msg_obj.get("content", "") or ""

            reasoning_parts: List[str] = []
            content_parts: List[str] = []
            reasoning_len = 0
            content_len = 0
            chunk_count = 0
            first_token_logged = False
            last_log_time = time.time()

            for raw_line in resp:
                elapsed = round(time.time() - t_start, 1)
                if elapsed > self.timeout:
                    logger.warning("⚠️ [DeepSeekReasoner] 流式生成达到总超时上限 (%ds)，截断退出", self.timeout)
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith(":"):
                    # SSE keep-alive 注释行
                    logger.debug("💓 [DeepSeekReasoner] 收到服务端 SSE keep-alive 心跳 (已耗时 %ss)", elapsed)
                    continue
                if not line.startswith("data:"):
                    continue

                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    logger.info("🏁 [DeepSeekReasoner] 收到 SSE [DONE] 结束标志！总耗时=%ss", elapsed)
                    break

                try:
                    chunk_obj = json.loads(data_str)
                except Exception:
                    continue

                choices = chunk_obj.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                r_delta = delta.get("reasoning_content") or ""
                c_delta = delta.get("content") or ""

                if r_delta or c_delta:
                    chunk_count += 1
                    if not first_token_logged:
                        first_token_logged = True
                        logger.info(
                            "⚡ [DeepSeekReasoner] 收到首个有效 Token (TTFT=%ss)! 模型正在高速输出...",
                            elapsed,
                        )

                if r_delta:
                    reasoning_parts.append(r_delta)
                    reasoning_len += len(r_delta)
                if c_delta:
                    content_parts.append(c_delta)
                    content_len += len(c_delta)

                # 每隔 3 秒在控制台打印一次实时思考/输出进度，让你清楚看到模型正在干什么
                now = time.time()
                if now - last_log_time >= 3.0:
                    last_log_time = now
                    if content_len == 0 and reasoning_len > 0:
                        tail = "".join(reasoning_parts[-15:]).replace("\n", " ")[-70:]
                        logger.debug(
                            "🧠 [DeepSeek 深度思考中] 已耗时 %ss | 思考链: %d 字符 (chunks=%d) | 最新思考: ...%s",
                            elapsed,
                            reasoning_len,
                            chunk_count,
                            tail,
                        )
                    elif content_len > 0:
                        tail = "".join(content_parts[-15:]).replace("\n", " ")[-70:]
                        logger.debug(
                            "✍️ [DeepSeek 生成板书中] 已耗时 %ss | 思考链: %d 字符 | JSON正文: %d 字符 | 最新内容: ...%s",
                            elapsed,
                            reasoning_len,
                            content_len,
                            tail,
                        )

            full_reasoning = "".join(reasoning_parts)
            full_content = "".join(content_parts)
            logger.info(
                "📊 [DeepSeekReasoner] 流式接收完成 | 思考链总长=%d 字符 | JSON正文总长=%d 字符 | 总耗时=%ss",
                len(full_reasoning),
                len(full_content),
                round(time.time() - t_start, 2),
            )
            return full_reasoning, full_content

    def solve(
        self,
        problem_description: str,
        extra_note: str = "",
        model_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        接收阶段 2 转录的几何命题描述文本，调用 DeepSeek 流式推理并提取规范的微课 JSON。
        """
        self.validate_credentials()

        primary_model = model_override or self.model
        # 构建候选模型队列：若 deepseek-v4-pro 在部分标准 API 端点报 Model Not Exist，自动无缝回退到 deepseek-reasoner / deepseek-chat
        candidate_models = [primary_model]
        if primary_model == "deepseek-v4-pro":
            candidate_models.append("deepseek-reasoner")
        elif primary_model == "deepseek-flash":
            candidate_models.append("deepseek-chat")

        prompt = build_reasoner_prompt(problem_description, extra_note)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一名拥有 20 年一线中考把关经验的顶级数学名师与 GeoGebra 交互课件架构大师。"
                    "你的任务是深入推导几何题，识别几何模型，并输出严格符合规范的微课 JSON 字符串。"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        req_url = f"{self.base_url}/chat/completions"
        ssl_ctx = create_ssl_context()
        modes_to_try = self._determine_proxy_modes(req_url)

        last_err: Exception | None = None

        for actual_model in candidate_models:
            payload: Dict[str, Any] = {
                "model": actual_model,
                "messages": messages,
                "temperature": self.temperature,
                "stream": True,
            }
            if "chat" in actual_model or "flash" in actual_model:
                payload["response_format"] = {"type": "json_object"}

            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

            logger.debug(
                "➡️ [DeepSeekReasoner] 准备发起流式推理请求 | url=%s | model=%s | temp=%s | connect_timeout=%ds | prompt_len=%d chars | body_size=%d bytes",
                req_url,
                actual_model,
                self.temperature,
                self.connect_timeout,
                len(prompt),
                len(body_bytes),
            )

            model_not_exist = False

            for attempt_idx, proxy_mode in enumerate(modes_to_try, start=1):
                mode_label = "系统代理模式" if proxy_mode else "无代理直连模式(Direct)"
                opener = build_http_opener(proxy_mode, ssl_ctx)

                t0 = time.time()
                logger.debug(
                    "🚀 [DeepSeekReasoner] 尝试连接 #%d/%d (%s) -> POST %s (model=%s, stream=True)...",
                    attempt_idx,
                    len(modes_to_try),
                    mode_label,
                    req_url,
                    actual_model,
                )

                try:
                    reasoning_content, content = self._stream_chat_completion(
                        opener=opener,
                        req_url=req_url,
                        body_bytes=body_bytes,
                        actual_model=actual_model,
                        mode_label=mode_label,
                    )

                    if reasoning_content:
                        logger.debug(
                            "💭 [DeepSeekReasoner] 思维链前 300 字符预览:\n%s...",
                            reasoning_content[:300],
                        )
                    if content:
                        logger.debug(
                            "📄 [DeepSeekReasoner] 输出正文前 300 字符预览:\n%s...",
                            content[:300],
                        )

                    final_text = content if content.strip() else reasoning_content
                    if not final_text.strip():
                        raise RuntimeError("DeepSeek 流式响应未返回任何有效文本内容。")

                    lesson_data = extract_json_from_text(final_text)
                    return lesson_data

                except urllib.error.HTTPError as e:
                    cost_sec = round(time.time() - t0, 2)
                    err_body = e.read().decode("utf-8", errors="ignore")
                    logger.error(
                        "❌ [DeepSeekReasoner] HTTP 状态码错误 (%s, model=%s, 耗时 %ss): code=%d, body=%s",
                        mode_label,
                        actual_model,
                        cost_sec,
                        e.code,
                        err_body[:600],
                    )
                    # 如果服务端提示模型名称不存在，自动尝试回退模型名
                    if e.code in (400, 404, 422) and ("model" in err_body.lower() or "not exist" in err_body.lower() or "invalid" in err_body.lower()):
                        logger.warning(
                            "⚠️ [DeepSeekReasoner] 服务端提示模型 '%s' 不可用 (%s)，正在自动切换备用模型名重试...",
                            actual_model,
                            err_body.strip()[:120],
                        )
                        model_not_exist = True
                        last_err = RuntimeError(f"DeepSeek API 模型报错 ({e.code}): {err_body}")
                        break

                    raise RuntimeError(f"DeepSeek API 请求失败 (状态码 {e.code}): {err_body}") from e

                except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as e:
                    cost_sec = round(time.time() - t0, 2)
                    last_err = e
                    reason = getattr(e, "reason", str(e))
                    logger.warning(
                        "⚠️ [DeepSeekReasoner] 尝试 #%d/%d (%s) 网络连接/超时异常 (耗时 %ss): %s",
                        attempt_idx,
                        len(modes_to_try),
                        mode_label,
                        cost_sec,
                        reason,
                    )
                    if attempt_idx < len(modes_to_try):
                        logger.info("🔄 [DeepSeekReasoner] 立即切换至备用网络通道重试...")
                        continue
                    raise RuntimeError(f"无法连接到 DeepSeek 服务 ({req_url}, 耗时 {cost_sec}s): {reason}") from e

            if model_not_exist:
                continue

        raise RuntimeError(f"DeepSeek 调用失败: {last_err}")
