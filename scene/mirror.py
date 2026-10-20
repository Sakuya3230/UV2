# -*- coding: utf-8 -*-
"""
対称の面 (メッシュのオブジェクト空間)。UVPathCut の対称と同じ仕様。

    state = mirror_state(surface, settings)   # MirrorState: plane (点, 単位の法線)・label・on・tolerance・from_maya
    plane, label = mirror_plane(surface, settings)

- Maya の対称 (symmetricModelling) がオンでワールド / オブジェクトなら、その面と許容値を使い、ツールの対称が
  オフでも両側に効く (on = True)。UVPathCut と同じ (Maya の対称とツールの対称が二重にかからないよう、Maya を
  優先する)
- オフ (かトポロジー) なら、ツールの設定 (symmetry / mirrorSpace / mirrorAxis / mirrorTolerance)。
  settings が None (スクリプト・テストでツールを通さないとき) は、前の版と同じくオン・オブジェクト X
- ワールドの面は、面の上の 3 点をオブジェクト空間に写して作り直す (メッシュが回っていても正しい面になる)
- 許容値は、鏡に写した位置から反対側の面を探す距離 (ペイントの塗った面を写すとき。core.region.mirror_faces)
"""
import collections

import numpy as np

import maya.cmds as cmds

__all__ = ["mirror_plane", "mirror_state", "maya_symmetry", "MirrorState", "plane_text", "DEFAULT_TOLERANCE"]

_AXES = {"x": 0, "y": 1, "z": 2}
DEFAULT_TOLERANCE = 0.1      # UVPathCut の mirrorTolerance の既定と同じ

MirrorState = collections.namedtuple("MirrorState", "plane label on tolerance from_maya space axis")


def maya_symmetry():
    """(空間 "world" / "object", 軸 "x" / "y" / "z", 許容値) か None (オフ・トポロジーの対称など)。"""
    try:
        if not cmds.symmetricModelling(query=True, symmetry=True):
            return None
        about = cmds.symmetricModelling(query=True, about=True)
        axis = cmds.symmetricModelling(query=True, axis=True)
    except RuntimeError:
        return None
    if about not in ("world", "object") or axis not in _AXES:
        return None
    try:
        tolerance = float(cmds.symmetricModelling(query=True, tolerance=True))
    except (RuntimeError, TypeError, ValueError):
        tolerance = DEFAULT_TOLERANCE
    return about, axis, tolerance


def plane_text(space, axis):
    return "{} {}".format("ワールド" if space == "world" else "オブジェクト", axis.upper())


def mirror_state(surface, settings=None, maya=Ellipsis):
    """今の対称 (MirrorState)。maya は maya_symmetry() の結果 (テストで渡す。省くと今の Maya の設定を読む)。"""
    maya = maya_symmetry() if maya is Ellipsis else maya
    if maya is not None:
        space, axis, tolerance = maya
        on, from_maya = True, True
        label = "Maya の対称 ({})".format(plane_text(space, axis))
    elif settings is None:
        space, axis, tolerance, on, from_maya = "object", "x", DEFAULT_TOLERANCE, True, False
        label = plane_text(space, axis)
    else:
        space, axis = settings.value("mirrorSpace"), settings.value("mirrorAxis")
        tolerance, on, from_maya = settings.value("mirrorTolerance"), bool(settings.value("symmetry")), False
        label = plane_text(space, axis) + ("" if on else " (対称はオフ)")
    return MirrorState(_plane(surface, space, axis), label, on, float(tolerance), from_maya, space, axis)


def mirror_plane(surface, settings=None):
    """(点, 単位の法線) をオブジェクト空間で、と説明の文字列。"""
    state = mirror_state(surface, settings)
    return state.plane, state.label


def _plane(surface, space, axis):
    normal = np.zeros(3)
    normal[_AXES[axis]] = 1.0
    if space == "object":
        return np.zeros(3), normal
    # ワールドの面の上の 3 点をオブジェクト空間へ
    others = [np.roll(normal, 1), np.roll(normal, 2)]
    points = surface.toObject(np.array([np.zeros(3), others[0], others[1]]))
    local_normal = np.cross(points[1] - points[0], points[2] - points[0])
    local_normal /= np.linalg.norm(local_normal)
    return points[0], local_normal
