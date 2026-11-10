"""Export synthetic evaluation files. --upload is reserved for explicit owner execution."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rag_research_agent.rag.langsmith_export import ExportError, export_files, upload


def main(argv=None, *, client_factory=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", required=True)
    ap.add_argument("--results")
    ap.add_argument("--out", default=".runs/langsmith")
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args(argv)
    try:
        key = os.environ.get("LANGSMITH_API_KEY")
        if args.upload and not key:
            raise ExportError("LANGSMITH_API_KEY가 없습니다. --upload 없이 로컬 파일을 먼저 만드세요")
        exports = export_files(args.set, args.out, args.results)
        if args.upload:
            print(upload(exports, api_key=key, client_factory=client_factory))
        print(Path(args.out).resolve())
        return 0
    except (ExportError, OSError, ValueError, KeyError) as exc:
        print(f"내보내기 오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
