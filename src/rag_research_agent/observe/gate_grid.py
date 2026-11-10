"""Compare-only gate calibration and held-out confirmation with Wilson intervals."""
import math

MATURITY = "incubating"


def wilson(errors, n, z=1.959963984540054):
    if n < 0 or not 0 <= errors <= n:
        raise ValueError("require 0 <= errors <= n")
    if not n:
        return {"errors": 0, "n": 0, "rate": None, "wilson95": None}
    p = errors / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return {"errors": errors, "n": n, "rate": p,
            "wilson95": [max(0., center - radius), min(1., center + radius)]}


def rates(rows, absolute, gap):
    negatives = [r for r in rows if not r["expected"]]
    positives = [r for r in rows if r["expected"]]
    def accepted(row):
        return row["vector"]["top1"] >= absolute and row["vector"]["gap"] >= gap
    return {"tau_abs": absolute, "tau_gap": gap,
            "false_accept": wilson(sum(accepted(r) for r in negatives), len(negatives)),
            "false_refusal": wilson(sum(not accepted(r) for r in positives), len(positives))}


def sweep(rows, absolutes, gaps):
    rows = [r for r in rows if r.get("type") != "injection"]
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)) or any(r.get("split") not in {"compare", "confirm"} for r in rows):
        raise ValueError("unique IDs and explicit compare/confirm splits required")
    absolutes, gaps = list(absolutes), list(gaps)
    if not absolutes or not gaps or any(not math.isfinite(x) for x in absolutes + gaps):
        raise ValueError("finite, nonempty threshold grids required")
    if any(not math.isfinite(r["vector"][k]) for r in rows for k in ("top1", "gap")):
        raise ValueError("non-finite score")
    compare = [r for r in rows if r["split"] == "compare"]
    confirm = [r for r in rows if r["split"] == "confirm"]
    grid = [rates(compare, a, g) for a in absolutes for g in gaps]
    eligible = [r for r in grid if r["false_accept"]["n"] and r["false_refusal"]["n"]]
    # Predeclared objective. Confirm is never consulted for selection or grid curves.
    selected = min(eligible, key=lambda r: (r["false_accept"]["rate"], r["false_refusal"]["rate"],
                                           -r["tau_abs"], -r["tau_gap"])) if eligible else None
    return {"compare_grid": grid, "selected": selected,
            "confirm": rates(confirm, selected["tau_abs"], selected["tau_gap"]) if selected else None,
            "calibrated_on": [r["id"] for r in compare], "confirmed_on": [r["id"] for r in confirm],
            "selection": "min compare false accept, then false refusal, then higher thresholds",
            "note": "0건 오수용은 보장이 아니다. 작은 표본의 Wilson 95% 구간을 함께 해석한다."}
