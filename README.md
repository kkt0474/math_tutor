# 📐 Math Tutor - 初中几何交互微课全自动生成器

> **基于多模态大模型与 GeoGebra 交互画板的初中数学几何微课自动化生产系统。**  
> 一键粘贴题目图片，全自动完成试卷笔迹擦除、几何空间拓扑转录、深度逻辑推理证明、GeoGebra 动态交互板书与中考规范解析生成，并支持电子白板自由手写批注与单文件离线课件导出。

---

## 🌟 核心亮点与特色

- 📸 **全自动多模型流水线**：集成 TextIn 试卷去笔迹 + Gemini 空间拓扑转录 + DeepSeek/Gemini 深度逻辑推演，亦支持多模态极速直连看图解题。
- 📐 **1:1 原图复刻与动态交互板书**：自适应建立几何坐标系，保证图形方位与原图完全一致；GeoGebra 动态呈现原题线段与亮黄辅助线，自动隐藏杂乱度数干扰。
- 💡 **启发式辅助线思维引导**：独创“辅助线是怎么想到的”思维剖析，精准识别一线三垂直、8字全等、倍长中线、截长补短等中考经典模型，讲透破局动机。
- ✏️ **透明电子白板自由手写批注**：画板上方叠加透明 HTML5 Canvas 涂鸦层，支持鼠标与触控笔随心圈角划线，提供多色调色盘、撤销与一键清空。
- 🖥️ **全幅沉浸推演看板 & 几何心语**：推演看板完整覆盖左侧舞台，实时流淌通俗进度日志并支持一键终止；内置数学几何趣味双关金句轮播（类似墨墨背单词风格）与 AI 专属定制寄语。
- 💾 **单文件独立离线微课导出**：支持自定义文件名与保存位置（跨平台兼容 Mac 与 Windows）；导出的 `.html` 单文件完全独立，在任意电脑双击浏览器即可全屏交互教学，无需依赖本软件或后端服务。
- 📱 **多端局域网教学共享**：全设备响应式适配，同一 Wi-Fi 下的 iPad、平板、手机即开即用，平板上支持手写笔流畅触控。

---

## 🛠️ 技术栈与使用的大模型

### 1. 前端技术栈
- **核心框架**：原生 HTML5 / CSS3（暗黑沉浸式质感）+ 原生 ES6+ JavaScript（零重量级框架依赖，极速轻量）；
- **动态几何引擎**：GeoGebra Web API (`webSimple` / `deployggb.js`)，实现代码级驱动的矢量几何动态构建与动画；
- **手绘涂鸦层**：HTML5 Canvas 批注系统，支持 Retina 高分屏 DPR 自适应与贝塞尔曲线平滑插值；
- **排版与渲染**：KaTeX 引擎渲染中考标准 LaTeX 数学公式，Markdown 结构化卡片排版。

### 2. 后端技术栈
- **语言与服务**：Python 3 原生标准库（`ThreadingHTTPServer`、`urllib`、`subprocess` 等，无需繁重第三方 Web 框架）；
- **传输协议**：RESTful API + SSE (Server-Sent Events) 长连接流式传输，保证实时进度轮询与秒级响应；
- **跨平台系统交互**：原生调起 macOS Finder 与 Windows 资源管理器文件夹选择器，实现精准本地另存为与文件定位。

### 3. 接入的大模型与服务
| 环节 / 角色 | 采用的模型 / 服务 | 核心职责说明 |
| :--- | :--- | :--- |
| **阶段 1：Cleaner** | **合合信息 TextIn API** | 智能物理擦除试卷、习题册上的手写笔迹、草稿与干扰红线，输出纯净印刷级题目底图。 |
| **阶段 2：Transcriber** | **Gemini 3.8 Flash (High/Medium)** | 空间视觉大模型，提取标准 LaTeX 题干与无歧义的空间几何拓扑关系（严禁解题）。 |
| **阶段 3：Reasoner** | **DeepSeek Pro (`deepseek-v4-pro` / `deepseek-reasoner`)**<br/>或 **Gemini 3.8 Flash High / Gemini 4 Argon High** | 旗舰深度推理大模型，开启完整思维链（Thinking Process），进行几何逻辑证明，构建辅助线与 GeoGebra 指令。 |
| **极速直连解题** | **Gemini 3.8 Flash High / Gemini 4 Argon High** | 原生多模态看图解题分支（跳过清洗与转录），单次直接完成视觉识别与板书生成。 |

---

## 🏗️ 系统架构描述

系统采用“**输入标准化 ➔ 视觉转录 ➔ 深度推理 ➔ 交互渲染**”的插件化三阶段流水线设计：

```mermaid
flowchart TD
    User(["用户终端: PC / iPad / 手机"]) -->|上传 / 粘贴题目图片| Server["server.py (HTTP 静态服务与 API 路由)"]
    
    subgraph Pipeline ["三阶段模块化推演流水线 (plugins/pipeline.py)"]
        Server -->|调度流水线| Manager["PipelineManager"]
        
        Manager -->|阶段 1: 物理擦除手写草稿| Cleaner["TextIn Cleaner 插件<br/>(智能原图指纹缓存)"]
        Cleaner -->|生成纯净印刷底图| Transcriber["Gemini Transcriber 插件"]
        
        Manager -->|阶段 2: 空间题设转录| Transcriber
        Transcriber -->|提取无歧义几何拓扑描述| Reasoner["Reasoner 推理大模型插件"]
        
        Manager -->|阶段 3: 深度证明与绘图设计| Reasoner
        Reasoner -->|选项 A: DeepSeek-V4-Pro / Reasoner (流式思维链)| SolveData["生成微课 JSON 数据"]
        Reasoner -->|选项 B: Gemini 3.8 Flash / 4 Argon| SolveData
    end

    subgraph Frontend ["前端教学主舞台 (viewer.html)"]
        Server -->|推送推演日志与最终微课数据| ViewCtrl["微课交互控制器"]
        ViewCtrl -->|渲染动态画板| GGB["GeoGebra Web 引擎 (1:1 原图还原 / 辅助线动画)"]
        ViewCtrl -->|自由批注| Canvas["HTML5 Canvas 批注层 (多色画笔 / 撤销 / 清除)"]
        ViewCtrl -->|中考规范解析| KaTeX["KaTeX 公式排版 (题眼信号 / 思维路线 / 规范解答)"]
        ViewCtrl -->|离线分发| Export["💾 独立单文件 HTML 导出 (双击即开，零依赖)"]
    end
```

---

## 📂 项目文件结构

```text
math-tutor-workspace/
├── README.md               # 项目完整技术文档与使用说明
├── config.json             # 外部全局配置文件（服务端口、流水线插件指定、模型参数等）
├── config.py               # 全局配置与环境初始化模块（日志、.env 加载、路径常量）
├── .env.example            # 敏感凭证配置模板示例（TextIn 与 DeepSeek API Key）
├── .env                    # 本地私密凭证文件（已配置 .gitignore，严禁提交）
├── server.py               # 本地 HTTP 服务入口（API 路由、进度状态轮询、取消任务、跨平台保存）
├── solver.py               # 解题总控调度器（调度多阶段插件流水线、数据持久化）
├── prompts.py              # 提词与教学规则库（以 AGENTS.md 为单一信任源，微课 JSON Schema，消除重复注入）
├── utils.py                # 底层通用工具库（原生 sips 图片瘦身、HTTP 直连/代理工厂、局域网 IP 扫描、四级容错 JSON 自愈引擎）
├── viewer.html             # 前端单页 Web 应用（模块化架构：GeoGebra 引擎、Canvas 批注、推演看板、导出弹窗）
├── lesson.js               # 当前微课数据本地持久化文件（供前端初次打开秒级回显）
├── plugins/                # 模块化插件体系
│   ├── base.py             # 抽象插件基类（BaseCleaner, BaseTranscriber, BaseReasoner）
│   ├── registry.py         # 插件工厂与动态注册表
│   ├── pipeline.py         # 三阶段流水线调度器（原图指纹缓存、阶段进度打点、取消检测）
│   ├── cleaners/           # 阶段 1：底图清洗插件
│   │   └── textin_cleaner.py       # 合合信息 TextIn 去手写笔迹 API 实现
│   ├── transcribers/       # 阶段 2：题设空间转录插件
│   │   └── gemini_rpc_transcriber.py # 基于 Gemini 的纯命题转录实现
│   └── reasoners/          # 阶段 3：深度推理插件
│       ├── deepseek_reasoner.py    # DeepSeek OpenAI 兼容 SSE 流式推理实现
│       └── gemini_rpc_reasoner.py  # 基于 Gemini RPC 的几何证明与板书生成实现
├── uploads/                # 运行时上传的图片、清洗产物、转录文本与调试日志目录
└── .antigravity/
    └── AGENTS.md           # 题目解析与教学板书生成的顶级准则与提示词约束（实时热加载）
```

---

## 🚀 本地部署与运行步骤

### 1. 环境准备
- **操作系统**：macOS / Windows / Linux
- **Python 版本**：Python 3.8 及以上（**采用 Python 原生标准库实现，零额外 `pip` 依赖**）
- **浏览器**：Chrome / Edge / Safari 等现代浏览器
- **推理客户端（可选）**：若需使用 Gemini 系列模型，请确保本机已运行并登录 **Antigravity** 客户端。

### 2. 配置 API 凭证
在项目根目录复制模板并创建 `.env` 文件：

```bash
cp .env.example .env
```

使用文本编辑器打开 `.env` 文件，填入您的 API 凭据：

```ini
# 1. TextIn 试卷去手写笔迹 API 凭证 (https://www.textin.com)
TEXTIN_APP_ID=your_textin_app_id
TEXTIN_SECRET_CODE=your_textin_secret_code

# 2. DeepSeek 深度推理 API Key (https://platform.deepseek.com)
DEEPSEEK_API_KEY=sk-your_deepseek_api_key
```

### 3. 启动服务
在项目根目录下直接运行：

```bash
python3 server.py
```

终端将打印如下启动信息：

```text
============================================================
 🚀 数学几何微课全自动 Web App 服务已启动（支持局域网共享）！
 🔒 严格沙箱工作区: /Users/dean/Documents/math-tutor-workspace
 💻 本机访问地址:   http://127.0.0.1:8765/viewer.html
 📱 局域网访问地址: http://192.168.x.x:8765/viewer.html
============================================================
```

### 4. 访问系统
- **本机电脑访问**：在浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)
- **iPad / 手机 / 局域网设备**：连接同一 Wi-Fi，打开终端显示的局域网地址（如 `http://192.168.1.100:8765`）即可直接在平板上进行手写触控教学。

---

## 📖 使用指引与常见问题 (FAQ)

### 快速使用指引
1. **输入题目**：截取几何题图片后，切换到浏览器直接按 **`Cmd + V`**（Mac）或 **`Ctrl + V`**（Windows）粘贴，亦可拖拽图片进入上传区。
2. **选择模式与要求**：
   - 勾选 **【是否图转文字】** 启用完整三阶段高精度流水线；未勾选时若选择 Gemini 则走原生多模态直接解题；
   - 在 **【补充讲题要求】** 中输入个性化约束（如：*“第(2)问请用截长补短法解答”*）。
3. **推演过程**：点击 **【✨ 提交并自动生成微课】**，全屏推演看板实时展现通俗日志、三阶段状态灯与几何心语轮播，推演中可随时点击 **【🛑 终止推演】**。
4. **课堂教学**：点击步骤按钮逐步查看动态生长的辅助线，利用左侧 **`✏️` 画笔** 自由板书，展开查看解题思路与中考规范书写。
5. **保存微课**：点击顶部 **【💾 保存微课】** 弹出小窗口，自定义文件名并自由选择保存文件夹，导出独立单文件课件。

### 常见问题 (FAQ)

#### Q1: 提示「未检测到有效的 DeepSeek API Key」或 TextIn 报错？
- **解答**：请检查根目录下是否存在 `.env` 文件且填写了正确的密钥。修改 `.env` 文件后，保存并在终端重启 `python3 server.py` 即可。
