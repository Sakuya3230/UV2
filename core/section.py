# -*- coding: utf-8 -*-
"""
輪切りのガイド: 平面とメッシュの断面の線 (Maya に依存しない。numpy)。

    curves = plane_section(mesh, plane)              # 断面の線のリスト (SectionCurve)
    curves = field_section(mesh, values)             # 頂点ごとの値が 0 になる所の線 (ペイントの囲む線にも使う)
    chosen = curves_in_stroke(curves, project, start, end)   # 描いた線の範囲に収まる線だけ

UVPathCut の輪切りはエッジ (境目) を選ぶが、ガイドはエッジを使わないので、本当の断面の線を求める:
1. 全頂点の、平面からの符号付きの距離 d (0 は表側に数える)
2. 頂点の表裏が分かれる三角形は、ちょうど 2 本の辺で平面と交わる。その 2 つの交点を結ぶ線分が断面の一部
3. 交点は辺ごとに 1 つ (隣の三角形と共有する) なので、辺を節にして線分をたどると、閉じた輪
   (筒を切った断面) か、開いた線 (メッシュの縁・穴で切れたもの) になる
2 は全三角形の配列の計算、3 は平面と交わる三角形の数だけの Python のループ (全体のごく一部)。

描いた線の範囲: 平面は視線を含むので、断面の点は画面ではすべて描いた線の延長の上に写る。線の始点を 0・
終点を 1 とした位置が範囲に収まる (ほぼ全部の点が -MARGIN〜1 + MARGIN) 線だけを残す。腕を横切って
描けば、平面は胴体も切るが、胴体の断面は線の外まで伸びるので外れる。
"""
import numpy as np

__all__ = ["SectionCurve", "plane_section", "field_section", "curves_in_stroke", "MARGIN", "INSIDE"]

MARGIN = 0.02      # 描いた線の範囲の余裕 (線の長さに対する割合)
INSIDE = 0.98      # 範囲に入る点がこの割合以上の線を残す


class SectionCurve(object):
    """断面の線。points は (n, 3)、closed なら最後の点から最初の点へもつながる。"""

    def __init__(self, points, closed):
        self.points = np.asarray(points, dtype=np.float64)
        self.closed = bool(closed)

    def __len__(self):
        return len(self.points)


def plane_section(mesh, plane):
    """mesh (MeshArrays) を平面 (点, 単位の法線) で切った断面の線のリスト。"""
    origin, normal = plane
    distance = (mesh.points - np.asarray(origin, dtype=np.float64)) @ np.asarray(normal, dtype=np.float64)
    return field_section(mesh, distance)


def field_section(mesh, distance):
    """頂点ごとの値 distance が 0 になる所の線 (等高線) のリスト。平面の断面は「平面からの距離」の 0 の線、
    ペイントの囲む線は「塗った量 - 0.5」の 0 の線 (core.region)。"""
    points, triangles = mesh.points, mesh.triangles
    distance = np.asarray(distance, dtype=np.float64)
    if not len(triangles):
        return []
    front = distance >= 0.0
    side = front[triangles]
    crossing = np.flatnonzero(side.any(axis=1) & ~side.all(axis=1))
    if not crossing.size:
        return []
    tri = triangles[crossing]
    side = side[crossing]
    edge_a = tri
    edge_b = tri[:, [1, 2, 0]]
    differ = side != side[:, [1, 2, 0]]                       # 3 本の辺のうち、ちょうど 2 本が交わる
    pick = np.argsort(~differ, axis=1, kind="stable")[:, :2]  # 交わる 2 本の辺の位置
    a = np.take_along_axis(edge_a, pick, axis=1)
    b = np.take_along_axis(edge_b, pick, axis=1)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    count = len(points)
    keys, segment_nodes = np.unique(lo * count + hi, return_inverse=True)
    segment_nodes = segment_nodes.reshape(-1, 2)
    node_lo, node_hi = keys // count, keys % count
    d_lo, d_hi = distance[node_lo], distance[node_hi]
    t = d_lo / (d_lo - d_hi)                                   # 符号が違うので分母は 0 にならない
    node_points = points[node_lo] + t[:, None] * (points[node_hi] - points[node_lo])
    return [SectionCurve(node_points[nodes], closed) for nodes, closed in _chain(segment_nodes, len(keys))]


def _chain(segments, node_count):
    """線分 (節, 節) をたどって (節のリスト, 閉じているか) のリストにする。
    節 (メッシュの辺) は 2 つの三角形に共有されるので、ふつうは 2 本の線分につながる (縁なら 1 本)。"""
    links = [[] for _ in range(node_count)]
    for index, (a, b) in enumerate(segments.tolist()):
        links[a].append((b, index))
        links[b].append((a, index))
    used = [False] * len(segments)
    result = []
    # 端 (つながる線分が 1 本の節) から始める線を先に (開いた線)、残りは輪
    order = [n for n in range(node_count) if len(links[n]) == 1] + list(range(node_count))
    for start in order:
        if not any(not used[i] for _, i in links[start]):
            continue
        nodes = [start]
        current = start
        closed = False
        while True:
            step = next(((other, i) for other, i in links[current] if not used[i]), None)
            if step is None:
                break
            other, i = step
            used[i] = True
            if other == start:
                closed = True
                break
            nodes.append(other)
            current = other
        if len(nodes) >= 2:
            result.append((nodes, closed))
    return result


def curves_in_stroke(curves, project, start, end, margin=MARGIN, inside=INSIDE):
    """描いた線 (画面の start -> end) の範囲に収まる断面の線。project は (n, 3) -> (n, 2) の画面の位置。"""
    start = np.asarray(start, dtype=np.float64)
    direction = np.asarray(end, dtype=np.float64) - start
    length2 = float(direction @ direction)
    if length2 <= 0.0:
        return []
    chosen = []
    for curve in curves:
        screen = np.asarray(project(curve.points), dtype=np.float64)
        along = (screen - start) @ direction / length2
        within = (along >= -margin) & (along <= 1.0 + margin)
        if within.mean() >= inside:
            chosen.append(curve)
    return chosen
