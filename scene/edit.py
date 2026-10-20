# -*- coding: utf-8 -*-
"""
ガイドを探す・足す・直す・消す (シーンを変えるものは 1 回の Undo)。統一した持ち方 (docs/05_unified_spec.md)。

どのガイドも 点 + 区間の作り方 + 点の付き方 (core.path_model.GuidePath) を持ち、作る道具が違っても編集は同じ:

    作る:   add_rings(found) / add_lines(targets, rays) / add_line_hits(targets, hits, closed, anchors=)
            add_curve(target, anchors, closed) / add_region(target, faces) / add_bridge(target, start, end, stops)
            circle_hits(targets, rays) + add_circle(target, anchors)   # 1 リングの Ctrl+ドラッグ (円を落とす)
            add_edge_guides([(target, chains)])
    点:     move_points(target, ident, {点の番号: 点}) / insert_point(target, ident, 点) / delete_points(...)
            moved_path(target, guides, ident, moves)        # 動かした形 (書かない。ドラッグ中のプレビュー)
    線:     extend_path / join_guides / split_guide / cut_segments
    区間:   set_segment_modes(target, ident, 区間の番号のリスト か None, 作り方)
    端:     set_end_attach(target, ident, 点の番号, 乗るガイドの番号 か None)   # ほかのガイドに乗せる / 外す
    動かす: adjust_ring(target, guides, ident, shift, tilt, rotate_axis) + write_adjusted   # 閉じたガイドのホイール
    戻る:   reset_rings(target, idents) / set_region(target, ident, faces)    # 断面に戻す / 塗り直す
    消す:   delete_guide(s)
    探す:   find_rings / cast_rays / pick_guide / pick_guide_line / guides_in_rect / screen_distance / world_guides

ガイドは写し (GuideSet.fromJson) を変えて書く (_commit)。書く前に、土台のガイドが変わった・消えたガイド (端が
乗っている) を作り直す (follow_hosts)。対称の相手は、編集したガイドから作り直す (_sync_partner。番号は保つ)。
ray はワールドの (始点, 向き)、project はワールドの点 (n, 3) -> 画面 (n, 2)。
"""
import collections

import numpy as np

from ..core import path_model as pm
from ..core.anchored import split_segments
from ..core.bridge import nearest_on_line, nearest_on_path, path_fraction, vertex_at_fraction
from ..core.bridge import shortest_vertex_path
from ..core.curve import catmull_rom
from ..core.geometry import plane_from_rays, reflect, reflect_vector, resample, rotate
from ..core.guides import BRIDGE, EDGE, Guide, GuideSet, REGION, RING, is_self_mirror
from ..core.path_model import Attach, GuidePath, Node, Segment
from ..core.region import (dense_faces, dense_weights, face_count, faces_from_vertex_weights, mirror_faces,
                           region_edge_loops, sparse_faces, surface_distance)
from ..core.section import curves_in_stroke, plane_section
from ..core.settings import ROUTE_SHORTEST, ROUTE_VALLEY
from ..core.stroke import surface_runs
from ..core.valley import DEFAULT_STRENGTH, valley_weights
from .store import read_guides, write_guides

__all__ = ["find_rings", "add_rings", "add_lines", "add_line_hits", "add_curve", "add_region", "add_bridge",
           "circle_hits", "add_circle",
           "add_edge_guides", "cast_rays", "curve_points", "RingFound", "SHIFT_SPACINGS",
           "move_points", "moved_path", "insert_point", "delete_points", "extend_path", "join_guides", "split_guide",
           "cut_segments", "set_segment_modes", "set_end_attach", "segment_modes",
           "adjust_ring", "write_adjusted", "reset_rings", "set_region", "region_faces", "region_mirror",
           "delete_guide", "delete_guides", "pick_guide", "pick_guide_line", "guides_in_rect", "screen_distance",
           "world_guides", "host_seam", "bridge_end", "auto_bridge_ends", "follow_hosts", "nearest_vertex",
           "bridge_weights", "route_setting", "line_segment", "set_bridge_route"]

SHIFT_SPACINGS = 2.0    # 平行移動の 1 目盛り (ガイドの点の間隔の何倍)
EDGE_LIKE = pm.EDGE_MODES

# 見つけた輪: 対象・断面の線・切った平面 (オブジェクト空間)・描いた線の向き (平面の中。傾けるときの軸)
RingFound = collections.namedtuple("RingFound", "target curves plane axis")


# -- 小さな道具 -------------------------------------------------------------------

def _object_ray(target, ray):
    origin, direction = (np.asarray(v, dtype=np.float64) for v in ray)
    a, b = target.surface.toObject(np.array([origin, origin + direction]))
    return a, b - a


def _copy(target):
    return GuideSet.fromJson(target.guides.toJson())


def nearest_vertex(target, point):
    """点 (オブジェクト空間) にいちばん近い頂点。"""
    arrays = target.surface.arrays()
    return int(np.argmin(np.linalg.norm(arrays.points - np.asarray(point, dtype=np.float64), axis=1)))


def bridge_weights(target, route):
    """谷の道の重み (MeshArrays.adjacency() の隣ごと) か None (最短 = 長さ)。谷の強さはツールの設定
    (target.symmetrySettings の valleyStrength。無ければ core.valley.DEFAULT_STRENGTH)。route は "valley" か
    区間の作り方 VALLEY。"""
    if route not in (ROUTE_VALLEY, pm.VALLEY):
        return None
    settings = target.symmetrySettings
    strength = settings.value("valleyStrength") if settings is not None else DEFAULT_STRENGTH
    return valley_weights(target.surface.arrays(), strength)


def route_setting(target):
    """新しいつなぎ線の通り方 (ツールの設定 bridgeRoute。無ければ最短)。"""
    settings = target.symmetrySettings
    return settings.value("bridgeRoute") if settings is not None else ROUTE_SHORTEST


def _rebuild(target, path, indices):
    """区間 indices を作り方から作り直す (固定は作り直さない)。作り直せなかった区間があれば False。"""
    ok = True
    arrays = target.surface.arrays()
    for index in sorted(set(i for i in indices if 0 <= i < len(path.segments))):
        segment = path.segments[index]
        if segment.mode in EDGE_LIKE:
            for node_index in path.segmentEnds(index):
                node = path.nodes[node_index]
                if node.vertex is None:
                    node.vertex = nearest_vertex(target, node.position)
                    node.position = tuple(arrays.points[node.vertex])
        if segment.mode == pm.FIXED:
            continue
        if not pm.rebuild_segment(path, index, arrays, target.surface.closest, target.spacing(),
                                  bridge_weights(target, segment.mode)):
            ok = False
    return ok


def _neighbors(path, node_index):
    """点 node_index を動かしたとき作り直す区間: 前後の区間と、曲線ならその隣 (Catmull-Rom は前後の点も使う)。"""
    count = len(path.segments)
    if not count:
        return []
    result = set()
    for offset in (-2, -1, 0, 1):
        index = node_index + offset
        if path.closed:
            index %= count
        elif not 0 <= index < count:
            continue
        if offset in (-1, 0) or path.segments[index].mode == pm.CURVE:
            result.add(index)
    return sorted(result)


def _touched(path, node_index):
    """点 node_index の前後の区間の番号。"""
    count = len(path.segments)
    result = []
    for index in (node_index - 1, node_index):
        if path.closed:
            result.append(index % count)
        elif 0 <= index < count:
            result.append(index)
    return result


def _commit(changes, undo_name):
    """[(target, GuideSet, [番号])] を書いて読み直す。{target の名前: [番号]}。
    書く前に、土台のガイドが変わった・消えたガイドを作り直す (follow_hosts。同じ 1 回の Undo)。"""
    if not changes:
        return {}
    for target, guides, _ids in changes:
        follow_hosts(target, guides)
    write_guides([(target.path, guides) for target, guides, _ids in changes], undo_name)
    result = {}
    for target, _guides, ids in changes:
        target.reload()
        result[target.name()] = ids
    return result


# -- 対称の相手 ---------------------------------------------------------------------

def _remap_vertices(target, vertices, transform):
    """頂点の列を transform (点 (n, 3) -> 点 (n, 3)) で写した所にいちばん近い頂点の列にし、隣どうしがエッジで
    つながらない所は最短パスで埋める (左右で形が違うメッシュでもエッジの道になる)。"""
    arrays = target.surface.arrays()
    moved = transform(arrays.points[list(vertices)])
    mapped = []
    for point in moved:
        vertex = nearest_vertex(target, point)
        if not mapped or mapped[-1] != vertex:
            mapped.append(vertex)
    result = [mapped[0]]
    for vertex in mapped[1:]:
        piece = shortest_vertex_path(arrays, result[-1], vertex)
        if piece is None:
            return None
        result.extend(piece[1:])
    return result


def _transform_path(target, guides, path, transform, attach_host=None, normal=None):
    """path を transform で写して表面に寄せた写し (GuidePath)。点はいちばん近い表面の点 (頂点を持つ点は近い頂点)、
    ガイドに乗る点は attach_host(元の番号) が返すガイドの上へ、固定の区間は形を写して寄せ (頂点の列も写す)、
    ほかの区間は作り直す。作れなければ None。"""
    snap = target.surface.closest
    arrays = target.surface.arrays()
    nodes = []
    for node in path.nodes:
        point = transform(np.array([node.position]))[0]
        attach = None
        if node.attach is not None and attach_host is not None:
            host = attach_host(node.attach.host)
            placed = bridge_end(target, guides, host, 0, point) if host is not None else None
            if placed is not None:
                nodes.append(placed)
                continue
        if node.vertex is not None:
            vertex = nearest_vertex(target, point)
            nodes.append(Node(arrays.points[vertex], vertex, attach))
        else:
            nodes.append(Node(snap(np.array([point]))[0], None, attach))
    segments = []
    for index, segment in enumerate(path.segments):
        a, b = path.segmentEnds(index)
        if segment.mode == pm.FIXED and segment.shape is not None:
            vertices = None
            if segment.vertices is not None:
                vertices = _remap_vertices(target, segment.vertices, transform)
            if vertices is not None:
                if nodes[a].vertex is not None and vertices[0] != nodes[a].vertex:
                    vertices = (shortest_vertex_path(arrays, nodes[a].vertex, vertices[0]) or [vertices[0]])[:-1] \
                        + vertices
                if nodes[b].vertex is not None and vertices[-1] != nodes[b].vertex:
                    vertices = vertices + (shortest_vertex_path(arrays, vertices[-1], nodes[b].vertex)
                                           or [vertices[-1]])[1:]
                shape = arrays.points[vertices]
            else:
                shape = snap(transform(segment.shape))
                shape[0], shape[-1] = nodes[a].position, nodes[b].position
            segments.append(Segment(pm.FIXED, shape, vertices))
        else:
            segments.append(Segment(segment.mode))
    result = GuidePath(nodes, segments, path.closed, path.origin, dict(path.source), path.pristine)
    if not _rebuild(target, result, [i for i, s in enumerate(result.segments) if s.mode != pm.FIXED]):
        return None
    return result


def _mirror_path(target, guides, guide):
    """guide の対称の相手の線 (GuidePath) か None。点・形を鏡に写して表面に寄せ、乗っているガイドは相手のガイド
    (無ければ同じガイド。中心の輪など) へ。作ったままのリングは鏡に写した平面の断面 (正確な断面のまま)。"""
    mirror, _label = target.mirrorPlane()
    path = guide.path

    def transform(points):
        return reflect(np.asarray(points, dtype=np.float64), mirror)

    def partner_of(host):
        other = guides.get(host)
        if other is not None and other.partner is not None and guides.get(other.partner) is not None:
            return other.partner
        return host if other is not None else None

    source = dict(path.source)
    if guide.plane is not None:
        origin = reflect(np.array([guide.plane[0]]), mirror)[0]
        source["plane"] = [list(origin), list(reflect_vector(guide.plane[1], mirror[1]))]
        if guide.axis is not None:
            source["axis"] = list(reflect_vector(guide.axis, mirror[1]))
    if path.origin == pm.ORIGIN_RING and path.pristine and source.get("plane"):
        center = transform(np.asarray(guide.points)).mean(axis=0)
        ring = _section_ring(target, (np.asarray(source["plane"][0]), np.asarray(source["plane"][1])), center,
                             float(np.ptp(np.asarray(guide.points), axis=0).max()))
        if ring is not None:
            ring.source = source
            return ring
    mirrored = _transform_path(target, guides, path, transform, partner_of)
    if mirrored is not None:
        mirrored.source = source
        if path.origin == pm.ORIGIN_PAINT and guide.faces is not None:
            faces, _unmatched = region_mirror(target, dense_faces(guide.faces, face_count(target.surface.arrays())))
            mirrored.source["faces"] = sparse_faces(faces)
    return mirrored


def _sync_partner(target, guides, guide, create=None):
    """guide の対称の相手を作る / 作り直す (番号は保つ)。create が None なら、相手がいれば作り直し、いなければ
    対称がオンのときだけ作る。相手が自分と重なる (中心を通る線) なら作らない (いれば外す)。相手の番号か None。"""
    partner = guides.get(guide.partner) if guide.partner is not None else None
    if partner is None and not (target.symmetric() if create is None else create):
        return None
    mirrored = _mirror_path(target, guides, guide)
    if mirrored is None or is_self_mirror(np.asarray(guide.points), mirrored.line(), target.tolerance()):
        if partner is not None:
            guides.detachPartner(guide.ident)
        return None
    if partner is not None:
        partner.path = mirrored
        return partner.ident
    ident = guides.add(Guide(mirrored, partner=guide.ident))
    guide.partner = ident
    return ident


def _add(target, guides, path):
    """guides に足し、対称の相手も足す (対称がオンなら)。足した番号のリスト。"""
    ident = guides.add(Guide(path))
    partner = _sync_partner(target, guides, guides.get(ident))
    return [ident] if partner is None else [ident, partner]


# -- 作る ------------------------------------------------------------------------

def find_rings(targets, ray0, ray1, start, end, project):
    """描いた線 (画面の start -> end。両端の視線 ray0 / ray1) の範囲の断面の線を、メッシュごとに。"""
    found = []
    for target in targets:
        local0 = _object_ray(target, ray0)
        plane = plane_from_rays(local0, _object_ray(target, ray1))
        if plane is None:
            continue
        curves = plane_section(target.surface.arrays(), plane)
        chosen = curves_in_stroke(curves, lambda points, t=target: project(t.surface.toWorld(points)),
                                  start, end)
        if chosen:
            axis = np.cross(plane[1], local0[1])         # 平面の中で、視線に直交する向き = 描いた線の向き
            axis /= max(np.linalg.norm(axis), 1e-12)
            found.append(RingFound(target, chosen, plane, axis))
    return found


def _ring_path(target, points, closed, plane, axis):
    """断面の線から、リングのガイドの線: 点の間隔に置き直し、等間隔の RING_NODES 点 + 固定の区間 (断面の形そのもの)。"""
    points = resample(np.asarray(points, dtype=np.float64), target.spacing(), closed=closed)
    if closed:
        indices = pm.even_indices(points, pm.RING_NODES, closed=True)
    else:
        indices = [0, len(points) - 1]
    source = {"plane": [list(np.asarray(plane[0], dtype=np.float64)), list(np.asarray(plane[1], dtype=np.float64))],
              "axis": list(np.asarray(axis, dtype=np.float64))}
    return pm._fixed_path(points, indices, closed, pm.ORIGIN_RING, source)


def _section_ring(target, plane, center, size):
    """平面の断面のうち、中心が center にいちばん近い (輪の大きさ size より近い) 輪のリングの線か None。"""
    curves = plane_section(target.surface.arrays(), plane)
    if not curves:
        return None
    distances = [float(np.linalg.norm(c.points.mean(axis=0) - center)) for c in curves]
    best = int(np.argmin(distances))
    if distances[best] > max(size, target.spacing()):
        return None
    axis = np.cross(plane[1], [1.0, 0.0, 0.0] if abs(plane[1][0]) < 0.9 else [0.0, 1.0, 0.0])
    return _ring_path(target, curves[best].points, curves[best].closed, plane, axis / np.linalg.norm(axis))


def add_rings(found, undo_name="輪切りのガイド"):
    changes = []
    for target, curves, plane, axis in found:
        guides = _copy(target)
        ids = []
        for curve in curves:
            ids += _add(target, guides, _ring_path(target, curve.points, curve.closed, plane, axis))
        changes.append((target, guides, ids))
    return _commit(changes, undo_name)


def cast_rays(targets, rays):
    """視線 (ワールドの (始点, 向き)) ごとに、いちばん手前で当たったメッシュの (番号, オブジェクト空間の点,
    ワールドの点)。当たらなければ None。"""
    if not targets or not rays:
        return [None] * len(rays)
    origins = [ray[0] for ray in rays]
    directions = [ray[1] for ray in rays]
    best = [None] * len(rays)
    best_distance = [np.inf] * len(rays)
    for index, target in enumerate(targets):
        local = target.surface.raycast(origins, directions)
        found = [k for k, hit in enumerate(local) if hit is not None]
        if not found:
            continue
        world = target.surface.toWorld([local[k] for k in found])
        for k, point in zip(found, world):
            distance = float(np.linalg.norm(point - np.asarray(origins[k], dtype=np.float64)))
            if distance < best_distance[k]:
                best_distance[k] = distance
                best[k] = (index, local[k], tuple(point))
    return best


def add_line_hits(targets, hits, closed=False, undo_name="補助線のガイド", anchors=None):
    """cast_rays の結果から補助線を足す (メッシュごとに、当たった区間ごとに 1 本)。
    anchors が無ければフリーハンド (両端の点 + 固定の区間。閉じた線は形を間引いた点)。anchors = (メッシュの番号,
    置いた点 (オブジェクト空間) のリスト) ならライン (置いた点 + 直線の区間。区間の形は当てた点の列)。線が途中で
    切れて何本かになったときは、置いた点を使わずフリーハンドと同じにする。"""
    changes = []
    for index, target in enumerate(targets):
        mine = [hit[1] if hit is not None and hit[0] == index else None for hit in hits]
        runs = surface_runs(mine)
        if not runs:
            continue
        guides = _copy(target)
        ids = []
        is_closed = closed and len(runs) == 1
        for run in runs:
            if is_closed and len(run) > 2 and np.linalg.norm(run[-1] - run[0]) <= target.spacing():
                run = run[:-1]                      # 閉じた線: 最初の点に戻った最後の点は除く
            points = resample(run, target.spacing(), closed=is_closed)
            mine_anchors = anchors[1] if anchors is not None and anchors[0] == index and len(runs) == 1 else None
            if mine_anchors is not None and len(mine_anchors) >= 2:
                path = _line_path(points, mine_anchors, is_closed)
            elif is_closed:
                path = pm._fixed_path(points, pm.simplify_indices(points, True, target.spacing() *
                                                                  pm.SIMPLIFY_SPACINGS), True, pm.ORIGIN_FREEHAND)
            else:
                path = pm._fixed_path(points, [0, len(points) - 1], False, pm.ORIGIN_FREEHAND)
            ids += _add(target, guides, path)
        changes.append((target, guides, ids))
    return _commit(changes, undo_name)


def _line_path(points, anchors, closed):
    anchors = np.asarray(anchors, dtype=np.float64).reshape(-1, 3)
    pieces = split_segments(points, anchors, closed)
    return GuidePath([Node(a) for a in anchors], [Segment(pm.STRAIGHT, piece) for piece in pieces], closed,
                     pm.ORIGIN_LINE)


def add_lines(targets, rays, closed=False, undo_name="補助線のガイド"):
    """画面の線の視線 (ワールドの (始点, 向き) のリスト) を、いちばん手前のメッシュに当てて補助線 (フリーハンド) にする。"""
    return add_line_hits(targets, cast_rays(targets, rays), closed, undo_name)


def curve_points(target, anchors, closed=False):
    """置いた点 anchors (オブジェクト空間) を通るカーブの点の列 (表面に寄せる。描いている間のプレビューにも)。"""
    spacing = target.spacing()
    dense = catmull_rom(anchors, closed=closed, spacing=spacing * 0.5)
    if len(dense) < 2:
        return dense
    return resample(target.surface.closest(dense), spacing, closed=closed)


def add_curve(target, anchors, closed=False, undo_name="カーブのガイド"):
    """置いた点を通るカーブのガイドを足す (置いた点 + 曲線の区間。対称の相手も。1 回の Undo)。{シェイプ: [番号]}。"""
    anchors = np.asarray(anchors, dtype=np.float64).reshape(-1, 3)
    if len(anchors) < 2:
        return {}
    count = len(anchors) if closed else len(anchors) - 1
    path = GuidePath([Node(a) for a in anchors], [Segment(pm.CURVE) for _ in range(count)], closed, pm.ORIGIN_CURVE)
    if not _rebuild(target, path, range(count)):
        return {}
    guides = _copy(target)
    return _commit([(target, guides, _add(target, guides, path))], undo_name)


def circle_hits(targets, rays):
    """画面の円の点の視線 rays を、カメラの向きに落とした所: (target, オブジェクト空間の点 (n, 3)) か None。
    全部が同じメッシュに当たったときだけ (はみ出す・別のメッシュにかかるなら None。作らない)。"""
    hits = cast_rays(targets, rays)
    if not hits or any(hit is None for hit in hits) or len({hit[0] for hit in hits}) != 1:
        return None
    return targets[hits[0][0]], np.array([hit[1] for hit in hits], dtype=np.float64)


def add_circle(target, anchors, undo_name="円のガイド"):
    """画面の円を落とした点 anchors (オブジェクト空間。円の順) を通る閉じた曲線のガイドを足す (点 + 曲線の区間。
    種類はリング、平面は持たない。対称の相手も。1 回の Undo)。{シェイプ: [番号]}。"""
    anchors = np.asarray(anchors, dtype=np.float64).reshape(-1, 3)
    if len(anchors) < 3:
        return {}
    path = GuidePath([Node(a) for a in anchors], [Segment(pm.CURVE) for _ in range(len(anchors))], True,
                     pm.ORIGIN_CIRCLE, pristine=False)
    if not _rebuild(target, path, range(len(anchors))):
        return {}
    guides = _copy(target)
    return _commit([(target, guides, _add(target, guides, path))], undo_name)


def _loop_path(target, vertices, closed, origin, source=None):
    """エッジの上の線 (頂点の列) のガイドの線: 形を間引いた点 + 固定の区間 (頂点の列も)。"""
    arrays = target.surface.arrays()
    points = arrays.points[list(vertices)]
    indices = pm.simplify_indices(points, closed, target.spacing() * pm.SIMPLIFY_SPACINGS)
    return pm._fixed_path(points, indices, closed, origin, source, list(vertices))


def add_edge_guides(chains_by_target, undo_name="境界のガイド"):
    """[(target, [(頂点の番号の配列, 閉じているか)])] を境界のガイドにする (全メッシュで 1 回の Undo。対称の相手は
    作らない)。{シェイプ: [番号]}。同じ頂点の列の境界のガイドがすでにあれば足さない。"""
    changes = []
    for target, chains in chains_by_target:
        guides = _copy(target)
        existing = set()
        for guide in guides.guides():
            if guide.kind == EDGE and guide.vertices:
                existing.add(_chain_key(guide.vertices, guide.closed))
        ids = []
        for vertices, closed in chains:
            vertices = [int(v) for v in vertices]
            key = _chain_key(vertices, closed)
            if len(vertices) < 2 or key in existing:
                continue
            existing.add(key)
            ids.append(guides.add(Guide(_loop_path(target, vertices, closed, pm.ORIGIN_EDGE))))
        if ids:
            changes.append((target, guides, ids))
    return _commit(changes, undo_name)


def _chain_key(vertices, closed):
    """頂点の列の同じさ (向き・閉じた線の始まりによらない)。"""
    vertices = list(vertices)
    if closed:
        return ("closed", frozenset(vertices), len(vertices))
    return ("open", tuple(vertices) if vertices[0] <= vertices[-1] else tuple(vertices[::-1]))


# -- ガイドに乗る点 (つなぎ線の端点など) -------------------------------------------

def host_seam(target, guide, line=0):
    """ガイド guide のシーム (頂点の番号の列, 閉じているか) か None。ガイドに乗る点が乗る所。"""
    if guide is None:
        return None
    path = pm.path_seam(target.surface.arrays(), guide.path)
    return None if path is None else (path.vertices, path.closed)


def bridge_end(target, guides, host, line, point):
    """ガイド host のシームの上で、点 point (オブジェクト空間) にいちばん近い頂点に乗る点 (Node)。目印は host の
    線の上のいちばん近い点。乗れない (無いガイド・シームが無い) なら None。"""
    guide = guides.get(host)
    if guide is None:
        return None
    seam = host_seam(target, guide)
    if seam is None:
        return None
    vertices, closed = seam
    arrays = target.surface.arrays()
    anchor = nearest_on_line(np.asarray(guide.points), guide.closed, point)
    vertex = nearest_on_path(arrays, vertices, anchor)
    attach = Attach(host, 0, path_fraction(arrays, vertices, closed, vertex), anchor,
                    pm.segment_place(guide.path, anchor))
    return Node(arrays.points[vertex], vertex, attach)


def _resolve_attach(target, guides, node):
    """乗っている点を、乗っているガイドの今の線に合わせる (目印を新しい線の上へ移し、そこに近いシームの頂点へ)。
    乗っているガイドが無くなっていれば固定 (attach を外す)。動いたら True。

    目印の移し方: 土台の点を動かした・形ごと動かした (点の数が同じで、断面のままの輪でない) なら、同じ区間の同じ割合の
    所 (place。尖らせて曲げても曲げた所に付いて行く)。断面のままの輪 (ホイールで断面を作り直すと点が作り直される)・
    点の数が変わった (足した・消した) なら、前の目印にいちばん近い線の上の点。"""
    attach = node.attach
    guide = guides.get(attach.host) if attach is not None else None
    seam = host_seam(target, guide) if guide is not None else None
    if seam is None:
        node.attach = None                                   # 乗っているガイドが消えた: その場に固定
        return False
    vertices, closed = seam
    arrays = target.surface.arrays()
    before = attach.point if attach.point is not None else node.position
    anchor = None if guide.pristine else pm.place_point(guide.path, attach.place)
    if anchor is None:
        anchor = nearest_on_line(np.asarray(guide.points), guide.closed, before)
    vertex = nearest_on_path(arrays, vertices, anchor)
    attach.point = tuple(float(c) for c in anchor)
    attach.place = pm.segment_place(guide.path, anchor)
    attach.fraction = path_fraction(arrays, vertices, closed, vertex)
    moved = vertex != node.vertex
    node.vertex = vertex
    node.position = tuple(arrays.points[vertex])
    return moved


def follow_hosts(target, guides):
    """土台のガイドが変わった (線が違う)・消えたガイドの、乗っている点を合わせて作り直す。比べるのはシームに保存して
    あるガイド (アトリビュートから読み直す。target.guides はツールがホイールの間に写しへ差し替えるため)。
    乗っている点の前後の区間は作り直す (固定の区間は曲線に変わる)。"""
    stored = read_guides(target.path)
    for guide in guides.guides():
        path = guide.path
        for index, node in enumerate(path.nodes):
            if node.attach is None:
                continue
            new, old = guides.get(node.attach.host), stored.get(node.attach.host)
            if new is not None and old is not None and new.points == old.points:
                place = node.attach.place
                if (place is None or place[2] != len(new.path.nodes)) and node.attach.point is not None:
                    node.attach.place = pm.segment_place(new.path, node.attach.point)   # 点を足した・消した (形は同じ)
                continue
            if _resolve_attach(target, guides, node):
                for segment_index in _touched(path, index):
                    if path.segments[segment_index].mode == pm.FIXED:
                        path.segments[segment_index] = Segment(pm.CURVE)
                _rebuild(target, path, _neighbors(path, index))


def auto_bridge_ends(target, guides, first, second, view):
    """編集で 2 本選んで作るときの端点 (Node, Node) か None: カメラから見て奥側。first は、そのシームのうちいちばん
    奥 (視線の向き view (オブジェクト空間) に最も進んだ) 頂点。second は、そのシームの奥側の半分の頂点のうち、first の
    端点から表面の最短距離がいちばん短いもの。"""
    arrays = target.surface.arrays()
    view = np.asarray(view, dtype=np.float64)
    seams = []
    for ident in (first, second):
        guide = guides.get(ident)
        seam = host_seam(target, guide) if guide is not None and guide.kind != BRIDGE else None
        if seam is None:
            return None
        seams.append(seam)
    (a_vertices, _a_closed), (b_vertices, _b_closed) = seams
    start = int(a_vertices[int(np.argmax(arrays.points[a_vertices] @ view))])
    depth_b = arrays.points[b_vertices] @ view
    far = [v for v, d in zip(b_vertices, depth_b) if d >= np.median(depth_b)]
    reach = surface_distance(arrays, [start], np.inf)
    goal = int(min(far, key=lambda v: reach[v]))
    if not np.isfinite(reach[goal]):
        return None
    return (bridge_end(target, guides, first, 0, arrays.points[start]),
            bridge_end(target, guides, second, 0, arrays.points[goal]))


def add_bridge(target, start, end, stops=(), undo_name="つなぎ線", route=None):
    """端点 start / end (Node。ガイドに乗る点か頂点) と中継点 stops (頂点の番号) のつなぎ線を足す (区間は最短 / 谷。
    対称がオンなら相手も。1 回の Undo)。通り方 route を省くとツールの設定。{シェイプ: [番号]}。つながらなければ {}。"""
    arrays = target.surface.arrays()
    mode = pm.VALLEY if (route or route_setting(target)) == ROUTE_VALLEY else pm.SHORTEST
    nodes = [start] + [Node(arrays.points[int(v)], int(v)) for v in stops] + [end]
    path = GuidePath(nodes, [Segment(mode) for _ in range(len(nodes) - 1)], False, pm.ORIGIN_BRIDGE,
                     {"route": mode}, pristine=False)
    if not _rebuild(target, path, range(len(path.segments))):
        return {}
    guides = _copy(target)
    return _commit([(target, guides, _add(target, guides, path))], undo_name)


def set_bridge_route(target, idents, route, undo_name="つなぎ線の通り方"):
    """ガイド idents (と相手) のエッジの上の区間 (最短 / 谷) を route に切り替える (1 回の Undo)。変えた番号。"""
    mode = pm.VALLEY if route == ROUTE_VALLEY else pm.SHORTEST
    guides = _copy(target)
    changed = []
    for ident in idents:
        guide = guides.get(ident)
        if guide is None:
            continue
        indices = [i for i, s in enumerate(guide.path.segments) if s.mode in EDGE_LIKE]
        if not indices:
            continue
        for index in indices:
            guide.path.segments[index] = Segment(mode)
        _rebuild(target, guide.path, indices)
        changed.append(ident)
        if _sync_partner(target, guides, guide) is not None:
            changed.append(guide.partner)
    if changed:
        _commit([(target, guides, changed)], undo_name)
    return changed


# -- 点の編集 (どのガイドでも同じ) -------------------------------------------------

def _place(target, guides, path, index, point):
    """点 index を point (オブジェクト空間) へ置く: ガイドに乗る点はそのシームの上をスライド、頂点を持つ点 (エッジの上の
    区間の端) は近い頂点、ほかは表面のいちばん近い点。"""
    node = path.nodes[index]
    point = np.asarray(point, dtype=np.float64)
    if node.attach is not None:
        placed = bridge_end(target, guides, node.attach.host, 0, point)
        if placed is not None:
            path.nodes[index] = placed
            return
        node.attach = None
    edge = node.vertex is not None or any(path.segments[i].mode in EDGE_LIKE for i in _touched(path, index))
    if edge:
        vertex = nearest_vertex(target, point)
        path.nodes[index] = Node(target.surface.arrays().points[vertex], vertex, None)
    else:
        path.nodes[index] = Node(target.surface.closest(np.array([point]))[0], None, None)


def moved_path(target, guides, ident, moves, attach=None):
    """ガイド ident の点を moves ({点の番号: 点}) へ動かした線 (GuidePath の写し。書かない)。動かした点の前後の
    固定の区間は曲線になる。attach ({点の番号: 乗せるガイドの番号 か None}) は、その点をガイドに乗せる / 外す
    (端をほかのガイドの近くへドラッグしたとき)。動かせなければ None。"""
    guide = guides.get(ident)
    if guide is None:
        return None
    path = guide.copy().path
    rebuild = set()
    attach = attach or {}
    for index, point in moves.items():
        if not 0 <= index < len(path.nodes):
            continue
        if index in attach:
            host = attach[index]
            path.nodes[index].attach = None
            placed = bridge_end(target, guides, host, 0, point) if host is not None and host != ident else None
            if placed is not None:
                path.nodes[index] = placed
            else:
                path.nodes[index] = Node(target.surface.closest(np.array([point], dtype=np.float64))[0],
                                         path.nodes[index].vertex if any(path.segments[i].mode in EDGE_LIKE
                                                                         for i in _touched(path, index)) else None)
                _place(target, guides, path, index, point)
        else:
            _place(target, guides, path, index, point)
        for segment_index in _touched(path, index):
            if path.segments[segment_index].mode == pm.FIXED:
                path.segments[segment_index] = Segment(pm.CURVE)
        rebuild.update(_neighbors(path, index))
    if not _rebuild(target, path, rebuild):
        return None
    path.pristine = False
    return path


def _replace(target, guides, guide, path):
    """guide の線を path にして、相手を作り直す。"""
    guide.path = path
    _sync_partner(target, guides, guide)


def move_points(target, ident, moves, undo_name="点を動かす", attach=None):
    """ガイド ident の点を動かす ({点の番号: 点})。attach は moved_path と同じ (端を乗せる / 外す)。1 回の Undo。
    動かせたら True。"""
    guides = _copy(target)
    path = moved_path(target, guides, ident, moves, attach)
    if path is None:
        return False
    _replace(target, guides, guides.get(ident), path)
    _commit([(target, guides, [ident])], undo_name)
    return True


def insert_point(target, ident, point, undo_name="点を足す"):
    """ガイド ident の線の上 (point にいちばん近い区間の形の点) に点を足す。形は変えない (区間をそこで 2 つに分ける。
    曲線の区間は作り直す)。足した点の番号か None。"""
    guides = _copy(target)
    guide = guides.get(ident)
    if guide is None:
        return None
    path = guide.path
    point = np.asarray(point, dtype=np.float64)
    best = None
    for index, segment in enumerate(path.segments):
        shape = segment.shape if segment.shape is not None else np.array(
            [path.nodes[i].position for i in path.segmentEnds(index)])
        gap = np.linalg.norm(shape - point, axis=1)
        k = int(np.argmin(gap))
        if best is None or gap[k] < best[0]:
            best = (gap[k], index, k)
    if best is None:
        return None
    _gap, index, k = best
    segment = path.segments[index]
    shape = segment.shape
    if shape is None or k == 0 or k == len(shape) - 1:
        return None                                        # 点の上: 足さない
    vertex = segment.vertices[k] if segment.vertices is not None else None
    node = Node(shape[k], vertex)
    first = Segment(segment.mode, shape[:k + 1], segment.vertices[:k + 1] if segment.vertices else None)
    second = Segment(segment.mode, shape[k:], segment.vertices[k:] if segment.vertices else None)
    new_index = index + 1
    path.nodes.insert(new_index, node)
    path.segments[index:index + 1] = [first, second]
    if segment.mode == pm.CURVE:
        _rebuild(target, path, _neighbors(path, new_index))
    path.pristine = False
    _replace(target, guides, guide, path)
    _commit([(target, guides, [ident])], undo_name)
    return new_index


def _merge(first, second):
    """点を消して前後の区間をつなぐときの区間: 両方固定なら形をつないだ固定、同じエッジの道なら同じ作り方、ほかは曲線。"""
    if first.mode == pm.FIXED and second.mode == pm.FIXED and first.shape is not None and second.shape is not None:
        vertices = None
        if first.vertices is not None and second.vertices is not None:
            vertices = first.vertices + second.vertices[1:]
        return Segment(pm.FIXED, np.vstack([first.shape, second.shape[1:]]), vertices)
    if first.mode == second.mode and first.mode in EDGE_LIKE:
        return Segment(first.mode)
    if first.mode == pm.STRAIGHT and second.mode == pm.STRAIGHT:
        return Segment(pm.STRAIGHT)
    return Segment(pm.CURVE)


def delete_points(target, ident, indices, undo_name="点を消す"):
    """ガイド ident の点 indices を消す (開いた線は 2 点・閉じた線は 3 点まで残す。それより少なくなるなら消さない)。
    前後の区間は 1 本にする (_merge)。1 回の Undo。消したら True。"""
    guides = _copy(target)
    guide = guides.get(ident)
    if guide is None:
        return False
    path = guide.path
    order = sorted(set(int(i) for i in indices if 0 <= int(i) < len(path.nodes)), reverse=True)
    if not order or len(path.nodes) - len(order) < (3 if path.closed else 2):
        return False
    rebuild_near = []
    for index in order:
        count = len(path.nodes)
        if path.closed:
            before = (index - 1) % count
            merged = _merge(path.segments[before], path.segments[index])
            path.segments[before] = merged
            del path.segments[index]
            del path.nodes[index]
            rebuild_near.append(before if before < index else before - 1)
        elif index == 0:
            del path.segments[0], path.nodes[0]
        elif index == count - 1:
            del path.segments[-1], path.nodes[-1]
        else:
            path.segments[index - 1] = _merge(path.segments[index - 1], path.segments[index])
            del path.segments[index]
            del path.nodes[index]
            rebuild_near.append(index - 1)
    rebuild = set()
    for segment_index in rebuild_near:
        if 0 <= segment_index < len(path.segments):
            rebuild.update(_neighbors(path, segment_index))
            rebuild.update(_neighbors(path, segment_index + 1))
    rebuild = {i for i in rebuild if path.segments[i].mode != pm.FIXED or path.segments[i].shape is None}
    _rebuild(target, path, rebuild)
    path.pristine = False
    _replace(target, guides, guide, path)
    _commit([(target, guides, [ident])], undo_name)
    return True


def segment_modes(guide):
    """区間ごとの作り方のリスト。"""
    return [segment.mode for segment in guide.path.segments]


def set_segment_modes(target, ident, indices, mode, undo_name="区間の作り方"):
    """ガイド ident の区間 indices (None なら全部) を作り方 mode にして作り直す (相手も。1 回の Undo)。
    固定にはしない (形の元が無いため)。変えたら True。"""
    if mode not in (pm.CURVE, pm.STRAIGHT, pm.SHORTEST, pm.VALLEY):
        return False
    guides = _copy(target)
    guide = guides.get(ident)
    if guide is None:
        return False
    path = guide.path
    chosen = list(range(len(path.segments))) if indices is None else [i for i in indices if 0 <= i < len(path.segments)]
    if not chosen:
        return False
    for index in chosen:
        path.segments[index] = Segment(mode)
        if mode not in EDGE_LIKE:
            for node_index in path.segmentEnds(index):      # 表面の上の区間の端は頂点に縛らない
                node = path.nodes[node_index]
                if node.attach is None and all(path.segments[i].mode not in EDGE_LIKE
                                               for i in _touched(path, node_index)):
                    node.vertex = None
    rebuild = set(chosen)
    for index in chosen:
        for node_index in path.segmentEnds(index):
            rebuild.update(_neighbors(path, node_index))
    if not _rebuild(target, path, rebuild):
        return False
    path.pristine = False
    _replace(target, guides, guide, path)
    _commit([(target, guides, [ident])], undo_name)
    return True


def set_end_attach(target, ident, index, host, undo_name="端をガイドに乗せる"):
    """開いた線 ident の端の点 index をガイド host に乗せる (host が None なら外す: その場の位置のまま自由な点に)。
    乗せると、host のシームの上のいちばん近い頂点へ動き、前後の区間を作り直す。1 回の Undo。変えたら True。"""
    guides = _copy(target)
    guide = guides.get(ident)
    if guide is None or guide.closed or index not in (0, len(guide.path.nodes) - 1):
        return False
    path = guide.path
    node = path.nodes[index]
    if host is None:
        if node.attach is None:
            return False
        node.attach = None
    else:
        if host == ident:
            return False
        placed = bridge_end(target, guides, host, 0, node.position)
        if placed is None:
            return False
        path.nodes[index] = placed
        for segment_index in _touched(path, index):
            if path.segments[segment_index].mode == pm.FIXED:
                path.segments[segment_index] = Segment(pm.CURVE)
        _rebuild(target, path, _neighbors(path, index))
    path.pristine = False
    _replace(target, guides, guide, path)
    _commit([(target, guides, [ident])], undo_name)
    return True


# -- 線の編集 (伸ばす・つなぐ・切り離す) ------------------------------------------

def extend_path(target, ident, anchor, at_start=False, points=None, smooth=None, undo_name="線を伸ばす"):
    """開いた線の端から anchor (オブジェクト空間) まで伸ばす。points を渡すと、その点の列 (端から外へ向かう順。画面の
    直線を表面に落としたもの) を直線の区間の形にする。smooth を省くと端の区間に合わせる (曲線なら曲線、エッジの道なら
    同じ作り方、ほかは直線)。1 回の Undo。伸ばしたら True。"""
    guides = _copy(target)
    guide = guides.get(ident)
    if guide is None or guide.closed:
        return False
    path = guide.path
    anchor = np.asarray(anchor, dtype=np.float64)
    end_segment = path.segments[0 if at_start else -1] if path.segments else Segment(pm.STRAIGHT)
    if smooth is True:
        mode = pm.CURVE
    elif smooth is False:
        mode = pm.STRAIGHT
    elif end_segment.mode in (pm.CURVE,) + EDGE_LIKE:
        mode = end_segment.mode
    else:
        mode = pm.STRAIGHT
    end_index = 0 if at_start else len(path.nodes) - 1
    end_node = path.nodes[end_index]
    shape = None
    if mode == pm.STRAIGHT and points is not None and len(points):
        shape = np.vstack([np.asarray(end_node.position), np.asarray(points, dtype=np.float64).reshape(-1, 3), anchor])
    vertex = nearest_vertex(target, anchor) if mode in EDGE_LIKE else None
    node = Node(target.surface.arrays().points[vertex] if vertex is not None else anchor, vertex)
    if at_start:
        path.nodes.insert(0, node)
        path.segments.insert(0, Segment(mode, None if shape is None else shape[::-1]))
        new_index = 0
    else:
        path.nodes.append(node)
        path.segments.append(Segment(mode, shape))
        new_index = len(path.nodes) - 1
    rebuild = set(_neighbors(path, new_index))
    if shape is not None:
        rebuild.discard(0 if at_start else len(path.segments) - 1)
    _rebuild(target, path, rebuild)
    path.pristine = False
    _replace(target, guides, guide, path)
    _commit([(target, guides, [ident])], undo_name)
    return True


def _reversed(path):
    nodes = path.nodes[::-1]
    segments = [Segment(s.mode, None if s.shape is None else s.shape[::-1],
                        None if s.vertices is None else s.vertices[::-1]) for s in path.segments[::-1]]
    return GuidePath(nodes, segments, path.closed, path.origin, dict(path.source), path.pristine)


def join_guides(target, first, second=None, undo_name="線をつなぐ"):
    """2 本の開いた線の近い端どうしをつないで 1 本にする。second を省くか同じなら、first の始点と終点をつないで閉じる
    (3 点以上)。つなぐ区間は、両側の区間がどちらも曲線なら曲線、そうでなければ直線 (端がほぼ同じ所なら点を 1 つに
    する)。対称の相手は作り直す (2 本が互いの相手なら、つないだ線は中心をまたぐので相手を作らない)。1 回の Undo。
    つないだ線の番号か None。"""
    guides = _copy(target)
    a = guides.get(first)
    b = guides.get(second) if second is not None and second != first else None
    if a is None or a.closed:
        return None
    path = a.path
    tolerance = target.spacing()
    if b is None:                                          # 閉じる
        if len(path.nodes) < 3:
            return None
        nodes, segments = list(path.nodes), list(path.segments)
        if np.linalg.norm(np.asarray(nodes[0].position) - np.asarray(nodes[-1].position)) <= tolerance:
            last = segments.pop()                              # 端がほぼ同じ所: 最後の区間が最初の点へ戻る
            nodes.pop()
            segments.append(Segment(last.mode, last.shape, last.vertices))
            if len(nodes) < 3:
                return None
            if last.shape is not None:
                segments[-1].shape = np.vstack([last.shape[:-1], [nodes[0].position]])
        else:
            joint = pm.CURVE if segments[0].mode == pm.CURVE and segments[-1].mode == pm.CURVE else pm.STRAIGHT
            segments.append(Segment(joint))
        joined = GuidePath(nodes, segments, True, path.origin, dict(path.source), False)
        _rebuild(target, joined, [len(segments) - 1] + _neighbors(joined, 0))
        old = guides.detachPartner(a.ident)
        a.path = joined
        if old is not None:
            a.partner = None
            _sync_partner(target, guides, a, create=True)
            if a.partner is not None and a.partner != old:
                guides.renumber(a.partner, old)
        _commit([(target, guides, [a.ident])], undo_name)
        return a.ident
    if b.closed:
        return None
    pa, pb = path, b.path
    ends = [(np.linalg.norm(np.asarray(pa.nodes[ia].position) - np.asarray(pb.nodes[ib].position)), ia, ib)
            for ia in (0, -1) for ib in (0, -1)]
    _distance, ia, ib = min(ends, key=lambda e: e[0])
    if ia == 0:
        pa = _reversed(pa)                                 # a はつなぐ端が終点になるように
    if ib == -1:
        pb = _reversed(pb)                                 # b はつなぐ端が始点になるように
    if np.linalg.norm(np.asarray(pa.nodes[-1].position) - np.asarray(pb.nodes[0].position)) <= tolerance:
        nodes = pa.nodes + pb.nodes[1:]
        segments = pa.segments + pb.segments
        bridge_index = None
    else:
        joint = pm.CURVE if pa.segments[-1].mode == pm.CURVE and pb.segments[0].mode == pm.CURVE else pm.STRAIGHT
        nodes = pa.nodes + pb.nodes
        segments = pa.segments + [Segment(joint)] + pb.segments
        bridge_index = len(pa.segments)
    joined = GuidePath(nodes, segments, False, path.origin, dict(path.source), False)
    rebuild = set(_neighbors(joined, len(pa.nodes) - 1))
    if bridge_index is not None:
        rebuild.add(bridge_index)
    _rebuild(target, joined, rebuild)
    mirrored_pair = a.partner == b.ident
    had = (a.partner is not None or b.partner is not None) and not mirrored_pair
    old = guides.detachPartner(a.ident)
    if not mirrored_pair:
        guides.detachPartner(b.ident)
    guides.remove(b.ident)
    a.path = joined
    a.partner = None
    if had or (not mirrored_pair and target.symmetric()):
        _sync_partner(target, guides, a, create=True)
        if old is not None and a.partner is not None and a.partner != old and not mirrored_pair:
            guides.renumber(a.partner, old)
    _commit([(target, guides, [a.ident])], undo_name)
    return a.ident


def split_guide(target, ident, index, undo_name="線を切り離す"):
    """点 index で線を切り離す。開いた線は 2 本に (端の点では切れない)、閉じた線はそこで開いた線にする。対称の相手も
    作り直す。1 回の Undo。できた線の番号のリストか None。"""
    guides = _copy(target)
    guide = guides.get(ident)
    if guide is None:
        return None
    path = guide.path
    count = len(path.nodes)
    if not 0 <= index < count:
        return None
    old = guides.detachPartner(ident)
    if path.closed:
        order = list(range(index, count)) + list(range(index))
        nodes = [path.nodes[k] for k in order] + [Node(path.nodes[index].position, path.nodes[index].vertex)]
        segments = [path.segments[k] for k in order]
        guide.path = GuidePath(nodes, segments, False, path.origin, _open_source(path), False)
        result = [ident]
    else:
        if index <= 0 or index >= count - 1:
            if old is not None:
                guide.partner = None
                _sync_partner(target, guides, guide, create=True)
            return None
        cut = Node(path.nodes[index].position, path.nodes[index].vertex)
        first = GuidePath(path.nodes[:index + 1], path.segments[:index], False, path.origin, dict(path.source), False)
        second = GuidePath([cut] + path.nodes[index + 1:], path.segments[index:], False, path.origin,
                           dict(path.source), False)
        guide.path = first
        result = [ident, guides.add(Guide(second))]
    if old is not None:
        guide.partner = None
        _sync_partner(target, guides, guide, create=True)
        if guide.partner is not None and guide.partner != old:
            guides.renumber(guide.partner, old)
        for other in result[1:]:
            _sync_partner(target, guides, guides.get(other), create=True)
    _commit([(target, guides, result)], undo_name)
    return result


def _open_source(path):
    """閉じた線を開くときの元の情報 (リングの平面は残す。断面に戻せる)。"""
    return dict(path.source)


def cut_segments(target, ident, removed, undo_name="線を切り離す"):
    """区間 removed (番号のリスト。区間 i は点 i と点 i + 1 の間) を消して、線をいくつかに分ける。閉じた線は、消した
    区間で開いた線になる。点が 1 つだけになった切れ端は捨てる。対称の相手は作り直す。1 回の Undo。
    できた線の番号のリストか None。"""
    guides = _copy(target)
    guide = guides.get(ident)
    removed = sorted(set(int(i) for i in removed))
    if guide is None or not removed:
        return None
    path = guide.path
    count = len(path.segments)
    if any(not 0 <= i < count for i in removed):
        return None
    nodes, segments = list(path.nodes), list(path.segments)
    if path.closed:
        first = removed[0]                                   # 消す区間の次の点から始まる開いた線にする
        order = list(range(first + 1, len(nodes))) + list(range(first + 1))
        nodes = [nodes[k % len(path.nodes)] for k in order]
        segments = [segments[k % count] for k in range(first + 1, first + 1 + count)]
        removed = [(i - first - 1) % count for i in removed[1:]]
        segments = segments[:-1]
    pieces = [([nodes[0]], [])]
    for i, segment in enumerate(segments):
        if i in removed:
            pieces.append(([Node(nodes[i + 1].position, nodes[i + 1].vertex, nodes[i + 1].attach)], []))
        else:
            pieces[-1][0].append(nodes[i + 1])
            pieces[-1][1].append(segment)
    pieces = [piece for piece in pieces if len(piece[0]) >= 2]
    if not pieces:
        return None
    old = guides.detachPartner(ident)
    result = []
    for k, (piece_nodes, piece_segments) in enumerate(pieces):
        piece = GuidePath(piece_nodes, piece_segments, False, path.origin, dict(path.source), False)
        if k == 0:
            guide.path = piece
            result.append(ident)
        else:
            result.append(guides.add(Guide(piece)))
    if old is not None:
        guide.partner = None
        for k, part in enumerate(result):
            _sync_partner(target, guides, guides.get(part), create=True)
            if k == 0 and guide.partner is not None and guide.partner != old:
                guides.renumber(guide.partner, old)
    _commit([(target, guides, result)], undo_name)
    return result


# -- ホイール (閉じたガイド) と、作った道具に戻る ---------------------------------------

def _frame(guide):
    """閉じたガイドを動かす向き: (中心, 法線, 軸)。リングは平面と軸、ほかは線の主成分 (法線 = いちばん散らばりの小さい
    向き、軸 = いちばん大きい向き)。"""
    points = np.asarray(guide.points, dtype=np.float64)
    center = points.mean(axis=0)
    if guide.plane is not None and guide.axis is not None:
        normal = np.asarray(guide.plane[1], dtype=np.float64)
        axis = np.asarray(guide.axis, dtype=np.float64)
    else:
        _u, _s, vt = np.linalg.svd(points - center, full_matrices=False)
        normal, axis = vt[2], vt[0]
    return center, normal / np.linalg.norm(normal), axis / np.linalg.norm(axis)


def adjust_ring(target, guides, ident, shift=0.0, tilt=0.0, rotate_axis=None):
    """guides (写し) の閉じたガイド ident を、向き (_frame の法線) に shift 目盛り (1 目盛り = 点の間隔 x
    SHIFT_SPACINGS) 平行移動し、中心を通る軸のまわりに tilt 度回す。回す軸は rotate_axis (オブジェクト空間の向き。
    ツールはカメラから中心への視線 = 画面の上で回す) か、省くと軸 (手前 / 奥へ傾ける)。
    作ったまま (点を編集していない) のリングは、平面を動かして断面を求め直す (正確な断面)。ほかは点と形を一緒に動かして
    表面に寄せ直す (形を保つ)。対称の相手も作り直す。書かない (write_adjusted で書く)。動かせたら True、動かせない
    (開いた線・メッシュから外れた) なら False。"""
    guide = guides.get(ident)
    if guide is None or not guide.adjustable():
        return False
    center, normal, axis = _frame(guide)
    origin = center
    if guide.plane is not None:
        plane_origin = np.asarray(guide.plane[0], dtype=np.float64)
        origin = center - ((center - plane_origin) @ normal) * normal   # 中心を平面に乗せて、回転の中心にする
    pivot = origin.copy()
    turn = None
    new_normal, new_axis = normal, axis
    if tilt:
        turn = axis if rotate_axis is None else np.asarray(rotate_axis, dtype=np.float64)
        turn = turn / np.linalg.norm(turn)
        new_normal = rotate(normal, turn, tilt)
        new_normal /= np.linalg.norm(new_normal)
        new_axis = rotate(axis, turn, tilt)
        new_axis /= np.linalg.norm(new_axis)
    offset = new_normal * (target.spacing() * SHIFT_SPACINGS * shift) if shift else np.zeros(3)
    size = max(float(np.ptp(np.asarray(guide.points), axis=0).max()), target.spacing())
    if guide.path.origin == pm.ORIGIN_RING and guide.path.pristine and guide.plane is not None:
        ring = _section_ring(target, (origin + offset, new_normal), center + offset, size)
        if ring is None:
            return False
        ring.source["axis"] = list(new_axis)
        guide.path = ring
    else:
        def transform(points):
            moved = np.asarray(points, dtype=np.float64) - pivot
            if turn is not None:
                moved = np.array([rotate(p, turn, tilt) for p in moved])
            return moved + pivot + offset
        moved = _transform_path(target, guides, guide.path, transform, attach_host=lambda host: host)
        if moved is None:
            return False
        line = moved.line()
        if float(np.linalg.norm(line.mean(axis=0) - transform(np.array([center]))[0])) > size:
            return False                                     # メッシュから外れた
        if guide.plane is not None:
            moved.source["plane"] = [list(origin + offset), list(new_normal)]
            moved.source["axis"] = list(new_axis)
        moved.pristine = False
        guide.path = moved
    _sync_partner(target, guides, guide)
    return True


def write_adjusted(target, guides, undo_name="輪切りを動かす"):
    """adjust_ring で変えた guides を書く (1 回の Undo)。"""
    return _commit([(target, guides, [])], undo_name)


def reset_rings(target, idents, undo_name="輪を断面に戻す"):
    """リング idents (平面を持つもの) を、今の平面の断面の輪に戻す (点の編集を捨てる。相手も。1 回の Undo)。
    戻した番号のリスト。"""
    guides = _copy(target)
    done = []
    for ident in idents:
        guide = guides.get(ident)
        if guide is None or guide.kind != RING or guide.plane is None:
            continue
        center = np.asarray(guide.points, dtype=np.float64).mean(axis=0)
        size = float(np.ptp(np.asarray(guide.points), axis=0).max())
        plane = (np.asarray(guide.plane[0]), np.asarray(guide.plane[1]))
        ring = _section_ring(target, plane, center, size)
        if ring is None:
            continue
        if guide.axis is not None:
            ring.source["axis"] = list(guide.axis)
        guide.path = ring
        _sync_partner(target, guides, guide)
        done.append(ident)
    if done:
        _commit([(target, guides, done)], undo_name)
    return done


# -- ペイント (塗った範囲を囲む線) -----------------------------------------------

def region_mirror(target, faces):
    """(対称の相手の塗った面, 対応しなかった面の数)。面は今の対称の面、許容値は設定の許容値。"""
    mirror, _label = target.mirrorPlane()
    return mirror_faces(target.surface.arrays(), faces, mirror, target.vertexTolerance())


def region_faces(target, guide):
    """ペイントのガイドの塗った面 (面ごとに 0 / 1 の配列)。前の版 (頂点ごとの量) は面に直す。"""
    arrays = target.surface.arrays()
    if guide.faces is not None:
        return dense_faces(guide.faces, face_count(arrays))
    weights = guide.path.source.get("weights")
    if weights:
        return faces_from_vertex_weights(arrays, dense_weights(weights, len(arrays.points)))
    return np.zeros(face_count(arrays))


def _region_paths(target, faces, group):
    loops = region_edge_loops(target.surface.arrays(), faces)
    source = {"faces": sparse_faces(faces), "group": group}
    return [_loop_path(target, vertices, closed, pm.ORIGIN_PAINT, dict(source)) for vertices, closed in loops]


def add_region(target, faces, undo_name="ペイントのガイド"):
    """塗った面 faces (面ごとに 0 / 1) を囲む線のガイドにする (囲む線ごとに 1 本。同じ塗りは source の group が同じ。
    対称の相手も。1 回の Undo)。{シェイプ: [番号]}。囲む線が無ければ {}。"""
    guides = _copy(target)
    group = guides._next
    paths = _region_paths(target, np.asarray(faces, dtype=np.float64), group)
    if not paths:
        return {}
    ids = []
    for path in paths:
        ids += _add(target, guides, path)
    return _commit([(target, guides, ids)], undo_name)


def set_region(target, ident, faces, undo_name="ペイントを塗り直す"):
    """ペイントのガイド ident (と同じ塗りの線) を、塗り直した面 faces から作り直す (点の編集は捨てる。相手も)。
    全部消したら消す。最初の線は ident の番号のまま。1 回の Undo。作り直したら True。"""
    guides = _copy(target)
    guide = guides.get(ident)
    if guide is None or guide.kind != REGION:
        return False
    group = guide.group if guide.group is not None else ident
    partner = guide.partner
    for other in [g for g in guides.guides() if g.kind == REGION and (g.group == group or g.ident == ident)]:
        guides.remove(other.ident)
    paths = _region_paths(target, np.asarray(faces, dtype=np.float64), group)
    ids = []
    for k, path in enumerate(paths):
        new = Guide(path, ident if k == 0 else None)
        if k == 0:
            guides.insert(new)
        else:
            guides.add(new)
        created = _sync_partner(target, guides, new, create=partner is not None or None)
        if k == 0 and created is not None and partner is not None and created != partner:
            guides.renumber(created, partner)
        ids.append(new.ident)
    _commit([(target, guides, ids or [ident])], undo_name)
    return True


def line_segment(target, start, end):
    """点 start -> end (オブジェクト空間) の直線を細かく分けて表面に寄せた点の列。"""
    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    count = max(2, int(np.ceil(np.linalg.norm(end - start) / (target.spacing() * 0.5))) + 1)
    line = start + (end - start) * np.linspace(0.0, 1.0, count)[:, None]
    snapped = target.surface.closest(line)
    snapped[0], snapped[-1] = start, end
    return snapped


# -- 消す・探す ---------------------------------------------------------------------

def delete_guide(target, ident, undo_name="ガイドを消す"):
    guides = _copy(target)
    removed = guides.remove(ident)
    if not removed:
        return []
    _commit([(target, guides, removed)], undo_name)
    return removed


def delete_guides(keys, undo_name="ガイドを消す"):
    """[(target, 番号)] をまとめて消す (対称の相手も。全メッシュで 1 回の Undo)。{シェイプ: [消した番号]}。"""
    groups = []
    for target, ident in keys:
        group = next((g for g in groups if g[0] is target), None)
        if group is None:
            group = (target, _copy(target), [])
            groups.append(group)
        group[2].extend(group[1].remove(ident))
    changes = [group for group in groups if group[2]]
    _commit(changes, undo_name)
    return {target.name(): sorted(removed) for target, _guides, removed in changes}


def guides_in_rect(targets, project, rect):
    """画面の矩形 (左, 下, 右, 上) に点が 1 つでも入るガイド [(target, 番号)]。ガイドの点は細かいので点で見る。"""
    left, bottom, right, top = rect
    result = []
    for target in targets:
        for guide, world, _closed in world_guides(target):
            screen = np.asarray(project(world), dtype=np.float64)
            inside = ((screen[:, 0] >= left) & (screen[:, 0] <= right)
                      & (screen[:, 1] >= bottom) & (screen[:, 1] <= top))
            if inside.any() and (target, guide.ident) not in result:
                result.append((target, guide.ident))
    return result


def world_guides(target):
    """[(ガイド, ワールドの点 (n, 3), 閉じているか)]。"""
    return [(guide, target.surface.toWorld(points), closed) for guide in target.guides.guides()
            for points, closed in guide.lines() if len(points)]


def _segment_distance(points, x, y, closed):
    """画面の折れ線 (n, 2) と点 (x, y) の最も近い距離。"""
    if closed and len(points) > 2:
        points = np.vstack([points, points[:1]])
    if len(points) == 1:
        return float(np.hypot(points[0, 0] - x, points[0, 1] - y))
    a, b = points[:-1], points[1:]
    ab = b - a
    length2 = np.maximum((ab * ab).sum(axis=1), 1e-12)
    t = np.clip(((np.array([x, y]) - a) * ab).sum(axis=1) / length2, 0.0, 1.0)
    nearest = a + ab * t[:, None]
    return float(np.hypot(nearest[:, 0] - x, nearest[:, 1] - y).min())


def screen_distance(target, guide, project, x, y):
    """画面の (x, y) から、ガイドを画面に写した線までの距離 (px)。カメラの後ろだけなら無限大。"""
    best = float("inf")
    for points, closed in guide.lines():
        if not len(points):
            continue
        screen = np.asarray(project(target.surface.toWorld(points)), dtype=np.float64)
        screen = screen[np.isfinite(screen).all(axis=1)]
        if len(screen):
            best = min(best, _segment_distance(screen, x, y, closed))
    return best


def pick_guide_line(targets, project, x, y, pixels, kinds=None, exclude=None):
    """画面の (x, y) から pixels 以内でいちばん近いガイドの線: (target, 番号, 0, その線の上の点 (オブジェクト空間。画面で
    いちばん近い所)) か None。kinds を渡すとその種類だけ、exclude ((シェイプ, 番号) の集まり) は除く。"""
    best = None
    for target in targets:
        for guide in target.guides.guides():
            if kinds is not None and guide.kind not in kinds:
                continue
            if exclude is not None and (target.name(), guide.ident) in exclude:
                continue
            for line, (points, closed) in enumerate(guide.lines()):
                if not len(points):
                    continue
                local = np.asarray(points, dtype=np.float64)
                screen = np.asarray(project(target.surface.toWorld(local)), dtype=np.float64)
                distance = _segment_distance(screen, x, y, closed)
                if distance <= pixels and (best is None or distance < best[0]):
                    near = int(np.argmin(np.hypot(screen[:, 0] - x, screen[:, 1] - y)))
                    best = (distance, target, guide.ident, line, local[near])
    return None if best is None else best[1:]


def pick_guide(targets, project, x, y, pixels):
    """画面の (x, y) から pixels 以内でいちばん近いガイドの (target, 番号)。無ければ (None, None)。"""
    best = (None, None, pixels)
    for target in targets:
        for guide, world, closed in world_guides(target):
            screen = np.asarray(project(world), dtype=np.float64)
            distance = _segment_distance(screen, x, y, closed)
            if distance <= best[2]:
                best = (target, guide.ident, distance)
    return best[0], best[1]


def vertex_at(target, guide, fraction):
    """ガイドのシームの上の割合 fraction の頂点 (乗る点の割合から引くとき)。"""
    seam = host_seam(target, guide)
    if seam is None:
        return None
    return vertex_at_fraction(target.surface.arrays(), seam[0], seam[1], fraction)
