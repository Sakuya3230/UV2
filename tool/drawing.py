# -*- coding: utf-8 -*-
"""
描画の補助 (ビューの視線・投影・色・線)。

    ray = view_ray(view, x, y)              # ピクセル (左下が原点) を通るワールドの視線 (始点, 向き)
    project = projector(view)               # ワールドの点 (n, 3) -> 画面 (n, 2)。カメラの後ろは nan
    draw_polyline(drawMgr, points, closed, rgb, width, eye, cm_key)
    draw_stroke(drawMgr, points2d)          # 描いている線 (画面の 2D)
    draw_handles(drawMgr, handles)          # 点の印 [(x, y, 色)] (黒いふちの付いた塗った四角)
    mesh = overlay_mesh(points, alphas, rgb, cm_key)   # 重ね塗りの三角形 (ペイントの塗った範囲)
    draw_triangles(drawMgr, mesh)
    plane = ScreenPlane(view, depth)        # 画面のピクセルを、カメラの前の平面の上のワールドの点に戻す
    render_buttons(drawMgr, plane, layout, buttons, first_handle, cm_key)   # ビューのボタン (押せる部品)

投影は modelViewMatrix x projectionMatrix (行ベクトル: p · MV · P) でまとめて計算する
(UVPathCut の project_points と同じ。点ごとに worldToView を呼ぶと遅い)。
色: カラーマネジメントが有効だと、マニピュレータの線の色は表示の変換を通る (青がシアンに見えるなど)。
display_color で「その色に見える値」を逆に求める (UVPathCut の tool/drawing.py と同じ。結果は覚えておく)。
線はカメラへ少し寄せて描く (面に重ねてもちらつかないように)。
"""
import numpy as np

import maya.api.OpenMaya as om
import maya.api.OpenMayaRender as omr
import maya.cmds as cmds

from ..constants import HANDLE_BORDER, HANDLE_PIXELS, STROKE_COLOR

__all__ = ["view_ray", "projector", "color_management_key", "display_color", "draw_polyline",
           "draw_stroke", "draw_handles", "overlay_mesh", "draw_triangles", "draw_labels", "EYE_OFFSET", "ScreenPlane", "render_buttons", "PLANE_NEAR_RATIO"]

EYE_OFFSET = 0.002     # 描く点をカメラへ寄せる量 (カメラまでの距離に対する割合)
PLANE_NEAR_RATIO = 1.5   # ボタンの平面の距離 (カメラのニアクリップに対する倍率)
BUTTON_FONT_SIZE = 11
_DISPLAY_COLOR_CACHE = {}


def view_ray(view, x, y):
    source = om.MPoint()
    direction = om.MVector()
    view.viewToWorld(int(x), int(y), source, direction)
    return (source.x, source.y, source.z), (direction.x, direction.y, direction.z)


def projector(view):
    """ワールドの点 (n, 3) を画面のピクセル (n, 2) にする関数。カメラの後ろの点は nan。"""
    width, height = view.portWidth(), view.portHeight()
    matrix = np.array(list(view.modelViewMatrix()), dtype=np.float64).reshape(4, 4).dot(
        np.array(list(view.projectionMatrix()), dtype=np.float64).reshape(4, 4))

    def project(points):
        coords = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        clip = np.hstack([coords, np.ones((len(coords), 1))]).dot(matrix)
        w = clip[:, 3]
        visible = w > 1e-9
        safe = np.where(visible, w, 1.0)
        screen = np.stack([(clip[:, 0] / safe * 0.5 + 0.5) * width,
                           (clip[:, 1] / safe * 0.5 + 0.5) * height], axis=1)
        screen[~visible] = np.nan
        return screen
    return project


def color_management_key():
    try:
        if not cmds.colorManagementPrefs(query=True, cmEnabled=True):
            return None
        return cmds.colorManagementPrefs(query=True, viewTransformName=True)
    except RuntimeError:
        return None


def display_color(rgb, key):
    """画面に rgb で見せるために drawMgr.setColor に渡す値。key が None なら変換しない。"""
    if key is None:
        return tuple(rgb)
    cache_key = (key, tuple(rgb))
    if cache_key in _DISPLAY_COLOR_CACHE:
        return _DISPLAY_COLOR_CACHE[cache_key]
    value = [max(c, 1e-3) ** 2.2 for c in rgb]
    for _sweep in range(8):
        for i in range(3):
            low, high = 0.0, 16.0
            for _ in range(30):
                trial = list(value)
                trial[i] = (low + high) / 2.0
                if cmds.colorManagementConvert(toDisplaySpace=trial)[i] < rgb[i]:
                    low = trial[i]
                else:
                    high = trial[i]
            value[i] = (low + high) / 2.0
        shown = cmds.colorManagementConvert(toDisplaySpace=value)
        if max(abs(s - t) for s, t in zip(shown, rgb)) < 1e-3:
            break
    result = tuple(value)
    _DISPLAY_COLOR_CACHE[cache_key] = result
    return result


def draw_polyline(drawMgr, points, closed, rgb, width, eye, cm_key, xray=False):
    """ワールドの折れ線を描く (カメラへ少し寄せる。xray なら面に隠れず前面に描く)。"""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 2:
        return
    if eye is not None:
        points = points + (np.asarray(eye) - points) * EYE_OFFSET
    if closed:
        points = np.vstack([points, points[:1]])
    drawMgr.beginDrawable(omr.MUIDrawManager.kNonSelectable, 0)
    drawMgr.setColor(om.MColor(display_color(rgb, cm_key) + (1.0,)))
    drawMgr.setLineWidth(float(width))
    if xray:
        drawMgr.beginDrawInXray()
    drawMgr.lineStrip(om.MPointArray([om.MPoint(*p) for p in points.tolist()]), False)
    if xray:
        drawMgr.endDrawInXray()
    drawMgr.endDrawable()


def draw_labels(drawMgr, labels):
    """ワールドの位置に文字 [(点, 文字)] (前面に。白)。"""
    if not labels:
        return
    drawMgr.beginDrawable(omr.MUIDrawManager.kNonSelectable, 0)
    drawMgr.beginDrawInXray()
    drawMgr.setColor(om.MColor((1.0, 1.0, 1.0, 1.0)))
    drawMgr.setFontSize(13)
    for point, text in labels:
        drawMgr.text(om.MPoint(*point), text, omr.MUIDrawManager.kLeft)
    drawMgr.endDrawInXray()
    drawMgr.endDrawable()


def draw_stroke(drawMgr, points2d, rgb=STROKE_COLOR, width=2.0):
    """画面の 2D の折れ線 (描いている線・ひも・折れ線の印)。文字・2D の色は表示の変換を通らないのでそのまま。"""
    if len(points2d) < 2:
        return
    drawMgr.beginDrawable()
    drawMgr.setColor(om.MColor(tuple(rgb) + (1.0,)))
    drawMgr.setLineWidth(float(width))
    for (x0, y0), (x1, y1) in zip(points2d[:-1], points2d[1:]):
        drawMgr.line2d(om.MPoint(x0, y0), om.MPoint(x1, y1))
    drawMgr.endDrawable()


def draw_handles(drawMgr, handles, size=HANDLE_PIXELS):
    """点の印: 黒いふち (2 px 外) の上に色を塗った四角。明るいメッシュの上でも暗いメッシュの上でも見える
    (線だけの小さな四角は見にくかった。GUI で確認)。文字・2D の色は表示の変換を通らないのでそのまま。
    handles は (x, y, 色) か (x, y, 色, 形)。形 "diamond" は 45 度回した少し大きい四角 (つなぎ線の端点)。"""
    if not handles:
        return
    drawMgr.beginDrawable(omr.MUIDrawManager.kNonSelectable, 0)
    shapes = []
    for handle in handles:
        diamond = len(handle) > 3 and handle[3] == "diamond"
        up = om.MVector(1.0, 1.0).normal() if diamond else om.MVector(0.0, 1.0)
        shapes.append((handle[0], handle[1], handle[2], up, size * 1.3 if diamond else float(size)))
    for x, y, _rgb, up, scale in shapes:
        drawMgr.setColor(om.MColor(tuple(HANDLE_BORDER) + (1.0,)))
        drawMgr.rect2d(om.MPoint(x, y), up, scale + 2.0, scale + 2.0, True)
    for x, y, rgb, up, scale in shapes:
        drawMgr.setColor(om.MColor(tuple(rgb) + (1.0,)))
        drawMgr.rect2d(om.MPoint(x, y), up, scale, scale, True)
    drawMgr.endDrawable()


def overlay_mesh(points, alphas, rgb, cm_key):
    """重ね塗りの三角形 (MPointArray, MColorArray)。points (k, 3, 3) ワールド、alphas (k,) 不透明度。
    作るのが重いので、呼ぶ側が覚えておく。"""
    base = display_color(rgb, cm_key)
    alphas = np.asarray(alphas, dtype=np.float64)
    colors = np.empty((len(alphas), 4))
    colors[:, :3] = base
    colors[:, 3] = alphas
    flat = np.asarray(points, dtype=np.float64).reshape(-1, 3).tolist()
    return om.MPointArray(flat), om.MColorArray(np.repeat(colors, 3, axis=0).tolist())


def draw_triangles(drawMgr, mesh):
    """overlay_mesh の三角形を描く (頂点ごとの色。半透明)。"""
    points, colors = mesh
    if not len(points):
        return
    drawMgr.beginDrawable(omr.MUIDrawManager.kNonSelectable, 0)
    drawMgr.mesh(omr.MUIDrawManager.kTriangles, points, None, colors)
    drawMgr.endDrawable()


class ScreenPlane(object):
    """画面のピクセルを、カメラの視線に垂直な平面の上のワールドの点に戻す (UVPathCut と同じ)。

    2D で描いたもの (rect2d など) はマニピュレータの押せる部品にならないので、ボタンの角をそれぞれの
    ピクセルを通る視線とこの平面の交点としてワールドに戻し、3D で描く (画面ではちょうど決めた形に見える)。
    平面はニアクリップのすぐ奥 (手前のメッシュに隠れない)。
    """

    def __init__(self, view, depth):
        self.view = view
        source = om.MPoint()
        direction = om.MVector()
        view.viewToWorld(int(view.portWidth() / 2), int(view.portHeight() / 2), source, direction)
        self.normal = direction.normal()
        self.center = source + self.normal * depth

    def point(self, x, y):
        source = om.MPoint()
        direction = om.MVector()
        self.view.viewToWorld(int(x), int(y), source, direction)
        denom = direction * self.normal
        if abs(denom) < 1e-12:
            return om.MPoint(self.center)
        t = ((self.center - source) * self.normal) / denom
        return source + direction * t


def render_buttons(drawMgr, plane, layout, buttons, first_handle, cm_key):
    """ビューのボタン。buttons は [(番号, ID, 文字, 色の名前)]。四角は押せる部品 (ハンドル = first_handle + 番号)、
    文字は 2D (押せない部品) で重ねる。"""
    from ..core.panel import BUTTON_COLORS, TEXT_COLOR
    for index, ident, _text, state in buttons:
        left, bottom, right, top = layout[ident]
        corners = [plane.point(x, y) for x, y in ((left, bottom), (right, bottom), (right, top), (left, top))]
        drawMgr.beginDrawable(omr.MUIDrawManager.kSelectable, first_handle + index)
        r, g, b = display_color(BUTTON_COLORS[state], cm_key)
        drawMgr.setColor(om.MColor((r, g, b, 1.0)))
        drawMgr.mesh(omr.MUIDrawManager.kTriangles, om.MPointArray(
            [corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]]))
        drawMgr.endDrawable()
    drawMgr.beginDrawable(omr.MUIDrawManager.kNonSelectable, 0)
    drawMgr.setFontSize(BUTTON_FONT_SIZE)
    for _index, ident, text, _state in buttons:
        left, bottom, right, top = layout[ident]
        drawMgr.setColor(om.MColor(TEXT_COLOR + (1.0,)))
        drawMgr.text2d(om.MPoint((left + right) / 2.0, (bottom + top) / 2.0 - 5), text, omr.MUIDrawManager.kCenter)
    drawMgr.endDrawable()
