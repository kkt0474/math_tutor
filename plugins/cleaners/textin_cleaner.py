#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TextIn 去笔记与试卷手写擦除插件 (plugins/cleaners/textin_cleaner.py)
================================================================
通过合合信息 TextIn REST API 进行试卷去手写/涂鸦擦除。
特性：
1. 若未配置 x-ti-app-id 或 x-ti-secret-code，在程序启动阶段即报错提示；
2. 默认采用无代理直连模式访问国内 api.textin.com（规避海外梯子/VPN 劫持导致的 60 秒超时或证书错误），
   并在网络异常时自动尝试切换代理模式重试；
3. 全流程 DEBUG 级别日志记录（请求头脱敏、包体字节数、耗时、响应码、x-request-id 等）。
"""

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Dict
from config import get_logger, mask_secret
from plugins.base import BaseCleaner
from utils import build_http_opener, create_ssl_context, optimize_image_bytes

logger = get_logger()


class TextInCleaner(BaseCleaner):
    """
    TextIn 去手写笔迹插件实现。
    使用官方 REST API:
    https://api.textin.com/ai/service/v1/handwritten_erase
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.app_id = (
            os.environ.get("TEXTIN_APP_ID", "").strip()
            or config.get("app_id", "").strip()
        )
        self.secret_code = (
            os.environ.get("TEXTIN_SECRET_CODE", "").strip()
            or config.get("secret_code", "").strip()
        )
        self.api_url = config.get(
            "api_url",
            "https://api.textin.com/ai/service/v1/handwritten_erase",
        ).strip()
        self.timeout = config.get("timeout", 60)
        # 国内 API 默认直连不走系统代理，防止被 VPN/Clash 拦截超时
        self.use_proxy = bool(config.get("use_proxy", False))

    def validate_credentials(self) -> None:
        """
        校验 TextIn 凭据是否配置。
        """
        if not self.app_id:
            self.app_id = os.environ.get("TEXTIN_APP_ID", "").strip()
        if not self.secret_code:
            self.secret_code = os.environ.get("TEXTIN_SECRET_CODE", "").strip()

        logger.debug(
            "[TextInCleaner] 校验凭证: app_id=%s, secret_code=%s, api_url=%s, timeout=%ds, use_proxy=%s",
            mask_secret(self.app_id),
            mask_secret(self.secret_code),
            self.api_url,
            self.timeout,
            self.use_proxy,
        )

        if not self.app_id or not self.secret_code:
            raise ValueError(
                "【TextIn 凭据未配置】未检测到有效的 TextIn 凭证！\n"
                "👉 请打开根目录下的 .env 文件，填写 TEXTIN_APP_ID 与 TEXTIN_SECRET_CODE。\n"
                "（请直接在根目录下的 .env 文件中填入对应的凭据，填好后重新启动服务）"
            )

    def clean_image(self, image_bytes: bytes, mime_type: str = "image/png") -> bytes:
        """
        调用 TextIn REST API 上传图片二进制并获取抹除笔迹后的纯净底图。
        内置超大图片自动瘦身（防 8~10MB 大图触发 SSL write timeout）、直连/代理双模容错重试与详细 DEBUG 日志。
        """
        self.validate_credentials()

        # 上传前对超过 1.2MB 的超大图片自动瘦身为高清 JPEG（避免 9MB 原图导致 TextIn 网关拒绝或 SSL write timeout）
        image_bytes, mime_type = optimize_image_bytes(
            image_bytes,
            mime_type=mime_type,
            max_bytes=1_200_000,
            max_dim=1800,
            quality=82,
        )

        sys_proxies = urllib.request.getproxies()
        logger.debug(
            "➡️ [TextInCleaner] 准备发起去手写请求 | url=%s | input_size=%d bytes | mime=%s | timeout=%ds | configured_use_proxy=%s | system_proxies=%s",
            self.api_url,
            len(image_bytes),
            mime_type,
            self.timeout,
            self.use_proxy,
            sys_proxies,
        )

        ssl_ctx = create_ssl_context()
        # 优先使用配置的连接模式（默认 False 直连），若遇网络连通超时则自动尝试备用模式
        modes_to_try = [self.use_proxy]
        if sys_proxies and not self.use_proxy:
            modes_to_try.append(True)
        elif not sys_proxies and self.use_proxy:
            modes_to_try.append(False)

        last_err: Exception | None = None

        for attempt_idx, proxy_mode in enumerate(modes_to_try, start=1):
            mode_label = "系统代理模式" if proxy_mode else "无代理直连模式(Direct)"
            opener = build_http_opener(proxy_mode, ssl_ctx)

            req = urllib.request.Request(
                self.api_url,
                data=image_bytes,
                headers={
                    "x-ti-app-id": self.app_id,
                    "x-ti-secret-code": self.secret_code,
                    "Content-Type": "application/octet-stream",
                    "User-Agent": "MathTutorWorkspace/2.0",
                },
                method="POST",
            )

            t0 = time.time()
            logger.debug(
                "🚀 [TextInCleaner] 第 %d/%d 次尝试 (%s) -> POST %s ...",
                attempt_idx,
                len(modes_to_try),
                mode_label,
                self.api_url,
            )

            try:
                with opener.open(req, timeout=self.timeout) as resp:
                    cost_sec = round(time.time() - t0, 2)
                    status_code = resp.status
                    content_type = resp.headers.get("Content-Type", "")
                    raw_bytes = resp.read()

                    logger.debug(
                        "⬅️ [TextInCleaner] 收到 HTTP 响应 | status=%s | 耗时=%ss | Content-Type=%s | resp_size=%d bytes | headers=%s",
                        status_code,
                        cost_sec,
                        content_type,
                        len(raw_bytes),
                        dict(resp.headers),
                    )

                    # 如果直接返回了图片二进制流
                    if "image" in content_type.lower():
                        logger.debug("✅ [TextInCleaner] 直接返回图片二进制流 (%d bytes)", len(raw_bytes))
                        return raw_bytes

                    # 解析 JSON 响应
                    raw_resp = raw_bytes.decode("utf-8", errors="replace")
                    data = json.loads(raw_resp)
                    code = data.get("code")
                    msg = data.get("message", "")
                    req_id = data.get("x_request_id", "")

                    logger.debug(
                        "📦 [TextInCleaner] JSON 响应解析 | code=%s | message=%s | x_request_id=%s | result_type=%s",
                        code,
                        msg,
                        req_id,
                        type(data.get("result")).__name__,
                    )

                    if code == 200:
                        result_obj = data.get("result", {})
                        if isinstance(result_obj, dict) and "image" in result_obj:
                            clean_bytes = base64.b64decode(result_obj["image"])
                            logger.debug(
                                "✅ [TextInCleaner] 成功解码 result.image | 原始干净底图大小=%d bytes",
                                len(clean_bytes),
                            )
                            clean_bytes, _ = optimize_image_bytes(clean_bytes, "image/png", max_bytes=1_200_000, max_dim=1800, quality=85)
                            return clean_bytes
                        elif isinstance(result_obj, str) and result_obj:
                            clean_bytes = base64.b64decode(result_obj)
                            logger.debug(
                                "✅ [TextInCleaner] 成功解码字符串 result | 原始干净底图大小=%d bytes",
                                len(clean_bytes),
                            )
                            clean_bytes, _ = optimize_image_bytes(clean_bytes, "image/png", max_bytes=1_200_000, max_dim=1800, quality=85)
                            return clean_bytes
                        else:
                            logger.error("❌ [TextInCleaner] 返回 code=200 但未找到有效图像字段: %s", raw_resp[:300])
                            raise RuntimeError(f"TextIn 返回未包含有效的图像数据: {raw_resp[:200]}")
                    else:
                        logger.error(
                            "❌ [TextInCleaner] 业务报错 | code=%s | message=%s | x_request_id=%s | raw=%s",
                            code,
                            msg,
                            req_id,
                            raw_resp[:400],
                        )
                        raise RuntimeError(f"TextIn API 调用失败 [code={code}]: {msg} (req_id={req_id})")

            except urllib.error.HTTPError as e:
                cost_sec = round(time.time() - t0, 2)
                err_body = e.read().decode("utf-8", errors="ignore")
                logger.error(
                    "❌ [TextInCleaner] HTTP 状态码错误 (%s, 耗时 %ss): code=%d, body=%s",
                    mode_label,
                    cost_sec,
                    e.code,
                    err_body[:500],
                    exc_info=True,
                )
                raise RuntimeError(f"TextIn HTTP 请求失败 (状态码 {e.code}): {err_body}") from e

            except (urllib.error.URLError, TimeoutError, OSError) as e:
                cost_sec = round(time.time() - t0, 2)
                last_err = e
                reason = getattr(e, "reason", str(e))
                logger.warning(
                    "⚠️ [TextInCleaner] 第 %d/%d 次尝试 (%s) 网络连接/超时异常 (耗时 %ss): %s",
                    attempt_idx,
                    len(modes_to_try),
                    mode_label,
                    cost_sec,
                    reason,
                    exc_info=True,
                )
                if attempt_idx < len(modes_to_try):
                    logger.info("🔄 [TextInCleaner] 正在自动切换网络代理模式进行重试...")
                    continue
                raise RuntimeError(f"无法连接到 TextIn 服务 ({self.api_url}, 耗时 {cost_sec}s): {reason}") from e

        raise RuntimeError(f"TextIn 调用失败: {last_err}")
