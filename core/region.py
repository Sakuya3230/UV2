# -*- coding: utf-8 -*-
"""
ペイント (塗った範囲を囲むガイド) の計算 (Maya に依存しない。numpy。scipy があれば速い)。

    faces = np.zeros(face_count(mesh))                # 面ごとに塗ったか (0 / 1)
    stamp(mesh, faces, center, radius)                # ブラシを 1 回押す (その場で変える。erase=True で消す)
    stamp(mesh, faces, center, radius, hit_face=f)    # サーフェス: 当たった面から表面に沿って radius 以内
    brush_faces(mesh, center, radius, hit_face)       # ブラシの中の面 (押したら塗られる面。下見に使う)
    square_faces(candidates, screen, center, half, front, angle)   # 四角のブラシ: 画面の四角に中心が入る表向きの面
    connected_faces(mesh, start, allowed)            # start の面から、allowed の面だけを通ってつながる面
    face_normals(mesh)                                # 面の法線 (Newell。長さ 1)
    loops = region_loops(mesh, faces)                 # 囲む線 [(点 (n, 3), 閉じているか)]。塗った面の境目のエッジの上
    edge_loops = region_edge_loops(mesh, faces)       # 同じ線を頂点の番号の列で [(頂点の番号 (n,), 閉じているか)]
    mirrored, unmatched = mirror_faces(mesh, faces, plane, tolerance)   # 対称の相手の塗った面
    grow_faces(mesh, faces, d) / shrink_faces(mesh, faces, d)           # 塗った範囲を表面に沿って d だけ広げる / 狭める

**面ごとに塗る**: ブラシの円の中に**中心**が入った面を塗る (Maya のペイント選択の面と同じ考え方)。当たった面は
半径が小さくても必ず塗る。前は円の中の頂点を塗り、面の頂点の平均が 0.5 以上の面を範囲にしていたが、円の端の
頂点 1 つで円の外まで広がる面が入り、円が面にかかっても頂点が入らなければ塗られず、円を見ても結果が読めなかった
(GUI で確認)。
距離: ボリュームは center から面の中心までの 3D の距離。サーフェスは表面に沿った距離 = 当たった面の頂点までは
直線、そこから辺をたどり (dijkstra)、最後に頂点から面の中心までの直線 (面の頂点のうち最も近いもの)。表面に沿った
距離 <= radius なら 3D の距離も <= radius なので、球の中の頂点だけの小さなグラフでたどれば足りる。
囲む線: 塗った面の境目のエッジをつないだ輪。線はエッジの上にあり、そのままシーム (scene.seams が頂点の列を
そのまま道にする) になる。
面: MeshArrays に面の情報 (faceCounts / faceConnects) があればその多角形、無ければ三角形。
"""
import heapq

import numpy as np

from .geometry import polyline_length, reflect

try:
    from scipy.spatial import cKDTree
except Exception:      # scipy が無い・壊れている
    cKDTree = None
try:
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
except Exception:
    csr_matrix = None

__all__ = ["face_count", "face_centers", "face_normals", "square_faces", "connected_faces", "stamp", "brush_faces", "region_loops", "region_edge_loops", "painted_faces",
           "painted_triangles", "faces_from_vertex_weights", "mirror_faces", "grow_faces", "shrink_faces",
           "surface_distance", "sparse_faces", "dense_faces", "dense_weights", "LEVEL"]

LEVEL = 0.5          # 0.5 以上を「塗った」とみなす (前の版の頂点の量から面に直すときも)


# -- 面の情報 (メッシュごとに 1 回作って覚える。MeshArrays は形が変わると作り直される) -----------------------------

def _faces(mesh):
    """(面ごとの頂点の数, 頂点の番号を続けたもの, 角ごとの面の番号, 面の最初の角)。"""
    cached = getattr(mesh, "_region_faces", None)
    if cached is None:
        if mesh.faceCounts is not None:
            counts, connects = mesh.faceCounts, mesh.faceConnects
        else:
            counts = np.full(len(mesh.triangles), 3, dtype=np.int64)
            connects = mesh.triangles.ravel()
        face = np.repeat(np.arange(len(counts)), counts)
        cached = mesh._region_faces = (counts, connects, face, np.cumsum(counts) - counts)
    return cached


def face_count(mesh):
    return len(_faces(mesh)[0])


def face_centers(mesh):
    """面の中心 (頂点の平均) (F, 3)。"""
    centers = getattr(mesh, "_region_centers", None)
    if centers is None:
        counts, connects, face, _starts = _faces(mesh)
        total = np.zeros((len(counts), 3))
        np.add.at(total, face, mesh.points[connects])
        centers = mesh._region_centers = total / np.maximum(counts, 1)[:, None]
    return centers


def face_normals(mesh):
    """面の法線 (F, 3)。多角形は Newell の方法 (角ごとの外積の和)。長さ 1 (潰れた面は 0)。"""
    normals = getattr(mesh, "_region_normals", None)
    if normals is None:
        counts, connects, face, starts = _faces(mesh)
        corner = np.arange(len(connects))
        following = starts[face] + (corner - starts[face] + 1) % counts[face]
        cross = np.cross(mesh.points[connects], mesh.points[connects[following]])
        total = np.zeros((len(counts), 3))
        np.add.at(total, face, cross)
        length = np.linalg.norm(total, axis=1)
        normals = mesh._region_normals = total / np.maximum(length, 1e-30)[:, None]
    return normals


def square_faces(candidates, screen, center, half, front=None, angle=0.0):
    """四角のブラシ: 候補の面 candidates のうち、面の中心の画面の位置 screen ((n, 2)。candidates と同じ順) が、
    画面の四角 (中心 center、半分の幅 half、画面の横から angle (ラジアン) だけ回した向き。0 なら上下左右にそろう) に
    入るもの。front ((n,) の bool) を渡すと、表向き (カメラの方を向く) の面だけ (四角は画面で見た形なので、裏側の面は
    塗らない)。"""
    candidates = np.asarray(candidates, dtype=np.int64)
    screen = np.asarray(screen, dtype=np.float64).reshape(-1, 2)
    dx, dy = screen[:, 0] - center[0], screen[:, 1] - center[1]
    c, s = np.cos(angle), np.sin(angle)
    inside = (np.abs(dx * c + dy * s) <= half) & (np.abs(-dx * s + dy * c) <= half)
    inside &= np.isfinite(screen).all(axis=1)
    if front is not None:
        inside &= np.asarray(front, dtype=bool)
    return candidates[inside]


def connected_faces(mesh, start, allowed):
    """面 start から、allowed (面の番号の並び) の面だけを通って (頂点を共有する面へ) たどり着く面 (start を含む。
    番号の昇順)。四角のブラシのサーフェス: 画面の四角に入る表向きの面のうち、当たった面とつながるものだけを塗る
    (表面に沿った距離で切らないので、カメラに対して傾いた面 (奥行きのある所) も四角の端まで塗れる)。"""
    counts, connects, _face, starts = _faces(mesh)
    indptr, owners = _vertex_faces(mesh)
    mask = np.zeros(len(counts), dtype=bool)
    mask[np.asarray(allowed, dtype=np.int64)] = True
    start = int(start)
    mask[start] = True
    seen = np.zeros(len(counts), dtype=bool)
    seen[start] = True
    face_ptr = np.concatenate([starts, [len(connects)]])
    frontier = np.array([start], dtype=np.int64)
    while len(frontier):
        vertices = np.unique(_gather(face_ptr, connects, frontier)[0])
        near = np.unique(_gather(indptr, owners, vertices)[0])
        near = near[mask[near] & ~seen[near]]
        seen[near] = True
        frontier = near
    return np.flatnonzero(seen)


def _center_tree(mesh):
    tree = getattr(mesh, "_region_center_tree", None)
    if tree is None and cKDTree is not None and face_count(mesh):
        tree = mesh._region_center_tree = cKDTree(face_centers(mesh))
    return tree


def _vertex_tree(mesh):
    tree = getattr(mesh, "_region_tree", None)
    if tree is None and cKDTree is not None and len(mesh.points):
        tree = mesh._region_tree = cKDTree(mesh.points)
    return tree


def _vertex_faces(mesh):
    """頂点ごとの面 (indptr, 面の番号)。頂点 v の面は indptr[v]:indptr[v + 1]。"""
    cached = getattr(mesh, "_region_vertex_faces", None)
    if cached is None:
        _counts, connects, face, _starts = _faces(mesh)
        order = np.argsort(connects, kind="stable")
        indptr = np.concatenate([[0], np.cumsum(np.bincount(connects, minlength=len(mesh.points)))])
        cached = mesh._region_vertex_faces = (indptr, face[order])
    return cached


def _gather(indptr, values, rows):
    """CSR の行 rows の中身をつないだもの (と、それぞれがどの行の何番目か)。"""
    rows = np.asarray(rows, dtype=np.int64)
    starts, sizes = indptr[rows], indptr[rows + 1] - indptr[rows]
    flat = np.arange(int(sizes.sum())) - np.repeat(np.cumsum(sizes) - sizes, sizes) + np.repeat(starts, sizes)
    return values[flat], np.repeat(np.arange(len(rows)), sizes)


def _face_distance(mesh, faces, vertex_distance):
    """面ごとの距離: 面の頂点のうち (頂点までの距離 + 頂点から面の中心までの直線) が最小のもの。"""
    counts, connects, _face, starts = _faces(mesh)
    faces = np.asarray(faces, dtype=np.int64)
    corners, owner = _gather(np.concatenate([starts, [len(connects)]]), np.arange(len(connects)), faces)
    vertices = connects[corners]
    centers = face_centers(mesh)
    through = vertex_distance[vertices] + np.linalg.norm(mesh.points[vertices] - centers[faces[owner]], axis=1)
    result = np.full(len(faces), np.inf)
    np.minimum.at(result, owner, through)
    return result


# -- ブラシ ------------------------------------------------------------------

def brush_faces(mesh, center, radius, hit_face=None):
    """ブラシの中の面 (番号の配列): 中心が半径の中に入った面 (と当たった面)。hit_face が None ならボリューム
    (3D の距離)、当たった面の番号ならサーフェス (表面に沿った距離。すぐ近くでも、つながっていない面・裏側は入らない)。"""
    center = np.asarray(center, dtype=np.float64)
    if not face_count(mesh):
        return np.zeros(0, dtype=np.int64)
    if hit_face is None:
        tree = _center_tree(mesh)
        if tree is not None:
            return np.sort(np.asarray(tree.query_ball_point(center, radius), dtype=np.int64))
        return np.flatnonzero(np.linalg.norm(face_centers(mesh) - center, axis=1) <= radius)
    counts, connects, _face, starts = _faces(mesh)
    hit_face = int(hit_face)
    seeds = connects[starts[hit_face]:starts[hit_face] + counts[hit_face]]
    nodes, distance = _surface_vertex_distance(mesh, center, radius, seeds)
    reached = nodes[distance <= radius]
    vertex_distance = np.full(len(mesh.points), np.inf)
    vertex_distance[nodes] = distance
    indptr, owners = _vertex_faces(mesh)
    candidates = np.union1d(_gather(indptr, owners, reached)[0], [hit_face])
    inside = candidates[_face_distance(mesh, candidates, vertex_distance) <= radius]
    return np.union1d(inside, [hit_face])


def stamp(mesh, faces, center, radius, erase=False, hit_face=None):
    """ブラシを center (オブジェクト空間) に半径 radius で 1 回押す: ブラシの中の面 (brush_faces) を 1 (erase なら 0)
    にする (faces をその場で変える)。ブラシの中の面の数。"""
    index = brush_faces(mesh, center, radius, hit_face)
    if len(index):
        faces[index] = 0.0 if erase else 1.0
    return len(index)


def _ball(mesh, center, radius):
    """center から 3D の距離が radius 以内の頂点 (番号の昇順)。"""
    tree = _vertex_tree(mesh)
    if tree is not None:
        return np.sort(np.asarray(tree.query_ball_point(center, radius), dtype=np.int64))
    return np.flatnonzero(np.linalg.norm(mesh.points - center, axis=1) <= radius)


def _surface_vertex_distance(mesh, center, radius, seeds):
    """(頂点の番号, 表面に沿った距離): 当たった面の頂点 seeds までは center からの直線、その先は辺をたどった長さ。
    表面に沿った距離 <= radius の頂点は 3D の距離も <= radius (道の途中の点も同じ) なので、球の中の頂点だけの
    小さなグラフでたどる (メッシュ全体のグラフを毎回作らない)。radius より遠い頂点は無限大。"""
    seeds = np.unique(np.asarray(seeds, dtype=np.int64))
    nodes = np.union1d(_ball(mesh, center, radius), seeds)   # 当たった面の頂点が半径の外でも、道の出発点にする
    count = len(nodes)
    if not count:
        return nodes, np.zeros(0)
    local = np.full(len(mesh.points), -1, dtype=np.int64)
    local[nodes] = np.arange(count)
    indptr, neighbors, lengths = mesh.adjacency()
    others, rows = _gather(indptr, np.arange(len(neighbors)), nodes)
    cols = local[neighbors[others]]
    keep = cols >= 0
    rows, cols, steps = rows[keep], cols[keep], lengths[others][keep]
    start = np.full(count, np.inf)
    start[local[seeds]] = np.linalg.norm(mesh.points[seeds] - center, axis=1)
    if csr_matrix is not None:
        # 出発点 (番号 count) から seeds へ、center からの直線の長さの辺を足して 1 回の dijkstra にする
        first = local[seeds]
        graph = csr_matrix((np.concatenate([steps, start[first]]),
                            (np.concatenate([rows, np.full(len(first), count)]), np.concatenate([cols, first]))),
                           shape=(count + 1, count + 1))
        return nodes, dijkstra(graph, directed=True, indices=count, limit=radius)[:count]
    distance = start.copy()
    order = np.argsort(rows, kind="stable")
    rows, cols, steps = rows[order], cols[order], steps[order]
    bounds = np.searchsorted(rows, np.arange(count + 1))
    queue = [(float(distance[k]), int(k)) for k in np.flatnonzero(np.isfinite(distance))]
    heapq.heapify(queue)
    while queue:
        d, vertex = heapq.heappop(queue)
        if d > distance[vertex]:
            continue
        for k in range(bounds[vertex], bounds[vertex + 1]):
            other, step = int(cols[k]), d + float(steps[k])
            if step <= radius and step < distance[other]:
                distance[other] = step
                heapq.heappush(queue, (step, other))
    return nodes, distance


def surface_distance(mesh, sources, limit):
    """sources (頂点の番号) から、面の辺をたどった距離 (表面に沿った距離) (V,)。limit より遠い頂点は無限大。
    3D の直線の距離だと、薄い所・近くの別の面 (指の間・裏側) に飛び移った (GUI で確認) ので、辺をたどる。"""
    count = len(mesh.points)
    sources = np.asarray(sources, dtype=np.int64)
    result = np.full(count, np.inf)
    if not len(sources):
        return result
    indptr, neighbors, lengths = mesh.adjacency()
    if csr_matrix is not None:
        graph = csr_matrix((lengths, neighbors, indptr), shape=(count, count))
        return dijkstra(graph, directed=False, indices=sources, min_only=True, limit=limit)
    result[sources] = 0.0
    queue = [(0.0, int(s)) for s in sources]
    heapq.heapify(queue)
    while queue:
        distance, vertex = heapq.heappop(queue)
        if distance > result[vertex]:
            continue
        for k in range(indptr[vertex], indptr[vertex + 1]):
            other, step = int(neighbors[k]), distance + float(lengths[k])
            if step <= limit and step < result[other]:
                result[other] = step
                heapq.heappush(queue, (step, other))
    return result


# -- 広げる / 狭める ------------------------------------------------------------

def _resize(mesh, faces, distance, grow):
    painted = np.asarray(faces) >= LEVEL
    if not painted.any() or painted.all():
        return 0
    counts, connects, face, _starts = _faces(mesh)
    side = painted if grow else ~painted                         # ここから測る (塗った面 / 塗っていない面)
    sources = np.unique(connects[side[face]])
    reach = surface_distance(mesh, sources, distance)
    targets = np.flatnonzero(~side)
    near = targets[_face_distance(mesh, targets, reach) <= distance]
    faces[near] = 1.0 if grow else 0.0
    return len(near)


def grow_faces(mesh, faces, distance):
    """塗った範囲を distance (オブジェクト空間の長さ) だけ広げる: 塗った面から表面に沿って、中心が distance 以内の
    面も塗る (その場で変える)。増えた面の数。ブラシと同じ測り方 (面の中心まで)。
    Maya のフェースの選択の拡大と同じく、つながりをたどる (近くの別の面には移らない)。ただし辺 1 周ずつではなく
    距離で決める (辺 1 周だと、不規則な三角形では長い辺の所だけ大きく広がってゆがんだ。GUI で確認)。"""
    return _resize(mesh, faces, distance, True)


def shrink_faces(mesh, faces, distance):
    """塗った範囲を distance だけ狭める: 塗っていない面から表面に沿って、中心が distance 以内の塗った面を消す
    (その場で変える)。減った面の数。"""
    return _resize(mesh, faces, distance, False)


# -- 囲む線 -----------------------------------------------------------------

def painted_faces(mesh, faces):
    """塗った面の (面ごとの頂点の数, 頂点の番号を続けたもの)。"""
    counts, connects, _face, _starts = _faces(mesh)
    chosen = np.asarray(faces) >= LEVEL
    return counts[chosen], connects[np.repeat(chosen, counts)]


def painted_triangles(mesh, faces):
    """塗った面を分けた三角形の番号 (表示用)。"""
    chosen = np.asarray(faces) >= LEVEL
    if mesh.faceCounts is not None:
        return np.flatnonzero(chosen[mesh.triangleFace])
    return np.flatnonzero(chosen)


def faces_from_vertex_weights(mesh, weights):
    """前の版 (頂点ごとの塗った量) から面ごとに直す: 面の頂点の量の平均が LEVEL 以上の面を 1 (F,)。"""
    counts, connects, face, _starts = _faces(mesh)
    weights = np.asarray(weights, dtype=np.float64)
    if not len(counts):
        return np.zeros(0)
    mean = np.bincount(face, weights[connects], minlength=len(counts)) / np.maximum(counts, 1)
    return (mean >= LEVEL - 1e-9).astype(np.float64)


def region_loops(mesh, faces, spacing=None):
    """塗った範囲を囲む線 [(点 (n, 3), 閉じているか)]。塗った面の境目のエッジの上 (点は頂点の位置)。長い順。
    spacing は前の版の名残り (使わない)。"""
    return [(mesh.points[vertices], closed) for vertices, closed in region_edge_loops(mesh, faces)]


def region_edge_loops(mesh, faces):
    """塗った面の境目のエッジをつないだ線 [(頂点の番号の配列, 閉じているか)]。長い順。
    塗った面の辺を面の向きで (a -> b) 並べ、逆向き (b -> a) が塗った面に無い辺が境目 (メッシュのふちも含む)。
    境目の辺は塗った範囲を同じ側に見て回るので、b から出る境目の辺へ次々たどると輪になる。2 つの塗った面が角だけで
    触れる頂点 (出る辺が 2 本) では、まだ使っていない最初の辺へ進む (輪の分かれ方は変わっても、エッジの集合は同じ)。"""
    if not len(faces) or not np.any(np.asarray(faces) >= LEVEL):
        return []
    counts, connects = painted_faces(mesh, faces)
    if not len(counts):
        return []
    starts = np.cumsum(counts) - counts
    following = np.arange(1, connects.size + 1)
    following[starts + counts - 1] = starts                  # 面の最後の頂点の次は最初の頂点
    heads, tails = connects, connects[following]
    keep = heads != tails
    heads, tails = heads[keep], tails[keep]
    size = np.int64(len(mesh.points))
    forward = heads * size + tails
    boundary = ~np.isin(tails * size + heads, forward)
    heads, tails = heads[boundary].tolist(), tails[boundary].tolist()
    outgoing = {}
    for index, head in enumerate(heads):
        outgoing.setdefault(head, []).append(index)
    used = [False] * len(heads)
    loops = []
    for first in range(len(heads)):
        if used[first]:
            continue
        chain = [heads[first]]
        current = first
        while True:
            used[current] = True
            vertex = tails[current]
            if vertex == chain[0]:
                break
            chain.append(vertex)
            current = next((k for k in outgoing.get(vertex, ()) if not used[k]), None)
            if current is None:
                break
        closed = vertex == chain[0]
        if len(chain) >= 3 or not closed:
            loops.append((np.asarray(chain, dtype=np.int64), closed))
    loops.sort(key=lambda loop: -polyline_length(mesh.points[loop[0]], loop[1]))
    return loops


# -- 対称 -------------------------------------------------------------------

def mirror_faces(mesh, faces, plane, tolerance):
    """(対称の相手の塗った面 (F,), 対応しなかった面の数)。面ごとに、自分の中心を鏡に写した所にいちばん近い面の値を
    拾う (写った先の面の側から拾うので、左右で面の細かさが違っても穴が空かない)。左右対称なメッシュなら、写した所に
    相手の面の中心がちょうどあり、同じ面になる。写した所から tolerance より遠い面 (左右で形が違う所) も近い面で
    写し、その数 (塗った分だけ) を返す (UVPathCut の「反対側が見つからない」のように知らせる)。
    鏡の向こうが塗った範囲から離れている面 (範囲の外接箱 + 塗った面の大きさ) は計算しない。"""
    faces = np.asarray(faces, dtype=np.float64)
    result = np.zeros_like(faces)
    painted = np.flatnonzero(faces >= LEVEL)
    if not len(painted):
        return result, 0
    centers = face_centers(mesh)
    counts, connects, face, _starts = _faces(mesh)
    corner_painted = np.isin(face, painted)
    margin = float(np.linalg.norm(mesh.points[connects[corner_painted]] - centers[face[corner_painted]],
                                  axis=1).max()) * 2.0
    low = centers[painted].min(axis=0) - margin
    high = centers[painted].max(axis=0) + margin
    mirrored = reflect(centers, plane)
    candidates = np.flatnonzero(np.all((mirrored >= low) & (mirrored <= high), axis=1))
    if not len(candidates):
        return result, 0
    tree = _center_tree(mesh)
    if tree is not None:
        distance, nearest = tree.query(mirrored[candidates])
    else:
        gaps = np.linalg.norm(mirrored[candidates][:, None, :] - centers[None, :, :], axis=2)
        nearest = np.argmin(gaps, axis=1)
        distance = gaps[np.arange(len(candidates)), nearest]
    values = faces[nearest]
    result[candidates] = values
    unmatched = int(np.count_nonzero((distance > tolerance) & (values >= LEVEL)))
    return result, unmatched


# -- 保存の形 ---------------------------------------------------------------

def sparse_faces(faces):
    """保存する形: 塗った面の番号のリスト。"""
    return [int(i) for i in np.flatnonzero(np.asarray(faces) >= LEVEL)]


def dense_faces(indices, count):
    """保存した形から (count,) の配列。範囲外の番号は捨てる (メッシュのトポロジーが変わったとき)。"""
    result = np.zeros(count, dtype=np.float64)
    indices = np.asarray([int(i) for i in indices or ()], dtype=np.int64)
    indices = indices[(indices >= 0) & (indices < count)]
    result[indices] = 1.0
    return result


def dense_weights(pairs, count):
    """前の版の保存の形 ([[頂点の番号, 量], ...]) から (count,) の配列。範囲外の番号は捨てる。"""
    result = np.zeros(count, dtype=np.float64)
    for index, value in pairs or ():
        if 0 <= int(index) < count:
            result[int(index)] = float(value)
    return result
