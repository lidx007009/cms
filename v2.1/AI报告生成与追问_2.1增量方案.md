# AI 报告生成 + 报告内追问 —— 2.1 增量方案

> 在 2.0（语义层 + 混合取数 + RAG + Vega-Lite + 结构化输出 + 评测/可观测 + MCP + 数值自校验）之上，
> 按"再领先半个身位、且不牺牲稳定性"的目标，补齐 **5 项增量**。
> 2.1 = 2.0 + 主动洞察 + 反馈飞轮 + 统一 Guardrails + 受控预测 + 长期记忆。
> 配套示例见本目录 `v2.1/examples/`。**前提：先落地 2.0，再叠加 2.1。**

---

## 0. 2.1 增量一览

| # | 增量 | 从→到 | 为什么稳 | 示例目录 |
|---|---|---|---|---|
| ① | 主动洞察 | 被动问答 → 主动巡检推送 | 复用语义层+归因+评测，离线跑、TopN 限流 | `01-proactive-insights/` |
| ② | 反馈飞轮 | 静态 few-shot → 反馈回灌的活资产 | 不微调/不训练，可回滚 | `02-feedback-flywheel/` |
| ③ | 统一 Guardrails | 分散护栏 → 输入/动作/输出三道关 | 独立中间层 + 红队 CI | `03-guardrails/` |
| ④ | 受控预测 | 描述/诊断 → 预测/建议 | 后端算、带不确定性、与事实严格区分 | `04-predictive/` |
| ⑤ | 长期记忆 | 会话内焦点 → 跨会话个性化 | 软提示注入、可编辑可关闭 | `05-long-term-memory/` |

> 优先级：**①②③ 是核心高 ROI**（先做）；④⑤ 锦上添花，按需。

---

## ① 主动洞察（Proactive Insights）
让系统"不用问也能发现问题"。
- `anomaly_scan_config.yaml`：定时巡检 → 多检测器并行（红线/环比突变/Zscore/趋势拐点）→ **打分排序只推 TopN**（防刷屏）→ 自动归因 → 叙事生成 → 推送/升级。
- `insight_digest.example.json`：产物是"经营异常摘要卡片"，每条带**根因 + 证据数字 + 建议 + `seed_question`（一键跳转到 2.0 追问）**，把"主动洞察"与"无尽追问"打通成闭环。
- `narrative_prompt.md`：把结构化异常翻成人话，复用 2.0 铁律（只用注入数字、结构化输出、`used_numbers` 供数值自校验）。
- 稳定性保障：只用 `certified` 指标、静默时段、用户可"不再提醒"。

## ② 反馈飞轮（Feedback Flywheel）
让系统"越用越准"，但**不碰模型训练**。
- `feedback_event.schema.json`：结构化采集 👍/👎/采纳/**用户修正**/重试/数字报错，并带完整上下文（query/工具调用/回答/召回命中）。
- `flywheel_pipeline.py`：正样本（尤其"用户把查询改对"的 edited）→ 进 few-shot 候选；负样本 → **自动扩充评测 golden_set**（防回归）+ 数字错立即告警；用反馈当相关性标签**校准检索重排**；**回灌后必须过评测门禁才发布**。
- `fewshot_promotion_rules.yaml`：few-shot 作为"活资产"的准入/晋升（影子先行）/淘汰/**一键回滚**治理。
- 为什么比 RLHF/微调稳：可解释、可回滚、改坏了秒退回上一版。

## ③ 统一 Guardrails（安全护栏层）
把 2.0 分散的护栏收敛成一个独立中间层，包住整个链路。
- `guardrails_config.yaml`：三道关——
  - **输入关**：用户 prompt 注入；★**数据内容注入**（药品名/备注字段被塞指令，医药高危，最易被忽略）。
  - **动作关**：行级权限强制、仅 certified、limit/范围/步数、禁写禁导出。
  - **输出关**：数值自校验、PII 脱敏、**合规过滤（禁越界诊疗建议）**、防幻觉。
- `injection_test_suite.jsonl`：10 条红队用例（含数据内容注入、越权、删数据、诊疗越界、PII、伪造数字），**进 CI 必跑**。
- `pii_policy.yaml`：患者姓名/手机号/身份证/处方号的分级脱敏 + 角色可见 + 审计留痕。

## ④ 受控预测（Predictive / Prescriptive）
从"发生了什么/为什么"扩展到"会怎样/该怎么办"。
- `forecast_skill.json`：`forecast_metric` 由**后端统计/ML 模型**算，返回点估计 + **80/95% 置信区间** + 方法 + 假设 + caveat。
- 纪律（关键）：预测必须**显式标注"预测"**、与事实数字**严格区分**、样本不足时只给方向不给点估计、同样走 `numeric_selfcheck`；严禁对个体患者做疗效/诊疗预测（被 ③ 的 compliance_filter 拦）。

## ⑤ 长期记忆（Long-term Memory）
跨会话个性化，但完全可控。
- `user_memory.example.json`：学习常看指标、默认周期、关注清单、简洁偏好；以**软提示检索注入**，优先级低于当轮明确指令；**用户可见/可编辑/可遗忘/可一键关闭**，排除 PII，留痕审计。

---

## 与 2.0 的集成点（改动很小，叠加式）
1. 追问主循环 `answer_follow_up`：最外层包 **Guardrails(③)**；进入前注入 **长期记忆(⑤)**；新增 `forecast_metric` 工具(④)。
2. 新增**离线巡检管道(①)**，独立调度，复用语义层+归因+叙事，产物推送并回链到追问。
3. 新增**飞轮管道(②)**，周期性消费反馈、更新 few-shot 与 reranker、回灌评测集。
4. 评测体系扩充：把 ③ 的红队用例、②自动新增的负样本并入 `eval_golden_set`，门禁不变（blocker 100%）。

---

## 落地顺序（在 2.0 之上）
| 步骤 | 做什么 | 验收 |
|---|---|---|
| 2.1-A | 统一 Guardrails(③) + 红队 CI | 10 条注入用例全过；越权/数据注入被拦 |
| 2.1-B | 反馈采集 + 飞轮(②) | 反馈入库；负样本自动进 golden_set；few-shot 可晋升/回滚 |
| 2.1-C | 主动洞察巡检(①) | 每周/每日生成 digest，可一键追问；只推 TopN |
| 2.1-D | 受控预测(④) | 预测带区间与"预测"标注，过数值自校验 |
| 2.1-E | 长期记忆(⑤) | 个性化默认口径生效，用户可编辑/关闭 |

> 建议先做 A（安全是底线）、再 B（让系统会成长）、再 C（提升主动价值），D/E 按业务需要排期。

---

## 示例索引（v2.1）
| 增量 | 文件 |
|---|---|
| ① 主动洞察 | `examples/01-proactive-insights/anomaly_scan_config.yaml` / `insight_digest.example.json` / `narrative_prompt.md` |
| ② 反馈飞轮 | `examples/02-feedback-flywheel/feedback_event.schema.json` / `flywheel_pipeline.py` / `fewshot_promotion_rules.yaml` |
| ③ Guardrails | `examples/03-guardrails/guardrails_config.yaml` / `injection_test_suite.jsonl` / `pii_policy.yaml` |
| ④ 受控预测 | `examples/04-predictive/forecast_skill.json` |
| ⑤ 长期记忆 | `examples/05-long-term-memory/user_memory.example.json` |
