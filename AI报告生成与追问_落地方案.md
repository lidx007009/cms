# AI 报告生成 + 报告内灵活追问 —— 完整可落地方案

> 目标：构建一个"**生成 AI 报告** → **用户看完后还能无尽追问**"的闭环系统。
> 适用场景示例：连锁药店月度经营分析（销售额、合规率、处方流转率、DTP/DOT 等）。
> 本文配套一整套**可直接复制**的示例文件，见仓库 `examples/` 目录，文中会逐一引用。

---

## 0. 一句话设计哲学

> **确定性的事交给代码，不确定的事交给 AI。**

| 类型 | 谁来做 | 为什么 |
|---|---|---|
| 取数、算同环比、格式化、画图 | 代码 / 固定 API | 必须 100% 准确、可复现，绝不能让模型"猜数字" |
| 文字解读、意图理解、工具编排 | AI（LLM） | 这是模型真正的价值，灵活、像人 |

如果违背这条原则（让 AI 直接写 SQL、直接报数字），系统一定会幻觉、对不上账、没法落地。整套方案的每个组件都是为这条原则服务的。

### 系统两大场景与组件总览

```
┌─────────────────────────── 场景一：生成 AI 报告（确定性主导） ───────────────────────────┐
│  报告模板  →  语义映射契约  →  后端硬取数(指标库)  →  版本快照(冻结)  →  章节Prompt→LLM写解读  │
│  examples/01     examples/02        examples/02         examples/04        examples/03       │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                          │ 用户看完报告，开始追问
                                          ▼
┌─────────────────────────── 场景二：报告内追问（探索性主导） ───────────────────────────┐
│  会话焦点状态  →  LLM(看元数据字典)选技能  →  Java技能库受控取数  →  LLM出"文字+图表协议"   │
│  examples/07         examples/06              examples/05               examples/08         │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

# 第一部分 · 场景一：生成 AI 报告

你已经有报告模板（定义了结构、候选指标、成篇逻辑）。要让 AI **稳定、忠实**地把模板填好，需要 3 个核心组件。

## 1.1 语义映射契约（Semantic Binding Contract）

### 它解决什么问题
模板里全是占位符，比如 `{{slot:compliance.rate}}`、`{{slot:sales.mom}}`。
**绝对不能**让 AI 去理解"5月处方流转率"该查哪张表、怎么算。否则每次结果都不一样，还会算错。

所以要在模板和指标之间，加一层**契约**：明确规定每个占位符 → 用哪个指标ID、什么口径、什么参数、怎么格式化。这一步**纯代码执行，AI 不参与**。

### 三份配套文件
1. **模板** → `examples/01-templates/report_template.md`
   只放结构 + 两种占位符：`{{slot:*}}`（数据槽，后端填）、`{{insight:*}}`（推理槽，AI 填）。
2. **映射契约** → `examples/02-contracts/semantic_binding.json`
   每个 slot 声明 `indicator_id` / `transform`(mom/yoy) / `params` / `format` / `thresholds` / `on_missing`。
3. **指标库目录** → `examples/02-contracts/indicator_catalog.yaml`
   所有指标的"唯一事实来源"：口径、支持的维度、支持的变换、取数实现 SQL、新鲜度 SLA。

### 一个契约片段长这样（节选自示例）
```json
"compliance.rate": {
  "source": "indicator",
  "indicator_id": "IND_COMPLIANCE_RATE",
  "params": { "org_id": "$.org.id", "period": "$.period.month", "scope": "all" },
  "type": "percent",
  "format": "0.0%",
  "thresholds": { "good": ">=0.95", "warn": "[0.85,0.95)", "bad": "<0.85" }
}
```
渲染时后端读到 `compliance.rate` → 找到 `IND_COMPLIANCE_RATE` → 带参数取数 → 按 `0.0%` 格式化 → 按 `thresholds` 打上 `level: bad` → 填进模板。**全程没有 AI。**

> ✅ 落地要点：给契约配一份 **JSON Schema**（`examples/02-contracts/semantic_binding.schema.json`），在 CI 里做校验。占位符写错、指标ID 不存在，直接挡在合并前（fail-fast）。

## 1.2 业务推理 Prompt 工程库（Reasoning Prompt）

### 它解决什么问题
取完数，要 AI 输出"洞察/解读"。但不能让它自由发挥，要给它**专业的业务推理规则**。

### 配套文件
`examples/03-prompts/PROMPT_COMPLIANCE_V2.md` —— 每个 `{{insight:*}}` 槽位对应一个这样的 Prompt 文件，包含 4 块：

1. **System（角色 + 铁律）**：唯一信息源是注入的 JSON；禁止编造数字；缺数据要说"数据不足"；结论必须标注字段名。
2. **Rules（业务阈值，把"什么算好/坏"写死）**：例如
   > DTP 的 DOT < 0.8 视为高风险，必须在报告中点名并给原因方向。
   > 合规率环比 < -3% 时，必须用 `compliance_breakdown` 找出贡献最大的品类/处方类型。
3. **Output Contract（输出结构）**：先结论→再归因→DTP专项→一句可执行建议；字数 ≤ 200。
4. **Input Data（注入数据）**：运行时由后端按契约填入，AI 不可改。

该文件末尾给了一个**完整拼装示例**（注入什么 JSON、AI 应该输出什么），照着写即可。

> ✅ 防幻觉：生成后做一道校验 —— 文本里出现的所有数字，必须都能在注入数据里找到，否则打回重生成（见 `validate_no_hallucination`）。

## 1.3 报告快照与血缘（Snapshot & Lineage）

### 它解决什么问题
用户之后要追问，AI 必须知道"报告当时看到的数字"。而且报告要可复现、可对账。

### 配套文件
`examples/04-snapshots/report_snapshot.json` —— 报告生成那一刻，把这些**冻结**下来：
- `frozen_values`：所有 slot 的原始值 + 展示值 + level。
- `extra_data`：章节明细（如 `compliance_breakdown`）。
- `generated_insights`：AI 写的每段文字 + 用的 prompt_id + token。
- `lineage`：数据截止时间、数据源表 + 新鲜度、pipeline run id、指标库版本、**LLM 模型与版本、temperature、代码 git revision**。
- `integrity`：对 frozen_values 做 hash，防篡改。

> ✅ 这就是"版本快照"：同一份 `snapshot_id` 任何时候都能 1:1 还原报告，追问也基于它，永远对得上账。

### 场景一端到端流程
见 `examples/10-pipeline/report_generation_pipeline.py` 的 `generate_report()`：
**加载模板/契约 → 后端硬取数填 data_slot → 取明细 → 生成快照(先冻结) → 逐章节喂Prompt给LLM写解读 → 防幻觉校验 → 回填渲染 → 落库。**

---

# 第二部分 · 场景二：报告内追问（无尽探索）

用户会问超出模板的问题（"为什么阿托伐他汀5月合规率掉这么多？"→"按处方类型拆一下"→"它销售额趋势呢"）。需要 4 个核心组件。

## 2.1 技能库 Skills Store（Java 封装的受控 API）

### 它解决什么问题
追问的问题没法预先建模，但**绝不能让 AI 现写 SQL**（注入、越权、跑垮库、算错）。
解决办法：把高频下钻分析能力，封装成一组**受控 API（Skills）**，AI 只能挑工具、填参数。

### 配套文件
- `examples/05-skills/skills_manifest.json` —— 直接喂给 LLM 的 function-calling 定义，含：
  - `get_indicator`（查单值/同环比）
  - `get_indicator_by_dimension`（按维度下钻）
  - `get_root_cause_analysis`（归因：自动返回各子维度对变化量的贡献度）
  - `get_indicator_trend`（趋势）
  - `resolve_entity`（把"阿托伐他汀"解析成 `drug_id=D8821`）
- `examples/05-skills/IndicatorSkillController.java` —— Java 实现示例，体现 4 条铁律：
  1. AI 永远拿不到 SQL 执行权；
  2. `indicator_id`/`dimension` 必须先在指标库校验合法，非法拒绝；
  3. **org 范围由后端从登录态注入，绝不信任 AI 传来的 org_id**（行级权限）；
  4. 出参结构稳定，既回填给 AI 推理，又能驱动图表协议。

## 2.2 面向 AI 的业务元数据字典（Metadata Dictionary）

### 它解决什么问题
AI 怎么知道"用户这句话该调哪个 skill、填什么参数"？要给它一份"说明书"。

### 配套文件
`examples/06-metadata/metadata_dictionary.yaml`（与指标库同源，但措辞是"给模型看的自然语言"）：
- 每个指标的**口语说法**（"合规率/合不合规/合规情况"都指 `IND_COMPLIANCE_RATE`）；
- 每个指标**能按哪些维度拆**；
- 维度**同义词**（"医保还是自费"→`payment_method`）；
- **意图路由**（问"为什么"→`get_root_cause_analysis`）；
- 默认口径（没说周期就继承焦点 / 取最近完结月）。

> 落地时把这份字典（按权限裁剪后）拼进追问的 system prompt。

## 2.3 会话上下文与状态管理（Session Context Manager）

### 它解决什么问题
多轮追问里全是指代和省略：「**它**同环比呢」「那**B药**呢」「按处方类型**拆一下**」。要维护一个**焦点状态（Focus State）**。

### 配套文件
`examples/07-session/focus_state.json` —— 记录 `org/period/indicator/filters/last_dimension/last_entity`，并定义**继承规则**：
- 没说周期 → 继承 `focus.period`；
- 说"它/那个" → 继承 `last_entity` 的 filters；
- 只换指标（"那毛利率呢"）→ 保留 period+filters，只改 indicator；
- 只换实体（"那B药呢"）→ 保留 indicator+period，替换实体；
- 说"整体/全部" → 清空 filters。

文件里有一段 3 轮对话的 `turns`，展示每轮如何把残缺的话补全成完整的 skill 调用参数。

## 2.4 动态图表渲染协议（AI-to-UI Protocol）

### 它解决什么问题
追问的回答常常需要图（"画个趋势图""按品类对比"）。但**AI 不画图**，只输出结构化指令，前端渲染。

### 配套文件
`examples/08-ui/chart_spec.json` —— AI 回答 = `text` + `charts[]`：
- 每个 chart 有 `chart_type`（严格白名单：line/bar/pie/table/kpi_card/waterfall）、`title`、`x`/`y`、`series`、`highlight`、`source`（可溯源到 skill + snapshot）；
- 还可带 `follow_up_suggestions`（引导用户继续追问，形成"无尽探索"）。

> ✅ 前端拿到 JSON 直接渲染；后端校验 `chart_type` 必须在白名单内，AI 不能乱发挥。

### 场景二端到端流程
见 `examples/10-pipeline/report_generation_pipeline.py` 的 `answer_follow_up()`，并配 `examples/09-conversation/drilldown_trace.md`（一次完整 4 轮对话 trace，含**指代消解、实体切换、越权兜底**三类关键用例，可直接当回归测试）。

---

# 第三部分 · 一步一步落地（实施步骤）

> 建议按下面顺序推进，每步都有明确产出物。可先做 MVP（见第四部分裁剪）。

### Step 1：建指标库（数据/后端团队）
产出：`indicator_catalog.yaml` + 每个指标的取数实现（OLAP/物化视图/预计算宽表）。
验收：能用 `get_indicator(IND_X, period, filters)` 取到正确数字，口径全公司统一。
> 这是地基。报告和追问都依赖它，必须先有、且口径唯一。

### Step 2：写模板 + 映射契约（产品/业务团队 + 后端）
产出：`report_template.md` + `semantic_binding.json` + schema 校验。
验收：模板里每个 `{{slot:*}}` 都能在契约里找到绑定，CI schema 校验通过。

### Step 3：做报告生成服务（后端 + AI 团队）
产出：`generate_report()`，先把所有 data_slot 硬取数填好（此时报告已是"有数字没解读"的半成品）。
验收：数字与 BI 系统对账 100% 一致。
> 关键里程碑：到这一步，即使 AI 一个字都不写，报告的数字已经完全正确。

### Step 4：接 Prompt 库写解读（AI 团队）
产出：每章节一个 `PROMPT_*.md`；接入 LLM；加 `validate_no_hallucination`。
验收：解读只引用注入数字；阈值判断符合业务规则；字数受控。

### Step 5：生成版本快照（后端）
产出：`make_snapshot()` + 落库 + hash。
验收：用 `snapshot_id` 能 1:1 还原报告；血缘字段齐全。
> 做完 Step 1~5，**场景一闭环**。可以先上线"只读报告"。

### Step 6：封装技能库 Skills（后端，Java）
产出：`get_indicator / by_dimension / root_cause / trend / resolve_entity` 等受控 API + 权限校验。
验收：非法 indicator/dimension 被拒；越权 org 被拦；SQL 注入打不进来。

### Step 7：写元数据字典 + 接 function calling（AI 团队）
产出：`metadata_dictionary.yaml` + 追问主循环 `answer_follow_up()`（限制最大工具步数）。
验收：常见追问能正确路由到 skill 并填对参数。

### Step 8：会话焦点管理（后端 + AI）
产出：`focus_state` 存储 + 继承规则 + 指代消解。
验收：`drilldown_trace.md` 的多轮用例全部通过。

### Step 9：图表协议 + 前端渲染（AI 团队 + 前端）
产出：`chart_spec` 协议 + 前端图表引擎 + `validate_chart_spec`。
验收：line/bar/table 等都能稳定渲染；非法 chart_type 被拦。
> 做完 Step 6~9，**场景二闭环**。

### Step 10：评测与防护（全员）
- **数字对账**：报告/追问的数字 vs BI，自动 diff。
- **幻觉评测**：构造"数据里没有的问法"，看 AI 是否老老实实说"数据不足/不支持"。
- **越权/注入红队测试**：见 trace 第 4 轮兜底用例。
- **回归集**：把 `drilldown_trace.md` 这类 trace 固化成自动化测试。

---

# 第四部分 · MVP 裁剪、团队分工与避坑

## MVP 最小闭环（想最快跑起来，砍掉这些）
- 场景一 MVP：1 个模板 + 5~8 个核心指标 + 2~3 个章节 Prompt + 快照。**先不做血缘的全部字段**，只存 frozen_values + 模型版本。
- 场景二 MVP：只做 3 个 skill（`get_indicator` / `get_indicator_by_dimension` / `get_root_cause_analysis`）+ 元数据字典 + 焦点继承（只做"周期继承"和"实体指代"两条规则）。图表先只支持 `line_chart` / `bar_chart` / `table`。

## 团队分工
| 团队 | 负责 |
|---|---|
| 产品/业务 | 报告模板、各章节业务解读逻辑、业务阈值规则 |
| 数据/后端 | 指标库、映射契约取数、Skills 受控 API、权限、快照 |
| AI/算法 | 章节 Prompt、防幻觉校验、追问意图识别与工具编排、图表协议生成 |
| 前端 | 报告渲染、图表引擎、追问交互 |

## 高频避坑清单
1. **别让 AI 取数/算数**：所有数字必须来自代码取数后注入。违反必幻觉。
2. **指标库要唯一口径**：同一个"销售额"全公司只能有一个定义，否则报告和追问对不上。
3. **org 权限后端注入**：永远不要相信 AI 传来的 org_id / 用户身份。
4. **fail-fast**：契约缺绑定、指标缺数据，宁可报错也别让 AI 圆场。
5. **快照先冻结再写文字**：保证文字只能基于已冻结的数据，杜绝"边写边变"。
6. **工具步数要设上限**：`MAX_TOOL_HOPS`，防止追问时模型无限调用。
7. **能力边界要兜底**：没有对应 skill 的问题，明确告知"暂不支持"，不许编。
8. **图表 chart_type 白名单**：协议严格枚举，前端才稳定。

---

## 配套示例文件索引

| 组件 | 文件 |
|---|---|
| 报告模板 | `examples/01-templates/report_template.md` |
| 映射契约 + Schema | `examples/02-contracts/semantic_binding.json` / `.schema.json` |
| 指标库目录 | `examples/02-contracts/indicator_catalog.yaml` |
| 章节推理 Prompt | `examples/03-prompts/PROMPT_COMPLIANCE_V2.md` |
| 版本快照 | `examples/04-snapshots/report_snapshot.json` |
| 技能库清单 + Java 实现 | `examples/05-skills/skills_manifest.json` / `IndicatorSkillController.java` |
| 元数据字典 | `examples/06-metadata/metadata_dictionary.yaml` |
| 会话焦点状态 | `examples/07-session/focus_state.json` |
| 图表渲染协议 | `examples/08-ui/chart_spec.json` |
| 多轮追问 trace | `examples/09-conversation/drilldown_trace.md` |
| 端到端流水线 | `examples/10-pipeline/report_generation_pipeline.py` |
