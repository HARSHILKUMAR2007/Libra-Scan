"""Geometry and bounding box clustering utilities for OCR lines."""

from app.schemas.book import FieldBox
from app.schemas.ocr import OcrLine


def cluster_neighbor_boxes(lines: list[OcrLine], side: str) -> list[FieldBox]:
    """Group lines that are vertical neighbors with horizontal overlap into tight boxes."""
    if not lines:
        return []
    sorted_lines = sorted(lines, key=lambda l: l.bbox[1])
    avg_h = sum(l.bbox[3] - l.bbox[1] for l in sorted_lines) / len(sorted_lines)
    threshold = 1.5 * max(avg_h, 0.02)

    clusters: list[list[OcrLine]] = []
    current_cluster = [sorted_lines[0]]
    for line in sorted_lines[1:]:
        c_x1 = min(l.bbox[0] for l in current_cluster)
        c_x2 = max(l.bbox[2] for l in current_cluster)
        c_y2 = max(l.bbox[3] for l in current_cluster)
        vert_gap = max(0.0, line.bbox[1] - c_y2)
        has_overlap = max(c_x1, line.bbox[0]) < min(c_x2, line.bbox[2])
        if vert_gap <= threshold and has_overlap:
            current_cluster.append(line)
        else:
            clusters.append(current_cluster)
            current_cluster = [line]
    clusters.append(current_cluster)

    return [
        FieldBox(
            image=side,
            bbox=(
                round(min(l.bbox[0] for l in cl), 4),
                round(min(l.bbox[1] for l in cl), 4),
                round(max(l.bbox[2] for l in cl), 4),
                round(max(l.bbox[3] for l in cl), 4),
            ),
        )
        for cl in clusters
    ]


def merge_boxes_for_field(valid_line_ids: list[int], lines_by_id: dict[int, OcrLine]) -> list[FieldBox]:
    """Merge lines per image, keeping non-neighbor lines as separate boxes."""
    f_lines = [lines_by_id[i] for i in valid_line_ids if i in lines_by_id and lines_by_id[i].image == "front"]
    b_lines = [lines_by_id[i] for i in valid_line_ids if i in lines_by_id and lines_by_id[i].image == "back"]
    return cluster_neighbor_boxes(f_lines, "front") + cluster_neighbor_boxes(b_lines, "back")
