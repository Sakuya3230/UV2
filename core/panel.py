# -*- coding: utf-8 -*-
"""
ビューのボタン (モードの切り替え) の並び (Maya に依存しない)。

    buttons = panel_buttons()                 # [(ID, 文字)]: モード (ガイド / 選択)・ガイドの種類・操作 (core.actions)
    layout = panel_layout(width, height, buttons)   # {ID: (左, 下, 右, 上)}。ビューの下の中央
    button_at(layout, x, y)                   # 位置のボタンの ID か None
    button_state(id, active, hover, pressed)  # 色の名前 (BUTTON_COLORS のキー)

ボタンの ID はモードの名前 (core.settings の choices)、"tool:" + ガイドの種類 (リング / ペイント / ライン)、
操作の ID (core.actions)。モード・ガイドの種類のボタンは押すとそれになり、今のモードと種類のボタンは
"active" の色。操作のボタンは押すとその操作。3 段: 上にモードと対称、真ん中にガイドの種類、下に操作 (つなぐ・切り離すは編集のモードだけ)。置き場所は UVPathCut と同じ (下の中央、カメラの名前より上)。
"""
from .actions import ACTIONS, EDIT_ONLY, TOGGLES
from .settings import definition

__all__ = ["mode_buttons", "tool_buttons", "panel_buttons", "is_mode", "is_tool", "tool_of", "TOOL_PREFIX", "panel_layout", "button_at", "button_state", "PANEL_BOTTOM", "BUTTON_WIDTH",
           "BUTTON_HEIGHT", "BUTTON_COLORS", "TEXT_COLOR"]

PANEL_BOTTOM = 36
ROW_GAP = 4
TOOL_PREFIX = "tool:"
BUTTON_WIDTH = 90
BUTTON_HEIGHT = 24
BUTTON_GAP = 2
GROUP_GAP = 14
SIDE_MARGIN = 4

BUTTON_COLORS = {
    "normal": (0.24, 0.24, 0.24),
    "hover": (0.36, 0.36, 0.36),
    "active": (0.20, 0.45, 0.70),
    "pressed": (0.30, 0.55, 0.80),
}
TEXT_COLOR = (0.95, 0.95, 0.95)


def mode_buttons():
    """[(モードの名前, 表示の文字)]。"""
    setting = definition("mode")
    return list(zip(setting.choices, setting.choice_labels))


def tool_buttons():
    """[(TOOL_PREFIX + ガイドの種類, "番号 表示の文字")]。番号はキー (1 / 2 / 3)。"""
    setting = definition("guideTool")
    return [(TOOL_PREFIX + name, "{} {}".format(index + 1, label))
            for index, (name, label) in enumerate(zip(setting.choices, setting.choice_labels))]


def panel_buttons(labels=None, mode=None):
    """[(ID, 文字)]: モード、切り替え (対称)、ガイドの種類、操作の順。labels ({ID: 文字}) で文字を替える (対称の
    ボタンは状態で変わる)。mode が作成なら、編集のモードだけの操作 (つなぐ・切り離す) は出さない。"""
    labels = labels or {}
    actions = [(action.id, labels.get(action.id, action.label)) for action in ACTIONS
               if not (mode == "create" and action.id in EDIT_ONLY)]
    return (mode_buttons() + [a for a in actions if a[0] in TOGGLES] + tool_buttons()
            + [a for a in actions if a[0] not in TOGGLES])


def is_mode(ident):
    return ident in definition("mode").choices


def is_tool(ident):
    return ident.startswith(TOOL_PREFIX)


def tool_of(ident):
    """ガイドの種類のボタンの ID から種類の名前。"""
    return ident[len(TOOL_PREFIX):]


def _group(ident):
    if is_mode(ident):
        return "mode"
    if is_tool(ident):
        return "tool"
    return "toggle" if ident in TOGGLES else "action"


def _gap(previous, ident):
    return GROUP_GAP if _group(previous) != _group(ident) else BUTTON_GAP


def _layout_row(port_width, buttons, bottom):
    total = len(buttons) * BUTTON_WIDTH + sum(_gap(a[0], b[0]) for a, b in zip(buttons, buttons[1:]))
    left = max(SIDE_MARGIN, (port_width - total) / 2.0)
    rects = {}
    previous = None
    for ident, _text in buttons:
        if previous is not None:
            left += _gap(previous, ident)
        rects[ident] = (left, bottom, left + BUTTON_WIDTH, bottom + BUTTON_HEIGHT)
        left += BUTTON_WIDTH
        previous = ident
    return rects


ROWS = (("action",), ("tool",), ("mode", "toggle"))   # 下の段から: 操作 / ガイドの種類 / モードと対称
ACTIONS_PER_ROW = 4     # 操作の段の 1 段のボタンの数 (多ければ下へ折り返す)


def panel_layout(port_width, port_height, buttons):
    """3 段 (どれも中央): 上からモードと対称、ガイドの種類、操作。2 段 (上にモード・種類・対称) だと 800 px を
    超えて横に長かった (GUI で確認)。操作は ACTIONS_PER_ROW 個ずつで下へ折り返す (上の行が先頭の操作)。"""
    rows = []
    for groups in ROWS:
        items = [b for b in buttons if _group(b[0]) in groups]
        if groups == ("action",):
            chunks = [items[k:k + ACTIONS_PER_ROW] for k in range(0, len(items), ACTIONS_PER_ROW)] or [[]]
            rows.extend(reversed(chunks))                 # 下から積むので、最後の行を先に
        else:
            rows.append(items)
    rects = {}
    for row, items in enumerate(rows):
        rects.update(_layout_row(port_width, items, PANEL_BOTTOM + row * (BUTTON_HEIGHT + ROW_GAP)))
    return rects


def button_at(layout, x, y):
    for ident, (left, bottom, right, top) in layout.items():
        if left <= x <= right and bottom <= y <= top:
            return ident
    return None


def button_state(ident, active, hover, pressed):
    """押している (離していない) > 今のもの (active は ID か ID の集まり) > ホバー > 普通。"""
    if pressed is not None and ident == pressed and hover == pressed:
        return "pressed"
    if ident == active or (isinstance(active, (set, frozenset, list, tuple)) and ident in active):
        return "active"
    if pressed is None and ident == hover:
        return "hover"
    return "normal"
