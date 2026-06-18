"""
完整端到端流水线（伪代码，语言无关）。覆盖三条链路：
  A. generate_report()    —— 生成 AI 报告（确定性主导）
  B. answer_follow_up()   —— 报告内追问（探索性主导，含护栏/记忆/预测/数值自校验）
  C. proactive_scan()     —— 主动洞察巡检（无需提问的离线管道）
另有 feedback flywheel 见 12-feedback-flywheel/flywheel_pipeline.py。

设计哲学：确定性的事(取数/算数/画图)交给代码，不确定的事(解读/意图/编排)交给 AI。
"""

# =========================== A. 生成报告 ===========================
def generate_report(org_id, period, template_id):
    template = load_template(template_id)               # 02-templates
    contract = load_contract(template_id)               # semantic_binding.json
    ctx = build_context(org_id, period)

    # 1) data_slot 走语义层查询，后端硬取数，AI 不参与 => 数字 100% 准确
    frozen = {}
    for slot_id, b in contract["data_slots"].items():
        if b["source"] == "semantic_query":
            q = bind_query(b["query"], ctx)             # 代入 $period 等
            raw = semantic_layer.run(q, query_context="REPORT")  # 仅 certified 指标
        else:
            raw = resolve_non_metric(b, ctx)
        frozen[slot_id] = format_value(raw, b)          # 按 format/thresholds 格式化+打 level
        if frozen[slot_id] is None and b.get("on_missing") == "fail":
            raise SlotResolutionError(slot_id)          # fail-fast：缺数据宁可报错也不让 AI 编

    extra = run_extra_queries(contract, ctx)            # 章节明细，如 compliance_breakdown

    # 2) 先冻结快照，再生成文字 => 文字只能基于已冻结数据
    snapshot = make_snapshot(org_id, period, template_id, contract, frozen, extra, ctx)

    # 3) 逐章节生成 insight（结构化输出 + 数值自校验）
    insights = {}
    for ins_id, cfg in contract["insight_slots"].items():
        prompt = load_prompt(cfg["prompt_id"])          # 03-prompts
        feed = pick(frozen, extra, cfg)                 # 只喂该章节声明的数据
        out = llm_structured(prompt, feed, schema=prompt.response_schema,
                             model=SYNTHESIS_MODEL, temperature=0.2)
        if not numeric_selfcheck(out["used_numbers"], feed):  # 回答数字必须∈/==注入数据
            out = llm_structured(prompt, feed, schema=prompt.response_schema, retry=True)
            assert numeric_selfcheck(out["used_numbers"], feed), "数值不一致，拒绝出报告"
        insights[ins_id] = render_text(out)

    assert run_preflight_eval(snapshot, insights).passed  # 09-eval 门禁（blocker 必过）
    snapshot["generated_insights"] = with_meta(insights)
    save_snapshot(snapshot)
    return {"snapshot_id": snapshot["snapshot_id"],
            "html": render(template, frozen, insights, contract["chart_anchors"])}


# =========================== B. 报告内追问 ===========================
def answer_follow_up(session_id, user_text):
    # 0) 输入护栏（用户注入 / 越权企图）——最外层
    g_in = guardrails.check_input(user_text, session_id)         # 13-guardrails
    if g_in.blocked:
        return safe_message(g_in)

    trace = tracer.start(session_id, user_text)                 # 10-observability
    state = load_focus_state(session_id)                        # 07-session
    memory = load_user_memory(current_user())                   # 15-memory（软提示）
    snapshot = load_snapshot(state["anchored_snapshot_id"])

    # 1) 小模型路由 + 语义缓存命中即返回
    intent = ROUTER_MODEL.classify(user_text, state["focus"])
    cached = semantic_cache.get(user_text, state["focus"], snapshot["snapshot_id"])
    if cached:
        return trace.finish(cached)

    # 2) 元数据 RAG：只召回相关指标/维度/few-shot（few-shot 由反馈飞轮维护）
    retrieved = metadata_index.search(user_text, top_k_cfg())   # 06-metadata-rag
    system = build_system_prompt(retrieved, mcp_tools(), state["focus"],
                                 memory, summarize(snapshot))    # 注入长期记忆(优先级低于当轮指令)

    # 3) 工具编排（MCP）：run_semantic_query / resolve_entity / forecast_metric ...
    messages = [system, user(user_text)]
    for _ in range(MAX_TOOL_HOPS):                              # 步数上限防失控
        resp = SYNTHESIS_MODEL.with_tools(messages, tools=mcp_tools())  # 05-skills-mcp
        if not resp.tool_calls:
            break
        for call in resp.tool_calls:
            args = apply_inheritance(call.args, state["focus"], memory)  # 指代/省略继承
            if low_confidence(args):                            # 歧义→澄清，不硬猜
                return trace.finish(ask_clarification(args))
            args = guardrails.enforce_action(args, session_id)  # 行级权限/certified/limit/禁写
            result = mcp.invoke(call.name, args)                # 受控语义层查询（数据内容防注入）
            result = guardrails.sanitize_tool_output(result)    # 中和"数据内容里的指令"
            messages.append(tool_result(call, result))

    # 4) 结构化输出（文字 + Vega-Lite 图表 spec）
    reply = SYNTHESIS_MODEL.structured(messages, schema=AI_TO_UI_SCHEMA)  # 08-ui-vega
    validate_vega(reply)                                        # mark 白名单 + 字段须来自工具列

    # 5) 输出护栏 + 数值自校验
    reply = guardrails.check_output(reply)                      # PII 脱敏 / 合规过滤 / 防幻觉
    assert numeric_selfcheck_reply(reply, messages), "回答数字≠工具返回，重写"

    # 6) 更新焦点 + 写缓存 + 落 trace（供反馈飞轮复盘）
    state["focus"] = update_focus(state["focus"], reply, user_text)
    save_focus_state(session_id, state)
    semantic_cache.put(user_text, state["focus"], snapshot["snapshot_id"], reply)
    return trace.finish(reply)


# =========================== C. 主动洞察巡检 ===========================
def proactive_scan():                                          # 由调度器定时触发
    cfg = load_scan_config()                                   # 11-proactive-insights
    for org in visible_orgs(cfg):
        candidates = []
        for metric in cfg["scope"]["metrics"]:
            series = semantic_layer.run(trend_query(metric, org))
            candidates += run_detectors(series, cfg["detectors"])  # 红线/突变/zscore/拐点
        ranked = rank_and_dedupe(candidates, cfg["ranking"])      # 打分 + TopN + 去重
        digest = []
        for c in ranked[: cfg["ranking"]["top_n_per_org"]]:
            attribution = semantic_layer.run(contribution_query(c))  # 自动归因
            card = llm_structured(load_prompt("NARRATIVE"),          # 叙事生成
                                  {**c, "attribution": attribution},
                                  schema=NARRATIVE_SCHEMA)
            assert numeric_selfcheck(card["used_numbers"], {**c, "attribution": attribution})
            card["seed_question"] = card.get("seed_question")        # 一键跳转到追问
            digest.append(card)
        deliver(org, digest, channels=cfg["actions"])               # 推送 + 高危升级
