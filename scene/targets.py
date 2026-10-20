# -*- coding: utf-8 -*-
"""
ツールの対象のメッシュ。

    targets = selected_targets()        # 選択 (オブジェクト・コンポーネント) のメッシュのシェイプ
    target.surface / target.guides      # Surface (scene.mesh) と、読み込んだ GuideSet
    target.reload()                     # アトリビュートから読み直す (Undo / Redo のあと)
    target.spacing() / target.tolerance()
    enter_edge_mode(targets)            # 対象をハイライトしてエッジの選択モードにする (Undo に積まない)

ガイドは target.guides を直接変えない。scene.edit が写しを変えてアトリビュートに書き、ツールは
アトリビュートの変更の通知で reload する (Undo / Redo でも同じ道を通るので、表示とシーンが食い違わない)。
"""
import numpy as np

import maya.api.OpenMaya as om
import maya.cmds as cmds

from ..constants import MIRROR_TOLERANCE_RATIO, SPACING_RATIO
from .mesh import Surface
from .mirror import mirror_state
from .store import read_guides

__all__ = ["GuideTarget", "selected_targets", "selected_mesh_paths", "enter_edge_mode"]


def _mesh_shapes(path):
    if path.apiType() == om.MFn.kMesh:
        return [] if om.MFnDagNode(path).isIntermediateObject else [om.MDagPath(path)]
    result = []
    for i in range(path.childCount()):
        child = path.child(i)
        if child.apiType() != om.MFn.kMesh:
            continue
        shape = om.MDagPath(path)
        shape.push(child)
        if not om.MFnDagNode(shape).isIntermediateObject:
            result.append(shape)
    return result


def selected_mesh_paths():
    selection = om.MGlobal.getActiveSelectionList()
    result, seen = [], set()
    for i in range(selection.length()):
        try:
            path = selection.getDagPath(i)
        except RuntimeError:
            continue
        for shape in _mesh_shapes(path):
            if shape.fullPathName() not in seen:
                seen.add(shape.fullPathName())
                result.append(shape)
    return result


def enter_edge_mode(targets):
    """対象のメッシュをハイライトしてエッジの選択モードにする (UVPathCut の enter_edge_mode と同じ)。

    オブジェクトを選んだままだと、ワイヤーフレームが選択の緑で描かれて、ガイドやシームが見にくい (GUI で確認)。
    右クリックのマーキングメニューの「エッジ」と同じことを cmds で行う。Undo には積まない (積むと Ctrl+Z が
    この切り替えを戻すだけになり、ガイドの Undo が 1 回ずれる)。
    """
    names = [om.MFnDagNode(t.path.transform()).fullPathName() for t in targets if t.isValid()]
    if not names or cmds.about(batch=True):
        return
    state = cmds.undoInfo(query=True, stateWithoutFlush=True)
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        if cmds.selectMode(query=True, object=True):
            cmds.selectType(objectComponent=True, allComponents=False)
            cmds.selectType(objectComponent=True, edge=True)
            cmds.selectType(edge=True)
        else:
            cmds.selectType(allComponents=False)
            cmds.selectType(edge=True)
        cmds.hilite(names)
    finally:
        cmds.undoInfo(stateWithoutFlush=state)


def selected_targets():
    return [GuideTarget(path) for path in selected_mesh_paths()]


class GuideTarget(object):
    def __init__(self, path):
        self.path = om.MDagPath(path)
        self.surface = Surface(self.path)
        self.guides = read_guides(self.path)
        self.symmetrySettings = None   # ツールの設定 (value(key) を持つもの)。None ならオン・オブジェクト X (scene.mirror)

    def name(self):
        return self.path.fullPathName()

    def isValid(self):
        try:
            return self.path.isValid() and om.MObjectHandle(self.path.node()).isValid() \
                and bool(self.path.fullPathName())
        except RuntimeError:
            return False

    def reload(self):
        self.guides = read_guides(self.path)
        return self.guides

    def spacing(self):
        return self.surface.size() * SPACING_RATIO

    def tolerance(self):
        return self.surface.size() * MIRROR_TOLERANCE_RATIO

    def mirrorState(self):
        """今の対称 (scene.mirror.MirrorState)。Maya の対称の設定・ツールの設定 (self.symmetrySettings) はそのときに読む。"""
        return mirror_state(self.surface, self.symmetrySettings)

    def mirrorPlane(self):
        """(オブジェクト空間の面, 説明)。対称がオフでも面は返す (前に作った相手を作り直すため)。"""
        state = self.mirrorState()
        return state.plane, state.label

    def symmetric(self):
        """新しいガイドに対称の相手を作るか (Maya の対称かツールの対称がオン)。"""
        return self.mirrorState().on

    def vertexTolerance(self):
        """鏡に写した位置から反対側の頂点を探す距離 (オブジェクト空間。設定の許容値をワールドの長さとして写す)。"""
        state = self.mirrorState()
        if state.space == "world" or state.from_maya:
            ends = self.surface.toObject(np.array([[0.0, 0.0, 0.0], [state.tolerance, 0.0, 0.0]]))
            return float(np.linalg.norm(ends[1] - ends[0]))
        return state.tolerance
