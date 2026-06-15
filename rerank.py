"""漏斗第 3 层（核心壁垒）：AI 精排。
把你脑子里"什么是好工程师"的标准固化成可批量跑的评分逻辑——这是传统关键词匹配做不到、别人也抄不走的部分。
改 RUBRIC 就是在调你的招聘品味。"""
import json
import os

from llm import structured

# ⬇⬇⬇ 这就是你的核心资产。每个岗位一份 RUBRIC（放在 roles/<岗位>/rubric.txt）。 ⬇⬇⬇
# 下面这份是默认模板（移动基础架构）；用 --role 时会被对应岗位的 rubric.txt 覆盖。
DEFAULT_RUBRIC = """你是招聘负责人的副手，按下面的标准给 "移动软件工程师 - 基础架构（Base 深圳）" 候选人打分。

硬要求 / 强加分：
- 强基础能力（fundamentals）是第一位：扎实的工程功底、系统/性能/构建/框架层面的实力 > 学历或 title。
- 移动基础架构背景最理想：Android（Kotlin/Java）或 iOS（Swift/Objective-C）皆可，做过 build system、
  framework、性能优化、SDK/工具链、CI、架构治理类项目 = 强加分。
- 业务端（纯做功能/UI）背景的候选人也可以考虑，但前提是看得出他"肯做、能做基础架构类项目"
  （比如自己写过工具/库、深挖过底层、有 infra 倾向的开源作品）。纯业务且无任何 infra 信号 = 减分。
- AI 是硬性项：必须能看出他真的在用 AI、对 AI 发展有想法——做过 AI 相关的业务或私人 project / 调研、
  仓库里有 LLM/agent/AI 工具类作品、或明显的快速学习能力。完全没有 AI 痕迹 = 明显减分。
- 学习能力强、技术广度好、活跃 = 加分；近一两年无任何活跃 commit = 减分。
- 地点（岗位 Base 深圳，这是硬约束）：
  · geo_class=cn（国内/大湾区/港澳台）= 正常评分；
  · geo_class=unknown（地点未填）= 正常评分，但在 red_flags 注明"地点待确认"；
  · geo_class=overseas（明显海外）且看不出 relocate 意愿 = 封顶 60 分（最多"观望"），
    哪怕技术再强也不给"值得联系"——因为来不了深圳等于用不了。

评分区间：
  80-100 = 值得联系（强基础 + infra 背景或明确 infra 倾向 + 有 AI 实践）
  50-79  = 观望（基础不错但 infra 或 AI 信号不全，需进一步看）
  0-49   = 跳过（基础弱、纯业务无 infra 意愿、或信息太弱）

evidence 要引用候选人的具体信号（命中的仓库、语言、贡献数、bio 里的线索）。
red_flags 写清楚减分点（如无 AI 痕迹、纯业务、不活跃）。
outreach_hook 写一句可直接发出去的开场白，必须引用他的具体作品，不要套话。"""

# 当前生效的 RUBRIC，默认用模板；--role 时由 run.py 用对应 rubric.txt 覆盖。
ACTIVE_RUBRIC = DEFAULT_RUBRIC


def set_rubric(text):
    global ACTIVE_RUBRIC
    ACTIVE_RUBRIC = text


SCORE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {"type": "integer"},
        "verdict": {"type": "string", "enum": ["值得联系", "观望", "跳过"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "outreach_hook": {"type": "string"},
    },
    "required": ["score", "verdict", "evidence", "red_flags", "outreach_hook"],
}


def _candidate_brief(cand):
    """把候选人资料压成一段给模型看的文本。"""
    langs = cand.get("languages")
    signals = cand.get("signals")
    if isinstance(langs, str):
        langs = json.loads(langs or "[]")
    if isinstance(signals, str):
        signals = json.loads(signals or "{}")
    brief = {
        "source": cand.get("source"),          # github / linkedin
        "id": cand.get("source_id"),
        "name": cand.get("name"),
        "bio": cand.get("bio"),
        "company": cand.get("company"),
        "location": cand.get("location"),
        "followers": cand.get("followers"),
        "url": cand.get("html_url"),
    }
    if cand.get("source") == "linkedin":
        # LinkedIn：履历 + 公司归属是关键证据
        brief.update({
            "current_title": signals.get("title"),
            "headline": signals.get("headline"),
            "experience": signals.get("experience", []),
            "hit_target_companies": signals.get("hit_target_companies", []),
        })
    else:
        # GitHub：top_repos 判断技术方向 / 领域信号
        brief.update({
            "languages": langs,
            "public_repos": cand.get("public_repos"),
            "geo_class": signals.get("geo_class"),
            "matched_via": {k: signals.get(k) for k in ("matched_repo", "repo_stars", "contributions")},
            "top_repos": signals.get("top_repos", []),
        })
    return json.dumps(brief, ensure_ascii=False, indent=2)


def _primary_language(signals):
    """GitHub 候选人 top_repos 里出现最多的语言。"""
    from collections import Counter
    repos = signals.get("top_repos") or []
    c = Counter(r.get("lang") for r in repos if r.get("lang"))
    return c.most_common(1)[0][0] if c else None


def _language_gate(profile, cand, result):
    """代码层硬门槛（不靠模型自觉）：GitHub 候选人主力语言若不在岗位要求语言里，封顶 40 分。
    只在画像声明了 github.languages 时生效；linkedin 候选人不适用（无 top_repos）。"""
    if cand.get("source") != "github":
        return result
    accepted = [l.lower() for l in ((profile.get("github") or {}).get("languages") or [])]
    if not accepted:
        return result
    signals = cand.get("signals")
    if isinstance(signals, str):
        signals = json.loads(signals or "{}")
    primary = _primary_language(signals or {})
    if primary and primary.lower() not in accepted and (result.get("score") or 0) > 40:
        result = dict(result)
        result["score"] = 40
        result["verdict"] = "跳过"
        rf = list(result.get("red_flags") or [])
        rf.insert(0, "主力语言 %s 非岗位要求语言，硬门槛判跳过" % primary)
        result["red_flags"] = rf
    return result


def score_candidate(profile, cand):
    model = os.environ.get("RERANK_MODEL", "deepseek-chat")
    system = ACTIVE_RUBRIC + "\n\n本次招聘画像：\n" + json.dumps(profile, ensure_ascii=False)
    user = "候选人资料：\n" + _candidate_brief(cand)
    result = structured(model, system, user, SCORE_SCHEMA, max_tokens=1500)
    return _language_gate(profile, cand, result)
