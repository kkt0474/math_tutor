#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - HTTP 服务端入口模块 (server.py)
==================================================
功能说明：
1. 本地多线程 Web 后端服务主入口（支持局域网内同一 Wi-Fi 多设备访问）；
2. 托管当前工作区静态 Web 资源（viewer.html, lesson.js 等）；
3. 服务启动前对三阶段流水线凭证（TextIn, DeepSeek 等）进行强校验，
   若未配置则直接在控制台报错并退出，避免静默失败；
4. 暴露 `/api/status` 与 `/api/solve` REST API，默认开启全链路 DEBUG 级别日志。
"""

import base64
import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from config import (
    DEBUG_LOG_PATH,
    DEFAULT_MODEL_SLUG,
    LESSON_JS_PATH,
    SERVER_HOST,
    SERVER_PORT,
    UPLOADS_DIR,
    WORKSPACE_DIR,
    get_logger,
    load_app_config,
)
from plugins.pipeline import PipelineManager
from solver import solve_problem_automatically
from utils import discover_local_antigravity_server, get_lan_ip

logger = get_logger()

# ==========================================
# 前端用户级实时推演进度与任务取消状态
# ==========================================
PIPELINE_STATUS: dict = {
    "status": "idle",  # "idle" | "running" | "done" | "error" | "cancelled"
    "stage": 0,        # 0: 就绪, 1: 清洗, 2: 转录, 3: 推演
    "title": "就绪",
    "logs": [],        # [{"time": "00:03", "text": "...", "type": "info"|"success"|"warning"|"error"}]
    "startTime": 0,
    "elapsed": 0,
    "cancel_requested": False,
    "error": None,
}


def humanize_error(err: Exception) -> str:
    """将底层晦涩的技术报错转换为面向普通用户的温和中文指导"""
    s = str(err)
    s_lower = s.lower()
    if "用户已取消" in s or "cancel" in s_lower:
        return "本次微课推演已由您手动终止。"
    if "403" in s or "forbidden" in s_lower:
        return "试卷去涂鸦或大模型服务接口鉴权失败 (403 Forbidden)，请检查 API 额度或账户权限。"
    if "401" in s or "unauthorized" in s_lower:
        return "API 凭证鉴权未通过 (401 Unauthorized)，请检查 .env 配置文件中的 API Key 是否有效。"
    if "429" in s or "rate limit" in s_lower:
        return "大模型调用频率达到限额 (429 Rate Limit)，请稍等 1~2 分钟后再试。"
    if "textin" in s_lower or "textin_app_id" in s:
        return "试卷底图去涂鸦服务 (TextIn) 处理异常，请检查凭证配置或原图格式。"
    if "antigravity" in s_lower or "language_server" in s:
        return "本地 Antigravity 客户端未检测到运行，请确认客户端软件已打开并完成登录。"
    if "timed out" in s_lower or "timeout" in s_lower:
        return "模型推演等待超时（题目复杂度较高或网络延迟较大），建议重新提交或切换为极速模型。"
    if "ellipsis" in s_lower or "json" in s_lower or "微课 json" in s:
        return "模型输出的几何板书答题卡格式异常，建议重新提交让模型重新生成。"
    if "connection" in s_lower or "refused" in s_lower or "network" in s_lower:
        return "网络连接中断或远端服务无响应，请检查当前网络状态后重试。"
    return f"推演遇到问题：{s[:90]}"


def report_progress(stage: int, title: str, text: str, log_type: str = "info"):
    """实时记录面向用户的进度日志"""
    now = time.time()
    t_start = PIPELINE_STATUS.get("startTime") or now
    elapsed_sec = int(now - t_start)
    m, s = divmod(elapsed_sec, 60)
    time_str = f"{m:02d}:{s:02d}"
    PIPELINE_STATUS["stage"] = stage
    PIPELINE_STATUS["title"] = title
    PIPELINE_STATUS["elapsed"] = elapsed_sec
    PIPELINE_STATUS["logs"].append({
        "time": time_str,
        "text": text,
        "type": log_type,
    })


def is_cancel_requested() -> bool:
    return bool(PIPELINE_STATUS.get("cancel_requested", False))


def get_system_default_dirs() -> dict:
    """获取系统默认保存路径与操作系统类型 (支持 macOS 与 Windows)"""
    home = Path.home()
    desktop = home / "Desktop"
    documents = home / "Documents"
    return {
        "desktop": str(desktop if desktop.exists() else home),
        "documents": str(documents if documents.exists() else home),
        "home": str(home),
        "os": platform.system().lower(),  # "darwin", "windows", "linux"
    }


def choose_folder_native(initial_dir: str = "") -> str:
    """跨平台唤起系统原生文件夹选择器 (Mac Finder / Windows 资源管理器)"""
    sys_name = platform.system().lower()
    start_dir = initial_dir if (initial_dir and Path(initial_dir).exists()) else str(Path.home() / "Desktop")

    if sys_name == "darwin":
        osa_script = f'''
        set defaultPath to POSIX file "{start_dir}"
        try
            set chosenFolder to choose folder with prompt "请选择微课保存文件夹:" default location defaultPath
            POSIX path of chosenFolder
        on error
            return ""
        end try
        '''
        try:
            res = subprocess.run(["osascript", "-e", osa_script], capture_output=True, text=True, timeout=60)
            return res.stdout.strip()
        except Exception as e:
            logger.warning("macOS 文件夹选择器调起异常: %s", e)
            return ""

    elif sys_name == "windows":
        ps_cmd = f'''
        Add-Type -AssemblyName System.Windows.Forms
        $f = New-Object System.Windows.Forms.FolderBrowserDialog
        $f.Description = "请选择微课保存文件夹"
        $f.SelectedPath = "{start_dir}"
        if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
            Write-Output $f.SelectedPath
        }}
        '''
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=60)
            return res.stdout.strip()
        except Exception as e:
            logger.warning("Windows 文件夹选择器调起异常: %s", e)
            return ""

    return ""


def open_file_in_explorer(file_path: str) -> bool:
    """在系统的文件管理器 (Finder / 资源管理器) 中定位选中文件"""
    sys_name = platform.system().lower()
    p = Path(file_path).resolve()
    if not p.exists():
        return False
    try:
        if sys_name == "darwin":
            subprocess.run(["open", "-R", str(p)], check=False)
            return True
        elif sys_name == "windows":
            subprocess.run(["explorer", f"/select,{str(p)}"], check=False)
            return True
    except Exception as e:
        logger.warning("打开文件管理器失败: %s", e)
    return False


class MathTutorHandler(SimpleHTTPRequestHandler):
    """
    初中几何交互微课 HTTP 请求处理器。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WORKSPACE_DIR), **kwargs)

    def log_message(self, format: str, *args):
        """
        将标准 HTTP 访问日志统一接入全局 DEBUG Logger。
        """
        logger.debug("[HTTP] %s - %s", self.address_string(), format % args)

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

        if self.path.startswith("/api/progress"):
            if PIPELINE_STATUS.get("status") == "running":
                now = time.time()
                t_start = PIPELINE_STATUS.get("startTime") or now
                PIPELINE_STATUS["elapsed"] = int(now - t_start)
            self._send_json({"ok": True, "progress": PIPELINE_STATUS})
            return

        if self.path.startswith("/api/status"):
            srv = discover_local_antigravity_server()
            mtime = LESSON_JS_PATH.stat().st_mtime if LESSON_JS_PATH.exists() else 0
            cfg = load_app_config()
            self._send_json({
                "ok": True,
                "workspace": str(WORKSPACE_DIR),
                "connected": bool(srv),
                "user": srv["user"] if srv else None,
                "lessonMtime": mtime,
                "pipeline": cfg.get("pipeline", {}),
            })
            return

        if self.path.startswith("/api/default_save_dir"):
            self._send_json({"ok": True, "dirs": get_system_default_dirs()})
            return

        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/select_folder"):
            length = int(self.headers.get("Content-Length", 0))
            body = {}
            if length > 0:
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:
                    pass
            initial_dir = body.get("initialDir", "")
            chosen = choose_folder_native(initial_dir)
            if chosen:
                self._send_json({"ok": True, "folderPath": chosen})
            else:
                self._send_json({"ok": False, "cancelled": True})
            return

        if self.path.startswith("/api/save_offline_lesson"):
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as e:
                self._send_json({"ok": False, "error": f"JSON解析失败: {e}"}, status=400)
                return

            filename = body.get("filename", "").strip()
            folder_path = body.get("folderPath", "").strip()
            html_content = body.get("htmlContent", "")

            if not filename or not html_content:
                self._send_json({"ok": False, "error": "文件名或微课内容为空"}, status=400)
                return

            if not filename.endswith(".html"):
                filename += ".html"

            # 清洗文件名中的非法字符
            filename = re.sub(r'[\\/:*?"<>|]', '_', filename)

            target_folder = Path(folder_path).resolve() if folder_path else (Path.home() / "Desktop")
            if not target_folder.exists():
                try:
                    target_folder.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self._send_json({"ok": False, "error": f"无法创建保存目录: {e}"}, status=400)
                    return

            target_file = target_folder / filename
            try:
                target_file.write_text(html_content, encoding="utf-8")
                logger.info("💾 [save_lesson] 成功保存单文件离线微课: %s (%d 字符)", target_file, len(html_content))
                self._send_json({
                    "ok": True,
                    "filePath": str(target_file),
                    "filename": filename,
                    "folderPath": str(target_folder),
                })
            except Exception as e:
                logger.error("❌ [save_lesson] 写入微课文件失败: %s", e)
                self._send_json({"ok": False, "error": f"写入文件失败: {e}"}, status=500)
            return

        if self.path.startswith("/api/open_file_folder"):
            length = int(self.headers.get("Content-Length", 0))
            body = {}
            if length > 0:
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:
                    pass
            file_path = body.get("filePath", "")
            ok = open_file_in_explorer(file_path)
            self._send_json({"ok": ok})
            return

        if self.path.startswith("/api/cancel"):
            PIPELINE_STATUS["cancel_requested"] = True
            PIPELINE_STATUS["status"] = "cancelled"
            report_progress(PIPELINE_STATUS.get("stage", 0), "终止", "🛑 您已手动下发终止指令，正在中止流水线...", "warning")
            logger.info("🛑 [/api/cancel] 收到前端取消指令")
            self._send_json({"ok": True, "message": "已成功下发取消指令"})
            return
        if self.path == "/api/solve":
            t_req_start = time.time()
            client_ip = self.client_address[0] if self.client_address else "unknown"
            length = int(self.headers.get("Content-Length", 0))
            logger.info("📥 [/api/solve] 收到解题请求 | client=%s | Content-Length=%d bytes", client_ip, length)

            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as e:
                logger.error("❌ [/api/solve] 请求体 JSON 解析失败: %s", e, exc_info=True)
                self._send_json({"ok": False, "error": f"请求体解析失败: {e}"}, status=400)
                return

            image_data = body.get("imageBase64", "")
            extra_note = body.get("note", "").strip()
            model_slug = body.get("model", DEFAULT_MODEL_SLUG)
            enable_transcription = bool(body.get("enableTranscription", True))
            transcription_model = body.get("transcriptionModel", "gemini-3.8-flash-medium")

            if not image_data:
                logger.warning("⚠️ [/api/solve] 请求未包含 imageBase64")
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

            # 备份上传的题目图片
            filename = f"problem_{int(time.time())}.{ext}"
            saved_path = (UPLOADS_DIR / filename).resolve()
            if not str(saved_path).startswith(str(WORKSPACE_DIR)):
                logger.error("🚨 [/api/solve] 非法路径访问拦截: %s", saved_path)
                self._send_json({"ok": False, "error": "非法路径访问已被沙箱拦截"}, status=403)
                return
            saved_path.write_bytes(raw_bytes)
            logger.debug(
                "💾 [/api/solve] 原始图片已保存: %s (%d bytes, mime=%s) | model=%s | transcribe=%s (%s) | note=%s",
                saved_path,
                len(raw_bytes),
                mime_type,
                model_slug,
                enable_transcription,
                transcription_model,
                extra_note,
            )

            # 重置并启动面向前端的实时进度追踪
            PIPELINE_STATUS.update({
                "status": "running",
                "stage": 1,
                "title": "正在启动流水线",
                "logs": [],
                "startTime": time.time(),
                "elapsed": 0,
                "cancel_requested": False,
                "error": None,
            })
            report_progress(1, "启动任务", "🚀 题目已接收，进入多模型几何推演流水线...", "info")

            try:
                result = solve_problem_automatically(
                    image_bytes=raw_bytes,
                    mime_type=mime_type,
                    extra_note=extra_note,
                    model_slug=model_slug,
                    enable_transcription=enable_transcription,
                    transcription_model=transcription_model,
                    progress_cb=report_progress,
                    cancel_check=is_cancel_requested,
                )
                logger.info(
                    "✅ [/api/solve] 请求处理成功！总耗时=%ss | 各阶段耗时=%s",
                    result.get("elapsed"),
                    result.get("stageElapsed"),
                )
                PIPELINE_STATUS["status"] = "done"
                report_progress(3, "推演完成", "🎉 微课生成完毕！正在装配动态画板与中考规范解析...", "success")

                self._send_json({
                    "ok": True,
                    "mode": "pipeline",
                    "model": result.get("model", "deepseek"),
                    "user": result.get("user", "Pro User"),
                    "elapsed": result.get("elapsed", 0),
                    "stageElapsed": result.get("stageElapsed", {}),
                    "lessonData": result["lessonData"],
                })
            except Exception as e:
                cost = round(time.time() - t_req_start, 2)
                tb_str = traceback.format_exc()
                user_msg = humanize_error(e)
                PIPELINE_STATUS["status"] = "cancelled" if is_cancel_requested() else "error"
                PIPELINE_STATUS["error"] = user_msg
                report_progress(PIPELINE_STATUS.get("stage", 0), "推演中断", f"❌ {user_msg}", "error")

                logger.error(
                    "💥 [/api/solve] 流水线执行抛出异常 (已耗时 %ss): %s\n%s",
                    cost,
                    e,
                    tb_str,
                )
                self._send_json({
                    "ok": False,
                    "error": user_msg,
                    "raw_error": str(e),
                    "traceback": tb_str,
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


def main():
    """
    启动服务主入口，严格执行启动前凭据自检并开启 DEBUG 日志。
    """
    os.chdir(WORKSPACE_DIR)
    lan_ip = get_lan_ip()

    print("============================================================")
    print(" 🚀 数学几何微课流水线 Web App 服务正在启动 (DEBUG 日志已开启)...")
    print(f" 🔒 工作区沙箱: {WORKSPACE_DIR}")
    print(f" 📜 实时调试日志文件: {DEBUG_LOG_PATH}")

    # 加载外部配置
    cfg = load_app_config()
    pipeline_mgr = PipelineManager(cfg)

    # 启动前强校验凭据，不满足直接报错中止
    try:
        pipeline_mgr.validate_all()
    except Exception as e:
        logger.error("❌ 服务启动终止：凭据校验未通过！详情: %s", e, exc_info=True)
        print("\n💡 提示：请打开根目录下的 .env 文件填入对应的 API 凭据后再次启动。")
        print("============================================================")
        sys.exit(1)

    print("============================================================")
    print(f" 💻 本机访问地址:   http://127.0.0.1:{SERVER_PORT}/viewer.html")
    print(f" 📱 局域网访问地址: http://{lan_ip}:{SERVER_PORT}/viewer.html")
    print("============================================================")

    server = ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), MathTutorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务已手动停止。")


if __name__ == "__main__":
    main()
