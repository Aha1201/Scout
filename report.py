"""生成一个自带样式的 HTML 报告，浏览器直接打开。
可按分数排序、按结论筛选、关键词搜索。无需服务器、无额外依赖。"""
import json

import db

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scout 候选人名单</title>
<style>
  :root { --good:#0f7b4f; --mid:#9a6700; --skip:#9aa0a6; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background:#f6f7f9; color:#1a1a1a; }
  header { padding: 20px 28px; background:#fff; border-bottom:1px solid #e6e8eb; position:sticky; top:0; z-index:2;}
  h1 { font-size: 20px; margin:0 0 4px; }
  .sub { color:#5f6368; font-size:13px; }
  .controls { display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; align-items:center; }
  .controls input { padding:8px 12px; border:1px solid #d0d3d7; border-radius:8px; font-size:14px; min-width:240px; }
  .chip { padding:6px 14px; border:1px solid #d0d3d7; border-radius:999px; background:#fff;
          cursor:pointer; font-size:13px; }
  .chip.active { background:#1a1a1a; color:#fff; border-color:#1a1a1a; }
  main { padding: 20px 28px; }
  .card { background:#fff; border:1px solid #e6e8eb; border-radius:12px; padding:16px 18px; margin-bottom:12px; }
  .row1 { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
  .score { font-size:26px; font-weight:700; min-width:48px; }
  .verdict { font-size:13px; font-weight:600; padding:3px 10px; border-radius:999px; }
  .v-good { color:#fff; background:var(--good); }
  .v-mid  { color:#fff; background:var(--mid); }
  .v-skip { color:#fff; background:var(--skip); }
  .who a { font-size:16px; font-weight:600; color:#1558d6; text-decoration:none; }
  .meta { color:#5f6368; font-size:13px; }
  .sec { margin-top:10px; font-size:14px; line-height:1.55; }
  .sec b { color:#3c4043; font-weight:600; }
  .flags { color:#b3261e; }
  .hook { margin-top:10px; padding:10px 12px; background:#f1f6ff; border-radius:8px; font-size:13.5px; }
  .hook button { float:right; border:none; background:#1558d6; color:#fff; border-radius:6px;
                 padding:3px 10px; cursor:pointer; font-size:12px; }
  .empty { color:#5f6368; padding:40px; text-align:center; }
</style>
</head>
<body>
<header>
  <h1>Scout 候选人名单</h1>
  <div class="sub" id="count"></div>
  <div class="controls">
    <input id="q" placeholder="搜索 GitHub / 姓名 / 证据...">
    <span class="chip active" data-f="all">全部</span>
    <span class="chip" data-f="值得联系">值得联系</span>
    <span class="chip" data-f="观望">观望</span>
    <span class="chip" data-f="跳过">跳过</span>
  </div>
</header>
<main id="list"></main>
<script>
const DATA = __DATA__;
let filter = "all", query = "";
function vclass(v){ return v==="值得联系"?"v-good":(v==="观望"?"v-mid":"v-skip"); }
function esc(s){ return (s||"").replace(/[&<>]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function render(){
  const list = document.getElementById("list");
  const rows = DATA.filter(r => (filter==="all"||r.verdict===filter) &&
    (query==="" || (r.source_id+" "+(r.name||"")+" "+r.evidence.join(" ")).toLowerCase().includes(query)));
  document.getElementById("count").textContent =
    "共 "+DATA.length+" 人，当前显示 "+rows.length+" 人 · 按分数降序";
  if(!rows.length){ list.innerHTML='<div class="empty">没有匹配的候选人</div>'; return; }
  list.innerHTML = rows.map(r => `
    <div class="card">
      <div class="row1">
        <span class="score">${r.score}</span>
        <span class="verdict ${vclass(r.verdict)}">${r.verdict}</span>
        <span class="who"><a href="${r.html_url}" target="_blank">${esc(r.source_id)}</a></span>
        <span class="meta">${esc(r.name||"")} · followers ${r.followers||0} · ${esc(r.location||"地点未知")}</span>
      </div>
      ${r.evidence.length?`<div class="sec"><b>证据：</b>${esc(r.evidence.join("；"))}</div>`:""}
      ${r.red_flags.length?`<div class="sec flags"><b>减分点：</b>${esc(r.red_flags.join("；"))}</div>`:""}
      ${r.outreach_hook?`<div class="hook"><button onclick="navigator.clipboard.writeText(this.parentNode.dataset.h)">复制</button><b>开场白：</b>${esc(r.outreach_hook)}</div>`:""}
    </div>`).join("");
  // 把开场白原文挂到 dataset 供复制
  list.querySelectorAll(".hook").forEach((el,i)=>{ el.dataset.h = rows[i].outreach_hook||""; });
}
document.getElementById("q").addEventListener("input", e=>{ query=e.target.value.toLowerCase(); render(); });
document.querySelectorAll(".chip").forEach(c=>c.addEventListener("click",()=>{
  document.querySelectorAll(".chip").forEach(x=>x.classList.remove("active"));
  c.classList.add("active"); filter=c.dataset.f; render();
}));
render();
</script>
</body>
</html>"""


def export_html(path, min_score=0):
    rows = db.all_scored(min_score=min_score)
    data = [{
        "score": r.get("score"),
        "verdict": r.get("verdict"),
        "source_id": r.get("source_id"),
        "name": r.get("name"),
        "followers": r.get("followers"),
        "location": r.get("location"),
        "html_url": r.get("html_url"),
        "evidence": json.loads(r.get("evidence") or "[]"),
        "red_flags": json.loads(r.get("red_flags") or "[]"),
        "outreach_hook": r.get("outreach_hook"),
    } for r in rows]
    html = _TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return len(rows)
