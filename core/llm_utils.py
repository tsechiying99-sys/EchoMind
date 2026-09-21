"""LLM response helpers shared by Anthropic-compatible providers."""
from typing import Any, Iterable, List
import json
from typing import Any

def extract_text_content(content: Iterable[Any]) -> str:
    """将Anthropic的回复内容转换为text块-Return text blocks from Anthropic-style response content."""
    texts: List[str] = []
    for block in content or []:
        if isinstance(block, str):
            texts.append(block)
            continue

        block_type = getattr(block, "type", None)
        text = getattr(block, "text", None)
        if isinstance(block, dict):
            block_type = block.get("type", block_type)
            text = block.get("text", text)

        if isinstance(text, str) and (block_type in (None, "text")):
            texts.append(text)

    return "\n".join(t for t in texts if t)

def extract_json_value(text: str, expected_type: type = dict) -> Any:
    """从模型输出中提取第一个合法 JSON 对象或数组。"""
    if not text or not text.strip():
        raise ValueError("LLM 返回了空内容")

    decoder = json.JSONDecoder()
    starts = [
        index for index, char in enumerate(text)
        if char in ("{", "[")
    ]

    for start in starts:
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue

        if isinstance(value, expected_type):
            return value

    preview = text[:200].replace("\n", "\\n")
    raise ValueError(f"未找到合法 JSON，模型输出开头: {preview}")
