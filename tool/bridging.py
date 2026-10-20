# -*- coding: utf-8 -*-
"""
つなぎ線のツールの操作 (SeamGuideContext に混ぜる。仕様は docs/04_bridge_spec.md)。

作成の「6 つなぎ線」:
    ガイドをクリック (始点) -> (ガイドの無いメッシュをクリック = 中継点。何個でも) -> 別のガイドをクリック (終点。確定)
    Backspace・Delete・Ctrl+Z = 最後の点を戻す (中継点が無ければやめる)、Esc = やめる。種類・モードを替えてもやめる
    描いている間: 始点 -> 中継点の線 (最短パス) をプレビュー、最後の点からマウスまでゴム紐、点の印、マウスの下の
    ガイドを強調 (クリックすると端点になる所)
編集の「つなぎ線」ボタン: 選んだ 2 本のガイドを、カメラから見て奥側でつなぐ (scene.edit.auto_bridge_ends)

端点はクリックした所に画面でいちばん近いガイドの線の点から、そのシームの頂点に置く (scene.edit.bridge_end)。
中継点はメッシュに当てた所にいちばん近い頂点。
"""
import numpy as np

from .. import log
from ..constants import PICK_PIXELS, PREVIEW_COLOR, SELECTED_WIDTH, STRING_COLOR
from ..core.bridge import bridge_vertices
from ..core.guides import BRIDGE, KINDS
from ..core.settings import MODE_EDIT, ROUTE_SHORTEST, ROUTE_VALLEY
from ..scene import edit

__all__ = ["BridgeMixin", "BridgeDraft", "HOST_KINDS"]

HOST_KINDS = tuple(kind for kind in KINDS if kind != BRIDGE)    # 端点が乗れるガイド (つなぎ線の上には乗れない)


class BridgeDraft(object):
    """描いているつなぎ線: 対象のメッシュ、始点 (core.path_model.Node。ガイドに乗る点)、中継点 (頂点の番号の列)、ここまでの線 (頂点の列)。"""

    def __init__(self, target, start, route=None):
        self.target = target
        self.start = start
        self.route = route
        self.stops = []
        self.vertices = [start.vertex]

    def stopsWithStart(self):
        return [self.start.vertex] + list(self.stops)

    def rebuild(self):
        """始点 -> 中継点の線を作り直す (プレビュー)。"""
        found = bridge_vertices(self.target.surface.arrays(), self.stopsWithStart(),
                                edit.bridge_weights(self.target, self.route))
        self.vertices = found if found is not None else [self.start.vertex]


class BridgeMixin(object):
    """SeamGuideContext に混ぜる。self.bridgeDraft (BridgeDraft か None) を使う。"""

    bridgeDraft = None

    # -- 作成 -----------------------------------------------------------------

    def bridgeClick(self, x, y):
        """作成の「6 つなぎ線」のクリック。足した {シェイプ: [番号]} (確定したときだけ)。"""
        project = self._view()[0]
        targets = self._valid_targets()
        picked = edit.pick_guide_line(targets, project, x, y, PICK_PIXELS, kinds=HOST_KINDS)
        if picked is not None:
            # 端点はクリックでメッシュに当たった所の近く (輪を真横から見ると、手前と奥の線が画面で重なるため)
            hit = edit.cast_rays(targets, [self._rays(x, y)])[0]
            if hit is not None and targets[hit[0]] is picked[0]:
                picked = picked[:3] + (np.asarray(hit[1], dtype=np.float64),)
        draft = self.bridgeDraft
        if draft is None:
            if picked is None:
                log.info("つなぎ線: ガイドの上をクリックしてください (そこが始点になります)")
                return {}
            target, ident, line, point = picked
            start = edit.bridge_end(target, target.guides, ident, line, point)
            if start is None:
                log.info("つなぎ線: このガイドにはつなげません (シームが無い)")
                return {}
            self.bridgeDraft = BridgeDraft(target, start, self.settings.value("bridgeRoute"))
            log.info("つなぎ線を始めました。メッシュのクリック = 中継点、別のガイドのクリック = 確定、Esc = やめる")
            self._redraw()
            return {}
        if picked is not None and picked[0] is draft.target:
            target, ident, line, point = picked
            end = edit.bridge_end(target, target.guides, ident, line, point)
            if end is None or (end.vertex == draft.start.vertex and not draft.stops):
                return {}
            self.bridgeDraft = None
            added = edit.add_bridge(target, draft.start, end, draft.stops, route=draft.route)
            if added:
                self._report(added, "つなぎ線")
                self._remember_created(added)
            else:
                log.info("つなぎ線: 端点の間がエッジでつながっていません")
            self._redraw()
            return added
        # ガイドの無い所: メッシュに当てて中継点 (始点と同じメッシュだけ)
        hit = edit.cast_rays(targets, [self._rays(x, y)])[0]
        if hit is None or targets[hit[0]] is not draft.target:
            return {}
        arrays = draft.target.surface.arrays()
        vertex = int(np.argmin(np.linalg.norm(arrays.points - np.asarray(hit[1]), axis=1)))
        if vertex != draft.stopsWithStart()[-1]:
            draft.stops.append(vertex)
            draft.rebuild()
        self._redraw()
        return {}

    def undoBridgePoint(self):
        """最後の中継点を戻す (無ければやめる)。"""
        draft = self.bridgeDraft
        if draft is None:
            return False
        if draft.stops:
            draft.stops.pop()
            draft.rebuild()
        else:
            self.bridgeDraft = None
            log.info("つなぎ線をやめました")
        self._redraw()
        return True

    def cancelBridge(self):
        had = self.bridgeDraft is not None
        self.bridgeDraft = None
        if had:
            log.info("つなぎ線をやめました")
            self._redraw()
        return had

    # -- 編集のボタン -----------------------------------------------------------

    def bridgeSelected(self):
        """編集で選んだ 2 本のガイドを、カメラから見て奥側でつなぐ。足した {シェイプ: [番号]}。"""
        if len(self.selection) != 2 or self.selection[0][0] != self.selection[1][0]:
            log.info("つなぎ線: 同じメッシュのガイドを 2 本選んでください")
            return {}
        target = self._target(self.selection[0][0])
        if target is None:
            return {}
        first, second = self.selection[0][1], self.selection[1][1]
        ends = edit.auto_bridge_ends(target, target.guides, first, second, self._view_direction(target))
        if ends is None:
            log.info("つなぎ線: 選んだガイドにはつなげません (つなぎ線どうし・シームが無い)")
            return {}
        added = edit.add_bridge(target, ends[0], ends[1], route=self.settings.value("bridgeRoute"))
        if added:
            self._report(added, "つなぎ線")
            self._remember_created(added)
        self._redraw()
        return added

    def toggleBridgeRoute(self):
        """通り方 (最短 / 谷) を切り替える (上の段のボタン)。新しいつなぎ線に効き、編集で選んだつなぎ線 (と相手) も
        作り直す (1 回の Undo)。"""
        route = ROUTE_VALLEY if self.settings.value("bridgeRoute") != ROUTE_VALLEY else ROUTE_SHORTEST
        self.settings.set("bridgeRoute", route)
        label = "谷" if route == ROUTE_VALLEY else "最短"
        changed = []
        if self.mode() == MODE_EDIT:
            groups = {}
            for name, ident in self.selection:
                guide = self._guide((name, ident))
                if guide is not None and guide.kind == BRIDGE:
                    groups.setdefault(name, []).append(ident)
            for name, idents in groups.items():
                target = self._target(name)
                if target is not None:
                    changed += edit.set_bridge_route(target, idents, route)
        if changed:
            log.info("つなぎ線の通り方を「{}」にしました ({} 本。対称の相手を含む)".format(label, len(changed)))
        else:
            log.info("つなぎ線の通り方: {} (新しいつなぎ線から)".format(label))
        if self.bridgeDraft is not None:
            self.bridgeDraft.route = route
            self.bridgeDraft.rebuild()
        self._redraw()
        return True

    def _view_direction(self, target):
        """カメラの視線の向き (オブジェクト空間。画面の真ん中の視線)。"""
        x = y = 0.0
        if self.viewFunctions is None:
            import maya.api.OpenMayaUI as omui
            view = omui.M3dView.active3dView()
            x, y = view.portWidth() * 0.5, view.portHeight() * 0.5
        origin, direction = self._view()[1](x, y)
        ends = target.surface.toObject(np.array([origin, np.asarray(origin) + np.asarray(direction)]))
        view = ends[1] - ends[0]
        return view / max(np.linalg.norm(view), 1e-12)

    # -- 表示 -------------------------------------------------------------------

    def bridgeItems(self):
        """描いているつなぎ線のプレビュー [(ワールドの点, 閉じているか, 色, 太さ)]。"""
        draft = self.bridgeDraft
        if draft is None or len(draft.vertices) < 2:
            return []
        world = draft.target.surface.toWorld(draft.target.surface.arrays().points[draft.vertices])
        return [(world, False, PREVIEW_COLOR, SELECTED_WIDTH, True)]

    def bridgeItems2d(self):
        """最後の点からマウスまでのゴム紐 [(点 (n, 2), 色, 太さ)]。"""
        draft = self.bridgeDraft
        if draft is None or self._mouse is None:
            return []
        last = self._bridge_screen([draft.stopsWithStart()[-1]])
        if not len(last) or not np.isfinite(last[0]).all():
            return []
        return [([tuple(last[0]), tuple(self._mouse)], STRING_COLOR, 1.0)]

    def bridgeHandles(self):
        """点の印 [(x, y, 色)]: 始点と中継点。"""
        draft = self.bridgeDraft
        if draft is None:
            return []
        screen = self._bridge_screen(draft.stopsWithStart())
        return [(x, y, self.color("handleColor")) for x, y in screen if np.isfinite(x) and np.isfinite(y)]

    def _bridge_screen(self, vertices):
        draft = self.bridgeDraft
        project = self._view()[0]
        world = draft.target.surface.toWorld(draft.target.surface.arrays().points[list(vertices)])
        return np.asarray(project(world), dtype=np.float64)
