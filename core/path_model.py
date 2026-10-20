# -*- coding: utf-8 -*-
"""
ガイドの統一した持ち方 (Maya に依存しない。numpy)。仕様は docs/05_unified_spec.md。段階 1。

どのガイドも 点 (Node) + 区間の作り方 (Segment) + 点の付き方 (Attach) でできている。

    path = GuidePath(nodes, segments, closed, origin, source)
    path.line()                          # 区間の形をつないだ線 (オブジェクト空間の点の列)
    path.toDict() / GuidePath.fromDict() # 保存の形 (version 2 の 1 本分)
    paths = paths_from_v1(guide, mesh, spacing)   # 前の版の Guide を新しい持ち方に (ペイントは囲む線ごとに 1 本)
    rebuild_segment(path, i, mesh, snap, spacing, weights=None)   # 区間 i の形を作り方から作り直す

区間の作り方:
    CURVE     前後の点も使う centripetal Catmull-Rom を表面に寄せる (今のカーブ)
    STRAIGHT  3D の直線を表面に寄せる (今のライン)
    SHORTEST  エッジの最短パス (今のつなぎ線)。両端の点は頂点
    VALLEY    くぼみを通るエッジの道 (core.valley)。両端の点は頂点
    FIXED     作ったときの形のまま (フリーハンドの手描き・断面・ペイントや境界のエッジ)
区間は形 (shape。両端の点を含む点の列) を覚えておき、作り直すまで使い回す (前の版のラインの区間と同じ。描いたときの
形を残す)。エッジの上の区間 (最短・谷・エッジの固定) は頂点の列 (vertices) も持つ。

点の付き方: 自由 (attach = None) か、ガイドに乗る (Attach: 乗っているガイドの番号・何本目の線か・シームの上の割合・
線の上の目印の点・区間の上の位置 place)。最短・谷の区間の端の点と、エッジの上の点は頂点 (vertex) を持つ。

元の情報 (source): リングは plane / axis、ペイントは faces と group (同じ塗りから作った線の組)。pristine は、作ったまま
点を編集していないか (リングのホイールで断面を求め直すかに使う)。origin は作った道具 (表示の色・戻る操作)。
"""
import numpy as np

from .anchored import split_segments
from .curve import curve_segment
from .edge_path import vertex_path
from .geometry import polyline_length

__all__ = ["Node", "Attach", "Segment", "GuidePath", "paths_from_v1", "rebuild_segment", "simplify_indices",
           "even_indices", "CURVE", "STRAIGHT", "SHORTEST", "VALLEY", "FIXED", "MODES", "EDGE_MODES",
           "ORIGIN_RING", "ORIGIN_FREEHAND", "ORIGIN_LINE", "ORIGIN_CURVE", "ORIGIN_PAINT", "ORIGIN_BRIDGE",
           "ORIGIN_EDGE", "ORIGIN_CIRCLE", "RING_NODES", "SIMPLIFY_SPACINGS", "PathEntry", "convert_v1_set", "entries_to_json",
           "entries_from_json", "line_length", "path_seam", "segment_seam", "node_vertex"]

CURVE, STRAIGHT, SHORTEST, VALLEY, FIXED = "curve", "straight", "shortest", "valley", "fixed"
MODES = (CURVE, STRAIGHT, SHORTEST, VALLEY, FIXED)
EDGE_MODES = (SHORTEST, VALLEY)
ORIGIN_RING, ORIGIN_FREEHAND, ORIGIN_LINE, ORIGIN_CURVE = "ring", "freehand", "line", "curve"
ORIGIN_PAINT, ORIGIN_BRIDGE, ORIGIN_EDGE = "paint", "bridge", "edge"
ORIGIN_CIRCLE = "circle"           # 1 リングの Ctrl+ドラッグ: 画面の円をカメラの向きに落とした閉じた曲線
RING_NODES = 4             # リングの点の数 (断面の輪の上の等間隔)
SIMPLIFY_SPACINGS = 2.0    # ペイント・境界の点の間引きの許容値 (点の間隔の何倍)
MIN_CLOSED_NODES = 4       # 閉じた線の点の最少 (足りなければ等間隔で足す)


class Attach(object):
    """ガイドに乗る点: 乗っているガイドの番号 host、何本目の線か line、シームの上の割合 fraction、線の上の目印 point、
    目印の区間の上の位置 place ((区間の番号, 区間の長さの割合, 乗っているガイドの点の数) か None。segment_place)。"""

    def __init__(self, host, line=0, fraction=0.0, point=None, place=None):
        self.host = int(host)
        self.line = int(line or 0)
        self.fraction = float(fraction or 0.0)
        self.point = None if point is None else tuple(float(c) for c in point)
        self.place = None if place is None else (int(place[0]), float(place[1]), int(place[2]))

    def toList(self):
        data = [self.host, self.line, self.fraction, None if self.point is None else list(self.point)]
        if self.place is not None:
            data.append(list(self.place))
        return data

    @classmethod
    def fromList(cls, data):
        return None if data is None else cls(*data[:5])


class Node(object):
    """点: 位置 position (オブジェクト空間)、頂点 vertex (エッジの上の点なら番号。無ければ None)、付き方 attach。"""

    def __init__(self, position, vertex=None, attach=None):
        self.position = tuple(float(c) for c in position)
        self.vertex = None if vertex is None else int(vertex)
        self.attach = attach

    def toDict(self):
        data = {"p": list(self.position)}
        if self.vertex is not None:
            data["v"] = self.vertex
        if self.attach is not None:
            data["attach"] = self.attach.toList()
        return data

    @classmethod
    def fromDict(cls, data):
        return cls(data["p"], data.get("v"), Attach.fromList(data.get("attach")))


class Segment(object):
    """区間: 作り方 mode、形 shape (両端の点を含む点の列。None なら作り直しが要る)、頂点の列 vertices (エッジの上なら)。"""

    def __init__(self, mode, shape=None, vertices=None):
        if mode not in MODES:
            raise ValueError("区間の作り方が違います: {}".format(mode))
        self.mode = mode
        self.shape = None if shape is None else np.asarray(shape, dtype=np.float64).reshape(-1, 3)
        self.vertices = None if vertices is None else [int(v) for v in vertices]

    def toDict(self):
        data = {"mode": self.mode}
        if self.shape is not None:
            data["shape"] = self.shape.tolist()
        if self.vertices is not None:
            data["vertices"] = list(self.vertices)
        return data

    @classmethod
    def fromDict(cls, data):
        return cls(data["mode"], data.get("shape"), data.get("vertices"))


class GuidePath(object):
    """1 本のガイドの線: 点 nodes、区間 segments (開いた線は点の数 - 1、閉じた線は点の数)、閉じているか、作った道具
    origin、元の情報 source (dict)、作ったまま編集していないか pristine。"""

    def __init__(self, nodes, segments, closed=False, origin=ORIGIN_CURVE, source=None, pristine=True):
        self.nodes = list(nodes)
        self.segments = list(segments)
        self.closed = bool(closed)
        self.origin = origin
        self.source = dict(source or {})
        self.pristine = bool(pristine)
        if len(self.segments) != self.segmentCount():
            raise ValueError("区間の数が点の数と合いません: 点 {} / 区間 {} / 閉じている {}".format(
                len(self.nodes), len(self.segments), self.closed))

    def segmentCount(self):
        count = len(self.nodes)
        return count if self.closed else max(count - 1, 0)

    def segmentEnds(self, index):
        """区間 index の両端の点の番号。"""
        return index, (index + 1) % len(self.nodes)

    def anchors(self):
        return np.asarray([node.position for node in self.nodes], dtype=np.float64).reshape(-1, 3)

    def line(self):
        """区間の形をつないだ線 (n, 3)。つなぎ目は 1 回だけ。閉じた線は最後の点 (= 最初の点) を入れない。
        形の無い区間は、両端の点を結んだ線にする (作り直す前の仮の形)。"""
        parts = []
        for index, segment in enumerate(self.segments):
            if segment.shape is not None and len(segment.shape) >= 2:
                parts.append(segment.shape)
            else:
                a, b = self.segmentEnds(index)
                parts.append(np.array([self.nodes[a].position, self.nodes[b].position]))
        if not parts:
            return self.anchors()
        points = [parts[0]] + [part[1:] for part in parts[1:]]
        joined = np.vstack(points)
        if self.closed and len(joined) > 1:
            joined = joined[:-1]
        return joined

    def lineVertices(self):
        """線全体の頂点の列 (区間がどれもエッジの上 = 頂点の列を持つときだけ。そうでなければ None)。"""
        if not self.segments or any(s.vertices is None for s in self.segments):
            return None
        result = list(self.segments[0].vertices)
        for segment in self.segments[1:]:
            result += segment.vertices[1:]
        if self.closed and len(result) > 1:
            result = result[:-1]
        return result

    def toDict(self):
        data = {"closed": self.closed, "origin": self.origin, "pristine": self.pristine,
                "nodes": [node.toDict() for node in self.nodes],
                "segments": [segment.toDict() for segment in self.segments]}
        if self.source:
            data["source"] = _plain(self.source)
        return data

    @classmethod
    def fromDict(cls, data):
        return cls([Node.fromDict(n) for n in data["nodes"]], [Segment.fromDict(s) for s in data["segments"]],
                   data.get("closed", False), data.get("origin", ORIGIN_CURVE), data.get("source"),
                   data.get("pristine", True))


def _plain(value):
    """JSON にできる形 (numpy の配列・tuple をリストに)。"""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_plain(v) for v in (value.tolist() if isinstance(value, np.ndarray) else value)]
    if isinstance(value, np.generic):
        return value.item()
    return value


# -- 点の間引き ----------------------------------------------------------------

def _shape_of(path, index):
    segment = path.segments[index]
    if segment.shape is not None and len(segment.shape) >= 2:
        return np.asarray(segment.shape, dtype=np.float64)
    a, b = path.segmentEnds(index)
    return np.array([path.nodes[a].position, path.nodes[b].position], dtype=np.float64)


def segment_place(path, point):
    """線 path の上で point にいちばん近い所の (区間の番号, 区間の長さの割合 0〜1, 点の数)。区間が無ければ None。
    乗っている点が、土台の点の編集・形ごとの移動に付いて行くための目印 (place_point で今の線の上の点に戻す)。"""
    point = np.asarray(point, dtype=np.float64)
    best = None
    for index in range(len(path.segments)):
        shape = _shape_of(path, index)
        a, b = shape[:-1], shape[1:]
        d = b - a
        length2 = np.maximum(np.einsum("ij,ij->i", d, d), 1e-30)
        u = np.clip(np.einsum("ij,ij->i", point - a, d) / length2, 0.0, 1.0)
        near = a + d * u[:, None]
        gap = np.linalg.norm(near - point, axis=1)
        k = int(np.argmin(gap))
        if best is None or gap[k] < best[0]:
            lengths = np.sqrt(np.einsum("ij,ij->i", d, d))
            total = float(lengths.sum())
            along = float(lengths[:k].sum() + lengths[k] * u[k])
            best = (gap[k], index, along / total if total > 0 else 0.0)
    return None if best is None else (best[1], best[2], len(path.nodes))


def place_point(path, place):
    """segment_place の目印 place の、今の線 path の上の点。点の数が変わった・区間が無いなら None。"""
    if place is None or place[2] != len(path.nodes) or not 0 <= place[0] < len(path.segments):
        return None
    shape = _shape_of(path, place[0])
    lengths = np.linalg.norm(np.diff(shape, axis=0), axis=1)
    total = float(lengths.sum())
    if total <= 0:
        return shape[0]
    target = min(max(place[1], 0.0), 1.0) * total
    edges = np.concatenate([[0.0], np.cumsum(lengths)])
    k = int(min(np.searchsorted(edges, target, side="right") - 1, len(lengths) - 1))
    u = (target - edges[k]) / lengths[k] if lengths[k] > 0 else 0.0
    return shape[k] + (shape[k + 1] - shape[k]) * u


def even_indices(points, count, closed=True, start=0):
    """線の上の長さで等間隔の count 個の点の番号 (start から)。"""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    n = len(points)
    if n <= count:
        return list(range(n))
    order = [(start + k) % n for k in range(n)] if closed else list(range(n))
    ring = points[order]
    if closed:
        ring = np.vstack([ring, ring[:1]])
    lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(ring, axis=0), axis=1))])
    total = lengths[-1]
    marks = [total * k / count for k in range(count)] if closed else [total * k / (count - 1) for k in range(count)]
    picked = []
    for mark in marks:
        k = int(np.argmin(np.abs(lengths[:n] - mark)))
        if order[k] not in picked:
            picked.append(order[k])
    return sorted(picked, key=lambda i: (i - start) % n) if closed else sorted(picked)


def simplify_indices(points, closed, tolerance, minimum=MIN_CLOSED_NODES):
    """線の形を保つよう間引いた点の番号 (Douglas-Peucker: 線分から最も離れた点が tolerance より遠ければ残して分ける)。
    閉じた線は、互いにいちばん離れた 2 点から始め、minimum 個に足りなければ等間隔で足す。開いた線は両端を必ず残す。"""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    n = len(points)
    if n <= 2:
        return list(range(n))

    def split(lo, hi, keep):
        """番号 lo -> hi (閉じた線は回り込む) の間を分ける。"""
        span = [(lo + k) % n for k in range(1, (hi - lo) % n if closed else hi - lo)]
        if not span:
            return
        a, b = points[lo], points[hi]
        ab = b - a
        length2 = float(ab @ ab)
        middle = points[span]
        if length2 < 1e-24:
            gap = np.linalg.norm(middle - a, axis=1)
        else:
            t = np.clip(((middle - a) @ ab) / length2, 0.0, 1.0)
            gap = np.linalg.norm(middle - (a + ab * t[:, None]), axis=1)
        far = int(np.argmax(gap))
        if gap[far] > tolerance:
            keep.add(span[far])
            split(lo, span[far], keep)
            split(span[far], hi, keep)

    if closed:
        first = 0
        second = int(np.argmax(np.linalg.norm(points - points[first], axis=1)))
        first = int(np.argmax(np.linalg.norm(points - points[second], axis=1)))
        keep = {first, second}
        split(first, second, keep)
        split(second, first, keep)
        result = sorted(keep)
        if len(result) < minimum:
            result = sorted(set(result) | set(even_indices(points, minimum, True, result[0])))
        return result
    keep = {0, n - 1}
    split(0, n - 1, keep)
    return sorted(keep)


def _pieces(points, indices, closed, vertices=None):
    """点の番号 indices で線を区間に分ける: [(形, 頂点の列か None)]。"""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    n = len(points)
    result = []
    count = len(indices) if closed else len(indices) - 1
    for k in range(count):
        a, b = indices[k], indices[(k + 1) % len(indices)]
        span = [(a + j) % n for j in range(((b - a) % n if closed else b - a) + 1)] if (closed or b > a) else [a, b]
        if closed and a == b:
            span = [(a + j) % n for j in range(n + 1)]
        result.append((points[span], None if vertices is None else [int(vertices[i]) for i in span]))
    return result


# -- 前の版 (version 1) から ------------------------------------------------------

def paths_from_v1(guide, mesh, spacing):
    """前の版の Guide (core.guides) を新しい持ち方の GuidePath のリストにする (ペイントは囲む線ごとに 1 本、ほかは 1 本)。
    mesh (MeshArrays) はエッジの上の線の頂点を引くのに、spacing (点の間隔) は間引きに使う。"""
    BRIDGE, K_CURVE, EDGE, LINE, REGION, RING = "bridge", "curve", "edge", "line", "region", "ring"   # 種類 (core.guides)
    kind = guide.kind
    if kind == BRIDGE:
        return [_bridge_from_v1(guide, mesh)]
    if kind in (K_CURVE, LINE) and guide.anchors:
        return [_anchored_from_v1(guide, ORIGIN_CURVE if kind == K_CURVE else ORIGIN_LINE)]
    if kind == RING:
        source = {}
        if guide.plane is not None:
            source = {"plane": [list(guide.plane[0]), list(guide.plane[1])], "axis": list(guide.axis)}
        if guide.anchors:
            path = _anchored_from_v1(guide, ORIGIN_RING, all_curve=True)
            path.source, path.pristine = source, False
            return [path]
        points = np.asarray(guide.points, dtype=np.float64)
        indices = even_indices(points, RING_NODES, closed=True)
        return [_fixed_path(points, indices, True, ORIGIN_RING, source)]
    if kind == LINE:                                       # フリーハンド (置いた点の無い補助線)
        points = np.asarray(guide.points, dtype=np.float64)
        if guide.closed:
            indices = simplify_indices(points, True, spacing * SIMPLIFY_SPACINGS)
        else:
            indices = [0, len(points) - 1]
        return [_fixed_path(points, indices, guide.closed, ORIGIN_FREEHAND)]
    if kind in (REGION, EDGE):
        origin = ORIGIN_PAINT if kind == REGION else ORIGIN_EDGE
        source = {}
        if kind == REGION:
            source = {"faces": list(guide.faces or []), "group": guide.ident}
            if guide.faces is None and guide.weights:
                source["weights"] = [list(w) for w in guide.weights]
        result = []
        for points, closed in guide.lines():
            points = np.asarray(points, dtype=np.float64)
            vertices = None
            if kind == EDGE and guide.vertices and len(guide.vertices) == len(points):
                vertices = list(guide.vertices)
            if vertices is None:
                found = vertex_path(mesh, points, closed)
                vertices = found.vertices if found is not None else None
            indices = simplify_indices(points, closed, spacing * SIMPLIFY_SPACINGS)
            result.append(_fixed_path(points, indices, closed, origin, dict(source), vertices))
        return result
    raise ValueError("変換できないガイドです: {}".format(kind))


def _fixed_path(points, indices, closed, origin, source=None, vertices=None):
    nodes = [Node(points[i], None if vertices is None else vertices[i]) for i in indices]
    segments = [Segment(FIXED, shape, verts) for shape, verts in _pieces(points, indices, closed, vertices)]
    return GuidePath(nodes, segments, closed, origin, source)


def _anchored_from_v1(guide, origin, all_curve=False):
    """置いた点を持つ線 (カーブ・ライン・点で曲げた輪): 点 = 置いた点、区間 = 曲線 / 直線 (形は今の線から)。"""
    K_CURVE = "curve"
    points = np.asarray(guide.points, dtype=np.float64)
    anchors = np.asarray(guide.anchors, dtype=np.float64)
    count = len(anchors) if guide.closed else len(anchors) - 1
    if all_curve:
        flags = [True] * count
    elif guide.smooth is not None and len(guide.smooth) == count:
        flags = list(guide.smooth)
    else:
        flags = [guide.kind == K_CURVE] * count
    pieces = split_segments(points, anchors, guide.closed)
    segments = [Segment(CURVE if smooth else STRAIGHT, piece) for smooth, piece in zip(flags, pieces)]
    return GuidePath([Node(a) for a in anchors], segments, guide.closed, origin, pristine=False)


def _bridge_from_v1(guide, mesh):
    """つなぎ線: 点 = 端点 (ガイドに乗る) と中継点 (頂点)、区間 = 最短 / 谷 (頂点の列は今の線を中継点で分ける)。"""
    vertices = list(guide.vertices or [])
    ends = guide.ends or []
    mode = VALLEY if guide.route == "valley" else SHORTEST
    stops = [int(s) for s in (guide.stops or [])]
    marks = [0]
    start = 0
    for stop in stops:                                     # 中継点の線の上の位置 (前から順に)
        start = vertices.index(stop, start) if stop in vertices[start:] else start
        marks.append(start)
    marks.append(len(vertices) - 1)
    nodes = []
    for k, mark in enumerate(marks):
        attach = None
        if k in (0, len(marks) - 1) and len(ends) == 2:
            end = ends[0 if k == 0 else 1]
            if end[0] is not None:
                attach = Attach(end[0], end[1], end[2], end[4] if len(end) > 4 else None)
        nodes.append(Node(mesh.points[vertices[mark]], vertices[mark], attach))
    segments = []
    for a, b in zip(marks[:-1], marks[1:]):
        piece = vertices[a:b + 1]
        segments.append(Segment(mode, mesh.points[piece], piece))
    return GuidePath(nodes, segments, False, ORIGIN_BRIDGE, {"route": mode}, pristine=False)


# -- 区間の作り直し --------------------------------------------------------------

def rebuild_segment(path, index, mesh, snap, spacing, weights=None):
    """区間 index の形を作り方から作り直す (その場で変える)。snap は点の列 (n, 3) を表面に寄せる関数、weights は
    谷の重み (core.valley.valley_weights。VALLEY のとき)。固定の区間は作り直さない (形はそのまま)。作り直したら True。"""
    from .bridge import shortest_vertex_path
    segment = path.segments[index]
    a, b = path.segmentEnds(index)
    start, end = np.asarray(path.nodes[a].position), np.asarray(path.nodes[b].position)
    if segment.mode == FIXED:
        return False
    if segment.mode == CURVE:
        shape = snap(curve_segment(path.anchors(), index, path.closed, spacing=spacing * 0.5))
        shape[0], shape[-1] = start, end
        segment.shape, segment.vertices = shape, None
        return True
    if segment.mode == STRAIGHT:
        count = max(2, int(np.ceil(np.linalg.norm(end - start) / (spacing * 0.5))) + 1)
        shape = snap(start + (end - start) * np.linspace(0.0, 1.0, count)[:, None])
        shape[0], shape[-1] = start, end
        segment.shape, segment.vertices = shape, None
        return True
    va, vb = path.nodes[a].vertex, path.nodes[b].vertex
    if va is None or vb is None:
        return False
    found = shortest_vertex_path(mesh, va, vb, weights if segment.mode == VALLEY else None)
    if found is None:
        return False
    segment.vertices = found
    segment.shape = mesh.points[found].copy()
    return True


def line_length(path):
    return polyline_length(path.line(), path.closed)


# -- ガイドの組 (保存の形 version 2) ------------------------------------------------

FORMAT = "SeamGuide.guides"
VERSION = 2


class PathEntry(object):
    """version 2 の 1 本: 番号 ident、対称の相手の番号 partner、線 path (GuidePath)。"""

    def __init__(self, ident, path, partner=None):
        self.ident = int(ident)
        self.path = path
        self.partner = None if partner is None else int(partner)

    def toDict(self):
        data = self.path.toDict()
        data["id"] = self.ident
        data["partner"] = self.partner
        return data

    @classmethod
    def fromDict(cls, data):
        return cls(data["id"], GuidePath.fromDict(data), data.get("partner"))


def convert_v1_set(guides, mesh, spacing):
    """前の版の GuideSet を version 2 の PathEntry のリストにする。ペイントは囲む線ごとに 1 本 (最初の線は元の番号、
    2 本目からは新しい番号)。対称の相手は同じ順番の線どうし、つなぎ線の乗っているガイド (と何本目の線か) は
    新しい番号に付け替える (線は 0 本目)。(entries, 次の番号)。"""
    next_id = max([g.ident for g in guides.guides()] + [-1]) + 1
    numbers = {}                                           # (元の番号, 何本目の線) -> 新しい番号
    converted = []
    for guide in guides.guides():
        paths = paths_from_v1(guide, mesh, spacing)
        for line, path in enumerate(paths):
            if line == 0:
                ident = guide.ident
            else:
                ident = next_id
                next_id += 1
            numbers[(guide.ident, line)] = ident
            converted.append((guide, line, ident, path))
    entries = []
    for guide, line, ident, path in converted:
        partner = None
        if guide.partner is not None:
            partner = numbers.get((guide.partner, line), numbers.get((guide.partner, 0)))
        for node in path.nodes:
            if node.attach is not None:
                node.attach.host = numbers.get((node.attach.host, node.attach.line), node.attach.host)
                node.attach.line = 0
        entries.append(PathEntry(ident, path, partner))
    return entries, next_id


def entries_to_json(entries, next_id):
    import json
    return json.dumps({"format": FORMAT, "version": VERSION, "next": int(next_id),
                       "guides": [entry.toDict() for entry in entries]}, separators=(",", ":"))


def entries_from_json(text):
    """version 2 の JSON から ([PathEntry], 次の番号)。version 2 でなければ ValueError。"""
    import json
    data = json.loads(text)
    if data.get("format") != FORMAT or int(data.get("version", 1)) != VERSION:
        raise ValueError("version 2 のガイドではありません")
    return [PathEntry.fromDict(d) for d in data.get("guides", [])], int(data.get("next", 0))


# -- シーム (段階 2) -------------------------------------------------------------

def node_vertex(mesh, node):
    """点の頂点: 頂点を持っていればそれ、無ければ位置にいちばん近い頂点。"""
    if node.vertex is not None and 0 <= node.vertex < len(mesh.points):
        return node.vertex
    return int(np.argmin(np.linalg.norm(mesh.points - np.asarray(node.position), axis=1)))


def segment_seam(mesh, path, index):
    """区間 index のシーム (頂点の列。両端は点の頂点)。つながらなければ None。
    エッジの上の区間 (頂点の列を持つ) はそれそのもの。表面の上の区間は、形に沿う重み付きの最短パス
    (core.edge_path.guide_edges。前の版のガイドと同じ求め方) で、端が点の頂点からずれたら最短パスで足して埋める。"""
    from .bridge import shortest_vertex_path
    from .edge_path import guide_edges, index_path
    segment = path.segments[index]
    a, b = path.segmentEnds(index)
    va, vb = node_vertex(mesh, path.nodes[a]), node_vertex(mesh, path.nodes[b])
    if segment.vertices is not None and index_path(mesh, segment.vertices, False) is not None:
        vertices = list(segment.vertices)
    else:
        shape = segment.shape if segment.shape is not None else np.array([path.nodes[a].position,
                                                                           path.nodes[b].position])
        found = guide_edges(mesh, shape, False) if len(shape) >= 2 else None
        vertices = list(found.vertices) if found is not None else [va]
    if vertices[0] != va:                                    # 端を点の頂点に合わせる
        head = shortest_vertex_path(mesh, va, vertices[0])
        if head is None:
            return None
        vertices = head[:-1] + vertices
    if vertices[-1] != vb:
        tail = shortest_vertex_path(mesh, vertices[-1], vb)
        if tail is None:
            return None
        vertices = vertices + tail[1:]
    return vertices


def path_seam(mesh, path):
    """ガイドの線のシーム (core.edge_path.EdgePath) か None: 区間ごとのシームを点の頂点でつなぎ、行って戻るとげと
    同じ頂点を 2 回通る輪を取り除く。"""
    from .edge_path import EdgePath, _simplify
    if not path.segments:
        return None
    vertices = []
    for index in range(len(path.segments)):
        part = segment_seam(mesh, path, index)
        if part is None:
            return None
        vertices.extend(part if not vertices else part[1:])
    if path.closed and len(vertices) > 1 and vertices[-1] == vertices[0]:
        vertices.pop()
    vertices = _simplify(vertices, path.closed)
    if len(vertices) < (3 if path.closed else 2):
        return None
    return EdgePath(vertices, path.closed)
