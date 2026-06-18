# 报告开发 Copilot（Authoring Agent）—— 用 AI 智能体对话式开发报告

> 回答："开发报告能不能通过 AI 智能体互动开发？" —— **能，且推荐**。
> 但它是**开发态的 Agent**，和运行态的"追问 Agent"是两码事：
> - 追问 Agent：调"查数 Skill" → 产出**答案**（给最终用户）。
> - 报告开发 Agent：调"**开发态 Skill**" → 产出**制品**（报告模板 + 映射契约 + 章节 Prompt 草稿），交人确认、过评测再发布（给报告作者）。

---

## 0. 设计哲学（与全方案一致）
> **确定性的事交给代码，不确定的事交给 AI。**

在"开发报告"里：
- **AI 负责（不确定）**：听懂业务诉求、推荐用哪些指标/维度、起草章节解读措辞、给布局建议。
- **代码负责（确定）**：把选定指标**生成映射契约**、**schema 校验**、**只允许 certified 指标**、**试生成预览取真数**、**跑评测门禁**、**版本化发布**。

=> AI 只"起草和建议"，**真正落库的契约由系统生成并校验**，绝不让 AI 编口径/编绑定。这样既对话化、又不失控。

---

## 1. 开发态 Skill 清单（Authoring Agent 能调的工具）
> 注意：这些是**开发态 Skill**，产物是"制品草稿/校验结果"，不是查询答案。同样用 MCP 暴露、受权限控制。

```json
{
  "authoring_skills": [
    {
      "name": "search_certified_metrics",
      "desc": "按业务意图检索【已认证】指标/维度(只返回 certified=true)，供作者挑选。",
      "args": { "intent_text": "string", "top_k": "int" }
    },
    {
      "name": "suggest_template_outline",
      "desc": "根据报告主题，推荐章节结构 + 每章建议指标/图表(草稿，待人确认)。",
      "args": { "topic": "string", "audience": "string" }
    },
    {
      "name": "generate_binding",
      "desc": "把作者确认的'槽位→指标'生成 semantic_binding.json(系统生成,非AI手写)，含 format/thresholds。",
      "args": { "slots": "array", "template_id": "string" }
    },
    {
      "name": "validate_contract",
      "desc": "对生成的契约跑 JSON-Schema + 指标存在性 + 维度合法性校验，返回错误清单(fail-fast)。",
      "args": { "binding": "object" }
    },
    {
      "name": "draft_section_prompt",
      "desc": "为某章节起草推理 Prompt + 结构化 schema 草稿(含业务阈值占位)，待人编辑。",
      "args": { "section": "string", "feed_slots": "array" }
    },
    {
      "name": "trial_generate",
      "desc": "用某机构/周期试生成报告预览(走真实运行态取数+快照)，让作者看真实效果。",
      "args": { "template_id": "string", "org_id": "string", "period": "string" }
    },
    {
      "name": "run_eval",
      "desc": "对草稿报告跑评测(数值对账/防幻觉/字数等),返回是否过门禁。",
      "args": { "snapshot_id": "string" }
    },
    {
      "name": "publish_artifact",
      "desc": "把'模板+契约+Prompt'作为新版本提交注册中心(需人确认+评测通过)。",
      "args": { "template_id": "string", "version": "string" }
    }
  ]
}
```

---

## 2. 对话式开发报告（人在环 trace 示例）

**作者：** 我要做一个"门店月度合规经营报告"，给区域合规负责人看。

1. Agent 调 `suggest_template_outline(topic="月度合规经营", audience="区域合规负责人")`
   → 建议大纲（草稿）：①整体概览 ②合规分析 ③风险与建议；并 `search_certified_metrics` 推荐指标。
   **Agent：** 建议三章。合规分析章我推荐这几个**已认证**指标：合规率、处方药合规率、DTP 的 DOT。要加吗？还想看哪些维度？

**作者：** 可以。合规分析按"处方类型"能拆吗？再加个销售额环比。

2. Agent 校验：`search_certified_metrics` 确认"销售额"已认证、"合规率支持 prescription_type 维度"。
   若作者要的指标**未认证** → Agent 明确告知"该指标未认证，不能进报告，可走认证流程或换 X"。
   **Agent：** 合规率支持按处方类型拆 ✅；销售额(含环比)已认证 ✅。我把它们放进槽位。

3. 作者确认后，Agent 调 `generate_binding(...)` → **系统生成** `semantic_binding.json`，再 `validate_contract` 校验。
   **Agent：** 契约已生成并校验通过（5 个数据槽 + 3 个解读槽）。

4. Agent 调 `draft_section_prompt("合规分析", ...)` → 起草章节 Prompt（含阈值占位：合规率<85%=高风险…）。
   **Agent：** 我起草了合规章解读 Prompt，阈值我先按"合规率<85%高风险、DOT<0.8 点名"，你可以改。

5. Agent 调 `trial_generate(org_id=ORG1024, period=2026-05)` → 用真数据预览。
   **Agent：** 这是用康民大药房 5 月数据的预览效果（附渲染图）。数字已与 BI 对账一致。

6. 作者微调措辞/阈值 → Agent 调 `run_eval` → 过门禁 → 作者点"发布" → `publish_artifact`。
   **Agent：** 评测通过（blocker 100%）。已发布为 `pharmacy_monthly v1.2`，业务方现在可以生成/查看/追问了。

> 全程：**AI 提建议 + 起草，人确认 + 编辑，系统生成契约 + 校验 + 评测 + 版本发布**。

---

## 3. Authoring Agent 的护栏（开发态也要管住）
1. **只能绑 certified 指标**：未认证指标不许进报告（口径不失控）。
2. **契约/ schema 由系统生成校验**：AI 不手写绑定，避免编错指标/口径。
3. **人在环强制**：关键步骤(选指标、发布)必须人确认，Agent 不能自动发布上线。
4. **发布必过评测门禁**：数值对账/防幻觉等 blocker 100% 才能发。
5. **全部制品化 + 版本化 + 可回滚**：草稿也存版本，发布走灰度。
6. **权限**：作者只能在其数据权限范围内 `trial_generate`(行级权限照常生效)。

---

## 4. 和"低代码报告设计器"是互补，不是二选一
| 方式 | 适合 | 特点 |
|---|---|---|
| **Authoring Agent(对话式)** | 不熟工具的业务方、快速起草、"我想要个 XX 报告" | 自然语言、AI 推荐与起草、上手快 |
| **低代码设计器(拖拽)** | 精细排版、像素级调整、批量改 | 可视化、可控、适合精修 |

**推荐组合**：**Agent 起草 → 自动落到低代码设计器 → 人精修 → 评测发布**。即"Agent 出 80% 草稿，设计器做 20% 精修"，兼顾效率与可控。

---

## 5. 一句话结论
**开发报告完全可以对话式 AI 智能体互动开发**：用一个**开发态 Authoring Agent + 开发态 Skill**，让业务"说需求"，AI 推荐指标、起草契约与 Prompt、试生成预览；但**契约生成、校验、评测、发布由系统把关，人在环确认**——既把开发门槛降到"会说话就行"，又始终守住口径、权限与质量。
