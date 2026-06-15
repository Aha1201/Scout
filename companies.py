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

SYSTEM = """你是金融科技招聘的行业专家。给定几个种子公司和岗位领域，列出市场上**同类的目标公司**，
用于在 LinkedIn 上按履历扩大搜索宽度。要求：
- 覆盖同赛道：加密交易所、传统券商 / 期货 / 经纪商、衍生品与做市平台等，与种子公司同类。
- 用 LinkedIn 上出现的英文公司名（如 OKX, Binance, Bybit, Coinbase, Kraken, Gate.io, KuCoin, Bitget,
  Huobi/HTX, Crypto.com, Deribit；Futu, Tiger Brokers, Interactive Brokers, Robinhood, Webull, eToro, Saxo Bank...）。
- 40-60 个，去重，按相关性排序，种子公司本身也包含进来。
- 只列与岗位领域（交易所核心/统一账户/保证金/风控/衍生品/经纪）相关的公司，不要无关公司。
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
