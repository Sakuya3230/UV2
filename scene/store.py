# -*- coding: utf-8 -*-
"""
ガイドをシーンに保存する (メッシュのシェイプの文字列のアトリビュート seamGuides に JSON)。

    guides = read_guides(path)                          # 無ければ空の GuideSet
    write_guides([(path, guides), ...], "ガイドを足す")    # まとめて 1 回の Undo
    with undo_chunk("点を動かす"): ...                     # いくつかの書き込みを 1 回の Undo に (中のチャンクは入れ子でよい)

保存の形は統一した持ち方 (core.guides の version 2)。前の版 (version 1) は読むときに直す (メッシュの頂点を引く)。
アトリビュートに入れるので、ガイドはシーンといっしょに保存され、Undo / Redo も Maya の setAttr がそのまま
扱う (ツールはアトリビュートの変更の通知で読み直す)。Undo の名前は undoInfo のチャンクの名前。
"""
import contextlib

import maya.cmds as cmds

from .. import log
from ..constants import GUIDE_ATTRIBUTE, SPACING_RATIO
from ..core.guides import GuideSet

__all__ = ["read_guides", "write_guides", "has_guides", "undo_chunk"]


@contextlib.contextmanager
def undo_chunk(name):
    """中の操作を 1 回の Undo (名前は name) にまとめる (複数の線の点をまとめて編集するとき)。"""
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)



def has_guides(name):
    return bool(cmds.attributeQuery(GUIDE_ATTRIBUTE, node=name, exists=True))


def read_guides(path):
    name = path.fullPathName()
    if not has_guides(name):
        return GuideSet()
    text = cmds.getAttr("{}.{}".format(name, GUIDE_ATTRIBUTE)) or ""
    try:
        if '"version":1' in text.replace(" ", ""):
            # 前の版 (種類ごとの持ち方): メッシュの頂点を引いて、統一した持ち方に直す (書くときは新しい版)
            from .mesh import Surface
            surface = Surface(path)
            return GuideSet.fromJson(text, surface.arrays(), surface.size() * SPACING_RATIO)
        return GuideSet.fromJson(text)
    except ValueError as error:
        log.warning("{} のガイドを読めません ({})。空として扱います".format(name, error))
        return GuideSet()


def write_guides(items, undo_name):
    """[(MDagPath, GuideSet)] をまとめて書く (1 回の Undo。名前は undo_name)。"""
    cmds.undoInfo(openChunk=True, chunkName=undo_name)
    try:
        for path, guides in items:
            name = path.fullPathName()
            if not has_guides(name):
                cmds.addAttr(name, longName=GUIDE_ATTRIBUTE, dataType="string")
            cmds.setAttr("{}.{}".format(name, GUIDE_ATTRIBUTE), guides.toJson(), type="string")
    finally:
        cmds.undoInfo(closeChunk=True)
