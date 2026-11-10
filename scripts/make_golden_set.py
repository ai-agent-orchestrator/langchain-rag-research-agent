"""Turn + keep / - cliche marked lines into a local golden set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.golden_edge_eval import evaluate, split_sentences


def make_set(marked, name, note=""):
    lines, keep, cliche = [], [], []
    for n, line in enumerate(marked.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("# "):
            continue
        flag = line[0] if line.startswith(("+ ", "- ")) else ""
        content = line[2:].strip() if flag else line
        if not content:
            continue
        segs = split_sentences(content)
        if flag and len(segs) > 1:
            warnings.warn(f"{n}행: 여러 문장으로 분할되어 같은 표시를 적용합니다", UserWarning)
        target = keep if flag == "+" else cliche if flag == "-" else None
        if target is not None:
            target.extend(content[s.start:s.end] for s in segs)
        lines.append(content)
    draft = " ".join(lines)
    sentences = {draft[s.start:s.end] for s in split_sentences(draft)}
    if any(s not in sentences for s in keep + cliche):
        raise ValueError("표시 문장이 이어진 초안에서 분리되지 않습니다. 줄 끝 문장부호를 확인해 주세요")
    if not draft:
        raise ValueError("빈 초안입니다")
    return {"name": name, "note": note, "draft": draft, "must_keep": keep, "cliche": cliche}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--name", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    try:
        if not args.name or Path(args.name).name != args.name or args.name in (".", ".."):
            raise ValueError("name은 경로가 아닌 이름이어야 합니다")
        out = Path(args.out or f".runs/golden/{args.name}.json").resolve()
        if any(out.is_relative_to(ROOT / part) for part in ("data", "profiles")):
            raise ValueError("data/와 profiles/에는 쓰지 않습니다. .runs/golden/을 사용해 주세요")
        if out == Path(args.file).resolve():
            raise ValueError("입력 파일을 덮어쓸 수 없습니다")
        data = make_set(Path(args.file).read_text(encoding="utf-8-sig"), args.name, args.note)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out)
        if args.check:
            run = evaluate(ROOT / "data/golden_rules/research_v1.json", out, [])
            print(json.dumps(run["metrics"], ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
