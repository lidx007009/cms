package com.example.report.skills;

import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import java.util.*;

/**
 * Java 版"探索性技能库"的一个 Skill 实现示例。
 *
 * 关键点（落地时务必照做）：
 *  1) AI 只能调用这些受控接口，永远拿不到原始 SQL 执行权 —— 杜绝注入/越权/跑垮库。
 *  2) 入参里的 indicator_id / dimension 必须先在【指标库目录】里校验合法，非法直接拒绝。
 *  3) 行级权限：org 范围由后端从登录态/会话注入，绝不信任 AI 传来的 org_id。
 *  4) 出参结构稳定，既能回填给 AI 推理，又能直接驱动前端图表协议。
 */
@RestController
@RequestMapping("/api/skills")
public class IndicatorSkillController {

    private final IndicatorCatalog catalog;     // 加载 indicator_catalog.yaml
    private final OlapQueryService olap;        // 真正去 OLAP/宽表取数
    private final SecurityContextProvider sec;  // 提供当前用户可见的 org 范围

    public IndicatorSkillController(IndicatorCatalog catalog, OlapQueryService olap, SecurityContextProvider sec) {
        this.catalog = catalog;
        this.olap = olap;
        this.sec = sec;
    }

    /** 对应 skills_manifest.json 里的 get_indicator_by_dimension */
    @PostMapping("/get_indicator_by_dimension")
    public SkillResult getByDimension(@Valid @RequestBody ByDimRequest req) {
        // 1. 合法性校验：指标、维度都必须在目录里，且该指标支持该维度
        IndicatorDef ind = catalog.requireIndicator(req.indicatorId);
        catalog.requireDimensionSupported(ind, req.dimension);

        // 2. 权限：org 只能是当前用户可见范围，AI 无权指定
        List<String> allowedOrgs = sec.currentVisibleOrgIds();

        // 3. 安全取数（参数化，绝不拼接字符串）
        List<DimRow> rows = olap.queryByDimension(
                ind, req.dimension, req.resolvePeriod(), req.filters,
                allowedOrgs, req.order, Math.min(req.limit, 50));

        // 4. 标准化返回（含给前端画图的 chart_hint）
        return SkillResult.builder()
                .skill("get_indicator_by_dimension")
                .indicator(ind.id)
                .dimension(req.dimension)
                .period(req.resolvePeriod())
                .rows(rows)
                .chartHint(new ChartHint("bar_chart", req.dimension, ind.valueType))
                .build();
    }

    /** 对应 get_root_cause_analysis：返回各子维度对"变化量"的贡献度 */
    @PostMapping("/get_root_cause_analysis")
    public RootCauseResult rootCause(@Valid @RequestBody RootCauseRequest req) {
        IndicatorDef ind = catalog.requireIndicator(req.indicatorId);
        List<String> dims = (req.candidateDims == null || req.candidateDims.isEmpty())
                ? ind.supportedDims : req.candidateDims;

        // 对每个候选维度做贡献度分解，挑出贡献最大的维度
        List<Contribution> contributions = new ArrayList<>();
        for (String dim : dims) {
            contributions.addAll(
                olap.contributionDecomposition(ind, dim, req.period, req.compareTo,
                        req.filters, sec.currentVisibleOrgIds()));
        }
        contributions.sort(Comparator.comparingDouble(c -> c.contribution)); // 升序：最负的在前

        return RootCauseResult.builder()
                .indicator(ind.id)
                .period(req.period)
                .compareTo(req.compareTo)
                .topContributors(contributions.subList(0, Math.min(5, contributions.size())))
                .build();
    }
}
