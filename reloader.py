# -*- coding: utf-8 -*-
"""
SeamGuide のモジュールを依存順に import / リロードする。

    import SeamGuide.reloader as r; r.reload().reload_modules()

reload() はこの reloader 自身を読み直して返す (新しい MODULES でリロードするため)。
reload_modules() は先にツールのコンテキストを消す (コンテキストは作ったときのクラスのままなので、
消さないと古いコードが動き続ける)。プラグインは読み直さなくてよい (creator が毎回モジュールを引く)。
モジュールを追加したら、MODULES (Maya 不要) / MAYA_MODULES / TOOL_MODULES に依存順で足すこと
(tests/SeamGuide/test_dependencies.py が漏れを検出する)。
"""
import importlib
import sys

__all__ = ["MODULES", "MAYA_MODULES", "TOOL_MODULES", "reload", "reload_modules", "reload_module"]

# Maya に依存しないもの (numpy は要る)
MODULES = [
    "SeamGuide.constants",
    "SeamGuide.log",
    "SeamGuide.core",
    "SeamGuide.core.geometry",
    "SeamGuide.core.mesh_arrays",
    "SeamGuide.core.section",
    "SeamGuide.core.edge_chain",
    "SeamGuide.core.stroke",
    "SeamGuide.core.curve",
    "SeamGuide.core.anchored",
    "SeamGuide.core.region",
    "SeamGuide.core.edge_path",
    "SeamGuide.core.valley",
    "SeamGuide.core.bridge",
    "SeamGuide.core.path_model",
    "SeamGuide.core.guides",
    "SeamGuide.core.actions",
    "SeamGuide.core.settings",
    "SeamGuide.core.panel",
    "SeamGuide.core.tool_ui_text",
]

# Maya が要るもの
MAYA_MODULES = [
    "SeamGuide.scene",
    "SeamGuide.scene.mesh",
    "SeamGuide.scene.store",
    "SeamGuide.scene.mirror",
    "SeamGuide.scene.targets",
    "SeamGuide.scene.edit",
    "SeamGuide.scene.prefs",
    "SeamGuide.scene.seams",
    "SeamGuide.scene.edges",
]

# ツール (Maya の UI の API。keys は Qt)
TOOL_MODULES = [
    "SeamGuide.tool",
    "SeamGuide.tool.drawing",
    "SeamGuide.tool.manipulator",
    "SeamGuide.tool.keys",
    "SeamGuide.tool.tool_ui",
    "SeamGuide.tool.bridging",
    "SeamGuide.tool.context",
    "SeamGuide.tool.command",
]

_LAST = ["SeamGuide.api", "SeamGuide"]


def _available(name):
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def reload_module(module_name):
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def reload():
    """この reloader 自身を読み直して返す。"""
    return reload_module(__name__)


def reload_modules():
    """一覧のモジュールを依存順にリロードする。読み直したモジュールのリストを返す。"""
    in_maya = _available("maya.cmds")
    if in_maya and "SeamGuide.tool.command" in sys.modules:
        sys.modules["SeamGuide.tool.command"].delete_tool_context()
    names = list(MODULES)
    if in_maya:
        names += MAYA_MODULES + TOOL_MODULES
    names += _LAST
    modules = [reload_module(name) for name in names]
    unlisted = sorted(name for name in sys.modules
                      if name.startswith("SeamGuide.") and name not in names
                      and name != __name__ and sys.modules[name] is not None)
    if unlisted:
        print("SeamGuide: 一覧 (reloader) に無いので読み直していないモジュール: {}".format(", ".join(unlisted)))
    return modules
