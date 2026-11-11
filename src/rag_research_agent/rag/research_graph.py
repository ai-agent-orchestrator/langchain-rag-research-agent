"""Division-of-labour research graph (docs/RESEARCH_GRAPH_DESIGN.ko.md), rule-based first.

    plan -> retrieve(base | pro | con) -> refine -> extract -> compare -> coverage --gap--> retrieve_gap
         -> write -> verify --GAP--> retrieve_gap | --style issue--> write | --pass/limit--> finish

- Rule nodes remain the default; five node functions and optional planning/extraction models are injectable.
- State accumulates sources, claims, metrics and relations through reducers; nothing is overwritten.
- Cost: every node records the tokens a model call *would* have used (shadow cost, ~chars/2), so the
  loop cost can be weighed against the prompt saved by retrieval (docs/RESEARCH_GRAPH_DESIGN.ko.md 10).
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import asdict, dataclass, replace
import operator
import re
from typing import Annotated, Callable, Literal, Optional, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command, interrupt

from rag_research_agent.core.research import (
    NO_COUNTER_EVIDENCE, Claim, Draft, Metric, Relation, ReportSentence, ResearchPlan, SourceRef, span_matches,
)
from rag_research_agent.guard.research_filter import (
    CAUSAL_CUES, CAUSAL_PATTERN, CLICHE_CUES, CONSTRAINT_CUES, relevant_claims, verify_report,
)
from rag_research_agent.observe.tracing import serving_config, serving_trace_guard

SearchFn = Callable[[str, int], list[tuple[str, str]]]      # (query, k) -> [(source_id, masked text)]

# Stance is about arguments (opportunity vs risk), not about whether a number went up or down.
PRO_CUES = ("기회", "긍정", "기대", "전망이 밝", "효과를 낼", "개선 효과", "회복 기회", "성장 기회")
CON_CUES = ("위험", "리스크", "우려", "부작용", "한계", "악화", "손실", "부담")
LIMIT_CUES = ("다만", "제외", "조건", "한정", "이하", "이상", "대상")
_JOSA_END = re.compile(r"(이|가|은|는|을|를|과|와|의|에|도|로|으로|이나)$")
_METRIC_SUFFIX = re.compile(r"(?:[가-힣A-Za-z]{1,8}\s)?(?:[가-힣A-Za-z]{1,8}\s수(?![가-힣])|[가-힣A-Za-z]{0,8}(?:규모|비율|비중|점유율|성장률|증가율|감소율|률|율|량|액|가격|건수|수익|매출|생산성|지출액))")
_STOP_METRIC = {"비율", "비중", "규모", "가격", "건수"}
_VALUE = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(%p|%|퍼센트|조\s*원|억\s*원|만\s*원|원|달러|명|건|배|시간|년|개월|곳|대|톤)?")
_SENT = re.compile(r"\S.*?(?:[.!?。](?=\s|$)|$)", re.M)
_INJECTION = re.compile(r"(?i)(ignore (all|previous) instructions|이전 지시를? 무시|system prompt|시스템 프롬프트)")


def est_tokens(text: str) -> int:
    """Rough model-token estimate for mixed Korean/English text (~2 chars per token). Not billing."""
    return max(1, (len(text) + 1) // 2) if text else 0


@dataclass(frozen=True)
class ResearchConfig:
    name: str = "graph_full"
    k: int = 2                      # passages per retrieval branch
    stance_split: bool = True       # retrieve pro / con separately (confirmation-bias guard)
    gap_loop: bool = True           # targeted re-search for missing required metrics
    rewrite_loop: bool = True       # verifier sends style issues back to the writer
    use_checklist: bool = True      # merge a user checklist into the auto-extracted metrics
    auto_metrics: bool = True
    no_con_policy: str = "note"     # "note": state it and continue | "stop": ask for material
    max_gap_rounds: int = 2         # per metric
    max_rewrites: int = 2
    max_sentences: int = 5          # first-draft budget; feedback can raise it
    max_shadow_tokens: int = 12000  # cost limit (estimated model tokens per request)
    parallel_branches: bool = False  # requires thread-safe, deterministic, prefix-stable top-k search
    extractor: str = "rule"        # "rule" | "llm" (requires model and masker)
    planner: Literal["rule", "llm"] = "rule"  # requires planner_model and masker
    review_plan: bool = False       # interrupt after planning; requires a checkpointer and thread_id
    drop_generic: bool = False      # omit cliche-heavy paragraphs without numbers/cause/conditions
    rewrite_codes: frozenset[str] | None = None  # None: all non-GAP codes (legacy); empty: none
    gap_first: bool = True          # priority when both verifier routes are available
    per_node_token_cap: int | None = None  # input + output estimate per invocation; stop after node
    stop_if_no_progress: bool = False  # any code recurring in consecutive verifications


PlannerFn = Callable[[str, tuple[str, ...], ResearchConfig], ResearchPlan]
ExtractorFn = Callable[[list[SourceRef], ResearchPlan, set[str]],
                       tuple[list[Claim], list[Metric], list[Relation]]]
WriterFn = Callable[[ResearchPlan, list[Claim], tuple[str, ...], ResearchConfig, bool], Draft]
RefinerFn = Callable[[list[SourceRef], ResearchConfig], tuple[list[SourceRef], list[str]]]


class VerifierFn(Protocol):
    def __call__(self, draft: Draft, plan: ResearchPlan, claims: list[Claim],
                 metrics: list[Metric], *, expect_balance: bool) -> tuple[str, ...]: ...


# ------------------------------------------------------------------ rule nodes (pure)
def plan_rule(question: str, checklist: tuple[str, ...], cfg: ResearchConfig) -> ResearchPlan:
    found: list[tuple[str, str]] = []
    if cfg.use_checklist:
        found += [(m.strip(), "checklist") for m in checklist if m.strip()]
    if cfg.auto_metrics:
        for raw in _METRIC_SUFFIX.finditer(question or ""):
            m = raw.group(0).strip()
            words = m.split()
            if len(words) > 1 and _JOSA_END.search(words[0]):
                m = " ".join(words[1:])
            if m not in _STOP_METRIC and all(m != f for f, _ in found):
                found.append((m, "auto"))
    return ResearchPlan(tuple(m for m, _ in found), tuple(found))


def stance_of(text: str) -> str:
    pro, con = sum(c in text for c in PRO_CUES), sum(c in text for c in CON_CUES)
    return "con" if con > pro else "pro" if pro > con else "neutral"


def kind_of(text: str) -> str:
    low = text.lower()
    if any(c in low for c in CONSTRAINT_CUES):
        return "constraint"
    if any(c in low for c in CAUSAL_CUES) or CAUSAL_PATTERN.search(text):
        return "causal"
    return "fact" if _VALUE.search(text) else "claim"


def extract_rule(sources: list[SourceRef], plan: ResearchPlan, known: set[str]) -> tuple[list[Claim], list[Metric], list[Relation]]:
    claims, metrics, relations = [], [], []
    for source in sources:
        for n, match in enumerate(_SENT.finditer(source.text)):
            raw = match.group(0)
            text = raw.strip()
            if len(text) < 6:
                continue
            start = match.start() + (len(raw) - len(raw.lstrip()))
            claim = Claim(f"{source.source_id}#{n}", source.source_id, start, start + len(text), text,
                          stance_of(text), kind_of(text))
            if claim.claim_id in known:
                continue
            claims.append(claim)
            if claim.kind == "causal":
                relations.append(Relation("causes", claim.claim_id, claim.claim_id, source.source_id))
            if claim.kind == "constraint":
                relations.append(Relation("condition", claim.claim_id, claim.claim_id, source.source_id))
            for value in _VALUE.finditer(text):
                if not value.group(2):
                    continue
                name = next((m for m in plan.required_metrics if m in text), "")
                metrics.append(Metric(name, value.group(1).replace(",", ""), value.group(2), claim.claim_id, source.source_id))
    return claims, metrics, relations


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[가-힣A-Za-z]{2,}", text)}


def compare_rule(claims: list[Claim]) -> list[Relation]:
    pros = [c for c in claims if c.stance == "pro"]
    cons = [c for c in claims if c.stance == "con"]
    out = []
    for p in pros:
        for c in cons:
            if p.source_id != c.source_id and len(_terms(p.text) & _terms(c.text)) >= 2:
                out.append(Relation("contradicts", p.claim_id, c.claim_id))
    return out


def coverage_rule(plan: ResearchPlan, claims: list[Claim], metrics: list[Metric]) -> tuple[str, ...]:
    covered = {m.name for m in metrics if m.name}
    covered |= {m for m in plan.required_metrics for c in claims if m in c.text and _VALUE.search(c.text)}
    return tuple(m for m in plan.required_metrics if m not in covered)


def write_rule(plan: ResearchPlan, claims: list[Claim], feedback: tuple[str, ...], cfg: ResearchConfig,
               no_con: bool) -> Draft:
    """Extractive writer: picks claims from State by priority; feedback codes change the priority."""
    budget = cfg.max_sentences + (2 if feedback else 0)
    picked: list[Claim] = []

    def add(c: Optional[Claim]):
        if c is not None and c not in picked:
            picked.append(c)

    for metric in plan.required_metrics:                       # 1. required metrics, with numbers
        add(next((c for c in claims if metric in c.text and _VALUE.search(c.text)), None))
    relevant = relevant_claims(plan, claims, picked)
    causal = [c for c in relevant if c.kind == "causal"] or [c for c in claims if c.kind == "causal"][:1]
    constraints = [c for c in relevant if c.kind == "constraint"] or [c for c in claims if c.kind == "constraint"][:1]
    for c in (causal if "CAUSAL_LOSS" in feedback else causal[:2]):
        add(c)
    for c in (constraints if "CONSTRAINT_DROPPED" in feedback else constraints[:1]):
        add(c)
    if cfg.stance_split or "ONE_SIDED" in feedback:
        add(next((c for c in claims if c.stance == "pro"), None))
        add(next((c for c in claims if c.stance == "con"), None))
    if "LOW_DENSITY" in feedback:
        picked = [c for c in picked if c.kind != "claim" or not any(x in c.text for x in CLICHE_CUES)]
    must = [c for c in picked if c.kind in ("causal", "constraint") or any(m in c.text for m in plan.required_metrics)]
    rest = [c for c in picked if c not in must]
    chosen = (must + rest)[:max(budget, len(must))]
    sentences = [ReportSentence(c.text, (c.claim_id,)) for c in chosen]
    if no_con:
        sentences.append(ReportSentence(NO_COUNTER_EVIDENCE, note=True))
    return Draft(tuple(sentences))


def lead_baseline(sources: list[SourceRef], max_sentences: int) -> Draft:
    """Reference point, not a model: the first sentence of each retrieved document, in order."""
    out = []
    for s in sources:
        first = next((m.group(0).strip() for m in _SENT.finditer(s.text) if len(m.group(0).strip()) >= 6), "")
        if first:
            out.append(ReportSentence(first))
    return Draft(tuple(out[:max_sentences]))


def refine_rule(sources: list[SourceRef], cfg: ResearchConfig) -> tuple[list[SourceRef], list[str]]:
    kept, dropped = [], 0
    generic_dropped = 0
    for src in sources:
        if _INJECTION.search(src.text):
            dropped += 1
            continue
        if cfg.drop_generic:
            # Blank lines delimit paragraphs. Replace discarded characters with spaces
            # so extractors still return offsets into the original, retained source.
            def filter_paragraph(match):
                nonlocal generic_dropped
                text = match.group(0)
                sentences = [m.group(0).strip() for m in _SENT.finditer(text)
                             if len(m.group(0).strip()) >= 6]
                generic = sum(any(cue in sentence.lower() for cue in CLICHE_CUES)
                              for sentence in sentences)
                if (sentences and generic * 2 >= len(sentences)
                        and not re.search(r"\d", text) and kind_of(text) == "claim"):
                    generic_dropped += 1
                    return re.sub(r"[^\r\n]", " ", text)
                return text

            text = re.sub(r"\S.*?(?=\r?\n[ \t]*\r?\n|\Z)", filter_paragraph,
                          src.text, flags=re.S)
            if not text.strip():
                continue
            src = replace(src, text=text)
        kept.append(src)
    codes = [f"REFINE:keep={len(kept)},drop_injection={dropped}"]
    if cfg.drop_generic:
        codes.append(f"REFINE:DROP_GENERIC:{generic_dropped}")
    return kept, codes


# ------------------------------------------------------------------ state
def _merge_sources(old: list, new: list) -> list:
    # Checkpoint channels contain plain records; live nodes use SourceRef objects.
    def source_id(source):
        return source["source_id"] if isinstance(source, dict) else source.source_id

    seen = {source_id(s) for s in old}
    return old + [s for s in new if source_id(s) not in seen and not seen.add(source_id(s))]


def _checkpoint_state(state: dict, *, restore: bool = False) -> dict:
    """Keep application dataclasses out of saver serialization and reconstruct real types.

    Use explicit state fields rather than importing classes named by persisted data.
    The supplied saver and its serializer remain owned by the caller.
    """
    result = dict(state)
    # JSON/MessagePack savers may decode tuples as lists. Restore the public
    # state contract as well as dataclasses, including nested cost records.
    if restore:
        for field in ("checklist", "gaps", "feedback", "verify_codes"):
            if field in result:
                result[field] = tuple(result[field])
        if "cost" in result:
            result["cost"] = [tuple(item) for item in result["cost"]]
    if "plan" in result and result["plan"] is not None:
        plan = result["plan"]
        result["plan"] = (ResearchPlan(tuple(plan["required_metrics"]),
                                       tuple(tuple(item) for item in plan["origin"]),
                                       tuple(plan["perspectives"])) if restore else asdict(plan))
    for field, cls in (("sources", SourceRef), ("pending", SourceRef), ("claims", Claim),
                       ("metrics", Metric), ("relations", Relation)):
        if field in result:
            result[field] = [cls(**item) if restore else asdict(item) for item in result[field]]
    if "draft" in result and result["draft"] is not None:
        draft = result["draft"]
        result["draft"] = (Draft(tuple(ReportSentence(item["text"], tuple(item["claim_ids"]), item["note"])
                                      for item in draft["sentences"])) if restore else asdict(draft))
    return result


class ResearchState(TypedDict, total=False):
    question: str
    checklist: tuple
    plan: ResearchPlan
    sources: Annotated[list, _merge_sources]
    branch_hits: Annotated[list, operator.add]  # (branch index, raw ranked hits), parallel retrieval only
    claims: Annotated[list, operator.add]
    metrics: Annotated[list, operator.add]
    relations: Annotated[list, operator.add]
    pending: list                      # sources not yet extracted
    gaps: tuple
    gap_rounds: dict
    rewrites: int
    feedback: tuple
    draft: Draft
    verify_codes: tuple
    stopped: str
    log: Annotated[list, operator.add]          # codes only
    cost: Annotated[list, operator.add]         # (node, kind, tokens)


@dataclass(frozen=True)
class ResearchResult:
    report: str
    draft: Draft
    plan: ResearchPlan
    claims: tuple
    metrics: tuple
    sources: tuple
    verify_codes: tuple
    stopped: str
    log: tuple
    cost: tuple
    path: tuple
    interrupts: tuple = ()          # LangGraph Interrupt objects; path covers this invocation only

    @property
    def shadow_tokens(self) -> int:
        return sum(t for _, _, t in self.cost)


def build_research_graph(search: SearchFn, cfg: ResearchConfig = ResearchConfig(), *,
                         extractor_model=None, planner_model=None, masker=None,
                         checkpointer: BaseCheckpointSaver | None = None,
                         planner: PlannerFn | None = None, extractor: ExtractorFn | None = None,
                         writer: WriterFn | None = None, verifier: VerifierFn | None = None,
                         refiner: RefinerFn | None = None, fallback_on_error: bool = True):
    """Build the real graph with optional synchronous rule-signature plugins.

    Explicit plugins take precedence over the corresponding LLM option. Only
    exceptions raised by an explicit plugin are caught; rule failures propagate.
    Fallback logs contain fixed codes, never exception messages. Plugins receive
    already-masked inputs and must not mutate them or perform remote tracing.
    """
    if cfg.review_plan and checkpointer is None:
        raise ValueError("review_plan requires a checkpointer")
    if cfg.per_node_token_cap is not None and (
            type(cfg.per_node_token_cap) is not int or cfg.per_node_token_cap < 1):
        raise ValueError("per_node_token_cap must be a positive integer or None")
    if cfg.planner not in ("rule", "llm"):
        raise ValueError("unknown planner")
    model_planner = None
    if cfg.planner == "llm" and planner is None:
        from rag_research_agent.rag.research_llm import llm_planner
        if planner_model is None:
            raise ValueError("llm planning requires planner_model")
        model_planner = llm_planner(planner_model, masker)
    if cfg.extractor not in ("rule", "llm"):
        raise ValueError("unknown extractor")
    model_extractor = None
    if cfg.extractor == "llm" and extractor is None:
        from rag_research_agent.rag.research_llm import llm_extractor
        if extractor_model is None:
            raise ValueError("llm extraction requires extractor_model")
        model_extractor = llm_extractor(extractor_model, masker)

    def call_plugin(name, plugin, rule, codes, *args, **kwargs):
        if plugin is not None:
            try:
                return plugin(*args, **kwargs)
            except Exception:
                if not fallback_on_error:
                    raise
                codes.append("PLUGIN_FALLBACK:" + name.upper())
        return rule(*args, **kwargs)

    def spend(node: str, kind: str, text: str):
        return [(node, kind, est_tokens(text))]

    def plan_node(s: ResearchState):
        codes = []
        checklist = tuple(s.get("checklist") or ())
        if planner is not None:
            plan = call_plugin("planner", planner, plan_rule, codes, s["question"], checklist, cfg)
            codes.append("PLAN:" + ",".join(f"{m}<{o}>" for m, o in plan.origin))
        elif model_planner is None:
            plan = plan_rule(s["question"], checklist, cfg)
            codes = ["PLAN:" + ",".join(f"{m}<{o}>" for m, o in plan.origin)]
        else:
            plan = model_planner(s["question"], checklist, cfg, log=codes)
        return {"plan": plan, "gap_rounds": {}, "rewrites": 0, "feedback": (), "stopped": "",
                "log": codes,
                "cost": spend("plan", "model_in", s["question"])}

    def review_plan_node(s: ResearchState):
        metrics = _review_metrics(interrupt({"required_metrics": list(s["plan"].required_metrics)}))
        plan = replace(s["plan"], required_metrics=metrics,
                       origin=tuple((metric, "review") for metric in metrics))
        return {"plan": plan, "log": ["PLAN_REVIEWED"]}

    def _fetch(query: str, branch: str, k: int, known: set[str]) -> list[SourceRef]:
        found = []
        for sid, text in search(query, k + len(known)):
            if sid not in known and len(found) < k:
                found.append(SourceRef(sid, text, branch))
        return found

    def retrieve_node(s: ResearchState):
        known = {x.source_id for x in s.get("sources", [])}
        q = s["question"]
        found = _fetch(q, "base", cfg.k, known)
        if cfg.stance_split:
            known |= {x.source_id for x in found}
            found += _fetch(q + " " + " ".join(PRO_CUES[:4]), "pro", cfg.k, known)
            known |= {x.source_id for x in found}
            found += _fetch(q + " " + " ".join(CON_CUES[:4]), "con", cfg.k, known)
            known |= {x.source_id for x in found}
            found += _fetch(q + " " + " ".join(LIMIT_CUES), "limits", cfg.k, known)
        return {"sources": found, "pending": found, "log": [f"RETRIEVE:{len(found)}"],
                "cost": [("retrieve", "search", 0)]}

    branches = [("base", "")]
    if cfg.stance_split:
        branches += [("pro", " ".join(PRO_CUES[:4])), ("con", " ".join(CON_CUES[:4])),
                     ("limits", " ".join(LIMIT_CUES))]

    def branch_node(index: int, suffix: str):
        def retrieve_branch(s: ResearchState):
            # Earlier branches can add at most index*k unique IDs. Fetch enough ranked
            # candidates to fill this branch even when all earlier hits overlap.
            known = {x.source_id for x in s.get("sources", [])}
            query = s["question"] + (" " + suffix if suffix else "")
            hits = search(query, cfg.k * (index + 1) + len(known))
            return {"branch_hits": [(index, hits)]}
        return retrieve_branch

    def join_retrieval(s: ResearchState):
        known = {x.source_id for x in s.get("sources", [])}
        found = []
        for index, hits in sorted(s.get("branch_hits", []), key=lambda item: item[0]):
            # Reproduce sequential top-k request truncation and branch precedence.
            # Do not let completion order affect source text, claims or report order.
            selected = [SourceRef(sid, text, branches[index][0])
                        for sid, text in hits[:cfg.k + len(known)] if sid not in known][:cfg.k]
            found += selected
            known.update(src.source_id for src in selected)
        return {"sources": found, "pending": found, "log": [f"RETRIEVE:{len(found)}"],
                "cost": [("retrieve", "search", 0)]}

    def refine_node(s: ResearchState):
        codes = []
        kept, refine_codes = call_plugin("refiner", refiner, refine_rule, codes,
                                         s.get("pending", []), cfg)
        return {"pending": kept, "log": codes + refine_codes}

    def extract_node(s: ResearchState):
        known = {c.claim_id for c in s.get("claims", [])}
        codes = []
        if extractor is not None:
            claims, metrics, relations = call_plugin(
                "extractor", extractor, extract_rule, codes, s.get("pending", []), s["plan"], known)
        elif model_extractor is None:
            claims, metrics, relations = extract_rule(s.get("pending", []), s["plan"], known)
        else:
            claims, metrics, relations = model_extractor(s.get("pending", []), s["plan"], known, log=codes)
        sources = {x.source_id: x for x in s.get("sources", [])}
        valid = [c for c in claims if span_matches(c, sources)]
        ids = {c.claim_id for c in valid}
        return {"claims": valid, "metrics": [m for m in metrics if m.claim_id in ids],
                "relations": [r for r in relations if r.src in ids], "pending": [],
                "log": codes + [f"EXTRACT:claims={len(valid)},bad_span={len(claims) - len(valid)}"],
                "cost": spend("extract", "model_in", " ".join(x.text for x in s.get("pending", [])))}

    def compare_node(s: ResearchState):
        rel = compare_rule(s.get("claims", []))
        return {"relations": rel, "log": [f"COMPARE:contradicts={len(rel)}"]}

    def coverage_node(s: ResearchState):
        gaps = coverage_rule(s["plan"], s.get("claims", []), s.get("metrics", []))
        return {"gaps": gaps, "log": ["COVERAGE:" + (",".join(gaps) if gaps else "full")]}

    def gap_open(s: ResearchState) -> list[str]:
        rounds = s.get("gap_rounds") or {}
        return [g for g in s.get("gaps", ()) if rounds.get(g, 0) < cfg.max_gap_rounds]

    def retrieve_gap_node(s: ResearchState):
        rounds = dict(s.get("gap_rounds") or {})
        known = {x.source_id for x in s.get("sources", [])}
        found = []
        for g in gap_open(s):
            rounds[g] = rounds.get(g, 0) + 1
            new = _fetch(g + " " + s["question"], "gap:" + g, cfg.k, known | {x.source_id for x in found})
            found += new
        return {"sources": found, "pending": found, "gap_rounds": rounds,
                "log": [f"GAP_SEARCH:{len(found)}"], "cost": [("retrieve_gap", "search", 0)]}

    def no_con(s: ResearchState) -> bool:
        return cfg.stance_split and not any(c.stance == "con" for c in s.get("claims", []))

    def write_node(s: ResearchState):
        claims = s.get("claims", [])
        codes = []
        draft = call_plugin("writer", writer, write_rule, codes,
                            s["plan"], claims, tuple(s.get("feedback") or ()), cfg, no_con(s))
        # A model writer would see a compact State table, not raw documents: only claims that carry
        # content (numbers, cause, condition, stance), never the generic background sentences.
        prompt = " ".join(c.text for c in claims if c.kind != "claim" or c.stance != "neutral")
        return {"draft": draft, "log": codes + [f"WRITE:{len(draft.sentences)}"],
                "cost": spend("write", "model_in", s["question"] + prompt) + spend("write", "model_out", draft.body())}

    def verify_node(s: ResearchState):
        plugin_codes = []
        codes = call_plugin("verifier", verifier, verify_report, plugin_codes,
                            s["draft"], s["plan"], s.get("claims", []), s.get("metrics", []),
                              expect_balance=cfg.stance_split)
        update = {"verify_codes": codes,
                  "log": plugin_codes + ["VERIFY:" + (",".join(codes) if codes else "PASS")]}
        if cfg.stop_if_no_progress and set(codes) & set(s.get("verify_codes", ())):
            update["stopped"] = "NO_PROGRESS"
            update["log"].append("STOP:NO_PROGRESS")
        return update

    def after_coverage(s: ResearchState) -> str:
        if s.get("stopped"):
            return "finish"
        if cfg.gap_loop and gap_open(s) and _cost(s) < cfg.max_shadow_tokens:
            return "retrieve_gap"
        if cfg.no_con_policy == "stop" and no_con(s):
            return "stop_no_con"
        return "write"

    def after_verify(s: ResearchState) -> str:
        codes = s.get("verify_codes", ())
        if s.get("stopped") or not codes:
            return "finish"
        if _cost(s) >= cfg.max_shadow_tokens:
            return "finish"
        can_gap = cfg.gap_loop and any(c.startswith("GAP:") for c in codes) and gap_open(s)
        can_rewrite = (cfg.rewrite_loop and s.get("rewrites", 0) < cfg.max_rewrites
                       and any(not c.startswith("GAP:")
                               and (cfg.rewrite_codes is None or c in cfg.rewrite_codes) for c in codes))
        if can_gap and (cfg.gap_first or not can_rewrite):
            return "retrieve_gap"
        if can_rewrite:
            return "rewrite"
        if can_gap:
            return "retrieve_gap"
        return "finish"

    def rewrite_node(s: ResearchState):
        return {"rewrites": s.get("rewrites", 0) + 1, "feedback": tuple(s.get("verify_codes", ())), "log": ["REWRITE"]}

    def stop_no_con_node(s: ResearchState):
        return {"stopped": "NEED_COUNTER_EVIDENCE", "draft": Draft(), "log": ["STOP:NEED_COUNTER_EVIDENCE"]}

    def _cost(s: ResearchState) -> int:
        return sum(t for _, _, t in s.get("cost", []))

    def checkpoint_node(fn):
        if checkpointer is None and cfg.per_node_token_cap is None:
            return fn

        def run(s: ResearchState):
            live = _checkpoint_state(s, restore=True) if checkpointer is not None else s
            update = fn(live)
            # Keep the full estimate: clipping cost would under-report the work done.
            # This is a post-node shadow budget, not an injected model's max_tokens.
            if (cfg.per_node_token_cap is not None
                    and sum(t for _, _, t in update.get("cost", [])) >= cfg.per_node_token_cap):
                update["stopped"] = "PER_NODE_TOKEN_CAP"
                update["log"] = update.get("log", []) + ["STOP:PER_NODE_TOKEN_CAP"]
            return _checkpoint_state(update) if checkpointer is not None else update
        return run

    def checkpoint_route(fn):
        if checkpointer is None:
            return fn

        def route(s: ResearchState):
            return fn(_checkpoint_state(s, restore=True))
        return route

    g = StateGraph(ResearchState)

    def forward(source: str, targets: str | list[str]):
        if cfg.per_node_token_cap is None:
            for target in ([targets] if isinstance(targets, str) else targets):
                g.add_edge(source, target)
        else:
            def route(s):
                return END if s.get("stopped") else targets
            destinations = [targets] if isinstance(targets, str) else targets
            g.add_conditional_edges(source, checkpoint_route(route),
                                    {node: node for node in [*destinations, END]})
    for name, fn in [("plan", plan_node), ("retrieve", retrieve_node), ("refine", refine_node),
                     ("extract", extract_node), ("compare", compare_node), ("coverage", coverage_node),
                     ("retrieve_gap", retrieve_gap_node), ("write", write_node), ("verify", verify_node),
                     ("rewrite", rewrite_node), ("stop_no_con", stop_no_con_node)]:
        if name == "retrieve" and cfg.parallel_branches:
            continue
        g.add_node(name, checkpoint_node(fn))
    g.add_edge(START, "plan")
    retrieval_start = "plan"
    if cfg.review_plan:
        g.add_node("review_plan", checkpoint_node(review_plan_node))
        forward("plan", "review_plan")
        retrieval_start = "review_plan"
    if cfg.parallel_branches:
        branch_names = []
        for index, (branch, suffix) in enumerate(branches):
            name = "retrieve_" + branch
            g.add_node(name, checkpoint_node(branch_node(index, suffix)))
            branch_names.append(name)
        forward(retrieval_start, branch_names)
        g.add_node("join_retrieval", checkpoint_node(join_retrieval))
        g.add_edge(branch_names, "join_retrieval")
        forward("join_retrieval", "refine")
    else:
        forward(retrieval_start, "retrieve")
        forward("retrieve", "refine")
    forward("retrieve_gap", "refine")
    forward("refine", "extract")
    forward("extract", "compare")
    forward("compare", "coverage")
    coverage_routes = {"retrieve_gap": "retrieve_gap", "write": "write", "stop_no_con": "stop_no_con"}
    if cfg.per_node_token_cap is not None:
        coverage_routes["finish"] = END
    g.add_conditional_edges("coverage", checkpoint_route(after_coverage), coverage_routes)
    forward("write", "verify")
    g.add_conditional_edges("verify", checkpoint_route(after_verify), {"finish": END, "retrieve_gap": "retrieve_gap", "rewrite": "rewrite"})
    forward("rewrite", "write")
    g.add_edge("stop_no_con", END)
    return g.compile(checkpointer=checkpointer)


def _review_metrics(value) -> tuple[str, ...]:
    """Validate the human edit before resuming; keep order and remove duplicates."""
    if not isinstance(value, dict) or set(value) != {"required_metrics"}:
        raise ValueError("review requires required_metrics")
    metrics = value["required_metrics"]
    if not isinstance(metrics, (list, tuple)) or any(not isinstance(m, str) or not m.strip() for m in metrics):
        raise ValueError("required_metrics must be a list or tuple of nonblank strings")
    return tuple(dict.fromkeys(m.strip() for m in metrics))


class ResearchRunner:
    def __init__(self, search: SearchFn, cfg: ResearchConfig = ResearchConfig(), *,
                 extractor_model=None, planner_model=None, masker=None,
                 checkpointer: BaseCheckpointSaver | None = None):
        self.cfg, self.search = cfg, search
        self.checkpointer = checkpointer
        self.graph = build_research_graph(search, cfg, extractor_model=extractor_model,
                                          planner_model=planner_model, masker=masker, checkpointer=checkpointer)

    def _config(self, thread_id: str | None):
        if self.checkpointer is not None:
            if not isinstance(thread_id, str) or not thread_id.strip():
                raise ValueError("checkpointer requires a nonblank thread_id")
        elif thread_id is not None:
            raise ValueError("thread_id requires a checkpointer")
        config = {**serving_config(), "recursion_limit": 60}
        if thread_id is not None:
            config["configurable"] = {"thread_id": thread_id}
        return config

    def run(self, question: str, checklist: tuple[str, ...] = (), *,
            thread_id: str | None = None) -> ResearchResult:
        """Start a new request. Checkpointed requests need a fresh, caller-owned thread ID."""
        with serving_trace_guard():
            config = self._config(thread_id)
            if self.checkpointer is not None and self.graph.get_state(config).values:
                raise ValueError("thread_id already exists; resume it or use a new thread_id")
            return self._execute({"question": question, "checklist": tuple(checklist)}, config)

    def resume(self, thread_id: str, *, required_metrics: list[str] | tuple[str, ...]) -> ResearchResult:
        """Continue a paused plan review using edited, already-masked metric names."""
        metrics = _review_metrics({"required_metrics": required_metrics})
        with serving_trace_guard():
            config = self._config(thread_id)
            if self.checkpointer is None or not self.cfg.review_plan:
                raise ValueError("resume requires checkpointed plan review")
            snapshot = self.graph.get_state(config)
            if not any(task.interrupts for task in snapshot.tasks):
                raise ValueError("thread_id has no pending plan review")
            return self._execute(Command(resume={"required_metrics": list(metrics)}), config)

    def _execute(self, graph_input, config) -> ResearchResult:
        path: list[str] = []
        state: dict = {}
        interrupts = ()
        for step in self.graph.stream(graph_input, config=config, stream_mode="updates"):
            for node, update in step.items():
                if node == "__interrupt__":
                    interrupts = tuple(update)
                    continue
                path.append(node)
                if self.checkpointer is not None:
                    update = _checkpoint_state(update or {}, restore=True)
                for key, value in (update or {}).items():
                    if key in ("sources",):
                        state[key] = _merge_sources(state.get(key, []), value)
                    elif key in ("claims", "metrics", "relations", "log", "cost"):
                        state[key] = state.get(key, []) + list(value)
                    else:
                        state[key] = value
        if self.checkpointer is not None:
            # Resume updates omit completed nodes; read the full reducer state from the saver.
            state = _checkpoint_state(self.graph.get_state(config).values, restore=True)
        draft = state.get("draft") or Draft()
        if state.get("verify_codes") and draft.sentences:
            # budget spent before the report passed: say so instead of presenting it as verified
            draft = Draft(draft.sentences + (ReportSentence("검수 미통과 항목: " + ", ".join(state["verify_codes"]), note=True),))
        if state.get("stopped") in ("PER_NODE_TOKEN_CAP", "NO_PROGRESS"):
            draft = Draft(draft.sentences + (ReportSentence("연구 중단: " + state["stopped"], note=True),))
        return ResearchResult(draft.render(), draft, state.get("plan") or ResearchPlan(()), tuple(state.get("claims", [])),
                              tuple(state.get("metrics", [])), tuple(state.get("sources", [])),
                              tuple(state.get("verify_codes", ())), state.get("stopped", ""),
                              tuple(state.get("log", [])), tuple(state.get("cost", [])), tuple(path), interrupts)


def run_baseline(search: SearchFn, question: str, *, k: int = 6, max_sentences: int = 5,
                 corpus_text: str = "") -> ResearchResult:
    """Single-pass reference: one search, first sentences, no State, no checks.
    Shadow cost = what a single model call over the whole corpus would read (corpus_text) or the hits."""
    hits = [SourceRef(sid, text) for sid, text in search(question, k)]
    draft = lead_baseline(hits, max_sentences)
    read = corpus_text or " ".join(h.text for h in hits)
    cost = (("single_call", "model_in", est_tokens(question + read)), ("single_call", "model_out", est_tokens(draft.body())))
    return ResearchResult(draft.render(), draft, ResearchPlan(()), (), (), tuple(hits), (), "", ("BASELINE",), cost,
                          ("single_call",))


def keyword_search(corpus: dict[str, str]) -> SearchFn:
    """Tiny deterministic keyword search for experiments and tests (Chroma adapter comes later)."""
    def terms(text):
        return {t for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", text)}

    def search(query: str, k: int):
        q = terms(query)
        scored = []
        for sid, text in corpus.items():
            t = terms(text)
            hit = sum(1 for x in q if x in t or any(x in y for y in t if len(x) >= 2))
            if hit:
                scored.append((hit, sid))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [(sid, corpus[sid]) for _, sid in scored[:k]]
    return search
