# -*- coding: utf-8 -*-
"""
Maya のメッシュとガイドの計算をつなぐ。

    surface = Surface(path)                 # メッシュのシェイプの MDagPath
    surface.arrays()                        # MeshArrays (オブジェクト空間。形が変わったら作り直す)
    surface.raycast(origins, directions)    # ワールドの視線ごとに、表面に当たった点 (オブジェクト空間) か None
    surface.closest(points)                 # オブジェクト空間の点を、表面の最も近い点に寄せる
    surface.normalAt(point)                 # オブジェクト空間の点のいちばん近い表面の法線 (オブジェクト空間)
    surface.toObject(points) / toWorld(points)

ガイドはオブジェクト空間で持つ (メッシュを動かしてもガイドがついてくる)。視線はワールドなので、
当てるときに変換する。
表面に当てる: MFnMesh.closestIntersection (加速の格子 MMeshIsectAccelParams を使い回す)。
寄せる: MMeshIntersector (単位行列で作り、オブジェクト空間のまま問い合わせる)。対称の相手 (鏡に写した線) を
表面に乗せるのに使う。
"""
import numpy as np

import maya.api.OpenMaya as om

from ..core.mesh_arrays import MeshArrays

__all__ = ["Surface", "mesh_path"]

RAY_LENGTH = 1.0e7


def mesh_path(name):
    """名前 (Transform かシェイプ) からメッシュのシェイプの MDagPath。"""
    selection = om.MSelectionList()
    selection.add(name)
    path = selection.getDagPath(0)
    if path.apiType() != om.MFn.kMesh:
        path.extendToShape()
    if path.apiType() != om.MFn.kMesh:
        raise ValueError("メッシュではありません: {}".format(name))
    return path


class Surface(object):
    def __init__(self, path):
        self.path = om.MDagPath(path)
        self._fn = None
        self._arrays = None
        self._accel = None
        self._intersector = None

    def fn(self):
        if self._fn is None:
            self._fn = om.MFnMesh(self.path)
        return self._fn

    def invalidate(self):
        """形が変わった: 配列・加速の構造を作り直す。"""
        self._fn = None
        self._arrays = None
        self._accel = None
        self._intersector = None

    def arrays(self):
        if self._arrays is None:
            fn = self.fn()
            points = np.array(fn.getPoints(om.MSpace.kObject), dtype=np.float64)[:, :3]
            counts, connects = fn.getVertices()
            self._arrays = MeshArrays.fromPolygons(points, counts, connects)
        return self._arrays

    def size(self):
        return self.arrays().size()

    # 座標 ------------------------------------------------------------------

    def _matrix(self, inverse=False):
        matrix = self.path.inclusiveMatrixInverse() if inverse else self.path.inclusiveMatrix()
        return np.array(list(matrix), dtype=np.float64).reshape(4, 4)

    def toObject(self, points):
        points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        homogeneous = np.c_[points, np.ones(len(points))]
        return (homogeneous @ self._matrix(inverse=True))[:, :3]     # Maya の行列は行ベクトル (p · M)

    def toWorld(self, points):
        points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        homogeneous = np.c_[points, np.ones(len(points))]
        return (homogeneous @ self._matrix())[:, :3]

    # 当てる・寄せる --------------------------------------------------------

    def raycast(self, origins, directions):
        """ワールドの視線 (始点, 向き) ごとに、表面に当たった最も近い点 (オブジェクト空間) か None。"""
        fn = self.fn()
        if self._accel is None:
            self._accel = fn.autoUniformGridParams()
        hits = []
        for origin, direction in zip(origins, directions):
            result = fn.closestIntersection(om.MFloatPoint(*origin), om.MFloatVector(*direction),
                                            om.MSpace.kWorld, RAY_LENGTH, False, accelParams=self._accel)
            if result is None:              # 当たらないと None (実機で確認)
                hits.append(None)
                continue
            point = result[0]
            hits.append((point.x, point.y, point.z))
        world = [h for h in hits if h is not None]
        if not world:
            return hits
        local = iter(self.toObject(world).tolist())
        return [None if h is None else tuple(next(local)) for h in hits]

    def normalAt(self, point):
        """オブジェクト空間の点のいちばん近い表面の法線 (オブジェクト空間。長さ 1)。"""
        self.closest(np.zeros((0, 3)))
        on_mesh = self._intersector.getClosestPoint(om.MPoint(*np.asarray(point, dtype=np.float64)))
        normal = on_mesh.normal
        vector = np.array([normal.x, normal.y, normal.z])
        return vector / max(np.linalg.norm(vector), 1e-12)

    def faceAt(self, point):
        """オブジェクト空間の点のいちばん近い面の番号 (ブラシの当たった面。サーフェスのブラシの出発点)。"""
        self.closest(np.zeros((0, 3)))
        return int(self._intersector.getClosestPoint(om.MPoint(*np.asarray(point, dtype=np.float64))).face)

    def closest(self, points):
        """オブジェクト空間の点 (n, 3) を、表面の最も近い点 (オブジェクト空間) に寄せる。"""
        if self._intersector is None:
            self._intersector = om.MMeshIntersector()
            self._intersector.create(self.path.node(), om.MMatrix())
        result = np.empty((len(points), 3))
        for index, point in enumerate(np.asarray(points, dtype=np.float64)):
            on_mesh = self._intersector.getClosestPoint(om.MPoint(*point))
            near = on_mesh.point
            result[index] = (near.x, near.y, near.z)
        return result
