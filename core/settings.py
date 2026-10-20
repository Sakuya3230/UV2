# -*- coding: utf-8 -*-
"""
ツールの設定 (Maya に依存しない)。項目は定義表 DEFINITIONS に 1 行ずつ。

    settings = Settings(storage)         # storage は load() -> dict か None / save(dict)。None なら保存しない
    settings.value("mode")               # "guide" / "select"
    settings.set("mode", "select")       # 名前でも番号でも。変わったらリスナーへ (キーの集合)
    settings.addListener(fn)

定義表から、コンテキストのコマンドのフラグ (tool/command.py) とツール設定のウィンドウ (core/tool_ui_text.py)
を作る。項目を足すときは表に 1 行足す (UVPathCut の core/settings.py と同じ考え方を小さくしたもの)。
"""
import collections

from .. import constants as c

__all__ = ["Setting", "Settings", "SettingsError", "DEFINITIONS", "CHOICE", "BOOL", "COLOR", "FLOAT", "MODE_CREATE", "MODE_EDIT",
           "definition", "defaults", "normalize", "TOOL_RING", "TOOL_FREEHAND", "TOOL_LINE", "TOOL_CURVE",
           "TOOL_PAINT", "TOOL_BRIDGE", "BRUSH_SURFACE", "BRUSH_VOLUME", "BRUSH_CIRCLE", "BRUSH_SQUARE", "BRUSH_SQUARE_STROKE", "ROUTE_SHORTEST", "ROUTE_VALLEY"]

CHOICE = "choice"
BOOL = "bool"
COLOR = "color"
FLOAT = "float"          # 小数。choices に (最小, 最大) を入れる (範囲の外は端に寄せる)
MODE_CREATE = "create"
MODE_EDIT = "edit"
TOOL_RING, TOOL_FREEHAND, TOOL_LINE, TOOL_CURVE, TOOL_PAINT = "ring", "freehand", "line", "curve", "paint"
TOOL_BRIDGE = "bridge"
BRUSH_SURFACE, BRUSH_VOLUME = "surface", "volume"
BRUSH_CIRCLE, BRUSH_SQUARE, BRUSH_SQUARE_STROKE = "circle", "square", "squareStroke"
ROUTE_SHORTEST, ROUTE_VALLEY = "shortest", "valley"

Setting = collections.namedtuple(
    "Setting", "key kind default choices choice_labels label section short_flag description")

DEFINITIONS = [
    Setting("mode", CHOICE, MODE_CREATE, (MODE_CREATE, MODE_EDIT), ("作成", "編集"), "モード", "モード", "-md",
            "作成: ガイドの種類 (1～6) で新しいガイドを描くだけ。編集: Maya と同じ修飾キーでガイドを選び、消す・輪を動かす・"
            "点を直す (Tab で切り替え)"),
    Setting("guideTool", CHOICE, TOOL_RING, (TOOL_RING, TOOL_FREEHAND, TOOL_LINE, TOOL_CURVE, TOOL_PAINT,
                                              TOOL_BRIDGE),
            ("リング", "フリーハンド", "ライン", "カーブ", "ペイント", "つなぎ線"), "ガイドの種類", "モード", "-gt",
            "作成のモードで描くもの (キーの 1～6)。リング = ドラッグで輪切り、フリーハンド = ドラッグで手描きの補助線、"
            "ライン = クリックで点を置く直線の折れ線、カーブ = クリックで置いた点を通るなめらかな線、"
            "ペイント = ブラシで塗った範囲を囲む線 (突起の根元の輪など)、"
            "つなぎ線 = ガイド -> (メッシュで中継点) -> ガイドと順にクリックすると、その間をエッジの最短パスでつなぐ "
            "(手足を切り開く線など)"),
    # 色 (モード・ガイドの種類ごとの欄)。既定は constants の色
    Setting("ringColor", COLOR, c.RING_COLOR, (), (), "線の色", "リング", "-rc", "リングのガイドの色"),
    Setting("lineColor", COLOR, c.LINE_COLOR, (), (), "線の色", "フリーハンド・ライン", "-lc",
            "フリーハンドとラインの補助線 (つないだ線で直線を含むものも) の色"),
    Setting("curveColor", COLOR, c.CURVE_COLOR, (), (), "線の色", "カーブ", "-cvc", "カーブのガイドの色"),
    Setting("regionColor", COLOR, c.REGION_COLOR, (), (), "確定した線", "ペイント", "-rgc",
            "確定したペイントのガイド (Enter で囲む線にしたあとの線) の色"),
    Setting("paintLineColor", COLOR, c.PAINT_LINE_COLOR, (), (), "塗っている間の線", "ペイント", "-plc",
            "塗っている間と、編集で選んだペイントの囲む線の色 (前面に描く)"),
    Setting("paintFillColor", COLOR, c.PAINT_COLOR, (), (), "塗った範囲", "ペイント", "-pfc",
            "塗った範囲を重ねて見せる色 (半透明)"),
    Setting("paintFill", BOOL, False, (), (), "塗った範囲を表示", "ペイント", "-pf",
            "塗った範囲を半透明の色で重ねて見せる (既定は出さない: 囲む線だけのほうが見やすかった)"),
    Setting("brushMode", CHOICE, BRUSH_SURFACE, (BRUSH_SURFACE, BRUSH_VOLUME), ("サーフェス", "ボリューム"),
            "ブラシ", "ペイント", "-bm",
            "サーフェス = 当たった面から表面に沿って半径の中を塗る (すぐ近くでも、つながっていない面・裏側は塗らない)。"
            "ボリューム = ブラシの球の中の頂点をすべて塗る (指の間・薄い所では、近くの別の面も塗る)"),
    Setting("brushShape", CHOICE, BRUSH_CIRCLE, (BRUSH_CIRCLE, BRUSH_SQUARE, BRUSH_SQUARE_STROKE),
            ("円", "四角", "四角 (向き)"), "ブラシの形", "ペイント",
            "-bs", "円 = ブラシの半径の中を塗る。四角 = 画面で見た四角 (画面の上下左右にそろう、一辺 = 半径 x 2) の中に"
            "中心が入る表向きの面を塗る (角のある所・まっすぐな縁を塗りやすい)。四角 (向き) = 四角をストローク (マウスの"
            "動き) の向きに回す。S キー・ビューの上の段のボタンで 円 -> 四角 -> 四角 (向き) と切り替え"),
    Setting("brushBackDepth", FLOAT, 0.5, (0.0, 5.0), (), "裏向きの面の奥行き", "ペイント", "-bbd",
            "四角のブラシで、カメラの方を向いていない面 (しわ・凹凸の向こう側の斜面) も、カメラから見て手前の表面から"
            "この奥行き (ブラシの半径の何倍か) の中なら塗る。それより奥 (指の裏など、厚みの分だけ奥にある面) は塗らない。"
            "0 なら向いていない面は塗らない"),
    Setting("bridgeRoute", CHOICE, ROUTE_SHORTEST, (ROUTE_SHORTEST, ROUTE_VALLEY), ("最短", "谷"), "通り方", "つなぎ線",
            "-brr", "新しいつなぎ線の通り方 (ビューの上の段のボタンでも切り替え。編集で選んだつなぎ線にも効く)。"
            "最短 = エッジの長さの最短パス、谷 = くぼみ (筋肉の境・折れ目・板の継ぎ目) を選んで通る (少し遠回りでも)"),
    Setting("valleyStrength", FLOAT, 3.0, (0.0, 20.0), (), "谷の強さ", "つなぎ線", "-vs",
            "通り方「谷」で、どのくらい遠回りしてでも谷を選ぶか (0 で最短と同じ。平らな所は 1 + 強さ 倍、山は 1 + 2 x 強さ "
            "倍の重み)。つなぎ線を作る・作り直すときに使う"),
    Setting("bridgeColor", COLOR, c.BRIDGE_COLOR, (), (), "線の色", "つなぎ線", "-brc",
            "つなぎ線 (2 本のガイドの間をエッジの最短パスでつないだ線) の色"),
    Setting("edgeColor", COLOR, c.EDGE_COLOR, (), (), "線の色", "境界", "-egc",
            "境界のガイド (UV の切れ目・選んだエッジから変換したもの) の色"),
    Setting("brushColor", COLOR, c.BRUSH_COLOR, (), (), "ブラシの円", "ペイント", "-bc", "ブラシの円 (四角) の枠の色"),
    Setting("brushPreview", BOOL, True, (), (), "下見を表示", "ペイント", "-bp",
            "ブラシの下に、今押したら塗られる面 (Ctrl なら消される面) を薄い色で見せる"),
    Setting("brushPreviewColor", COLOR, c.BRUSH_PREVIEW_COLOR, (), (), "下見の色", "ペイント", "-bpc",
            "下見 (押したら塗られる面) の色"),
    Setting("brushEraseColor", COLOR, c.BRUSH_ERASE_COLOR, (), (), "下見の色 (消す)", "ペイント", "-bec",
            "Ctrl を押しているときの下見 (押したら消される面) の色"),
    Setting("brushPreviewAlpha", FLOAT, 0.3, (0.05, 1.0), (), "下見の不透明度", "ペイント", "-bpa",
            "下見の濃さ (0.05〜1。1 で不透明)"),
    Setting("selectedColor", COLOR, c.SELECTED_COLOR, (), (), "選んだ線", "編集", "-slc", "選んだガイド (と相手) の色"),
    Setting("hoverColor", COLOR, c.HOVER_COLOR, (), (), "マウスの下の線", "編集", "-hvc", "マウスの下のガイドの色"),
    Setting("handleColor", COLOR, c.HANDLE_COLOR, (), (), "点の印", "編集", "-hdc", "線の点の印の色"),
    Setting("handleSelectedColor", COLOR, c.HANDLE_SELECTED_COLOR, (), (), "選んだ点", "編集", "-hsc",
            "選んだ点・動かしている点の印の色"),
    # 対称 (UVPathCut と同じ仕様)
    Setting("symmetry", BOOL, False, (), (), "対称", "対称", "-sy",
            "新しく描いたガイドに、反対側の相手も作る (X キー・ビューのボタンでも切り替え)。Maya の対称がオン "
            "(ワールド / オブジェクト) の間は、Maya の面で両側に作る。前に作った相手との組は、オフにしても残る"),
    Setting("mirrorSpace", CHOICE, "object", ("world", "object"), ("ワールド", "オブジェクト"), "空間", "対称", "-ms",
            "対称の面の空間 (ワールド: ワールドの原点を通る面 / オブジェクト: Transform の原点を通る面)"),
    Setting("mirrorAxis", CHOICE, "x", ("x", "y", "z"), ("X", "Y", "Z"), "軸", "対称", "-ma",
            "対称の面に垂直な軸 (X なら左右)"),
    Setting("mirrorTolerance", FLOAT, 0.1, (0.0001, 10.0), (), "許容値", "対称", "-mt",
            "ペイントの塗った面を反対側へ写すとき、鏡に写した位置からこの距離の中に面の中心があれば対応するとみなす "
            "(無い所もいちばん近い面で写し、その数をログに出す)"),
    Setting("seamPreview", BOOL, True, (), (), "シームを表示", "シーム", "-sp",
            "ガイドから求めたエッジ (シーム) をビューに描く。ガイドを描く・動かすたびに求め直す"),
    Setting("seamColor", COLOR, c.SEAM_COLOR, (), (), "シームの色", "シーム", "-smc", "シームのエッジの色"),
]
COLOR_KEYS = tuple(s.key for s in DEFINITIONS if s.kind == COLOR)


class SettingsError(ValueError):
    pass


def definition(key):
    for setting in DEFINITIONS:
        if setting.key == key:
            return setting
    raise SettingsError("知らない設定です: {}".format(key))


def defaults():
    return {setting.key: setting.default for setting in DEFINITIONS}


def normalize(key, value):
    """値を設定の型に直す。選択肢は名前か番号。直せなければ SettingsError。"""
    setting = definition(key)
    if setting.kind == CHOICE:
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(setting.choices):
            return setting.choices[value]
        text = str(value)
        if text in setting.choices:
            return text
        if text.isdigit() and int(text) < len(setting.choices):
            return setting.choices[int(text)]
        raise SettingsError("{} は {} のどれかです: {}".format(key, " / ".join(setting.choices), value))
    if setting.kind == BOOL:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "on", "yes"):
            return True
        if text in ("0", "false", "off", "no"):
            return False
        raise SettingsError("{} は真偽値です: {}".format(key, value))
    if setting.kind == COLOR:
        parts = value.replace(",", " ").split() if isinstance(value, str) else list(value)
        try:
            rgb = tuple(min(1.0, max(0.0, float(part))) for part in parts)
        except (TypeError, ValueError):
            rgb = ()
        if len(rgb) != 3:
            raise SettingsError("{} は色 (r g b。0～1) です: {}".format(key, value))
        return rgb
    if setting.kind == FLOAT:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise SettingsError("{} は数です: {}".format(key, value))
        if number != number:
            raise SettingsError("{} は数です: {}".format(key, value))
        low, high = setting.choices
        return min(high, max(low, number))
    raise SettingsError("知らない種類です: {}".format(setting.kind))


class Settings(object):
    def __init__(self, storage=None):
        self._storage = storage
        self._values = defaults()
        self._listeners = []
        data = storage.load() if storage is not None else None
        for key, value in (data or {}).items():
            try:
                self._values[key] = normalize(key, value)
            except SettingsError:
                pass                # 知らない項目・直せない値は既定値のまま

    def value(self, key):
        return self._values[key]

    def values(self):
        return dict(self._values)

    def choiceIndex(self, key):
        return definition(key).choices.index(self._values[key])

    def set(self, key, value):
        """変えたら True (リスナーへ知らせ、保存する)。"""
        value = normalize(key, value)
        if self._values[key] == value:
            return False
        self._values[key] = value
        if self._storage is not None:
            self._storage.save(self._values)
        for listener in list(self._listeners):
            listener({key})
        return True

    def addListener(self, listener):
        self._listeners.append(listener)
