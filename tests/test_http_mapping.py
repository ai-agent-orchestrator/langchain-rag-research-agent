"""N11: every pipeline outcome maps to a fixed status/body, and no raw text leaks into error bodies."""
from types import SimpleNamespace

import pytest

from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.core.types import Status
from rag_research_agent.rag.answer import DraftRejected, EvidenceStatus
from rag_research_agent.rag.execution import InferenceCapacityExceeded, InferenceTimeout
from rag_research_agent.rag.guidance import BackboneNotConfigured, GuidanceDisabled, GuidanceReply
from rag_research_agent.rag.http_mapping import (
    ERRORS, REPLY_STATUS, map_exception, map_outcome, map_reply, validate_request,
)
from rag_research_agent.retrieve.breaker import CircuitOpen

SECRET = "홍길동 010-1234-5678 C:\\Users\\x\\secret.txt Traceback"


def test_answer_and_no_evidence_are_200_with_the_existing_body():
    ok = GuidanceReply(Status.OK, "안내", "model-v1", EvidenceStatus.FOUND, ("c1",), 1, "OK")
    status, body, headers = map_reply(ok)
    assert status == 200 and body == ok.to_dict() and body["citationIds"] == ["c1"]
    assert headers["Content-Type"].startswith("application/json")
    more = GuidanceReply(Status.REQUEST_MORE, "자료를 준비해 주세요", retrieval_status="EMPTY")
    status, body, _ = map_reply(more)
    assert status == 200 and body["evidenceStatus"] == "NOT_FOUND" and body["model"] == "not-invoked"


def test_policy_block_is_an_answer_not_a_technical_error():
    blocked = GuidanceReply(Status.BLOCKED, "요청을 처리할 수 없습니다.", reason_code="BLOCKED_JAILBREAK")
    status, body, _ = map_reply(blocked)
    assert status == 200 and body == {"blocked": True, "reasonCode": "BLOCKED_JAILBREAK",
                                      "answer": "요청을 처리할 수 없습니다."}


def test_every_status_the_pipeline_produces_is_mapped():
    # GuidancePipeline.ainvoke returns exactly these three statuses.
    assert set(REPLY_STATUS) == {Status.OK, Status.REQUEST_MORE, Status.BLOCKED}


def test_unknown_reply_status_is_a_server_error():
    status, body, _ = map_reply(GuidanceReply(Status.OUTPUT_REJECTED, "x"))
    assert (status, body) == (500, {"error": "INTERNAL_ERROR"})


@pytest.mark.parametrize("error,status,code,retry", [
    (RetrievalUnavailable(SECRET), 503, "RETRIEVAL_UNAVAILABLE", "30"),
    (CircuitOpen(SECRET), 503, "RETRIEVAL_UNAVAILABLE", "30"),             # breaker open is still 503
    (InferenceCapacityExceeded(SECRET), 503, "GENERATION_CAPACITY_EXCEEDED", "5"),
    (InferenceTimeout(SECRET), 504, "INFERENCE_TIMEOUT", None),
    (BackboneNotConfigured(SECRET), 503, "BACKBONE_NOT_CONFIGURED", None),
    (GuidanceDisabled(SECRET), 503, "RAG_DISABLED", None),
    (DraftRejected(SECRET), 502, "AI_DRAFT_REJECTED", None),
    (ValueError(SECRET), 500, "INTERNAL_ERROR", None),                      # inside the pipeline = server bug
    (KeyError(SECRET), 500, "INTERNAL_ERROR", None),
])
def test_exceptions_map_to_fixed_codes_without_raw_text(error, status, code, retry):
    got_status, body, headers = map_exception(error)
    assert (got_status, body) == (status, {"error": code})
    assert headers.get("Retry-After") == retry
    assert "홍길동" not in repr((body, headers)) and "Traceback" not in repr(body)


def test_error_table_covers_every_documented_exception_once():
    kinds = [kind for kind, *_ in ERRORS]
    assert len(kinds) == len(set(kinds))
    assert {RetrievalUnavailable, InferenceCapacityExceeded, InferenceTimeout, BackboneNotConfigured,
            GuidanceDisabled, DraftRejected} == set(kinds)


@pytest.mark.parametrize("request_body", [
    None, [], {"coreStatement": "x"}, {"caseType": "TAX", "coreStatement": "x"},
    {"caseType": "CIVIL", "coreStatement": "   "}, {"caseType": "CIVIL", "coreStatement": "x", "desiredNextStep": 3},
])
def test_malformed_requests_are_400_before_the_pipeline_runs(request_body):
    status, body, _ = validate_request(request_body)
    assert (status, body) == (400, {"error": "INVALID_REQUEST"})


def test_valid_request_passes_validation_and_client_name_is_not_required():
    assert validate_request({"caseType": "CIVIL", "coreStatement": "합성 상담 자료"}) is None


def test_map_outcome_routes_replies_exceptions_and_guardrail_results():
    reply = GuidanceReply(Status.REQUEST_MORE, "자료")
    assert map_outcome(reply)[0] == 200
    assert map_outcome(RetrievalUnavailable("x"))[0] == 503
    assert map_outcome(SimpleNamespace(reply=reply, stop_code=""))[0] == 200
    stopped = map_outcome(SimpleNamespace(reply=None, stop_code="LOOP_LIMIT"))
    assert stopped[:2] == (503, {"error": "GUARDRAIL_STOPPED"})
    assert map_outcome(object())[:2] == (500, {"error": "INTERNAL_ERROR"})
