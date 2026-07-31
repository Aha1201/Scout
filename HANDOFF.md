# Scout 交接包

> 人才精准猎寻漏斗。给一个岗位需求，从公开/合规数据源找人，用可定制的 AI 评分标准精排，输出可直接开聊的候选人名单。
> 单人可用，Python，~1200 行。本文件是理解和接手 Scout 的唯一入口。

---

## 1. 它是什么 / 解决什么问题

难点从来不在"搜索界面"，在**底层有没有可搜的人**。Scout 是一个薄漏斗：

```
需求结构化 ──▶ 多源召回 ──▶ AI 精排 ──▶ 网页/CSV 报告
 (profile)     (recall_*)    (rerank)      (report)
                    └──────── SQLite 候选池 (db) 贯穿全程，每层回写、去重、不重复召回
```

**核心资产是第 3 层的 RUBRIC**（每个岗位一份评分标准），不是爬数据。数据源可插拔，评分标准是别人抄不走的招聘品味。

---

## 2. 架构 / 文件地图

| 文件 | 职责 |
|---|---|
| `run.py` | 编排器 + CLI 入口。所有命令从这里进 |
| `profile.py` | 第1层：JD/口述 → 结构化召回画像（同时产出 GitHub + LinkedIn 搜索参数） |
| `recall_github.py` | 源①：按代码找人（搜仓库→扒贡献者→拉资料+top仓库）。免费 |
| `recall_linkedin.py` | 源②：CoreSignal Multi-source Employee API，按履历/公司找人。付费 |
| `recall_manual.py` | 源③：把猎聘/脉脉/BOSS 复制的文本用 LLM 解析成候选人。不花 API 钱 |
| `companies.py` | 目标公司自动扩展：几个种子公司 → 全市场同类雇主，放大 LinkedIn 宽度 |
| `rerank.py` | 第3层：AI 精排。`ACTIVE_RUBRIC` 是核心壁垒；含可选语言硬门槛 |
| `report.py` | 生成自带样式的网页报告（可点/搜/筛/复制开场白） |
| `db.py` + `schema.sql` | SQLite 候选池，每层回写 |
| `llm.py` | LLM 封装（DeepSeek，OpenAI 兼容接口，JSON 模式） |

候选人在库里有 `source` 字段（github/linkedin/manual），三个源产出**同一种格式**，所以下游 DB/精排/报告完全复用——加新源只需写一个 `recall_*.py`。

---

## 3. 三个数据源 —— 什么岗用什么源（最重要的经验）

| 源 | 适合 | 成本 | 教训 |
|---|---|---|---|
| **GitHub** | 开源技术人：Web3、移动基础架构、**Java+电商/微服务**等 GitHub 上有代码痕迹的 | 免费 | 优先用它兜底 |
| **LinkedIn**(CoreSignal) | 闭源/企业/金融岗：交易所核心、解决方案架构师、销售等 GitHub 看不到履历的 | 2 credit/人 ≈ $0.39/人 | 唯一能"按公司履历找人"的 |
| **手动粘贴** | 国内岗（猎聘/脉脉本地池远胜 LinkedIn），或任何你手头有名单的 | 免费 | 不碰爬虫（脉脉判例，法律风险） |

**铁律级经验（用真实数据验证过）：同一个岗位，需求措辞决定哪个源有效。**
- UTA 交易所 Java（闭源）→ GitHub 50 人只有 1 个能要；LinkedIn 直接捞出 OKX/MEXC 工程师。
- 同是"架构师"：措辞"双云+英文"时 GitHub 抓瞎；措辞"Java+电商"时 GitHub 满载（芋道、litemall 作者都在上海）。

**分流建议**：GitHub 免费兜底 → LinkedIn 专攻闭源金融/企业岗且精打细算 → 国内岗优先猎聘/脉脉人工搜。

---

## 4. 怎么跑（Setup + 常用命令）

```bash
cd /Users/Dannyzhang/Scout
python3 -m venv .venv && source .venv/bin/activate   # 首次
pip install -r requirements.txt                       # 首次
# 编辑 .env 填 key（见第 7 节）；每次开工先 source .venv/bin/activate
```

```bash
# 完整漏斗（GitHub 源）
python run.py --role <岗位> "岗位JD文本" --source github --max 40 --html

# 闭源岗用 LinkedIn（需 CoreSignal credit）
python run.py --role <岗位> "JD" --source linkedin --max 30 --html

# 手动粘贴：把猎聘/脉脉候选人存进 candidates.txt（多个用 --- 分隔），再：
python run.py --role <岗位> --paste candidates.txt --html

# 只看/重出报告（不重跑召回，免费）
python run.py --role <岗位> --html
python run.py --role <岗位> --list

# 预览/生成某岗位的目标公司列表（免费，DeepSeek）
python run.py --role <岗位> --expand-companies "JD"
```

### 命令行参数
`--role`(岗位隔离) · `--source github|linkedin|both` · `--max`(召回量) · `--top`(展示数) ·
`--min-score`(默认50，隐藏低分；设0看全部) · `--lang-gate`(语言硬门槛，见下) ·
`--paste <file>`(手动源) · `--expand-companies` · `--html` · `--export`(CSV) · `--list` · `--rerank-only`

### 结果在哪看
- **网页**（`--html`，推荐）：`roles/<岗位>/scout_report.html`，可点名字/搜索/按结论筛选/一键复制开场白
- **CSV**（`--export`）：Excel/Numbers 打开
- **`roles/<岗位>/scout.db`**：SQLite 数据源

---

## 5. 多岗位系统 —— 怎么开新岗位

每个岗位 = `roles/<岗位名>/` 一个文件夹，内含：
- `rubric.txt` —— **该岗位的评分标准（核心资产）**
- `scout.db` —— 独立候选池（gitignored，不入库）
- `companies.txt` —— LinkedIn 目标公司列表（可手动增删）
- `scout_report.html` / `scout_export.csv` —— 报告（gitignored）

**开新岗位**：`python run.py --role <新名> "JD" --source github --html`。
首次会自动生成默认 rubric 模板 —— **然后一定要按岗位改 `roles/<新名>/rubric.txt`**（这是决定成败的一步）。

已建岗位：`uta-java`（交易所核心 Java，LinkedIn）· `digital-architect`（上海 Java+电商架构师，GitHub）·
`mobile-infra`（移动基础架构）· `Mobile-Security`。可参考它们的 rubric 写法。

### 写 rubric 的要点
- 硬性条件、一票否决（dealbreaker）、加分项、资历信号、评分区间要写清楚。
- GitHub 岗要提醒模型"看 top_repos 判断技术方向/领域信号"。
- LinkedIn 岗要提醒"公司归属是强证据""闭源经历 GitHub 看不到≠没有，留待面聊"。
- 参考 `roles/uta-java/rubric.txt`（含语言硬门槛）和 `roles/digital-architect/rubric.txt`（Michelin 客户，含 dealbreaker）。

---

## 6. 质量护栏（踩过坑换来的）

- **语言硬门槛** `--lang-gate`（默认关）：GitHub 候选人主力语言不在岗位语言里就封顶 40 分。
  代码层强制，不靠模型自觉。**只在"精通某语言"的岗开**（如 UTA 精通 Java）；架构师等重广度的岗**别开**，否则误杀。
- **公司自动扩展**（`companies.py`）：种子 → 全市场同类雇主（领域无关，按岗位推导）。放大 LinkedIn 召回宽度一个量级。
- **地点过滤**（GitHub）：岗位 geo 是国内/大湾区时，明显海外的直接跳过、地点未知的保留；写 remote 则不过滤。
- **网络健壮性**：GitHub/CoreSignal 都有 503/网络抖动退避重试；**边召回边入库**（崩了也保住已抓到的）。
- **CoreSignal 402**（credit 用尽）：干净停止并提示，不静默产出空记录。
- **LinkedIn 召回精度**：两段式——先目标公司（要求 Java/后端信号，不用过宽的"Engineer"）优先，再用领域词填充。

---

## 7. 成本 / 密钥

### 密钥（`.env`，**已 gitignore，绝不入库**）
- `GITHUB_TOKEN`：免费，classic token 不勾任何权限，把限额 60→5000/h
- `CORESIGNAL_API_KEY`：付费，LinkedIn 源用
- `DEEPSEEK_API_KEY`：精排 + 需求结构化用（OpenAI 兼容，`base_url=https://api.deepseek.com`）
- `RERANK_MODEL` / `PROFILE_MODEL`：默认都 `deepseek-chat`

### 成本账
- **GitHub**：免费。
- **DeepSeek**：极便宜，每个候选人精排几厘钱。
- **CoreSignal**：搜索 credit 单独池子（基本免费），**collect 2 credit/人 ≈ $0.39/人**。
  Starter $49/月 = 250 credit = **≈125 人/月**。一次 `--max 30` 跑 ≈ 60 credit。
  实测转化：拉一个"值得联系"≈ $5.9，一个"≥50 可看"≈ $2.4。
- **省钱铁律**：① GitHub 优先兜底 ② 外科手术式不铺量（250/月≈一次 --max 100 多点）③ 精度>数量（搜索免费、collect 才花钱）。

---

## 8. 已验证 / 当前状态

- 三源全跑通，真实数据验证：GitHub 跑出上海 Java+电商架构师、LinkedIn 跑出 OKX/MEXC 工程师、手动源精排正常。
- git 5 个 commit，密钥全程未入库。
- 结论：**开发阶段基本完成，进入运营阶段**（选源、铺岗、精打细算 credit）。

---

## 9. 已知限制 / 技术债 / 下一步

- **CoreSignal credit 已用完**（上次 402）。要跑 LinkedIn 需先充值。
- **无触达闭环**：报告能生成开场白、有 `status` 字段（new/contacted/replied/rejected）但没做状态管理 UI，目前手动。
- **LinkedIn 转化率**：目标公司里混非工程师（精排会拒但白花 credit）。已收紧到 Java/后端信号，可继续调。
- **手动源**依赖你人工在猎聘/脉脉搜 + 复制，Scout 自动化不了"找人"这步（中国平台无合规 API）。
- **无自动化测试**：改召回/精排逻辑后靠真实小批量跑验证。
- 可选下一步：触达状态管理、第四个源、跑前 credit 预估+二次确认保护。

---

## 10. 快速上手路径（接手者读完本文后）

1. `source .venv/bin/activate`，`python run.py --role digital-architect --html` 看现成结果长啥样。
2. 读 `roles/uta-java/rubric.txt` 和 `roles/digital-architect/rubric.txt` 理解 rubric 怎么写。
3. 开自己的岗位：`python run.py --role <新名> "JD" --source github --html`，然后改 `roles/<新名>/rubric.txt`。
4. 闭源/企业岗充 CoreSignal 后加 `--source linkedin`；国内岗用 `--paste`。
