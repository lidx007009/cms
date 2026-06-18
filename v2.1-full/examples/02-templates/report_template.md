# 报告模板：药店月度经营分析报告

> 占位符语法：`{{slot:数据槽}}`（后端硬取数填，AI 不碰数字）/ `{{insight:推理槽}}`（AI 基于已注入数据写解读）/ `<!-- chart-anchor: X -->`（图表锚点）。
> 数据槽绑定到【语义层查询】，绑定关系见 `semantic_binding.json`。

# {{slot:org.name}} · {{slot:period.label}} 经营分析报告

报告生成时间：{{slot:meta.generated_at}}　数据截止：{{slot:meta.data_cutoff}}　快照号：{{slot:meta.snapshot_id}}

## 一、整体经营概览
本月销售额 **{{slot:sales.amount}}**，环比 {{slot:sales.mom}}，同比 {{slot:sales.yoy}}；毛利率 **{{slot:gross_margin.rate}}**。
{{insight:overview}}
<!-- chart-anchor: overview_trend -->

## 二、合规经营分析
整体合规率 **{{slot:compliance.rate}}**（环比 {{slot:compliance.mom}}），处方药合规率 {{slot:compliance.rx_rate}}，DTP 的 DOT 为 {{slot:dtp.dot}}。
{{insight:compliance}}
<!-- chart-anchor: compliance_by_category -->

## 三、风险提示与下月建议
{{insight:risk_and_action}}
