"""Opt-in terminal review around real research/guardrail runners.

Questions, drafts and evidence must already be masked by the caller/pipeline.
They belong to the injected checkpoint store, never to the code-only event.
Existing runners and their default entry points are unchanged.
"""
from __future__ import annotations

MATURITY = "incubating"

import asyncio
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from rag_research_agent.core.research import Draft, ReportSentence
from rag_research_agent.guard.domain_filter import get_filter
from rag_research_agent.guard.research_filter import verify_report
from rag_research_agent.observe.tracing import serving_config, serving_trace_guard
from rag_research_agent.rag.guardrail_graph import GuardrailRunner, VERIFY_FAILED_ANSWER
from rag_research_agent.rag.research_graph import ResearchRunner, _checkpoint_state


@dataclass(frozen=True)
class ReviewPolicy:
    domain: str = "research"
    human_review: bool | None = None

    @property
    def enabled(self) -> bool:
        return self.human_review if self.human_review is not None else self.domain in {"legal", "medical"}


class ReviewState(TypedDict, total=False):
    request: dict
    question: str
    draft: str
    answer: str
    failure_codes: list[str]
    evidence: list[str]
    branch: str
    end_type: str
    reviewer_action: str
    research_context: dict


@dataclass(frozen=True)
class HumanReviewResult:
    answer: str
    failure_codes: tuple[str, ...]
    end_type: str
    reviewer_action: str = ""
    interrupts: tuple = ()

    def event(self) -> dict:
        """Local event extension; deliberately excludes review text and evidence."""
        return {"end_type": self.end_type, "reviewer_action": self.reviewer_action}


def _decision(value):
    if (not isinstance(value, dict) or not isinstance(value.get("action"), str)
            or value["action"] not in {"approve", "edit", "reject"}):
        raise ValueError("review action must be approve, edit or reject")
    if value["action"] == "edit":
        if not isinstance(value.get("answer"), str) or not value["answer"].strip():
            raise ValueError("edit requires a nonblank masked answer")
        if set(value) != {"action", "answer"}:
            raise ValueError("edit accepts only action and answer")
    elif set(value) != {"action"}:
        raise ValueError("approve/reject accepts only action")
    return value


class HumanReviewRunner:
    """Explicit wrapper with injected saver; resume is bound to a pending thread.

    Disabled policies return the underlying runner's original result unchanged.
    Enabled policies return HumanReviewResult. Failed edits request review again.
    A research plan-review session must be handled separately before this wrapper.
    """

    def __init__(self, runner, *, policy: ReviewPolicy | None = None,
                 checkpointer=None, verifier=None):
        if not isinstance(runner, (ResearchRunner, GuardrailRunner)):
            raise TypeError("runner must be ResearchRunner or GuardrailRunner")
        self.runner = runner
        domain = getattr(runner, "domain", None)
        self.policy = policy or ReviewPolicy(getattr(domain, "name", "research"))
        self.verifier = verifier or domain
        self.checkpointer = checkpointer
        self.graph = None
        if not self.policy.enabled:
            return
        if checkpointer is None:
            raise ValueError("human review requires a checkpointer")
        if self.verifier is None:
            self.verifier = get_filter(self.policy.domain)
        if isinstance(runner, ResearchRunner) and (runner.checkpointer is not None or runner.cfg.review_plan):
            raise ValueError("nested research checkpoint/plan review requires separate integration")

        async def execute(state):
            request = state["request"]
            if isinstance(self.runner, ResearchRunner):
                result = await asyncio.to_thread(self.runner.run, request["coreStatement"],
                                                tuple(request.get("checklist", ())))
                # Use the actual draft, without the appended failure notice.
                draft = result.draft.body()
                evidence = [c.text for c in result.claims]
                return {"question": request["coreStatement"], "draft": draft,
                        "answer": result.report, "failure_codes": list(result.verify_codes),
                        "evidence": evidence, "branch": "default", "end_type": result.end_type,
                        "reviewer_action": "", "research_context": _checkpoint_state({
                            "plan": result.plan, "claims": list(result.claims),
                            "metrics": list(result.metrics)})}
            # Updates preserve the last generated draft before finish replaces it
            # with VERIFY_FAILED_ANSWER. Do not rerun generation on resume.
            live = {}
            draft, evidence = "", []
            async for update in self.runner.graph.astream({"request": request},
                                                         config=serving_config(), stream_mode="updates"):
                for node, values in update.items():
                    live.update(values or {})
                    if node == "rag" and (values or {}).get("reply") is not None:
                        draft = values["reply"].answer
                        evidence = list(values.get("evidence", ()))
            reply = live.get("reply")
            return {"question": request.get("coreStatement", ""), "draft": draft,
                    "answer": reply.answer if reply else VERIFY_FAILED_ANSWER,
                    "failure_codes": list(live.get("verify_codes", ())), "evidence": evidence,
                    "branch": live.get("branch") or "default", "reviewer_action": "",
                    "end_type": "cutoff" if live.get("stop_code") else (
                        "give_up" if live.get("verify_codes") else "END")}

        def review(state):
            choice = _decision(interrupt({"question": state["question"], "draft": state["draft"],
                                          "failure_codes": state["failure_codes"],
                                          "evidence": state["evidence"]}))
            action = choice["action"]
            answer = state["draft"] if action == "approve" else VERIFY_FAILED_ANSWER
            codes = state["failure_codes"]
            if action == "edit":
                answer = choice["answer"]
                verdict = self.verifier.verify(answer, tuple(state["evidence"]), state["branch"])
                edit_codes = list(verdict.codes) if not verdict.ok else []
                if isinstance(self.runner, ResearchRunner):
                    context = _checkpoint_state(state["research_context"], restore=True)
                    # Conservative attribution: plain edits may cite only claims
                    # whose full text survives, rather than assigning every source.
                    cited = tuple(c.claim_id for c in context["claims"] if c.text in answer)
                    draft = Draft((ReportSentence(answer, cited),))
                    edit_codes.extend(verify_report(draft, context["plan"], context["claims"],
                        context["metrics"], expect_balance=self.runner.cfg.stance_split,
                        check_claim_alignment=True))
                    grader = self.runner.cfg.grader
                    if grader is not None and not grader.grade_grounded(answer, tuple(state["evidence"])).grounded:
                        edit_codes.append("UNGROUNDED")
                if edit_codes:
                    return {"draft": answer, "answer": VERIFY_FAILED_ANSWER,
                            "failure_codes": list(dict.fromkeys(edit_codes)), "reviewer_action": "edit",
                            "end_type": "give_up"}
                codes = []
            return {"answer": answer, "failure_codes": codes,
                    "reviewer_action": action, "end_type": "human"}

        graph = StateGraph(ReviewState)
        graph.add_node("execute", execute)
        graph.add_node("human_review", review)
        graph.add_edge(START, "execute")
        graph.add_conditional_edges("execute", lambda s: "human_review" if s["failure_codes"] else END)
        graph.add_conditional_edges("human_review", lambda s: END if s["end_type"] == "human" else "human_review")
        self.graph = graph.compile(checkpointer=checkpointer)

    def _config(self, thread_id):
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("human review requires a nonblank thread_id")
        return {**serving_config(), "configurable": {"thread_id": thread_id}}

    async def ainvoke(self, request: dict, *, thread_id: str | None = None):
        with serving_trace_guard():
            if not self.policy.enabled:
                if isinstance(self.runner, ResearchRunner):
                    return await asyncio.to_thread(self.runner.run, request["coreStatement"],
                                                   tuple(request.get("checklist", ())), thread_id=thread_id)
                return await self.runner.ainvoke(request)
            config = self._config(thread_id)
            if (await self.graph.aget_state(config)).values:
                raise ValueError("thread_id already exists; resume or use a new thread_id")
            return await self._execute({"request": request}, config)

    async def resume(self, thread_id: str, decision: dict) -> HumanReviewResult:
        decision = _decision(decision)
        if self.graph is None:
            raise ValueError("human review is disabled")
        with serving_trace_guard():
            config = self._config(thread_id)
            snapshot = await self.graph.aget_state(config)
            if not any(task.interrupts for task in snapshot.tasks):
                raise ValueError("thread_id has no pending human review")
            return await self._execute(Command(resume=decision), config)

    async def _execute(self, value, config):
        state = await self.graph.ainvoke(value, config=config)
        pending = tuple(state.get("__interrupt__", ()))
        return HumanReviewResult("" if pending else state["answer"],
                                 tuple(state["failure_codes"]), state["end_type"],
                                 state.get("reviewer_action", ""), pending)
