# -*- coding: utf-8 -*-
"""
ガイドから求めたシーム (エッジの道) を覚えておき、UV をカットする・エッジを選ぶ。段階 3。

    book = SeamBook()
    book.paths(target)            # [(ガイド, EdgePath か None)]。ガイドの中身ごとに覚えておく
    book.edgeIds(target)          # シームの Maya のエッジの番号 (並べ替え済み)
    book.pairs(target)            # シームのエッジ [(a, b)] (頂点の番号。並べ替え済み)
    book.signature(target)        # シームが変わったかを見分ける目印 (チャートを調べ直すかに使う)
    cut_seams(targets, book)      # UV をカット (全メッシュで 1 回の Undo)。{シェイプ: エッジの数}
    select_seams(targets, book)   # シームのエッジを選ぶ

ペイントの囲む線は塗った面の境目のエッジの上にあるので、頂点の列をそのまま道にする (core.edge_path.vertex_path。
頂点の上にない前の版の線は、ほかのガイドと同じく最短パスで求める)。
ガイドが変わらなければ道も変わらないので、ガイドの種類・閉じているか・点の列を鍵にして覚える
(メッシュの形が変わって MeshArrays が作り直されたら全部捨てる)。ホイールで輪を動かすと、その輪の分だけ
求め直す。
エッジの番号: 道は頂点の組で持つので、Maya のエッジの番号は、頂点につながるエッジ (MItMeshVertex) から
相手の頂点が合うものを探す (道の頂点の分だけ。全エッジを読まない)。
"""
import maya.api.OpenMaya as om
import maya.cmds as cmds

from ..core.path_model import path_seam

__all__ = ["SeamBook", "cut_seams", "select_seams", "edge_names"]


def _guide_key(guide):
    return (guide.kind, guide.closed, tuple(guide.points))


def _line_key(guide, points, closed):
    return (guide.kind, closed, tuple(tuple(p) for p in points), tuple(guide.vertices or ()))


def edge_names(name, ids):
    """エッジの名前 (続いた番号は e[a:b] にまとめる)。"""
    names = []
    for index in sorted(set(ids)):
        if names and index == names[-1][1] + 1:
            names[-1][1] = index
        else:
            names.append([index, index])
    return ["{}.e[{}]".format(name, a) if a == b else "{}.e[{}:{}]".format(name, a, b) for a, b in names]


class SeamBook(object):
    def __init__(self):
        self._paths = {}      # シェイプの名前 -> (MeshArrays, {鍵: EdgePath か None})
        self._edges = {}      # シェイプの名前 -> (MeshArrays, {(a, b): エッジの番号})
        self._signatures = {}  # シェイプの名前 -> (MeshArrays の id, ガイドの鍵の tuple のハッシュ)

    def clear(self):
        self._paths = {}
        self._edges = {}
        self._signatures = {}

    def _store(self, cache, target):
        arrays = target.surface.arrays()
        entry = cache.get(target.name())
        if entry is None or entry[0] is not arrays:
            entry = (arrays, {})
            cache[target.name()] = entry
        return arrays, entry[1]

    def paths(self, target):
        arrays, known = self._store(self._paths, target)
        result = []
        used = set()
        for guide in target.guides.guides():
            for points, closed in guide.lines():           # ペイントは囲む線ごとにシーム
                key = _line_key(guide, points, closed)
                used.add(key)
                if key not in known:
                    known[key] = path_seam(arrays, guide.path)     # 区間ごとのシームをつなぐ (段階 2)
                result.append((guide, known[key]))
        for key in list(known):            # 消えたガイドの分は忘れる
            if key not in used:
                del known[key]
        self._signatures[target.name()] = (id(arrays), hash(tuple(sorted(used))))
        return result

    def signature(self, target):
        self.paths(target)
        return self._signatures[target.name()]

    def pairs(self, target):
        return sorted(set(pair for _guide, path in self.paths(target) if path is not None for pair in path.edges()))

    def edgeIds(self, target):
        pairs = self.pairs(target)
        if not pairs:
            return []
        _arrays, known = self._store(self._edges, target)
        missing = [pair for pair in pairs if pair not in known]
        if missing:
            vertices = om.MItMeshVertex(target.path)
            edges = om.MItMeshEdge(target.path)
            for a, b in missing:
                vertices.setIndex(a)
                for edge in vertices.getConnectedEdges():
                    edges.setIndex(edge)
                    ends = (edges.vertexId(0), edges.vertexId(1))
                    if b in ends:
                        known[(a, b)] = edge
                        break
        return sorted(known[pair] for pair in pairs if pair in known)


def cut_seams(targets, book, undo_name="シームで UV をカット"):
    """シームのエッジで UV をカットする (全メッシュで 1 回の Undo)。{シェイプ: エッジの数}。"""
    work = [(target, book.edgeIds(target)) for target in targets]
    work = [(target, ids) for target, ids in work if ids]
    if not work:
        return {}
    cmds.undoInfo(openChunk=True, chunkName=undo_name)
    try:
        for target, ids in work:
            cmds.polyMapCut(edge_names(target.name(), ids))
    finally:
        cmds.undoInfo(closeChunk=True)
    return {target.name(): len(ids) for target, ids in work}


def select_seams(targets, book):
    """シームのエッジを Maya で選ぶ (1 回の Undo)。選んだエッジの数。"""
    names = []
    for target in targets:
        names += edge_names(target.name(), book.edgeIds(target))
    if not names:
        cmds.select(clear=True)
        return 0
    cmds.select(names, replace=True)
    if not cmds.about(batch=True):
        cmds.selectMode(component=True)
        cmds.selectType(edge=True)
    return len(cmds.ls(names, flatten=True))
