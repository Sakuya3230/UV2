# -*- coding: utf-8 -*-
"""
置いた点を通るなめらかな曲線 (Maya に依存しない。numpy)。カーブのガイド (4 カーブ) に使う。

    points = catmull_rom(anchors, closed=False, spacing=0.1)   # (n, 3)。anchors をすべて通る
    i = nearest_segment(anchors, point, closed)                 # point にいちばん近い区間 (点を足す所)
    piece = curve_segment(anchors, i, closed, spacing)          # 区間 i だけの曲線 (つないだ線の曲線の区間)
    points = path_points(anchors, smooth, closed)               # 区間ごとに曲線か直線かを混ぜた線 (プレビュー)

centripetal Catmull-Rom (alpha = 0.5): 点と点の間の「時間」を距離の平方根にする。点の間隔がばらついても、
点の近くで輪を作ったり行き過ぎたりしにくい (uniform では点が近いと尖り、chordal では緩みすぎる)。
区間ごとに、その区間の両隣の点まで使う。開いた線の端は、端の点の外側に鏡に写した点を足して使う。
spacing を渡すと、区間をおよそその間隔で分ける (無ければ区間ごとに samples 個)。
閉じた線は最初の点を最後に繰り返さない (ガイドの点の列と同じ決まり)。
"""
import numpy as np

__all__ = ["catmull_rom", "curve_segment", "path_points", "nearest_segment", "ALPHA"]

ALPHA = 0.5
_EPS = 1e-12


def _knot(a, b, t):
    return t + max(float(np.linalg.norm(b - a)) ** ALPHA, _EPS)


def _segment(p0, p1, p2, p3, count):
    """p1 -> p2 の区間を count 個に分けた点 (p1 を含み p2 は含まない)。Barry-Goldman のピラミッド。"""
    t0 = 0.0
    t1 = _knot(p0, p1, t0)
    t2 = _knot(p1, p2, t1)
    t3 = _knot(p2, p3, t2)
    t = np.linspace(t1, t2, count, endpoint=False)[:, None]
    a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
    a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
    a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
    b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
    b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
    return (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2


def catmull_rom(anchors, closed=False, spacing=None, samples=8):
    """anchors (n, 3) をすべて通る曲線の点 (m, 3)。"""
    parts, points, closed = _parts(anchors, closed, spacing, samples)
    if not parts:
        return points.copy()
    if not closed:
        parts.append(points[-1:])
    return np.vstack(parts)


def _neighbors(points, index, closed):
    """区間 index (points[index] -> 次の点) の Catmull-Rom の 4 点。開いた線の端は鏡に写した点で延ばす。"""
    count = len(points)
    p1, p2 = points[index], points[(index + 1) % count]
    if closed:
        return points[(index - 1) % count], p1, p2, points[(index + 2) % count]
    p0 = points[index - 1] if index > 0 else 2 * p1 - p2
    p3 = points[index + 2] if index + 2 < count else 2 * p2 - p1
    return p0, p1, p2, p3


def curve_segment(anchors, index, closed=False, spacing=None, samples=8):
    """区間 index だけの曲線の点 (両端の置いた点を含む)。隣の点まで使うので、つないだ線の中の曲線の区間にも使える
    (直線の区間と混ざっていても、置いた点の並び全体で向きを決める)。"""
    points = np.asarray(anchors, dtype=np.float64).reshape(-1, 3)
    closed = closed and len(points) >= 3
    p0, p1, p2, p3 = _neighbors(points, index, closed)
    if np.linalg.norm(p2 - p1) <= _EPS:
        return np.vstack([p1, p2])
    pieces = max(2, int(np.ceil(np.linalg.norm(p2 - p1) / spacing))) if spacing else max(2, int(samples))
    return np.vstack([_segment(p0, p1, p2, p3, pieces), p2[None, :]])


def path_points(anchors, smooth, closed=False, samples=12):
    """置いた点と区間ごとの曲線か直線か (smooth) からの、描くための点 (表面には寄せない。プレビュー用)。"""
    points = np.asarray(anchors, dtype=np.float64).reshape(-1, 3)
    parts = []
    for i, curved in enumerate(smooth):
        piece = curve_segment(points, i, closed, samples=samples) if curved else             np.vstack([points[i], points[(i + 1) % len(points)]])
        parts.append(piece if not parts else piece[1:])
    joined = np.vstack(parts) if parts else points.copy()
    return joined[:-1] if closed and len(joined) > 2 else joined


def nearest_segment(anchors, point, closed=False, samples=16):
    """曲線の上で point にいちばん近い区間の番号 i (anchors[i] と anchors[i + 1] の間。閉じた線の最後の区間は
    最後の点と最初の点の間)。点を足すときに、どこへ差し込むかを決める。"""
    raw = np.asarray(anchors, dtype=np.float64).reshape(-1, 3)
    if len(raw) < 2:
        return 0
    point = np.asarray(point, dtype=np.float64)
    count = len(raw) if closed and len(raw) >= 3 else len(raw) - 1
    best, best_index = np.inf, 0
    for i in range(count):
        pair = np.vstack([raw[i], raw[(i + 1) % len(raw)]])
        neighbors = np.vstack([raw[i - 1] if (i > 0 or closed) else 2 * raw[0] - raw[1],
                               pair,
                               raw[(i + 2) % len(raw)] if (i + 2 < len(raw) or closed) else 2 * pair[1] - pair[0]])
        if np.linalg.norm(pair[1] - pair[0]) <= _EPS:
            continue
        piece = np.vstack([_segment(neighbors[0], neighbors[1], neighbors[2], neighbors[3], samples), pair[1:]])
        distance = float(np.linalg.norm(piece - point, axis=1).min())
        if distance < best:
            best, best_index = distance, i
    return best_index


def _parts(anchors, closed, spacing, samples):
    """区間ごとの点の配列のリスト、重なりを除いた点、閉じているか (点が 3 つ未満なら開いた線)。"""
    points = np.asarray(anchors, dtype=np.float64).reshape(-1, 3)
    # 同じ所に続けて置いた点は 1 つにする (区間の長さ 0 で割らないように)
    if len(points) > 1:
        keep = np.concatenate([[True], np.linalg.norm(np.diff(points, axis=0), axis=1) > _EPS])
        points = points[keep]
    if closed and len(points) > 2 and np.linalg.norm(points[-1] - points[0]) <= _EPS:
        points = points[:-1]
    count = len(points)
    if count < 2:
        return [], points, False
    if closed and count >= 3:
        extended = np.vstack([points[-1:], points, points[:2]])
        segments = count
    else:
        closed = False
        extended = np.vstack([2 * points[0] - points[1], points, 2 * points[-1] - points[-2]])
        segments = count - 1
    parts = []
    for i in range(segments):
        p0, p1, p2, p3 = extended[i], extended[i + 1], extended[i + 2], extended[i + 3]
        if spacing:
            pieces = max(2, int(np.ceil(np.linalg.norm(p2 - p1) / spacing)))
        else:
            pieces = max(2, int(samples))
        parts.append(_segment(p0, p1, p2, p3, pieces))
    return parts, points, closed
