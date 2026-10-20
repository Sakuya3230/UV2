# -*- coding: utf-8 -*-
"""
ガイドのデータ (Maya に依存しない)。統一した持ち方 (docs/05_unified_spec.md)。

    guides = GuideSet()
    ident = guides.add(Guide(path))                  # path は core.path_model.GuidePath。番号を付けて足す
    guides.remove(ident)                             # 対称の相手もいっしょに消す
    text = guides.toJson(); GuideSet.fromJson(text, mesh, spacing)   # シームに保存する形 (version 2)

どのガイドも 点 + 区間の作り方 + 点の付き方 (core.path_model.GuidePath) を 1 本持つ。作った道具 (origin) から
種類 (kind) を決める: リング = RING、フリーハンド・ライン = LINE、カーブ = CURVE、ペイント = REGION (囲む線ごとに
1 本。同じ塗りの線は source の group が同じ)、境界 = EDGE、つなぎ線 = BRIDGE。種類は表示の色と、作った道具に戻る
操作 (断面に戻す・塗り直す) にだけ使い、編集の操作はどれも同じ。

対称: 相手のガイドを partner で互いに指す。消すときはいっしょに消す。中心を通る輪 (首・胴の輪切り) は
鏡に写しても自分と重なるので、相手を作らない (is_self_mirror)。

前の版 (version 1。種類ごとにばらばらの持ち方) は LegacyGuide として読み、core.path_model.convert_v1_set で
新しい持ち方に直す (メッシュの頂点を引くので、読むときに mesh と spacing を渡す)。
"""
import json

from .geometry import mean_nearest_distance

__all__ = ["Guide", "GuideSet", "LegacyGuide", "LegacyGuideSet", "RING", "LINE", "CURVE", "REGION", "EDGE", "BRIDGE",
           "KINDS", "FORMAT", "VERSION", "is_self_mirror"]




RING = "ring"
LINE = "line"
CURVE = "curve"
REGION = "region"
EDGE = "edge"
BRIDGE = "bridge"
KINDS = (RING, LINE, CURVE, REGION, EDGE, BRIDGE)
FORMAT = "SeamGuide.guides"
VERSION = 2
KIND_OF_ORIGIN = {"ring": RING, "circle": RING, "freehand": LINE, "line": LINE, "curve": CURVE, "paint": REGION,
                  "edge": EDGE, "bridge": BRIDGE}   # circle = 1 リングの Ctrl+ドラッグの円 (平面を持たない輪)


class Guide(object):
    """1 本のガイド: 線 path (GuidePath)、番号 ident、対称の相手の番号 partner。"""

    def __init__(self, path, ident=None, partner=None):
        self.path = path
        self.ident = ident
        self.partner = partner

    @property
    def kind(self):
        return KIND_OF_ORIGIN.get(self.path.origin, LINE)

    @property
    def origin(self):
        return self.path.origin

    @property
    def closed(self):
        return self.path.closed

    @property
    def points(self):
        return [tuple(p) for p in self.path.line().tolist()]

    @property
    def anchors(self):
        """点の位置 [(x, y, z)]。"""
        return [tuple(node.position) for node in self.path.nodes]

    @property
    def vertices(self):
        """線全体の頂点の列 (どの区間もエッジの上のときだけ。無ければ None)。"""
        return self.path.lineVertices()

    @property
    def plane(self):
        """リングの平面 (点, 単位の法線) か None。"""
        plane = self.path.source.get("plane")
        return None if not plane else (tuple(float(c) for c in plane[0]), tuple(float(c) for c in plane[1]))

    @property
    def axis(self):
        axis = self.path.source.get("axis")
        return None if axis is None else tuple(float(c) for c in axis)

    @property
    def faces(self):
        """ペイントの塗った面 (面の番号のリスト) か None。"""
        return self.path.source.get("faces")

    @property
    def group(self):
        """同じ塗りから作ったペイントの線の組の印 (無ければ None)。"""
        return self.path.source.get("group")

    @property
    def pristine(self):
        return self.path.pristine

    def lines(self):
        """ガイドの線 [(点の列, 閉じているか)] (1 本)。"""
        return [(self.points, self.closed)]

    def adjustable(self):
        """ホイールで形ごと動かせるか (閉じたガイドすべて)。"""
        return self.closed and len(self.path.nodes) >= 3

    def toDict(self):
        data = self.path.toDict()
        data["id"] = self.ident
        data["partner"] = self.partner
        return data

    @classmethod
    def fromDict(cls, data):
        from .path_model import GuidePath
        return cls(GuidePath.fromDict(data), data.get("id"), data.get("partner"))

    def copy(self):
        return Guide.fromDict(self.toDict())



# -- 前の版 (version 1) ----------------------------------------------------------------

class LegacyGuide(object):
    def __init__(self, kind, points, closed=False, ident=None, partner=None, plane=None, axis=None, anchors=None,
                 smooth=None, loops=None, weights=None, faces=None, vertices=None, ends=None, stops=None,
                 route=None):
        if kind not in KINDS:
            raise ValueError("ガイドの種類が違います: {}".format(kind))
        self.kind = kind
        self.points = [tuple(float(c) for c in point) for point in points]
        self.closed = bool(closed)
        self.ident = ident
        self.partner = partner
        self.plane = None if plane is None else (tuple(float(c) for c in plane[0]),
                                                 tuple(float(c) for c in plane[1]))
        self.axis = None if axis is None else tuple(float(c) for c in axis)
        self.anchors = None if anchors is None else [tuple(float(c) for c in point) for point in anchors]
        self.smooth = None if smooth is None else [bool(s) for s in smooth]
        self.loops = None
        self.weights = None if weights is None else [[int(i), float(w)] for i, w in weights]
        self.faces = None if faces is None else [int(i) for i in faces]
        self.vertices = None if vertices is None else [int(i) for i in vertices]
        self.ends = None if ends is None else [
            [None if e[0] is None else int(e[0]), int(e[1]), float(e[2]), int(e[3])]
            + ([[float(c) for c in e[4]]] if len(e) > 4 and e[4] is not None else []) for e in ends]
        self.stops = None if stops is None else [int(i) for i in stops]
        self.route = None if route is None else str(route)
        if loops is not None:
            self.setLoops(loops)

    def setLoops(self, loops):
        """囲む線 [(点の列, 閉じているか)] を入れ、points / closed をいちばん長い (最初の) 線にする。"""
        self.loops = [([tuple(float(c) for c in p) for p in points], bool(closed)) for points, closed in loops]
        if self.loops:
            self.points, self.closed = list(self.loops[0][0]), self.loops[0][1]
        else:
            self.points, self.closed = [], True

    def lines(self):
        """ガイドの線 [(点の列, 閉じているか)]。ペイントは囲む線すべて。"""
        if self.loops is not None:
            return list(self.loops)
        return [(self.points, self.closed)]

    def adjustable(self):
        """平行移動・回転できるか (平面と軸を持つ輪切り)。"""
        return self.kind == RING and self.plane is not None and self.axis is not None

    def toDict(self):
        data = {"id": self.ident, "kind": self.kind, "closed": self.closed, "partner": self.partner,
                "points": [list(point) for point in self.points]}
        if self.plane is not None:
            data["plane"] = list(self.plane[0]) + list(self.plane[1])
        if self.axis is not None:
            data["axis"] = list(self.axis)
        if self.anchors is not None:
            data["anchors"] = [list(point) for point in self.anchors]
        if self.smooth is not None:
            data["smooth"] = list(self.smooth)
        if self.loops is not None:
            data["loops"] = [{"points": [list(p) for p in points], "closed": closed} for points, closed in self.loops]
        if self.weights is not None:
            data["weights"] = [list(pair) for pair in self.weights]
        if self.faces is not None:
            data["faces"] = list(self.faces)
        if self.vertices is not None:
            data["vertices"] = list(self.vertices)
        if self.ends is not None:
            data["ends"] = [list(e) for e in self.ends]
        if self.stops is not None:
            data["stops"] = list(self.stops)
        if self.route is not None:
            data["route"] = self.route
        return data

    @classmethod
    def fromDict(cls, data):
        plane = data.get("plane")
        return cls(data["kind"], data["points"], data.get("closed", False), data.get("id"), data.get("partner"),
                   (plane[:3], plane[3:]) if plane else None, data.get("axis"), data.get("anchors"),
                   data.get("smooth"),
                   [(loop["points"], loop.get("closed", True)) for loop in data["loops"]] if "loops" in data else None,
                   data.get("weights"), data.get("faces"), data.get("vertices"), data.get("ends"), data.get("stops"),
                   data.get("route"))


def is_self_mirror(points, mirrored, tolerance):
    """鏡に写した線が元の線とほぼ重なる (中心を通る輪など) か。"""
    return mean_nearest_distance(mirrored, points) <= tolerance




class GuideSet(object):
    def __init__(self):
        self._guides = []
        self._next = 1

    def __len__(self):
        return len(self._guides)

    def guides(self):
        return list(self._guides)

    def get(self, ident):
        return next((guide for guide in self._guides if guide.ident == ident), None)

    def add(self, guide):
        """番号を付けて足し、その番号を返す。"""
        guide.ident = self._next
        self._next += 1
        self._guides.append(guide)
        return guide.ident

    def insert(self, guide):
        """番号を付けたまま足す (前の番号を保つとき。番号が使われていれば ValueError)。"""
        if self.get(guide.ident) is not None:
            raise ValueError("番号 {} は使われています".format(guide.ident))
        self._guides.append(guide)
        self._next = max(self._next, guide.ident + 1)
        return guide.ident

    def renumber(self, old, new):
        """ガイド old の番号を new にする (new は空いていること)。相手からの参照も直す。対称の相手を作り直すとき、
        前と同じ番号にするため (つなぎ線が相手のガイドに乗っているので、番号が変わると土台が消えたことになる)。"""
        guide = self.get(old)
        if guide is None or self.get(new) is not None:
            return False
        guide.ident = new
        for other in self._guides:
            if other.partner == old:
                other.partner = new
        self._next = max(self._next, new + 1)
        return True

    def detachPartner(self, ident):
        """ident の対称の相手だけを消す (ident は残す)。消した番号か None。"""
        guide = self.get(ident)
        if guide is None or guide.partner is None:
            return None
        partner = guide.partner
        guide.partner = None
        self._guides = [g for g in self._guides if g.ident != partner]
        return partner

    def remove(self, ident):
        """ident のガイドと、その対称の相手を消す。消した番号のリスト。"""
        guide = self.get(ident)
        if guide is None:
            return []
        removed = {ident}
        if guide.partner is not None and self.get(guide.partner) is not None:
            removed.add(guide.partner)
        self._guides = [g for g in self._guides if g.ident not in removed]
        return sorted(removed)

    def clear(self):
        self._guides = []

    def copy(self):
        return GuideSet.fromJson(self.toJson())

    def toJson(self):
        return json.dumps({"format": FORMAT, "version": VERSION, "next": self._next,
                           "guides": [guide.toDict() for guide in self._guides]}, separators=(",", ":"))

    @classmethod
    def fromJson(cls, text, mesh=None, spacing=None):
        """保存した文字列から作る。空なら空の GuideSet、形式が違えば ValueError。前の版 (version 1) は mesh
        (MeshArrays) と spacing (点の間隔) を使って新しい持ち方に直す (無ければ ValueError)。"""
        result = cls()
        if not text:
            return result
        data = json.loads(text)
        if data.get("format") != FORMAT:
            raise ValueError("ガイドの形式ではありません")
        if int(data.get("version", 1)) < VERSION:
            if mesh is None or spacing is None:
                raise ValueError("前の版のガイドを直すにはメッシュが要ります")
            from .path_model import convert_v1_set
            legacy = LegacyGuideSet([LegacyGuide.fromDict(item) for item in data.get("guides", [])])
            entries, next_id = convert_v1_set(legacy, mesh, spacing)
            for entry in entries:
                result._guides.append(Guide(entry.path, entry.ident, entry.partner))
            result._next = max(next_id, data.get("next", 1))
            return result
        for item in data.get("guides", []):
            result._guides.append(Guide.fromDict(item))
        result._next = max([data.get("next", 1)] + [g.ident + 1 for g in result._guides if g.ident is not None])
        return result


class LegacyGuideSet(object):
    """前の版のガイドの組 (変換にだけ使う)。"""

    def __init__(self, guides):
        self._guides = list(guides)

    def guides(self):
        return list(self._guides)

    def get(self, ident):
        return next((guide for guide in self._guides if guide.ident == ident), None)

    def __len__(self):
        return len(self._guides)
