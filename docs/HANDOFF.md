# Session Handoff State

## 1. 需求说明 (Requirements Summary)

- **业务背景与目标**：
  - 构建一个单页几何微课 Web App，面向初中生数学几何培优学习。
  - 用户上传或粘贴几何原题图片（支持 `Cmd/Ctrl + V` 粘贴、拖拽、文件选择），全自动执行多阶段多模型流水线处理，生成 1:1 还原原图、分步推导、动态生成 GeoGebra 交互式板书指令与中考规范书写过程，前台自动加载显示。
- **三阶段流水线架构（TextIn ➔ Gemini ➔ DeepSeek / Gemini）**：
  1. **阶段 1：TextIn / 去笔迹工具（底图物理清洗员）**：
     - 官方文档：[TextIn 智能手写涂鸦擦除 (text_auto_removal)](https://www.textin.com/document/text_auto_removal)
     - REST API 端点：`https://api.textin.com/ai/service/v1/handwritten_erase`
     - 职责：抹除试卷上的手写字、铅笔草稿、红笔批改与学生自画错误辅助线，输出黑白清晰印刷底图。
     - 严禁：不提取语义，不解析空间逻辑。
  2. **阶段 2：Gemini 本地 Antigravity RPC（空间视觉与题设转录员）**：
     - 职责：提取题干中所有文字与公式（转为标准 LaTeX），精准识别图中点线空间拓扑（延长线、相交、共线、垂直标、等长等角标），输出毫无歧义的纯文本几何命题描述。
     - 严禁：**严禁解题**，严禁输出任何证明步骤或辅助线构造。
  3. **阶段 3：DeepSeek / Gemini 推理架构师（深度证明与绘图架构师）**：
     - 支持模型：`deepseek-v4-pro`（旗舰深度推理）、`deepseek-flash`（极速推演）以及本地免费的 `gemini_rpc`；
     - 职责：接收阶段 2 转录的纯文本命题，开启深度思维链（Thinking），识别中考模型（旋转、隐圆、一线三垂直、费马点等），构造辅助线并输出无跳步证明，生成 GeoGebra 指令及前端契约 JSON。
     - 严禁：不直接接收原始图片，不参与图像预处理。
- **核心交互特色功能**：
  1. **全幅沉浸推演看板 & 任务终止**：推演看板完整覆盖左侧绘图区，实时流淌通俗进度日志并提供中止推演按钮（AbortController + `/api/cancel`）。
  2. **几何双关金句轮播与 AI 专属定制寄语**：推演看板底部展示数学几何双关趣味金句（墨墨背单词气泡风格），并在模型推演完成时自动展示基于题目模型特征的 AI 定制专属寄语。
  3. **单文件独立微课课件导出**：点击右对齐的“保存微课”按钮，弹窗支持自定义文件名与选择保存路径（跨平台支持 Mac/Windows），一键导出纯单文件 HTML（双击即开，零依赖）。
  4. **透明手写电子白板**：Canvas 批注涂鸦层，支持多色画笔、荧光笔、撤销与清空。
- **架构设计要求与约束**：
  1. **插件式配置模式（Strategy / Registry 模式）**：
     - `plugins/base.py` 抽象出 `BaseCleaner`, `BaseTranscriber`, `BaseReasoner`；
     - `plugins/registry.py` 支持类路径反射加载与装饰器注册。
  2. **统一配置与凭据隔离 (`.env` + `config.json`)**：
     - `.env` 隔离存放敏感密钥，`config.json` 集中管理提供商与超参数；
     - 服务启动时强制自检凭据，缺失时在终端友好报错拦截。
  3. **中考教学与绘图铁律（单一信任源：`.antigravity/AGENTS.md`）**：
     - 视觉方位 1:1 对齐原图；
     - 第 1 步纯粹原图呈现（蓝色实线）；
     - 第 2 步起辅助线动态生长（亮黄虚线），首行必须以 `【💡 辅助线是怎么想到的？】` 开头并精准点出模型（如【一线三垂直（K字全等）】）；
     - 分步因果分行排版，末行必须使用 `==...==` 高亮核心结论，数学符号包裹 `$...$`。

---

## 2. 当前进度与已踩的坑 (Progress & Lessons Learned)

### 已实现并验证的功能与重构成果
1. **多模型插件流水线架构完全落成并投入实战**：
   - `plugins/cleaners/textin_cleaner.py`：TextIn 手写涂鸦擦除 REST 插件；
   - `plugins/transcribers/gemini_rpc_transcriber.py`：Gemini 题设与拓扑转录插件；
   - `plugins/reasoners/deepseek_reasoner.py`：DeepSeek SSE 流式深度推理与绘图插件；
   - `plugins/reasoners/gemini_rpc_reasoner.py`：Gemini RPC 本地免费推演插件；
   - `plugins/pipeline.py`：三阶段流水线编排器（含指纹缓存与分阶段耗时统计）。
2. **全屏沉浸推演看板与金句轮播系统**：
   - 解决了原小窗口过小遮挡问题，以全幅遮罩覆盖左侧计算区；
   - 实现了数学几何双关趣味金句轮播与 AI 个性化定制寄语（`MATH_GEOMETRY_QUOTES`）。
3. **“保存微课”按钮布局与离线单文件导出**：
   - 按钮移至与右侧“上传几何题目图片”卡片右对齐；
   - 支持跨平台原生目录选择与本地单文件保存。
4. **全项目代码深度体检与健康度重构**：
   - **死变量与冗余清理**：移除了 `config.py` 中的 `MAX_POLL_TIMEOUT_SECONDS`、`POLL_INTERVAL_SECONDS`、`ENV_VARS` 及废弃的 `claude` 模型；移除了 `solver.py` 中未使用的 `agy_rpc` 导入；移除了 `pipeline.py` 中的单模型旧缓存分支；
   - **Prompt Token 瘦身**：统一将 `.antigravity/AGENTS.md` 作为单一信任源，移除了 `prompts.py` 中数千字重复注入的旧规则，单次推演节省约 1000 个上下文 Token；修复了 `note_content` 重复注入与编号跳跃问题；
   - **底层网络通信复用**：将 `create_ssl_context` 和 `build_http_opener` 抽象收拢至 `utils.py`，供 `textin_cleaner` 与 `deepseek_reasoner` 共享；
   - **`viewer.html` 单文件内部模块化（方案 A）**：维持单个 HTML 文件的便携性与零依赖离线导出能力，将脚本按 7 大子系统清晰模块化归类并解耦金句轮播与执行轮询逻辑；
   - **文档与 README 同步更新**：精简了核心亮点说明，校准了启动命令（`python3 server.py`）并更新了文件架构说明。

### 探索中解决的重大问题与避坑经验 (Lessons Learned)
1. **`viewer.html` 拆分方案的选择（为何否决物理拆分为外联 CSS/JS）**：
   - **踩坑风险**：`viewer.html` 具备“保存单文件离线微课”功能（通过内存深克隆当前 DOM 并序列化导出）。若直接将 CSS/JS 抽离为独立的外部文件，导出的单文件一旦脱离本地目录就会失去样式与脚本；
   - **解决方案**：采取**方案 A（内部模块化解耦）**，在保持单个 HTML 自包含特性的前提下，在文件内部划分清晰的模块标头与逻辑边界，兼顾可维护性与零依赖便携性。
2. **Prompt 规范双重注入导致 Token 膨胀与模型混乱**：
   - **原因**：早先在 `prompts.py` 中硬编码了 `GEOGEBRA_AND_TEACHING_RULES`，重构后又动态读入了 `AGENTS.md`，两份大同小异的规则同时拼入 Prompt，浪费了大量 Token；
   - **解决方案**：统一由 `AGENTS.md` 担任单一信任源，`prompts.py` 仅保留精炼的后备降级，杜绝双重注入。
3. **缓存命名与多模型维度的绑定**：
   - **经验**：转录题干缓存必须严格带有模型后缀（如 `cache_{hash}_{model}_transcription.txt`），若回退使用不带模型的旧格式可能导致不同模型间的转录产物交叉污染。
4. **macOS SSL 证书链与代理拦截 ([SSL: CERTIFICATE_VERIFY_FAILED])**：
   - **解决方案**：在 `utils.py` 中统一提供绕过证书链阻断的 `create_ssl_context()` 及直连/代理切换的 `build_http_opener()`。
5. **超大原图（8~10MB）导致 TextIn 60 秒写超时**：
   - **解决方案**：后端 `utils.optimize_image_bytes` 自动调用 macOS 原生 `sips` 在 0.14 秒内将大图转为高清 JPEG（体积减少 92%+），彻底杜绝上传超时。
6. **DeepSeek 长思考假死与 Ellipsis 序列化异常**：
   - **解决方案**：改用 SSE 流式传输 (`stream: True`) + 3 秒控制台心跳输出；在 `prompts.py` 中引导模型完成草稿后立即输出 JSON；在 `utils.extract_json_from_text` 中增加对 `[ ... ]` 的过滤清洗，防止 Python AST 解析出无法序列化的 `Ellipsis` 对象。
7. **Gemini RPC 轮询停机条件误判与截断 JSON 解析异常 ('[' was never closed)**：
   - **踩坑风险**：`gemini_rpc_reasoner.py` 早先误将非终态的 `finishReason`（如 `FINISH_REASON_UNSPECIFIED`）作为完成判定，导致模型刚吐出第一批字符即提前跳出循环并销毁会话；加之模型截断后尾部缺少闭合括号，触发 AST 解析异常 `SyntaxError: '[' was never closed`；
   - **解决方案**：
     1. 在 `prompts.py` 尾部引入专属结束信标 `===END_OF_LESSON===`；
     2. 严格校验 `latest_status in DONE/COMPLETED` 或 `latest_finish_reason in STOP/END_TURN/MAX_TOKENS`，并结合 4 次连续文本无变化稳定检测；
     3. 维持深度推演模型 `gemini-3.8-flash-high`，依托五级 JSON 自愈与精确流式停机检测支撑完整思考与生成闭环；
     4. 在 `utils.py` 中升级五级 JSON 自愈管线（阶段 5：括号栈反向闭合与截断数据补全 `repair_truncated_json`），即使输出被意外切断也能完整拯救已生成的几何小问与推导步骤；
     5. 在 `AGENTS.md` 中确立铁律：凡涉及性能影响、推理档位降级等重大权衡修改必须事先征得用户明确同意。

---

## 3. 关键代码资产 (Key Code Assets)

- **流水线插件与架构核心**：
  - [`config.json`](file:///Users/dean/Documents/math-tutor-workspace/config.json)：系统外部配置与模型超参数集中管理。
  - [`.env`](file:///Users/dean/Documents/math-tutor-workspace/.env) 与 [`.env.example`](file:///Users/dean/Documents/math-tutor-workspace/.env.example)：敏感 API 凭证管理文件（受 `.gitignore` 保护）。
  - [`plugins/base.py`](file:///Users/dean/Documents/math-tutor-workspace/plugins/base.py)：三大角色抽象基类 (`BaseCleaner`, `BaseTranscriber`, `BaseReasoner`)。
  - [`plugins/registry.py`](file:///Users/dean/Documents/math-tutor-workspace/plugins/registry.py)：热插拔插件注册表与动态工厂。
  - [`plugins/pipeline.py`](file:///Users/dean/Documents/math-tutor-workspace/plugins/pipeline.py)：三阶段流水线调度器（含指纹缓存与耗时统计）。
  - [`plugins/cleaners/textin_cleaner.py`](file:///Users/dean/Documents/math-tutor-workspace/plugins/cleaners/textin_cleaner.py)：TextIn 去手写清洗器。
  - [`plugins/transcribers/gemini_rpc_transcriber.py`](file:///Users/dean/Documents/math-tutor-workspace/plugins/transcribers/gemini_rpc_transcriber.py)：Gemini 空间拓扑与题设转录器。
  - [`plugins/reasoners/deepseek_reasoner.py`](file:///Users/dean/Documents/math-tutor-workspace/plugins/reasoners/deepseek_reasoner.py)：DeepSeek SSE 流式深度推理与板书架构师。
  - [`plugins/reasoners/gemini_rpc_reasoner.py`](file:///Users/dean/Documents/math-tutor-workspace/plugins/reasoners/gemini_rpc_reasoner.py)：本地 Antigravity Pro 免费极速推演架构师。
- **服务、调度与通用工具**：
  - [`server.py`](file:///Users/dean/Documents/math-tutor-workspace/server.py)：集成启动凭证自检、多线程 HTTP 服务与全链路 DEBUG 日志记录。
  - [`solver.py`](file:///Users/dean/Documents/math-tutor-workspace/solver.py)：流水线总入口与微课持久化调度。
  - [`config.py`](file:///Users/dean/Documents/math-tutor-workspace/config.py)：全局 DEBUG 日志器、配置加载与路径常量导出。
  - [`prompts.py`](file:///Users/dean/Documents/math-tutor-workspace/prompts.py)：提示词构造模块（单一信任源，消除重复注入）。
  - [`utils.py`](file:///Users/dean/Documents/math-tutor-workspace/utils.py)：原生直连 `agy_rpc`、进程探测、四级 JSON 自愈提取管线、原生 `sips` 图像瘦身引擎与统一网络 Opener 工厂。
  - [`viewer.html`](file:///Users/dean/Documents/math-tutor-workspace/viewer.html)：单页 Web App 主界面（模块化 7 大系统：Canvas 手绘层 + GeoGebra 引擎 + 核心控制器 + 上传控制 + 几何金句轮播 + 任务看板 + 独立课件导出）。
  - [`README.md`](file:///Users/dean/Documents/math-tutor-workspace/README.md)：项目技术文档与使用部署说明。
- **测试与验证手段**：
  - 全量 Python 文件语法编译：`python3 -m py_compile *.py plugins/*.py plugins/*/*.py`
  - 插件凭据与工厂可用性检测：`python3 -c "from plugins import PipelineManager; from config import load_app_config; PipelineManager(load_app_config()).validate_all()"`
  - 服务本地运行：`python3 server.py`
