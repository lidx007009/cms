# LLM-as-Judge 评分 Prompt（评"解读质量"这类没有唯一标准答案的输出）

## System
```
你是严格的数据分析质量评审。对"AI 生成的章节解读"打分。只依据【输入数据】判断，不要自带外部知识。
```

## 评分维度（各 1-5 分）
1. 忠实性 faithfulness：结论是否都能由输入数据支撑，有无臆断。
2. 归因正确性 attribution：是否抓住贡献最大的维度（对照 breakdown）。
3. 阈值合规 rule_compliance：是否按业务阈值判档（合规率<85%=高风险，DOT<0.8 点名）。
4. 可执行性 actionability：建议是否具体可落地。
5. 简洁度 conciseness：是否在字数内、无废话。

## 输入
```json
{ "feed_data": {{feed_data_json}}, "answer": {{answer_json}} }
```

## 输出（结构化）
```json
{ "faithfulness":5, "attribution":4, "rule_compliance":5, "actionability":4, "conciseness":5,
  "overall": 4.6, "issues": ["..."], "verdict": "pass|revise" }
```
> overall < 4.0 记为 minor 失败，进迭代清单；faithfulness < 5 直接标记重写。
