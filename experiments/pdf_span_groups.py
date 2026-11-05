"""Conservative grouping of PDF figure-label span proposals.

Outputs are supplemental *group suggestions*. Input instances are preserved,
never rewritten or deleted. Only near-vertical, left-aligned fragments in the
same detected figure are considered. Generic geometry cannot reliably resolve
every rotated/multicolumn label; keep ambiguous cases for human review.
"""
from __future__ import annotations


def _shared_figure_ids(item):
    """Stable figure boxes rather than runtime order or detector indices."""
    return {
        tuple(region.get("bbox_pdf_points", ()))
        for region in item.get("nearby_regions", [])
        if region.get("class_name") == "figure"
        and region.get("relation") == "OVERLAPS_REGION"
        and len(region.get("bbox_pdf_points", ())) == 4
    }


def _compatible_above(a, b):
    """Does a appear to be the first line of the same label as b?"""
    ax0, ay0, ax1, ay1 = a["bbox_pdf_points"]
    bx0, by0, bx1, by1 = b["bbox_pdf_points"]
    ah = ay1 - ay0
    bh = by1 - by0
    if ah <= 0 or bh <= 0 or ay0 >= by0:
        return False
    if not _shared_figure_ids(a).intersection(_shared_figure_ids(b)):
        return False
    if abs(a["size_pt"] - b["size_pt"]) > 1.5:
        return False
    if abs(ax0 - bx0) > max(4, min(ah, bh) * 0.5):
        return False
    if by0 - ay1 > 4 or by0 - ay0 < min(ah, bh) * 0.4:
        return False
    if min(ax1, bx1) - max(ax0, bx0) < 0.5 * min(ax1 - ax0, bx1 - bx0):
        return False
    return True


def propose_span_groups(instances):
    """Return independent, non-overlapping review groups, never edit spans.

    Conservative: one incoming/outgoing partner per span, with a unique best
    vertical neighbor only. Ambiguous pairings are left ungrouped.
    """
    neighbors = {}
    for i, a in enumerate(instances):
        scored = []
        for j, b in enumerate(instances):
            if i != j and _compatible_above(a, b):
                dist = b["bbox_pdf_points"][1] - a["bbox_pdf_points"][1]
                scored.append((round(dist, 3), j))
        scored.sort()
        if len(scored) == 1 or (len(scored) >= 2 and scored[1][0] - scored[0][0] > 3):
            if scored:
                neighbors[i] = scored[0][1]
    incoming = {}
    for first, second in neighbors.items():
        incoming.setdefault(second, []).append(first)
    links = {
        first: second for first, second in neighbors.items()
        if len(incoming[second]) == 1
    }
    groups = []
    visited = set()
    for i in range(len(instances)):
        if i in visited or i in incoming:
            continue
        chain = [i]
        while chain[-1] in links and links[chain[-1]] not in chain:
            chain.append(links[chain[-1]])
        if len(chain) < 2:
            continue
        for index in chain:
            visited.add(index)
        parts = [instances[index] for index in chain]
        boxes = [p["bbox_pdf_points"] for p in parts]
        groups.append({
            "proposed_text": " ".join(p["text"] for p in parts),
            "source_spans": [
                {"text": p["text"], "bbox_pdf_points": p["bbox_pdf_points"]}
                for p in parts
            ],
            "bbox_pdf_points": [
                round(min(b[0] for b in boxes), 1),
                round(min(b[1] for b in boxes), 1),
                round(max(b[2] for b in boxes), 1),
                round(max(b[3] for b in boxes), 1),
            ],
            "status": "REVIEW_REQUIRED",
            "approved": False,
        })
    return groups
