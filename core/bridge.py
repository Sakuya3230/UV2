# -*- coding: utf-8 -*-
"""
つなぎ線 (BRIDGE): 2 本のガイドの間を、エッジの最短パスでつなぐ線の計算 (Maya に依存しない。numpy。scipy が
あれば速い)。仕様は docs/04_bridge_spec.md。

    t = path_fraction(mesh, host_vertices, host_closed, vertex)        # 乗っているガイドのシームの上の位置 (0〜1)
    vertex = vertex_at_fraction(mesh, host_vertices, host_closed, t)  # 位置 -> シームの頂点
    vertex = nearest_on_path(mesh, host_vertices, point)              # 点にいちばん近いシームの頂点
    path = shortest_vertex_path(mesh, a, b)                           # 頂点 a -> b のエッジの最短パス (頂点の列)
    vertices = bridge_vertices(mesh, stops)                           # 端点 -> 中継点 -> 端点 をつないだ頂点の列

端点は、乗っているガイドの**シームの頂点の上**に置く (線の上に置くと、乗っている側のシームと頂点を共有しない
ことがあり、カットが途中で途切れる)。乗っている点の持ち方と付いて行き方は core.path_model.Attach と
scene.edit._resolve_attach (線の上の目印で追う。割合で追うと輪を作り直すたびに一周の数え始めが変わって大きく回った)。
最短パスは面の辺だけ (MeshArrays.adjacency) を長さの重みでたどる (core.edge_path と同じ考え方。帯は使わない)。
"""
import heapq

import numpy as np

try:
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
except Exception:      # scipy が無い・壊れている
    csr_matrix = None

__all__ = ["path_fraction", "vertex_at_fraction", "nearest_on_path", "nearest_on_line", "shortest_vertex_path",
           "bridge_vertices"]


def _cumulative(mesh, vertices, closed):
    """シームの頂点の列の、頂点ごとの長さ (始点から) と全長。閉じた線は最後の頂点から始点へ戻る分も全長に入る。"""
    points = mesh.points[np.asarray(vertices, dtype=np.int64)]
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    lengths = np.concatenate([[0.0], np.cumsum(steps)])
    total = float(lengths[-1])
    if closed and len(points) > 2:
        total += float(np.linalg.norm(points[0] - points[-1]))
    return lengths, total


def path_fraction(mesh, vertices, closed, vertex):
    """シームの頂点の列 vertices の上の、頂点 vertex の位置 (長さの割合 0〜1)。列に無ければ None。"""
    vertices = list(vertices)
    if vertex not in vertices:
        return None
    lengths, total = _cumulative(mesh, vertices, closed)
    return float(lengths[vertices.index(vertex)] / total) if total > 0 else 0.0


def vertex_at_fraction(mesh, vertices, closed, fraction):
    """シームの上の位置 fraction (0〜1) にいちばん近い、シームの頂点。"""
    vertices = list(vertices)
    lengths, total = _cumulative(mesh, vertices, closed)
    if not total:
        return int(vertices[0])
    if closed:
        target = (float(fraction) % 1.0) * total
        gap = np.abs(lengths - target)
        gap = np.minimum(gap, total - gap)                    # 一周の向こう側からも近い
    else:
        target = min(max(float(fraction), 0.0), 1.0) * total
        gap = np.abs(lengths - target)
    return int(vertices[int(np.argmin(gap))])


def nearest_on_line(points, closed, point):
    """折れ線 points (n, 3) の上の、点 point にいちばん近い点。"""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    point = np.asarray(point, dtype=np.float64)
    if len(points) == 1:
        return points[0]
    if closed and len(points) > 2:
        points = np.vstack([points, points[:1]])
    a, b = points[:-1], points[1:]
    ab = b - a
    t = np.clip(((point - a) * ab).sum(axis=1) / np.maximum((ab * ab).sum(axis=1), 1e-24), 0.0, 1.0)
    near = a + ab * t[:, None]
    return near[int(np.argmin(np.linalg.norm(near - point, axis=1)))]


def nearest_on_path(mesh, vertices, point):
    """点 point (オブジェクト空間) にいちばん近い、シームの頂点。"""
    vertices = np.asarray(vertices, dtype=np.int64)
    gap = np.linalg.norm(mesh.points[vertices] - np.asarray(point, dtype=np.float64), axis=1)
    return int(vertices[int(np.argmin(gap))])


def _graph(mesh, weights=None):
    """scipy の疎行列のグラフ (重みは長さか weights)。メッシュに覚えておく (weights は同じ配列なら使い回す)。"""
    if csr_matrix is None:
        return None
    indptr, neighbors, lengths = mesh.adjacency()
    count = len(mesh.points)
    if weights is None:
        graph = getattr(mesh, "_bridge_graph", None)
        if graph is None:
            graph = mesh._bridge_graph = csr_matrix((lengths, neighbors, indptr), shape=(count, count))
        return graph
    cached = getattr(mesh, "_bridge_weighted", None)
    if cached is not None and cached[0] is weights:
        return cached[1]
    graph = csr_matrix((np.asarray(weights, dtype=np.float64), neighbors, indptr), shape=(count, count))
    mesh._bridge_weighted = (weights, graph)
    return graph


def shortest_vertex_path(mesh, start, goal, weights=None):
    """頂点 start -> goal のエッジの最短パスの頂点の列。重みは長さ、weights を渡すとその重み (MeshArrays.adjacency()
    の隣ごと。core.valley.valley_weights など)。つながっていなければ None。"""
    start, goal = int(start), int(goal)
    if start == goal:
        return [start]
    graph = _graph(mesh, weights)
    if graph is not None:
        distance, previous = dijkstra(graph, directed=False, indices=start, return_predecessors=True)
        if not np.isfinite(distance[goal]):
            return None
        path = [goal]
        while path[-1] != start:
            path.append(int(previous[path[-1]]))
        return path[::-1]
    indptr, neighbors, lengths = mesh.adjacency()
    if weights is not None:
        lengths = weights
    best = {start: 0.0}
    previous = {}
    queue = [(0.0, start)]
    while queue:
        d, vertex = heapq.heappop(queue)
        if vertex == goal:
            break
        if d > best.get(vertex, np.inf):
            continue
        for k in range(indptr[vertex], indptr[vertex + 1]):
            other, step = int(neighbors[k]), d + float(lengths[k])
            if step < best.get(other, np.inf):
                best[other] = step
                previous[other] = vertex
                heapq.heappush(queue, (step, other))
    if goal not in best:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(previous[path[-1]])
    return path[::-1]


def bridge_vertices(mesh, stops, weights=None):
    """端点 -> 中継点 -> … -> 端点 (頂点の番号の列 stops) を、区間ごとのエッジの最短パスでつないだ頂点の列
    (重みは shortest_vertex_path と同じ)。つながらない区間があれば None。続けて同じ頂点の中継点は 1 つにする。"""
    stops = [int(s) for s in stops]
    stops = [s for k, s in enumerate(stops) if k == 0 or s != stops[k - 1]]
    if len(stops) < 2:
        return list(stops) if stops else None
    result = [stops[0]]
    for a, b in zip(stops[:-1], stops[1:]):
        piece = shortest_vertex_path(mesh, a, b, weights)
        if piece is None:
            return None
        result.extend(piece[1:])
    return result
