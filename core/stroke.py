# -*- coding: utf-8 -*-
"""
補助線: 画面に描いた線を表面に落とした点を、ガイドの折れ線にする (Maya に依存しない。numpy)。

    runs = surface_runs(hits)                  # hits = 描いた線の点ごとの表面の点 (外れたら None)
    lines = [resample(run, spacing) for run in runs]

描いた線がメッシュの外を通る (表面に当たらない) 所で切れ、別の線になる。点が 2 つに満たない切れ端は捨てる。
画面の線は数 px おきに取り、表面に落としてから長さで置き直す (近くと遠くで点の間隔を揃えるため)。

描く手助け (画面の 2D):
    brush = LazyBrush(start, radius)   # レイジーマウス: カーソルとペン先をひも (長さ radius) でつなぐ
    brush.follow(cursor)           # ひもが張ったときだけペン先が動く。動いたら新しい位置、動かなければ None
    snap_angle(start, end, 15)     # 線の向きを 15 度刻みにそろえた終点 (長さはそのまま)
    segment_points(a, b, spacing)  # 画面の直線を spacing px おきの点に (折れ線の区間を表面に落とすため)
"""
import math

import numpy as np

from .geometry import resample

__all__ = ["surface_runs", "line_points", "LazyBrush", "snap_angle", "segment_points"]


def surface_runs(hits, minimum=2):
    """点のリスト (表面に当たらなければ None) を、続いて当たった区間の (n, 3) の配列のリストにする。"""
    runs = []
    current = []
    for hit in list(hits) + [None]:
        if hit is None:
            if len(current) >= minimum:
                runs.append(np.asarray(current, dtype=np.float64))
            current = []
        else:
            current.append(tuple(hit))
    return runs


def line_points(hits, spacing):
    """表面に当たった区間ごとに、spacing の間隔に置き直した点の配列のリスト。"""
    return [resample(run, spacing) for run in surface_runs(hits)]


class LazyBrush(object):
    """レイジーマウス: ペン先は、カーソルがひもの長さ radius より離れたときだけ、ひもが張る分だけ追う
    (手ぶれの小さな揺れは、ひものたるみに吸われて線に出ない)。"""

    def __init__(self, start, radius):
        self.position = (float(start[0]), float(start[1]))
        self.radius = float(radius)

    def follow(self, cursor):
        dx = cursor[0] - self.position[0]
        dy = cursor[1] - self.position[1]
        distance = math.hypot(dx, dy)
        if distance <= self.radius:
            return None
        k = (distance - self.radius) / distance
        self.position = (self.position[0] + dx * k, self.position[1] + dy * k)
        return self.position


def snap_angle(start, end, degrees):
    """start -> end の向きを degrees 刻みにそろえた終点 (長さはそのまま)。"""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0.0 or degrees <= 0.0:
        return (float(end[0]), float(end[1]))
    step = math.radians(degrees)
    angle = round(math.atan2(dy, dx) / step) * step
    return (start[0] + length * math.cos(angle), start[1] + length * math.sin(angle))


def segment_points(a, b, spacing):
    """画面の直線 a -> b を、spacing ほどの間隔の点にする (a は含まず、b は含む)。"""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    count = max(int(math.ceil(length / max(spacing, 1e-9))), 1)
    return [(a[0] + (b[0] - a[0]) * i / count, a[1] + (b[1] - a[1]) * i / count) for i in range(1, count + 1)]
