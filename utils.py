#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - 通用工具函数模块 (utils.py)
=============================================
功能说明：
1. 自动探测本机正在运行的 Antigravity 客户端及其 RPC 端口和 CSRF Token；
2. 获取本机局域网物理真实 IP（智能过滤 127.0.0.1 及 198.18.x.x 代理虚拟网卡）；
3. 实现面向大模型长输出的高鲁棒性 JSON 提取与四级自愈管线（extract_json_from_text）。
"""

import ast
import json
import re
import subprocess
import time
import urllib.request
from config import UPLOADS_DIR


def get_lan_ip() -> str:
    """
    获取本机在当前局域网内的真实物理 IP 地址。

    通过执行 `ifconfig` 扫描网络接口，自动过滤回环地址 (127.0.0.1) 以及常见代理/VPN 虚拟网卡 (198.18.x.x)，
    优先提取常见的私有 IP 网段 (192.168.x.x, 10.x.x.x, 172.16-31.x.x)。

    Returns:
        str: 本机局域网真实 IP；若探测失败或无可用物理网卡则退回 '127.0.0.1'。
    """
    try:
        out = subprocess.check_output(["ifconfig"], text=True, stderr=subprocess.DEVNULL)
        for m in re.finditer(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out):
            ip = m.group(1)
            if ip.startswith("192.168.") or ip.startswith("10.") or re.match(r"^172\.(1[6-9]|2\d|3[0-1])\.", ip):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def discover_local_antigravity_server() -> dict | None:
    """
    自动探测本机正在运行的 Antigravity language_server 进程，提取其本地监听端口与 CSRF Token。

    实现逻辑：
    1. 扫描本机 `ps aux` 输出，检索包含 `language_server` 与 `--csrf_token` 的进程；
    2. 优先匹配当前工作区或独立运行模式的进程；
    3. 调用 `lsof` 获取该 PID 正在监听的 TCP 端口；
    4. 逐个端口向 `GetUserStatus` 发起免认证探测请求验证有效性；
    5. 返回包含有效端口、CSRF Token、进程 PID 以及用户名称的字典。

    Returns:
        dict | None: 探测成功返回 `{"port": int, "csrf_token": str, "pid": int, "user": str}`；
                     若未检测到运行中的进程或无响应则返回 None。
    """
    try:
        ps_out = subprocess.check_output(["ps", "aux"], text=True)
    except Exception:
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
        # 优先级权重：standalone (Antigravity 2.0) > 当前工作区进程 > 普通进程
        priority = 0
        if "math_tutor_workspace" in line:
            priority = 2
        elif "--standalone" in line:
            priority = 3
        candidates.append((priority, pid, csrf_token))

    candidates.sort(key=lambda x: x[0], reverse=True)

    for _, pid, csrf_token in candidates:
        try:
            lsof_out = subprocess.check_output(
                ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            ports = re.findall(r"127\.0\.0\.1:(\d+)\s+\(LISTEN\)", lsof_out)
            # 逐个端口测试 GetUserStatus 连通性
            for port in ports:
                url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    headers={
                        "Content-Type": "application/json",
                        "x-codeium-csrf-token": csrf_token,
                    },
                )
                try:
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if "userStatus" in data:
                            return {
                                "port": int(port),
                                "csrf_token": csrf_token,
                                "pid": int(pid),
                                "user": data["userStatus"].get("name", "Pro User"),
                            }
                except Exception:
                    continue
        except Exception:
            continue
    return None


def extract_json_from_text(text: str) -> dict:
    """
    从模型返回的非受控长文本中精确提取合法的微课 JSON 数据结构。

    针对大模型在输出两万字符以上几何公式和板书时偶发的语法微瑕疵，内置四级容错自愈管线：
    - 阶段 0：自动将原始输出持久化备份到 `uploads/last_raw_model_reply.txt`，便于问题复盘；
    - 阶段 1：去除 Markdown 代码块包裹与前后缀后，尝试标准宽松解析；
    - 阶段 2：标点自愈（修复句号误作逗号、对象误插大括号过早闭合）、单反斜杠转义自愈（加负向后顾防御）、移除多余末尾逗号；
    - 阶段 3：清洗 GeoGebra 嵌套引号与中文全角标点；
    - 阶段 4：降级使用 Python AST (literal_eval) 对类 JSON 结构做容错提取。

    Args:
        text (str): 大模型返回的原始回答文本。

    Returns:
        dict: 提取并解析成功的微课字典对象（包含 `viewConfig` 和 `questions`）。

    Raises:
        ValueError: 当所有自愈阶段均无法恢复出合法 JSON 结构时抛出，附带具体错误成因。
    """
    # 0. 变量赋初始默认值
    parse_error: Exception | None = None

    # 实时备份原始文本
    try:
        raw_log = UPLOADS_DIR / "last_raw_model_reply.txt"
        raw_log.write_text(text, encoding="utf-8")
        print(f"[{time.strftime('%H:%M:%S')}] 💾 原始模型输出已记录到: {raw_log} (长度: {len(text)} 字符)")
    except Exception:
        pass

    text_clean = text.strip()

    # 1. 提取 JSON 代码块或最外层大括号
    fence_match = re.search(r"```(?:json|javascript|js)?\s*(\{[\s\S]*\})\s*```", text_clean)
    if fence_match:
        text_clean = fence_match.group(1).strip()
    else:
        start = text_clean.find("{")
        end = text_clean.rfind("}")
        if start != -1 and end != -1 and end > start:
            text_clean = text_clean[start : end + 1]

    # 去掉 window.LESSON_DATA 前缀与尾部可能存在的分号
    text_clean = re.sub(r"^window\.LESSON_DATA\s*=\s*", "", text_clean).rstrip(";").strip()

    # 阶段 1：尝试直接解析（宽松模式）
    try:
        return json.loads(text_clean, strict=False)
    except Exception as err:
        parse_error = err
        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 基础 JSON 解析未通过 ({err})，启动智能自愈管线...")

    # 阶段 2：全方位 LaTeX 单反斜杠自愈 + 标点自愈
    # 修复句号结尾误写 (如 "..."." 或 "..."。\n)
    fixed = re.sub(r'\"[.。]\s*([\r\n]+\s*\")', r'",\1', text_clean)
    # 修复对象过早闭合误插大括号 (如 },\n "steps": [)
    fixed = re.sub(
        r'\}\s*,\s*([\r\n]+\s*"(?:steps|solutionMarkdown|thoughtAnalysis|name|modelName|explanation|ggbCommands)"\s*:)',
        r',\1',
        fixed,
    )
    # 在标准 JSON 中，只有 \" \\ \/ \b \f \n \r \t \uXXXX 是合法的转义序列。
    # 几何模型生成的 LaTeX 公式如果带有单斜杠必须全部转为 \\（严格加负向后顾 (?<!\\)，防止将已合法的 \\angle 篡改成 \\\angle）
    fixed = re.sub(r'(?<!\\)\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', fixed)
    # 移除数组与对象末尾的非法逗号 (trailing commas)
    fixed = re.sub(r',\s*([\]}])', r'\1', fixed)

    try:
        data = json.loads(fixed, strict=False)
        print(f"[{time.strftime('%H:%M:%S')}] ✅ 自愈成功：阶段 2 (LaTeX 转义、标点与尾部逗号修复) 成功解析 JSON！")
        return data
    except Exception as err:
        parse_error = err
        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 阶段 2 未通过 ({err})，尝试阶段 3 嵌套引号与特殊符号清洗...")

    # 阶段 3：修复 GeoGebra 嵌套引号与字符串内单双引号混乱
    fixed2 = re.sub(r'SetColor\(([^,]+),\s*"([^"]+)"\)', r'SetColor(\1, \\"\2\\")', fixed)
    fixed2 = re.sub(r'SetColor\(([^,]+),\s*""([^"]+)""\)', r'SetColor(\1, \\"\2\\")', fixed2)
    # 移除对象键名缺失引号或中文全角冒号
    fixed2 = fixed2.replace("：", ":")

    try:
        data = json.loads(fixed2, strict=False)
        print(f"[{time.strftime('%H:%M:%S')}] ✅ 自愈成功：阶段 3 (嵌套引号修复) 成功解析 JSON！")
        return data
    except Exception as err:
        parse_error = err
        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 阶段 3 未通过 ({err})，尝试阶段 4 Python AST 容错提取...")

    # 阶段 4：Python AST 解析降级（可容忍大部分 JSON 标点微瑕疵）
    try:
        py_repr = fixed2
        py_repr = re.sub(r'\btrue\b', 'True', py_repr)
        py_repr = re.sub(r'\bfalse\b', 'False', py_repr)
        py_repr = re.sub(r'\bnull\b', 'None', py_repr)
        res = ast.literal_eval(py_repr)
        if isinstance(res, dict) and "questions" in res:
            print(f"[{time.strftime('%H:%M:%S')}] ✅ 自愈成功：阶段 4 (AST 结构解析) 成功拯救微课数据！")
            return res
    except Exception as err:
        parse_error = err

    # 若所有救砖机制均无法恢复，抛出详细诊断信息
    err_detail = str(parse_error) if parse_error is not None else "未知 JSON 解析错误"
    print(f"[{time.strftime('%H:%M:%S')}] ❌ 所有自愈机制均告竭，原始报错：{err_detail}")
    if parse_error is not None:
        raise ValueError(f"微课 JSON 解析失败: {err_detail}") from parse_error
    raise ValueError("微课 JSON 解析失败: 无法从模型回复中提取合法数据结构")
