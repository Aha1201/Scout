"""LLM 调用封装：DeepSeek（OpenAI 兼容接口），用 JSON 模式拿干净结构化输出。

DeepSeek 不支持 Anthropic 那种 json_schema 强约束，但支持 response_format={"type":"json_object"}。
做法：把目标 schema 写进 system 提示里要求模型遵守，再用 json.loads 解析。"""
import json
import os

from openai import OpenAI

_client = None


def client():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    return _client


def structured(model, system, user, schema, max_tokens=2000):
    """调一次模型，要求按 schema 返回 JSON，解析成 dict。"""
    sys_with_schema = (
        system
        + "\n\n只返回一个 JSON 对象，严格符合下面的 JSON schema（不要包含多余文字、不要 markdown 代码块）：\n"
        + json.dumps(schema, ensure_ascii=False)
    )
    resp = client().chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": sys_with_schema},
            {"role": "user", "content": user},
        ],
    )
    return json.loads(resp.choices[0].message.content)
