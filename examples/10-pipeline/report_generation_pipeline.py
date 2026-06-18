"""
报告生成流水线（伪代码，语言无关，照此实现即可）。
核心思想：确定性的事（取数、格式化、快照）交给代码；不确定的事（文字解读）交给 LLM。
"""

def generate_report(org_id: str, period: str, template_id: str) -> dict:
    # 1. 加载模板 + 映射契约 + 上下文
    template = load_template(template_id)                       # examples/01-templates
    contract = load_contract(template_id)                       # examples/02-contracts/semantic_binding.json
    context = build_context(org_id, period)

    # 2. 解析所有 data_slot：后端硬取数（AI 完全不参与，保证数字 100% 准确）
    frozen_values = {}
    for slot_id, binding in contract["data_slots"].items():
        raw = resolve_slot(binding, context)                   # 调指标库 / 上下文 / 系统
        frozen_values[slot_id] = format_value(raw, binding)    # 按 format/unit/thresholds 格式化+打标 level
        if frozen_values[slot_id] is None and binding.get("on_missing") == "fail":
            raise SlotResolutionError(slot_id)                 # fail-fast：缺数据宁可报错也不让 AI 编

    # 3. 取章节所需的明细数据（如 compliance_breakdown）
    extra_data = fetch_extra_data(contract, context)

    # 4. 生成版本快照（先冻结数据，再生成文字 —— 保证文字只能基于这份快照）
    snapshot = make_snapshot(org_id, period, template_id, contract,
                             frozen_values, extra_data, context)  # examples/04-snapshots

    # 5. 逐章节生成 insight：把"对应 slot 值 + 章节 Prompt"喂给 LLM
    insights = {}
    for ins_id, ins_cfg in contract["insight_slots"].items():
        prompt = load_prompt(ins_cfg["prompt_id"])             # examples/03-prompts
        feed = pick_values(frozen_values, extra_data, ins_cfg) # 只喂该章节声明的数据
        text = llm_complete(
            system=prompt.system,
            rules=prompt.rules,
            output_contract=prompt.output_contract,
            feed_data_json=feed,
            max_words=ins_cfg["max_words"],
            temperature=0.2,
        )
        validate_no_hallucination(text, feed)                  # 校验：文中出现的数字必须都在 feed 里
        insights[ins_id] = text

    # 6. 渲染：占位符回填 + 图表锚点 + 落库
    snapshot["generated_insights"] = insights
    rendered = render_template(template, frozen_values, insights, contract["chart_anchors"])
    save_snapshot(snapshot)                                    # 落库，供前端展示 & 追问引用
    return {"snapshot_id": snapshot["snapshot_id"], "html": rendered}


# ----------------------------------------------------------------------------

def answer_follow_up(session_id: str, user_text: str) -> dict:
    """报告内追问主循环（无尽探索）。"""
    state = load_focus_state(session_id)                       # examples/07-session
    snapshot = load_snapshot(state["anchored_snapshot_id"])

    # 1. 把"元数据字典 + 技能清单 + 当前焦点 + 快照关键值"组成 system 上下文
    system = build_system_prompt(
        metadata_dict=load_metadata_dictionary(),             # examples/06-metadata
        skills=load_skills_manifest(),                        # examples/05-skills
        focus=state["focus"],
        snapshot_summary=summarize(snapshot),
    )

    # 2. 让 LLM 做 function calling（可能多步：先 resolve_entity 再取数）
    messages = [system, {"role": "user", "content": user_text}]
    for _ in range(MAX_TOOL_HOPS):                             # 限制最大工具调用步数，防失控
        resp = llm_with_tools(messages, tools=load_skills_manifest())
        if resp.tool_calls:
            for call in resp.tool_calls:
                # 关键：参数缺省用 focus 补全；org 由后端权限注入，不信任 AI
                args = apply_inheritance(call.args, state["focus"])
                args = enforce_permissions(args, session_id)
                result = invoke_skill(call.name, args)        # 调 Java Skills（受控API）
                messages.append(tool_result(call, result))
        else:
            break

    # 3. LLM 产出"文字 + 图表 spec"（AI-to-UI 协议）
    reply = parse_ai_to_ui(resp.content)                      # examples/08-ui/chart_spec.json
    validate_chart_spec(reply)                                # 校验 chart_type 在白名单内

    # 4. 更新焦点状态，供下一轮指代/省略消解
    state["focus"] = update_focus(state["focus"], reply, user_text)
    save_focus_state(session_id, state)
    return reply
