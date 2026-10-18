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


def agy_rpc(server_info: dict, method: str, payload: dict, timeout: int = 180) -> dict:
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
      "solutionMarkdown": "### 第 (1) 问：...\\n\\n* **【解题思路】**：...\\n\\n#### 【中考规范书写过程】\\n1. ...（支持标准 LaTeX 公式如 $\\\\triangle AOB \\\\cong \\\\triangle CFA$）"
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
   - 严禁使用“极易证得”、“显然”、“易知”等跳步词汇！证全等或相似必须明确列出 3 个条件。
5. **隐藏角度度数标签 & 反角防御**：
   - GeoGebra 的 `Angle(P1, Vertex, P2)` 默认按逆时针方向计算角度！画直角或内角时，务必按逆时针方向排列三个点，使角度显示在 0°~180° 之间。
   - 凡是创建 `ang = Angle(...)`，必须紧接着调用 `ShowLabel(ang, false)`，只保留直角方框或圆弧符号，严禁显示角度度数文字以免重叠！
6. 用户补充要求：{extra_note or "无，请完整覆盖题目所有小问，1:1还原原图朝向，凡有辅助线必须先讲清楚是怎么想到的"}
"""


def extract_json_from_text(text: str) -> dict:
    """从模型返回的文本中提取合法的 JSON 对象"""
    text = text.strip()
    # 去掉 markdown 代码块包裹
    fence_match = re.search(r"```(?:json|javascript|js)?\s*(\{[\s\S]*\})\s*```", text)
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        # 寻找第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

    # 若带有 window.LESSON_DATA = 前缀则剥离
    text = re.sub(r"^window\.LESSON_DATA\s*=\s*", "", text).rstrip(";").strip()
    # 防止模型在 JSON 中将 \triangle, \text, \because, \frac, \right, \neq 等写成单斜杠被 json.loads 当作控制字符
    text = re.sub(
        r"(?<!\\)\\(triangle|text|times|theta|therefore|tau|because|begin|beta|bar|frac|forall|right|rho|neq|nu|nabla)",
        r"\\\\\1",
        text,
    )
    return json.loads(text)


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

        # 2. 发送图片 + 强约束 Prompt，阻塞等待模型推理完成
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
                "blocking": True,
                "cascadeConfig": {
                    "plannerConfig": {
                        "planModel": plan_model,
                    }
                },
            },
            timeout=240,
        )

        # 3. 读取模型响应
        steps_res = agy_rpc(server_info, "GetCascadeTrajectorySteps", {"cascadeId": cascade_id})
        model_reply = ""
        for st in reversed(steps_res.get("steps", [])):
            if st.get("type") == "CORTEX_STEP_TYPE_PLANNER_RESPONSE":
                resp_text = st.get("plannerResponse", {}).get("response", "")
                if resp_text.strip():
                    model_reply = resp_text
                    break

        if not model_reply:
            raise RuntimeError("模型未返回有效内容，请重试。")

        lesson_data = extract_json_from_text(model_reply)

        # 4. 覆写到工作区的 lesson.js 中持久化
        js_content = "window.LESSON_DATA = " + json.dumps(lesson_data, ensure_ascii=False, indent=2) + ";\n"
        LESSON_JS_PATH.write_text(js_content, encoding="utf-8")

        return {
            "lessonData": lesson_data,
            "model": model_slug,
            "user": server_info["user"],
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
