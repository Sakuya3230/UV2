# -*- coding: utf-8 -*-
"""
マニピュレータ (ガイドの表示・ホバー・モードのボタン)。

    manip.setItems(provider)    # provider() -> [(ワールドの点 (n, 3), 閉じているか, 色, 太さ)]
    manip.setItems2d(provider)  # provider() -> [(画面の点 (n, 2), 色, 太さ)] (ゴム紐など)
    manip.setHandles(provider)  # provider() -> [(x, y, 色)] (点の印。いちばん上に描く)
    manip.setMeshes(provider)   # provider() -> [(MPointArray, MColorArray)] (ペイントの重ね塗り。いちばん下に描く)
    manip.setLabels(provider)   # provider() -> [(ワールドの点, 文字)] (ブラシの半径など。前面に)
    setItems の要素に 5 つ目 True を付けると、その線は前面 (X 線) に描く (ブラシの円・塗っている線のプレビュー)
    manip.setHover(hover)       # hover(x, y) -> 描き直しが要るなら True (ホバー・ゴム紐)
    manip.setPanel(active, handler) # active() -> 今のボタンの ID (モードとガイドの種類) の集まり、
                                    # handler(ID) -> ボタン (モード・種類・操作) を押して離したとき
    manip.renderInto(drawMgr)   # コンテキストの doDrag の drawMgr に同じものを描く

仕組みは UVPathCut の tool/manipulator.py と同じ:
- registerForMouseMove で、マウスを動かすたびに doMove が呼ばれる (MPxContext には移動のイベントが無い)
- preDrawUI でカメラの位置・カラーマネジメント・ボタンの配置と平面を読み、drawUI で描く
- ボタン (core.panel) は押せる部品 (kSelectable)。押下はマニピュレータの doPress に届き (glActiveName で
  どのボタンか)、離したときに同じボタンの上ならそのモードにする (押したまま外へ動かせばやめられる)。
  ボタン以外は押せない部品なので、ほかのクリックはコンテキストの doPress に届く
- ボタンの上ではガイドのホバーをしない
- ドラッグ中、Maya はマニピュレータを描き直さないので、ドラッグ中の表示はコンテキストの doDrag の
  drawMgr に描く (renderInto)
- プラグをつながないので connectToDependNode / finishAddingManips は呼ばない
"""
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui

from ..core.panel import button_at, button_state, panel_buttons, panel_layout
from .drawing import (PLANE_NEAR_RATIO, ScreenPlane, color_management_key, draw_handles, draw_labels,
                      draw_polyline, draw_stroke, draw_triangles, render_buttons)

__all__ = ["SeamGuideManip"]


class SeamGuideManip(omui.MPxManipulatorNode):
    def __init__(self):
        super().__init__()
        self._items = None
        self._items2d = None
        self._handles = None
        self._meshes = None
        self._labels = None
        self._hover = None
        self._mode = None
        self._handler = None
        self._eye = None
        self._cm_key = None
        self._first_handle = 0
        self._layout = {}
        self._plane = None
        self._hover_button = None
        self._pressed_button = None

    @staticmethod
    def initialize():
        pass

    def postConstructor(self):
        self.registerForMouseMove()
        self._first_handle = self.glFirstHandle()

    def setItems(self, provider):
        self._items = provider

    def setItems2d(self, provider):
        self._items2d = provider

    def setHandles(self, provider):
        self._handles = provider

    def setMeshes(self, provider):
        self._meshes = provider

    def setLabels(self, provider):
        self._labels = provider

    def setHover(self, hover):
        self._hover = hover

    def setPanel(self, active, handler, buttons=None):
        self._mode = active
        self._handler = handler
        self._button_list = buttons    # () -> [(ID, 文字)] (モードで並び・文字が変わる)。None なら core.panel の既定

    def _buttons(self):
        provider = getattr(self, "_button_list", None)
        return provider() if provider is not None else panel_buttons()

    # -- マウス ------------------------------------------------------------

    def doMove(self, view, refresh):
        x, y = self.mousePosition()
        self._layout = panel_layout(view.portWidth(), view.portHeight(), self._buttons())
        button = button_at(self._layout, x, y)
        changed = button != self._hover_button
        self._hover_button = button
        if button is None and self._hover is not None and self._hover(x, y):
            changed = True
        if changed:
            view.refresh(False, True)

    def doPress(self, view):
        # ボタン (kSelectable) の上で押したときだけ呼ばれる。実行は離したとき
        index = self.glActiveName() - self._first_handle
        buttons = self._buttons()
        self._pressed_button = buttons[index][0] if 0 <= index < len(buttons) else None
        view.refresh(False, True)

    def doDrag(self, view):
        x, y = self.mousePosition()
        button = button_at(self._layout, x, y)
        if button != self._hover_button:
            self._hover_button = button
            view.refresh(False, True)

    def doRelease(self, view):
        pressed, self._pressed_button = self._pressed_button, None
        x, y = self.mousePosition()
        self._hover_button = button_at(self._layout, x, y)
        if pressed is not None and pressed == self._hover_button and self._handler is not None:
            self._handler(pressed)
        view.refresh(False, True)

    # -- 描画 --------------------------------------------------------------

    def preDrawUI(self, view):
        camera = om.MFnCamera(view.getCamera())
        eye = camera.eyePoint(om.MSpace.kWorld)
        self._eye = (eye.x, eye.y, eye.z)
        self._cm_key = color_management_key()
        self._layout = panel_layout(view.portWidth(), view.portHeight(), self._buttons())
        self._plane = ScreenPlane(view, max(camera.nearClippingPlane * PLANE_NEAR_RATIO, 1e-3))

    def renderInto(self, drawMgr):
        if self._meshes is not None:
            for mesh in self._meshes():
                draw_triangles(drawMgr, mesh)
        if self._items is None:
            return
        for item in self._items():
            points, closed, rgb, width = item[:4]
            draw_polyline(drawMgr, points, closed, rgb, width, self._eye, self._cm_key,
                          xray=len(item) > 4 and item[4])
        if self._items2d is not None:
            for points, rgb, width in self._items2d():
                draw_stroke(drawMgr, points, rgb, width)
        if self._handles is not None:
            draw_handles(drawMgr, self._handles())
        if self._labels is not None:
            draw_labels(drawMgr, self._labels())

    def panelButtons(self):
        """[(番号, モード, 文字, 色の名前)]。"""
        active = self._mode() if self._mode is not None else None
        return [(index, ident, text, button_state(ident, active, self._hover_button, self._pressed_button))
                for index, (ident, text) in enumerate(self._buttons())]

    def drawUI(self, drawMgr, frameContext):
        self.renderInto(drawMgr)
        if self._plane is not None and self._layout:
            render_buttons(drawMgr, self._plane, self._layout, self.panelButtons(), self._first_handle,
                           self._cm_key)
