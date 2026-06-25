"""目标公司扩展：把 JD 里点名的几个种子公司（OKX/MEXC/老虎…）衍生成市场上同赛道的全套目标公司，
放大 LinkedIn 召回宽度。结果存成 roles/<岗位>/companies.txt，可人工编辑。"""
import os

from llm import structured

EXPAND_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"companies": {"type": "array", "items": {"type": "string"}}},
    "required": ["companies"],
}

SYSTEM = """你是资深招聘行业专家。给定岗位领域和（可能为空的）几个种子公司，列出市场上**该岗位候选人最可能任职的目标公司**，
用于在 LinkedIn 上按履历扩大搜索宽度。要求：
- 根据岗位领域自行判断赛道，列出同类雇主。例如：
  · 交易所核心 Java → 加密交易所 + 券商（OKX, Binance, Bybit, Coinbase, Futu, Tiger Brokers, IBKR...）
  · 数字化 / 解决方案架构师（云）→ 系统集成商与咨询（Accenture, Thoughtworks, Capgemini, Deloitte, IBM, Cognizant）、
    云厂商（Microsoft, Alibaba Cloud, AWS, Google Cloud）、企业软件（SAP, Oracle, Salesforce）等
  · 其他岗位同理，按领域推导。
- 用 LinkedIn 上出现的英文公司名（中国公司也用其英文名/常见写法）。
- 40-60 个，去重，按相关性排序；若给了种子公司，也包含进来。
- 只列与该岗位领域相关的雇主，不要无关公司。
只输出 JSON。"""


def expand_companies(seeds, role_desc):
    model = os.environ.get("PROFILE_MODEL", "deepseek-chat")
    user = "岗位领域：%s\n种子公司：%s" % (role_desc, ", ".join(seeds or []))
    out = structured(model, SYSTEM, user, EXPAND_SCHEMA, max_tokens=3000)
    return out["companies"]


def resolve(role_dir, seeds, role_desc):
    """返回用于 LinkedIn 召回的目标公司列表。
    优先读 roles/<岗位>/companies.txt（用户可编辑）；没有就用 LLM 扩展并写入。"""
    path = os.path.join(role_dir, "companies.txt") if role_dir else None
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            comps = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        print("已加载目标公司列表（%d 家）：%s" % (len(comps), path))
        return comps
    comps = expand_companies(seeds, role_desc)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 目标公司列表（LinkedIn 召回用）。一行一个，可手动增删；删掉本文件会重新自动生成。\n")
            f.write("\n".join(comps) + "\n")
        print("已自动扩展并保存目标公司列表（%d 家）：%s" % (len(comps), path))
    return comps
