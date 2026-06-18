# AI 报告生成 + 报告内灵活追问 —— 2.0 落地方案

> 在 1.0（确定性数据 + AI 解读 + Skills + 会话状态 + 图表协议）基础上，按方案评审建议升级为更标准、更可扩展、可长期运营的架构。
> 配套示例见本目录 `v2/examples/`，文中逐一引用。**1.0 的核心哲学不变**：确定性的事交给代码，不确定的事交给 AI。

---

## 0. 2.0 相对 1.0 改了什么（一张表看懂）

| 维度 | 1.0 做法 | 2.0 升级 | 解决的问题 |
|---|---|---|---|
| 指标口径 | 指标库内嵌 SQL（手搓） | **语义层 Semantic Layer**（A） | 口径漂移、维护地狱 |
| 追问取数 | 只用固定 Skills | **Skills + 受约束语义查询**（B） | 长尾问题答不了 |
| 元数据喂法 | 整份字典塞进 Prompt | **元数据 RAG 召回 Top-K**（B） | context 爆、成本高、路由乱 |
| 图表协议 | 自研 chart_spec | **Vega-Lite 标准 + 结构化输出**（C） | 重造轮子、解析脆弱 |
| 质量保障 | 仅回归测试 | **Eval harness + LLM-judge + 门禁**（D） | 改一处不知好坏 |
| 可观测 | 无 | **Trace + 语义缓存 + 大小模型分工**（D/F） | 不可运营、贵、慢 |
| 数字正确 | 校验"数字∈输入" | **+ 数值自校验(回答==工具返回)**（E） | 转述错误 |
| 工具暴露 | 私有 manifest | **MCP 标准**（G） | 难复用、绑死模型 |
| 歧义处理 | 直接取数 | **低置信→澄清反问** | 乱猜 |

---

## 第一部分 · 升级点详解

### A. 语义层取代手搓指标库（最高价值）
`v2/examples/01-semantic-layer/metrics.yaml`：只声明**度量 + 维度 + 实体 + 数据源**，由 dbt Semantic Layer / Cube / Malloy 编译成 SQL。报告、追问、BI 看板**共用同一套口径**，根除漂移。
- 指标分 `simple / ratio`（如合规率=合规数/总数），支持 `scope`（rx/otc）、`transforms`（mom/yoy/trend/by_dim/contribution）。
- 治理元信息（`certified` / `freshness_sla` / `pii_level`）被快照血缘与评测引用；**报告只允许引用 `certified=true` 的指标**。

### B. 混合取数：Skills + 受约束语义查询 + 元数据 RAG
- AI 对长尾问题产出 `v2/examples/01-semantic-layer/semantic_query.example.json` 里的**语义查询**（不是裸 SQL）；后端校验（指标/维度/scope 合法 + 行级权限 + 自动 LIMIT）后交语义层执行。安全≈Skill，灵活≈SQL。
- 元数据不再整份进 Prompt，而是 `v2/examples/06-metadata-rag/retrieval_config.yaml`：对指标/维度/few-shot 建向量索引，每轮只召回 Top-K，控制 token 预算。

### C. Vega-Lite + 结构化输出
- 图表用 `v2/examples/08-ui-vega/chart_spec_vega.json` 的 **Vega-Lite** 标准语法，前端用现成渲染器；`mark` 白名单 + 字段必须来自工具返回列。
- 解读和图表都用模型的**结构化输出（JSON-Schema 约束解码）**产出，免去脆弱的文本解析（见 `v2/examples/03-prompts/PROMPT_COMPLIANCE_V2.md` 的 response schema）。

### D. 评测 + 可观测（让方案能长期运营）
- `v2/examples/09-eval/`：金标准集 `eval_golden_set.jsonl`（含数值对账、防幻觉、指代消解、澄清、越权、图表类型、数值自校验）、`eval_config.yaml`（blocker 必须 100% 过的上线门禁）、`llm_judge_prompt.md`（评解读质量）。CI 每次改动自动跑分、回归报警。
- `v2/examples/10-observability/observability.yaml`：全链路 Trace（Langfuse/OTel GenAI）、语义缓存、告警。

### E. 数值自校验
结构化输出里强制 `used_numbers[{field,value}]`；校验器逐一比对注入数据/工具返回，不一致即重写或降级。解决"AI 把 -4.2pct 说成 -4.2%"这类转述错误。

### F. 大小模型分工
意图分类/实体消歧/缓存判定用**便宜小模型**，解读/编排/图表用**强模型**，显著降本降延迟（见 observability.yaml 的 `model_routing`）。

### G. MCP 暴露技能
`v2/examples/05-skills-mcp/mcp_tools.json` 用 **Model Context Protocol** 暴露 `run_semantic_query / resolve_entity / search_metadata`；换模型、接第三方 Agent 即插即用。Java 实现见 `SemanticQuerySkill.java`（校验→行级权限→编译执行→审计）。

---

## 第二部分 · 端到端流程
见 `v2/examples/11-pipeline/pipeline_v2.py`：
- `generate_report()`：语义层取数 → 快照(记编译SQL指纹) → 结构化输出写解读 → **数值自校验** → 上线前 preflight eval → 渲染。
- `answer_follow_up()`：小模型路由+缓存 → 元数据RAG → MCP工具/语义查询(权限注入) → 低置信澄清 → 结构化+Vega输出 → 数值自校验 → 更新焦点+缓存+Trace。

完整多轮 trace（含指代、长尾组合、澄清、越权兜底）：`v2/examples/12-conversation/drilldown_trace_v2.md`。

---

## 第三部分 · 一步一步落地（在 1.0 基础上的迁移路径）

| 阶段 | 任务 | 产出 / 验收 |
|---|---|---|
| 进阶一-1 | 部署语义层，迁移指标定义 | `metrics.yaml`；报告数值 vs BI 对账 100% |
| 进阶一-2 | data_slot 改绑语义查询 | `semantic_binding_v2.json`；快照记录编译SQL指纹 |
| 进阶一-3 | 搭评测 + Trace | golden_set 跑通，CI 门禁生效；Trace 可见每轮调用 |
| 进阶一-4 | 元数据 RAG | 建向量索引；追问只注入召回的 Top-K |
| 进阶二-1 | 受约束语义查询打开长尾 | 长尾组合问题可答且安全 |
| 进阶二-2 | Vega-Lite + 结构化输出 | 图表稳定渲染；解析零字符串 hack |
| 进阶二-3 | 数值自校验 + 低置信澄清 | num/clarify 用例全过 |
| 进阶三-1 | MCP 暴露技能 | 第三方/换模型可复用 |
| 进阶三-2 | 语义缓存 + 大小模型分工 | p95 延迟与成本下降 |

> 兼容性：1.0 已上线的可平滑迁移——先把指标搬进语义层、报告链路切到语义查询（用户无感），再逐步打开追问的混合取数与评测门禁。

---

## 第四部分 · 医药合规与避坑（2.0 强化）
1. **优先可私有化部署的开源权重模型**或合规私有推理；快照血缘支撑审计。
2. **行级权限后端强制注入**，永不信任 AI 传入 org（`SemanticQuerySkill` + `enforce_permissions`）。
3. **报告只用 certified 指标**；追问可放宽但仍须语义层注册。
4. **blocker 评测必须 100% 过**才能上线（数值对账/防幻觉/越权/边界/数值自校验）。
5. 其余 1.0 铁律（fail-fast、快照先冻结、工具步数上限、能力边界兜底）继续保留。

---

## 配套示例索引（v2）
| 组件 | 文件 |
|---|---|
| 语义层 + 语义查询 | `examples/01-semantic-layer/metrics.yaml` / `semantic_query.example.json` |
| 模板 + v2 映射契约 | `examples/02-templates/report_template.md` / `semantic_binding_v2.json` |
| 章节 Prompt(结构化输出) | `examples/03-prompts/PROMPT_COMPLIANCE_V2.md` |
| 版本快照(含编译SQL指纹) | `examples/04-snapshots/report_snapshot_v2.json` |
| MCP 技能 + Java 实现 | `examples/05-skills-mcp/mcp_tools.json` / `SemanticQuerySkill.java` |
| 元数据 RAG | `examples/06-metadata-rag/retrieval_config.yaml` |
| 会话焦点(含澄清) | `examples/07-session/focus_state_v2.json` |
| Vega-Lite 图表协议 | `examples/08-ui-vega/chart_spec_vega.json` |
| 评测框架 | `examples/09-eval/eval_golden_set.jsonl` / `eval_config.yaml` / `llm_judge_prompt.md` |
| 可观测 + 缓存 + 路由 | `examples/10-observability/observability.yaml` |
| 端到端流水线 | `examples/11-pipeline/pipeline_v2.py` |
| 多轮追问 trace | `examples/12-conversation/drilldown_trace_v2.md` |
