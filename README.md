# Scout — Web3 / Fintech 人才精准猎寻

一个单人可用的精准猎寻漏斗：**需求 → 召回 → AI 精排 → 触达**。
v1 只接 GitHub 一个源，专门跑通"Web3 智能合约工程师"这一类画像。

## 为什么是这个形状

难点从来不在搜索界面，在底层有没有可搜的人。Web3 工程师的工作成果（代码、贡献）几乎全公开，
所以 **GitHub 是最便宜、最高质量的人群来源**。把"什么是好工程师"的标准固化进 `rerank.py` 的
RUBRIC——这是传统关键词匹配做不到、也是别人抄不走的核心壁垒。

```
需求结构化 ──▶ GitHub 召回 ──▶ AI 精排 ──▶ Top 名单 + 开场白
 (profile.py)  (recall_github.py) (rerank.py)   (run.py)
                    └──────── SQLite 候选池 (db.py) 贯穿全程，每层回写，不重复召回
```

## 快速开始

```bash
cd /Users/Dannyzhang/Scout
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # 填 GITHUB_TOKEN（免费）和 ANTHROPIC_API_KEY
```

GitHub token 免费：https://github.com/settings/tokens → Generate new token (classic) → 不勾任何权限即可
（只为把限额从 60/h 提到 5000/h）。

## 用法

```bash
# 一条命令跑完整漏斗
python run.py "招高级智能合约工程师，Solidity + DeFi 实战经验，远程优先"

# 从文件读 JD，多召回一些
python run.py --jd-file jd.txt --max 80 --top 30

# 只精排库里还没评分的人（比如换了 RUBRIC 后重跑，需先清空 score）
python run.py --rerank-only

# 只看当前 Top 名单
python run.py --list --top 30

# 跑完顺带导出 CSV（用 Excel / Numbers 打开整张排序名单）
python run.py "..." --export
# 或单独导出库里已有结果
python run.py --export results.csv
```

## 结果在哪看

- **网页报告**（`--html`，推荐）：自动在浏览器打开，可按分数排序、按结论筛选、搜索，开场白一键复制
- **CSV 导出**（`--export`）：Excel / Numbers 直接打开
- **终端**：每次跑完打印 Top 名单
- **`scout.db`**：SQLite，所有召回过的人（数据源，每层回写）

```bash
python run.py "你的JD" --max 50 --html   # 跑完自动开网页
python run.py --html                      # 不重跑，只把库里结果出成网页
```

## 成本

- GitHub：免费
- LLM 用 DeepSeek（OpenAI 兼容接口）：`deepseek-chat`(V3) 极便宜，适合批量铺量精排几百上千人；
  想要更强推理可把 `.env` 的 `RERANK_MODEL` 调成 `deepseek-reasoner`(R1)。

## 调优重点

第一版只该动两个地方：
1. `rerank.py` 的 `RUBRIC` —— 把你的招聘品味写进去（这是核心资产）。
2. `.env` 的 `RERANK_MODEL` —— `deepseek-chat`(便宜快) ↔ `deepseek-reasoner`(更会推理)。

跑通验证标准：Top 20 里有 ≥12 个你点头"值得联系"。跑通了再加 Farcaster / Proxycurl 第二、三个源。

## 召回源（多源）

```bash
python run.py --role <岗位> "JD" --source github     # 默认，按代码找人，适合 OSS 重的岗位
python run.py --role <岗位> "JD" --source linkedin    # 按履历/公司找人，适合交易所/金融等闭源领域
python run.py --role <岗位> "JD" --source both        # 两个源都跑，汇入同一候选池
```

LinkedIn 源经 CoreSignal 合规 API（注:Proxycurl 已于 2025 关停，勿用）。需在 `.env` 填 `CORESIGNAL_API_KEY`。
首次接入需用一条真实返回校准 `recall_linkedin.py` 的字段映射（已标 ⚠ CALIBRATE）。

## 范围之外（先不做）

Farcaster、链上数据源、批量触达发送、Web UI。
