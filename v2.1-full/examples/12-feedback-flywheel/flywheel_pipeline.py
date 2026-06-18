"""
反馈飞轮回灌管道（伪代码）。
关键理念：不微调、不训练，靠"动态 few-shot 库 + 检索重排 + 评测集扩充"形成飞轮——
比 RLHF/微调更稳、更快、可解释、可回滚。
"""

def run_flywheel(period="weekly"):
    events = load_feedback_events(period)          # 见 feedback_event.schema.json

    # ---------- 1. 正样本入库：好评/被采纳/用户修正 → few-shot 候选 ----------
    for e in events:
        sig = e["signal"]["type"]
        if sig in ("thumbs_up", "adopted"):
            promote_candidate(make_fewshot(e["context"]["user_query"],
                                           e["context"]["tool_calls"]), weight=+1)
        if sig == "edited":
            # 用户把 AI 的查询改对了 = 最高价值正样本（含"错→对"信号）
            promote_candidate(make_fewshot(e["context"]["user_query"],
                                           e["context"]["corrected_query"]), weight=+3)

    # ---------- 2. 负样本 → 评测集 + 修复清单 ----------
    for e in events:
        if e["signal"]["type"] in ("thumbs_down", "report_error"):
            add_to_golden_set(e)                   # 自动扩充 eval_golden_set，防回归
            if "数字错" in e["signal"].get("reason_tags", []):
                page_oncall(e)                     # 数字错=blocker，立即告警排查

    # ---------- 3. few-shot 晋升/淘汰（见 fewshot_promotion_rules.yaml） ----------
    for cand in pending_fewshots():
        if cand.net_weight >= PROMOTE_THRESHOLD and offline_eval_pass(cand):
            activate_fewshot(cand)                 # 进入线上 few-shot 库(被 RAG 召回)
        if cand.recent_negative_rate > DEMOTE_THRESHOLD:
            retire_fewshot(cand)                   # 表现变差则下线，可回滚

    # ---------- 4. 检索重排校准：用反馈当作相关性标签 ----------
    rel_labels = build_relevance_labels(events)    # 召回命中却差评 = 召回质量问题
    if enough(rel_labels):
        retrain_reranker(rel_labels)               # 仅训练轻量 reranker，不动主模型

    # ---------- 5. 上线前必须过评测门禁（见 09-eval 的 eval gates） ----------
    report = run_eval_suite()
    assert report.blocker_pass_rate == 1.0, "回灌后 blocker 未全过，禁止发布"
    publish(report)                                # 飞轮跑分进可观测看板，可见周环比提升


# few-shot 是"活的"：被召回 → 影响 AI 决策 → 用户反馈 → 再调整库，形成闭环。
# 全程无模型训练，改坏了一键回滚到上一版 few-shot 快照。
