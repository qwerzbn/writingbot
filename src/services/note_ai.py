# -*- coding: utf-8 -*-
"""
Note AI Service
================

AI-powered features for notes: polish, continue writing, summarize, suggest tags.
Uses the shared LLM client infrastructure.
"""

import logging
from typing import Generator

from src.services.llm import get_llm_client, get_llm_config

logger = logging.getLogger("note_ai")

# ---- Prompt templates ----

PROMPTS = {
    "polish": {
        "system": "你是一位学术写作润色专家。请优化用户提供的笔记内容，使其更加清晰、准确、学术化。保持 Markdown 格式。只输出润色后的内容，不要添加解释。",
        "user": "请润色以下笔记内容：\n\n{content}",
    },
    "continue": {
        "system": "你是一位学术写作助手。请根据已有内容，自然地继续扩展写作。保持相同的风格和 Markdown 格式。只输出续写的内容，不要重复已有内容。",
        "user": "请基于以下内容继续写作：\n\n{content}",
    },
    "summarize": {
        "system": "你是一位学术文档摘要专家。请为以下笔记生成一段简洁的摘要（3-5句话），概括核心观点。使用 Markdown 格式。",
        "user": "请为以下笔记生成摘要：\n\n{content}",
    },
    "suggest_tags": {
        "system": "你是一位学术标签推荐专家。请为以下笔记推荐3-5个相关标签。只输出标签，用逗号分隔，不要解释。",
        "user": "请为以下笔记推荐标签：\n\n标题：{title}\n\n内容：{content}",
    },
    "custom": {
        "system": "你是一位学术写作助手。请根据用户的指令处理笔记内容。保持 Markdown 格式。",
        "user": "笔记内容：\n\n{content}\n\n---\n用户指令：{instruction}",
    },
}


def stream_note_ai(
    action: str,
    content: str,
    title: str = "",
    instruction: str = "",
) -> Generator[str, None, None]:
    """Stream AI response for a note action.

    Args:
        action: One of 'polish', 'continue', 'summarize', 'suggest_tags', 'custom'
        content: The note content
        title: The note title (used for tag suggestion)
        instruction: Custom instruction (used for 'custom' action)

    Yields:
        Text chunks from the LLM
    """
    if action not in PROMPTS:
        raise ValueError(f"Unknown action: {action}")

    prompts = PROMPTS[action]
    system_msg = prompts["system"]
    user_msg = prompts["user"].format(
        content=content,
        title=title,
        instruction=instruction,
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    client = get_llm_client()
    config = get_llm_config()

    logger.info(f"note_ai stream: action={action}, model={config.model}")

    try:
        for chunk in client.chat_stream(
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
        ):
            yield chunk
    except Exception as e:
        logger.error(f"note_ai error: {e}")
        raise RuntimeError(f"AI 生成失败: {str(e)}") from e
