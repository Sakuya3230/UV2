# -*- coding: utf-8 -*-
"""
操作の表 (Maya に依存しない)。ビューのボタン (core.panel) とツール設定のウィンドウ (core.tool_ui_text) と
コンテキストのコマンドの -runAction が、この表から作られる。

    for action in ACTIONS: action.id / action.label / action.description

操作の中身はコンテキストの runAction(ID) (tool/context.py)。
"""
import collections

__all__ = ["Action", "ACTIONS", "TOGGLES", "EDIT_ONLY", "action_by_id", "symmetry_label", "route_label"]

Action = collections.namedtuple("Action", "id label description")

ACTIONS = [
    Action("symmetry", "対称 OFF", "対称 (新しいガイドに反対側の相手も作る) を切り替える (X キー)。Maya の対称がオンの間は"
           "Maya の面が使われ、両側に作る (ツールの対称を切り替えても変わらない)"),
    Action("bridgeRoute", "通り方 最短", "つなぎ線の通り方を 最短 / 谷 に切り替える。新しいつなぎ線に効き、編集で選んだ"
           "つなぎ線 (と相手) も作り直す (1 回の Undo)"),
    Action("cut", "UV をカット", "シーム (ガイドから求めたエッジ) で UV を切る。全メッシュで 1 回の Undo"),
    Action("selectEdges", "エッジを選択", "シームのエッジを Maya で選ぶ (ほかのツールで使う・確かめる)"),
    Action("fromEdges", "境界をガイドに", "Maya で選んだエッジ (選んでいなければ今の UV の境界すべて) を、境界のガイドに"
           "する。枝分かれする頂点で区切り、輪は閉じた線。メッシュの開いた縁は入れない。1 回の Undo"),
    Action("bridge", "つなぎ線", "編集: 選んだ 2 本のガイドの間を、カメラから見て奥側でエッジの最短パスでつなぐ "
           "(1 本目のいちばん奥の頂点から、2 本目の奥側の半分で最短の頂点へ)"),
    Action("segmentMode", "区間: -", "編集: 区間の作り方を 曲線 -> 直線 -> 最短 -> 谷 と切り替える (選んだ点の隣り合う 2 点の"
           "間の区間、点を選んでいなければ選んだ線全体。固定の区間は曲線から。対称の相手も。1 回の Undo)"),
    Action("ringReset", "断面に戻す", "編集: 点で形を変えた輪を、今の平面の断面の輪に戻す (点を捨てる。対称の相手も。"
           "1 回の Undo)"),
    Action("join", "つなぐ", "編集: 選んだ 2 本の線 (カーブ・ライン・ペイント) の近い端どうしをつないで 1 本にする。"
           "1 本だけなら始点と終点をつないで閉じる"),
    Action("split", "切り離す", "編集: 選んだ点で線を切り離す (開いた線は 2 本に、閉じた線は開いた線に)"),
]


EDIT_ONLY = ("bridge", "segmentMode", "ringReset", "join", "split")   # 編集のモードだけの操作 (作成のモードではビューのボタンを出さない)
TOGGLES = ("symmetry", "bridgeRoute")    # 切り替えのボタン (ビューの上の段。ツール設定のウィンドウでは設定の欄で切り替える)


def symmetry_label(on, axis, maya_axis=None):
    """対称のボタンの文字 (UVPathCut と同じ): Maya の対称が効いていれば「Maya 対称 Z」、ツールの対称なら
    「対称 X」、無ければ「対称 OFF」。"""
    if maya_axis:
        return "Maya 対称 {}".format(maya_axis.upper())
    if on:
        return "対称 {}".format(str(axis).upper())
    return "対称 OFF"


def route_label(route):
    """通り方のボタンの文字: 「通り方 最短」/「通り方 谷」。"""
    return "通り方 谷" if route == "valley" else "通り方 最短"


def action_by_id(ident):
    for action in ACTIONS:
        if action.id == ident:
            return action
    raise KeyError(ident)
