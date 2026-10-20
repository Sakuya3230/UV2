# -*- coding: utf-8 -*-
"""
メッシュの形を numpy の配列で持つ (Maya に依存しない)。

    mesh = MeshArrays.fromPolygons(points, face_counts, face_connects)
    mesh.points        # (V, 3) オブジェクト空間の頂点
    mesh.triangles     # (T, 3) 面を扇形に分けた三角形の頂点の番号 (断面の計算に使う)
    mesh.triangleFace  # (T,) 三角形が属する面の番号
    mesh.edges()       # (E, 2) 本物のエッジ (面の辺。小さい番号が先)。三角形に分けた対角線は入らない
    mesh.adjacency()   # (indptr, neighbors, lengths): 頂点 v の隣は neighbors[indptr[v]:indptr[v + 1]]
    mesh.medianEdge()  # エッジの長さの中央値 (ガイドをエッジにするときの尺度)
    mesh.size()        # 外接箱の対角線の長さ (許容値などの尺度)

ガイドはエッジを使わないので、断面は面を三角形にして求める (四角形・多角形・デシメートされた三角形の
メッシュで同じに扱える)。凹んだ多角形は扇形の三角形が外へはみ出すことがあるが、断面の線の形が
少し変わるだけ (ガイドはざっくりした線なので構わない)。
ガイドをエッジにする (段階 3) ときは、三角形の対角線を通らないよう、面の辺だけでたどる (edges / adjacency)。
"""
import numpy as np

__all__ = ["MeshArrays"]


class MeshArrays(object):
    def __init__(self, points, triangles, triangle_face, face_counts=None, face_connects=None):
        self.points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        self.triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
        self.triangleFace = np.asarray(triangle_face, dtype=np.int64)
        self.faceCounts = None if face_counts is None else np.asarray(face_counts, dtype=np.int64)
        self.faceConnects = None if face_connects is None else np.asarray(face_connects, dtype=np.int64)
        self._edges = None
        self._adjacency = None

    @classmethod
    def fromPolygons(cls, points, face_counts, face_connects):
        """MFnMesh.getVertices の形 (面ごとの頂点の数, 頂点の番号を続けたもの) から作る。"""
        counts = np.asarray(face_counts, dtype=np.int64)
        connects = np.asarray(face_connects, dtype=np.int64)
        starts = np.cumsum(counts) - counts
        per_face = np.clip(counts - 2, 0, None)
        total = int(per_face.sum())
        face = np.repeat(np.arange(counts.size), per_face)
        local = np.arange(total) - np.repeat(np.cumsum(per_face) - per_face, per_face) + 1
        first = starts[face]
        corners = np.stack([first, first + local, first + local + 1], axis=1) if total else np.zeros((0, 3), np.int64)
        triangles = connects[corners] if total else np.zeros((0, 3), np.int64)
        return cls(points, triangles, face, counts, connects)

    def size(self):
        if not len(self.points):
            return 0.0
        return float(np.linalg.norm(self.points.max(axis=0) - self.points.min(axis=0)))

    def edges(self):
        """本物のエッジ (面の隣り合う頂点の組。重複なし。小さい番号が先)。"""
        if self._edges is None:
            if self.faceCounts is None:
                tri = self.triangles
                pairs = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
            else:
                counts, connects = self.faceCounts, self.faceConnects
                starts = np.cumsum(counts) - counts
                following = np.arange(1, connects.size + 1)
                following[starts + counts - 1] = starts               # 面の最後の頂点の次は最初の頂点
                pairs = np.stack([connects, connects[following]], axis=1)
            pairs = np.sort(pairs, axis=1)
            pairs = pairs[pairs[:, 0] != pairs[:, 1]]
            self._edges = np.unique(pairs, axis=0) if len(pairs) else np.zeros((0, 2), np.int64)
        return self._edges

    def adjacency(self):
        """(indptr, neighbors, lengths)。頂点 v の隣の頂点とエッジの長さは indptr[v]:indptr[v + 1] の範囲。"""
        if self._adjacency is None:
            edges = self.edges()
            both = np.concatenate([edges, edges[:, ::-1]])
            order = np.argsort(both[:, 0], kind="stable")
            both = both[order]
            counts = np.bincount(both[:, 0], minlength=len(self.points))
            indptr = np.concatenate([[0], np.cumsum(counts)])
            lengths = np.linalg.norm(self.points[both[:, 1]] - self.points[both[:, 0]], axis=1)
            self._adjacency = (indptr, both[:, 1], lengths)
        return self._adjacency

    def medianEdge(self):
        edges = self.edges()
        if not len(edges):
            return 0.0
        return float(np.median(np.linalg.norm(self.points[edges[:, 1]] - self.points[edges[:, 0]], axis=1)))
