# -*- coding: utf-8 -*-
"""
谷 (くぼみ) を通る道の重み (Maya に依存しない。numpy)。つなぎ線の通り方「谷」に使う (core.bridge)。

    c = vertex_concavity(mesh)                 # 頂点ごとのくぼみ (-1 = 山 〜 0 = 平ら 〜 1 = 谷)
    weights = valley_weights(mesh, strength)   # MeshArrays.adjacency() の隣ごとの道の重み

くぼみの測り方:
1. 面の辺を共有する 2 つの面ごとに、2 つの面の法線のなす角 (折れの角度。0 = 平ら)。符号は、相手の面の中心が自分の面の
   表側にあれば谷 (内側に折れている) で正、裏側にあれば山で負
2. 頂点ごとに、つながるエッジの角度を長さの重みで平均する
3. SMOOTH_ITERATIONS 回、隣の頂点との平均で半分ずつならす (スカルプトのノイズ・デシメートした三角形のガタつきで、
   小さな谷に引っ張られて線がジグザグにならないように)
4. くぼみの大きさの NORMAL_PERCENTILE パーセンタイルで割って -1〜1 に (メッシュの細かさ・形によらず同じ強さで効く)
道の重み = エッジの長さ x (1 + 強さ x (1 - くぼみ))。両端の頂点のくぼみの平均で、谷 (1) は長さそのまま、平ら (0) は
1 + 強さ 倍、山 (-1) は 1 + 2 x 強さ 倍。強さ 0 なら長さだけ (最短と同じ)。
面は MeshArrays に面の情報 (faceCounts / faceConnects) があればその多角形 (四角形の対角線は谷にも山にもならない)、
無ければ三角形。
"""
import numpy as np

__all__ = ["vertex_concavity", "valley_weights", "SMOOTH_ITERATIONS", "NORMAL_PERCENTILE", "DEFAULT_STRENGTH"]

SMOOTH_ITERATIONS = 4
NORMAL_PERCENTILE = 90.0
DEFAULT_STRENGTH = 3.0


def _faces(mesh):
    if mesh.faceCounts is not None:
        return np.asarray(mesh.faceCounts, dtype=np.int64), np.asarray(mesh.faceConnects, dtype=np.int64)
    return np.full(len(mesh.triangles), 3, dtype=np.int64), mesh.triangles.ravel()


def vertex_concavity(mesh, iterations=SMOOTH_ITERATIONS):
    """頂点ごとのくぼみ (V,)。-1 (山) 〜 1 (谷)。メッシュに覚えておく (MeshArrays は形が変わると作り直される)。"""
    cache = getattr(mesh, "_valley_concavity", None)
    if cache is not None and cache[0] == iterations:
        return cache[1]
    points = mesh.points
    count = len(points)
    counts, connects = _faces(mesh)
    result = np.zeros(count)
    if not len(counts):
        mesh._valley_concavity = (iterations, result)
        return result
    starts = np.cumsum(counts) - counts
    face = np.repeat(np.arange(len(counts)), counts)
    following = np.arange(1, connects.size + 1)
    following[starts + counts - 1] = starts
    heads, tails = connects, connects[following]
    # 面の法線 (Newell。多角形でも向きが安定) と中心
    p, q = points[heads], points[tails]
    cross = np.stack([(p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2]),
                      (p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0]),
                      (p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1])], axis=1)
    normals = np.zeros((len(counts), 3))
    np.add.at(normals, face, cross)
    normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-30)[:, None]
    centers = np.zeros((len(counts), 3))
    np.add.at(centers, face, points[connects])
    centers /= np.maximum(counts, 1)[:, None]
    # 同じエッジを共有する 2 つの面
    low, high = np.minimum(heads, tails), np.maximum(heads, tails)
    keep = low != high
    low, high, owner = low[keep], high[keep], face[keep]
    key = low * np.int64(count) + high
    order = np.argsort(key, kind="stable")
    key, low, high, owner = key[order], low[order], high[order], owner[order]
    _unique, first, number = np.unique(key, return_index=True, return_counts=True)
    shared = first[number == 2]
    a, b = owner[shared], owner[shared + 1]
    angle = np.arccos(np.clip((normals[a] * normals[b]).sum(axis=1), -1.0, 1.0))
    concave = ((centers[b] - centers[a]) * normals[a]).sum(axis=1) > 0.0
    signed = np.where(concave, angle, -angle)
    length = np.linalg.norm(points[high[shared]] - points[low[shared]], axis=1)
    total = np.zeros(count)
    weight = np.zeros(count)
    for ends in (low[shared], high[shared]):
        np.add.at(total, ends, signed * length)
        np.add.at(weight, ends, length)
    values = np.where(weight > 0, total / np.maximum(weight, 1e-30), 0.0)
    # ならす
    edges = mesh.edges()
    if len(edges):
        degree = np.bincount(edges.ravel(), minlength=count).astype(np.float64)
        for _ in range(iterations):
            near = np.zeros(count)
            np.add.at(near, edges[:, 0], values[edges[:, 1]])
            np.add.at(near, edges[:, 1], values[edges[:, 0]])
            values = np.where(degree > 0, 0.5 * values + 0.5 * near / np.maximum(degree, 1.0), values)
    scale = float(np.percentile(np.abs(values), NORMAL_PERCENTILE)) if count else 0.0
    result = np.clip(values / scale, -1.0, 1.0) if scale > 1e-12 else np.zeros(count)
    mesh._valley_concavity = (iterations, result)
    return result


def valley_weights(mesh, strength=DEFAULT_STRENGTH):
    """MeshArrays.adjacency() の隣ごとの道の重み (lengths と同じ並び)。谷ほど安い。メッシュに覚えておく。"""
    strength = max(float(strength), 0.0)
    cache = getattr(mesh, "_valley_weights", None)
    if cache is not None and cache[0] == strength:
        return cache[1]
    indptr, neighbors, lengths = mesh.adjacency()
    concavity = vertex_concavity(mesh)
    rows = np.repeat(np.arange(len(indptr) - 1), np.diff(indptr))
    edge = 0.5 * (concavity[rows] + concavity[neighbors])
    weights = lengths * (1.0 + strength * (1.0 - edge))
    mesh._valley_weights = (strength, weights)
    return weights
