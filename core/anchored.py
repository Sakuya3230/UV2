# -*- coding: utf-8 -*-
"""
置いた点 (anchors) を持つ補助線 (ライン) の、点と点の間の区間を扱う (Maya に依存しない。numpy)。

    segments = split_segments(points, anchors, closed)   # 区間ごとの点の列 (両端の置いた点を含む)
    points = join_segments(segments, closed)             # つなぎ直す (つなぎ目は 1 回だけ)
    i = anchor_insert_index(points, anchors, point, closed)   # 線の上の point を、置いた点の何番目に入れるか

ラインの区間は、描いたときの視点で画面の直線を表面に落としたもの (作り直すと形が変わる)。点を編集するときは、
変わった区間だけを作り直し、ほかの区間は描いたときの点の列のまま残す (scene.edit の move_line_point など)。
置いた点は線の点の列の上にある (描いたときに当てた点そのもの) ので、点の列の中のいちばん近い点で区切る
(前の置いた点より後ろだけを探す)。閉じた線は、最初の置いた点が先頭になるよう点の列を回してから区切る。
"""
import numpy as np

__all__ = ["anchor_indices", "split_segments", "join_segments", "anchor_insert_index"]


def anchor_indices(points, anchors):
    """置いた点ごとの、点の列の中の番号 (増えていく順)。"""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    result = []
    start = 0
    for anchor in np.asarray(anchors, dtype=np.float64).reshape(-1, 3):
        distance = np.linalg.norm(points[start:] - anchor, axis=1)
        index = start + int(np.argmin(distance))
        result.append(index)
        start = index
    return result


def split_segments(points, anchors, closed=False):
    """区間ごとの点の列のリスト。開いた線は len(anchors) - 1 個、閉じた線は len(anchors) 個 (最後は最後の点から
    最初の点へ)。区間は両端の置いた点を含み、端は置いた点そのものにする。"""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    anchors = np.asarray(anchors, dtype=np.float64).reshape(-1, 3)
    if closed:
        first = int(np.argmin(np.linalg.norm(points - anchors[0], axis=1)))
        points = np.roll(points, -first, axis=0)
    index = anchor_indices(points, anchors)
    segments = []
    for i in range(len(anchors) - 1):
        piece = points[index[i]:index[i + 1] + 1].copy()
        if len(piece) < 2:
            piece = np.vstack([anchors[i], anchors[i + 1]])
        piece[0], piece[-1] = anchors[i], anchors[i + 1]
        segments.append(piece)
    if closed:
        piece = np.vstack([points[index[-1]:], points[:1]])
        if len(piece) < 2:
            piece = np.vstack([anchors[-1], anchors[0]])
        piece[0], piece[-1] = anchors[-1], anchors[0]
        segments.append(piece)
    return segments


def join_segments(segments, closed=False):
    """区間をつないだ点の列 (つなぎ目の点は 1 回だけ。閉じた線は最初の点を最後に繰り返さない)。"""
    parts = [np.asarray(segments[0], dtype=np.float64)]
    parts += [np.asarray(segment, dtype=np.float64)[1:] for segment in segments[1:]]
    joined = np.vstack(parts)
    if closed and len(joined) > 2:
        joined = joined[:-1]
    return joined


def anchor_insert_index(points, anchors, point, closed=False):
    """線の上の point (点の列のどれかに近い点) を置いた点に足すときの位置 (anchors.insert の番号)。"""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if closed:
        first = int(np.argmin(np.linalg.norm(points - np.asarray(anchors[0]), axis=1)))
        points = np.roll(points, -first, axis=0)
    index = anchor_indices(points, anchors)
    where = int(np.argmin(np.linalg.norm(points - np.asarray(point, dtype=np.float64), axis=1)))
    position = len(anchors) if closed else len(anchors) - 1
    for i, anchor_index in enumerate(index):
        if where <= anchor_index:
            position = i
            break
    return max(1, position)
