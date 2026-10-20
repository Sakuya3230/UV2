# -*- coding: utf-8 -*-
"""
ガイドの計算で使う小さな幾何 (Maya に依存しない。numpy)。

    plane_from_rays((s0, r0), (s1, r1))   # 線の両端の視線 2 本を含む平面 (点, 単位の法線)
    reflect(points, plane)                # 点 (n, 3) を平面で鏡に写す
    polyline_length(points, closed)
    resample(points, spacing, closed)     # 折れ線を、ほぼ等しい間隔の点に置き直す
    mean_nearest_distance(a, b)           # a の各点から b の最も近い点までの距離の平均
    rotate(vector, axis, degrees)         # ベクトルを軸のまわりに回す (右手系)
    reflect_vector(vector, normal)        # 向き (法線・軸) を鏡に写す (位置は動かさない)

plane_from_rays は UVPathCut.core.section と同じ式 (ここに写して、パッケージを独立させる):
視線 2 本 (始点 s・向き r) は s0・s0 + r0・s1 + r1 を通る平面に乗る。画面では、この平面の上の点は
すべて描いた線の延長の上に写る (透視でも平行投影でも)。
"""
import numpy as np

__all__ = ["plane_from_rays", "reflect", "polyline_length", "resample", "mean_nearest_distance", "rotate",
           "reflect_vector"]


def plane_from_rays(ray0, ray1):
    """視線 2 本 ((始点, 向き), (始点, 向き)) を含む平面 (点, 単位の法線)。決まらなければ None。"""
    (s0, r0), (s1, r1) = ray0, ray1
    s0 = np.asarray(s0, dtype=np.float64)
    a = np.asarray(r0, dtype=np.float64)
    b = np.asarray(s1, dtype=np.float64) + np.asarray(r1, dtype=np.float64) - s0
    normal = np.cross(a, b)
    length = float(np.linalg.norm(normal))
    if length < 1e-12:
        return None   # 線が短すぎる・視線と平行
    return s0, normal / length


def reflect(points, plane):
    """点 (n, 3) を平面 (点, 単位の法線) で鏡に写す。"""
    points = np.asarray(points, dtype=np.float64)
    origin, normal = plane
    distance = (points - origin) @ normal
    return points - 2.0 * distance[:, None] * normal


def reflect_vector(vector, normal):
    vector = np.asarray(vector, dtype=np.float64)
    normal = np.asarray(normal, dtype=np.float64)
    return vector - 2.0 * (vector @ normal) * normal


def rotate(vector, axis, degrees):
    """vector を単位ベクトル axis のまわりに degrees 回す (ロドリゲスの式)。"""
    vector = np.asarray(vector, dtype=np.float64)
    axis = np.asarray(axis, dtype=np.float64)
    angle = np.radians(degrees)
    return (vector * np.cos(angle) + np.cross(axis, vector) * np.sin(angle)
            + axis * (axis @ vector) * (1.0 - np.cos(angle)))


def polyline_length(points, closed=False):
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 2:
        return 0.0
    if closed:
        points = np.vstack([points, points[:1]])
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def resample(points, spacing, closed=False):
    """折れ線を spacing (長さ) ほどの等しい間隔の点に置き直す。端 (開いた線) は残す。"""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 2 or spacing <= 0.0:
        return points.copy()
    path = np.vstack([points, points[:1]]) if closed else points
    steps = np.linalg.norm(np.diff(path, axis=0), axis=1)
    keep = np.r_[True, steps > 0.0]             # 同じ点が続いたら 1 つにする
    path = path[keep]
    steps = steps[steps > 0.0]
    total = float(steps.sum())
    if total <= 0.0:
        return points[:1].copy()
    count = max(int(round(total / spacing)), 3 if closed else 1)
    along = np.r_[0.0, np.cumsum(steps)]
    targets = np.linspace(0.0, total, count + 1)
    if closed:
        targets = targets[:-1]                  # 始めと同じ点は除く
    result = np.empty((targets.size, points.shape[1]))
    for axis in range(points.shape[1]):
        result[:, axis] = np.interp(targets, along, path[:, axis])
    return result


def mean_nearest_distance(a, b, chunk=2048):
    """a (n, 3) の各点から b (m, 3) の最も近い点までの距離の平均 (総当たり。ガイドの点の数ほどなら十分速い)。"""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if not len(a) or not len(b):
        return float("inf")
    nearest = np.empty(len(a))
    for start in range(0, len(a), chunk):
        part = a[start:start + chunk]
        squared = ((part[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
        nearest[start:start + chunk] = np.sqrt(squared.min(axis=1))
    return float(nearest.mean())
