"""Owner-run, explicit network preparation; ordinary providers load cached revisions only."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag_research_agent.embed.registry import MODELS, DEFAULT_MODELS


def prepare(name, revision=None, out=DEFAULT_MODELS):
    # Explicit preparation only. No .env, authentication tokens or remote code.
    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import HfApi, snapshot_download
    model_id = MODELS[name]["model_id"]
    pinned = HfApi(token=False).model_info(model_id, revision=revision or "main").sha
    if not re.fullmatch(r"[0-9a-fA-F]{40}", pinned or ""):
        raise ValueError("model repository did not return an exact revision")
    path = snapshot_download(repo_id=model_id, revision=pinned, token=False)
    out = Path(out)
    records = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    records[name] = {**MODELS[name], "revision": pinned, "cache_path": str(path)}
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(".tmp")
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(out)
    return records[name]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, choices=["e5", "bge-m3"])
    ap.add_argument("--revision")
    args = ap.parse_args(argv)
    print(json.dumps(prepare(args.model, args.revision), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
