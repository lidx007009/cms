# AI 报告生成 + 报告内灵活追问 —— 完整可落地方案（v2.1）

> 这是一份**自包含**的完整方案：从零到上线、从生成报告到无尽追问、再到主动洞察与持续优化，你**只读本目录即可**，无需对照其它版本。
> 适用场景示例：连锁药店月度经营分析（销售额、合规率、处方流转率、DTP/DOT 等）。结构通用，可迁移到其它领域。
> 配套**可直接复制**的示例文件在 `examples/`，文中逐一引用。

---

## 0. 设计哲学（贯穿全文的一条线）

> **确定性的事交给代码，不确定的事交给 AI。**

| 类型 | 谁来做 | 为什么 |
|---|---|---|
| 取数、算同环比、格式化、画图、权限 | 代码 / 语义层 / 受控 API | 必须 100% 准确、可复现、可审计，绝不能让模型"猜数字" |
| 文字解读、意图理解、工具编排、叙事 | AI（LLM） | 这才是模型的价值：灵活、像人 |

违背这条原则（让 AI 直接写 SQL、直接报数字）就会幻觉、对不上账、无法落地。下文每个组件都为这条原则服务。

### 全景架构（一张图看懂）

```
                         ┌──────────────── 语义层(SSOT) examples/01 ────────────────┐
                         │   唯一口径：度量/维度/实体；编译成SQL；报告·追问·洞察共用    │
                         └───────────────────────────┬──────────────────────────────┘
   ┌────────────── A. 生成报告(确定性) ──────────────┐│┌───────── B. 报告内追问(探索性) ─────────┐
   │ 模板02 →映射契约02 →语义层硬取数 →版本快照04     │││ 统一护栏13 →小模型路由/缓存10 →记忆15+RAG06 │
   │      →章节Prompt03→LLM写解读→数值自校验          │││  →MCP工具05/语义查询/预测14 →结构化+Vega08  │
   └─────────────────────────────────────────────────┘││  →数值自校验 →更新焦点07                    │
                         ▲ 用户看完报告 → 一键追问      │└──────────────────────┬───────────────────┘
   ┌────────────── C. 主动洞察(无需提问) ─────────────┐│                       │ 用户反馈(👍/👎/修正)
   │ 巡检11 →检测异常 →自动归因 →叙事 →推送(带seed)   │┘                       ▼
   └─────────────────────────────────────────────────┘   D. 反馈飞轮12：回灌few-shot/重排/评测集
                                                          贯穿全程：评测门禁09 + 可观测10 + 护栏13
```

九大支柱：**①语义层 ②映射契约+快照 ③Prompt+结构化输出 ④MCP受控技能+语义查询 ⑤元数据RAG ⑥会话焦点+长期记忆 ⑦Vega图表协议 ⑧评测+可观测+护栏 ⑨主动洞察+反馈飞轮**。

---

# 第一部分 · 生成 AI 报告（场景 A）

你已有报告模板（结构、候选指标、成篇逻辑）。要让 AI **稳定、忠实**地填好，需要下面 4 件事。

## 1.1 语义层：全系统唯一口径（SSOT）
`examples/01-semantic-layer/metrics.yaml`：只声明**度量(measure) + 维度(dimension) + 实体(entity) + 数据源**，由 dbt Semantic Layer / Cube / Malloy 在运行时编译成 SQL。
- 报告、追问、主动洞察、BI 看板**共用同一套口径**，根除"同一个销售额各处算法不一样"的漂移。
- 指标分 `simple`（如销售额）/ `ratio`（如合规率=合规数/总数），支持 `scope`(rx/otc)、`transforms`(mom/yoy/trend/by_dim/contribution)。
- 治理元信息 `certified`/`freshness_sla`/`pii_level` 被快照与评测引用；**报告只允许引用 `certified=true` 的指标**。
> 这是地基。绝不让 AI 碰裸 SQL，AI 只产"语义查询"，由本层编译执行（见 `examples/01-semantic-layer/semantic_query.example.json`）。

## 1.2 模板 + 语义映射契约
- 模板 `examples/02-templates/report_template.md`：只放结构 + 两种占位符——`{{slot:*}}`（数据槽，后端填）/`{{insight:*}}`（推理槽，AI 填）/`<!-- chart-anchor -->`（图表锚点）。
- 契约 `examples/02-templates/semantic_binding.json`：每个 `slot` 绑定一个**语义层查询** + `format` + `thresholds` + `on_missing`。渲染时后端按契约取数→格式化→打 `level(good/warn/bad)`→填模板，**全程无 AI**。
- 校验 `examples/02-templates/semantic_binding.schema.json`：CI 跑 schema，占位符没绑定/指标不存在直接挡在合并前（fail-fast）。

## 1.3 章节推理 Prompt（结构化输出）
`examples/03-prompts/PROMPT_COMPLIANCE.md`：每个 `{{insight:*}}` 一个 Prompt，含 4 块：
1. **System**（角色 + 铁律：唯一信息源是注入 JSON、禁编造、缺数据说"数据不足"、登记 used_numbers）。
2. **Rules**（业务阈值写死：合规率<85%=高风险必须解释；DOT<0.8 必须点名；环比<-3% 必须用 breakdown 归因）。
3. **Response Schema**（结构化输出 `{conclusion, attribution, dtp_note, action, used_numbers[]}`，便于数值自校验）。
4. **Input Data**（运行时注入，AI 不可改）。文件末尾有完整拼装示例。

## 1.4 版本快照与血缘
`examples/04-snapshots/report_snapshot.json`：生成那一刻**先冻结再写文字**，记录：
- `frozen_values`（所有 slot 值+展示+level）、`extra_data`（章节明细）、`generated_insights`（AI 文字+用的 prompt+token+numeric_check）。
- `lineage`：数据截止、数据源新鲜度、pipeline run、语义层版本、**每个 slot 的编译 SQL 指纹(行级可审计)**、LLM 模型/版本/温度、代码 git revision、评测结果。
- `integrity`：hash 防篡改。
> 作用：报告可 1:1 复现、可对账、可审计；追问也基于它，永远对得上。

**场景 A 端到端**：见 `examples/16-pipeline/pipeline.py` 的 `generate_report()`。

---

# 第二部分 · 报告内追问（场景 B，无尽探索）

用户会问超出模板的问题（"为什么阿托伐他汀5月合规率掉这么多？"→"那它医保/自费销售额趋势？"→"下月预计多少？"）。需要下面 6 件事。

## 2.1 MCP 受控技能 + 语义查询（取数主力）
- `examples/05-skills-mcp/mcp_tools.json`：用 **MCP(Model Context Protocol)** 标准暴露技能（`run_semantic_query`/`resolve_entity`/`search_metadata`/`forecast_metric`），换模型/接第三方 Agent 即插即用。
- **AI 不写裸 SQL**：常见问题命中工具；长尾组合则产出**受约束的语义查询**（见 `semantic_query.example.json`），后端校验(指标/维度/scope 合法 + 行级权限 + 自动 LIMIT)后交语义层执行。安全≈固定 API，灵活≈SQL。
- Java 实现 `examples/05-skills-mcp/SemanticQuerySkill.java`：校验合法性→**org 由后端注入(绝不信任 AI 传入)**→编译执行→审计留痕。

## 2.2 元数据 RAG（喂得准、喂得省）
`examples/06-metadata-rag/retrieval_config.yaml`：指标/维度上百个时不要整份塞进 Prompt。对指标/维度/few-shot 建向量索引，每轮只召回 Top-K + 重排，控制 token 预算。低于命中阈值则走澄清。

## 2.3 会话焦点 + 长期记忆
- 会话内 `examples/07-session/focus_state.json`：记录 `metric/period/filters/last_entity...` + **继承规则**（指代"它"、省略"B药呢"、只换指标/实体、"整体"清空 filters）+ **低置信→澄清**(不硬猜)。
- 跨会话 `examples/15-memory/user_memory.example.json`：长期偏好(常看指标、默认周期、关注清单)以**软提示**注入，优先级低于当轮指令，**可见/可编辑/可关闭**、排除 PII。

## 2.4 受控预测（从"为什么"到"会怎样"）
`examples/14-predictive/forecast_skill.json`：`forecast_metric` 由**后端统计/ML 模型**算，返回点估计 + **80/95% 置信区间** + 方法 + 假设 + caveat。纪律：必须标注"预测"、与事实严格区分、样本不足只给方向、同样走数值自校验。

## 2.5 Vega-Lite 图表协议（AI 出 spec，不画图）
`examples/08-ui-vega/chart_spec_vega.json`：AI 回答 = `text` + `charts[]`(Vega-Lite spec) + `follow_up_suggestions`。`mark` 白名单、字段必须来自工具返回列、行数超限降级 table。前端用现成 Vega 渲染器。

## 2.6 数值自校验（防转述错误）
结构化输出强制 `used_numbers[{field,value}]`；校验器逐一比对工具返回，**不一致即重写或降级**。解决"把 -4.2pct 说成 -4.2%"这类错误。

**场景 B 端到端**：见 `examples/16-pipeline/pipeline.py` 的 `answer_follow_up()`；完整多轮 trace（含指代、长尾、预测、澄清、越权/注入兜底）见 `examples/17-conversation/drilldown_trace.md`。

---

# 第三部分 · 主动洞察（场景 C，无需提问）

让系统"不用问也能发现问题"，并把发现的问题一键导回追问。
- `examples/11-proactive-insights/anomaly_scan_config.yaml`：定时巡检 → 多检测器并行（红线/环比突变/Zscore/趋势拐点）→ **打分排序只推 TopN**(防刷屏) → 自动归因 → 叙事 → 推送/高危升级。只用 certified 指标、静默时段、可"不再提醒"。
- `examples/11-proactive-insights/insight_digest.example.json`：产物是"经营异常摘要卡片"，每条带**根因 + 证据数字 + 建议 + `seed_question`(一键进入追问)**，把主动洞察与无尽追问打通成闭环。
- `examples/11-proactive-insights/narrative_prompt.md`：把结构化异常翻成人话，复用同一套铁律与数值自校验。

**场景 C 端到端**：`pipeline.py` 的 `proactive_scan()`。

---

# 第四部分 · 持续优化与安全（贯穿全程）

## 4.1 反馈飞轮（越用越准，不微调）
- `examples/12-feedback-flywheel/feedback_event.schema.json`：结构化采集 👍/👎/采纳/**用户修正**/重试/数字报错 + 完整上下文。
- `examples/12-feedback-flywheel/flywheel_pipeline.py`：正样本(尤其 edited)→ few-shot 候选；负样本 → **自动扩充评测 golden_set**(防回归) + 数字错立即告警；用反馈校准检索重排；**回灌后必须过评测门禁才发布**。
- `examples/12-feedback-flywheel/fewshot_promotion_rules.yaml`：few-shot 作为"活资产"的准入/晋升(影子先行)/淘汰/**一键回滚**。比 RLHF/微调更稳、可解释、可回滚。

## 4.2 评测框架（敢上线的分水岭）
`examples/09-eval/`：金标准集 `eval_golden_set.jsonl`(数值对账/防幻觉/指代/澄清/越权/图表/数值自校验) + `eval_config.yaml`(**blocker 必须 100% 过的上线门禁**) + `llm_judge_prompt.md`(评解读质量)。CI 每次改动自动跑分、回归报警。

## 4.3 可观测 + 缓存 + 模型分工
`examples/10-observability/observability.yaml`：全链路 Trace(Langfuse/OTel GenAI)、语义缓存(省钱降延迟)、大小模型分工(小模型路由/强模型合成)、成本护栏。

## 4.4 统一安全护栏（医药合规重点）
`examples/13-guardrails/`：独立中间层，包住整个链路三道关——
- **输入关**：用户 prompt 注入；★**数据内容注入**(药品名/备注字段被塞指令，医药高危、最易忽略)。
- **动作关**：行级权限强制、仅 certified、limit/范围/步数、禁写禁导出。
- **输出关**：数值自校验、PII 脱敏(`pii_policy.yaml`)、合规过滤(禁越界诊疗建议)、防幻觉。
- 红队用例 `injection_test_suite.jsonl` 进 CI 必跑。

---

# 第五部分 · 一步一步落地

> 按下面顺序推进，每步有明确产出与验收。可先做 MVP（见后）。

| 步骤 | 做什么 | 验收 |
|---|---|---|
| 1 | 部署语义层，定义指标 `metrics.yaml` | 报告数值 vs BI 对账 100% 一致；口径唯一 |
| 2 | 模板 + 映射契约 + schema 校验 | 每个 `{{slot}}` 有绑定，CI 通过 |
| 3 | 报告生成：先把 data_slot 硬取数填好 | 即使 AI 不写字，数字已全对（里程碑） |
| 4 | 接 Prompt 库 + 结构化输出 + 数值自校验 | 解读只引用注入数字、阈值判断正确 |
| 5 | 版本快照 + 血缘 + hash | 用 snapshot_id 能 1:1 还原报告 |
| — | **以上完成 → 场景 A 闭环，可上线只读报告** | |
| 6 | MCP 技能 + 语义查询 + 行级权限 | 非法指标/越权/注入被拦 |
| 7 | 元数据 RAG + 追问主循环(步数上限) | 常见追问正确路由并填对参数 |
| 8 | 会话焦点 + 指代消解 + 低置信澄清 | `drilldown_trace.md` 用例全过 |
| 9 | Vega-Lite 协议 + 前端渲染 | 图表稳定渲染，非法 chart 被拦 |
| — | **以上完成 → 场景 B 闭环** | |
| 10 | 统一 Guardrails + 红队 CI | 10 条注入用例全过 |
| 11 | 评测框架 + Trace + 缓存 | 门禁生效；链路可观测 |
| 12 | 反馈采集 + 飞轮 | 负样本自动进 golden_set；few-shot 可晋升/回滚 |
| 13 | 主动洞察巡检 | 定时生成 digest，可一键追问，只推 TopN |
| 14 | 受控预测 + 长期记忆 | 预测带区间与"预测"标注；个性化默认口径生效 |

### MVP 最小闭环（最快跑起来）
- 场景 A：语义层 5~8 个核心指标 + 1 模板 + 2~3 章节 Prompt + 快照。
- 场景 B：MCP 只上 `run_semantic_query`+`resolve_entity`+元数据 RAG + 焦点继承(周期继承/实体指代两条规则) + Vega(line/bar/table)。
- 安全/评测：先上**行级权限 + 数值自校验 + 数值对账评测**这三条底线，其余增量后补。

---

# 第六部分 · 团队分工 & 避坑

| 团队 | 负责 |
|---|---|
| 产品/业务 | 报告模板、各章节解读逻辑、业务阈值规则、洞察推送策略 |
| 数据/后端 | 语义层、映射契约取数、MCP 受控技能、行级权限、快照、巡检/飞轮管道 |
| AI/算法 | 章节 Prompt、意图识别与工具编排、结构化输出、数值自校验、RAG、评测 |
| 平台/安全 | Guardrails、可观测、缓存、模型路由、PII 合规 |
| 前端 | 报告渲染、Vega 图表引擎、追问交互、洞察卡片 |

**高频避坑清单**
1. 别让 AI 取数/算数——所有数字来自语义层取数后注入。
2. 指标口径唯一(语义层 SSOT)，否则报告和追问对不上。
3. org 权限后端强制注入，永不信任 AI 传入。
4. fail-fast：契约缺绑定、指标缺数据，宁可报错不让 AI 圆场。
5. 快照先冻结再写文字。
6. 工具步数设上限 `MAX_TOOL_HOPS`。
7. 能力边界要兜底，没有对应工具就明说"暂不支持"。
8. 图表 chart_type/Vega mark 白名单。
9. 数值自校验是 blocker，回答数字必须==工具返回。
10. 数据内容注入要中和(医药字段易藏指令)；PII 默认脱敏。
11. 预测必须标注"预测"+不确定性，与事实严格区分。
12. 评测 blocker 必须 100% 过才能上线；反馈回灌也要过门禁。

---

## 配套示例索引（examples/）

| # | 组件 | 文件 |
|---|---|---|
| 01 | 语义层 + 语义查询 | `01-semantic-layer/metrics.yaml` / `semantic_query.example.json` |
| 02 | 模板 + 映射契约 + Schema | `02-templates/report_template.md` / `semantic_binding.json` / `semantic_binding.schema.json` |
| 03 | 章节推理 Prompt | `03-prompts/PROMPT_COMPLIANCE.md` |
| 04 | 版本快照(含编译SQL指纹) | `04-snapshots/report_snapshot.json` |
| 05 | MCP 技能 + Java 实现 | `05-skills-mcp/mcp_tools.json` / `SemanticQuerySkill.java` |
| 06 | 元数据 RAG | `06-metadata-rag/retrieval_config.yaml` |
| 07 | 会话焦点(含澄清) | `07-session/focus_state.json` |
| 08 | Vega-Lite 图表协议 | `08-ui-vega/chart_spec_vega.json` |
| 09 | 评测框架 | `09-eval/eval_golden_set.jsonl` / `eval_config.yaml` / `llm_judge_prompt.md` |
| 10 | 可观测 + 缓存 + 路由 | `10-observability/observability.yaml` |
| 11 | 主动洞察 | `11-proactive-insights/anomaly_scan_config.yaml` / `insight_digest.example.json` / `narrative_prompt.md` |
| 12 | 反馈飞轮 | `12-feedback-flywheel/feedback_event.schema.json` / `flywheel_pipeline.py` / `fewshot_promotion_rules.yaml` |
| 13 | 统一 Guardrails | `13-guardrails/guardrails_config.yaml` / `injection_test_suite.jsonl` / `pii_policy.yaml` |
| 14 | 受控预测 | `14-predictive/forecast_skill.json` |
| 15 | 长期记忆 | `15-memory/user_memory.example.json` |
| 16 | 端到端流水线(A/B/C) | `16-pipeline/pipeline.py` |
| 17 | 多轮追问 trace | `17-conversation/drilldown_trace.md` |
