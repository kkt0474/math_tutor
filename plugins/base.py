#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插件基类与数据结构定义 (plugins/base.py)
======================================
定义几何微课生成流水线（Pipeline）的三大核心阶段接口：
1. BaseCleaner: 底图物理清洗员（消除笔记与涂鸦，输出清晰印刷底图）
2. BaseTranscriber: 空间视觉与题设转录员（识别题干文字、公式 LaTeX 及几何拓扑，严禁解题）
3. BaseReasoner: 深度证明与绘图架构师（接收纯文本命题，输出思考链、GeoGebra 指令及中考规范步骤）
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseCleaner(ABC):
    """
    底图物理清洗员基类。
    职责：
    - 消除试卷上的手写字、铅笔草稿与红笔批改
    - 抹除学生自画的错误辅助线
    - 输出高对比度、黑白分明的几何印刷底图
    严禁：
    - 不负责提取文字语义
    - 不负责解析几何空间逻辑
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def validate_credentials(self) -> None:
        """
        验证所需凭据是否完整配置。若不完整必须直接抛出异常并在程序启动时提示。
        """
        pass

    @abstractmethod
    def clean_image(self, image_bytes: bytes, mime_type: str = "image/png") -> bytes:
        """
        处理原始图片，擦除笔迹后返回干净的图片二进制数据。

        Args:
            image_bytes (bytes): 用户上传的原始图片二进制。
            mime_type (str): 图片的 MIME 类型。

        Returns:
            bytes: 去除手写笔迹后的纯净图片二进制数据。
        """
        pass


class BaseTranscriber(ABC):
    """
    空间视觉与题设转录员基类。
    职责：
    - 提取题干中所有文字与公式（转为标准 LaTeX）
    - 精准识别图中的点线拓扑（延长线、相交、共线、垂直标、等长线等）
    - 输出毫无歧义的纯文本几何命题描述
    严禁：
    - 严禁解题
    - 不输出证明步骤或思路推导
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def validate_credentials(self) -> None:
        """
        验证所需凭据或环境连接是否就绪。
        """
        pass

    @abstractmethod
    def transcribe(
        self,
        clean_image_bytes: bytes,
        mime_type: str = "image/png",
        model_override: Optional[str] = None,
    ) -> str:
        """
        分析干净的底图，转录为结构化的纯文本几何命题描述（含 LaTeX）。

        Args:
            clean_image_bytes (bytes): 经过清洗后的图片二进制。
            mime_type (str): 图片 MIME 类型。
            model_override (str, optional): 转录所使用的特定模型标识。

        Returns:
            str: 几何命题描述纯文本。
        """
        pass


class BaseReasoner(ABC):
    """
    深度证明与绘图架构师基类。
    职责：
    - 支持纯文本或多模态图像输入，开启深度思维链（Thinking）
    - 识别中考几何模型（旋转、隐圆、一线三垂直、费马点等）
    - 构造核心辅助线并输出无跳步证明
    - 编写对应的标准 GeoGebra 辅助线绘制指令
    - 输出严格符合前端契约的 JSON 数据结构
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def validate_credentials(self) -> None:
        """
        验证 API Key、Base URL 或 RPC 连接等配置。
        """
        pass

    @abstractmethod
    def solve(
        self,
        problem_description: str = "",
        extra_note: str = "",
        model_override: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/png",
    ) -> Dict[str, Any]:
        """
        接收命题纯文本或多模态图像，进行深度推演并返回符合 LESSON_DATA 契约的字典对象。

        Args:
            problem_description (str): 阶段 2 转录出的纯文本几何命题描述（若单阶段直接识图则可为空）。
            extra_note (str): 用户补充的讲题要求（如“禁止使用三角函数”）。
            model_override (str, optional): 前端选定的特定子模型名称。
            image_bytes (bytes, optional): 原始图片二进制数据（单阶段直接识图解题模式）。
            mime_type (str): 图片 MIME 类型。

        Returns:
            Dict[str, Any]: 包含 viewConfig, questions 等规范字段的字典。
        """
        pass
