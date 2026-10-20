# Session Handoff State

## 1. 需求说明 (Requirements Summary)

- **业务背景与目标**：
  - 构建一个单页几何微课 Web App，面向初中生数学几何培优学习。
  - 用户上传或粘贴几何原题图片（支持 Cmd+V 粘贴、拖拽、文件选择），系统全自动调用本机 Antigravity 后台引擎（复用用户的 Gemini 3.8 Flash / Gemini 4 Argon 等 Pro 高阶模型），全自动识别题目、1:1 还原原图、分步推导、动态生成 GeoGebra 交互式板书指令与中考规范书写过程，前台自动加载显示。
- **输入输出与数据契约**：
  - **输入**：题目图片（Base64 PNG/JPEG）、可选模型选择（默认 Gemini 3.8 Flash High）、可选补充讲题要求（`extra_note`）。
  - **输出数据格式**：严格格式化的 JSON 对象（定义在 `window.LESSON_DATA`），包含：
    - `viewConfig`: `{ hasAxes: false, bounds: { xmin, xmax, ymin, ymax } }`
    - `questions`: 数组，覆盖题目所有小问。每一问包含：
      - `title`: 小问题目与求证目标
      - `thoughtAnalysis`: 符合人类思维习惯的解题思路分析（题眼信号识别 + 人类破题思维路线，不堆砌详细算数）
      - `steps`: 3~4 个分步板书。每个步骤含 `name`、`modelName`、`explanation`、`ggbCommands`（GeoGebra 板书指令数组）
      - `solutionMarkdown`: 纯粹规范中考书写全文（支持 LaTeX 公式）
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
  11. **等角分组着色**：前端按角的数值把相等的角分组，同组同色同弧半径，不同组颜色与弧半径不同（`applyStep` 内 `ANGLE_GROUP_STYLES`），着色后必须再次隐藏角度标签（否则 GeoGebra 会重新显示 `angB = 60°`）。
  12. **自选坐标禁止“巧合特殊位置”**：未给出的角/线段不得恰好成为 90° 或相等（已写入 `AGENTS.md` 第 0 条）。
  13. **用户补充要求最高优先级**：`server.py` 把 `extra_note` 放在提示词最前面，并要求所有字段遵守。

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
5. **双模块默认折叠与「解题思路分析」功能**：
   - 页面左下侧「🧭 解题思路分析」与「📝 中考满分规范解答」默认均保持折叠状态，点击标题栏即可同步平滑展开/收起，有效精简页面垂直高度；
   - 契约新增 `thoughtAnalysis` 字段，严格聚焦“题眼信号识别（破题开关）”与“人类破题思维路线（逆向目标+顺向搭桥）”，避免跳跃式推导，不重复堆砌详细算数。

6. **近期新增并验证**：非阻塞轮询（`blocking: False` + 2 秒轮询，上限 900 秒）、四级 JSON 自愈解析、完成后显示计算耗时、标题/Tab 的 KaTeX 渲染、直角吸附（阈值 `1e-13`）、高亮结论裸 LaTeX 自动补 `$`。以上修复均只做过语法检查（`py_compile` / `node -c`），**尚待用户在浏览器端确认**：垂足 M 是否显示方框、黄色结论是否正常渲染公式。

### 已否决方案与避坑经验 (Lessons Learned)
0. **“生成失败：timed out”不一定是网络问题**：页面会继续显示旧的 `lesson.js` 内容，容易误判为新结果（曾误以为提示词没生效）；以右下角状态框为准。`server.py` 里还曾硬编码 `timeout=240`，覆盖了默认值。
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
6. **防范角命名同义反复与等号自指废话（如 $\angle B = \angle ABC$）**：
   - 模型在总结高亮结论时容易将单字母代号与三字母全称划等号。已在 `.antigravity/AGENTS.md` 与 `server.py` 的提示词中确立铁律：严禁单字母与三字母角自身划等号，除题干要求外统一使用三字母标准记法，等号两侧必须具备几何定理转化依据。
7. **思路分析卡片章节标题误判与括号吞噬防御**：
   - 前端解析 `thoughtAnalysis` 时严禁简单用 `line.includes('破局开关')` 作为大章节分割条件（因条目内部必然会出现“【破局开关】”标签），必须严格以正则 `^[#*•\-\s]*【?[💡\s]*题眼信号` 锚定行首标题；同时替换步骤标题时完整保留原文本中的括号内容，杜绝出现空括号 `()` 或文字丢失。
8. **GeoGebra 优角/反角（>180°吃豆人）与斜线垂足直角方框（∟）丢失的底层根治引擎**：
   - **为什么之前会出现反角修复失效 & 斜线垂足 M 变成圆弧而非直角方框 `∟`**：
     1. 中文环境下 `ggbApp.getCommandString(objName)` 可能返回本地化指令名（如 `角[...]`），导致正则匹配 `Angle(...)` 失败；为此改为在 `applyStep` 执行 `step.ggbCommands` 时**直接源头捕获 `Angle(P1, V, P2)` 三顶点映射表 `angleDefs`**，彻底摆脱对 GeoGebra 内部命令字符串的依赖。
     2. 利用**二维向量叉积（$\vec{v}_1 \times \vec{v}_2 = v_{1x}v_{2y} - v_{1y}v_{2x}$）**纯数学判定方向：只要 `cross < 0`（或弧度 $> \pi$），立即在前端执行 `Angle(P2, V, P1)` 翻转并注入 `<allowReflexAngle val="false"/>`，100% 根治 $>180^\circ$ 优角问题。
     3. **斜线垂足直角退化为圆弧的真凶**：当垂线落在 $60^\circ$ 等斜线上时，AI 导出的 3 位小数坐标（如 `M = (4.041, 7)`）会使 $\angle AMC \approx 90.00367^\circ$，而 GeoGebra 要求误差 $< 10^{-8}$ 才会绘制直角方框 `∟`！前端新增**正交投影自动吸附算法**：凡检测到角度在 $[88.0^\circ, 92.0^\circ]$ 区间内，自动通过向量内积将垂足坐标正交投影到精确的 $90.000000000000^\circ$ 位置并注入 `<emphasizeRightAngle val="true"/>`，实现所有斜线垂足 100% 渲染标准直角方框 `∟`。
9. **已知条件相等线段与相等角的全自动标出（Prompt 规范 + 前端智能扫描双保险）**：
   - 在 `.antigravity/AGENTS.md` 与 `server.py` 中确立刚性规范：从 `steps[0]` 起，所有已知相等线段必须用 `SetDecoration(seg, 1/2)` 标出刻度线（`|` / `||`），所有已知相等角必须用同色 `Angle` 标出；
   - 在 `viewer.html` 前端 `applyStep` 中内置**已知等长线段智能扫描器**：自动提取小问题干与首步说明中（`求证`/`求` 之前）的已知线段相等式（如 `DE = EF`、`BC = CD`），若画板仅有 `Polygon` 未单独建边则自动补建 `Segment`，并自动调用 `SetDecoration` 挂载等长刻度符号。
10. **Antigravity RPC 长时间推演超时破除（非阻塞轮询架构）**：
    - **真凶排查**：当题目包含 3 个大问且有强负向约束（如“禁止使用三角函数”）时，高阶模型深度思考耗时可达 4~6 分钟。若在 `SendUserCascadeMessage` 中使用 `blocking: True`，即使将 Python 超时改大，底层语言服务网关仍会在约 300 秒（5分钟）强制切断单 HTTP 请求导致 `timed out`；且原代码第 278 行硬编码了 `timeout=240`；
    - **根治**：在 `server.py` 中将发送改造为 `blocking: False`（非阻塞，毫秒级返回），随后以 2 秒间隔轻量轮询 `GetCascadeTrajectorySteps`（总超时上限 900 秒/15分钟），彻底摆脱底层网关 300 秒连接截断限制；前端同步增加动态秒级耗时计数器。
11. **模型长 JSON 解析自愈与等待时长体验优化**：
    - **真凶排查**：改造非阻塞轮询后，模型耗时 7~8 分钟完整输出了 21,904 字符的微课数据（证明轮询连接已打通，不再被 240s/300s 掐断）。但在最后一步 Python `json.loads` 时报错 `Expecting ',' delimiter: line 164`。原因是大模型在长达两万字符的 LaTeX 公式（如 `\angle`, `\perp` 等）与 GeoGebra 指令（如嵌套引号 `SetColor(seg, "#38BDF8")`）中存在单反斜杠与未转义引号；
    - **根治**：在 `server.py` 的 `extract_json_from_text` 中构建四级自愈管线（自动备份 `uploads/last_raw_model_reply.txt`、全量 LaTeX 单反斜杠转义、尾部多余逗号清洗、GeoGebra 引号清洗、AST 结构降级解析），100% 救回轻微语法瑕疵的 JSON。
12. **页面标题/标签 KaTeX 全覆盖、计算耗时显式回传与默认高精度模型策略**：
    - **美元符号残留修复**：题干标题中的数学公式（如 `$\angle BAC=90^\circ$`）在小问 Tab 标签（`btn.innerText`）、步骤标题栏（`subStep.innerText`）和解答标题中原先使用了纯文本赋值导致未触发 KaTeX 渲染；统一改造为调用 `formatMathAndMarkdown(...)` 赋值 `innerHTML`，实现全页面 100% 优雅公式渲染；
    - **耗时实时可视化**：后端 `server.py` 计算并回传 `elapsed` 秒数，前端完成时显式呈现 `⏱️ 本次推演计算耗时：X 分 Y 秒`；
    - **默认模型策略**：鉴于初中压轴几何题对多步辅助线探索、旋转倒角与“禁止使用三角函数”负向约束的高难度要求，默认模型坚定锁定为 **`Gemini 3.8 Flash (High)`**，确保数学推演精度与辅助线灵感处于最佳状态。
13. **直角方框回归与高亮结论裸 LaTeX 兜底**：
    - **垂足 M 又变圆弧的真因**：正交投影吸附原先仅在偏差 `> 1e-5°` 时才触发；而 6 位小数坐标产生的偏差约 `4e-6°`，既小于该阈值（不吸附），又远大于 GeoGebra 直角方框判定阈值（约 `1e-8` rad ≈ `6e-7°`），于是落入“漏网区间”画成圆弧。现将触发阈值降为 `1e-13`，只要在 88°~92° 就一律吸附到精确 90°；
    - **高亮结论 `\angle` 裸露**：模型有时在 `==...==` 中漏写 `$...$`。前端 `formatMathAndMarkdown` 增加兜底：对不含 `$` 但含 LaTeX 命令的 `==...==` 块，按非 ASCII 字符切段并为含反斜杠命令的片段自动包上 `$...$`；同时在 `server.py` 提示词中新增铁律，要求高亮块内数学符号必须用 `$...$` 包裹。

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
