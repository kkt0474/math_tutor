# Session Handoff State

## 1. 需求说明 (Requirements Summary)

- **业务背景与目标**：
  - 构建一个单页几何微课 Web App，面向初中生数学几何培优学习。
  - 用户上传或粘贴几何原题图片（支持 Cmd+V 粘贴、拖拽、文件选择），系统全自动调用本机 Antigravity 后台引擎（复用用户的 Gemini 3.8 Flash / Gemini 4 Argon 等 Pro 高阶模型），全自动识别题目、1:1 还原原图、分步推导、动态生成 GeoGebra 交互式板书指令与中考规范书写过程，前台自动加载显示。
- **输入输出与数据契约**：
  - **输入**：题目图片（Base64 PNG/JPEG）、可选模型选择（默认 Gemini 3.8 Flash）、可选补充讲题要求（`extra_note`）。
  - **输出数据格式**：严格格式化的 JSON 对象（定义在 `window.LESSON_DATA`），包含：
    - `viewConfig`: `{ hasAxes: false, bounds: { xmin, xmax, ymin, ymax } }`
    - `questions`: 数组，覆盖题目所有小问。每一问包含：
      - `title`: 小问题目与求证目标
      - `steps`: 3~4 个分步板书。每个步骤含 `name`、`modelName`、`explanation`、`ggbCommands`（GeoGebra 板书指令数组）
      - `solutionMarkdown`: 规范中考书写全文（支持 LaTeX 公式）
- **核心逻辑与教学规范约束**：
  1. **视觉方位 1:1 对齐原图**：原图无坐标系时必须以原图水平/铅直线为基准建系，严禁随意旋转或扭曲图形几何拓扑。
  2. **第 1 步纯粹原图呈现**：第 1 步（`steps[0]`）只画题目已知几何点线（蓝色实线），严禁在第 1 步出现任何辅助线。
  3. **辅助线动态生长**：第 2 步起通过亮黄色虚线（`SetLineStyle(aux, 2)`, `SetColor(aux, "#FACC15")`）动态生长辅助线。
  4. **启发式辅助线思维引导铁律**：凡是有辅助线的步骤，`explanation` 第 1 行必须以 `【💡 辅助线是怎么想到的？】` 开头，讲清“图中现有残缺特征 $\rightarrow$ 为什么需要补这条线 $\rightarrow$ 如何作辅助线”，严禁直接生硬下达作图指令。
  5. **经典解题套路精准识别**：
     - 若出现典型残缺模型特征（如直线上已有两直角且伴随等腰直角斜边相等，即“一线两垂直”），**必须明确点出【一线三垂直（K字型全等）】**，讲清“知二补一”；其他如 8字型（沙漏）全等、倍长中线、截长补短、手拉手、将军饮马等真模型，均需讲明触发信号并明确点出。
     - 若完全无需画辅助线、顺着已知条件自然推导（如第 1 问直接证 SAS 全等），则严禁生搬硬套复杂模型名。
  6. **按行分步排版**：每一行只写一个有直接关联的因果推导（“因为……，所以我们得到……。”），下一个子步骤必须用 `\n` 换行另起一行，以 `①`、`②`、`③` 规整展示。
  7. **本步核心目标高亮**：每个步骤 `explanation` 最后一行必须用 `==...==` 包裹最终达成的核心目标，前端自动渲染为带有 `🎯` 的金色荧光笔高亮胶囊。
  8. **严格工作区沙箱隔离**：独立创建 Antigravity 临时会话，所有操作与数据只限定在 `math-tutor-workspace` 内，请求完成后自动清理会话，严禁污染其他工作区。
  9. **局域网全网卡共享**：后端绑定 `0.0.0.0:8765` 并采用多线程并发，同一 Wi-Fi 内其他设备（手机、iPad、PC）可直接通过本机 IP 访问使用。
  10. **画板交互标注功能（方案 A）**：画板内置轻量交互工具栏，支持鼠标点击线段一键打上初中数学规范的等长双划线刻度（`||`）、高亮等角与一键清空标记。

---

## 2. 当前进度与已踩的坑 (Progress & Lessons Learned)

### 已实现并验证的功能
1. **全自动端到端单页 Web App**：
   - 前端：`viewer.html` 集成 GeoGebra Web 引擎与 KaTeX 公式渲染器，支持拖拽、点击、Cmd+V 粘贴图片，一键提交并在画板中央呈现居中 Loading 状态，生成后自动无缝展示动态板书。
   - 后端：`server.py` 通过发现本地运行的 Antigravity Local Language Server RPC 端口，直接以 `StartCascade` 隔离方式发起多模态视觉推理，生成标准几何 JSON 数据并持久化到 `lesson.js` 与 `uploads/`。
2. **启发式辅助线思维卡片（`💡 辅助线是怎么想到的？`）**：
   - 前端已支持自动识别并在行首渲染翡翠绿色的 `💡 辅助线思维引导` 胶囊，中间行渲染天蓝色 `① ② ③` 因果推导，末尾行渲染金色 `🎯 目标高亮`。
3. **交互式几何标注工具栏（方案 A）**：
   - 在 GeoGebra 画板右上角实现悬浮磨砂玻璃工具栏，包含 `[ |=| 标记等长边 ]`、`[ ⌒ 标记等角 ]`、`[ 🧹 清空标记 ]`。
   - 监听 GeoGebra 对象的点击事件，用户点击两条线段即可自动添加数学双划线 `||` 刻度与亮色高亮，并伴有底部操作气泡提示。
4. **局域网多设备共享**：
   - `server.py` 已升级为 `ThreadingHTTPServer(("0.0.0.0", 8765))`，自动扫描获取本地真实局域网 IP（自动过滤 198.18.x.x 代理虚拟网卡），前端 API 地址自动自适应 `window.location.origin`。

### 已否决方案与避坑经验 (Lessons Learned)
1. **严禁一刀切完全禁用套路名**：
   - 之前因禁止模型“生搬硬套解题套路”，导致模型过度纠偏，在遇到真正需要“一线三垂直/K字全等”时也变成了生硬的指令式作图。必须明确划分**“何时必讲模型信号（知二补一作辅助线）”**与**“何时不强行套模型（无辅助线常规顺推）”**的边界。
2. **严禁依赖纯客户端直接直连公网 Gemini API**：
   - Gemini API 免额度仅限较低端模型，且无法直接使用用户的 Antigravity Pro 会员权益；走本地 RPC 通道（`127.0.0.1` RPC）是唯一既免 API Key 又能 100% 使用 Gemini 3.8 Flash / 4 Argon 等顶级模型的正确路线。
3. **严禁直接让前端调用写死的 `http://127.0.0.1:8765`**：
   - 写死 127.0.0.1 会导致局域网其他设备访问时请求失败，必须使用 `window.location.protocol.startsWith('http') ? window.location.origin : 'http://127.0.0.1:8765'`。
4. **防范 JSON 中单反斜杠转义控制字符破坏**：
   - 模型在 JSON 字符串中有时会把 LaTeX 写作单反斜杠 `\triangle`, `\text`, `\because`, `\frac`，这会被 `json.loads` 错误转义成 Tab、Backspace、FormFeed 等 ASCII 控制字符。已在 `server.py` 和 `viewer.html` 中加入了双重前置正规化修复。
5. **GeoGebra 角度度数文字重叠**：
   - GeoGebra 生成 `Angle(...)` 时默认会显示角度名称和具体度数，多角重叠时极其凌乱。已在前端注入技术兜底：自动遍历画板对象执行 `ggbApp.setLabelVisible(objName, false)`，仅保留直角方框与圆弧，隐藏文字度数。

---

## 3. 关键代码资产 (Key Code Assets)

- **核心业务与前端**：
  - `/Users/dean/Documents/math-tutor-workspace/viewer.html`：单页 Web App 主界面，包含 GeoGebra 交互画板容器、几何标注工具栏、字幕分步排版器、KaTeX 公式渲染、图片上传及状态控制器。
  - `/Users/dean/Documents/math-tutor-workspace/server.py`：全自动本地服务后端（多线程 HTTP），承载 Antigravity RPC 进程探测、工作区隔离会话、多模态 Prompt 构造、单反斜杠防御解析及局域网服务分发。
  - `/Users/dean/Documents/math-tutor-workspace/lesson.js`：当前题目经过完整格式化、带有启发式辅助线思维与等长边标注的完整微课数据载体。
- **系统行为与契约规则**：
  - `/Users/dean/Documents/math-tutor-workspace/.antigravity/AGENTS.md`：Antigravity 模型在当前工作区生成微课时遵循的最高准则与铁律（含 1:1 还原、启发式辅助线引导、按行排版与高亮规则）。
  - `/Users/dean/Documents/math-tutor-workspace/.antigravity/skills/save/SKILL.md`：`/save` 命令规范与执行指南。
  - `/Users/dean/Documents/math-tutor-workspace/.antigravity/skills/resume/SKILL.md`：`/resume` 命令规范与执行指南。
- **交接与状态文件**：
  - `/Users/dean/Documents/math-tutor-workspace/docs/HANDOFF.md`：跨会话上下文交接基准文档。
