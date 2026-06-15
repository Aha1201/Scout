"""漏斗第 2 层 · 数据源二：LinkedIn（经 CoreSignal Multi-source Employee API）。
适合 GitHub 盲区的岗位——交易所/金融后端这类闭源经历，LinkedIn 的履历+公司信号能直接命中。

流程：用画像的 linkedin 参数构造 Elasticsearch DSL -> search 拿到员工 ID 列表 -> 逐个 collect 详情
      -> 映射成与 GitHub 同样格式的候选人（source='linkedin'），下游 DB/精排/报告原样复用。

字段映射已对照 CoreSignal 真实返回 schema 校准（2026-06）。
"""
import os

import requests

BASE = os.environ.get("CORESIGNAL_BASE", "https://api.coresignal.com/cdapi")
SEARCH_PATH = "/v2/employee_multi_source/search/es_dsl"
COLLECT_PATH = "/v2/employee_multi_source/collect/%s"


def _headers():
    key = os.environ.get("CORESIGNAL_API_KEY")
    if not key:
        raise RuntimeError("缺少 CORESIGNAL_API_KEY，请在 .env 填入 CoreSignal 的 API key")
    return {"apikey": key, "Content-Type": "application/json"}


def _or(terms, n):
    return " OR ".join('"%s"' % t for t in (terms or [])[:n])


def _company_q(comp):
    # 公司在 experience[] 数组里，必须用 nested（扁平 query_string 搜 experience.company_name 恒为 0）
    return {"nested": {"path": "experience",
                       "query": {"query_string": {"query": comp, "fields": ["experience.company_name"]}}}}


def _company_dsl(li):
    """第一段（最高价值）：在目标公司（交易所/券商）干过 + 像工程师的人。"""
    companies = _or(li.get("companies"), 12)
    if not companies:
        return None
    return {"query": {"bool": {"must": [
        _company_q(companies),
        {"query_string": {"query": "Java OR Backend OR Engineer OR Developer OR 工程师 OR 研发",
                          "fields": ["active_experience_title", "headline", "inferred_skills"]}},
    ]}}}


def _domain_dsl(li):
    """第二段（填充）：职位匹配 + 金融/交易领域词。"""
    titles = _or(li.get("titles"), 6)
    keywords = _or(li.get("keywords"), 8)
    locations = _or(li.get("locations"), 6)

    must = []
    if titles:
        must.append({"query_string": {"query": titles, "default_operator": "OR",
                                       "fields": ["active_experience_title", "headline"]}})
    if keywords:
        must.append({"query_string": {"query": keywords,
                                       "fields": ["inferred_skills", "summary", "headline",
                                                  "active_experience_description"]}})
    should = []
    if locations:
        should.append({"query_string": {"query": locations, "fields": ["location_full", "location_country"]}})
    bool_q = {"must": must or [{"match_all": {}}]}
    if should:
        bool_q["should"] = should
    return {"query": {"bool": bool_q}}


def _search(body):
    r = requests.post(BASE + SEARCH_PATH, headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    ids = r.json()
    if isinstance(ids, dict):
        ids = ids.get("data") or ids.get("hits") or []
    return ids if isinstance(ids, list) else []


def _active_company(exp):
    for e in exp:
        if e.get("active_experience") == 1 and e.get("company_name"):
            return e["company_name"]
    return exp[0].get("company_name") if exp else None


def _to_candidate(rec, li):
    exp = rec.get("experience") or []
    title = rec.get("active_experience_title") or (exp[0].get("position_title") if exp else None)
    company = _active_company(exp)

    companies_seen = [(e.get("company_name") or "") for e in exp]
    hit_companies = [c for c in (li.get("companies") or [])
                     if any(c.lower() in cs.lower() for cs in companies_seen)]

    return {
        "source": "linkedin",
        "source_id": str(rec.get("id")),
        "name": rec.get("full_name"),
        "email": rec.get("primary_professional_email"),
        "location": rec.get("location_full") or rec.get("location_country"),
        "bio": rec.get("headline") or rec.get("summary"),
        "company": company,
        "followers": rec.get("connections_count") or rec.get("followers_count"),
        "public_repos": rec.get("github_contributions_count"),
        "languages": (rec.get("inferred_skills") or [])[:8],
        "signals": {
            "title": title,
            "headline": rec.get("headline"),
            "skills": (rec.get("inferred_skills") or [])[:12],
            "experience": [{"title": e.get("position_title"), "company": e.get("company_name"),
                            "from": e.get("date_from"), "to": e.get("date_to")} for e in exp[:6]],
            "hit_target_companies": hit_companies,
            "github_url": rec.get("github_url"),  # CoreSignal 交叉到的 GitHub（若有）
            "total_experience_months": rec.get("total_experience_duration_months"),
        },
        "html_url": rec.get("linkedin_url"),
    }


def recall(profile, max_candidates=60):
    li = profile.get("linkedin") or {}

    # 两段式：先抓目标公司（交易所/券商）校友——最高价值、GitHub 找不到；再用领域词填满。
    company_ids = _search(_company_dsl(li)) if _company_dsl(li) else []
    domain_ids = _search(_domain_dsl(li))
    company_quota = min(len(company_ids), int(max_candidates * 0.6))  # 至少给目标公司留 60% 名额
    print("LinkedIn：目标公司命中 %d，领域命中 %d；优先取公司 %d，其余用领域填充"
          % (len(company_ids), len(domain_ids), company_quota))

    ordered = company_ids[:company_quota]
    seen = set(ordered)
    for eid in domain_ids:
        if len(ordered) >= max_candidates:
            break
        if eid not in seen:
            seen.add(eid)
            ordered.append(eid)

    for eid in ordered[:max_candidates]:
        try:
            cr = requests.get(BASE + (COLLECT_PATH % eid), headers=_headers(), timeout=30)
            cr.raise_for_status()
            rec = cr.json()
        except requests.exceptions.RequestException as e:
            print("  ! 跳过 id=%s（取详情失败：%s）" % (eid, e))
            continue
        cand = _to_candidate(rec, li)
        print("  + %s | %s @ %s | %s"
              % (cand["name"] or cand["source_id"], cand["signals"].get("title") or "?",
                 cand.get("company") or "?", cand.get("location") or "?"))
        yield cand
