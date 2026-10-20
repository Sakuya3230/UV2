# -*- coding: utf-8 -*-
"""
ツール設定のウィンドウの MEL を、設定の定義表から組み立てる (Maya に依存しない)。

    text = tool_ui_mel()     # tool/tool_ui.py が mel.eval で定義する

Maya はツールのアイコンをダブルクリックしたとき (とツールを有効にしたとき) に、
<クラス名>Properties (部品を作る) と <クラス名>Values(ツールの名前) (コマンドを付けて値を入れる) を呼ぶ。
クラス名はコンテキストの stringClassName() ("seamGuide")。

設定は種類ごとの部品 (選択肢 = radioButtonGrp (5 つ以上は optionMenuGrp。radioButtonGrp は 4 つまでで、
-labelArray5 は「Invalid flag」になった。GUI で確認)、真偽値 = checkBoxGrp)。欄 (Setting.section) ごとに
frameLayout を作り、操作 (core.actions) は「シーム」の欄のボタン (-runAction ID)。項目を表に足せば
ウィンドウにも出る。将来、ガイドの一覧の欄を足す予定。

値は SetValues で、コンテキストのコマンドに問い合わせず、Python の tool.tool_ui.setting_value (保存した設定
= optionVar) から読む。GUI で `seamGuideCtx -q -seamPreview` が空を返し、checkBoxGrp -value1 が
「Invalid argument:」になった (原因は standalone ではコンテキストを作れず確かめられていない)。設定は変えるたびに
保存するので、ツールの値と同じ。

UVPathCut で確かめた落とし穴 (同じ作り):
- Properties は最初の 1 回しか呼ばれないらしいので、Values の先頭で古いレイアウトを消して呼び直す
- Values で setParent してから部品を名前だけで操作する
- 問い合わせは文字列を返せないので、選択肢は番号で返る (radioButtonGrp の -select は 1 から)
"""
from .actions import ACTIONS, TOGGLES
from .settings import BOOL, CHOICE, COLOR, DEFINITIONS, FLOAT

__all__ = ["CLASS_NAME", "CONTEXT_COMMAND", "control_name", "tool_ui_mel", "HELP_LINES"]

CLASS_NAME = "seamGuide"
TOOL_UI_MODULE = "SeamGuide.tool.tool_ui"
CONTEXT_COMMAND = "seamGuideCtx"
LABEL_WIDTH = 120
CHOICE_WIDTH = 90
SYMMETRY_SECTION = "対称"
MAYA_SYMMETRY_TEXT = "mayaSymmetry"                      # Maya の対称が効いているときの説明の文字
MAYA_DISABLES = ("mirrorSpace", "mirrorAxis", "mirrorTolerance")   # Maya の対称が効いている間は灰色
COLOR_SWATCH_WIDTH = 60    # 色の四角の幅 (押すと色の選択。colorSliderGrp はスライダーが長く見切れた。GUI で確認)
COLOR_SWATCH_HEIGHT = 18
BUTTONS_PER_ROW = 3        # 操作のボタンを 1 行に並べる数 (1 行に全部だと見切れた)
MAX_RADIO = 4          # radioButtonGrp に並べられる選択肢の数 (これより多ければ optionMenuGrp)

HELP_LINES = (
    "Tab / ビューの下のボタン: 作成 / 編集のモードを切り替える (1～6 は作成のその種類)",
    "作成 1 リング: ドラッグ = 輪切り (Shift で 15 度刻み)。Ctrl+ドラッグ = 円 (押した所が中心、カメラの向きに落とす)",
    "作成 2 フリーハンド: ドラッグ = 手描きの補助線 (レイジーマウス)",
    "作成 3 ライン / 4 カーブ: クリック = 点を置く (Enter / 最後の点で確定、最初の点で閉じる、Backspace・Ctrl+Z で戻す)",
    "作成 6 つなぎ線: ガイドをクリック -> (メッシュのクリック = 中継点) -> 別のガイドをクリック = 間をエッジの最短パスで"
    "つなぐ。Backspace・Ctrl+Z = 最後の点を戻す、Esc = やめる",
    "編集: 2 本選んで「つなぎ線」= カメラから見て奥側でつなぐ",
    "編集 (選んだ輪): 線のクリック = 点を足して形を曲げる (点のドラッグ・Ctrl+クリックで消す)。「断面に戻す」で戻す",
    "作成 5 ペイント: ドラッグ = 塗る (Ctrl で消す)、B+ドラッグ = 半径、S = ブラシの形 (円 / 四角)、> / < = 塗った範囲を広げる / 狭める、"
    "Enter = 囲む線にする、Esc = やめる",
    "編集: クリック / 矩形で選ぶ (Shift 切り替え / Ctrl 外す / Ctrl+Shift 足す)、Delete = 消す、Ctrl+ホイール = 選んだ閉じたガイドを平行移動、Shift+ホイール = 回す",
    "編集 (選んだ線の点): ドラッグ = 動かす、Shift / 矩形 = 複数選ぶ、Delete・Ctrl+クリック = 消す、線のクリック = 足す",
    "編集: 端の点を選んでメッシュのクリック = 伸ばす。「つなぐ」「切り離す」。ペイントを選んで 5 = 塗り直す",
    "X / ビューのボタン: 対称 (新しいガイドに反対側の相手も作る)。Maya の対称がオンの間は Maya の面で両側に",
    "シーム: ガイドから求めたエッジ。ビューの下のボタンか、この欄のボタンで UV をカット / エッジを選択",
)
ACTION_SECTION = "シーム"     # 操作のボタンを置く欄
BUTTON_WIDTH = 100


def control_name(key):
    return "{}_{}".format(CLASS_NAME, key)


# MEL に渡すと、その後ろの日本語がすべて「?」になる文字 (SkinWeightSlider で確かめた。U+301C の波ダッシュ)。
# SeamGuide でも説明に「1〜5」と書いたら、ウィンドウの文字がすべて「???」になった (GUI で確認)
UNSAFE_CHARACTERS = {"〜": "～"}


def safe_text(text):
    for bad, good in UNSAFE_CHARACTERS.items():
        text = text.replace(bad, good)
    return text


def mel_string(text):
    return '"{}"'.format(safe_text(text).replace("\\", "\\\\").replace('"', '\\"'))


def _sections(definitions):
    order = []
    for setting in definitions:
        if setting.section not in order:
            order.append(setting.section)
    return [(name, [s for s in definitions if s.section == name]) for name in order]


def _control(setting):
    if setting.kind == COLOR:
        return ("rowLayout -numberOfColumns 2 -columnWidth2 {0} {1} -columnAlign 1 \"right\"; "
                "text -label {2} -width {3} -annotation {4}; "
                "canvas -width {1} -height {5} -annotation {4} {6}; setParent ..;").format(
            LABEL_WIDTH + 4, COLOR_SWATCH_WIDTH, mel_string(setting.label), LABEL_WIDTH,
            mel_string(setting.description), COLOR_SWATCH_HEIGHT, control_name(setting.key))
    if setting.kind == BOOL:
        return "checkBoxGrp -numberOfCheckBoxes 1 -label {} -label1 \"\" -columnWidth 1 {} -annotation {} {};".format(
            mel_string(setting.label), LABEL_WIDTH, mel_string(setting.description), control_name(setting.key))
    if setting.kind == FLOAT:
        return ("floatFieldGrp -numberOfFields 1 -label {} -precision 4 -columnWidth 1 {} -columnWidth 2 80 "
                "-annotation {} {};").format(mel_string(setting.label), LABEL_WIDTH, mel_string(setting.description),
                                             control_name(setting.key))
    if setting.kind != CHOICE:
        raise ValueError("知らない種類です: {}".format(setting.kind))
    count = len(setting.choices)
    if count > MAX_RADIO:                       # radioButtonGrp は 4 つまで (-labelArray5 は無い): ドロップダウン
        items = " ".join("menuItem -label {};".format(mel_string(text)) for text in setting.choice_labels)
        return "optionMenuGrp -label {} -columnWidth 1 {} -annotation {} {}; {}".format(
            mel_string(setting.label), LABEL_WIDTH, mel_string(setting.description), control_name(setting.key), items)
    labels = " ".join(mel_string(text) for text in setting.choice_labels)
    widths = " ".join("-columnWidth {} {}".format(i + 2, CHOICE_WIDTH) for i in range(count))
    return "radioButtonGrp -numberOfRadioButtons {} -label {} -labelArray{} {} -columnWidth 1 {} {} " \
           "-annotation {} {};".format(count, mel_string(setting.label), count, labels, LABEL_WIDTH, widths,
                                       mel_string(setting.description), control_name(setting.key))


def _action_row(actions):
    """操作のボタン (BUTTONS_PER_ROW ずつの行)。"""
    lines = []
    for start in range(0, len(actions), BUTTONS_PER_ROW):
        row = actions[start:start + BUTTONS_PER_ROW]
        lines.append("rowLayout -numberOfColumns {} -columnWidth 1 {} {};".format(
            len(row) + 1, LABEL_WIDTH, " ".join("-columnWidth {} {}".format(i + 2, BUTTON_WIDTH)
                                                for i in range(len(row)))))
        lines.append('    text -label "";')
        for action in row:
            lines.append("    button -label {} -width {} -annotation {} {};".format(
                mel_string(action.label), BUTTON_WIDTH - 4, mel_string(action.description), control_name(action.id)))
        lines.append("setParent ..;")
    return lines


def _command(setting):
    if setting.kind == COLOR:
        return 'canvas -edit -pressCommand ("{}PickColor " + $toolName + " {}") {};'.format(
            CLASS_NAME, setting.key, control_name(setting.key))
    if setting.kind == BOOL:
        return 'checkBoxGrp -edit -changeCommand1 ("{} -edit -{} #1 " + $toolName) {};'.format(
            CONTEXT_COMMAND, setting.key, control_name(setting.key))
    if setting.kind == FLOAT:
        # 欄の値は呼ばれたときに読む (コマンドの文字列の中の `...` は実行のときに評価される)
        return 'floatFieldGrp -edit -changeCommand ("{} -edit -{} `floatFieldGrp -q -value1 {}` " + $toolName) {};'.format(
            CONTEXT_COMMAND, setting.key, control_name(setting.key), control_name(setting.key))
    if len(setting.choices) > MAX_RADIO:
        # 選んだ番号 (1 から) - 1 を渡す (#1 は表示の文字なので使わない)
        return "optionMenuGrp -edit -changeCommand (\"{} -edit -{} (`optionMenuGrp -q -select {}` - 1) \" + $toolName) "                "{};".format(CONTEXT_COMMAND, setting.key, control_name(setting.key), control_name(setting.key))
    parts = ['-onCommand{} ("{} -edit -{} {} " + $toolName)'.format(
        i + 1, CONTEXT_COMMAND, setting.key, choice) for i, choice in enumerate(setting.choices)]
    return "radioButtonGrp -edit {} {};".format(" ".join(parts), control_name(setting.key))


def _query(key):
    """設定の値を Python から受け取る MEL の式 (int。選択肢は番号、真偽値は 0 / 1)。"""
    return "python(\"__import__('{}', fromlist=['x']).setting_value('{}')\")".format(TOOL_UI_MODULE, key)


def _value(setting):
    if setting.kind == COLOR:
        query = "python(\"__import__('{}', fromlist=['x']).color_value('{}')\")".format(TOOL_UI_MODULE, setting.key)
        return "{{ float $c[] = {}; canvas -edit -rgbValue $c[0] $c[1] $c[2] {}; }}".format(
            query, control_name(setting.key))
    if setting.kind == BOOL:
        return "checkBoxGrp -edit -value1 ({}) {};".format(_query(setting.key), control_name(setting.key))
    if setting.kind == FLOAT:
        return "floatFieldGrp -edit -value1 ({}) {};".format(_query(setting.key), control_name(setting.key))
    kind = "optionMenuGrp" if len(setting.choices) > MAX_RADIO else "radioButtonGrp"
    return "{} -edit -select ({} + 1) {};".format(kind, _query(setting.key), control_name(setting.key))


def tool_ui_mel(definitions=DEFINITIONS):
    """Properties / Values / SetValues / RefreshUI の MEL。"""
    lines = []

    def add(text, depth=0):
        lines.append("    " * depth + text)

    add("global proc {}PickColor(string $toolName, string $key)".format(CLASS_NAME))
    add("{")
    add('string $control = "{}_" + $key;'.format(CLASS_NAME), 1)
    add("float $c[] = `canvas -q -rgbValue $control`;", 1)
    add("colorEditor -rgbValue $c[0] $c[1] $c[2];", 1)
    add("if (!`colorEditor -q -result`) return;", 1)
    add("$c = `colorEditor -q -rgb`;", 1)
    add("canvas -edit -rgbValue $c[0] $c[1] $c[2] $control;", 1)
    add('eval("{} -edit -" + $key + " \\"" + $c[0] + " " + $c[1] + " " + $c[2] + "\\" " + $toolName);'.format(
        CONTEXT_COMMAND), 1)
    add("}")
    add("")
    add("global proc {}Properties()".format(CLASS_NAME))
    add("{")
    add("setUITemplate -pushTemplate OptionsTemplate;", 1)
    add("setParent `toolPropertyWindow -q -location`;", 1)
    add("columnLayout -adjustableColumn true {};".format(CLASS_NAME), 1)
    for section, settings in _sections(definitions):
        add("frameLayout -label {} -collapsable true -collapse false;".format(mel_string(section)), 2)
        add("columnLayout -adjustableColumn true;", 3)
        for setting in settings:
            add(_control(setting), 4)
        if section == ACTION_SECTION:
            for line in _action_row([a for a in ACTIONS if a.id not in TOGGLES]):
                add(line, 4)
        if section == SYMMETRY_SECTION:
            add('text -align "left" -label "" {};'.format(control_name(MAYA_SYMMETRY_TEXT)), 4)
        add("setParent ..;", 3)
        add("setParent ..;", 2)
    add('frameLayout -label "キーとマウス" -collapsable true -collapse true;', 2)
    add("columnLayout -adjustableColumn true;", 3)
    for text in HELP_LINES:
        add('text -align "left" -label {};'.format(mel_string(text)), 4)
    add("setParent ..;", 3)
    add("setParent ..;", 2)
    add("setParent ..;", 1)
    add("setUITemplate -popTemplate;", 1)
    add("}")
    add("")
    add("global proc {}Values(string $toolName)".format(CLASS_NAME))
    add("{")
    add('string $parent = `toolPropertyWindow -q -location` + "|{}";'.format(CLASS_NAME), 1)
    add("if (`layout -exists $parent`) deleteUI $parent;", 1)
    add("{}Properties();".format(CLASS_NAME), 1)
    add("setParent $parent;", 1)
    for setting in definitions:
        add(_command(setting), 1)
    for action in [a for a in ACTIONS if a.id not in TOGGLES]:
        add('button -edit -command ("{} -edit -runAction {} " + $toolName) {};'.format(
            CONTEXT_COMMAND, action.id, control_name(action.id)), 1)
    add("{}SetValues $toolName;".format(CLASS_NAME), 1)
    add("toolPropertySelect {};".format(CLASS_NAME), 1)
    add("}")
    add("")
    add("global proc {}SetValues(string $toolName)".format(CLASS_NAME))
    add("{")
    for setting in definitions:
        add(_value(setting), 1)
    # Maya の対称が効いている間は、ツールの空間・軸・許容値を灰色にして、使っている面を出す (UVPathCut と同じ)
    add("string $maya = python(\"__import__('{}', fromlist=['x']).maya_symmetry_text()\");".format(TOOL_UI_MODULE), 1)
    add('if (`text -exists {0}`) text -edit -label $maya -visible ($maya != "") {0};'.format(
        control_name(MAYA_SYMMETRY_TEXT)), 1)
    for key in MAYA_DISABLES:
        add('if (`control -exists {0}`) control -edit -enable ($maya == "") {0};'.format(control_name(key)), 1)
    add("}")
    add("")
    add("global proc {}RefreshUI()".format(CLASS_NAME))
    add("{")
    add('string $parent = `toolPropertyWindow -q -location` + "|{}";'.format(CLASS_NAME), 1)
    add("if (!`layout -exists $parent`) return;", 1)
    add("string $tool = `currentCtx`;", 1)
    add("if (catch(`{} -q -{} $tool`)) return;".format(CONTEXT_COMMAND, definitions[0].key), 1)
    add("string $old = `setParent -q`;", 1)
    add("setParent $parent;", 1)
    add("{}SetValues $tool;".format(CLASS_NAME), 1)
    add('if ($old != "") setParent $old;', 1)
    add("}")
    return "\n".join(lines) + "\n"
