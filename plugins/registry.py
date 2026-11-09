#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插件注册表与动态加载工厂 (plugins/registry.py)
==============================================
提供三大流水线阶段插件的动态注册与加载能力：
- 用户新增模型只需编写类似 plugins/reasoners/x_big_model.py 的文件，
  并在其中通过 @register_cleaner / @register_transcriber / @register_reasoner 注册，
  或在 config.json 中直接通过 "module.ClassName" 路径进行反射加载，无需改动核心架构代码！
"""

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any, Dict, Type
from plugins.base import BaseCleaner, BaseReasoner, BaseTranscriber

CLEANER_REGISTRY: Dict[str, Type[BaseCleaner]] = {}
TRANSCRIBER_REGISTRY: Dict[str, Type[BaseTranscriber]] = {}
REASONER_REGISTRY: Dict[str, Type[BaseReasoner]] = {}


def register_cleaner(name: str):
    """装饰器：注册去笔迹清洗器插件"""
    def decorator(cls: Type[BaseCleaner]):
        CLEANER_REGISTRY[name.lower()] = cls
        return cls
    return decorator


def register_transcriber(name: str):
    """装饰器：注册题设转录员插件"""
    def decorator(cls: Type[BaseTranscriber]):
        TRANSCRIBER_REGISTRY[name.lower()] = cls
        return cls
    return decorator


def register_reasoner(name: str):
    """装饰器：注册证明与绘图推理插件"""
    def decorator(cls: Type[BaseReasoner]):
        REASONER_REGISTRY[name.lower()] = cls
        return cls
    return decorator


def _load_class_from_path(class_path: str) -> Type[Any]:
    """
    通过 'module.submodule.ClassName' 形式动态加载类。
    例如 'plugins.reasoners.x_big_model.XBigModelReasoner'
    """
    if ":" in class_path:
        module_name, class_name = class_path.split(":", 1)
    elif "." in class_path:
        module_name, class_name = class_path.rsplit(".", 1)
    else:
        raise ValueError(f"无法识别的类路径格式: {class_path}")

    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name, None)
    if cls is None:
        raise AttributeError(f"模块 '{module_name}' 中未找到类 '{class_name}'")
    return cls


def create_cleaner(provider_name: str, config: Dict[str, Any]) -> BaseCleaner:
    """
    根据配置创建 BaseCleaner 实例。
    """
    # 1. 尝试从已知别名注册表中匹配
    key = provider_name.lower().strip()
    if key in CLEANER_REGISTRY:
        return CLEANER_REGISTRY[key](config)

    # 2. 如果是点分路径，尝试动态反射加载
    if "." in provider_name:
        cls = _load_class_from_path(provider_name)
        if issubclass(cls, BaseCleaner):
            return cls(config)

    raise ValueError(f"未知的 Cleaner 提供商或类: '{provider_name}'。当前可用: {list(CLEANER_REGISTRY.keys())}")


def create_transcriber(provider_name: str, config: Dict[str, Any]) -> BaseTranscriber:
    """
    根据配置创建 BaseTranscriber 实例。
    """
    key = provider_name.lower().strip()
    if key in TRANSCRIBER_REGISTRY:
        return TRANSCRIBER_REGISTRY[key](config)

    if "." in provider_name:
        cls = _load_class_from_path(provider_name)
        if issubclass(cls, BaseTranscriber):
            return cls(config)

    raise ValueError(f"未知的 Transcriber 提供商或类: '{provider_name}'。当前可用: {list(TRANSCRIBER_REGISTRY.keys())}")


def create_reasoner(provider_name: str, config: Dict[str, Any]) -> BaseReasoner:
    """
    根据配置创建 BaseReasoner 实例。
    """
    key = provider_name.lower().strip()
    if key in REASONER_REGISTRY:
        return REASONER_REGISTRY[key](config)

    if "." in provider_name:
        cls = _load_class_from_path(provider_name)
        if issubclass(cls, BaseReasoner):
            return cls(config)

    raise ValueError(f"未知的 Reasoner 提供商或类: '{provider_name}'。当前可用: {list(REASONER_REGISTRY.keys())}")


# 自动加载并注册默认内置插件
def _register_builtin_plugins():
    from plugins.cleaners.textin_cleaner import TextInCleaner
    register_cleaner("textin")(TextInCleaner)

    from plugins.transcribers.gemini_rpc_transcriber import GeminiRpcTranscriber
    register_transcriber("gemini_rpc")(GeminiRpcTranscriber)
    register_transcriber("gemini")(GeminiRpcTranscriber)

    from plugins.reasoners.deepseek_reasoner import DeepSeekReasoner
    register_reasoner("deepseek")(DeepSeekReasoner)

    from plugins.reasoners.gemini_rpc_reasoner import GeminiRpcReasoner
    register_reasoner("gemini_rpc")(GeminiRpcReasoner)
    register_reasoner("gemini")(GeminiRpcReasoner)


_register_builtin_plugins()
