# 报告模板示例：药店月度经营分析报告

> 这是"产品/业务团队"维护的纯结构文件。
> 模板里只放**结构 + 占位符 + 章节意图**，绝不放"AI 自由发挥"的内容。
> 占位符语法统一为 `{{slot:槽位ID}}`（数据槽）和 `{{insight:章节ID}}`（推理槽）。
> 每个占位符都必须能在 `semantic_binding.json`（映射契约）里找到对应定义，否则渲染时直接报错（fail-fast）。

---

# {{slot:org.name}} · {{slot:period.label}} 经营分析报告

报告生成时间：{{slot:meta.generated_at}}
数据截止时间：{{slot:meta.data_cutoff}}
报告版本号：{{slot:meta.snapshot_id}}

---

## 一、整体经营概览

本月销售额 **{{slot:sales.amount}}**，环比 {{slot:sales.mom}}，同比 {{slot:sales.yoy}}；
毛利率 **{{slot:gross_margin.rate}}**，处方流转率 **{{slot:rx.transfer_rate}}**。

{{insight:overview}}

<!-- chart-anchor: overview_trend -->

## 二、合规经营分析

本月整体合规率 **{{slot:compliance.rate}}**（环比 {{slot:compliance.mom}}）。
其中处方药合规率 {{slot:compliance.rx_rate}}，DTP 业务 DOT 指标为 {{slot:dtp.dot}}。

{{insight:compliance}}

<!-- chart-anchor: compliance_by_category -->

## 三、品类与药品表现

TOP3 增长品类：{{slot:category.top3_growth}}
TOP3 下滑品类：{{slot:category.top3_decline}}

{{insight:category}}

## 四、风险提示与下月建议

{{insight:risk_and_action}}

---

> 说明：
> - `{{slot:*}}`：由后端按"映射契约"硬取数填入，**AI 不参与取数**，保证数字 100% 准确。
> - `{{insight:*}}`：由 AI 基于"已注入的结构化数据 + 章节推理 Prompt"生成文字解读，**只允许引用已注入的数字**。
> - `<!-- chart-anchor: X -->`：图表锚点，渲染时替换为对应图表组件。
