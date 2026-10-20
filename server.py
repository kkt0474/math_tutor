#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 Web App 全自动后端服务
=======================================
工作原理：
直接对接你本机正在运行的 Antigravity Local Language Server RPC 通道，
100% 复用你的 Antigravity Pro 会员与高阶模型（Gemini 3.8 Flash / Gemini 4 Argon / Claude Sonnet 5.5），
无需配置任何外部 API Key，无需任何人工复制粘贴介入！

严格工作区沙箱隔离：
所有文件读写与会话均锁定在 WORKSPACE_DIR (/Users/dean/Documents/math-tutor-workspace) 内，
并在每次生成完毕后自动清理临时会话，绝不污染其他工作区或聊天列表。

运行方式：
    python3 server.py
然后在浏览器打开：
    http://127.0.0.1:8765/viewer.html
"""

import os
import re
import json
import time
import shutil
import base64
import subprocess
import urllib.request
from pathlib import Path
from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler

# 严格锁定当前工作区目录，防止污染任何外部目录
WORKSPACE_DIR = Path("/Users/dean/Documents/math-tutor-workspace").resolve()
UPLOADS_DIR = WORKSPACE_DIR / "uploads"
AGENTS_MD_PATH = WORKSPACE_DIR / ".antigravity" / "AGENTS.md"
LESSON_JS_PATH = WORKSPACE_DIR / "lesson.js"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 模型友好名称与底层枚举映射
MODEL_MAP = {
    "gemini-3.8-flash-medium": "MODEL_PLACEHOLDER_M319",
    "gemini-3.8-flash-high": "MODEL_PLACEHOLDER_M318",
    "gemini-3.8-flash-low": "MODEL_PLACEHOLDER_M320",
    "gemini-4-argon-medium": "MODEL_PLACEHOLDER_M418",
    "gemini-4-argon-high": "MODEL_PLACEHOLDER_M417",
    "claude-sonnet-5-5-medium": "MODEL_PLACEHOLDER_M404",
}


def discover_local_antigravity_server() -> dict | None:
    """
    自动探测本机正在运行的 Antigravity language_server 进程，
    提取其本地监听端口与 CSRF Token。
    """
    try:
        ps_out = subprocess.check_output(["ps", "aux"], text=True)
    except Exception:
        return None

    candidates = []
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
        # 优先选择 standalone (Antigravity 2.0) 或当前 math_tutor_workspace 的进程
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
            # 逐个端口测试 GetUserStatus
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


def agy_rpc(server_info: dict, method: str, payload: dict, timeout: int = 600) -> dict:
    """调用本地 Antigravity LanguageServerService RPC 接口"""
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


def build_strict_json_prompt(extra_note: str) -> str:
    """构建让模型直接返回纯 JSON 数据的强约束 Prompt（无需调工具，一次成型）"""
    agents_spec = ""
    if AGENTS_MD_PATH.exists():
        agents_spec = AGENTS_MD_PATH.read_text(encoding="utf-8")

    return f"""你现在是《初中几何交互微课生成器 (基于 GeoGebra 引擎)》。
请仔细识别我上传的几何题目图片，严格遵循以下教学与绘图规范，一次性生成包含题目所有小问的微课 JSON 数据。

【重要指令：请勿调用任何工具（Do NOT call any tools）！直接输出纯 JSON 对象！】

【用户最高优先级补充要求（与下文规范冲突时以此为准，全篇所有字段——含 thoughtAnalysis、explanation、solutionMarkdown——都必须遵守）】：
{extra_note or "无"}

{agents_spec}

【输出 JSON 结构强制要求】：
请直接输出一个合法的 JSON 对象（不要加任何多余的前后缀解释，直接输出 JSON），结构必须严格如下：
{{
  "viewConfig": {{
    "hasAxes": true,
    "bounds": {{ "xmin": -8.5, "xmax": 9.5, "ymin": -7.5, "ymax": 4.5 }}
  }},
  "questions": [
    {{
      "title": "第(1)问：...",
      "thoughtAnalysis": "* **【💡 题眼信号识别（破题开关）】**：明确指出题干哪句原话是关键开关，看到该条件第一反应联想到什么几何定理/模型；\\n* **【🧭 人类解题思维路线】**：按照人类探索思维（要求什么 -> 缺什么 -> 由题眼搭桥连通已知 -> 逻辑闭环）引导用户一步步破局，转化为人类可复用的思维方式，不罗列机械算数细节。",
      "steps": [
        {{
          "name": "步骤短标题（如：构造一线三垂直全等 △BCD ≌ △EMB）",
          "modelName": "本步核心模型或思路（如确实用到一线三垂直/8字全等/倍长中线/截长补短/手拉手等经典模型必须明确写出模型名；若无辅助线常规推导则写方法概述）",
          "explanation": "【💡 辅助线是怎么想到的？】观察图形发现 [现有几何特征/残缺信号，如已有两个直角在一线上形成一线两垂直]，为了 [连接什么已知条件与目标]，因此想到过点 X 作 YY（补全第三个垂直）。\\n因为 [条件1]，所以 [结论1]。\\n因为 [条件2]，所以 [结论2]。\\n结合以上推导，==所以 [本步最终证明或达成的核心结论]==",
          "ggbCommands": [
            "O = (0, 0)",
            "A = (0, 3)",
            "segOA = Segment(O, A)",
            "SetColor(segOA, \\"#38BDF8\\")"
          ]
        }}
      ],
      "solutionMarkdown": "#### 【中考规范书写过程】\\n解：\\n1. ...（纯粹的中考规范书写步骤，支持标准 LaTeX 公式如 $\\\\triangle AOB \\\\cong \\\\triangle CFA$）"
    }}
  ]
}}

【GeoGebra 指令与讲题引导特别铁律】：
1. **视觉方位 1:1 对齐原图（严禁旋转或扭曲原图形状）**：
   - 若原题无坐标轴，建系时必须先观察原图中哪条边是水平或铅直的，各顶点的上下左右相对方位、凸凹性必须与原题图 100% 视觉一致！绝不允许为了计算偷懒把斜线当水平轴导致图形旋转或变形！
2. **第 1 步（steps[0]）必须是纯粹的原题图**：
   - 每个小问的第 1 步（steps[0]）只允许绘制原题已知的顶点、多边形与已知线段（蓝色实线），**严禁在第 1 步画出任何辅助线或辅助点**！从第 2 步开始才用黄色虚线（`SetLineStyle(aux, 2)`, `SetColor(aux, "#FACC15")`）动态生长出辅助线！
3. **【核心】凡作辅助线必须先写“【💡 辅助线是怎么想到的？】” + 精准关联模型**：
   - **严禁直接生硬下达辅助线指令（如一上来就写“过点 E 作 EM ⊥ BC”）**！凡是添加辅助线的步骤，第 1 行必须以 `【💡 辅助线是怎么想到的？】` 开头，引导孩子思考为什么会想到画这条线！
   - **当用到经典模型构造辅助线时必须明确点出套路**：例如图中直线上已出现两个直角（“一线两垂直”）且伴随等腰直角斜边相等时，必须明确点出**【一线三垂直（K字型全等）】**套路，告诉孩子“看到一线两垂直，自然想到补第三个垂直”；同理，遇到8字型（沙漏）全等、倍长中线、截长补短、手拉手、将军饮马等真模型时必须明确写出模型名称并讲清识别信号！
   - **即使某条辅助线不对应特定命名模型**：也必须详细说明思维动机（如“为了把分散的相等线段转化到同一个三角形中 / 为了构造平行线内错角搭桥，所以我们想到……”）。只有在完全无需辅助线的常规顺推步骤中，才不强行套模型名。
4. **分步排版（一行一个“因为…所以…”子步骤） & 核心结论高亮（`==...==`） & 禁止跳步**：
   - 在每个 step 的 `explanation` 中，把有直接关联的“因为 XXXXX，所以我们得到 YYYYY。”写在一行里，下一个子步骤必须用 `\\n` 换行另起一行开始！
   - 在 `explanation` 的最后一行，**必须将该步骤最终要证明或达成的核心结论用双等号 `==...==` 包裹起来**。
   - **`==...==` 内部出现的任何数学符号/角/度数也必须用 `$...$` 包裹**（如 `==所以求得 $\\\\angle ABC + \\\\angle ADC = 240^\\\\circ$==`），严禁在高亮结论中裸写 LaTeX 源码！
   - 严禁使用“极易证得”、“显然”、“易知”等跳步词汇！证全等或相似必须明确列出 3 个条件。
5. **隐藏角度度数标签 & 反角防御 & 斜线垂足高精度**：
   - GeoGebra 的 `Angle(P1, Vertex, P2)` 默认按逆时针方向计算角度！画直角或内角时，务必按逆时针方向排列三个点，使角度显示在 0°~180° 之间。
   - 凡是创建 `ang = Angle(...)`，必须紧接着调用 `ShowLabel(ang, false)`，只保留直角方框或圆弧符号，严禁显示角度度数文字以免重叠！
   - 凡是题干或小问包含垂直条件（如 `CM ⊥ AB 于 M`），必须为每个垂足创建 `Angle` 标记直角！若垂线落在斜线上含无理数坐标，坐标必须保留至少 6 位小数（如 `4.041452`），防止因小数截断导致角度偏离 90° 而无法显示直角方框 `∟`！
6. **已知相等线段与相等角在 Step 1 自动标出（视觉条件显性化）**：
   - 题干或当前小问已知条件明确给出的**相等线段**（如 `DE = EF`、`BC = CD`），在 `steps[0]`（第 1 步）中必须显式创建对应的 `Segment` 并调用 `SetDecoration(seg, 1)` 或 `SetDecoration(seg, 2)` 标出等长刻度线（`|` 或 `||`）！
   - 题干已知条件给出的**相等角或特殊角**（如 `∠BAD = ∠BCD = 60°`），在 `steps[0]` 中必须全部创建 `Angle` 并设置相同颜色（如 `#10B981`），让已知相等条件在原图中一目了然！
7. **严禁角命名同义反复与等号废话（实质性几何转化约束）**：
   - 等式两边必须是具有几何依据的转化，**严禁将同一个角的单字母简写与其三字母全称划等号**（如严禁写 `\\angle B = \\angle ABC`、`\\angle C = \\angle ACB` 这种自我解释废话）！
   - 示范：❌ 禁止写 `==所以求得底角 \\angle B = \\angle ABC = 15^\\circ==`；✅ 必须规范写为 `==所以求得底角 \\angle ABC = 15^\\circ==` 或 `==所以求得底角 \\angle ABC = \\angle ABD = 15^\\circ==`。除题干明确要求外，统一使用三字母角记法。
8. 用户补充要求：{extra_note or "无，请完整覆盖题目所有小问，1:1还原原图朝向，凡有辅助线必须先讲清楚是怎么想到的"}
"""


def extract_json_from_text(text: str) -> dict:
    """
    从模型返回的文本中提取合法的 JSON 对象。
    具备多重自动容错自愈能力：
    1. 自动备份原始文本到 uploads/last_raw_model_reply.txt 便于排查；
    2. 允许 strict=False 容忍字符串内控制字符；
    3. 全方位正则识别修复 LaTeX 单反斜杠公式（\\angle, \\perp, \\cong, \\sim, \\triangle 等）；
    4. 自动移除末尾多余逗号（trailing commas）；
    5. 自动修复 GeoGebra 嵌套引号与中文符号；
    6. 降级使用 ast.literal_eval 救砖恢复。
    """
    # 0. 实时备份原始文本
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

    # 去掉 window.LESSON_DATA 前缀
    text_clean = re.sub(r"^window\.LESSON_DATA\s*=\s*", "", text_clean).rstrip(";").strip()

    # 阶段 1：尝试直接解析（宽松模式）
    try:
        return json.loads(text_clean, strict=False)
    except Exception as e1:
        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 基础 JSON 解析未通过 ({e1})，启动智能自愈管线...")

    # 阶段 2：全方位 LaTeX 单反斜杠自愈
    # 在标准 JSON 中，只有 \" \\ \/ \b \f \n \r \t \uXXXX 是合法的转义序列。
    # 几何模型生成的 LaTeX 公式（如 \angle, \perp, \cong, \triangle, \because 等）如果带有单斜杠必须全部转为 \\
    fixed = re.sub(r'\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', text_clean)
    # 移除数组与对象末尾的非法逗号 (trailing commas)
    fixed = re.sub(r',\s*([\]}])', r'\1', fixed)

    try:
        data = json.loads(fixed, strict=False)
        print(f"[{time.strftime('%H:%M:%S')}] ✅ 自愈成功：阶段 2 (LaTeX 转义与尾部逗号修复) 成功解析 JSON！")
        return data
    except Exception as e2:
        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 阶段 2 未通过 ({e2})，尝试阶段 3 嵌套引号与特殊符号清洗...")

    # 阶段 3：修复 GeoGebra 嵌套引号与字符串内单双引号混乱
    # 例如 SetColor(seg, "#38BDF8") 内部未转义的双引号
    fixed2 = re.sub(r'SetColor\(([^,]+),\s*"([^"]+)"\)', r'SetColor(\1, \\"\2\\")', fixed)
    fixed2 = re.sub(r'SetColor\(([^,]+),\s*""([^"]+)""\)', r'SetColor(\1, \\"\2\\")', fixed2)
    # 移除对象键名缺失引号或中文全角冒号
    fixed2 = fixed2.replace("：", ":")

    try:
        data = json.loads(fixed2, strict=False)
        print(f"[{time.strftime('%H:%M:%S')}] ✅ 自愈成功：阶段 3 (嵌套引号修复) 成功解析 JSON！")
        return data
    except Exception as e3:
        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 阶段 3 未通过 ({e3})，尝试阶段 4 Python AST 容错提取...")

    # 阶段 4：Python AST 解析降级（可容忍大部分 JSON 标点微瑕疵）
    try:
        import ast
        py_repr = fixed2
        py_repr = re.sub(r'\btrue\b', 'True', py_repr)
        py_repr = re.sub(r'\bfalse\b', 'False', py_repr)
        py_repr = re.sub(r'\bnull\b', 'None', py_repr)
        res = ast.literal_eval(py_repr)
        if isinstance(res, dict) and "questions" in res:
            print(f"[{time.strftime('%H:%M:%S')}] ✅ 自愈成功：阶段 4 (AST 结构解析) 成功拯救微课数据！")
            return res
    except Exception:
        pass

    # 若所有救砖机制均无法恢复，抛出详细诊断信息
    print(f"[{time.strftime('%H:%M:%S')}] ❌ 所有自愈机制均告竭，原始报错：{e1}")
    raise e1


def solve_problem_automatically(image_bytes: bytes, mime_type: str, extra_note: str, model_slug: str) -> dict:
    """
    全自动调用本机 Antigravity 服务解析几何题图片并生成 LESSON_DATA
    """
    server_info = discover_local_antigravity_server()
    if not server_info:
        raise RuntimeError("未检测到正在运行的 Antigravity 客户端进程，请确认 Antigravity 已打开。")

    plan_model = MODEL_MAP.get(model_slug, "MODEL_PLACEHOLDER_M319")

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
    cascade_id = start_res["cascadeId"]

    try:
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

        # 3. 轮询读取模型响应（最长等待 900 秒 = 15 分钟，每 2 秒查询一次）
        start_time = time.time()
        max_wait_seconds = 900
        model_reply = ""
        poll_count = 0
        print(f"[{time.strftime('%H:%M:%S')}] 🚀 已发起模型推演请求 (模型: {model_slug})，开始轮询等待结果...", flush=True)
        while time.time() - start_time < max_wait_seconds:
            time.sleep(2)
            poll_count += 1
            if poll_count % 10 == 0:
                print(f"[{time.strftime('%H:%M:%S')}] ⏳ 模型正在深度思考与排版板书... (已耗时 {int(time.time() - start_time)} 秒)", flush=True)

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

            steps = steps_res.get("steps", [])
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
                print(f"[{time.strftime('%H:%M:%S')}] 🎉 模型推演完成！耗时 {int(time.time() - start_time)} 秒，输出 {len(model_reply)} 字符", flush=True)
                break

        if not model_reply:
            raise RuntimeError(f"模型在 {int(time.time() - start_time)} 秒内未完成推演，请重试或切换为 Medium 模式。")

        lesson_data = extract_json_from_text(model_reply)

        # 4. 覆写到工作区的 lesson.js 中持久化
        js_content = "window.LESSON_DATA = " + json.dumps(lesson_data, ensure_ascii=False, indent=2) + ";\n"
        LESSON_JS_PATH.write_text(js_content, encoding="utf-8")

        elapsed_seconds = round(time.time() - start_time, 1)
        return {
            "lessonData": lesson_data,
            "model": model_slug,
            "user": server_info["user"],
            "elapsed": elapsed_seconds,
        }
    finally:
        # 5. 自动清理临时会话，保持用户的 Antigravity 聊天列表干净无污染
        try:
            agy_rpc(server_info, "DeleteCascadeTrajectory", {"cascadeId": cascade_id}, timeout=10)
        except Exception:
            pass


class MathTutorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WORKSPACE_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.path = "/viewer.html"
        if self.path.startswith("/api/status"):
            srv = discover_local_antigravity_server()
            mtime = LESSON_JS_PATH.stat().st_mtime if LESSON_JS_PATH.exists() else 0
            self._send_json({
                "ok": True,
                "workspace": str(WORKSPACE_DIR),
                "connected": bool(srv),
                "user": srv["user"] if srv else None,
                "lessonMtime": mtime,
            })
            return
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/solve":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))

            image_data = body.get("imageBase64", "")
            extra_note = body.get("note", "")
            model_slug = body.get("model", "gemini-3.8-flash-medium")

            if not image_data:
                self._send_json({"ok": False, "error": "请先上传或粘贴题目图片"}, status=400)
                return

            header, _, b64 = image_data.partition(",")
            mime_type = "image/png"
            ext = "png"
            if "jpeg" in header or "jpg" in header:
                mime_type = "image/jpeg"
                ext = "jpg"
            elif "webp" in header:
                mime_type = "image/webp"
                ext = "webp"

            raw_bytes = base64.b64decode(b64 if b64 else image_data)

            # 备份上传图片到工作区 uploads/
            filename = f"problem_{int(time.time())}.{ext}"
            saved_path = (UPLOADS_DIR / filename).resolve()
            if not str(saved_path).startswith(str(WORKSPACE_DIR)):
                self._send_json({"ok": False, "error": "非法路径访问已被沙箱拦截"}, status=403)
                return
            saved_path.write_bytes(raw_bytes)

            try:
                result = solve_problem_automatically(raw_bytes, mime_type, extra_note, model_slug)
                self._send_json({
                    "ok": True,
                    "mode": "auto",
                    "model": result["model"],
                    "user": result["user"],
                    "elapsed": result.get("elapsed", 0),
                    "lessonData": result["lessonData"],
                })
            except Exception as e:
                self._send_json({
                    "ok": False,
                    "error": str(e),
                }, status=500)
            return

        self._send_json({"ok": False, "error": "Not Found"}, status=404)

    def _send_json(self, data: dict, status: int = 200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def get_lan_ip() -> str:
    """获取本机局域网真实 IP（过滤 127.0.0.1 与代理虚拟网卡 198.18.x.x）"""
    try:
        out = subprocess.check_output(["ifconfig"], text=True, stderr=subprocess.DEVNULL)
        for m in re.finditer(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out):
            ip = m.group(1)
            if ip.startswith("192.168.") or ip.startswith("10.") or re.match(r"^172\.(1[6-9]|2\d|3[0-1])\.", ip):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


if __name__ == "__main__":
    os.chdir(WORKSPACE_DIR)
    port = 8765
    lan_ip = get_lan_ip()
    srv_info = discover_local_antigravity_server()
    print("============================================================")
    print(" 🚀 数学几何微课全自动 Web App 服务已启动（支持局域网共享）！")
    print(f" 🔒 严格沙箱工作区: {WORKSPACE_DIR}")
    if srv_info:
        print(f" ✅ 已自动连接 Antigravity Pro 引擎 (用户: {srv_info['user']}, 端口: {srv_info['port']})")
    else:
        print(" ⚠️ 未检测到 Antigravity 客户端，请保持 Antigravity 开启")
    print(f" 💻 本机访问地址:   http://127.0.0.1:{port}/viewer.html")
    print(f" 📱 局域网访问地址: http://{lan_ip}:{port}/viewer.html  (或直接 http://{lan_ip}:{port})")
    print("============================================================")
    server = ThreadingHTTPServer(("0.0.0.0", port), MathTutorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
