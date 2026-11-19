#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - 通用工具函数模块 (utils.py)
=============================================
功能说明：
1. 自动探测本机正在运行的 Antigravity 客户端及其 RPC 端口和 CSRF Token；
2. 封装本机 127.0.0.1 直连 RPC 通道 (agy_rpc)，强制绕过系统代理，附带 DEBUG 级全链路日志；
3. 获取本机局域网物理真实 IP（智能过滤 127.0.0.1 及 198.18.x.x 代理虚拟网卡）；
4. 实现面向大模型长输出的高鲁棒性 JSON 提取与 json-repair 状态机自愈引擎（extract_json_from_text）；
5. 智能无损压缩超大题目图片（optimize_image_bytes，基于 macOS 原生 sips 引擎，彻底杜绝上传超时）；
6. 统一底层 HTTPS/直连/代理 Opener 与 SSLContext 构建工厂（create_ssl_context, build_http_opener）。
"""

import json
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from json_repair import repair_json
from config import UPLOADS_DIR, get_logger, mask_secret

logger = get_logger()

# 专用于本机 127.0.0.1 RPC 的无代理直连 Opener（彻底规避 macOS 系统代理劫持 127.0.0.1 及逆向 DNS 阻塞）
_LOCAL_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def create_ssl_context() -> ssl.SSLContext:
    """
    创建 SSL 上下文：防范 macOS Python 证书未初始化或代理证书验证失败。
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def build_http_opener(
    use_proxy: bool = False,
    ssl_ctx: ssl.SSLContext | None = None,
) -> urllib.request.OpenerDirector:
    """
    构建统一 HTTP/HTTPS Opener：
    - use_proxy=False 时显式传入 ProxyHandler({}) 强制直连，彻底规避本地代理劫持与超时；
    - use_proxy=True 时使用系统代理配置。
    """
    if ssl_ctx is None:
        ssl_ctx = create_ssl_context()
    https_handler = urllib.request.HTTPSHandler(context=ssl_ctx)
    if not use_proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), https_handler)
    return urllib.request.build_opener(https_handler)


def get_lan_ip() -> str:
    """
    获取本机在当前局域网内的真实物理 IP 地址。
    """
    try:
        out = subprocess.check_output(["ifconfig"], text=True, stderr=subprocess.DEVNULL)
        for m in re.finditer(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out):
            ip = m.group(1)
            if ip.startswith("192.168.") or ip.startswith("10.") or re.match(r"^172\.(1[6-9]|2\d|3[0-1])\.", ip):
                return ip
    except Exception as e:
        logger.debug("获取局域网 IP 异常 (使用 127.0.0.1 兜底): %s", e)
    return "127.0.0.1"


def optimize_image_bytes(
    image_bytes: bytes,
    mime_type: str = "image/png",
    max_bytes: int = 1_200_000,
    max_dim: int = 1800,
    quality: int = 82,
) -> tuple[bytes, str]:
    """
    对超大题目图片（如手机拍照或高分屏无损 PNG 截图动辄 8~10MB）进行智能无损视觉压缩：
    - 当图片字节数 <= max_bytes (默认 1.2MB) 时直接原样返回；
    - 当图片字节数 > max_bytes 时，调用 macOS 原生 sips 缩放至最大边长 max_dim 并转为高清晰度 JPEG，
      将 9MB 的大图在 0.2 秒内压缩至 ~500KB，彻底避免 TextIn 与大模型上传时发生 SSL write timeout！
    """
    orig_size = len(image_bytes)
    if orig_size <= max_bytes:
        logger.debug(
            "🖼️ [optimize_image] 图片体积 (%d bytes) <= 阈值 (%d bytes)，保持原图传输",
            orig_size,
            max_bytes,
        )
        return image_bytes, mime_type

    t0 = time.time()
    ts_ns = time.time_ns()
    in_path = UPLOADS_DIR / f"_tmp_in_{ts_ns}.img"
    out_path = UPLOADS_DIR / f"_tmp_out_{ts_ns}.jpg"

    try:
        in_path.write_bytes(image_bytes)
        cmd = [
            "sips",
            "-s", "format", "jpeg",
            "-s", "formatOptions", str(quality),
            "-Z", str(max_dim),
            str(in_path),
            "--out", str(out_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if out_path.exists():
            comp_bytes = out_path.read_bytes()
            cost_ms = int((time.time() - t0) * 1000)
            ratio = round((1 - len(comp_bytes) / orig_size) * 100, 1)
            logger.info(
                "⚡ [optimize_image] 超大图片已自动瘦身: %d bytes (%.2f MB) -> %d bytes (%.2f KB) | 缩减 %s%% | 耗时 %dms",
                orig_size,
                orig_size / (1024 * 1024),
                len(comp_bytes),
                len(comp_bytes) / 1024,
                ratio,
                cost_ms,
            )
            return comp_bytes, "image/jpeg"
    except Exception as e:
        logger.warning("⚠️ [optimize_image] sips 压缩未生效，回退使用原图: %s", e)
    finally:
        for p in (in_path, out_path):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    return image_bytes, mime_type


def agy_rpc(server_info: dict, method: str, payload: dict, timeout: int = 600) -> dict:
    """
    向本地 Antigravity LanguageServerService 发起直连 RPC 请求（强制绕过系统代理）。
    """
    url = f"http://127.0.0.1:{server_info['port']}/exa.language_server_pb.LanguageServerService/{method}"
    body_bytes = json.dumps(payload).encode("utf-8")

    # 避免在日志中打印完整 base64 图片内容
    payload_summary = {}
    for k, v in payload.items():
        if k == "media" and isinstance(v, list):
            payload_summary[k] = f"<media list len={len(v)}>"
        elif k == "items" and isinstance(v, list):
            total_txt = sum(len(x.get("text", "")) for x in v if isinstance(x, dict))
            payload_summary[k] = f"<items len={len(v)}, text_chars={total_txt}>"
        else:
            payload_summary[k] = v

    logger.debug(
        "➡️ [agy_rpc] 请求 %s | url=%s | payload=%s | body_size=%d bytes | timeout=%ds",
        method,
        url,
        payload_summary,
        len(body_bytes),
        timeout,
    )

    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "x-codeium-csrf-token": server_info["csrf_token"],
        },
        method="POST",
    )

    t0 = time.time()
    try:
        with _LOCAL_DIRECT_OPENER.open(req, timeout=timeout) as resp:
            raw_resp = resp.read().decode("utf-8")
            cost_ms = int((time.time() - t0) * 1000)
            res_dict = json.loads(raw_resp)
            logger.debug(
                "⬅️ [agy_rpc] 响应 %s | status=%s | 耗时=%dms | resp_size=%d bytes | keys=%s",
                method,
                resp.status,
                cost_ms,
                len(raw_resp),
                list(res_dict.keys()),
            )
            return res_dict
    except urllib.error.HTTPError as e:
        cost_ms = int((time.time() - t0) * 1000)
        err_body = e.read().decode("utf-8", errors="ignore")
        logger.error(
            "❌ [agy_rpc] HTTP 错误 %s | status=%d | 耗时=%dms | body=%s",
            method,
            e.code,
            cost_ms,
            err_body[:500],
        )
        raise
    except Exception as e:
        cost_ms = int((time.time() - t0) * 1000)
        logger.error(
            "❌ [agy_rpc] 调用异常 %s | url=%s | 耗时=%dms | err=%s",
            method,
            url,
            cost_ms,
            e,
            exc_info=True,
        )
        raise


def discover_local_antigravity_server() -> dict | None:
    """
    自动探测本机正在运行的 Antigravity language_server 进程，提取其本地监听端口与 CSRF Token。
    """
    try:
        ps_out = subprocess.check_output(["ps", "aux"], text=True)
    except Exception as e:
        logger.error("执行 ps aux 探测 Antigravity 进程失败: %s", e)
        return None

    candidates: list[tuple[int, str, str]] = []
    for line in ps_out.splitlines():
        if "language_server" not in line or "--csrf_token" not in line:
            continue
        m_token = re.search(r"--csrf_token[=\s]+([0-9a-fA-F\-]+)", line)
        if not m_token:
            continue
        csrf_token = m_token.group(1)
        parts = line.split()
        if len(parts) < 2 or not parts[1].isdigit():
            continue
        pid = parts[1]
        priority = 0
        if "math_tutor_workspace" in line or "math-tutor-workspace" in line:
            priority = 2
        elif "--standalone" in line:
            priority = 3
        candidates.append((priority, pid, csrf_token))

    candidates.sort(key=lambda x: x[0], reverse=True)
    logger.debug("探测到 %d 个候选 Antigravity language_server 进程: %s", len(candidates), [(p, pid) for p, pid, _ in candidates])

    for priority, pid, csrf_token in candidates:
        try:
            lsof_out = subprocess.check_output(
                ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            ports = re.findall(r"127\.0\.0\.1:(\d+)\s+\(LISTEN\)", lsof_out)
            logger.debug("进程 PID=%s (priority=%d) 监听端口列表: %s", pid, priority, ports)
            for port in ports:
                url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    headers={
                        "Content-Type": "application/json",
                        "x-codeium-csrf-token": csrf_token,
                    },
                    method="POST",
                )
                try:
                    with _LOCAL_DIRECT_OPENER.open(req, timeout=2) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if "userStatus" in data:
                            user_name = data["userStatus"].get("name", "Pro User")
                            logger.debug("✅ 成功验证 Antigravity RPC 服务: PID=%s, Port=%s, User=%s", pid, port, user_name)
                            return {
                                "port": int(port),
                                "csrf_token": csrf_token,
                                "pid": int(pid),
                                "user": user_name,
                            }
                except Exception as ep:
                    logger.debug("端口 %s (PID=%s) GetUserStatus 探测未通过: %s", port, pid, ep)
                    continue
        except Exception as e:
            logger.debug("扫描 PID=%s 端口异常: %s", pid, e)
            continue

    logger.warning("⚠️ 未能找到任何可用的本地 Antigravity RPC 监听端口")
    return None


def _protect_latex_backslashes(s: str) -> str:
    """
    保护未转义的 LaTeX 单反斜杠指令（如 \\triangle, \\frac, \\therefore, \\angle），
    防止 JSON 解析器或状态机将 \\t/\\f/\\r/\\b 误吞为控制字符。
    """
    s = re.sub(
        r'(?<!\\)\\(triangle|theta|text|times|tan|therefore|frac|forall|right|rho|because|begin|bar|beta|boxed)',
        r'\\\\\1',
        s,
    )
    return re.sub(r'(?<!\\)\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', s)


def _slice_json_root(s: str) -> str:
    """
    精准截取最外层 JSON 对象区间：
    - 若最外层 `{` 存在对应的平衡闭合 `}`，截取到该闭合位置（剔除尾部多余文本）；
    - 若最外层 `{` 尚未闭合（发生输出截断），保留到文本末尾完整内容交由 json-repair 状态机补全，
      避免误用 rfind('}') 切丢末尾残缺的坐标与步骤数据。
    """
    start = s.find("{")
    if start == -1:
        return s

    depth = 0
    in_str = False
    escape = False
    for idx in range(start, len(s)):
        ch = s[idx]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : idx + 1]
    return s[start:]


def extract_json_from_text(text: str) -> dict:
    """
    高鲁棒性微课 JSON 提取与状态机自愈管线：
    - 阶段 1：极速通道（标准宽松 json.loads）；
    - 阶段 2：LaTeX 反斜杠保护 + json-repair 有限状态机自愈（自动兼容缺失/多余逗号、
      误写分号/句号、未转义引号、Markdown 杂质以及截断未闭合括号）。
    """
    parse_error: Exception | None = None

    try:
        raw_log = UPLOADS_DIR / "last_raw_model_reply.txt"
        raw_log.write_text(text, encoding="utf-8")
        logger.debug("💾 原始模型输出已备份至: %s (总长度: %d 字符)", raw_log, len(text))
    except Exception as e:
        logger.warning("保存 last_raw_model_reply.txt 失败: %s", e)

    text_clean = text.replace("===END_OF_LESSON===", "").strip()

    fence_match = re.search(r"```(?:json|javascript|js)?\s*(\{[\s\S]*?)(?:\s*```|$)", text_clean)
    if fence_match:
        text_clean = fence_match.group(1).strip()
        logger.debug("已从 Markdown 代码块中提取 JSON 主体 (长度: %d 字符)", len(text_clean))
    else:
        text_clean = _slice_json_root(text_clean)
        logger.debug("已精准定位 JSON 主体 (长度=%d)", len(text_clean))

    text_clean = re.sub(r"^window\.LESSON_DATA\s*=\s*", "", text_clean).rstrip(";").strip()

    # 阶段 1：标准解析快速通道
    try:
        data = json.loads(text_clean, strict=False)
        if isinstance(data, dict):
            logger.debug("✅ [JSON提取-阶段1] 标准 json.loads 直接解析成功！包含小问数: %d", len(data.get("questions", [])))
            return data
    except Exception as err:
        parse_error = err
        logger.warning("⚠️ [JSON提取-阶段1] 基础解析未通过 (%s)，启动 json-repair 状态机自愈...", err)

    # 阶段 2：LaTeX 反斜杠保护 + json-repair 状态机通用自愈
    try:
        protected = _protect_latex_backslashes(text_clean)
        repaired = repair_json(protected, return_objects=True)
        if isinstance(repaired, dict) and "questions" in repaired:
            q_count = len(repaired.get("questions", []))
            s_count = sum(len(q.get("steps", [])) for q in repaired.get("questions", []) if isinstance(q, dict))
            logger.info("✅ [JSON提取-阶段2] json-repair 状态机自愈成功！解析 %d 个小问共 %d 个步骤", q_count, s_count)
            return repaired
        parse_error = ValueError(f"json-repair 返回结构缺少 questions 字段 (type={type(repaired).__name__})")
    except Exception as err:
        parse_error = err
        logger.error("❌ [JSON提取-阶段2] json-repair 自愈失败: %s", err)

    err_detail = str(parse_error) if parse_error is not None else "未知 JSON 解析错误"
    logger.error("❌ JSON 提取失败，原始报错：%s\n文本前 500 字符预览:\n%s", err_detail, text_clean[:500])
    raise ValueError(f"微课 JSON 解析失败: {err_detail}") from parse_error
