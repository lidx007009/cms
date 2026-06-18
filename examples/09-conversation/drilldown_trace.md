# 端到端追问示例（一次完整多轮对话的内部 trace）

> 这份 trace 把"用户说话 → 焦点状态更新 → AI 选工具 → 后端取数 → AI 组织回答 + 图表"完整串起来，
> 是验证整套追问链路是否打通的"金标准用例"，也可直接当回归测试脚本。

场景：用户正在看 `SNAP-20260601-ORG1024-7f3a9c`（康民大药房 2026年5月报告）的合规章节，开始追问。

---

## 第 1 轮

**用户：** 为什么阿托伐他汀这个月合规率掉这么多？

1. **意图识别**：root_cause（命中"为什么/掉")。
2. **实体消歧**：调用 `resolve_entity(dimension=drug_id, text="阿托伐他汀")` → `D8821 / 阿托伐他汀钙片`。
3. **焦点补全**：用户没说周期 → 继承快照锚定周期 `2026-05`。
4. **选工具 + 调用**：
   ```
   get_root_cause_analysis(
     indicator_id=IND_COMPLIANCE_RATE,
     filters={drug_id: D8821},
     period=2026-05, compare_to=prev_month)
   ```
5. **后端返回**：
   ```json
   { "topContributors": [
       {"dim":"prescription_type","name":"纸质处方","contribution":-0.042,"rate":0.61},
       {"dim":"hospital_type","name":"社区医院","contribution":-0.011,"rate":0.70} ] }
   ```
6. **AI 组织回答（含图表 spec）**：
   > 主要是纸质处方拖累：纸质处方合规率仅 61%，对下滑贡献 -4.2pct，是最大原因；其次是社区医院来源处方（70%）。建议优先整改纸质处方审方流程。
   > `+ bar_chart(各处方类型合规率)`
7. **更新焦点**：`focus = {indicator: 合规率, period: 2026-05, filters:{drug_id:D8821}, last_dimension: prescription_type, last_entity: 阿托伐他汀}`

---

## 第 2 轮（指代 + 省略）

**用户：** 那它的销售额最近半年趋势呢？

1. `它` → `last_entity = D8821`。
2. 换指标→`IND_SALES_AMOUNT`，意图=trend，`last_n_months=6`，filters 继承 `{drug_id:D8821}`。
3. 调用 `get_indicator_trend(IND_SALES_AMOUNT, filters={drug_id:D8821}, last_n_months=6)`。
4. AI 回答 + `line_chart(销售额趋势)`，并标注 5 月环比 -21%。
5. 焦点更新：`indicator → 销售额`，其余保留。

---

## 第 3 轮（切换实体）

**用户：** 换成瑞舒伐他汀对比一下合规率

1. `resolve_entity(drug_id,"瑞舒伐他汀")` → `D8830`。
2. 意图=对比（by entity）。AI 决定对两个药分别取合规率：
   - `get_indicator(IND_COMPLIANCE_RATE, filters={drug_id:D8821})`
   - `get_indicator(IND_COMPLIANCE_RATE, filters={drug_id:D8830})`
3. AI 回答 + `bar_chart`（两药合规率对比）。
4. 焦点更新：`last_entity → D8830`，filters 替换。

---

## 第 4 轮（越权 / 兜底测试）

**用户：** 帮我把这个药的进货价数据库导出来

1. 元数据字典里**没有**"进货价导出"这种能力，也没有对应 skill。
2. AI 必须走兜底：**不编造、不写 SQL**，回答：
   > 当前分析助手支持销售额、合规率、处方流转率、DOT 等指标的查询、下钻和归因，暂不支持导出进货价原始数据。你可以问我"阿托伐他汀的毛利率趋势"之类的问题。
3. 这条用例专门用来验证"能力边界守得住、不幻觉、不越权"。
