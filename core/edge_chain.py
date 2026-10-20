# -*- coding: utf-8 -*-
"""
エッジの集まりを線にする・UV の境界を探す (Maya に依存しない。numpy)。境界のガイド (EDGE) を作るのに使う。

    chains = edge_chains(pairs)                   # [(頂点の番号の配列, 閉じているか)]。長い順
    pairs = uv_seam_pairs(counts, connects, uv_counts, uv_ids)   # UV の境界のエッジ [(a, b)] (a < b)

edge_chains: エッジ (頂点の組) の集まりを、つながりごとの頂点の列にする。**枝分かれする頂点** (3 本以上の
エッジが集まる所) と端 (1 本だけ) で区切り、どこも 2 本ずつの輪は閉じた線にする。

uv_seam_pairs: 面の辺を面の向きで並べ (半辺)、同じエッジを共有する 2 つの面で、両端の頂点の UV の番号が
違えば UV の境界 (カットされた切れ目)。片方の面にだけ UV があるエッジも境界。メッシュの開いた縁 (面が 1 つ)
と、どちらの面にも UV が無いエッジは入れない。3 つ以上の面が共有するエッジ (多様体でない) も入れない。
"""
import numpy as np

__all__ = ["edge_chains", "uv_seam_pairs", "face_half_edges"]


def face_half_edges(counts, connects):
    """面の辺を面の向きで: (始点, 終点, 面の番号, 角の番号 (始点), 角の番号 (終点))。"""
    counts = np.asarray(counts, dtype=np.int64)
    connects = np.asarray(connects, dtype=np.int64)
    starts = np.cumsum(counts) - counts
    following = np.arange(1, connects.size + 1)
    following[starts + counts - 1] = starts                   # 面の最後の頂点の次は最初の頂点
    face = np.repeat(np.arange(len(counts)), counts)
    corners = np.arange(connects.size)
    return connects, connects[following], face, corners, following


def edge_chains(pairs):
    """エッジ [(a, b)] を、つながりごとの頂点の列 [(頂点の番号の配列, 閉じているか)] にする (長い = 頂点の多い順)。
    枝分かれする頂点 (3 本以上) と端 (1 本) で区切る。どこも 2 本ずつのつながりは輪 (閉じた線)。"""
    pairs = np.asarray(pairs, dtype=np.int64).reshape(-1, 2)
    pairs = pairs[pairs[:, 0] != pairs[:, 1]]
    if not len(pairs):
        return []
    pairs = np.unique(np.sort(pairs, axis=1), axis=0)
    links = {}
    for index, (a, b) in enumerate(pairs.tolist()):
        links.setdefault(a, []).append((b, index))
        links.setdefault(b, []).append((a, index))
    used = [False] * len(pairs)
    chains = []

    def walk(start, first_edge):
        vertices = [start]
        current, edge = start, first_edge
        while True:
            used[edge] = True
            other = next(v for v, e in links[current] if e == edge)
            vertices.append(other)
            if other == start:
                return vertices[:-1], True                    # 一周して戻った: 輪
            if len(links[other]) != 2:
                return vertices, False                        # 端か枝分かれで止まる
            edge = next((e for _v, e in links[other] if not used[e]), None)
            if edge is None:
                return vertices, False
            current = other

    # 端・枝分かれの頂点から出る線を先に (開いた線)、残りは輪
    for vertex in sorted(links):
        if len(links[vertex]) == 2:
            continue
        for _other, edge in links[vertex]:
            if not used[edge]:
                vertices, closed = walk(vertex, edge)
                chains.append((np.asarray(vertices, dtype=np.int64), closed))
    for vertex in sorted(links):
        for _other, edge in links[vertex]:
            if not used[edge]:
                vertices, closed = walk(vertex, edge)
                chains.append((np.asarray(vertices, dtype=np.int64), closed))
    chains.sort(key=lambda chain: -len(chain[0]))
    return chains


def uv_seam_pairs(counts, connects, uv_counts, uv_ids):
    """UV の境界のエッジ (a < b の (n, 2))。counts / connects は面ごとの頂点 (MFnMesh.getVertices の形)、
    uv_counts / uv_ids は面ごとの UV の番号 (MFnMesh.getAssignedUVs の形。UV の無い面は数 0)。"""
    counts = np.asarray(counts, dtype=np.int64)
    uv_counts = np.asarray(uv_counts, dtype=np.int64)
    uv_ids = np.asarray(uv_ids, dtype=np.int64)
    heads, tails, _face, corners, following = face_half_edges(counts, connects)
    if not len(heads):
        return np.zeros((0, 2), dtype=np.int64)
    has = uv_counts > 0
    if np.all(uv_counts[has] == counts[has]):                # ふつう: UV のある面は頂点と同じ数の UV
        corner_uv = np.full(len(heads), -1, dtype=np.int64)
        corner_uv[np.repeat(has, counts)] = uv_ids
    else:
        corner_uv = _mapped_uvs(counts, uv_counts, uv_ids)
    head_uv, tail_uv = corner_uv[corners], corner_uv[following]
    low, high = np.minimum(heads, tails), np.maximum(heads, tails)
    low_uv = np.where(heads <= tails, head_uv, tail_uv)       # 小さい番号の頂点の UV
    high_uv = np.where(heads <= tails, tail_uv, head_uv)
    keep = low != high
    low, high, low_uv, high_uv = low[keep], high[keep], low_uv[keep], high_uv[keep]
    size = int(max(low.max(), high.max())) + 1
    key = low * size + high
    order = np.argsort(key, kind="stable")
    key, low, high, low_uv, high_uv = key[order], low[order], high[order], low_uv[order], high_uv[order]
    unique, first, number = np.unique(key, return_index=True, return_counts=True)
    shared = first[number == 2]                               # 2 つの面が共有するエッジ (縁・多様体でないものは除く)
    a, b = shared, shared + 1
    either = (low_uv[a] >= 0) | (low_uv[b] >= 0)              # どちらかの面に UV がある
    differ = (low_uv[a] != low_uv[b]) | (high_uv[a] != high_uv[b])
    seam = shared[either & differ]
    return np.stack([low[seam], high[seam]], axis=1) if len(seam) else np.zeros((0, 2), dtype=np.int64)


def _mapped_uvs(counts, uv_counts, uv_ids):
    """角ごとの UV の番号 (UV の数が頂点の数と合わない面は -1)。uv_ids は UV のある面の分だけ続いている。"""
    result = np.full(int(counts.sum()), -1, dtype=np.int64)
    corner = 0
    position = 0
    for count, uv_count in zip(counts.tolist(), uv_counts.tolist()):
        if uv_count == count and count > 0:
            result[corner:corner + count] = uv_ids[position:position + count]
        position += uv_count
        corner += count
    return result
