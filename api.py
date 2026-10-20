# -*- coding: utf-8 -*-
"""
SeamGuide の公開 API。

    import SeamGuide
    SeamGuide.tool()            # プラグインを読み込んで、このツールにする (メッシュを選んでから)
    SeamGuide.reload_modules()  # reloader を読み直してから全モジュールをリロードする (ツールのコンテキストも消す)
    SeamGuide.reload_plugin()   # プラグインを読み直す (コマンド・ノードを足したとき)

maya はここでは import しない (関数を呼んだときに読む)。
"""
import os

from .constants import PLUGIN_NAME, TOOL_COMMAND

__all__ = ["tool", "load_plugin", "plugin_path", "reload_modules", "reload_plugin"]


def plugin_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "plug-ins", PLUGIN_NAME + ".py"))


def load_plugin():
    import maya.cmds as cmds
    if cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        return
    try:
        cmds.loadPlugin(PLUGIN_NAME + ".py", quiet=True)
    except RuntimeError:
        cmds.loadPlugin(plugin_path(), quiet=True)


def tool():
    """プラグインを読み込んで、このツールにする。コンテキストの名前を返す。"""
    import maya.cmds as cmds
    load_plugin()
    return getattr(cmds, TOOL_COMMAND)()


def reload_modules():
    from . import reloader
    return reloader.reload().reload_modules()


def reload_plugin():
    """プラグインを読み直す (ツールのコンテキストを消してから)。"""
    import maya.cmds as cmds
    if cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        from .tool.command import delete_tool_context
        delete_tool_context()
        cmds.unloadPlugin(PLUGIN_NAME)
    load_plugin()
