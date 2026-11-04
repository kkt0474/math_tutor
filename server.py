#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - HTTP 服务端入口模块 (server.py)
==================================================
功能说明：
1. 本地多线程 Web 后端服务主入口（支持局域网内同一 Wi-Fi 多设备访问）；
2. 托管当前工作区静态 Web 资源（viewer.html, lesson.js 等）；
3. 暴露 `/api/status` 接口：供前端实时检测本机 Antigravity 连接状态与课件修改时间；
4. 暴露 `/api/solve` 接口：接收前端上传的题目图片 Base64 与补充讲题要求，
   调用 `solver.solve_problem_automatically` 异步执行全流程几何微课生成；
5. 实施严格的工作区沙箱安全隔离，杜绝跨目录越界读写。

运行方式：
    python3 server.py
然后在浏览器打开：
    http://127.0.0.1:8765/viewer.html (或局域网 IP)
"""

import base64
import json
import os
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from config import (
    DEFAULT_MODEL_SLUG,
    LESSON_JS_PATH,
    SERVER_HOST,
    SERVER_PORT,
    UPLOADS_DIR,
    WORKSPACE_DIR,
)
from solver import solve_problem_automatically
from utils import discover_local_antigravity_server, get_lan_ip


class MathTutorHandler(SimpleHTTPRequestHandler):
    """
    初中几何交互微课 HTTP 请求处理器。

    继承自 SimpleHTTPRequestHandler，支持工作区静态页面托管、CORS 跨域头注入
    以及 `/api/status` 与 `/api/solve` REST API 处理。
    """

    def __init__(self, *args, **kwargs):
        """
        初始化 HTTP 请求处理器并将根目录严格锁定至 WORKSPACE_DIR。
        """
        super().__init__(*args, directory=str(WORKSPACE_DIR), **kwargs)

    def end_headers(self):
        """
        注入跨域支持 (CORS) 与强缓存禁用响应头，确保前端每次获取到最新生成的课件。
        """
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        """
        响应浏览器的 OPTIONS 预检请求。
        """
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        """
        处理 HTTP GET 请求：
        - 根路径 `/` 默认重定向映射至 `/viewer.html`；
        - `/api/status` 返回 Antigravity 本地连接状态与 lesson.js 修改时间戳；
        - 其他路径由父类托管返回工作区静态文件。
        """
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
        """
        处理 HTTP POST 请求：
        - `/api/solve`：解析前端提交的题目图片 Base64、可选模型与讲题要求，
          触发 Antigravity 视觉推理并将推演结果返回前端。
        """
        if self.path == "/api/solve":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as e:
                self._send_json({"ok": False, "error": f"请求体解析失败: {e}"}, status=400)
                return

            image_data = body.get("imageBase64", "")
            extra_note = body.get("note", "")
            model_slug = body.get("model", DEFAULT_MODEL_SLUG)

            if not image_data:
                self._send_json({"ok": False, "error": "请先上传或粘贴题目图片"}, status=400)
                return

            # 解析 DataURL 头部并提取图片原始二进制
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

            # 备份上传的题目图片到工作区 uploads/ 目录
            filename = f"problem_{int(time.time())}.{ext}"
            saved_path = (UPLOADS_DIR / filename).resolve()
            if not str(saved_path).startswith(str(WORKSPACE_DIR)):
                self._send_json({"ok": False, "error": "非法路径访问已被沙箱拦截"}, status=403)
                return
            saved_path.write_bytes(raw_bytes)

            # 触发端到端自动解题
            result = None
            try:
                result = solve_problem_automatically(raw_bytes, mime_type, extra_note, model_slug)
                self._send_json({
                    "ok": True,
                    "mode": "auto",
                    "model": result.get("model", model_slug),
                    "user": result.get("user", "Pro User"),
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
        """
        向客户端发送 JSON 格式响应的辅助方法。

        Args:
            data (dict): 待序列化的响应数据字典。
            status (int, optional): HTTP 状态码，默认为 200。
        """
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    """
    启动初中几何微课 HTTP 服务的命令行主入口。
    """
    os.chdir(WORKSPACE_DIR)
    lan_ip = get_lan_ip()
    srv_info = discover_local_antigravity_server()

    print("============================================================")
    print(" 🚀 数学几何微课全自动 Web App 服务已启动（支持局域网共享）！")
    print(f" 🔒 严格沙箱工作区: {WORKSPACE_DIR}")
    if srv_info:
        print(f" ✅ 已自动连接 Antigravity Pro 引擎 (用户: {srv_info['user']}, 端口: {srv_info['port']})")
    else:
        print(" ⚠️ 未检测到 Antigravity 客户端，请保持 Antigravity 开启")
    print(f" 💻 本机访问地址:   http://127.0.0.1:{SERVER_PORT}/viewer.html")
    print(f" 📱 局域网访问地址: http://{lan_ip}:{SERVER_PORT}/viewer.html  (或直接 http://{lan_ip}:{SERVER_PORT})")
    print("============================================================")

    server = ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), MathTutorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")


if __name__ == "__main__":
    main()
