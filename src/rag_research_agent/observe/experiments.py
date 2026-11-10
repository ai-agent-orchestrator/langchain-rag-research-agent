"""Shared offline evaluation controls; fake values are path tests, not model evidence."""
from statistics import mean

MATURITY = "incubating"


def instruction_option(value):
    if value not in {"none", "default"} and not (value.startswith("custom:") and value[7:].strip()):
        raise ValueError("instruction must be none, default, or custom:<text>")
    return value


class QueryInstruction:
    """Change only query encoding. BGE-M3 stays an unprefixed control."""
    def __init__(self, base, instruction="default"):
        self.base = base
        self.instruction = instruction_option(instruction)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def encode_query(self, text):
        if "bge-m3" in self.model_id.lower():
            return self.base.encode_documents([text])[0]
        if self.instruction == "default":
            return self.base.encode_query(text)
        if self.instruction.startswith("custom:"):
            text = f"Instruct: {self.instruction[7:]}\nQuery: {text}"
        return self.base.encode_documents([text])[0]


def score_summary(rows, fake):
    """Rows carry relevance fractions at 3 and correct/no-evidence score samples."""
    evidence = [r for r in rows if r["expected"]]
    correct = [r["correct_score"] for r in evidence if r.get("correct_score") is not None]
    negatives = [r["vector"]["top1"] for r in rows if not r["expected"]]
    metrics = {"recall_at_3": mean(r["recall_at_3"] for r in evidence) if evidence else None,
               "mrr": mean(r["reciprocal_rank"] for r in evidence) if evidence else None,
               "correct_no_evidence_margin": mean(correct) - mean(negatives) if correct and negatives else None,
               "correct_n": len(correct), "no_evidence_n": len(negatives)}
    return {"path_test": metrics if fake else None, "real_model": None if fake else metrics}


def metric_table(summary):
    # Separate columns in persisted results and separate labelled rows in this compact table.
    lines = ["| 지표 | fake: 경로 시험 | 실제 모델 |", "| --- | --- | --- |"]
    for key in ("recall_at_3", "mrr", "correct_no_evidence_margin"):
        lines.append("| " + key + " | " + " | ".join(str(summary[k].get(key)) if summary[k] else "미실행" for k in ("path_test", "real_model")) + " |")
    return lines
