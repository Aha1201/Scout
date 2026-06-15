"""Scout 漏斗编排器：需求 -> 召回 -> 精排 -> Top 名单。

用法：
  python run.py "招高级智能合约工程师，要 Solidity + DeFi 实战经验，远程"
  python run.py --jd-file jd.txt --max 60 --top 20
  python run.py --rerank-only            # 只把库里没精排的候选人跑一遍
  python run.py --list --top 30          # 只看当前 Top 名单
"""
import argparse
import csv
import json
import os
import sys
import webbrowser

from dotenv import load_dotenv

load_dotenv()

import db
import report
import rerank
from profile import jd_to_profile
from recall_github import recall
from rerank import score_candidate

ROLES_DIR = os.path.join(os.path.dirname(__file__), "roles")


def _apply_role(slug, args):
    """切换到某个岗位：独立 DB、独立 RUBRIC、导出落到岗位目录。"""
    base = os.path.join(ROLES_DIR, slug)
    if not os.path.exists(base):
        os.makedirs(base)
    db.set_db_path(os.path.join(base, "scout.db"))

    rubric_file = os.path.join(base, "rubric.txt")
    if os.path.exists(rubric_file):
        with open(rubric_file, encoding="utf-8") as f:
            rerank.set_rubric(f.read())
        print("已加载岗位 RUBRIC：%s" % rubric_file)
    else:
        with open(rubric_file, "w", encoding="utf-8") as f:
            f.write(rerank.DEFAULT_RUBRIC)
        print("⚠ 该岗位还没有 RUBRIC，已生成默认模板：%s\n  建议先按岗位修改这份文件再跑精排。" % rubric_file)
    # 导出落到岗位目录
    if args.export:
        args.export = os.path.join(base, os.path.basename(args.export))
    if args.html:
        args.html = os.path.join(base, os.path.basename(args.html))


def _export_csv(path):
    rows = db.all_scored()
    cols = ["score", "verdict", "source_id", "name", "followers", "location",
            "html_url", "evidence", "red_flags", "outreach_hook", "status"]
    # utf-8-sig 让 Excel 正确显示中文
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["分数", "结论", "GitHub", "姓名", "followers", "地点",
                    "主页", "证据", "减分点", "开场白", "状态"])
        for r in rows:
            w.writerow([
                r.get("score"), r.get("verdict"), r.get("source_id"), r.get("name"),
                r.get("followers"), r.get("location"), r.get("html_url"),
                "；".join(json.loads(r.get("evidence") or "[]")),
                "；".join(json.loads(r.get("red_flags") or "[]")),
                r.get("outreach_hook"), r.get("status"),
            ])
    print("已导出 %d 人到 %s（用 Excel / Numbers 打开）" % (len(rows), path))


def _export_html(path, open_browser=True):
    n = report.export_html(path)
    abspath = os.path.abspath(path)
    print("已生成网页报告（%d 人）：%s" % (n, abspath))
    if open_browser:
        webbrowser.open("file://" + abspath)


def _print_top(limit):
    rows = db.top_candidates(limit=limit)
    if not rows:
        print("（还没有已精排的候选人）")
        return
    print("\n===== Top %d 名单 =====" % len(rows))
    for r in rows:
        print("\n[%s] %s  %s" % (r["score"], r["verdict"], r["source_id"]))
        print("  %s | followers=%s | %s" % (r.get("name") or "-", r.get("followers"), r.get("html_url")))
        ev = json.loads(r.get("evidence") or "[]")
        if ev:
            print("  证据: " + "；".join(ev))
        if r.get("outreach_hook"):
            print("  开场白: " + r["outreach_hook"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jd", nargs="?", help="招聘需求（口述或 JD 文本）")
    ap.add_argument("--jd-file", help="从文件读取 JD")
    ap.add_argument("--max", type=int, default=60, help="本次最多召回多少候选人")
    ap.add_argument("--top", type=int, default=20, help="最后展示 Top N")
    ap.add_argument("--rerank-only", action="store_true", help="跳过召回，只精排库里未评分的人")
    ap.add_argument("--list", action="store_true", help="只展示当前 Top 名单")
    ap.add_argument("--export", nargs="?", const="scout_export.csv",
                    help="导出已精排名单为 CSV（默认 scout_export.csv）")
    ap.add_argument("--html", nargs="?", const="scout_report.html",
                    help="生成网页报告并在浏览器打开（默认 scout_report.html）")
    ap.add_argument("--role", help="岗位名（独立 DB + 独立 RUBRIC，放在 roles/<名>/）")
    ap.add_argument("--source", choices=["github", "linkedin", "both"], default="github",
                    help="召回源：github（默认）/ linkedin（需 CORESIGNAL_API_KEY）/ both")
    args = ap.parse_args()

    if args.role:
        _apply_role(args.role, args)

    db.init()

    if args.list:
        _print_top(args.top)
        return

    # 纯查看模式：没给 JD / rerank 时，只导出/开网页，不跑漏斗
    if (args.export or args.html) and not (args.jd or args.jd_file or args.rerank_only):
        if args.export:
            _export_csv(args.export)
        if args.html:
            _export_html(args.html)
        return

    # --- 拿 JD ---
    jd = None
    if not args.rerank_only:
        if args.jd_file:
            with open(args.jd_file) as f:
                jd = f.read()
        elif args.jd:
            jd = args.jd
        else:
            print("需要提供 JD（位置参数或 --jd-file），或用 --rerank-only / --list")
            sys.exit(1)

    profile = None
    if jd:
        print("== 第 1 层：需求结构化 ==")
        profile = jd_to_profile(jd)
        print(json.dumps(profile, ensure_ascii=False, indent=2))

        sources = []
        if args.source in ("github", "both"):
            sources.append(("GitHub", recall))
        if args.source in ("linkedin", "both"):
            from recall_linkedin import recall as recall_li
            sources.append(("LinkedIn", recall_li))

        for label, fn in sources:
            print("\n== 第 2 层：%s 召回 ==" % label)
            found = new = 0
            # 边召回边入库：即使中途出错，已抓到的人也已落库
            for c in fn(profile, max_candidates=args.max):
                found += 1
                if db.upsert_candidate(c, query_tag=profile["role"]):
                    new += 1
            print("%s 召回 %d 人，新增 %d 人（其余已在库）" % (label, found, new))

    print("\n== 第 3 层：AI 精排 ==")
    # rerank-only 时没有 profile，用一个空壳；rubric 本身已含标准
    profile = profile or {"role": "（复用库内候选人）"}
    unscored = db.get_unscored()
    print("待精排 %d 人" % len(unscored))
    for i, cand in enumerate(unscored, 1):
        try:
            result = score_candidate(profile, cand)
            db.save_score(cand["id"], result)
            print("  [%d/%d] %s -> %d (%s)" % (i, len(unscored), cand["source_id"],
                                               result["score"], result["verdict"]))
        except Exception as e:
            print("  [%d/%d] %s 精排失败: %s" % (i, len(unscored), cand["source_id"], e))

    _print_top(args.top)

    if args.export:
        _export_csv(args.export)
    if args.html:
        _export_html(args.html)


if __name__ == "__main__":
    main()
