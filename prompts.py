#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初中几何交互微课 - 提词与教学规则模块 (prompts.py)
=================================================
功能说明：
1. 抽离并集中管理面向高阶大模型的系统提词、结构化输出约束与中考教学规范；
2. 维护标准的微课输出 JSON 模式骨架（JSON_SCHEMA_TEMPLATE）；
3. 读取并整合智能体规范文档（.antigravity/AGENTS.md，作为单一信任源）；
4. 提供阶段 2（Gemini 转录）提示词构建函数 `build_transcription_prompt`；
5. 提供阶段 3（DeepSeek/Gemini 推理）提示词构建函数 `build_reasoner_prompt`；
6. 保留向后兼容的单阶段 Prompt 构造函数 `build_strict_json_prompt`。
"""

from config import AGENTS_MD_PATH

# ==========================================
# 1. 强制 JSON 输出结构契约模板
# ==========================================
JSON_SCHEMA_TEMPLATE: str = """{
  "viewConfig": {
    "hasAxes": true,
    "bounds": { "xmin": -8.5, "xmax": 9.5, "ymin": -7.5, "ymax": 4.5 }
  },
  "encouragement": "结合本题核心几何模型与解题心得的一句精炼、温暖或幽默的数学双关鼓励寄语（25字以内，如：心态转个弯，就像补齐了一线三垂直，难题豁然开朗）",
  "questions": [
    {
      "title": "第(1)问：...",
      "thoughtAnalysis": "* **【💡 题眼信号识别（破题开关）】**：明确指出题干哪句原话是关键开关，看到该条件第一反应联想到什么几何定理/模型；\\n* **【🧭 人类解题思维路线】**：按照人类探索思维（要求什么 -> 缺什么 -> 由题眼搭桥连通已知 -> 逻辑闭环）引导用户一步步破局，转化为人类可复用的思维方式，不罗列机械算数细节。",
      "steps": [
        {
          "name": "步骤短标题（如：构造一线三垂直全等 △BCD ≌ △EMB）",
          "modelName": "本步核心模型或思路（如确实用到一线三垂直/8字全等/倍长中线/截长补短/手拉手等经典模型必须明确写出模型名；若无辅助线常规推导则写方法概述）",
          "explanation": "【💡 辅助线是怎么想到的？】观察图形发现 [现有几何特征/残缺信号，如已有两个直角在一线上形成一线两垂直]，为了 [连接什么已知条件与目标]，因此想到过点 X 作 YY（补全第三个垂直）。\\n因为 [条件1]，所以 [结论1]。\\n因为 [条件2]，所以 [结论2]。\\n结合以上推导，==所以 [本步最终证明或达成的核心结论]==",
          "ggbCommands": [
            "O = (0, 0)",
            "A = (0, 3)",
            "segOA = Segment(O, A)",
            "SetColor(segOA, \\"#38BDF8\\")"
          ]
        }
      ],
      "solutionMarkdown": "#### 【中考规范书写过程】\\n解：\\n1. ...（纯粹的中考规范书写步骤，支持标准 LaTeX 公式如 $\\\\triangle AOB \\\\cong \\\\triangle CFA$）"
    }
  ]
}"""

# 兜底规范（当 .antigravity/AGENTS.md 不存在时作为后备单一信任源）
DEFAULT_TEACHING_RULES: str = """【GeoGebra 指令与讲题引导核心铁律】：
1. 视觉方位 1:1 对齐原图（严禁旋转或扭曲原图形状）。
2. 第 1 步（steps[0]）必须是纯粹的原题图，严禁画出任何辅助线或辅助点。
3. 凡作辅助线必须以“【💡 辅助线是怎么想到的？】”开头，讲透动机并精准关联模型套路。
4. 分步排版（一行一个因果推导，换行符 \\n 分隔），末行必须用 ==...== 高亮核心结论。
5. 角度一律隐藏度数文字标签；按逆时针排列防反角（优角）；垂足直角标记高精度坐标防变形。
6. 原题已知的相等线段（SetDecoration 刻度线）与相等角（同色圆弧）必须在 Step 1 显性化标出。
7. 严禁角命名同义反复（如禁止写 ∠B = ∠ABC = 15°），全篇除题干特殊要求外统一三字母角记法。"""


def get_agents_spec() -> str:
    """
    读取并返回工作区下的 .antigravity/AGENTS.md 规范文本；若不存在则使用兜底规则。
    """
    if AGENTS_MD_PATH.exists():
        try:
            content = AGENTS_MD_PATH.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass
    return DEFAULT_TEACHING_RULES


# ==========================================
# 阶段 2: 空间视觉与题设转录 Prompt (Gemini)
# ==========================================
def build_transcription_prompt() -> str:
    """
    构造供视觉大模型（Gemini）使用的题设与图形空间拓扑转录提示词。
    严格要求：只负责精准录入题干与识别图中几何拓扑，严禁解题！
    """
    return """你现在的角色是【空间视觉与题设转录员】。
请仔细观察上传的这张纯净几何题目底图，执行精准的数字化转录工作。

【重要指令】：
- 请直接输出转录文本，不要调用任何外部工具！

【核心职责】：
1. **完整提取题干文字与所有小问**：
   - 将所有数学符号、字母、公式转录为标准 LaTeX 格式（如 $\\triangle ABC$, $\\angle BAC = 90^\\circ$, $AB = AC$, $BD \\perp AE$ 于点 $D$ 等）。
   - 保留原题所有小问的完整编号与求证/求解目标。
2. **精准识别几何图形空间拓扑关系与点位朝向**：
   - 点的相对空间方位（如：点 A 在最上方，BC 是底边水平放置，点 D 在线段 BC 上等）；
   - 线段关系：共线、相交、延长线、平行、垂直；
   - 图中已标注的记号：图中的直角方框（如 $\\angle BDA = 90^\\circ$）、等长刻度、特殊角等。
   - 形状特征：如等腰直角三角形、正方形、矩形等。

【🚫 严禁事项（极其重要）】：
- **严禁解题**！严禁输出任何证明过程、辅助线构造思路或解题步骤！
- **不进行任何数学推导**，你的唯一任务是输出一份“100% 忠实还原原图与题干、毫无歧义的几何命题纯文本描述”。

请直接输出整理好的结构化命题纯文本（并在全文最后一行附上结束标记 `===END_OF_TRANSCRIPTION===`）：
1. 【原题题干与小问】
2. 【图形拓扑与点位空间分布】
===END_OF_TRANSCRIPTION===
"""


# ==========================================
# 阶段 3: 深度证明与绘图架构 Prompt (DeepSeek / Gemini)
# ==========================================
def build_reasoner_prompt(problem_description: str, extra_note: str = "") -> str:
    """
    构造供深度推理大模型使用的命题求解与 GeoGebra 板书架构提示词。
    纯文本输入，输出符合 LESSON_DATA 契约的严格 JSON 字符串。
    """
    agents_spec = get_agents_spec()
    note_content = extra_note.strip() if extra_note else "无，请完整覆盖题目所有小问，1:1还原原图朝向，凡有辅助线必须先讲清楚是怎么想到的"

    return f"""你现在是《初中几何交互微课生成器 (基于 GeoGebra 引擎)》的【深度证明与绘图架构师】。
以下是经过转录的高精度中考几何命题描述与空间拓扑关系：

==================== 几何命题开始 ====================
{problem_description}
==================== 几何命题结束 ====================

【用户最高优先级补充要求（全篇所有字段——含 thoughtAnalysis、explanation、solutionMarkdown 都必须遵守）】：
{note_content}

{agents_spec}

【输出 JSON 结构强制要求】：
请直接输出一个合法的 JSON 对象（不要加任何多余的前缀或后缀解释，直接输出标准 JSON），结构必须严格如下：
{JSON_SCHEMA_TEMPLATE}

【极其重要指令（必须严格遵守）】：
1. **先在草稿中彻底推导数学逻辑与精确 GeoGebra 解析坐标**：
   - 必须确保图形朝向与原图 1:1 视觉一致、点位逆时针角排列正确、直角/等长刻度（SetDecoration）与辅助线指令计算无误；
2. **推导与验算完成后，立即完整输出最终 JSON**：
   - 严禁在思考阶段无限纠结转义符语法，推导闭环后必须立即启动 JSON 格式输出；
   - 严禁在输出中使用省略号 `...` 或 `[ ... ]`！所有 steps、ggbCommands、explanation 和 solutionMarkdown 必须写出真实完整的几何证明与指令；
3. 不要输出任何代码外的解释文本，第一行必须是 `{{`，最后一行必须是 `}}`。
4. 在闭合最后一个 `}}` 之后，请在下一行单独输出结束标记：`===END_OF_LESSON===`。
"""


def build_strict_json_prompt(extra_note: str = "") -> str:
    """
    向前兼容的单阶段 Prompt 构造函数（直接看图解题模式）。
    """
    agents_spec = get_agents_spec()
    note_content = extra_note.strip() if extra_note else "无，请完整覆盖题目所有小问，1:1还原原图朝向，凡有辅助线必须先讲清楚是怎么想到的"

    return f"""你现在是《初中几何交互微课生成器 (基于 GeoGebra 引擎)》。
请仔细识别我上传的几何题目图片，严格遵循以下教学与绘图规范，一次性生成包含题目所有小问的微课 JSON 数据。

【重要指令：请勿调用任何工具（Do NOT call any tools）！直接输出纯 JSON 对象！】

【用户最高优先级补充要求（与下文规范冲突时以此为准，全篇所有字段——含 thoughtAnalysis、explanation、solutionMarkdown——都必须遵守）】：
{note_content}

{agents_spec}

【输出 JSON 结构强制要求】：
请直接输出一个合法的 JSON 对象（不要加任何多余的前后缀解释，直接输出 JSON），结构必须严格如下：
{JSON_SCHEMA_TEMPLATE}

【极其重要指令（必须严格遵守）】：
1. **先在草稿中彻底推导数学逻辑与精确 GeoGebra 解析坐标**：
   - 必须确保图形朝向与原图 1:1 视觉一致、点位逆时针角排列正确、直角/等长刻度（SetDecoration）与辅助线指令计算无误；
2. **推导与验算完成后，立即完整输出最终 JSON**：
   - 严禁在思考阶段无限纠结转义符语法，推导闭环后必须立即启动 JSON 格式输出；
   - 严禁在输出中使用省略号 `...` 或 `[ ... ]`！所有 steps、ggbCommands、explanation 和 solutionMarkdown 必须写出真实完整的几何证明与指令；
3. 不要输出任何代码外的解释文本，第一行必须是 `{{`，最后一行必须是 `}}`。
4. 在闭合最后一个 `}}` 之后，请在下一行单独输出结束标记：`===END_OF_LESSON===`。
"""
