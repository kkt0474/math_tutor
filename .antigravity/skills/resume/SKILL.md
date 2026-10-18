---
name: resume
description: 从 docs/HANDOFF.md 加载完整上下文并待命
---

# /resume Execution Instructions

当用户在新 Chat 输入 `/resume` 时：
1. 静默读取 `docs/HANDOFF.md`。
2. 用 2 句话向用户做认知对齐：
   - “已加载上下文。当前整体需求是 [A]，目前进度已完成 [B]，已知避坑点有 [C]。”
   - “我已就绪，请告诉我接下来做什么。”
3. 停止输出，等待用户的具体新指令。
