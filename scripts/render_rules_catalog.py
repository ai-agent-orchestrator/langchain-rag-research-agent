"""Render a golden-rules JSON file into a readable Markdown catalog (the JSON stays the single source).

    python scripts/render_rules_catalog.py > docs/GOLDEN_RULES_CATALOG.ko.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILLARS = {"correlation": "상관관계", "trend": "트렌드", "numbers": "의미 있는 수치", "attribution": "누가·언제"}


def cell(x) -> str:
    return ", ".join(f"`{v}`" for v in x) if x else "-"


def render(path: Path) -> str:
    d = json.loads(path.read_text(encoding="utf-8"))
    pillar = d.get("pillar_rules", [])
    packs = d.get("packs", {})
    wr = d.get("weight_rules", [])
    n_common = len(d["causal_types"]) + len(pillar) + len(d.get("cliche_rules", [])) + len(wr)
    n_pack = sum(len(p["rules"]) for p in packs.values())
    out = [f"# 골든룰 카탈로그: {d.get('label', '')}", "",
           f"> 자동 생성 문서입니다. 정본은 `{path.relative_to(ROOT)}`이며, 이 문서를 직접 고치지 말고 JSON을 고친 뒤 "
           "`python scripts/render_rules_catalog.py > docs/GOLDEN_RULES_CATALOG.ko.md`로 다시 만드세요. "
           "모든 규칙은 v1 초안이며 검증 전입니다.", "",
           f"공통 규칙 **{n_common}개** + 분야 묶음 **{n_pack}개**. 설명: [GOLDEN_RULES.ko.md](GOLDEN_RULES.ko.md) · "
           "실행: [FEEDBACK_LOOP.ko.md](FEEDBACK_LOOP.ko.md)", "",
           "## 가중치", "", "| 요소 | 값 |", "| --- | --- |"]
    out += [f"| {k} | {v} |" for k, v in d["weights"].items()]
    out += ["", f"## 인과관계 ({len(d['causal_types'])})", "", "| ID | 묶음 | 이름 | 신호 표현 | 항상 보호 |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {t['id']} | {t.get('group', '')} | {t['name']} | {cell(t.get('cues'))} | {'예' if t.get('always_protect') else ''} |"
            for t in d["causal_types"]]
    for key, title in PILLARS.items():
        rows = [r for r in pillar if r["pillar"] == key]
        out += ["", f"## {title} ({len(rows)})", "", "| ID | 이름 | 신호 표현 | 패턴 | 항상 보호 |", "| --- | --- | --- | --- | --- |"]
        out += [f"| {r['id']} | {r['name']} | {cell(r.get('cues'))} | {cell(r.get('patterns'))} | {'예' if r.get('always_protect') else ''} |" for r in rows]
    cl = d.get("cliche_rules", [])
    out += ["", f"## 뻔한 클리셰, 감점 ({len(cl)})", "", "| ID | 이름 | 신호 표현 | 패턴 |", "| --- | --- | --- | --- |"]
    out += [f"| {r['id']} | {r['name']} | {cell(r.get('cues'))} | {cell(r.get('patterns'))} |" for r in cl]
    out += ["", f"## 가중치 규칙 ({len(wr)}) — 걸리면 점수를 올림 (boost)", "",
            "| ID | 이름 | 신호 표현 | 패턴 | 가중 |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {r['id']} | {r['name']} | {cell(r.get('cues'))} | {cell(r.get('patterns'))} | {r.get('weight', 1.0)} |" for r in wr]
    pol = d.get("cliche_policy")
    if pol:
        out += ["", "### 클리셰 정책", "", f"- 내용 신호(수치·인과·기둥·묶음)가 함께 있으면 감점하지 않음: {pol.get('penalize_only_without_content')}",
                f"- 클리셰만으로 삭제하지 않음: {pol.get('never_delete_on_cliche_alone')}", f"- 근거: {pol.get('note', '-')}"]
    out += ["", f"## 분야 묶음 ({n_pack}) — 실행할 때 `--packs`로 켭니다"]
    for name, p in packs.items():
        out += ["", f"### {name} ({len(p['rules'])})", "", f"근거: {p.get('why', '-')}", "",
                "| ID | 이름 | 신호 표현 |", "| --- | --- | --- |"]
        out += [f"| {r['id']} | {r['name']} | {cell(r.get('cues'))} |" for r in p["rules"]]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/golden_rules/research_v1.json"
    sys.stdout.write(render(src.resolve()))
