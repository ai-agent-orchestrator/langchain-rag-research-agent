"""Request-local Equalizer stages shared by Python and graph adapters."""
from __future__ import annotations

MATURITY = "incubating"

from copy import copy
from rag_research_agent.core.types import Brief, Status
from rag_research_agent.edge.scorer import RuleProtectedPicker
from rag_research_agent.knobs.mapper import blend


def prepare(parts, raw_draft, task=None, knobs=None, preset=None, budget=600, focus=None, packs=None):
    p = copy(parts).ready()
    cfg = p.config
    pre = cfg.presets.get(preset) if preset else None
    if preset and pre is None:
        raise ValueError(f"unknown preset {preset}; available: {sorted(cfg.presets)}")
    from rag_research_agent.core.types import Knobs
    knobs = knobs or (pre.knobs if pre else Knobs())
    packs = tuple(packs if packs is not None else (pre.packs if pre else ()))
    if focus is None and pre and pre.focus:
        focus = dict(pre.focus)
    st = cfg.mapper.map(knobs)
    return {"raw_draft": raw_draft, "task": task, "parts": p, "selection": st, "focus": focus,
            "packs": packs, "budget": budget, "status": Status.OK, "rows": [], "diet_log": [],
            "generation_calls": 0, "node_calls": [], "excluded_segments": [], "diet_rounds": 0,
            "settings": {"preset": preset, "similarity": knobs.similarity, "edge_weight": knobs.edge_weight,
                         "threshold": st.threshold, "top_k": st.top_k, "extract_only": st.extract_only,
                         "protected_path": st.protected_path, "budget": budget, "packs": list(packs), "focus": focus or {}},
            "versions": {"rule_version": p.rules.rule_version, "equalizer": "v0", "mapper": repr(cfg.mapper)}}


def _visit(state, name):
    return {**state, "node_calls": [*state["node_calls"], name]}


def _finish(state, brief):
    return {**state, "brief": brief, "status": brief.status, "_finished": True,
            "final_prompt_input": brief.final_prompt_input, "included_ids": brief.included_ids,
            "filtered_context": "\n".join(row["text"] for row in state["rows"] if row["id"] in brief.included_ids),
            "token_count": len(brief.final_prompt_input)}


def guard_input(state, parts):
    s = _visit(state, "guard_input")
    decision = parts.input_policy.check(s["raw_draft"] + "\n" + (s["task"] or ""))
    if not decision.allowed:
        s["diet_log"] = [f"blocked: {decision.reason}"]
        return _finish(s, Brief("", Status.BLOCKED, versions=s["versions"]))
    return s


def chunk_and_label(state, parts):
    s = _visit(state, "chunk_and_label")
    text = s["raw_draft"]
    labeler = parts.labeler.with_text(text) if hasattr(parts.labeler, "with_text") else parts.labeler
    segments = labeler.label(parts.chunker.split(text, "draft"))
    builder = parts.link_builder.with_text(text) if hasattr(parts.link_builder, "with_text") else parts.link_builder
    return {**s, "segments": segments, "links": builder.build(segments)}


def score(state, parts):
    s = _visit(state, "score")
    text, segs, st = s["raw_draft"], s["segments"], s["selection"]
    scorer = parts.scorer_factory(parts.rules, text, s["packs"], focus=s["focus"])
    edge = {e.segment_id: e for e in scorer.score(segs)}
    rel_of = parts.relevance(s["task"])
    rel = {seg.segment_id: rel_of(text[seg.start:seg.end]) for seg in segs}
    final = {seg.segment_id: blend(rel[seg.segment_id], edge[seg.segment_id].total, st.edge_weight) for seg in segs}
    return {**s, "scorer": scorer, "edge_scores": edge, "relevance_scores": rel, "final_scores": final}


def select(state, parts):
    s = _visit(state, "select")
    segs, st, cfg = s["segments"], s["selection"], parts.config
    edge, rel, final = s["edge_scores"], s["relevance_scores"], s["final_scores"]
    ordinary = [seg for seg in segs if rel[seg.segment_id] >= st.threshold]
    ordinary = sorted(ordinary, key=lambda seg: (-final[seg.segment_id], seg.start))[:st.top_k]
    protected = set()
    if st.protected_path:
        protected = {c.segment_id for c in RuleProtectedPicker(s["scorer"]).pick(segs, list(edge.values()))}
        protected |= {seg.segment_id for seg in segs if getattr(seg.ontology_label, "value", seg.ontology_label) in cfg.never_remove}
    chosen_ids = {seg.segment_id for seg in ordinary} | protected
    chosen = [seg for seg in segs if seg.segment_id in chosen_ids]
    excluded = [(seg.segment_id, "below_threshold" if rel[seg.segment_id] < st.threshold else "outside_top_k")
                for seg in segs if seg.segment_id not in chosen_ids]
    rows = [{"id": seg.segment_id, "label": getattr(seg.ontology_label, "value", seg.ontology_label),
             "relevance": rel[seg.segment_id], "edge": edge[seg.segment_id].total,
             "final": final[seg.segment_id], "protected": seg.segment_id in protected,
             "chosen": seg.segment_id in chosen_ids, "text": s["raw_draft"][seg.start:seg.end]} for seg in segs]
    s.update(protected_ids=protected, chosen_segments=chosen, excluded_segments=excluded, rows=rows)
    if not chosen:
        s["diet_log"] = ["no candidates"]
        return _finish(s, Brief("", Status.REQUEST_MORE, excluded=tuple(excluded), versions=s["versions"]))
    return s


def diet(state, parts):
    s = _visit(state, "diet")
    cfg = parts.config
    dieter = parts.dieter_factory(s["budget"], cfg.class_order, cfg.never_remove)
    result = dieter.run(s["chosen_segments"], s["raw_draft"], s["final_scores"], s["protected_ids"], s["links"])
    kept_ids = {seg.segment_id for seg in result.kept}
    s.update(kept_segments=result.kept, excluded_segments=[*s["excluded_segments"], *result.removed],
             rows=[{**row, "kept": row["id"] in kept_ids} for row in s["rows"]],
             diet_log=list(result.log), diet_rounds=result.rounds, status=result.status)
    # Legacy build_brief returns protected extractive content on overflow. Finalize here,
    # using the same function, so a graph may end at diet without changing that contract.
    return compose_and_check(s, parts) if result.status == Status.BUDGET_PROTECTED_OVERFLOW else s


def compose_and_check(state, parts):
    s = _visit(state, "compose_and_check")
    brief = parts.composer.compose(s["kept_segments"], s["raw_draft"], s["versions"], s["excluded_segments"], s["diet_log"], s["status"])
    status = parts.checker.check(brief, s["raw_draft"])
    if status is not brief.status:
        brief = Brief("", status, brief.included_ids, brief.excluded, brief.diet_log, brief.versions)
    return _finish(s, brief)


STAGES = (guard_input, chunk_and_label, score, select, diet, compose_and_check)
