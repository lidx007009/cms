"""
2.0 端到端流水线（伪代码）。相对 1.0 的增量已用 [2.0] 标注。
依赖：语义层引擎、向量库(元数据RAG)、MCP 工具、结构化输出、评测器、Trace。
"""

# ============================ 场景一：生成报告 ============================
def generate_report(org_id, period, template_id):
    template = load_template(template_id)
    contract = load_contract(template_id)               # 绑定到 semantic_query
    ctx = build_context(org_id, period)

    # [2.0] data_slot 走"语义层查询"，不再内嵌 SQL
    frozen = {}
    for slot_id, b in contract["data_slots"].items():
        if b["source"] == "semantic_query":
            q = bind_query(b["query"], ctx)             # 把 $period 等占位代入
            raw = semantic_layer.run(q, query_context="REPORT")  # 仅 certified 指标
        else:
            raw = resolve_non_metric(b, ctx)
        frozen[slot_id] = format_value(raw, b)
        if frozen[slot_id] is None and b.get("on_missing") == "fail":
            raise SlotResolutionError(slot_id)          # fail-fast

    extra = run_extra_queries(contract, ctx)
    snapshot = make_snapshot_v2(org_id, period, template_id, contract, frozen, extra, ctx)
    # [2.0] 快照记录每个 slot 的编译 SQL 指纹（compiled_queries），行级可审计

    insights = {}
    for ins_id, cfg in contract["insight_slots"].items():
        prompt = load_prompt(cfg["prompt_id"])
        feed = pick(frozen, extra, cfg)
        # [2.0] 结构化输出：返回 JSON(conclusion/attribution/.../used_numbers)
        out = llm_structured(prompt, feed, schema=prompt.response_schema,
                             model=SYNTHESIS_MODEL, temperature=0.2)
        # [2.0] 数值自校验：used_numbers 必须与 feed 完全一致
        if not numeric_selfcheck(out["used_numbers"], feed):
            out = llm_structured(prompt, feed, schema=prompt.response_schema, retry=True)
            assert numeric_selfcheck(out["used_numbers"], feed), "数值不一致，拒绝出报告"
        insights[ins_id] = render_text(out)

    # [2.0] 上线前自检：跑该报告相关的 golden checks
    assert run_preflight_eval(snapshot, insights).passed

    snapshot["generated_insights"] = with_meta(insights)
    save_snapshot(snapshot)
    return {"snapshot_id": snapshot["snapshot_id"],
            "html": render(template, frozen, insights, contract["chart_anchors"])}


# ============================ 场景二：追问 ============================
def answer_follow_up(session_id, user_text):
    trace = tracer.start(session_id, user_text)         # [2.0] 全链路 trace
    state = load_focus_state(session_id)
    snapshot = load_snapshot(state["anchored_snapshot_id"])

    # [2.0] 大小模型分工：先用小模型分类意图 + 判定缓存
    intent = ROUTER_MODEL.classify(user_text, state["focus"])
    cached = semantic_cache.get(user_text, state["focus"], snapshot["snapshot_id"])
    if cached: return trace.finish(cached)

    # [2.0] 元数据 RAG：只召回相关指标/维度/few-shot，而非全量字典
    retrieved = metadata_index.search(user_text, top_k_cfg())
    system = build_system_prompt(retrieved, mcp_tools(), state["focus"], summarize(snapshot))

    messages = [system, user(user_text)]
    for _ in range(MAX_TOOL_HOPS):                       # 步数上限
        resp = SYNTHESIS_MODEL.with_tools(messages, tools=mcp_tools())  # MCP 暴露
        if not resp.tool_calls: break
        for call in resp.tool_calls:
            args = apply_inheritance(call.args, state["focus"])    # 指代/省略继承
            if needs_clarification(args):                          # [2.0] 置信度低→反问
                return trace.finish(ask_clarification(args))
            args = enforce_permissions(args, session_id)           # org 后端注入
            result = mcp.invoke(call.name, args)                   # 受控语义层查询
            messages.append(tool_result(call, result))

    # [2.0] 结构化输出 + Vega-Lite 图表 spec
    reply = SYNTHESIS_MODEL.structured(messages, schema=AI_TO_UI_SCHEMA)
    validate_vega(reply)                                  # mark 白名单 + 字段须来自工具列
    assert numeric_selfcheck_reply(reply, messages)      # [2.0] 回答数字==工具返回

    state["focus"] = update_focus(state["focus"], reply, user_text)
    save_focus_state(session_id, state)
    semantic_cache.put(user_text, state["focus"], snapshot["snapshot_id"], reply)
    return trace.finish(reply)
