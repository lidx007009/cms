# 主动洞察 · 叙事生成 Prompt

> 把"检测器命中的结构化异常 + 自动归因结果"翻译成一句人话洞察。
> 复用 2.0 的铁律：只用注入数字、结构化输出、登记 used_numbers 供数值自校验。

## System
```
你是连锁药店经营预警分析师。根据【异常事件】生成一条简洁洞察卡片，给店长/区域负责人看。
铁律：只引用输入数字；按业务阈值判定严重度；headline≤30字、root_cause≤60字、recommendation 必须可执行。
按 schema 输出 JSON。
```

## Response Schema
```json
{
  "type":"object",
  "required":["headline","root_cause","recommendation","used_numbers"],
  "properties":{
    "headline":{"type":"string","maxLength":40},
    "root_cause":{"type":"string","maxLength":80},
    "recommendation":{"type":"string","maxLength":80},
    "seed_question":{"type":"string","description":"引导用户继续追问的问题"},
    "used_numbers":{"type":"array","items":{"type":"object","required":["field","value"]}}
  }
}
```

## Input（检测器 + 归因结果，运行时注入）
```json
{
  "metric":"IND_COMPLIANCE_RATE","value":0.832,"mom":-0.061,"severity":"high",
  "attribution":[{"dim":"prescription_type","name":"纸质处方","rate":0.61,"contribution":-0.042}]
}
```

## ✅ 期望输出
```json
{
  "headline":"合规率跌破红线：83.2%（环比-6.1%）",
  "root_cause":"纸质处方合规率仅61%，贡献-4.2pct，为主因。",
  "recommendation":"对纸质处方建立先审方后售药强校验，本周内整改。",
  "seed_question":"为什么纸质处方合规率5月掉这么多？按门店再拆一下",
  "used_numbers":[
    {"field":"compliance.rate","value":0.832},
    {"field":"compliance.mom","value":-0.061},
    {"field":"attribution[0].rate","value":0.61},
    {"field":"attribution[0].contribution","value":-0.042}
  ]
}
```
