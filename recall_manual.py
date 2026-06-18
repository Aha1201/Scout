"""手动源：把从猎聘 / 脉脉 / BOSS直聘 等平台复制的候选人文本，用 LLM 解析成统一候选人格式，
走 Scout 同一套精排 + 报告。不爬虫、不调任何受限 API——纯你粘贴。

用法：把候选人信息（一个或多个）粘进一个 .txt 文件，多个候选人之间用一行 --- 分隔（可选），
然后： python run.py --role <岗位> --paste 那个文件.txt
"""
import hashlib
import os

from llm import structured

PARSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},        # 当前职位
                    "company": {"type": "string"},      # 当前公司
                    "location": {"type": "string"},
                    "years": {"type": "string"},        # 工作年限（文本，如 "8年"）
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "experience": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "company": {"type": "string"},
                            },
                            "required": ["title", "company"],
                        },
                    },
                    "summary": {"type": "string"},      # 一句话概况/亮点
                    "url": {"type": "string"},          # 简历链接（若有）
                },
                "required": ["name", "title", "company", "location", "years",
                             "skills", "experience", "summary", "url"],
            },
        }
    },
    "required": ["candidates"],
}

SYSTEM = """你是简历解析器。下面是从招聘平台（猎聘 / 脉脉 / BOSS直聘 等）复制的候选人信息，
格式可能杂乱、一段里可能有一个或多个候选人。把每个候选人抽取成结构化 JSON，放进 candidates 数组。
- 缺失的字段留空字符串或空数组，绝不编造。
- experience 抽取能看到的工作经历（公司 + 职位）。
- years 是总工作年限的文本。
只输出 JSON。"""


def parse(text):
    """解析粘贴文本 -> 统一候选人 dict 列表（source='manual'）。"""
    model = os.environ.get("PROFILE_MODEL", "deepseek-chat")
    out = structured(model, SYSTEM, text, PARSE_SCHEMA, max_tokens=4000)
    cands = []
    for c in out.get("candidates", []):
        name = (c.get("name") or "").strip()
        company = (c.get("company") or "").strip()
        if not name and not company:
            continue
        # 用 姓名|公司 生成稳定 id，便于去重（同一人重复粘贴只入库一次）
        sid = hashlib.md5(("%s|%s" % (name, company)).encode("utf-8")).hexdigest()[:12]
        cands.append({
            "source": "manual",
            "source_id": sid,
            "name": name or None,
            "email": None,
            "location": c.get("location"),
            "bio": c.get("summary") or c.get("title"),
            "company": company or None,
            "followers": None,
            "public_repos": None,
            "languages": c.get("skills") or [],
            "signals": {
                "title": c.get("title"),
                "years": c.get("years"),
                "skills": c.get("skills") or [],
                "experience": c.get("experience") or [],
            },
            "html_url": c.get("url"),
        })
    return cands
