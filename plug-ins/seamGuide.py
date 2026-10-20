# -*- coding: utf-8 -*-
"""
シームガイドのプラグイン (登録だけ)。中身は scripts/SeamGuide パッケージ。

    import SeamGuide; SeamGuide.tool()

UVPathCut のプラグインと同じ形: creator はパッケージのクラスを呼ばれるたびに importlib で引く
(リロードしたあとに作るものは新しいクラス)。名前は SeamGuide.constants。
"""
import importlib

import maya.api.OpenMaya as om

_VENDOR = "MayaPy"
_VERSION = "0.1"
_COMMAND_MODULE = "SeamGuide.tool.command"
_MANIP_MODULE = "SeamGuide.tool.manipulator"


def maya_useNewAPI():
    pass


def _constants():
    try:
        return importlib.import_module("SeamGuide.constants")
    except ImportError:
        raise RuntimeError("SeamGuide パッケージが見つかりません。scripts/ を PYTHONPATH に足してください "
                           "(起動用のバッチ maya20XX.bat が足します)")


def _commands():
    return importlib.import_module(_COMMAND_MODULE)


def _create_context_command():
    return _commands().SeamGuideContextCommand()


def _create_tool_command():
    return _commands().ToolCommand()


def _create_manip():
    return importlib.import_module(_MANIP_MODULE).SeamGuideManip()


def _initialize_manip():
    importlib.import_module(_MANIP_MODULE).SeamGuideManip.initialize()


def initializePlugin(plugin):
    names = _constants()
    _commands()
    fn = om.MFnPlugin(plugin, _VENDOR, _VERSION, "Any")
    fn.registerNode(names.MANIP_NODE, om.MTypeId(names.MANIP_TYPE_ID), _create_manip, _initialize_manip,
                    om.MPxNode.kManipulatorNode)
    fn.registerContextCommand(names.CONTEXT_COMMAND, _create_context_command)
    fn.registerCommand(names.TOOL_COMMAND, _create_tool_command)


def uninitializePlugin(plugin):
    names = _constants()
    _commands().delete_tool_context()
    fn = om.MFnPlugin(plugin)
    fn.deregisterCommand(names.TOOL_COMMAND)
    fn.deregisterContextCommand(names.CONTEXT_COMMAND)
    fn.deregisterNode(om.MTypeId(names.MANIP_TYPE_ID))
