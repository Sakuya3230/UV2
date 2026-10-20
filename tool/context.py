# -*- coding: utf-8 -*-
"""
ガイドを描くツール (コンテキスト)。段階 2・3。

シーム (段階 3): ガイドから求めたエッジ (scene.seams.SeamBook。ガイドの中身ごとに覚えておく) を、設定
seamPreview がオンなら赤紫で描く。操作 (core.actions。ビューの下のボタン・ツール設定のウィンドウ・
-runAction) の「UV をカット」「エッジを選択」は runAction。ツールに入ったら、手すきのときにメッシュの
配列・隣接の表・頂点の木と、今のガイドのシームを先に作る (1 回目だけ重いため)。

モード (設定 mode。Tab・ビューの下のボタン・ツール設定のウィンドウで切り替える。optionVar に残る):
    作成     新しいガイドを描くだけ。描くものはガイドの種類 (設定 guideTool。キーの 1〜4・ビューの下のボタン・
             ツール設定のウィンドウ): 1 リング / 2 ペイント / 3 ライン / 4 カーブ。選択・ホバー・カーブの点の印は
             出さず、ガイドの上のクリックでも選ばない。ホイールでは動かさない (カメラのズーム)
    編集     できているガイドを選んで直すだけ。Maya と同じ選び方: クリック / ドラッグ (矩形) で選ぶ。Shift 切り替え /
             Ctrl 外す / Ctrl+Shift 足す。Delete で消す、Ctrl+ホイールで選んだ閉じたガイドを動かす、点の編集
    描いたガイドは選んだ状態にしておくので、Tab で編集にするとすぐ直せる

操作 (作成のモード):
  1 リング
    ドラッグ              輪切りのガイド (描いた線の範囲の断面。ドラッグ中はプレビュー)
    Shift+ドラッグ        輪切り。線の向きを画面で STEP_DEGREES (15 度) 刻みにそろえる
    Ctrl+ドラッグ         円: 押した所を中心に、マウスまでの距離 (画面) を半径にした円を広げ、離すとカメラの向きに
                          落として閉じた曲線のガイドにする (CIRCLE_NODES 点 + 曲線の区間。種類はリング、平面は持たない。
                          円の一部でもメッシュから外れる・別のメッシュにかかるなら作らない。プレビューは赤)。Ctrl は
                          押したときだけ見る (ドラッグの途中で円 / 輪切りは替わらない)
        Alt (円のドラッグ中)  押している間は、半径でなく円の移動になる (中心がマウスと一緒に動く)。離すとまた半径。
                          前のマウスの位置からの差で中心を動かすので、離したときに半径は飛ばない
  2 ペイント
    ドラッグ              補助線 (フリーハンド)。レイジーマウス: カーソルとペン先をひも (LAZY_PIXELS) で
                          つなぎ、ひもが張ったときだけペン先が動く (手ぶれが線に出ない)
  3 ライン
    クリック              直線の折れ線の補助線を始める / 点を足す (ドラッグしても離した所に点を置く)。
                          区間は画面で真っすぐな線を、点を足したときの視点で表面に落とす (途中で視点を回してよい)
        Ctrl+クリック     区間の向きを 15 度刻みにそろえる
        Enter / 最後の点をクリック    確定 (開いた線)
        最初の点をクリック (3 点以上)  閉じて確定
        Backspace         最後の点を戻す
        Esc               やめる
    Ctrl はドラッグの途中で押しても離しても効く (今の修飾キーを Qt から読む。tool.keys.modifiers)
    ホイール              Ctrl・Shift が無ければいつも Maya に渡す (カメラのズーム)
    Ctrl+ホイール         編集のモードで、選んでいる閉じたガイドを面の向きに平行移動する (1 目盛り = 点の間隔 x 2)。
                          カーソルの位置は問わない (Ctrl が合図。2026-10-20 にユーザーの指定で、ホイールだけで動かす・
                          カーソルが輪の近くのときだけ・Ctrl で 5 倍 / 15 度、をやめて置き換えた)
    Shift+ホイール        選んでいる閉じたガイドを、カメラの向き (カメラから中心への視線) を軸に回す = 画面の上で
                          線を回す (TILT_DEGREES)。手前 / 奥へ傾けたいときは横から見て回す (Ctrl+Shift でも同じ)
                          作成のモードでは動かさない。動かすガイドが無いときは Maya に渡す。動かした結果は止めてから
                          COMMIT_MS 後に 1 回の Undo で書く (それまでは写しを表示する。ほかの操作の前にも書く)
    クリック (リング・ペイント)  何もしない (選ぶのは編集のモード)
    Ctrl+クリック         線を描いている間は 15 度刻み。ガイドそのものは消さない (誤操作になるため。ユーザーの指定)
    Ctrl+Z                線を描いている間は最後の点を戻す (描いていなければ Maya の Undo)
    Delete / Backspace    描いている線の最後の点を戻す (編集のモード: 選んだガイドをまとめて消す。対称の相手も。1 回の Undo)
    Esc                   描いている線・折れ線をやめる (編集のモード: 点の選択・ガイドの選択を外す)
どれも対称の相手を作る / 消す (scene.edit)。足す・消すは 1 回の Undo (名前付き)。

流れ:
- toolOnSetup: 選んでいるメッシュを対象にし (scene.targets)、マニピュレータ (表示とホバー) とキーを付け、
  シェイプのアトリビュートの変更 (ガイドの保存・Undo / Redo) と dirty (形の変更) を見張る
- ガイドはアトリビュートが正 (scene.store)。足す・消すはアトリビュートを書き、変更の通知で読み直して描く
- ドラッグ中は Maya がマニピュレータを描き直さないので、ガイドとプレビューは doDrag の drawMgr にも描く
- 押したときにビューの投影と視線の関数を作り、ドラッグの間は使い回す (カメラはドラッグ中は動かない)
- 折れ線は、点を足すたびにその区間の視線を表面に当てておき (scene.edit.cast_rays)、確定で
  scene.edit.add_line_hits に渡す。画面の点ではなく表面の点を覚えるので、途中で視点を変えてもずれない。
  次の点までのゴム紐 (画面の 2D) はマウスの移動 (マニピュレータの doMove -> hoverAt) で描き直す
- マウスの処理は press / drag / release (doPress などはイベントの位置を渡すだけ)。viewFunctions に
  (投影, 視線) を入れると、ビューの代わりにそれを使う (mayapy のテスト。standalone にはビューが無い)

UVPathCut と同じく、基底の toolOnSetup / toolOffCleanup は呼ばない (API 2.0 では SystemError)。
クラスでは引数なしの super() (リロードのあとに古いインスタンスへイベントが届いても TypeError にならない)。
"""
import time
import traceback

import numpy as np

import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
import maya.utils

from .. import log
from ..constants import (RESIZE_RATIO, BRUSH_RADIUS_RATIO, CIRCLE_NODES, CIRCLE_SAMPLES, COMMIT_MS, DRAG_PIXELS,
                         MAX_STAMPS, PAINT_FILL_INTERVAL, SQUARE_REACH, STAMP_SPACING, STROKE_ANGLE_PIXELS, GUIDE_ATTRIBUTE, GUIDE_WIDTH, LAZY_PIXELS,
                         MANIP_NODE, PAINT_ALPHA, PAINT_OFFSET_RATIO, PICK_PIXELS, PREVIEW_COLOR, RADIUS_DRAG_PIXELS,
                         SAMPLE_PIXELS, SEAM_WIDTH, SELECTED_WIDTH, STEP_DEGREES, STRING_COLOR,
                         STROKE_COLOR, TILT_DEGREES)
from ..core.geometry import reflect
from ..core.curve import catmull_rom
from ..core.guides import BRIDGE, CURVE, EDGE, GuideSet, REGION, RING
from ..core.panel import TOOL_PREFIX, is_mode, is_tool, panel_buttons, tool_of
from ..core.region import (brush_faces, connected_faces, face_centers, face_count, face_normals, grow_faces,
                           painted_triangles, region_loops, shrink_faces, square_faces)
from ..core.settings import COLOR_KEYS
from ..core.settings import (BRUSH_CIRCLE, BRUSH_SQUARE, BRUSH_SQUARE_STROKE, BRUSH_SURFACE, MODE_CREATE, MODE_EDIT, TOOL_CURVE, TOOL_FREEHAND, TOOL_LINE, TOOL_BRIDGE,
                             TOOL_PAINT, TOOL_RING,
                             Settings,
                             definition)
from ..core.stroke import LazyBrush, segment_points, snap_angle
from ..scene import edit
from ..scene.prefs import OptionVarStorage
from ..scene.store import undo_chunk
from ..scene.seams import SeamBook, cut_seams, select_seams
from ..scene.edges import boundary_chains
from ..scene.mirror import maya_symmetry
from ..scene.targets import enter_edge_mode, selected_targets
from ..core.actions import brush_shape_label, route_label, symmetry_label
from . import keys
from . import tool_ui
from .drawing import color_management_key, draw_stroke, overlay_mesh, projector, view_ray
from ..core.valley import vertex_concavity
from .bridging import BridgeMixin
from .manipulator import SeamGuideManip

SEGMENT_CYCLE = ("curve", "straight", "shortest", "valley")   # 区間の作り方のボタンで回す順
SEGMENT_LABELS = {"curve": "曲線", "straight": "直線", "shortest": "最短", "valley": "谷", "fixed": "固定"}
MAYA_SYMMETRY_INTERVAL = 0.5    # Maya の対称の設定を読み直す間隔 (秒。ボタンの文字)
LOOPS_INTERVAL = 0.05
ERASE_PREVIEW_COLOR = (1.0, 0.35, 0.35)   # Ctrl+ドラッグの円がはみ出したときの色

__all__ = ["SeamGuideContext", "Polyline", "HELP", "help_text"]

_CREATE = " / X = 対称 / 1 リング・2 フリーハンド・3 ライン・4 カーブ・5 ペイント / Tab = 編集"
HELP = {
    TOOL_RING: ("シームガイド 作成 (1 リング): ドラッグ = 輪切り (Shift で 15 度刻み) / Ctrl+ドラッグ = 円 "
                "(押した所が中心、カメラの向きに落とす)"),
    TOOL_FREEHAND: "シームガイド 作成 (2 フリーハンド): ドラッグ = 手描きの補助線 (レイジーマウス)",
    TOOL_BRIDGE: ("シームガイド 作成 (6 つなぎ線): ガイドをクリック -> (メッシュのクリック = 中継点) -> 別のガイドをクリック = "
                  "間をエッジの最短パスでつなぐ (Backspace・Ctrl+Z で戻す、Esc でやめる)"),
    TOOL_PAINT: ("シームガイド 作成 (5 ペイント): ドラッグ = 塗る (Ctrl で消す) / B+ドラッグ = 半径 / S = 円・四角 / "
                 "> < = 広げる・狭める / "
                 "Enter = 塗った範囲を囲む線にする / Ctrl+Z = 1 筆戻す / Esc = やめる (ペイントを選んでから 5 で塗り直す)"),
    TOOL_LINE: ("シームガイド 作成 (3 ライン): クリック = 点を置く (Enter / 最後の点で確定、最初の点で閉じる、"
                "Backspace・Delete・Ctrl+Z で戻す、Esc でやめる)"),
    TOOL_CURVE: ("シームガイド 作成 (4 カーブ): クリック = 通る点を置く (Enter / 最後の点で確定、最初の点で閉じる、"
                 "Backspace・Delete・Ctrl+Z で戻す、Esc でやめる)"),
    MODE_EDIT: ("シームガイド 編集: クリック / ドラッグで選ぶ (Shift 切り替え / Ctrl 外す / Ctrl+Shift 足す) / Delete = 消す / "
                "Ctrl+ホイール = 選んだ閉じたガイドを動かす、Shift+ホイール = 回す / 点のドラッグ = 動かす (V で途中の点も乗せる)、線のクリック = 点を足す、"
                "点の Ctrl+クリック・Delete = 点を消す / 1〜4 = 作成 / Tab = 作成"),
}


def help_text(mode, tool):
    """ヘルプの行 (作成のモードは種類ごと)。"""
    if mode == MODE_EDIT:
        return HELP[MODE_EDIT]
    return HELP[tool] + _CREATE

# 選択の操作 (Maya と同じ): 修飾キーなし = 置き換え、Shift = 切り替え、Ctrl = 外す、Ctrl+Shift = 足す
REPLACE, TOGGLE, REMOVE, ADD = "replace", "toggle", "remove", "add"


def selection_op(shift, ctrl):
    if shift and ctrl:
        return ADD
    if shift:
        return TOGGLE
    if ctrl:
        return REMOVE
    return REPLACE


def event_position(event):
    position = event.position
    return (position[0], position[1])


POINT_TOOLS = (TOOL_LINE, TOOL_CURVE)     # クリックで点を置く種類


class PaintSession(object):
    """塗っている途中: 塗る対象のメッシュ、面ごとに塗ったか (0 / 1)、塗り直しているガイドの番号 (新しいなら None)、
    1 筆ごとの塗る前の面 (Ctrl+Z で戻す)、囲む線のプレビュー。"""

    def __init__(self, target, faces, ident=None):
        self.target = target
        self.faces = np.asarray(faces, dtype=np.float64).copy()
        self.ident = ident
        self.history = []
        self.loops = []
        self.version = 0
        self.loops_version = -1      # loops を作ったときの version
        self.loops_time = 0.0        # 最後に loops を作り終えた時刻 (ドラッグ中の作り直しの間引き)
        self.loops_cost = 0.0        # 作るのにかかった秒

    def begin_stroke(self):
        self.history.append(self.faces.copy())

    def undo(self):
        """1 筆戻す。戻す筆が無ければ False。"""
        if not self.history:
            return False
        self.faces = self.history.pop()
        self.version += 1
        return bool(self.history) or bool(np.any(self.faces > 0)) or self.ident is not None


def handle_points(guide):
    """編集のモードで点の印を出す点: どのガイドもその点 (統一した持ち方。docs/05_unified_spec.md)。"""
    return guide.anchors


def attached_indices(guide):
    """ほかのガイドに乗っている点の番号の集まり (点の印をひし形にする)。"""
    return {i for i, node in enumerate(guide.path.nodes) if node.attach is not None}


class Polyline(object):
    """描いている折れ線 / カーブ。点 (ワールド) と、区間ごとの当てた結果 (scene.edit.cast_rays の要素のリスト)。

    ライン: 区間は画面の直線を当てた点の列。カーブ: 区間は置いた点 1 つだけ (曲線は点から 3D で作る)。
    """

    def __init__(self, first_hit, tool=TOOL_LINE):
        self.tool = tool
        self.anchors = [first_hit[2]]
        self.segments = [[first_hit]]     # 最初の要素は、最初の点そのもの

    def __len__(self):
        return len(self.anchors)

    def add(self, hits):
        self.anchors.append(hits[-1][2])
        self.segments.append(hits)

    def pop(self):
        """最後の点を戻す。点が無くなったら True。"""
        self.anchors.pop()
        self.segments.pop()
        return not self.anchors

    def hits(self):
        return [hit for segment in self.segments for hit in segment]

    def world(self, closed=False):
        """描く線 (ワールド)。カーブは置いた点を通る曲線 (表面には寄せない。描いている間は軽く)。"""
        if self.tool == TOOL_CURVE:
            return catmull_rom(np.array(self.anchors), closed=closed, samples=12)
        return np.array([hit[2] for hit in self.hits() if hit is not None])


class SeamGuideContext(BridgeMixin, omui.MPxContext):
    def __init__(self):
        super().__init__()
        self.setTitleString("シームガイド")
        self.settings = Settings(OptionVarStorage())     # 作ったときに読み、変えるたびに保存する
        self.settings.addListener(self._settings_changed)
        self._maya_symmetry_cache = None   # (読んだ時刻, maya_symmetry())
        self.seams = SeamBook()     # ガイドから求めたエッジ (段階 3)
        self.targets = []
        self.selection = []       # 選んだガイド [(シェイプの名前, ガイドの番号)]。最後が selected
        self.hover = None
        self.polyline = None      # 描いている折れ線 (Polyline)
        self._mouse = None        # 最後のマウスの位置 (折れ線のゴム紐)
        self.cursor = None        # 最後のマウスの位置 (ビューの px)
        self._manip = None
        self._callbacks = []
        self._press = None        # 押した位置 (画面)
        self.pointSelection = []     # 選んだ点 [(シェイプの名前, ガイドの番号, 点の番号)]
        self.created = None          # 描いたばかりのガイド (シェイプの名前, 番号)
        self.paint = None            # 塗っている途中 (PaintSession)。Enter で囲む線にする
        self.brushRadius = None      # ブラシの半径 (ワールド)。None なら最初に使うときメッシュの大きさから決める
        self._brush_spot = None           # ブラシの円を置く所 (target, オブジェクト空間の点, ワールドの点, ワールドの法線)
        self._adjust = None          # B + ドラッグで半径を調整している途中 {"x", "start"}
        self._painting = False       # ペイントの 1 筆の途中 (押している間)
        self._paint_meshes = {}      # 重ね塗りの面を覚えておく {鍵: 面}
        self._preview_mesh = None    # ブラシの下見の面を覚えておく (鍵, 面)。描き直しでは作り直さない
        self._repaint = None         # 塗り直すペイント (シェイプの名前, 番号)。編集で選んで 5 にしたときだけ
        self._fill_last = None       # 1 筆の途中の塗った範囲の面 (塗りの id, 作った時刻, 面)。PAINT_FILL_INTERVAL ごと
        self._point_press = None     # 点を押した {"key": 押した点, "drags": {(名前, 番号): (target, 置いた点の写し, {番号: 画面の位置})}}
        self._drag_drawing = False   # doDrag の絵を描いている間 (点を動かすプレビューはこちらにだけ描く)
        self._tool = TOOL_RING    # 押したときのガイドの種類
        self._line = False        # ペイント (フリーハンドの補助線) か
        self._step = False        # 15 度刻み (Ctrl) か
        self._marquee = False     # 編集のモードの押下 (クリック / 矩形) か
        self._rect = None         # 矩形 (左, 下, 右, 上)
        self._dragged = False
        self._samples = []        # 補助線の画面の点 (レイジーマウスのペン先の跡)
        self._brush = None        # LazyBrush
        self._end = None          # 輪切りの線の終点 (刻みにそろえたもの)
        self._found = []          # 輪切りのプレビュー [(target, [SectionCurve])]
        self._circle = False      # 1 リングの Ctrl+ドラッグ (円を落とす) か (押したときに決める)
        self._circle_preview = None   # 円のプレビュー (target, 曲線の点 (オブジェクト空間)) か None
        self._circle_center = None    # 円の中心 (画面の px)。Alt のドラッグで動く
        self._circle_radius = 0.0     # 円の半径 (画面の px)
        self._circle_last = None      # 円のドラッグの前のマウスの位置 (Alt の間は、その差だけ中心を動かす)
        self.altState = None          # () -> Alt を押しているか。GUI では keys.alt_held (テストは差し替える)
        self._brush_angle = 0.0       # 四角 (向き) のブラシの向き (画面の横からのラジアン)。マウスの動きで替わる
        self._brush_trail = None      # 向きを決めるための、前に向きを替えたマウスの位置 (画面の px)
        self._last_stamp = None       # 1 筆の中で最後に押した画面の位置 (間を埋める)
        self._shift_press = False     # 押したときの Shift (今の状態が読めないとき)
        self._project = None      # ワールド -> 画面 (押したときのビュー)
        self._rays = None         # (x, y) -> ワールドの視線
        self._error_shown = False
        self.viewFunctions = None   # (project, rays)。テストで差し替える
        self.modifierState = None   # () -> (Shift, Ctrl) の今の状態。GUI では keys.modifiers (テストは差し替える)
        self.heldKeys = None        # () -> 押している B / V の集合 (テストで差し替える。GUI では keys.HELD)
        self._pending = None        # 動かして、まだ書いていない輪 (target, GuideSet の写し)
        self._commit_timer = None   # ホイールを止めてから書くタイマー (GUI だけ)
        self._writing = False       # 自分で書いている間 (アトリビュートの変更の通知を区別する)

    def stringClassName(self):
        # Maya はこの名前に Properties / Values を付けた MEL でツール設定のウィンドウを作る (tool/tool_ui.py)
        return tool_ui.CLASS_NAME

    # -- モード ------------------------------------------------------------

    def mode(self):
        return self.settings.value("mode")

    def setMode(self, mode):
        """モードを替える (ボタン・Tab・ツール設定のウィンドウ)。替えたら True。"""
        return self.settings.set("mode", mode)

    def setSetting(self, key, value):
        """コンテキストのコマンド (-mode など) から。"""
        return self.settings.set(key, value)

    def guideTool(self):
        """作成のモードで描くもの: TOOL_RING / TOOL_FREEHAND / TOOL_LINE / TOOL_CURVE / TOOL_PAINT。"""
        return self.settings.value("guideTool")

    def setGuideTool(self, tool):
        """ガイドの種類を替える (1〜4 のキー・ボタン)。編集のモードなら作成のモードにする。編集のモードでペイントを
        1 本選んで 5 (ペイント) にしたときだけ、そのペイントの塗り直しにする (_repaint)。"""
        repaint = None
        if tool == TOOL_PAINT and self.mode() == MODE_EDIT:
            found = self._selected_region()
            if found is not None:
                repaint = (found[0].name(), found[1].ident)
        changed = self.settings.set("guideTool", tool)
        if self.mode() != MODE_CREATE:
            changed = self.setMode(MODE_CREATE) or changed
        self._repaint = repaint
        if repaint is not None:
            log.info("選んだペイントを塗り直します (ドラッグで塗り足す / Ctrl で消す、Enter で確定)")
        return changed

    def activeButtons(self):
        """ビューのボタンのうち今のもの (モードとガイドの種類、対称が効いていれば対称)。"""
        active = {self.mode(), TOOL_PREFIX + self.guideTool()}
        if self.settings.value("symmetry") or self.mayaSymmetry() is not None:
            active.add("symmetry")
        if self.settings.value("bridgeRoute") == "valley":
            active.add("bridgeRoute")
        if self.settings.value("brushShape") != BRUSH_CIRCLE:
            active.add("brushShape")
        return active

    def panelButtons(self):
        """ビューのボタン [(ID, 文字)]: 対称の文字は状態で、つなぐ・切り離すは編集のモードだけ。"""
        return panel_buttons(self.buttonLabels(), self.mode())

    def buttonLabels(self):
        """状態で文字が変わるボタン {ID: 文字}: 対称 X / 対称 OFF / Maya 対称 Z。"""
        maya = self.mayaSymmetry()
        mode = self.currentSegmentMode() if self.mode() == MODE_EDIT else None
        return {"symmetry": symmetry_label(self.settings.value("symmetry"), self.settings.value("mirrorAxis"),
                                           maya[1] if maya is not None else None),
                "bridgeRoute": route_label(self.settings.value("bridgeRoute")),
                "brushShape": brush_shape_label(self.settings.value("brushShape")),
                "segmentMode": "区間: {}".format(SEGMENT_LABELS.get(mode, "-"))}

    def mayaSymmetry(self):
        """Maya の対称 (scene.mirror.maya_symmetry)。変更の通知が無いので、描くたびに読まず 0.5 秒に 1 回まで読む。"""
        now = time.perf_counter()
        cached = self._maya_symmetry_cache
        if cached is None or now - cached[0] > MAYA_SYMMETRY_INTERVAL:
            cached = self._maya_symmetry_cache = (now, maya_symmetry())
        return cached[1]

    def toggleSymmetry(self):
        """対称を切り替える (X キー・ボタン)。Maya の対称がオンの間は、切り替えても Maya の面で両側に作る。"""
        self.settings.set("symmetry", not self.settings.value("symmetry"))
        on = self.settings.value("symmetry")
        self._maya_symmetry_cache = None
        if self.mayaSymmetry() is not None:
            log.warning("Maya の対称がオンなので、ツールの対称を切り替えても両側に作ります"
                        " (Maya の対称をオフにすると、ツールの対称に従います)")
        else:
            log.info("対称: {}".format("オン ({})".format(str(self.settings.value("mirrorAxis")).upper()) if on else "オフ"))
        tool_ui.refresh()
        self._redraw()
        return True

    def toggleBrushShape(self):
        """ペイントのブラシの形を 円 -> 四角 -> 四角 (向き) と切り替える (S キー・ボタン)。"""
        order = (BRUSH_CIRCLE, BRUSH_SQUARE, BRUSH_SQUARE_STROKE)
        current = self.settings.value("brushShape")
        shape = order[(order.index(current) + 1) % len(order)] if current in order else BRUSH_CIRCLE
        self.settings.set("brushShape", shape)
        log.info("ブラシの形: {}".format({BRUSH_SQUARE: "四角 (画面で見た四角の中を塗る)",
                                          BRUSH_SQUARE_STROKE: "四角 (向き。ストロークの向きに回る)"}.get(shape, "円")))
        tool_ui.refresh()
        self._redraw()
        return True

    def _settings_changed(self, keys):
        if "seamPreview" in keys or "paintFill" in keys or "brushShape" in keys or "brushBackDepth" in keys \
                or "brushPreview" in keys or "brushPreviewAlpha" in keys \
                or keys & set(COLOR_KEYS) or keys & {"symmetry", "mirrorSpace", "mirrorAxis", "mirrorTolerance"}:
            self._redraw()
        if "mode" in keys or "guideTool" in keys:
            self.cancelBridge()                  # 描いているつなぎ線はやめる
        if ("mode" in keys or "guideTool" in keys) and self.paint is not None:
            self.finishPaint()                  # 種類・モードを替えたら、塗っている分を囲む線にする
        if "mode" in keys or "guideTool" in keys:
            self._repaint = None                # 塗り直しは 5 にしたとき (setGuideTool) に決め直す
        if "mode" in keys:
            self.commitAdjust()
            self._press = None
            self._found = []
            if self.polyline is not None:
                self.cancelPolyline()
            self.setHelpString(help_text(self.mode(), self.guideTool()))
            log.info("{} のモードにしました".format(dict(zip(definition("mode").choices,
                                                          definition("mode").choice_labels))[self.mode()]))
            tool_ui.refresh()
            self._redraw()
        if "guideTool" in keys:
            self.commitAdjust()
            self._press = None
            self._found = []
            if self.polyline is not None and self.polyline.tool != self.guideTool():
                self.cancelPolyline()
            self.setHelpString(help_text(self.mode(), self.guideTool()))
            log.info("ガイドの種類: {}".format(dict(zip(definition("guideTool").choices,
                                                     definition("guideTool").choice_labels))[self.guideTool()]))
            tool_ui.refresh()
            self._redraw()

    @property
    def selected(self):
        """最後に選んだガイド (シェイプの名前, 番号) か None。ホイールで動かす輪。"""
        return self.selection[-1] if self.selection else None

    @selected.setter
    def selected(self, key):
        self.selection = [] if key is None else [key]

    # -- 有効 / 無効 -------------------------------------------------------

    def toolOnSetup(self, event):
        self.setHelpString(help_text(self.mode(), self.guideTool()))
        self.targets = selected_targets()
        for target in self.targets:
            target.symmetrySettings = self.settings     # 対称の設定 (symmetry / mirrorSpace / mirrorAxis / mirrorTolerance)
        self.selected = self.hover = self.polyline = None
        if not self.targets:
            log.warning("メッシュを選んでからツールにしてください")
            return
        for target in self.targets:
            _plane, label = target.mirrorPlane()
            log.info("対象 {} (ガイド {} 本。対称の面: {})".format(target.name(), len(target.guides), label))
        enter_edge_mode(self.targets)      # 選択の緑のワイヤーフレームでガイドが見にくいので
        self._create_manipulator()
        self._watch()
        self.seams.clear()
        maya.utils.executeDeferred(self._prebuild)
        self.modifierState = keys.modifiers
        self.altState = keys.alt_held
        self._commit_timer = keys.single_shot(COMMIT_MS, self.commitAdjust)
        keys.install(self._on_key, wants=self._wants_key, wheel=self.wheelAt)

    def toolOffCleanup(self):
        self.commitAdjust()
        if self._commit_timer is not None:
            self._commit_timer.stop()
            self._commit_timer = None
        keys.uninstall()
        self._unwatch()
        self.deleteManipulators()
        self._manip = None
        self.targets = []
        self.selected = self.hover = self.polyline = None
        self._press = None
        self._found = []

    def _create_manipulator(self):
        self.deleteManipulators()
        manip, manip_object = SeamGuideManip.newManipulator(MANIP_NODE)
        self.addManipulator(manip_object)
        manip.setItems(self.drawItems)
        manip.setItems2d(self.drawItems2d)
        manip.setHandles(self.drawHandles)
        manip.setMeshes(self.paintMeshes)
        manip.setLabels(self.drawLabels)
        manip.setHover(self.hoverAt)
        manip.setPanel(self.activeButtons, self.panelPressed, self.panelButtons)
        self._manip = manip

    def _prebuild(self):
        """手すきのときに、メッシュの配列・隣接の表・頂点の木・ブラシの面の表 (面の中心など。20 万面で 0.5 秒) と、
        今のガイドのシームを作っておく。"""
        try:
            for target in self._valid_targets():
                arrays = target.surface.arrays()
                arrays.adjacency()
                if face_count(arrays):
                    brush_faces(arrays, arrays.points[0], 0.0, 0)     # ブラシの表 (core.region がメッシュに覚える)
                    brush_faces(arrays, arrays.points[0], 0.0)
                vertex_concavity(arrays)                              # つなぎ線の「谷」のくぼみ (20 万面で 0.2 秒)
                self.seams.paths(target)
            self._redraw()
        except Exception:
            self._report_error("シームの用意")

    def _watch(self):
        self._unwatch()
        for target in self.targets:
            node = target.path.node()
            self._callbacks.append(om.MNodeMessage.addAttributeChangedCallback(
                node, self._attribute_changed, target))
            self._callbacks.append(om.MNodeMessage.addNodeDirtyPlugCallback(node, self._dirty, target))

    def _unwatch(self):
        for callback in self._callbacks:
            try:
                om.MMessage.removeCallback(callback)
            except RuntimeError:
                pass
        self._callbacks = []

    def _attribute_changed(self, message, plug, other, target):
        if plug.partialName(useLongNames=True) != GUIDE_ATTRIBUTE:
            return
        if not self._writing and self._pending is not None and self._pending[0] is target:
            # 書く前の動かした輪がある所で、ほかの変更 (Undo など) が来た: 動かした分は捨てる
            self._pending = None
            if self._commit_timer is not None:
                self._commit_timer.stop()
            log.info("動かしていた輪を取り消しました (ほかの変更が先に来たため)")
        target.reload()
        self._forget_missing()
        maya.utils.executeDeferred(self._redraw)

    def _dirty(self, node, plug, target):
        if plug.partialName(useLongNames=True) != GUIDE_ATTRIBUTE:
            target.surface.invalidate()     # 形が変わった (配列・当てる仕組みを作り直す)

    def _forget_missing(self):
        """消えたガイド (Undo など) を選択・ホバーから外す。"""
        self.selection = [key for key in self.selection if self._guide(key) is not None]
        if self.hover is not None and self._guide(self.hover) is None:
            self.hover = None
        if self.created is not None and self._guide(self.created) is None:
            self.created = None

    def _target(self, name):
        return next((t for t in self.targets if t.name() == name and t.isValid()), None)

    def _guide(self, key):
        target = self._target(key[0])
        return target.guides.get(key[1]) if target is not None else None

    def _redraw(self):
        if self._manip is not None:
            omui.M3dView.active3dView().refresh(False, True)

    def _view(self):
        """(ワールド -> 画面の投影, (x, y) -> ワールドの視線)。"""
        if self.viewFunctions is not None:
            return self.viewFunctions
        view = omui.M3dView.active3dView()
        return projector(view), (lambda x, y: view_ray(view, x, y))

    def _valid_targets(self):
        return [t for t in self.targets if t.isValid()]

    # -- 表示 --------------------------------------------------------------

    def _highlighted(self, key):
        """選んだガイドとその対称の相手。"""
        if key is None:
            return set()
        guide = self._guide(key)
        if guide is None:
            return set()
        result = {key}
        if guide.partner is not None:
            result.add((key[0], guide.partner))
        return result

    def seamItems(self):
        """シーム (ガイドから求めたエッジ) の描くもの。設定 seamPreview がオフなら無し。"""
        if not self.settings.value("seamPreview"):
            return []
        items = []
        for target in self._valid_targets():
            points = target.surface.arrays().points
            for _guide, path in self.seams.paths(target):
                if path is not None:
                    items.append((target.surface.toWorld(points[path.vertices]), path.closed, self.color("seamColor"),
                                  SEAM_WIDTH))
        return items

    def drawItems(self):
        """マニピュレータが描くもの [(ワールドの点, 閉じているか, 色, 太さ)]。シームがいちばん下。"""
        try:
            items = self.seamItems()
        except Exception:
            items = []
            self._report_error("シームの表示")
        selected = set()
        hovered = set()
        if self.mode() == MODE_EDIT:                 # 作成のモードでは選択・ホバーを見せない
            for key in self.selection:
                selected |= self._highlighted(key)
            hovered = self._highlighted(self.hover)
        elif self.guideTool() == TOOL_BRIDGE and self.hover is not None:
            hovered = {self.hover}                   # つなぎ線: クリックすると端点になるガイド
        editing = set()
        if self._point_press is not None:           # 点を動かす線 (と相手) は前の形を描かない
            for name, ident in self._point_press["drags"]:
                editing |= self._highlighted((name, ident))
        if self.paint is not None and self.paint.ident is not None:   # 塗り直しているペイントは前の線を描かない
            editing |= self._highlighted((self.paint.target.name(), self.paint.ident))
        for target in self._valid_targets():
            for guide, world, closed in edit.world_guides(target):
                key = (target.name(), guide.ident)
                if key in editing:
                    continue                    # 点を動かしている線 (と相手) は、前の形を描かない
                if key in selected:
                    color, width = self.color("selectedColor"), SELECTED_WIDTH
                elif key in hovered:
                    color, width = self.color("hoverColor"), GUIDE_WIDTH
                else:
                    color = self.color({RING: "ringColor", CURVE: "curveColor", REGION: "regionColor",
                                        EDGE: "edgeColor", BRIDGE: "bridgeColor"}.get(
                        guide.kind, "lineColor"))
                    width = GUIDE_WIDTH
                items.append((world, closed, color, width))
        for world, closed in self._front_lines():
            # 前面 (X 線) に。黒いふちはギザギザして見にくかった (GUI で確認) ので、ふちなしの黄 (設定で変えられる)
            items.append((world, closed, self.color("paintLineColor"), SELECTED_WIDTH, True))
        items += self._brush_items()
        if self._circle_preview is not None:
            target, points = self._circle_preview
            items.append((target.surface.toWorld(points), True, PREVIEW_COLOR, SELECTED_WIDTH))
            if target.symmetric():
                plane, _label = target.mirrorPlane()
                items.append((target.surface.toWorld(reflect(points, plane)), True, PREVIEW_COLOR, GUIDE_WIDTH))
        for target, curves, _plane, _axis in self._found:
            plane, _label = target.mirrorPlane()
            symmetric = target.symmetric()
            for curve in curves:
                items.append((target.surface.toWorld(curve.points), curve.closed, PREVIEW_COLOR, SELECTED_WIDTH))
                if not symmetric:
                    continue
                # 対称の相手のプレビューは、表面に寄せずに鏡に写しただけ (ドラッグ中なので軽く)
                mirrored = target.surface.toWorld(reflect(curve.points, plane))
                items.append((mirrored, curve.closed, PREVIEW_COLOR, GUIDE_WIDTH))
        if self._point_press is not None and self._drag_drawing:
            for (name, ident), (target, anchors, _screens) in self._point_press["drags"].items():
                guide = target.guides.get(ident)
                preview = self._point_press.get("previews", {}).get((name, ident))
                if guide is None or preview is None:
                    continue
                items.append((target.surface.toWorld(preview), guide.closed, PREVIEW_COLOR, SELECTED_WIDTH, True))
                if guide.partner is not None:          # 相手は鏡に写しただけ (表面に寄せない。軽く)
                    plane, _label = target.mirrorPlane()
                    items.append((target.surface.toWorld(reflect(preview, plane)), guide.closed, PREVIEW_COLOR,
                                  GUIDE_WIDTH))
        if self.polyline is not None:
            world = self.polyline.world()
            if len(world) >= 2:
                items.append((world, False, PREVIEW_COLOR, SELECTED_WIDTH))
        items += self.bridgeItems()
        return items

    def color(self, key):
        """設定の色 (r, g, b)。"""
        return self.settings.value(key)

    def _front_lines(self):
        """前面 (X 線) に黒いふち付きで描く線 [(ワールドの点, 閉じているか)]: 塗っている間の囲む線のプレビューと、
        編集のモードで選んだペイントの囲む線 (塗った範囲の色と重なっても見えるように)。"""
        if self.paint is not None:
            if self._painting and not self._drag_drawing:
                return []   # 1 筆の途中はマニピュレータの絵 (ドラッグ中も残る) に描かず、doDrag の絵にだけ描く
            return [(self.paint.target.surface.toWorld(points), closed) for points, closed in self.paint.loops]
        lines = []
        if self.mode() == MODE_EDIT:
            for name, ident in self.selection:
                target = self._target(name)
                guide = target.guides.get(ident) if target is not None else None
                if guide is not None and guide.kind == REGION:
                    lines += [(target.surface.toWorld(points), closed) for points, closed in guide.lines()]
        return lines

    def _painting_tool(self):
        return self.mode() == MODE_CREATE and self.guideTool() == TOOL_PAINT

    def _brush_items(self):
        """ブラシの円 (volumeColorBrush と同じ: 当たった面に沿った円と、半分の円。前面に描く)。"""
        if not self._painting_tool() or self._brush_spot is None:
            return []
        if (self._painting or self._adjust is not None) and not self._drag_drawing:
            return []       # マニピュレータの絵 (ドラッグ中も押した所に残る) には描かず、doDrag の絵にだけ描く
        target, _local, center, normal = self._brush_spot
        radius = self._world_radius(self._brush_spot[0])
        if self._square_brush():
            return self._square_items(target, center, radius)
        axis = np.cross(normal, [0.0, 1.0, 0.0] if abs(normal[1]) < 0.9 else [1.0, 0.0, 0.0])
        axis /= np.linalg.norm(axis)
        other = np.cross(normal, axis)
        angles = np.linspace(0.0, 2.0 * np.pi, 48, endpoint=False)
        ring = np.cos(angles)[:, None] * axis + np.sin(angles)[:, None] * other
        color = self.color("brushColor")
        return [(center + ring * radius, True, color, 2.0, True),
                (center + ring * radius * 0.5, True, color, 1.0, True)]

    def _square_brush(self):
        return self.settings.value("brushShape") in (BRUSH_SQUARE, BRUSH_SQUARE_STROKE)

    def _square_angle(self):
        """四角の向き (ラジアン): 四角 (向き) ならストロークの向き、四角なら 0 (画面にそろう)。"""
        return self._brush_angle if self.settings.value("brushShape") == BRUSH_SQUARE_STROKE else 0.0

    def _follow_stroke(self, pos):
        """マウスの動きからブラシの向きを替える (前に替えた所から STROKE_ANGLE_PIXELS 以上動いたとき)。四角の辺が
        動く向きにそろう (向きは 180 度回しても同じ四角)。"""
        if self._brush_trail is None:
            self._brush_trail = tuple(pos)
            return
        dx, dy = pos[0] - self._brush_trail[0], pos[1] - self._brush_trail[1]
        if np.hypot(dx, dy) >= STROKE_ANGLE_PIXELS:
            self._brush_angle = float(np.arctan2(dy, dx))
            self._brush_trail = tuple(pos)

    def _square_items(self, target, center, radius):
        """四角のブラシの絵: 画面で見た四角 (と半分の四角) を、ブラシの中心の深さに置いた線。"""
        frame = self._square_frame(center, radius)
        if frame is None:
            return []
        screen, half, _view = frame
        color = self.color("brushColor")
        c, s = np.cos(self._square_angle()), np.sin(self._square_angle())
        items = []
        for scale, width in ((1.0, 2.0), (0.5, 1.0)):
            h = half * scale
            corners = [(screen[0] + (u * c - v * s) * h, screen[1] + (u * s + v * c) * h)
                       for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            items.append((np.array([self._at_depth(x, y, center, _view) for x, y in corners]), True, color, width, True))
        return items

    def _at_depth(self, x, y, world, view):
        """画面の (x, y) の視線の上で、ワールドの点 world と同じ深さ (視線の向き view に沿った距離) の点。"""
        origin, direction = (np.asarray(v, dtype=np.float64) for v in self._view()[1](x, y))
        depth = float(np.dot(np.asarray(world) - origin, view))
        along = float(np.dot(direction, view))
        return origin + direction * (depth / along if abs(along) > 1e-12 else depth)

    def _square_frame(self, world, radius):
        """四角のブラシの (画面の中心, 画面の半分の幅 (px), 視線の向き (ワールド)) か None。半分の幅は、ブラシの
        中心の深さでワールドの半径 radius が画面で何 px か。"""
        project, rays = self._view()
        screen = np.asarray(project(np.array([world], dtype=np.float64)), dtype=np.float64)[0]
        if not np.isfinite(screen).all():
            return None
        view = np.asarray(rays(*screen)[1], dtype=np.float64)
        view /= max(np.linalg.norm(view), 1e-12)
        step = 10.0
        offset = self._at_depth(screen[0] + step, screen[1], world, view)
        per_px = float(np.linalg.norm(offset - np.asarray(world))) / step
        if per_px <= 1e-12:
            return None
        return screen, radius / per_px, view

    def _brush_faces(self, target, local, world):
        """今のブラシ (円 / 四角) で、オブジェクト空間の点 local (ワールドの world) に押したら塗られる面。
        四角: 半径 x SQUARE_REACH の球の中の面のうち、面の中心が画面の四角に入る表向きの面 (core.region.square_faces)
        と、裏向きでも見えている表面のすぐ後ろの面 (_near_visible。しわの向こう側の斜面)。
        サーフェスは、そのうち当たった面からつながる面だけ (connected_faces。表面に沿った距離で切らないので、カメラに
        対して傾いた面 = 奥行きのある所も四角の端まで塗る)。ボリュームは、ブラシの中心から奥行き (視線の向き) が半径の
        中の面 (四角の箱)。当たった面は必ず入る。"""
        arrays = target.surface.arrays()
        radius = self._object_radius(target, world)
        hit_face = self._hit_face(target, local)
        if not self._square_brush():
            return brush_faces(arrays, local, radius, hit_face)
        own = target.surface.faceAt(local) if hit_face is None else hit_face
        world_radius = self._world_radius(target)
        frame = self._square_frame(world, world_radius)
        candidates = brush_faces(arrays, local, radius * SQUARE_REACH)          # 球の中 (探す範囲を絞るだけ)
        if frame is None or not len(candidates):
            return np.array([] if own is None else [own], dtype=np.int64)
        screen, half, view = frame
        project = self._view()[0]
        centers = target.surface.toWorld(face_centers(arrays)[candidates])
        points = np.asarray(project(centers), dtype=np.float64)
        ends = target.surface.toObject(np.array([world, np.asarray(world) + view]))
        view_local = ends[1] - ends[0]
        inside = np.isin(candidates, square_faces(candidates, points, screen, half, None, self._square_angle()))
        front = face_normals(arrays)[candidates] @ view_local < 0.0
        back = np.flatnonzero(inside & ~front)
        if len(back):
            front[back] = self._near_visible(target, centers[back], points[back], view,
                                             world_radius * self.settings.value("brushBackDepth"))
        allowed = inside & front
        if hit_face is None:                                                  # ボリューム: 奥行きも半径の中
            allowed &= np.abs((centers - np.asarray(world)) @ view) <= world_radius
        faces = candidates[allowed]
        if own is None:
            return faces
        if hit_face is not None:                                              # サーフェス: 当たった面とつながる面
            return connected_faces(arrays, own, faces)
        return np.union1d(faces, [own])

    def _near_visible(self, target, centers, screen, view, depth):
        """裏向きの面の中心 centers (ワールド。画面の位置 screen) のうち、カメラから見て手前の表面 (その画面の位置の
        視線が最初に当たる所) からの奥行き (視線の向き view に沿った距離) が depth 以下のもの ((n,) の bool)。
        しわ・凹凸の向こう側の斜面は手前の表面のすぐ後ろなので塗り、指の裏のように厚みの分だけ奥の面は塗らない。"""
        result = np.zeros(len(centers), dtype=bool)
        if depth <= 0.0 or not len(centers):
            return result
        rays = self._view()[1]
        lines = [rays(x, y) for x, y in screen]
        hits = target.surface.raycast([line[0] for line in lines], [line[1] for line in lines])
        found = [k for k, hit in enumerate(hits) if hit is not None]
        if not found:
            return result
        first = target.surface.toWorld([hits[k] for k in found])
        behind = (np.asarray(centers)[found] - first) @ np.asarray(view)
        result[found] = behind <= depth
        return result

    def drawLabels(self):
        """文字 [(ワールドの点, 文字)]: B で調整している間の半径。"""
        if self._adjust is None or self._brush_spot is None:
            return []
        text = "半径 {:.4g}".format(self._world_radius(self._brush_spot[0]))
        return [(tuple(self._brush_spot[2]), "  " + text)]

    def _world_radius(self, target):
        if self.brushRadius is None:
            world = target.surface.toWorld(target.surface.arrays().points)
            self.brushRadius = float(np.linalg.norm(world.max(axis=0) - world.min(axis=0))) * BRUSH_RADIUS_RATIO
        return self.brushRadius

    def _place_brush(self, pos):
        """ブラシの円を置く所をマウスの下の表面にする。外れたら円を消す。"""
        hit = self._surface_hit(pos)
        if hit is None:
            self._brush_spot = None
            return None
        target, local, world = hit
        normal_local = target.surface.normalAt(local)
        ends = target.surface.toWorld([local, local + normal_local])
        normal = ends[1] - ends[0]
        normal /= max(np.linalg.norm(normal), 1e-12)
        self._brush_spot = (target, local, world, normal)
        return hit

    def drawItems2d(self):
        """画面の 2D の線 [(点 (n, 2), 色, 太さ)]: 描いている線の、次の点までのゴム紐。"""
        if self.bridgeDraft is not None:
            return self.bridgeItems2d()
        if self.polyline is None or not len(self.polyline):
            return []
        project = self._view()[0]
        anchors = np.asarray(project(np.array(self.polyline.anchors[-1:])), dtype=np.float64)
        items = []
        if self._mouse is not None and np.isfinite(anchors[-1]).all():
            items.append(([tuple(anchors[-1]), self._mouse], STRING_COLOR, 1.0))
        return items

    def drawHandles(self):
        """点の印 [(x, y, 色)]: 描いている線の点、または選んだカーブの点 (選んだ点・動かしている点は黄色)。"""
        project = self._view()[0]
        if self.bridgeDraft is not None:
            return self.bridgeHandles()
        if self.polyline is not None and len(self.polyline):
            screen = np.asarray(project(np.array(self.polyline.anchors)), dtype=np.float64)
            return [(x, y, self.color("handleColor")) for x, y in screen if np.isfinite(x) and np.isfinite(y)]
        selected = {(t.name(), g.ident, i) for t, g, i in self.selectedPoints()}
        drags = self._point_press["drags"] if self._point_press is not None else {}
        handles = []
        for target, guide in self.editGuides():
            key = (target.name(), guide.ident)
            anchors = handle_points(guide)
            moving = set()
            if key in drags:
                anchors, moving = drags[key][1], set(drags[key][2])
                if not self._drag_drawing:
                    # マニピュレータの絵には、動かす点を描かない (ドラッグ中も残るため)
                    anchors = [a for i, a in enumerate(anchors) if i not in moving]
                    index_map = [i for i in range(len(drags[key][1])) if i not in moving]
                else:
                    index_map = list(range(len(anchors)))
            else:
                index_map = list(range(len(anchors)))
            screen = np.asarray(project(target.surface.toWorld(anchors)), dtype=np.float64) if len(anchors) else []
            ends = attached_indices(guide)                 # ほかのガイドに乗っている点はひし形
            for (x, y), index in zip(screen, index_map):
                if np.isfinite(x) and np.isfinite(y):
                    chosen = (key + (index,)) in selected or index in moving
                    color = self.color("handleSelectedColor" if chosen else "handleColor")
                    handles.append((x, y, color, "diamond") if index in ends else (x, y, color))
        return handles

    def hoverAt(self, x, y):
        """マウスの移動 (マニピュレータの doMove から)。描き直しが要るなら True。
        折れ線を描いている間はゴム紐を追う。それ以外はマウスの下のガイドを強調する。"""
        self.cursor = (x, y)
        if self.polyline is not None:
            self._mouse = (x, y)
            return True
        if self._painting_tool():
            if self._adjust is None:
                self._follow_stroke((x, y))     # 四角 (向き): 動かしている向きに回す (塗る前から見える)
                self._place_brush((x, y))       # ブラシの円を追う
            return True
        bridging = self.mode() == MODE_CREATE and self.guideTool() == TOOL_BRIDGE
        if bridging:
            self._mouse = (x, y)                # つなぎ線: ゴム紐を追い、マウスの下のガイド (端点になる所) を強調
        if self._press is not None or not self.targets or (self.mode() != MODE_EDIT and not bridging):
            return bridging and self.bridgeDraft is not None
        try:
            target, ident = edit.pick_guide(self._valid_targets(), self._view()[0], x, y, PICK_PIXELS)
        except RuntimeError:
            return False
        key = (target.name(), ident) if target is not None else None
        if key == self.hover:
            return bridging and self.bridgeDraft is not None   # ゴム紐は描き直す
        self.hover = key
        return True

    # -- マウス ------------------------------------------------------------

    def doPress(self, event, drawMgr, context):
        if event.mouseButton() != omui.MEvent.kLeftMouse or not self.targets:
            return
        self.press(event_position(event), event.isModifierControl(), event.isModifierShift())

    def doDrag(self, event, drawMgr, context):
        self.drag(event_position(event), drawMgr)

    def doRelease(self, event, drawMgr, context):
        self.release(event_position(event))

    def press(self, pos, step=False, shift=False):
        self.commitAdjust()
        self._error_shown = False
        self._point_press = None
        handle = self.handleAt(*pos) if self.polyline is None and self.mode() == MODE_EDIT else None
        if handle is not None:
            self._begin_point_press(handle)
        self._press = tuple(pos)
        self._marquee = self.mode() == MODE_EDIT
        self._tool = self.guideTool()
        self._line = not self._marquee and self._tool == TOOL_FREEHAND
        self._painting = not self._marquee and self._tool == TOOL_PAINT
        if self._painting and "b" in self._held():
            self._painting = False
            self._begin_adjust(pos)
        elif self._painting:
            self._paint_press(pos)
        self._step = bool(step)
        self._shift_press = bool(shift)
        self._circle = not self._marquee and self._tool == TOOL_RING and self._ctrl()
        self._circle_preview = None
        self._circle_center = tuple(pos)
        self._circle_radius = 0.0
        self._circle_last = tuple(pos)
        self._rect = None
        self._dragged = False
        self._samples = [self._press]
        self._brush = LazyBrush(self._press, LAZY_PIXELS)
        self._end = None
        self._found = []
        self._project, self._rays = self._view()

    def _ctrl(self):
        """Ctrl (15 度刻み) を押しているか。今の状態が読めればそれ、読めなければ押したときの状態。"""
        if self.modifierState is not None:
            try:
                return bool(self.modifierState()[1])
            except Exception:
                pass
        return self._step

    def _shift(self):
        """Shift (1 リングの 15 度刻み) を押しているか。今の状態が読めればそれ、読めなければ押したときの状態。"""
        if self.modifierState is not None:
            try:
                return bool(self.modifierState()[0])
            except Exception:
                pass
        return self._shift_press

    def _alt(self):
        """Alt を押しているか (円のドラッグ中の移動)。読めなければ False。"""
        if self.altState is not None:
            try:
                return bool(self.altState())
            except Exception:
                pass
        return False

    def _circle_follow(self, pos):
        """円のドラッグ: Alt を押している間は、前のマウスの位置からの動きだけ中心を動かし (半径はそのまま)、押して
        いなければ中心からマウスまでの距離を半径にする。前の位置からの差で動かすので、マウスと中心の位置関係は
        半径を決めた最後の時と同じに保たれ、Alt を離しても半径は飛ばない (Alt を押した最初の動きも移動に数える)。"""
        last, self._circle_last = self._circle_last, tuple(pos)
        center = self._circle_center
        if self._alt():
            if last is not None:
                self._circle_center = (center[0] + pos[0] - last[0], center[1] + pos[1] - last[1])
        else:
            self._circle_radius = float(np.hypot(pos[0] - center[0], pos[1] - center[1]))

    def _circle_at(self, center, radius):
        """画面の円 (中心 center、半径 radius) を落とした (target, 円の点 CIRCLE_NODES 個 (オブジェクト空間),
        円の画面の点) か (None, None, 画面の点)。半径が DRAG_PIXELS 未満なら作らない。"""
        angles = np.linspace(0.0, 2.0 * np.pi, CIRCLE_SAMPLES, endpoint=False)
        screen = [(center[0] + radius * np.cos(a), center[1] + radius * np.sin(a)) for a in angles]
        if radius < DRAG_PIXELS:
            return None, None, screen
        found = edit.circle_hits(self._valid_targets(), [self._rays(x, y) for x, y in screen])
        if found is None:
            return None, None, screen
        target, points = found
        step = CIRCLE_SAMPLES // CIRCLE_NODES
        return target, points[::step][:CIRCLE_NODES], screen

    def drag(self, pos, drawMgr=None):
        if self._press is None:
            return
        try:
            self._drag(tuple(pos), drawMgr)
        except Exception:
            self._report_error("ドラッグ")

    def _drag(self, pos, drawMgr):
        start = self._press
        if self._point_press is not None:
            self._drag_point(pos, drawMgr)
            return
        if self._adjust is not None:
            self._adjust_to(pos, drawMgr)
            return
        if self._painting:
            self._paint_drag(pos, drawMgr)
            return
        if self.polyline is not None or (not self._marquee and self._tool in POINT_TOOLS + (TOOL_BRIDGE,)):
            return                       # ライン・カーブ・つなぎ線: ドラッグしても点を置くだけ (離したとき)
        if not self._dragged and max(abs(pos[0] - start[0]), abs(pos[1] - start[1])) < DRAG_PIXELS:
            return
        self._dragged = True
        if self._marquee:
            self._rect = (min(start[0], pos[0]), min(start[1], pos[1]), max(start[0], pos[0]), max(start[1], pos[1]))
            if drawMgr is not None:
                left, bottom, right, top = self._rect
                draw_stroke(drawMgr, [(left, bottom), (right, bottom), (right, top), (left, top), (left, bottom)],
                            STROKE_COLOR, 1.0)
        elif self._line:
            tip = self._brush.follow(pos)
            last = self._samples[-1]
            if tip is not None and max(abs(tip[0] - last[0]), abs(tip[1] - last[1])) >= SAMPLE_PIXELS:
                self._samples.append(tip)
            if drawMgr is not None:
                draw_stroke(drawMgr, self._samples)
                draw_stroke(drawMgr, [self._brush.position, pos], STRING_COLOR, 1.0)   # ひも
        elif self._circle:
            self._circle_follow(pos)
            target, anchors, screen = self._circle_at(self._circle_center, self._circle_radius)
            self._circle_preview = None if target is None else (target, edit.curve_points(target, anchors, True))
            if drawMgr is not None:
                draw_stroke(drawMgr, screen + screen[:1], STROKE_COLOR if target is not None else ERASE_PREVIEW_COLOR)
        else:
            end = snap_angle(start, pos, STEP_DEGREES) if self._shift() else pos
            self._end = end
            self._found = edit.find_rings(self._valid_targets(), self._rays(*start), self._rays(*end),
                                          start, end, self._project)
            if drawMgr is not None:
                draw_stroke(drawMgr, [start, end])
        if self._manip is not None and drawMgr is not None:
            self._manip.renderInto(drawMgr)

    def release(self, pos):
        """離した: クリックなら選ぶ / 折れ線、ドラッグならガイドを足す。足した {シェイプ: [番号]}。"""
        if self._press is None:
            return {}
        press, self._press = self._press, None
        step = self._ctrl()
        added = {}
        try:
            if self._point_press is not None:
                self._release_point()
            elif self._adjust is not None:
                self._end_adjust()
            elif self._painting:
                self._painting = False
                self._paint_release()
            elif self._marquee:
                plain = not self._dragged and not any(self._modifiers())
                if not (plain and (self.insertPointAt(*press) or self.extendAt(*press))):
                    self._select_release(press)        # 編集: 選ぶ (点を足す・端から伸ばす以外)
            elif self.polyline is not None or self._tool in POINT_TOOLS:
                added = self.polylineClick(tuple(pos), step)
            elif self._tool == TOOL_BRIDGE:
                added = self.bridgeClick(*press)       # 6 つなぎ線: クリックで端点・中継点
            elif not self._dragged:
                pass                                    # 作成のリング・ペイントのクリックは何もしない (選ぶのは編集)
            elif self._circle:
                self._circle_follow(tuple(pos))
                target, anchors, _screen = self._circle_at(self._circle_center, self._circle_radius)
                if target is None:
                    log.info("円がメッシュからはみ出しています (円の全体がメッシュの上に乗るように描いてください)")
                else:
                    added = edit.add_circle(target, anchors)
                    self._report(added, "円")
                    self._remember_created(added)
            elif self._line:
                tip = self._brush.position              # レイジーマウス: 線はペン先で終わる
                if tip != self._samples[-1]:
                    self._samples.append(tip)
                added = edit.add_lines(self._valid_targets(), [self._rays(x, y) for x, y in self._samples])
                self._report(added, "補助線")
                self._remember_created(added)
            else:
                end = snap_angle(press, tuple(pos), STEP_DEGREES) if self._shift() else tuple(pos)
                found = edit.find_rings(self._valid_targets(), self._rays(*press), self._rays(*end),
                                        press, end, self._project)
                if not found:
                    log.info("線の範囲に輪切りの線がありません (筒を横切るように描いてください)")
                added = edit.add_rings(found)
                self._report(added, "輪切り")
                self._remember_created(added)           # 編集に替えるとすぐ直せる
        except Exception:
            self._report_error("離す")
        finally:
            self._found = []
            self._circle = False
            self._circle_preview = None
            self._circle_last = None
            self._samples = []
            self._point_press = None
            self._redraw()
        return added

    # -- 点の編集 (選んだ線の置いた点。いくつでも選べる) --------------------

    def editGuides(self):
        """点の印を出す線 [(target, ガイド)]: 編集のモードで選んでいる線のうち、カーブ・ライン・開いたペイント。
        対称の相手どうしを両方選んでいれば片方だけ (相手は編集した線から作り直されるため)。"""
        if self.mode() != MODE_EDIT:
            return []
        result, seen = [], set()
        for name, ident in self.selection:
            target = self._target(name)
            guide = target.guides.get(ident) if target is not None else None
            if guide is None or handle_points(guide) is None or (name, ident) in seen:
                continue
            seen.add((name, ident))
            if guide.partner is not None:
                seen.add((name, guide.partner))
            result.append((target, guide))
        return result

    def editGuide(self):
        """点の印を出す線が 1 本だけならその (target, ガイド)、そうでなければ None。"""
        found = self.editGuides()
        return found[0] if len(found) == 1 else None

    def editCurve(self):
        """点を動かす・足す・消せる線 (置いた点を持つカーブ・ライン) が 1 本だけならその (target, ガイド)。"""
        found = self.editGuide()
        return found if found is not None and found[1].anchors else None

    def selectedPoints(self):
        """選んでいる点 [(target, ガイド, 番号)] (今も点の印が出ているものだけ)。"""
        guides = {(target.name(), guide.ident): (target, guide) for target, guide in self.editGuides()}
        result = []
        for name, ident, index in self.pointSelection:
            found = guides.get((name, ident))
            if found is not None and 0 <= index < len(handle_points(found[1])):
                result.append((found[0], found[1], index))
        return result

    def _selected_point(self):
        """選んでいる点が 1 つだけならその番号 (その線の点の印の番号)、そうでなければ None。"""
        points = self.selectedPoints()
        return points[0][2] if len(points) == 1 else None

    def _selected_end(self):
        """選んでいる点が 1 つだけで端なら (target, ガイド, 始点の側か)。そうでなければ None。"""
        points = self.selectedPoints()
        if len(points) != 1:
            return None
        target, guide, index = points[0]
        if guide.closed or index not in (0, len(handle_points(guide)) - 1):
            return None
        return target, guide, index == 0

    def handleAt(self, x, y):
        """画面の (x, y) の近く (PICK_PIXELS) にある点の印 (target, ガイド, 番号) か None (いちばん近いもの)。"""
        project = self._view()[0]
        best = None
        for target, guide in self.editGuides():
            if not len(handle_points(guide)):
                continue
            screen = np.asarray(project(target.surface.toWorld(handle_points(guide))), dtype=np.float64)
            distance = np.hypot(screen[:, 0] - x, screen[:, 1] - y)
            distance[~np.isfinite(distance)] = np.inf
            index = int(np.argmin(distance))
            if distance[index] <= PICK_PIXELS and (best is None or distance[index] < best[0]):
                best = (distance[index], target, guide, index)
        return None if best is None else best[1:]

    def _begin_point_press(self, handle):
        """点を押した: 動かす点を決める (選んでいる点を押したら選んでいる点すべて、そうでなければ押した点だけ)。"""
        target, guide, index = handle
        key = (target.name(), guide.ident, index)
        keys = [(t.name(), g.ident, i) for t, g, i in self.selectedPoints()]
        moving = keys if key in keys else [key]
        project = self._view()[0]
        drags = {}
        for name, ident, idx in moving:
            owner = self._target(name)
            line = owner.guides.get(ident)
            if line is None:
                continue
            points = handle_points(line)
            entry = drags.setdefault((name, ident), (owner, [tuple(p) for p in points], {}))
            screen = np.asarray(project(owner.surface.toWorld([points[idx]])), dtype=np.float64)[0]
            entry[2][idx] = tuple(screen)
        self._point_press = {"key": key, "drags": drags, "previews": {}, "attach": {}}
        self._redraw()          # 動かす線を外した絵にしておく (ドラッグ中、マニピュレータは描き直されない)

    def _drag_point(self, pos, drawMgr):
        """点のドラッグ: 動かす点を、押したときの画面の位置からマウスの動きだけずらした所の表面 (同じメッシュ) へ。
        作り直した線を見せる (書くのは離したとき)。"""
        start = self._press
        if not self._dragged and max(abs(pos[0] - start[0]), abs(pos[1] - start[1])) < DRAG_PIXELS:
            return
        drags = self._point_press["drags"]
        if not drags:
            return                              # 置いた点の無い補助線の端は動かさない (クリックで選んで伸ばす)
        self._dragged = True
        dx, dy = pos[0] - start[0], pos[1] - start[1]
        attach = self._end_attach(pos)
        self._point_press["attach"] = attach
        for (name, ident), (owner, anchors, screens) in drags.items():
            moves = {}
            for idx, (sx, sy) in screens.items():
                hit = owner.surface.raycast(*zip(self._rays(sx + dx, sy + dy)))[0]
                if hit is not None:
                    moves[idx] = tuple(hit)
            if not moves:
                continue
            path = edit.moved_path(owner, owner.guides, ident, moves, attach.get((name, ident)))
            if path is None:
                continue
            for idx in moves:                          # 点の印は吸い付いた所 (ガイドの上・頂点)
                anchors[idx] = tuple(path.nodes[idx].position)
            self._point_press["previews"][(name, ident)] = path.line()
        if drawMgr is not None and self._manip is not None:
            self._drag_drawing = True
            try:
                self._manip.renderInto(drawMgr)
            finally:
                self._drag_drawing = False

    def _release_point(self):
        press, self._point_press = self._point_press, None
        key = press["key"]
        if self._dragged:
            moved = []
            with undo_chunk("点を動かす"):
                for (name, ident), (owner, anchors, screens) in press["drags"].items():
                    if edit.move_points(owner, ident, {idx: anchors[idx] for idx in screens},
                                        attach=press.get("attach", {}).get((name, ident))):
                        moved += [(name, ident, idx) for idx in screens]
            if moved:
                self.pointSelection = moved
                log.info("点を {} 個動かしました (対称の相手も)".format(len(moved)))
            return
        shift, ctrl = self._modifiers()
        if ctrl and not shift:                  # Ctrl+クリック: その点を消す
            self.pointSelection = [key]
            self.deletePoints()
            return
        keys = [(t.name(), g.ident, i) for t, g, i in self.selectedPoints()]
        if shift and ctrl:
            keys = keys + [key] if key not in keys else keys
        elif shift:
            keys = [k for k in keys if k != key] if key in keys else keys + [key]
        else:
            keys = [key]
        self.pointSelection = keys
        log.info("点を {} 個選んでいます (ドラッグで動かす、Delete で消す、「切り離す」、端 1 つならメッシュのクリックで"
                 "伸ばす)".format(len(keys)))

    def selectPointsInRect(self, rect, op=REPLACE):
        """画面の矩形 (左, 下, 右, 上) に入る点の印を選ぶ。入る点が無ければ False (ガイドを選ぶ)。"""
        left, bottom, right, top = rect
        project = self._view()[0]
        found = []
        for target, guide in self.editGuides():
            if not len(handle_points(guide)):
                continue
            screen = np.asarray(project(target.surface.toWorld(handle_points(guide))), dtype=np.float64)
            for index, (x, y) in enumerate(screen):
                if left <= x <= right and bottom <= y <= top:
                    found.append((target.name(), guide.ident, index))
        if not found:
            return False
        keys = [(t.name(), g.ident, i) for t, g, i in self.selectedPoints()]
        if op == REPLACE:
            keys = found
        else:
            for key in found:
                if key in keys and op in (TOGGLE, REMOVE):
                    keys.remove(key)
                elif key not in keys and op in (TOGGLE, ADD):
                    keys.append(key)
        self.pointSelection = keys
        log.info("点を {} 個選んでいます".format(len(keys)))
        return True

    def extendAt(self, x, y):
        """端の点を 1 つ選んでいるとき、ガイドの無いメッシュの上のクリックで、その端からそこまで伸ばす。
        曲線の区間の端は点を足して曲線で、直線の区間の端は画面の直線をそのときの視点で表面に落とした区間を足す
        (作成のラインと同じ)。伸ばした先が新しい端として選ばれ、続けてクリックで伸ばせる。伸ばしたら True。"""
        found = self._selected_end()
        if found is None:
            return False
        target, guide, at_start = found
        project, rays = self._view()
        targets = self._valid_targets()
        if edit.pick_guide(targets, project, x, y, PICK_PIXELS)[0] is not None:
            return False                        # ガイドの上: 選ぶ (伸ばさない)
        hit = target.surface.raycast(*zip(rays(x, y)))[0]
        if hit is None:
            return False
        end_mode = guide.path.segments[0 if at_start else -1].mode if guide.path.segments else "straight"
        if end_mode not in ("straight", "fixed"):        # 端の区間が曲線・エッジの道: 点を足して同じ作り方で伸ばす
            if edit.extend_path(target, guide.ident, hit, at_start):
                self._select_new_end(target, guide.ident, at_start)
                log.info("{}から伸ばしました".format("始点" if at_start else "終点"))
            return True
        end = guide.points[0] if at_start else guide.points[-1]
        start = tuple(np.asarray(project(target.surface.toWorld([end])), dtype=np.float64)[0])
        index = targets.index(target)
        hits = edit.cast_rays(targets, [rays(px, py) for px, py in segment_points(start, (x, y), SAMPLE_PIXELS)])
        points = [h[1] for h in hits if h is not None and h[0] == index]
        if not hits or hits[-1] is None or hits[-1][0] != index or not points:
            log.info("伸ばす先はメッシュの上に置いてください (途中でメッシュから外れない所)")
            return True
        if edit.extend_path(target, guide.ident, hits[-1][1], at_start, points=points[:-1]):
            self._select_new_end(target, guide.ident, at_start)
            log.info("{}から伸ばしました".format("始点" if at_start else "終点"))
        return True

    def _select_new_end(self, target, ident, at_start):
        guide = target.guides.get(ident)
        if guide is not None and guide.anchors:
            self.pointSelection = [(target.name(), ident, 0 if at_start else len(guide.anchors) - 1)]

    def insertPointAt(self, x, y):
        """ガイドを 1 本だけ選んでいるとき、その線の上 (PICK_PIXELS 以内) のクリックで点を足す。足したら True。
        何本か選んでいるときのクリックは選び直し (足すと思わぬ線の形が変わるため)。"""
        found = self.editGuide()
        if found is None:
            return False
        target, guide = found
        project, rays = self._view()
        if edit.screen_distance(target, guide, project, x, y) > PICK_PIXELS:
            return False
        hit = target.surface.raycast(*zip(rays(x, y)))[0]
        if hit is None:
            return False
        index = edit.insert_point(target, guide.ident, hit)
        if index is not None:
            self.pointSelection = [(target.name(), guide.ident, index)]
            log.info("点を足しました ({} 番目)".format(index + 1))
        return True

    def deletePoints(self):
        """選んでいる点を消す (線ごとに、開いた線は 2 点・閉じた線は 3 点まで残す)。消そうとしたら True。"""
        points = self.selectedPoints()
        if not points:
            return False
        groups = {}
        for target, guide, index in points:
            groups.setdefault((target.name(), guide.ident), (target, guide, []))[2].append(index)
        deleted = 0
        with undo_chunk("点を消す"):
            for target, guide, indices in groups.values():
                remaining = len(guide.anchors) - len(set(indices))
                if guide.kind == RING and guide.plane is not None and guide.closed and remaining < 3:
                    if edit.reset_rings(target, [guide.ident]):
                        deleted += len(set(indices))
                        log.info("輪の点が少なくなったので、断面の輪に戻しました")
                    continue
                if remaining < (3 if guide.closed else 2):
                    log.info("これ以上点を消せません (線ごと消すなら点の選択を外して Delete)")
                    continue
                if edit.delete_points(target, guide.ident, indices):
                    deleted += len(set(indices))
        if deleted:
            self.pointSelection = []
            log.info("点を {} 個消しました".format(deleted))
        return True

    deletePoint = deletePoints                  # 前の名前 (1 点)

    def joinSelected(self):
        """編集: 選んだ 2 本の近い端どうしをつないで 1 本にする (1 本なら閉じる)。つないだ線を選ぶ。番号か None。"""
        if self.mode() != MODE_EDIT:
            log.info("つなぐのは編集のモードで、線を 1〜2 本選んでから")
            return None
        keys = list(self.selection)                  # 自分の対称の相手ともつなげる (中心をまたぐ 1 本の線になる)
        if len(keys) not in (1, 2) or len({name for name, _ident in keys}) != 1:
            log.info("つなぐ線を 1 本 (閉じる) か、同じメッシュの 2 本選んでください")
            return None
        target = self._target(keys[0][0])
        joined = edit.join_guides(target, keys[0][1], keys[1][1] if len(keys) == 2 else None)
        if joined is None:
            log.info("つなげません (閉じた線はつなげない。閉じるには 3 点以上)")
            return None
        self.selection = [(target.name(), joined)]
        self.pointSelection = []
        log.info("線を{}しました (対称の相手も作り直す)".format("つないで 1 本に" if len(keys) == 2 else "閉じた線に"))
        return joined

    def splitAtPoint(self):
        """編集の「切り離す」: 点を 1 つ選んでいればその点で切り離す (開いた線は 2 本に、閉じた線は開く)。
        2 つ以上選んでいれば、両端の点をどちらも選んでいる区間 (隣り合う 2 点の間) を消して分ける。
        できた線の番号のリストか None。"""
        points = self.selectedPoints()
        if not points:
            log.info("切り離すのは、線の点を選んでから")
            return None
        if len(points) == 1:
            target, guide, index = points[0]
            parts = edit.split_guide(target, guide.ident, index)
            if parts is None:
                log.info("端の点では切り離せません")
                return None
        else:
            groups = {}
            for target, guide, index in points:
                groups.setdefault((target.name(), guide.ident), (target, guide, set()))[2].add(index)
            parts = []
            with undo_chunk("線を切り離す"):
                for target, guide, indices in groups.values():
                    count = len(guide.anchors)
                    segments = [i for i in range(count if guide.closed else count - 1)
                                if i in indices and (i + 1) % count in indices]
                    if segments:
                        parts += edit.cut_segments(target, guide.ident, segments) or []
            if not parts:
                log.info("隣り合う 2 点を選んでください (その間の区間を消します)")
                return None
            target = points[0][0]
        self.selection = [(target.name(), parts[0])]
        self.pointSelection = []
        log.info("線を切り離しました ({} 本)".format(len(parts)))
        return parts

    # -- ペイント (塗った範囲を囲む線) -----------------------------------------

    def _repaint_region(self):
        """塗り直すペイント (target, ガイド) か None (編集のモードで選んで 5 にしたときだけ。_repaint)。"""
        if self._repaint is None:
            return None
        target = self._target(self._repaint[0])
        guide = self._guide(self._repaint) if target is not None else None
        return (target, guide) if guide is not None and guide.kind == REGION else None

    def _selected_region(self):
        """ペイントのガイドを 1 本だけ選んでいれば (target, ガイド)。"""
        if len(self.selection) != 1:
            return None
        target = self._target(self.selection[0][0])
        guide = self._guide(self.selection[0])
        return (target, guide) if target is not None and guide is not None and guide.kind == REGION else None

    def resizePaint(self, grow=True):
        """塗った範囲をブラシの半径の RESIZE_RATIO 倍だけ広げる / 狭める (> / <)。塗っている途中が無ければ、選んだペイントから塗り直しを始める。
        1 筆として数える (Ctrl+Z で戻す)。変えたら True。"""
        if self.paint is None:
            found = self._repaint_region()
            if found is None:
                return False
            target, guide = found
            self.paint = PaintSession(target, edit.region_faces(target, guide), guide.ident)
        target = self.paint.target
        arrays = target.surface.arrays()
        step = self._resize_step(target)
        self.paint.begin_stroke()
        changed = (grow_faces if grow else shrink_faces)(arrays, self.paint.faces, step)
        self.paint.version += 1
        self._paint_release()
        log.info("塗った範囲を{}ました ({} 面)。Enter で囲む線にする".format("広げ" if grow else "狭め", changed))
        self._redraw()
        return True

    def _resize_step(self, target):
        """> / < で広げる・狭める距離 (オブジェクト空間): ブラシの半径の RESIZE_RATIO 倍 (辺の長さの中央値より小さくしない)。"""
        origin = target.surface.toWorld(target.surface.arrays().points[:1])[0]
        ends = target.surface.toObject([origin, origin + np.array([self._world_radius(target), 0.0, 0.0])])
        radius = float(np.linalg.norm(ends[1] - ends[0]))
        return max(radius * RESIZE_RATIO, target.surface.arrays().medianEdge())

    def _paint_press(self, pos):
        """ペイントの 1 筆を始める: 塗っている途中が無ければ始める (ペイントのガイドを 1 本選んでいれば、その塗った量
        から塗り直す)。押した所を塗る。"""
        hit = self._place_brush(pos)
        if self.paint is None:
            if hit is None:
                self._painting = False
                return
            target = hit[0]
            ident, faces = None, np.zeros(face_count(target.surface.arrays()))
            found = self._repaint_region()               # 塗り直しは編集で選んで 5 にしたときだけ (確定した直後の
            if found is not None and found[0] is target:  # 選択では続きにしない)
                ident, faces = found[1].ident, edit.region_faces(target, found[1])
            self.paint = PaintSession(target, faces, ident)
            log.info("ペイントを{}ました。ドラッグで塗る (Ctrl で消す)、B+ドラッグでブラシの大きさ、Enter で囲む線にする、"
                     "Esc でやめる".format("塗り直し" if ident is not None else "始め"))
        self.paint.begin_stroke()
        self._redraw()           # 塗っている面を外した絵にしておく (ドラッグ中、マニピュレータは描き直されない)
        self._last_stamp = None
        if hit is not None:
            self._stamp(pos, hit)
            self._last_stamp = tuple(pos)

    def _stamp_points(self, pos):
        """前に押した所から pos までの間に押す画面の点 (両端は含まない)。間隔はブラシの画面の半径 x STAMP_SPACING
        (MAX_STAMPS まで)。"""
        last = self._last_stamp
        if last is None or self._brush_spot is None:
            return []
        frame = self._square_frame(self._brush_spot[2], self._world_radius(self._brush_spot[0]))
        if frame is None:
            return []
        spacing = max(frame[1] * STAMP_SPACING, 2.0)
        count = min(int(np.hypot(pos[0] - last[0], pos[1] - last[1]) // spacing), MAX_STAMPS)
        return [(last[0] + (pos[0] - last[0]) * k / (count + 1), last[1] + (pos[1] - last[1]) * k / (count + 1))
                for k in range(1, count + 1)]

    def _surface_hit(self, pos):
        """画面の pos の下の表面 (target, オブジェクト空間の点, ワールドの点) か None。"""
        rays = self._view()[1]
        hits = edit.cast_rays(self._valid_targets(), [rays(*pos)])
        if not hits or hits[0] is None:
            return None
        index, local, world = hits[0]
        return self._valid_targets()[index], np.asarray(local), np.asarray(world)

    def _brush_radius(self, pos, hit):
        """ブラシの半径 (ワールド) を、当たった所でのオブジェクト空間の長さにする (スケールの付いたメッシュ)。"""
        return self._object_radius(hit[0], hit[2])

    def _object_radius(self, target, world):
        """ブラシの半径 (ワールド) の、ワールドの点 world でのオブジェクト空間の長さ。"""
        world = np.asarray(world, dtype=np.float64)
        radius = self._world_radius(target)
        ends = target.surface.toObject([world, world + np.array([radius, 0.0, 0.0])])
        return float(np.linalg.norm(ends[1] - ends[0]))

    def _held(self):
        """押している B / V の集合 (keys.HELD。テストでは heldKeys で差し替える)。"""
        return self.heldKeys() if self.heldKeys is not None else set(keys.HELD)

    def _begin_adjust(self, pos):
        """B + 左ドラッグ: 半径を変え始める (塗らない。Esc で戻す)。"""
        if self._brush_spot is None:
            self._place_brush(pos)
        target = self._brush_spot[0] if self._brush_spot is not None else (self._valid_targets() or [None])[0]
        if target is None:
            return
        self._adjust = {"x": float(pos[0]), "start": self._world_radius(target)}
        self._redraw()      # 押した所の円を外した絵にしておく

    def _adjust_to(self, pos, drawMgr):
        adjust = self._adjust
        dx = float(pos[0]) - adjust["x"]
        self.brushRadius = adjust["start"] * 2.0 ** (dx / RADIUS_DRAG_PIXELS)
        if drawMgr is not None and self._manip is not None:
            self._drag_drawing = True
            try:
                self._manip.renderInto(drawMgr)
            finally:
                self._drag_drawing = False

    def _end_adjust(self):
        self._adjust = None
        log.info("ブラシの半径: {:.4g}".format(self.brushRadius))

    def _cancel_adjust(self):
        """Esc: 調整を始める前の値に戻す。"""
        adjust, self._adjust = self._adjust, None
        self._press = None
        if adjust is None:
            return
        self.brushRadius = adjust["start"]
        self._redraw()

    def _stamp(self, pos, hit):
        target = hit[0]
        if target is not self.paint.target:
            return                              # 塗り始めたメッシュだけ
        index = self._brush_faces(target, hit[1], hit[2])
        if len(index):
            self.paint.faces[index] = 0.0 if self._ctrl() else 1.0
        self.paint.version += 1

    def _hit_face(self, target, local):
        """サーフェスのブラシなら当たった面の番号 (そこから表面に沿って塗る)、ボリュームなら None。"""
        if self.settings.value("brushMode") == BRUSH_SURFACE:
            return target.surface.faceAt(local)
        return None

    def brushPreviewFaces(self):
        """(target, 面の番号, 消すか): 今押したら塗られる (Ctrl なら消される) 面。ブラシの円が無ければ None。"""
        if not self._painting_tool() or self._brush_spot is None:
            return None
        target, local, center, _normal = self._brush_spot
        if self.paint is not None and target is not self.paint.target:
            return None                         # 塗り始めたメッシュだけ塗る
        return target, self._brush_faces(target, local, center), self._ctrl()

    def _paint_drag(self, pos, drawMgr):
        if self.paint is None:
            return
        self._dragged = True
        self._follow_stroke(pos)
        for point in self._stamp_points(pos):                    # 速く動かしても間が空かないよう、間も押す
            hit = self._surface_hit(point)
            if hit is not None:
                self._stamp(point, hit)
        hit = self._place_brush(pos)
        if hit is not None:
            self._stamp(pos, hit)
            self._last_stamp = tuple(pos)
        self._update_loops()
        if drawMgr is not None and self._manip is not None:
            self._drag_drawing = True
            try:
                self._manip.renderInto(drawMgr)
            finally:
                self._drag_drawing = False

    def _paint_release(self):
        """1 筆を終えた: 囲む線のプレビューを作り直す。"""
        if self.paint is None:
            return
        self._update_loops(force=True)

    def _update_loops(self, force=False):
        """囲む線のプレビューを作り直す。ドラッグ中 (force でない) は間引く: 前に作り終えてから、
        max(LOOPS_INTERVAL, かかった時間 x 2) 秒たつまで作らない (重いメッシュでもドラッグが重くならないように)。"""
        paint = self.paint
        if paint is None or (paint.loops_version == paint.version and not force):
            return
        now = time.perf_counter()
        if not force and now - paint.loops_time < max(LOOPS_INTERVAL, paint.loops_cost * 2.0):
            return
        target = paint.target
        paint.loops = region_loops(target.surface.arrays(), paint.faces)
        paint.loops_version = paint.version
        paint.loops_time = time.perf_counter()
        paint.loops_cost = paint.loops_time - now

    def finishPaint(self):
        """塗った範囲を囲む線のガイドにする (塗り直しならそのガイドを作り直す)。足した / 直した {シェイプ: [番号]}。"""
        paint, self.paint = self.paint, None
        self._painting = False
        self._repaint = None                     # 次の 1 筆は新しいペイント
        if paint is None:
            return {}
        target = paint.target
        self._report_unmatched(target, paint.faces)
        if paint.ident is not None:
            if edit.set_region(target, paint.ident, paint.faces):
                log.info("ペイントを塗り直しました (対称の相手も)")
            self._redraw()
            return {target.name(): [paint.ident]}
        if not np.any(paint.faces > 0):
            self._redraw()
            return {}
        added = edit.add_region(target, paint.faces)
        if added:
            self._report(added, "ペイント")
            self._remember_created(added)
        else:
            log.info("塗った範囲が小さすぎて囲む線になりません (もう少し広く塗ってください)")
        self._redraw()
        return added

    def _report_unmatched(self, target, faces):
        """対称の相手を作るとき、左右で形が違って対応しなかった面の数を知らせる (近い面で写す)。"""
        try:
            if not target.symmetric() or not np.any(faces > 0):
                return
            _mirrored, unmatched = edit.region_mirror(target, faces)
        except Exception:
            self._report_error("対称の相手")
            return
        if unmatched:
            log.info("対称の相手: 左右で形が違い、許容値の中に反対側の面が無い所が {} 面ありました"
                     " (いちばん近い面で写しました。許容値は設定の「対称」)".format(unmatched))

    def cancelPaint(self):
        had = self.paint is not None
        self.paint = None
        self._painting = False
        self._repaint = None
        if had:
            log.info("ペイントをやめました")
        self._redraw()
        return had

    def undoStroke(self):
        """塗っている途中の 1 筆を戻す (無くなったらやめる)。"""
        if self.paint is None:
            return False
        if not self.paint.undo():
            return self.cancelPaint()
        self._paint_release()
        self._redraw()
        return True

    def paintMeshes(self):
        """重ね塗りの面 [(MPointArray, MColorArray)]: 塗っている途中、または編集のモードで選んだペイントの塗った範囲。
        1 筆の途中は、マニピュレータの絵 (ドラッグ中も残る) には描かず doDrag の絵にだけ描く。"""
        meshes = self._brush_preview_meshes()
        sources = []
        if not self.settings.value("paintFill"):
            return meshes
        if self.paint is not None:
            if not self._painting or self._drag_drawing:
                sources.append((self.paint.target, ("paint", id(self.paint), self.paint.version), self.paint.faces))
        elif self.mode() == MODE_EDIT:
            for name, ident in self.selection:
                target = self._target(name)
                guide = target.guides.get(ident) if target is not None else None
                if guide is not None and guide.kind == REGION:
                    sources.append((target, ("guide", name, ident, id(guide)), None))
        try:
            cm_key = color_management_key()
            now = time.perf_counter()
            for target, key, weights in sources:
                key = key + (cm_key, tuple(target.path.inclusiveMatrix()), self.color("paintFillColor"))
                mesh = self._paint_meshes.get(key)
                last = self._fill_last
                if mesh is None and self._painting and key[0] == "paint" and last is not None \
                        and last[0] == key[1] and now - last[1] < PAINT_FILL_INTERVAL:
                    mesh = last[2]                   # 1 筆の途中: 作ってから間が無ければ前の面のまま (少し遅れて付いて来る)
                if mesh is None:
                    if weights is None:
                        weights = edit.region_faces(target, self._guide(key[1:3]))
                    mesh = self._build_paint_mesh(target, painted_triangles(target.surface.arrays(), weights),
                                                  self.color("paintFillColor"), PAINT_ALPHA, cm_key)
                    if len(self._paint_meshes) > 8:
                        self._paint_meshes = {}
                    self._paint_meshes[key] = mesh
                    if key[0] == "paint":
                        self._fill_last = (key[1], now, mesh)
                meshes.append(mesh)
        except Exception:
            self._report_error("ペイントの表示")
        return meshes

    def _brush_preview_meshes(self):
        """ブラシの下見: 今押したら塗られる面 (Ctrl なら消される面) を薄い色で。円と同じく、塗っている間・半径を
        変えている間はマニピュレータの絵 (ドラッグ中も残る) に描かず、doDrag の絵にだけ描く。"""
        if (self._painting or self._adjust is not None) and not self._drag_drawing:
            return []
        try:
            key = self._preview_key()
            if key is None or not self.settings.value("brushPreview"):
                return []
            if self._preview_mesh is not None and self._preview_mesh[0] == key:
                return [self._preview_mesh[1]] if self._preview_mesh[1] is not None else []
            found = self.brushPreviewFaces()
            mesh = None
            if found is not None and len(found[1]):
                target, faces, erase = found
                arrays = target.surface.arrays()
                mask = np.zeros(face_count(arrays))
                mask[faces] = 1.0
                color = self.color("brushEraseColor" if erase else "brushPreviewColor")
                mesh = self._build_paint_mesh(target, painted_triangles(arrays, mask), color,
                                              self.settings.value("brushPreviewAlpha"), key[-1])
            self._preview_mesh = (key, mesh)
            return [mesh] if mesh is not None else []
        except Exception:
            self._report_error("ブラシの下見")
            return []

    def _preview_key(self):
        """ブラシの下見を作り直すかを決める鍵 (ブラシの所・大きさ・形・向き・消すか・設定・視点)。無ければ None。"""
        if not self._painting_tool() or self._brush_spot is None:
            return None
        target, local, world, _normal = self._brush_spot
        project = self._view()[0]
        view = np.asarray(project(np.asarray(world) + np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])))
        return (id(target), tuple(np.round(local, 9)), self._world_radius(target), self.settings.value("brushShape"),
                round(self._square_angle(), 6), self._ctrl(), self.settings.value("brushMode"),
                self.settings.value("brushBackDepth"), self.color("brushPreviewColor"), self.color("brushEraseColor"),
                self.settings.value("brushPreviewAlpha"),
                tuple(target.path.inclusiveMatrix()), tuple(np.round(view, 3).ravel()), color_management_key())

    def _build_paint_mesh(self, target, index, color, alpha, cm_key):
        """三角形 index を色 color・不透明度 alpha で重ねる面。塗った範囲は、囲む線と同じ面 (塗った面) を同じ濃さで
        塗る (三角形ごとの量の平均を濃さにすると、三角形ごとに色が違い、線とも合わなかった。GUI で確認)。
        頂点は三角形どうしで共有し、使う頂点だけをワールドにして、頂点の法線 (まわりの三角形の平均) の向きに少し
        浮かせる (面に重ねてもちらつかない)。"""
        arrays = target.surface.arrays()
        triangles = arrays.triangles[index]
        if not len(triangles):
            return overlay_mesh(np.zeros((0, 3)), np.zeros((0, 3)), color, alpha, cm_key)
        used, inverse = np.unique(triangles.ravel(), return_inverse=True)
        inverse = inverse.reshape(-1, 3)
        world = target.surface.toWorld(arrays.points[used])
        corners = world[inverse]
        normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        normals = np.zeros_like(world)
        for k in range(3):
            np.add.at(normals, inverse[:, k], normal)
        normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-30)[:, None]
        low, high = arrays.points.min(axis=0), arrays.points.max(axis=0)
        box = target.surface.toWorld([low, high])
        size = float(np.linalg.norm(box[1] - box[0]))
        return overlay_mesh(world + normals * (size * PAINT_OFFSET_RATIO), inverse, color, alpha, cm_key)

    def _remember_created(self, added):
        """描いたばかりのガイドを覚える: 編集のモードに替えたときは、これを選んだ状態にする (すぐ直せるように。
        Ctrl+ホイールで動かせる)。"""
        for name, ids in added.items():
            if ids:
                self.created = (name, ids[0])
                self.selection = [self.created]

    def _modifiers(self):
        """(Shift, Ctrl) の今の状態。読めなければ (False, 押したときの Ctrl)。"""
        if self.modifierState is not None:
            try:
                shift, ctrl = self.modifierState()
                return bool(shift), bool(ctrl)
            except Exception:
                pass
        return False, self._step

    def _select_release(self, press):
        """編集のモードで離した: クリックならマウスの下のガイド、ドラッグなら矩形のガイドを、修飾キーで選ぶ。"""
        project = self._view()[0]
        if self._dragged and self._rect is not None:
            # ガイドを選んでいて、その点の印が矩形に入るなら点を選ぶ (ほかのガイドにかかっても点が先)。
            # 選んだガイドの点が入らなければガイドを選ぶ
            if self.selectPointsInRect(self._rect, selection_op(*self._modifiers())):
                return
            found = edit.guides_in_rect(self._valid_targets(), project, self._rect)
        else:
            target, ident = edit.pick_guide(self._valid_targets(), project, press[0], press[1], PICK_PIXELS)
            found = [] if target is None else [(target, ident)]
        self.applySelection([(target.name(), ident) for target, ident in found], selection_op(*self._modifiers()))

    def applySelection(self, keys, op=REPLACE):
        """選択を変える (Maya と同じ: 置き換え / 切り替え / 外す / 足す)。選んでいる数。"""
        if op == REPLACE:
            self.selection = list(keys)
        else:
            for key in keys:
                if key in self.selection and op in (TOGGLE, REMOVE):
                    self.selection.remove(key)
                elif key not in self.selection and op in (TOGGLE, ADD):
                    self.selection.append(key)
        if keys or op == REPLACE:
            log.info("{} 本を選んでいます{}".format(len(self.selection), "。Delete で消す" if self.selection else ""))
        return len(self.selection)

    # -- 操作 (ボタン・ウィンドウ・-runAction) ------------------------------

    def panelPressed(self, ident):
        """ビューの下のボタンを押して離した: モードならそのモード、操作ならその操作。"""
        if is_mode(ident):
            self.setMode(ident)
        elif is_tool(ident):
            self.setGuideTool(tool_of(ident))
        else:
            self.runAction(ident)

    def runAction(self, ident):
        """操作の表 (core.actions) の操作。cut = シームで UV をカット、selectEdges = シームのエッジを選ぶ、
        symmetry = 対称を切り替える。"""
        if ident == "symmetry":
            return self.toggleSymmetry()
        if ident == "bridgeRoute":
            return self.toggleBridgeRoute()
        if ident == "brushShape":
            return self.toggleBrushShape()
        self.commitAdjust()
        targets = self._valid_targets()
        missing = sum(1 for target in targets for _guide, path in self.seams.paths(target) if path is None)
        if missing:
            log.warning("エッジにできなかったガイドが {} 本あります (飛ばします)".format(missing))
        if ident == "cut":
            result = cut_seams(targets, self.seams)
            if result:
                for name, count in result.items():
                    log.info("シームで UV をカットしました: {} (エッジ {} 本)".format(name, count))
            else:
                log.info("カットするシームがありません (ガイドを描いてください)")
        elif ident == "join":
            self.joinSelected()
        elif ident == "split":
            self.splitAtPoint()
        elif ident == "selectEdges":
            count = select_seams(targets, self.seams)
            log.info("シームのエッジを {} 本選びました".format(count))
        elif ident == "fromEdges":
            self.convertBoundaries()
        elif ident == "bridge":
            self.bridgeSelected()
        elif ident == "ringReset":
            self.resetSelectedRings()
        elif ident == "segmentMode":
            self.cycleSegmentMode()
        self._redraw()

    def _end_attach(self, pos):
        """ドラッグしている点を、ほかのガイドに乗せる / 外す ({(シェイプ, 番号): {点の番号: 乗せる番号 か None}})。
        点を 1 つだけ動かしているときだけ: 開いた線の端の点は、マウスの下 (PICK_PIXELS) にほかのガイド (自分と相手
        以外) があればそれに乗せる。途中の点・閉じたガイドの点は V を押しているときだけ乗せる (形を整えるために動かす
        点が、近くのガイドにうっかり吸い付かないように)。乗っている点 (端でも途中でも。乗った端から伸ばすと途中に
        残る) は、そのガイドから離れた所 (PICK_PIXELS x 3 より遠く) へ動かしたら外す。"""
        drags = self._point_press["drags"]
        if len(drags) != 1:
            return {}
        (key, (owner, _anchors, screens)), = drags.items()
        if len(screens) != 1:
            return {}
        index = next(iter(screens))
        guide = owner.guides.get(key[1])
        if guide is None or not 0 <= index < len(guide.path.nodes):
            return {}
        end = not guide.closed and index in (0, len(guide.anchors) - 1)
        if end or "v" in self._held():
            exclude = {key, (key[0], guide.partner)}
            picked = edit.pick_guide_line([owner], self._view()[0], pos[0], pos[1], PICK_PIXELS, exclude=exclude)
            if picked is not None:
                return {key: {index: picked[1]}}
        node = guide.path.nodes[index]
        if node.attach is not None:
            host = owner.guides.get(node.attach.host)
            far = host is None or edit.screen_distance(owner, host, self._view()[0], pos[0], pos[1]) > PICK_PIXELS * 3
            if far:
                return {key: {index: None}}
        return {}

    def segmentTargets(self):
        """区間の作り方を変える対象 [(target, ガイド, 区間の番号のリスト か None)]: 編集で選んだ線ごとに、選んだ点の
        隣り合う 2 点の間の区間 (点を選んでいなければ線全体 = None)。"""
        points = {}
        for target, guide, index in self.selectedPoints():
            points.setdefault((target.name(), guide.ident), set()).add(index)
        result = []
        for target, guide in self.editGuides():
            chosen = points.get((target.name(), guide.ident))
            if chosen:
                count = len(guide.anchors)
                indices = [i for i in range(len(guide.path.segments)) if i in chosen and (i + 1) % count in chosen]
                if indices:
                    result.append((target, guide, indices))
            elif not points:
                result.append((target, guide, None))
        return result

    def currentSegmentMode(self):
        """区間の作り方のボタンに出す今の作り方 (対象の最初の区間)。対象が無ければ None。"""
        found = self.segmentTargets()
        if not found:
            return None
        _target, guide, indices = found[0]
        return guide.path.segments[(indices or [0])[0]].mode

    def cycleSegmentMode(self):
        """区間の作り方を 曲線 -> 直線 -> 最短 -> 谷 -> 曲線 と切り替える (選んだ点の間の区間、点を選んでいなければ線
        全体。固定の区間は曲線から)。相手も作り直す。1 回の Undo。変えた本数。"""
        found = self.segmentTargets()
        if not found:
            log.info("区間の作り方: 編集で線を選んでください (点を選べば、その間の区間だけ)")
            return 0
        order = SEGMENT_CYCLE
        current = self.currentSegmentMode()
        mode = order[(order.index(current) + 1) % len(order)] if current in order else order[0]
        changed = 0
        with undo_chunk("区間の作り方"):
            for target, guide, indices in found:
                if edit.set_segment_modes(target, guide.ident, indices, mode):
                    changed += 1
        if changed:
            log.info("区間の作り方を「{}」にしました ({} 本)".format(SEGMENT_LABELS[mode], changed))
        self._redraw()
        return changed

    def resetSelectedRings(self):
        """編集で選んだ、点で形を変えた輪を、今の平面の断面の輪に戻す (相手も。1 回の Undo)。"""
        groups = {}
        for name, ident in self.selection:
            guide = self._guide((name, ident))
            if guide is not None and guide.kind == RING and guide.plane is not None and not guide.pristine:
                groups.setdefault(name, []).append(ident)
        done = []
        for name, idents in groups.items():
            target = self._target(name)
            if target is not None:
                done += edit.reset_rings(target, idents)
        if done:
            self.pointSelection = []
            log.info("輪を断面に戻しました ({} 本)".format(len(done)))
        else:
            log.info("断面に戻す輪がありません (点で形を変えた輪を選んでください)")
        self._redraw()
        return done

    def convertBoundaries(self):
        """境界をガイドに: Maya で選んだエッジ (無ければ今の UV の境界すべて) を境界のガイドにする (1 回の Undo)。
        足した {シェイプ: [番号]}。"""
        found, source = boundary_chains(self._valid_targets())
        added = edit.add_edge_guides(found)
        count = sum(len(ids) for ids in added.values())
        what = "選んだエッジ" if source == "selection" else "UV の境界"
        if count:
            log.info("{}を境界のガイドにしました ({} 本)".format(what, count))
        elif found:
            log.info("{}は、すでに境界のガイドになっています".format(what))
        else:
            log.info("UV の境界がありません (エッジを選ぶか、UV をカットしてから使ってください)")
        self._redraw()
        return added

    def selectInRect(self, rect, op=REPLACE):
        """画面の矩形 (左, 下, 右, 上) にかかるガイドを選ぶ。"""
        found = edit.guides_in_rect(self._valid_targets(), self._view()[0], rect)
        return self.applySelection([(target.name(), ident) for target, ident in found], op)

    # -- 輪を動かす --------------------------------------------------------

    def wheelAt(self, delta, shift=False, ctrl=False):
        """Ctrl+ホイール: 編集のモードで選んでいる閉じたガイドを平行移動、Shift+ホイール: 回す。受け取ったら True
        (Maya に渡さない)。Ctrl も Shift も無ければいつも Maya に渡す (カメラのズーム)。"""
        if not ctrl and not shift:
            return False
        key = self.wheelRing()
        if not delta or self._press is not None or self.polyline is not None or key is None:
            return False
        guide = self._guide(key)
        target = self._target(key[0])
        if guide is None or target is None or not guide.adjustable():
            return False
        if not guide.adjustable():
            log.info("この輪は動かせません (平面を持たない前の版の輪です。描き直してください)")
            return False
        if self._pending is not None and self._pending[0] is not target:
            self.commitAdjust()
        guides = self._pending[1] if self._pending is not None else GuideSet.fromJson(target.guides.toJson())
        sign = 1 if delta > 0 else -1
        if shift:
            moved = edit.adjust_ring(target, guides, key[1],
                                     tilt=sign * TILT_DEGREES,
                                     rotate_axis=self._view_axis(target, guide))
        else:
            moved = edit.adjust_ring(target, guides, key[1], shift=sign)
        if not moved:
            log.info("これ以上動かすと、メッシュから外れます")
            return True
        edit.follow_hosts(target, guides)   # つなぎ線も付いて行く (表示。書くのは止めてから)
        self._pending = (target, guides)
        target.guides = guides              # 書くまでは写しを表示する
        self._forget_missing()
        if self._commit_timer is not None:
            self._commit_timer.start()      # 止めてから COMMIT_MS 後に書く
        self._redraw()
        return True

    def wheelRing(self):
        """Ctrl / Shift+ホイールで動かすガイドの (シェイプの名前, 番号) か None: 編集のモードで最後に選んだ閉じたガイド。
        作成のモードでは動かさない (None)。"""
        key = self.selected if self.mode() == MODE_EDIT else None
        guide = self._guide(key) if key is not None else None
        return key if guide is not None and guide.adjustable() else None

    def _view_axis(self, target, guide):
        """カメラから輪の中心への視線の向き (オブジェクト空間)。求められなければ None (描いた線の向きで回す)。"""
        project, rays = self._view()
        center = target.surface.toWorld([np.asarray(guide.points).mean(axis=0)])[0]
        screen = np.asarray(project([center]), dtype=np.float64)[0]
        if not np.isfinite(screen).all():
            return None
        origin, direction = (np.asarray(v, dtype=np.float64) for v in rays(*screen))
        a, b = target.surface.toObject(np.array([origin, origin + direction]))
        length = np.linalg.norm(b - a)
        return (b - a) / length if length > 1e-12 else None

    def commitAdjust(self):
        """動かした輪を書く (1 回の Undo)。書いたら True。"""
        if self._pending is None:
            return False
        target, guides = self._pending
        self._pending = None
        if self._commit_timer is not None:
            self._commit_timer.stop()
        if not target.isValid():
            return False
        self._writing = True
        try:
            edit.write_adjusted(target, guides)
        finally:
            self._writing = False
        return True

    # -- 折れ線 ------------------------------------------------------------

    def polylineClick(self, pos, step=False):
        """折れ線のクリック: 始める / 点を足す / 最後の点で確定 / 最初の点で閉じて確定。確定したら足した結果。"""
        project, rays = self._view()
        targets = self._valid_targets()
        if self.polyline is None:
            hit = edit.cast_rays(targets, [rays(*pos)])[0]
            if hit is None:
                log.info("点はメッシュの上に置いてください")
                return {}
            tool = self.guideTool() if self.guideTool() in POINT_TOOLS else TOOL_LINE
            self.polyline = Polyline(hit, tool)
            self.selected = None
            log.info("{}を始めました。クリックで点を足す、Enter か最後の点で確定、最初の点で閉じる、"
                     "Backspace で戻す、Esc でやめる".format("カーブ" if tool == TOOL_CURVE else "折れ線"))
            return {}
        anchors = np.asarray(project(np.array(self.polyline.anchors)), dtype=np.float64)
        last = anchors[-1]
        if len(self.polyline) >= 2 and np.hypot(*(np.asarray(pos) - last)) <= PICK_PIXELS:
            return self.finishPolyline()
        if len(self.polyline) >= 3 and np.hypot(*(np.asarray(pos) - anchors[0])) <= PICK_PIXELS:
            if self.polyline.tool != TOOL_CURVE:
                self._add_polyline_segment(tuple(last), tuple(anchors[0]), rays, targets)
            return self.finishPolyline(closed=True)
        end = snap_angle(tuple(last), pos, STEP_DEGREES) if step else pos
        if self.polyline.tool == TOOL_CURVE:
            return self._add_curve_point(end, rays, targets)
        if not self._add_polyline_segment(tuple(last), end, rays, targets):
            log.info("点はメッシュの上に置いてください")
        return {}

    def _add_curve_point(self, pos, rays, targets):
        """カーブの点を置く (最初の点と同じメッシュの上だけ)。"""
        hit = edit.cast_rays(targets, [rays(*pos)])[0]
        if hit is None:
            log.info("点はメッシュの上に置いてください")
        elif hit[0] != self.polyline.segments[0][0][0]:
            log.info("カーブの点は最初の点と同じメッシュの上に置いてください")
        else:
            self.polyline.add([hit])
        return {}

    def _add_polyline_segment(self, start, end, rays, targets):
        """画面の直線 start -> end の視線を当てて、区間として足す。終点が当たらなければ足さずに False。"""
        hits = edit.cast_rays(targets, [rays(x, y) for x, y in segment_points(start, end, SAMPLE_PIXELS)])
        if not hits or hits[-1] is None:
            return False
        self.polyline.add(hits)
        return True

    def finishPolyline(self, closed=False):
        """折れ線を確定して補助線にする (点が 2 つ以上のとき)。"""
        polyline, self.polyline = self.polyline, None
        self._mouse = None
        if polyline is None or len(polyline) < 2:
            self._redraw()
            return {}
        if polyline.tool == TOOL_CURVE:
            first = polyline.segments[0][0]
            target = self._valid_targets()[first[0]]
            anchors = [hit[1] for hit in polyline.hits()]
            added = edit.add_curve(target, anchors, closed=closed)
            self._report(added, "カーブ{}".format(" (閉じた)" if closed else ""))
            self._remember_created(added)
        else:
            anchor_hits = [segment[-1] for segment in polyline.segments]   # 区間の最後 = 置いた点
            if closed:
                anchor_hits = anchor_hits[:-1]         # 閉じた線: 最初の点へ戻った区間の終わりは最初の点
            mesh = anchor_hits[0][0]
            anchors = (mesh, [hit[1] for hit in anchor_hits]) if all(h[0] == mesh for h in anchor_hits) else None
            added = edit.add_line_hits(self._valid_targets(), polyline.hits(), closed=closed, anchors=anchors)
            self._report(added, "折れ線{}".format(" (閉じた)" if closed else ""))
            self._remember_created(added)
        self._redraw()
        return added

    def cancelPolyline(self):
        had = self.polyline is not None
        self.polyline = None
        self._mouse = None
        self._redraw()
        return had

    def _report(self, added, label):
        for name, ids in added.items():
            log.info("{} のガイドを足しました: {} ({} 本。対称の相手を含む)".format(label, name, len(ids)))

    def _report_error(self, where):
        if not self._error_shown:
            self._error_shown = True
            log.warning("{} でエラー:\n{}".format(where, traceback.format_exc()))

    # -- キー --------------------------------------------------------------

    def _wants_key(self, name):
        if name == "brushShape":
            return self._painting_tool()          # S はペイントの間だけ (ほかは Maya に渡す)
        if name == "mode" or name == "symmetry" or is_tool(name):
            return bool(self.targets)
        if name == "hold:v":
            return self.mode() == MODE_EDIT and bool(self.editGuides())
        if name.startswith("hold:"):
            return self._painting_tool()
        if name.startswith("region:"):
            return self._painting_tool() and (self.paint is not None or self._repaint_region() is not None)
        if name == "cancel" and self._adjust is not None:
            return True
        if self.paint is not None and name in ("finish", "cancel", "undo", "back"):
            return True
        if self.bridgeDraft is not None and name in ("cancel", "undo", "back", "delete"):
            return True
        if name == "cancel":
            if self._press is not None or self.polyline is not None:
                return True
            return self.mode() == MODE_EDIT and self.selected is not None
        if name in ("finish",):
            return self.polyline is not None
        if name == "undo":
            return self.polyline is not None          # 描いている間だけ (ほかは Maya の Undo)
        if self.polyline is not None:
            return name in ("back", "delete")           # 作成: 描いている線の最後の点を戻す
        return self.mode() == MODE_EDIT and self.selected is not None and name in ("back", "delete")

    def _on_key(self, name):
        self.commitAdjust()
        if name == "cancel" and self._adjust is not None:
            self._cancel_adjust()
            return True
        if name == "symmetry":
            return self.toggleSymmetry()
        if name == "brushShape":
            return self.toggleBrushShape()
        if name.startswith("region:"):
            return self.resizePaint(grow=name == "region:grow")
        if self.paint is not None and name in ("finish", "cancel", "undo", "back"):
            if name == "finish":
                self.finishPaint()
            elif name == "cancel":
                self.cancelPaint()
            else:
                self.undoStroke()
            return True
        if self.bridgeDraft is not None and name in ("cancel", "undo", "back", "delete"):
            if name == "cancel":
                self.cancelBridge()
            else:
                self.undoBridgePoint()
            return True
        if name == "cancel":
            self.abortAction()
            return True
        if name == "mode":
            self.setMode(MODE_EDIT if self.mode() == MODE_CREATE else MODE_CREATE)
            return True
        if is_tool(name):
            self.setGuideTool(tool_of(name))
            return True
        if name == "finish":
            self.finishPolyline()
            return True
        if name in ("back", "delete", "undo") and self.polyline is not None:
            if self.polyline.pop():
                self.cancelPolyline()
            self._redraw()
            return True
        if name in ("delete", "back") and self.mode() == MODE_EDIT:
            if self.selectedPoints():
                return self.deletePoints()
            return self.deleteSelected()
        return False

    def deleteSelected(self):
        """選んでいるガイドをまとめて消す (対称の相手も。1 回の Undo)。"""
        self.commitAdjust()
        if not self.selection:
            return False
        keys = [(self._target(name), ident) for name, ident in self.selection]
        keys = [(target, ident) for target, ident in keys if target is not None]
        self.selection = []
        removed = edit.delete_guides(keys) if keys else {}
        count = sum(len(ids) for ids in removed.values())
        if count:
            log.info("ガイドを {} 本消しました (対称の相手を含む)".format(count))
        self._redraw()
        return True

    def abortAction(self):
        # Esc: 描いている線・折れ線をやめる / (編集のモード) 点の選択・ガイドの選択を外す
        if self._adjust is not None:
            self._cancel_adjust()
            return
        if self._press is not None:
            self._press = None
            self._found = []
            self._samples = []
        elif self.polyline is not None:
            self.cancelPolyline()
            log.info("折れ線をやめました")
        elif self.mode() != MODE_EDIT:
            pass
        elif self.selectedPoints():
            self.pointSelection = []
        elif self.selection:
            self.selection = []
        self._redraw()
