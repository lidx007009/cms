# 底表与字段数据字典（Source Tables & Field Dictionary）

> 由"数据/后端团队"维护，是 `metrics.yaml` 里所有 `table` 与 `{source}.field` 引用的**字段级说明书**。
> 作用：① 让指标口径可追溯到具体表/字段；② 行级权限、PII 脱敏、血缘审计的依据；③ 新增指标时照此选字段。
> 约定：所有事实表都带 `org_id`（行级权限键）和 `drug_id`（实体键），`stat_date/stat_month`（时间维）。

---

## 1. `dw.dws_pharmacy_sales_d` —— 药店销售日汇总事实表
粒度（grain）：门店 × 药品 × 支付方式 × 客流来源 × 日

| 字段 | 类型 | 含义 | 示例 | PII | 用途 |
|---|---|---|---|---|---|
| `stat_date` | DATE | 统计日期 | 2026-05-18 | 否 | 时间维 |
| `org_id` | STRING | 门店ID | ORG1024 | 否 | 行级权限键 / 实体 org |
| `drug_id` | STRING | 药品ID | D8821 | 否 | 实体 drug，关联 `dim_drug` |
| `drug_category` | STRING | 药品品类 | 心血管 | 否 | 维度 drug_category |
| `payment_method` | STRING | 支付方式 | 医保/自费/商保 | 否 | 维度 payment_method |
| `source_type` | STRING | 客流来源 | 处方导流 | 否 | 维度 source_type |
| `amount` | DECIMAL(18,2) | 含税销售额(已扣退货前) | 1280.50 | 否 | 度量 sales_amount |
| `cost` | DECIMAL(18,2) | 销售成本 | 970.00 | 否 | 度量 gross_profit |
| `qty` | INT | 销售数量 | 3 | 否 | 备用度量 |
| `is_return` | TINYINT | 是否退货(1=退货) | 0 | 否 | 默认过滤 `is_return=0` |

口径映射：
- `sales_amount = SUM(amount)`（默认 `WHERE is_return=0`）
- `gross_profit = SUM(amount - cost)`；`毛利率 = gross_profit / sales_amount`

---

## 2. `dw.dws_compliance_txn_d` —— 合规交易明细事实表
粒度：单笔交易（一行一笔 `txn_id`）

| 字段 | 类型 | 含义 | 示例 | PII | 用途 |
|---|---|---|---|---|---|
| `stat_date` | DATE | 交易日期 | 2026-05-18 | 否 | 时间维 |
| `org_id` | STRING | 门店ID | ORG1024 | 否 | 行级权限键 |
| `txn_id` | STRING | 交易ID（主键） | T20260518000931 | 否 | 度量 total_txn 计数 |
| `drug_id` | STRING | 药品ID | D8821 | 否 | 实体 drug |
| `drug_category` | STRING | 药品品类 | 心血管 | 否 | 维度 |
| `prescription_type` | STRING | 处方类型 | 纸质处方/电子处方/无处方 | 否 | 维度 prescription_type |
| `hospital_type` | STRING | 来源医院类型 | 三甲/二级/社区/互联网医院 | 否 | 维度 hospital_type |
| `is_rx` | TINYINT | 是否处方药(1=是) | 1 | 否 | scope=rx/otc 过滤 |
| `is_compliant` | TINYINT | 是否合规(1=合规) | 1 | 否 | 度量 compliant_txn |
| `patient_name` | STRING | 患者姓名 | 张三 | **高** | 仅明细查询，需脱敏 |
| `phone` | STRING | 患者手机号 | 138****1234 | **高** | 脱敏 |
| `id_card` | STRING | 身份证号 | hash/屏蔽 | **高** | hash 或拒绝 |
| `doctor_name` | STRING | 开方医生 | 李医生 | 中 | 角色可见 |

口径映射：
- `compliant_txn = SUM(CASE WHEN is_compliant=1 THEN 1 ELSE 0 END)`
- `total_txn = COUNT(txn_id)`
- `合规率 = compliant_txn / total_txn`；`scope=rx` 时追加 `WHERE is_rx=1`

> 注意：`patient_name/phone/id_card` 等是 PII，聚合指标（合规率）不暴露个体；只有"明细查询"才会触及，必须走 `pii_policy.yaml` 脱敏 + 审计。

---

## 3. `dw.dws_dtp_dot_m` —— DTP 用药依从月表
粒度：门店 × 药品 × 月

| 字段 | 类型 | 含义 | 示例 | PII | 用途 |
|---|---|---|---|---|---|
| `stat_month` | STRING | 统计月(YYYY-MM) | 2026-05 | 否 | 时间维 |
| `org_id` | STRING | 门店ID | ORG1024 | 否 | 行级权限键 |
| `drug_id` | STRING | 药品ID | D8821 | 否 | 实体 drug |
| `disease_area` | STRING | 疾病领域 | 心血管 | 否 | 维度 disease_area |
| `dot_avg` | DECIMAL(6,2) | 平均用药持续天数(DOT) | 0.71 | 否 | 度量 dot_avg |

口径映射：`IND_DTP_DOT = AVG(dot_avg)`

---

## 4. 维表（Dimension Tables）

### `dim_drug` —— 药品维表
| 字段 | 类型 | 含义 | 示例 |
|---|---|---|---|
| `drug_id` | STRING | 药品ID(主键) | D8821 |
| `drug_name` | STRING | 药品名 | 阿托伐他汀钙片 |
| `drug_category` | STRING | 品类 | 心血管 |
| `disease_area` | STRING | 疾病领域 | 心血管 |
| `aliases` | ARRAY | 别名/口语名(供 resolve_entity) | [阿托伐他汀, 立普妥] |

### `dim_org` —— 门店维表
| 字段 | 类型 | 含义 | 示例 |
|---|---|---|---|
| `org_id` | STRING | 门店ID(主键) | ORG1024 |
| `org_name` | STRING | 门店名 | 康民大药房(中山北路店) |
| `region` | STRING | 所属区域 | 华东-上海 |

---

## 5. 字段血缘总表（Field → 度量/维度 → 指标）
> 一眼看清"每个业务指标最终落到哪张表、哪个字段"。

| 业务指标 (metric) | 度量/维度 | 底表 | 字段 | 计算 |
|---|---|---|---|---|
| IND_SALES_AMOUNT | sales_amount | dws_pharmacy_sales_d | `amount` (filter `is_return=0`) | SUM |
| IND_GROSS_MARGIN_RATE | gross_profit / sales_amount | dws_pharmacy_sales_d | `amount`,`cost` | SUM(amount-cost)/SUM(amount) |
| IND_COMPLIANCE_RATE | compliant_txn / total_txn | dws_compliance_txn_d | `is_compliant`,`txn_id` (scope→`is_rx`) | SUM(...)/COUNT(...) |
| IND_DTP_DOT | dot_avg | dws_dtp_dot_m | `dot_avg` | AVG |
| 维度 drug_category | — | sales/compliance_fct | `drug_category` | group by |
| 维度 payment_method | — | dws_pharmacy_sales_d | `payment_method` | group by |
| 维度 prescription_type | — | dws_compliance_txn_d | `prescription_type` | group by |
| 维度 hospital_type | — | dws_compliance_txn_d | `hospital_type` | group by |
| 维度 disease_area | — | dws_dtp_dot_m | `disease_area` | group by |
| 实体 drug 过滤 | — | 各事实表 | `drug_id` | where drug_id=? |
| 行级权限 | — | 各事实表 | `org_id` | where org_id in (会话授权范围) |
