"""漏斗第 2 层（v1 唯一数据源）：GitHub 召回。
思路：按 画像的语言+关键词 搜到相关仓库 -> 扒贡献者 -> 拉个人资料(含 top 仓库) -> 按 followers 过滤。

两个关键设计：
1. 多仓库轮询(round-robin)：不把一个仓库扒满，而是在所有命中仓库间轮流取人，保证候选人来源多样。
2. 每个候选人额外拉他的 top 仓库（名字/描述/语言/stars）——这样精排才能判断
   "他做过 AI 项目吗""是 infra 倾向还是纯业务"，而不是只看 bio 瞎猜。"""
import os
import time

import requests

API = "https://api.github.com"

# 国内 / 大湾区相关地点关键词（GitHub location 字段命中即视为国内圈）
_CN_TERMS = [
    "china", "中国", "prc", "shenzhen", "深圳", "beijing", "北京", "shanghai", "上海",
    "guangzhou", "广州", "hangzhou", "杭州", "chengdu", "成都", "shenzhen", "大湾区",
    "greater bay", "hong kong", "hongkong", "香港", "taiwan", "台湾", "macau", "澳门",
    "nanjing", "南京", "wuhan", "武汉", "xiamen", "厦门", "suzhou", "苏州",
    "singapore", "新加坡",  # 华语人才常见聚集地
]


def _geo_class(location):
    """把 location 粗分三类：cn(国内/大湾区) / unknown(空或看不出) / overseas(明显海外)。"""
    if not location or not location.strip():
        return "unknown"
    low = location.lower()
    if any(t in low for t in _CN_TERMS):
        return "cn"
    return "overseas"


def _cn_focused(profile):
    """是否在召回层硬过滤海外。
    - 岗位写明 remote/远程 时不硬过滤（远程岗可在任意地点，地点偏好交给 RUBRIC 软打分）。
    - 否则只要 geo 命中国内/大湾区/华语区关键词，就开启硬过滤。"""
    blob = " ".join(profile.get("geo", []) or []).lower()
    if "remote" in blob or "远程" in blob:
        return False
    return any(t in blob for t in _CN_TERMS)


def _headers():
    h = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = "Bearer " + token
    return h


def _get(path, params=None):
    """带限流 + 网络抖动重试的 GET。
    - 命中 rate limit：按 reset 时间等待（封顶 60s）。
    - 瞬时网络/SSL 错误：退避重试，不让单次抖动崩掉整轮召回。"""
    last_err = None
    for attempt in range(4):
        try:
            r = requests.get(API + path, headers=_headers(), params=params, timeout=20)
        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))  # 2s,4s,6s 退避
            continue
        if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
            reset = int(r.headers.get("X-RateLimit-Reset", "0"))
            wait = max(0, min(60, reset - int(time.time()) + 1))
            print("  [rate limit] 等待 %ds...（建议在 .env 填 GITHUB_TOKEN 提到 5000/h）" % wait)
            time.sleep(wait or 5)
            continue
        r.raise_for_status()
        return r.json()
    if last_err:
        raise last_err
    raise RuntimeError("GET 失败: " + path)


def _build_query(keywords, language):
    kw = " OR ".join(keywords[:5]) if keywords else ""
    q = "(%s)" % kw if kw else ""
    q += " language:%s" % language
    return q.strip()


def _fetch_user(login):
    """拉个人资料 + top 仓库（按 stars 排序，取前 8 个），供精排判断方向。"""
    user = _get("/users/%s" % login)
    try:
        repos = _get("/users/%s/repos" % login, {"per_page": 100, "sort": "pushed"})
    except requests.HTTPError:
        repos = []
    top = sorted(repos, key=lambda r: r.get("stargazers_count") or 0, reverse=True)[:8]
    top_repos = [{
        "name": r.get("name"),
        "desc": r.get("description"),
        "lang": r.get("language"),
        "stars": r.get("stargazers_count"),
    } for r in top]
    return user, top_repos


def recall(profile, max_candidates=60, repos_per_query=20, contributors_per_repo=15):
    gh = profile["github"]
    min_followers = gh.get("min_followers", 0)
    cn_focus = _cn_focused(profile)  # 岗位以国内为主时，过滤掉明显海外的人
    if cn_focus:
        print("（地点偏好：国内/大湾区——明显海外的候选人将被跳过，地点未知的保留）")

    # 第一步：搜仓库，收集每个仓库的贡献者名单（先不拉个人资料，省调用）。
    # 只需要足够多的"桶"来保证多样性即可，不必把所有搜到的仓库都扒一遍。
    buckets = []  # (repo_meta, language, [logins], {login: contributions})
    # 开了地点过滤会刷掉很多人，需要更宽的召回面才能凑够数。
    bucket_cap = max(max_candidates * (4 if cn_focus else 2), 12)
    for language in gh["languages"][:3]:
        if len(buckets) >= bucket_cap:
            break
        q = _build_query(gh["repo_keywords"], language)
        print("搜索仓库: %s" % q)
        data = _get("/search/repositories",
                    {"q": q, "sort": "stars", "order": "desc", "per_page": repos_per_query})
        time.sleep(2)  # 避开 search 二级限流
        for repo in data.get("items", []):
            if len(buckets) >= bucket_cap:
                break
            try:
                contribs = _get("/repos/%s/contributors" % repo["full_name"],
                                {"per_page": contributors_per_repo})
            except requests.HTTPError:
                continue
            logins = [c.get("login") for c in contribs if c.get("login")]
            cmap = {c.get("login"): c.get("contributions") for c in contribs}
            if logins:
                buckets.append((repo, language, logins, cmap))

    if not buckets:
        return

    # 第二步：跨仓库轮询取人，保证来源多样。逐个 yield，让调用方边召回边入库——
    # 这样即使中途出错，已抓到的人也已落库，不会全丢。
    seen = set()
    produced = 0
    skipped_overseas = 0
    rank = 0
    while produced < max_candidates:
        progressed = False
        for repo, language, logins, cmap in buckets:
            if rank >= len(logins):
                continue
            progressed = True
            login = logins[rank]
            if login in seen:
                continue
            seen.add(login)

            try:
                user, top_repos = _fetch_user(login)
            except requests.exceptions.RequestException as e:
                print("  ! 跳过 %s（拉取失败：%s）" % (login, e))
                continue
            # GitHub 的 type 分 User / Organization / Bot——组织号和机器人不是候选人。
            # 在这里跳过而不是等精排再判，是因为精排每个人都要花 LLM 的钱。
            acct_type = user.get("type") or "User"
            if acct_type != "User":
                print("  ! 跳过 %s（%s 账号，非真人）" % (login, acct_type))
                continue

            followers = user.get("followers") or 0
            if followers < min_followers:
                continue

            geo_class = _geo_class(user.get("location"))
            if cn_focus and geo_class == "overseas":
                skipped_overseas += 1
                continue  # 明显海外，直接跳过不送精排，省钱

            print("  + %s (followers=%d, geo=%s, via %s)"
                  % (login, followers, geo_class, repo["full_name"]))
            yield {
                "source": "github",
                "source_id": login,
                "account_type": acct_type,
                "name": user.get("name"),
                "email": user.get("email"),
                "location": user.get("location"),
                "bio": user.get("bio"),
                "company": user.get("company"),
                "followers": followers,
                "public_repos": user.get("public_repos"),
                "languages": [language],
                "signals": {
                    "matched_repo": repo["full_name"],
                    "repo_stars": repo.get("stargazers_count"),
                    "contributions": cmap.get(login),
                    "top_repos": top_repos,
                    "geo_class": geo_class,
                },
                "html_url": user.get("html_url"),
            }
            produced += 1
            if produced >= max_candidates:
                break
        rank += 1
        if not progressed:
            break
    if cn_focus and skipped_overseas:
        print("（已跳过 %d 个明显海外候选人）" % skipped_overseas)
