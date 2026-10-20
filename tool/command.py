# -*- coding: utf-8 -*-
"""
コンテキストのコマンド (seamGuideCtx)・ツールのコマンド (seamGuideTool)・コンテキストの削除。

    cmds.seamGuideTool()                                  # このツールにする (コンテキストが無ければ作る)
    cmds.seamGuideCtx("seamGuideContext", e=True, mode="select")
    cmds.seamGuideCtx("seamGuideContext", q=True, mode=True)     # 番号 (0 = ガイド, 1 = 選択)
    cmds.seamGuideCtx("seamGuideContext", e=True, seamPreview=False)
    cmds.seamGuideCtx("seamGuideContext", e=True, runAction="cut")  # 操作の表 (core.actions) の操作
    delete_tool_context()                                 # リロードの前に消す

フラグは設定の定義表 (core/settings.DEFINITIONS) から作る。問い合わせは文字列を返せない (kFailure になる。
UVPathCut で確認) ので、選択肢は番号で返す。編集は名前でも番号でもよい。
プラグイン (plug-ins/seamGuide.py) が、creator でこのモジュールを毎回引いて作る。
"""
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
import maya.cmds as cmds

from ..constants import CONTEXT_COMMAND, TOOL_CONTEXT
from ..core.actions import action_by_id
from ..core.settings import BOOL, CHOICE, COLOR, DEFINITIONS, FLOAT, SettingsError

__all__ = ["SeamGuideContextCommand", "ToolCommand", "delete_tool_context", "RUN_ACTION_FLAG"]

RUN_ACTION_FLAG = ("-ra", "-runAction")


def _long_flag(setting):
    return "-" + setting.key


class SeamGuideContextCommand(omui.MPxContextCommand):
    def __init__(self):
        super().__init__()
        self._context = None

    def makeObj(self):
        from .context import SeamGuideContext     # context は重いので、作るときに読む
        self._context = SeamGuideContext()
        return self._context

    def appendSyntax(self):
        syntax = self.syntax()
        for setting in DEFINITIONS:
            kind = {BOOL: om.MSyntax.kBoolean, FLOAT: om.MSyntax.kDouble}.get(setting.kind, om.MSyntax.kString)
            syntax.addFlag(setting.short_flag, _long_flag(setting), kind)
        syntax.addFlag(RUN_ACTION_FLAG[0], RUN_ACTION_FLAG[1], om.MSyntax.kString)

    def doEditFlags(self):
        parser = self.parser()
        for setting in DEFINITIONS:
            if not parser.isFlagSet(setting.short_flag):
                continue
            if setting.kind == BOOL:
                value = parser.flagArgumentBool(setting.short_flag, 0)
            elif setting.kind == FLOAT:
                value = parser.flagArgumentDouble(setting.short_flag, 0)
            else:
                value = parser.flagArgumentString(setting.short_flag, 0)
            try:
                self._context.setSetting(setting.key, value)
            except SettingsError as error:
                raise RuntimeError("{}: {}".format(CONTEXT_COMMAND, error))
        if parser.isFlagSet(RUN_ACTION_FLAG[0]):
            ident = parser.flagArgumentString(RUN_ACTION_FLAG[0], 0)
            try:
                action_by_id(ident)
            except KeyError:
                raise RuntimeError("{}: -runAction: 知らない操作です: {}".format(CONTEXT_COMMAND, ident))
            self._context.runAction(ident)

    def doQueryFlags(self):
        parser = self.parser()
        for setting in DEFINITIONS:
            if parser.isFlagSet(setting.short_flag):
                if setting.kind == CHOICE:
                    self.setResult(self._context.settings.choiceIndex(setting.key))
                elif setting.kind == BOOL:
                    self.setResult(bool(self._context.settings.value(setting.key)))
                elif setting.kind == FLOAT:
                    self.setResult(float(self._context.settings.value(setting.key)))
                elif setting.kind == COLOR:
                    # コンテキストのコマンドはリストも文字列も返せない (kFailure) ので、色は返さない
                    # (ウィンドウは tool_ui.color_value で読む)
                    pass
                return


class ToolCommand(om.MPxCommand):
    """seamGuideTool: このツールにする。決まった名前のコンテキストを使い回す。"""

    def doIt(self, args):
        if not cmds.contextInfo(TOOL_CONTEXT, exists=True):
            getattr(cmds, CONTEXT_COMMAND)(TOOL_CONTEXT)
        cmds.setToolTo(TOOL_CONTEXT)
        self.setResult(TOOL_CONTEXT)


def delete_tool_context():
    if not cmds.contextInfo(TOOL_CONTEXT, exists=True):
        return False
    if cmds.currentCtx() == TOOL_CONTEXT:
        cmds.setToolTo("selectSuperContext")
    cmds.deleteUI(TOOL_CONTEXT, toolContext=True)
    return True
