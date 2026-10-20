# -*- coding: utf-8 -*-
"""
ガイド (表面の上の折れ線) を、メッシュのエッジの道にする (Maya に依存しない。numpy。scipy があれば速い)。段階 3。

    path = guide_edges(mesh, points, closed)    # EdgePath か None (道が見つからない)
    path.vertices                               # 頂点の番号の列 (閉じていれば最後から最初へもつながる)
    path.edges()                                # [(a, b)] (a < b)

仕組み:
1. ガイドを細かく (エッジの長さの中央値 h の半分の間隔で) 置き直し、WAYPOINT_EDGES x h ごとに中継点を置く。
   中継点にいちばん近い頂点を選ぶ (scipy の cKDTree。無ければ総当たり)
2. 隣り合う中継点の間を、重み付きの最短パス (Dijkstra) でつなぐ:
       エッジの重み = 長さ x (1 + OFF_WEIGHT x (ガイドからの距離 / h)^2)
   ガイドからの距離は、両端の頂点の、その区間のガイドの線までの距離の平均。ガイドに沿うほど安い。
   探すのは区間のガイドから BAND_EDGES x h 以内の頂点だけ (帯)。帯の中で着けなければ帯を広げてやり直す
3. 区間の道をつなぎ、行って戻るとげ (x, y, x) と、同じ頂点を 2 回通る小さな輪を取り除く
   (閉じたガイドは、最後の中継点から最初の中継点へ戻って一周)

面を三角形に分けた対角線は本物のエッジではないので、面の辺 (MeshArrays.adjacency) だけでたどる。
デシメートした不規則な三角形でも、ガイドの近くのエッジを選んでジグザグに沿う (エッジの流れには引きずられない)。
"""
import heapq

import numpy as np

from .geometry import resample

try:
    from scipy.spatial import cKDTree
except Exception:      # scipy が無い・壊れている
    cKDTree = None

__all__ = ["EdgePath", "guide_edges", "vertex_path", "index_path", "WAYPOINT_EDGES", "OFF_WEIGHT", "BAND_EDGES"]

WAYPOINT_EDGES = 6.0     # 中継点の間隔 (エッジの長さの中央値の何倍)
OFF_WEIGHT = 4.0         # ガイドから離れる重み
BAND_EDGES = 4.0         # 探す帯の半径 (中央値の何倍)
BAND_RETRIES = 3         # 着けなければ帯を 2 倍にしてやり直す回数


class EdgePath(object):
    def __init__(self, vertices, closed):
        self.vertices = list(vertices)
        self.closed = bool(closed)

    def edges(self):
        pairs = list(zip(self.vertices[:-1], self.vertices[1:]))
        if self.closed and len(self.vertices) > 2:
            pairs.append((self.vertices[-1], self.vertices[0]))
        return [(a, b) if a < b else (b, a) for a, b in pairs]

    def __len__(self):
        return len(self.vertices)


class _Nearest(object):
    """頂点を近い順に引く (cKDTree か総当たり)。"""

    def __init__(self, points):
        self.points = points
        self.tree = cKDTree(points) if cKDTree is not None and len(points) else None

    def nearest(self, query):
        query = np.asarray(query, dtype=np.float64).reshape(-1, 3)
        if self.tree is not None:
            return self.tree.query(query)[1].astype(np.int64)
        return np.array([int(np.argmin(((self.points - q) ** 2).sum(axis=1))) for q in query])

    def within(self, query, radius):
        """query のどれかから radius 以内の頂点 (番号の配列)。"""
        query = np.asarray(query, dtype=np.float64).reshape(-1, 3)
        if self.tree is not None:
            found = self.tree.query_ball_point(query, radius)
            items = [i for group in found for i in group]
            return np.unique(np.array(items, dtype=np.int64))
        low = query.min(axis=0) - radius
        high = query.max(axis=0) + radius
        inside = np.flatnonzero(((self.points >= low) & (self.points <= high)).all(axis=1))
        if not inside.size:
            return inside
        near = np.zeros(inside.size, dtype=bool)
        for q in query:
            near |= ((self.points[inside] - q) ** 2).sum(axis=1) <= radius * radius
        return inside[near]


def _distance_to_polyline(points, polyline):
    """点 (n, 3) から折れ線 (m, 3) までの距離 (n,)。"""
    if len(polyline) == 1:
        return np.linalg.norm(points - polyline[0], axis=1)
    a, b = polyline[:-1], polyline[1:]
    ab = b - a
    length2 = np.maximum((ab * ab).sum(axis=1), 1e-24)
    ap = points[:, None, :] - a[None, :, :]
    t = np.clip((ap * ab[None, :, :]).sum(axis=2) / length2[None, :], 0.0, 1.0)
    nearest = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    return np.sqrt(((points[:, None, :] - nearest) ** 2).sum(axis=2).min(axis=1))


def _dijkstra(adjacency, distance, allowed, start, goal, h):
    """allowed (bool の配列) の中で start -> goal。distance は頂点ごとのガイドからの距離。頂点の列か None。"""
    indptr, neighbors, lengths = adjacency
    best = {start: 0.0}
    previous = {}
    queue = [(0.0, start)]
    while queue:
        cost, vertex = heapq.heappop(queue)
        if vertex == goal:
            path = [goal]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return path[::-1]
        if cost > best.get(vertex, np.inf):
            continue
        for k in range(indptr[vertex], indptr[vertex + 1]):
            other = int(neighbors[k])
            if not allowed[other]:
                continue
            off = (distance[vertex] + distance[other]) * 0.5 / h
            step = cost + lengths[k] * (1.0 + OFF_WEIGHT * off * off)
            if step < best.get(other, np.inf):
                best[other] = step
                previous[other] = vertex
                heapq.heappush(queue, (step, other))
    return None


def _segment(mesh, nearest, portion, start, goal, h):
    """区間のガイド portion (m, 3) に沿って start -> goal (頂点の列か None)。帯で探し、着けなければ広げる。"""
    if start == goal:
        return [start]
    adjacency = mesh.adjacency()
    radius = BAND_EDGES * h
    for _ in range(BAND_RETRIES + 1):
        band = nearest.within(portion, radius)
        band = np.union1d(band, [start, goal])
        allowed = np.zeros(len(mesh.points), dtype=bool)
        allowed[band] = True
        distance = np.zeros(len(mesh.points))
        distance[band] = _distance_to_polyline(mesh.points[band], portion)
        path = _dijkstra(adjacency, distance, allowed, start, goal, h)
        if path is not None:
            return path
        radius *= 2.0
    return None


def _simplify(vertices, closed):
    """行って戻るとげ (x, y, x) と、同じ頂点を 2 回通る輪を取り除く。"""
    out = []
    position = {}
    for vertex in vertices:
        if vertex in position:                    # 前に通った頂点に戻った: その間の輪 (とげも) を捨てる
            keep = position[vertex] + 1
            for dropped in out[keep:]:
                del position[dropped]
            del out[keep:]
            continue
        position[vertex] = len(out)
        out.append(vertex)
    if closed:
        # 一周のつなぎ目のとげ: 最後と最初の近くで行って戻っていれば、その分を落とす
        while len(out) > 3 and out[-1] == out[1]:
            out = out[1:-1]
    return out


def index_path(mesh, vertices, closed):
    """頂点の番号の列が、どれも頂点の範囲にあり、隣どうしが本物のエッジでつながっていれば、その EdgePath。
    そうでなければ None (メッシュのトポロジーが変わったとき。境界のガイドの vertices を確かめる)。"""
    vertices = [int(v) for v in vertices or ()]
    if len(vertices) < 2 or min(vertices) < 0 or max(vertices) >= len(mesh.points):
        return None
    path = EdgePath(vertices, closed)
    pairs = np.asarray(path.edges(), dtype=np.int64)
    edges = mesh.edges()
    size = np.int64(len(mesh.points))
    if not len(edges) or not np.all(np.isin(pairs[:, 0] * size + pairs[:, 1], edges[:, 0] * size + edges[:, 1])):
        return None
    return path


def vertex_path(mesh, points, closed):
    """点がどれも頂点の上にあり、隣どうしが本物のエッジでつながっているなら、その頂点の列の EdgePath。そうでなければ
    None。ペイントの囲む線 (core.region.region_loops。塗った面の境目のエッジの上) を、最短パスで求め直さずにそのまま
    シームにする (塗っている間に見えた線と、確定したシームを同じにするため)。"""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(points) < 2 or not len(mesh.points):
        return None
    nearest = getattr(mesh, "_seam_nearest", None)
    if nearest is None:
        nearest = mesh._seam_nearest = _Nearest(mesh.points)
    vertices = nearest.nearest(points)
    tolerance = max(mesh.size(), 1e-12) * 1e-6
    if np.any(np.linalg.norm(mesh.points[vertices] - points, axis=1) > tolerance):
        return None
    path = EdgePath(vertices.tolist(), closed)
    pairs = np.asarray(path.edges(), dtype=np.int64)
    edges = mesh.edges()
    size = np.int64(len(mesh.points))
    if not len(edges) or not np.all(np.isin(pairs[:, 0] * size + pairs[:, 1], edges[:, 0] * size + edges[:, 1])):
        return None
    return path


def guide_edges(mesh, points, closed, h=None):
    """ガイドの点 (n, 3。メッシュのオブジェクト空間) をエッジの道にする。EdgePath か None。"""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 2 or not len(mesh.points):
        return None
    h = h or mesh.medianEdge() or mesh.size() * 0.01
    fine = resample(points, h * 0.5, closed=closed)
    if len(fine) < 2:
        return None
    step = max(int(round(WAYPOINT_EDGES * 2)), 1)
    marks = list(range(0, len(fine), step))
    if not closed and marks[-1] != len(fine) - 1:
        marks.append(len(fine) - 1)
    if closed and len(marks) < 3:                 # 小さい輪: 3 つ以上に分ける
        marks = sorted(set(int(round(i)) for i in np.linspace(0, len(fine), 4)[:3]))
    nearest = getattr(mesh, "_seam_nearest", None)
    if nearest is None:                           # 頂点の木はメッシュごとに 1 回 (MeshArrays は形が変わると作り直される)
        nearest = mesh._seam_nearest = _Nearest(mesh.points)
    snapped = nearest.nearest(fine[marks]).tolist()
    sections = list(zip(marks[:-1], marks[1:]))
    if closed:
        sections.append((marks[-1], len(fine)))   # 最後の中継点から最初へ (最初の点まで回り込む)
    vertices = []
    for index, (i0, i1) in enumerate(sections):
        portion = fine[i0:i1 + 1] if i1 < len(fine) else np.vstack([fine[i0:], fine[:1]])
        start = snapped[index]
        goal = snapped[(index + 1) % len(snapped)] if closed else snapped[index + 1]
        part = _segment(mesh, nearest, portion, start, goal, h)
        if part is None:
            return None
        vertices.extend(part if not vertices else part[1:])
    if closed and len(vertices) > 1 and vertices[-1] == vertices[0]:
        vertices.pop()
    vertices = _simplify(vertices, closed)
    if len(vertices) < (3 if closed else 2):
        return None
    return EdgePath(vertices, closed)
