# -*- coding: utf-8 -*-
"""
境界のガイドにするエッジを Maya から読む。

    found, source = boundary_chains(targets)   # [(target, [(頂点の番号の配列, 閉じているか)])], "selection" / "uv"

- Maya で対象のメッシュのエッジを選んでいれば、そのエッジ (source = "selection")
- 選んでいなければ、今の UV セットの UV の境界 (カットされた切れ目) すべて (source = "uv")
- どちらも core.edge_chain.edge_chains でつながりごとの頂点の列にする (枝分かれする頂点で区切る)
"""
import numpy as np

import maya.api.OpenMaya as om

from ..core.edge_chain import edge_chains, uv_seam_pairs

__all__ = ["boundary_chains", "selected_edge_pairs", "uv_border_pairs"]


def selected_edge_pairs(target):
    """Maya で選んでいる、target のメッシュのエッジ (a < b の (n, 2))。"""
    selection = om.MGlobal.getActiveSelectionList()
    shape = target.path.fullPathName()
    pairs = []
    for index in range(selection.length()):
        try:
            path, component = selection.getComponent(index)
        except RuntimeError:
            continue
        if component.isNull() or component.apiType() != om.MFn.kMeshEdgeComponent:
            continue
        try:
            path.extendToShape()
        except RuntimeError:
            pass
        if path.fullPathName() != shape:
            continue
        edges = om.MItMeshEdge(path, component)      # path と component は変数に持ったまま渡す (参照を保持しない)
        while not edges.isDone():
            a, b = edges.vertexId(0), edges.vertexId(1)
            pairs.append((min(a, b), max(a, b)))
            edges.next()
    return np.asarray(pairs, dtype=np.int64).reshape(-1, 2)


def uv_border_pairs(target):
    """target のメッシュの、今の UV セットの UV の境界のエッジ (a < b の (n, 2))。メッシュの開いた縁は入れない。"""
    fn = om.MFnMesh(target.path)
    counts, connects = fn.getVertices()
    try:
        uv_set = fn.currentUVSetName()
        uv_counts, uv_ids = fn.getAssignedUVs(uv_set)
    except RuntimeError:
        return np.zeros((0, 2), dtype=np.int64)
    return uv_seam_pairs(np.asarray(counts), np.asarray(connects), np.asarray(uv_counts), np.asarray(uv_ids))


def boundary_chains(targets):
    """([(target, [(頂点の番号の配列, 閉じているか)])], "selection" か "uv")。どのメッシュもエッジを選んで
    いなければ UV の境界。"""
    selected = [(target, selected_edge_pairs(target)) for target in targets]
    if any(len(pairs) for _target, pairs in selected):
        return [(target, edge_chains(pairs)) for target, pairs in selected if len(pairs)], "selection"
    found = []
    for target in targets:
        pairs = uv_border_pairs(target)
        if len(pairs):
            found.append((target, edge_chains(pairs)))
    return found, "uv"
