"""Inter-annotator agreement metrics.

Three views of the same data:

- Frame-level Cohen's κ — robust to segmentation mismatch. Both annotators'
  segment text is projected onto a 10ms grid (silence outside any segment).
  Computed in pure Python without sklearn to keep the deploy footprint flat.

- Boundary-tolerance hit-rate — for each annotator's set of segment
  start/end times, the fraction that have a matching boundary in the other
  annotator's set within ±50ms. Two rates (A→B and B→A) plus their F1.

- Matched-segment phoneme error rate — segments are bipartite-matched by
  max IoU above a 0.5 threshold; for matched pairs, the IPA strings are
  compared via Levenshtein normalized by max length.

Limitations to note in v1:
- Frame-κ uses the whole segment IPA string as the label, so two
  annotators who agree phoneme-by-phoneme but disagree on segment grouping
  will undershoot. A per-character/per-phoneme variant is a future step.
- Greedy bipartite matching, not Hungarian. Fast and adequate for the
  small segment counts we see in practice.
"""

from __future__ import annotations

from typing import Any

HOP_SECONDS = 0.01
BOUNDARY_TOLERANCE_SECONDS = 0.05
IOU_THRESHOLD = 0.5
SILENCE_LABEL = "<sil>"


def _frame_labels(segments: list[dict[str, Any]], total_duration: float) -> list[str]:
    n_frames = max(1, int(total_duration / HOP_SECONDS) + 1)
    labels = [SILENCE_LABEL] * n_frames
    for seg in segments:
        i_start = max(0, int(seg["startTime"] / HOP_SECONDS))
        i_end = min(n_frames, int(seg["endTime"] / HOP_SECONDS))
        text = seg.get("text") or SILENCE_LABEL
        for i in range(i_start, i_end):
            labels[i] = text
    return labels


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    n = min(len(labels_a), len(labels_b))
    if n == 0:
        return None
    classes: set[str] = set(labels_a[:n]) | set(labels_b[:n])
    p_o = sum(1 for i in range(n) if labels_a[i] == labels_b[i]) / n
    if len(classes) < 2:
        return 1.0
    p_e = 0.0
    for c in classes:
        p_a = sum(1 for x in labels_a[:n] if x == c) / n
        p_b = sum(1 for x in labels_b[:n] if x == c) / n
        p_e += p_a * p_b
    if p_e >= 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def _boundary_times(segments: list[dict[str, Any]]) -> list[float]:
    seen: set[float] = set()
    for s in segments:
        seen.add(round(float(s["startTime"]), 4))
        seen.add(round(float(s["endTime"]), 4))
    return sorted(seen)


def _hit_rate(a: list[float], b: list[float], tol: float) -> float:
    if not a:
        return 0.0
    return sum(1 for x in a if any(abs(x - y) <= tol for y in b)) / len(a)


def boundary_agreement(
    a_segs: list[dict[str, Any]],
    b_segs: list[dict[str, Any]],
    tol: float = BOUNDARY_TOLERANCE_SECONDS,
) -> dict[str, float]:
    bounds_a = _boundary_times(a_segs)
    bounds_b = _boundary_times(b_segs)
    p_ab = _hit_rate(bounds_a, bounds_b, tol)
    p_ba = _hit_rate(bounds_b, bounds_a, tol)
    f1 = (2 * p_ab * p_ba / (p_ab + p_ba)) if (p_ab + p_ba) > 0 else 0.0
    return {"precisionAtoB": p_ab, "precisionBtoA": p_ba, "f1": f1}


def _iou(seg_a: dict[str, Any], seg_b: dict[str, Any]) -> float:
    a0, a1 = float(seg_a["startTime"]), float(seg_a["endTime"])
    b0, b1 = float(seg_b["startTime"]), float(seg_b["endTime"])
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def matched_segment_per(
    a_segs: list[dict[str, Any]],
    b_segs: list[dict[str, Any]],
    iou_threshold: float = IOU_THRESHOLD,
) -> tuple[int, float | None]:
    """Greedy max-IoU matching, then mean length-normalized Levenshtein on IPA."""
    used_b: set[int] = set()
    matched_pairs: list[tuple[int, int, float]] = []
    for ai, sa in enumerate(a_segs):
        best_iou = 0.0
        best_bi: int | None = None
        for bi, sb in enumerate(b_segs):
            if bi in used_b:
                continue
            iou = _iou(sa, sb)
            if iou > best_iou:
                best_iou = iou
                best_bi = bi
        if best_bi is not None and best_iou >= iou_threshold:
            matched_pairs.append((ai, best_bi, best_iou))
            used_b.add(best_bi)
    if not matched_pairs:
        return 0, None
    total = 0.0
    for ai, bi, _ in matched_pairs:
        ta = str(a_segs[ai].get("text", ""))
        tb = str(b_segs[bi].get("text", ""))
        total += _levenshtein(ta, tb) / max(len(ta), len(tb), 1)
    return len(matched_pairs), total / len(matched_pairs)


def pairwise(a_segs: list[dict[str, Any]], b_segs: list[dict[str, Any]]) -> dict[str, Any]:
    total = max(
        (s["endTime"] for s in a_segs),
        default=0.0,
    )
    total_b = max(
        (s["endTime"] for s in b_segs),
        default=0.0,
    )
    total_duration = max(total, total_b)
    labels_a = _frame_labels(a_segs, total_duration)
    labels_b = _frame_labels(b_segs, total_duration)
    kappa = cohens_kappa(labels_a, labels_b)
    boundary = boundary_agreement(a_segs, b_segs)
    matched_count, per = matched_segment_per(a_segs, b_segs)
    match_rate = matched_count / max(len(a_segs), len(b_segs), 1)
    return {
        "frameKappa": kappa,
        "boundaryF1": boundary["f1"],
        "boundaryPrecisionAtoB": boundary["precisionAtoB"],
        "boundaryPrecisionBtoA": boundary["precisionBtoA"],
        "matchedSegmentCount": matched_count,
        "matchRate": match_rate,
        "phonemeErrorRate": per,
        "framesCompared": len(labels_a),
    }
