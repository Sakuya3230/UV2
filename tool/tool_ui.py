# -*- coding: utf-8 -*-
"""
ツール設定のウィンドウ。MEL は core/tool_ui_text.py が定義表から組み立てる。

    define()     MEL のプロシージャを定義する (import したときに 1 回。リロードでも定義し直す)
    refresh()    開いているウィンドウの値を今の設定に合わせる (ボタン・Tab でモードを変えたとき)
    setting_value(key)   ウィンドウの MEL が python() で呼ぶ: 保存した設定の値 (選択肢は番号、真偽値は 0 / 1)
    color_value(key)     同じく色の設定の値 [r, g, b] (Python のリストが MEL の float[] になる)

Maya は、ツールのアイコンをダブルクリックしたとき (とツールを有効にしたとき) に seamGuideProperties /
seamGuideValues を呼ぶので、それより前 (プラグインを読み込んでコンテキストのモジュールを import したとき) に定義する。
"""
import maya.mel as mel

from ..core.settings import BOOL, FLOAT, Settings, definition
from ..core.tool_ui_text import CLASS_NAME, tool_ui_mel
from ..scene.mirror import maya_symmetry, plane_text
from ..scene.prefs import OptionVarStorage

__all__ = ["define", "refresh", "setting_value", "color_value", "maya_symmetry_text", "CLASS_NAME"]


def define():
    mel.eval(tool_ui_mel())


def setting_value(key):
    """保存した設定の値 (int)。設定は変えるたびに optionVar に保存されるので、ツールの値と同じ。"""
    settings = Settings(OptionVarStorage())
    if definition(key).kind == BOOL:
        return int(bool(settings.value(key)))
    if definition(key).kind == FLOAT:
        return float(settings.value(key))
    return settings.choiceIndex(key)


def color_value(key):
    """保存した色の設定の値 [r, g, b]。"""
    return [float(v) for v in Settings(OptionVarStorage()).value(key)]


def maya_symmetry_text():
    """Maya の対称が効いていれば「Maya の対称: ワールド Z  許容値 0.1 (この面で両側に作る)」、無ければ ""。"""
    found = maya_symmetry()
    if found is None:
        return ""
    space, axis, tolerance = found
    return "Maya の対称: {}  許容値 {:g} (この面で両側に作る)".format(plane_text(space, axis), tolerance)


def refresh():
    try:
        mel.eval("{}RefreshUI".format(CLASS_NAME))
    except RuntimeError:
        pass


define()
