"""漏斗第 1 层：把口述/JD 转成机器能用的召回画像。"""
import os

from llm import structured

PROFILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "role": {"type": "string"},
        "must_have": {"type": "array", "items": {"type": "string"}},
        "nice_to_have": {"type": "array", "items": {"type": "string"}},
        "github": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                # GitHub 仓库搜索用：语言 + 关键词
                "languages": {"type": "array", "items": {"type": "string"}},
                "repo_keywords": {"type": "array", "items": {"type": "string"}},
                "min_followers": {"type": "integer"},
            },
            "required": ["languages", "repo_keywords", "min_followers"],
        },
        "linkedin": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                # LinkedIn 员工搜索用
                "titles": {"type": "array", "items": {"type": "string"}},      # 目标职位名
                "companies": {"type": "array", "items": {"type": "string"}},   # 目标/加分公司
                "keywords": {"type": "array", "items": {"type": "string"}},    # 领域/技能词
                "locations": {"type": "array", "items": {"type": "string"}},   # 地点
            },
            "required": ["titles", "companies", "keywords", "locations"],
        },
        "exclude": {"type": "array", "items": {"type": "string"}},
        "geo": {"type": "array", "items": {"type": "string"}},
        "seniority": {"type": "string"},
    },
    "required": ["role", "must_have", "nice_to_have", "github", "linkedin", "exclude", "geo", "seniority"],
}

SYSTEM = """你是技术招聘需求分析师。把招聘需求转成 JSON 召回画像，同时服务 GitHub 和 LinkedIn 两个召回源。

GitHub（按代码找人）：
- github.languages 用 GitHub 能识别的语言名（Kotlin/Swift/Java/Go/Solidity...），最核心的放前面。
- github.repo_keywords 是相关仓库名/描述里会出现的词（android, gradle, trading, margin, risk...）。
- github.min_followers 过滤下限（10 起步，可调高）。

LinkedIn（按履历/公司找人，适合闭源领域如交易所/金融后端）：
- linkedin.titles 目标职位名（如 "Java Engineer","交易系统工程师","Risk Engineer","Backend Engineer"）。
- linkedin.companies 目标或加分公司（如 Binance, OKX, Bybit, Futu 富途, Tiger 老虎, IBKR）。
- linkedin.keywords 领域/技能词（如 margin, risk engine, derivatives, matching engine, Spring Boot, Kafka）。
- linkedin.locations 地点（从 geo 推断）。

geo 反映地点要求；exclude 反映明确不要的方向。只输出 JSON。"""


def jd_to_profile(jd_text):
    model = os.environ.get("PROFILE_MODEL", "deepseek-chat")
    return structured(model, SYSTEM, jd_text, PROFILE_SCHEMA, max_tokens=1500)
