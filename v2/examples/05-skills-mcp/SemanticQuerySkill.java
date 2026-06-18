package com.example.report.v2.skills;

import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import java.util.*;

/**
 * 2.0 主力技能：受约束的语义层查询执行器（被 MCP server 的 run_semantic_query 调用）。
 *
 * 设计要点：
 *  - AI 产出"语义查询(SemanticQuery)"而非 SQL；本类负责【校验 → 行级权限注入 → 交语义层编译执行 → 结构化返回】。
 *  - 既能覆盖固定问法，又能兜住长尾组合，且全程不暴露裸 SQL。
 */
@RestController
@RequestMapping("/api/v2")
public class SemanticQuerySkill {

    private final SemanticLayer semanticLayer;     // dbt/Cube/Malloy 适配器
    private final MetricRegistry registry;         // 加载 metrics.yaml
    private final SecurityContextProvider sec;
    private final AuditLogger audit;

    public SemanticQuerySkill(SemanticLayer sl, MetricRegistry reg,
                              SecurityContextProvider sec, AuditLogger audit) {
        this.semanticLayer = sl; this.registry = reg; this.sec = sec; this.audit = audit;
    }

    @PostMapping("/run_semantic_query")
    public QueryResult run(@Valid @RequestBody SemanticQuery q) {
        // 1) 合法性：指标、维度、scope 必须在语义层注册，且该指标支持
        MetricDef m = registry.requireMetric(q.metric);          // 不存在 → 400
        if (q.groupBy != null) q.groupBy.forEach(d -> registry.requireDimSupported(m, d));
        if (q.scope != null) registry.requireScope(m, q.scope);

        // 2) 报告链路只允许 certified 指标；追问链路放宽但仍需注册
        if (q.context == QueryContext.REPORT && !m.certified)
            throw new PolicyException("report 仅允许 certified 指标: " + q.metric);

        // 3) 行级权限：org 由后端注入，忽略 AI 传入的 org 过滤
        q.filters = stripOrgFilters(q.filters);
        q.injectedOrgScope = sec.currentVisibleOrgIds();

        // 4) 自动 limit、范围保护
        if (q.limit == null || q.limit <= 0) q.limit = 200;
        if (q.limit > 200) throw new PolicyException("limit 超上限");
        guardTimeRange(q.time);                                   // >36月 或越权 → 拒绝

        // 5) 交语义层编译并执行（语义层负责生成参数化 SQL）
        CompiledQuery compiled = semanticLayer.compile(q);
        QueryResult result = semanticLayer.execute(compiled);

        // 6) 审计（记录编译 SQL 指纹，可追溯）
        audit.log("run_semantic_query", q, compiled.sqlFingerprint(),
                  result.rowCount(), result.execMs(), sec.currentUser());

        // 7) 结构化返回 + 给前端的图表建议(Vega-Lite 类型)
        result.setChartHint(ChartHint.suggest(q));               // line/bar/table...
        return result;
    }
}
