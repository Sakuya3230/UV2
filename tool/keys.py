# -*- coding: utf-8 -*-
"""
キー (Delete / Backspace / Enter / Esc / Tab / 1～6 = ガイドの種類 / B = ペイントのブラシの半径 / S = ブラシの形 / > < = 塗った範囲を広げる・狭める) と、今の修飾キー。Qt のイベントフィルター (UVPathCut の
tool/keys.py と同じ方式)。

    keys.install(callback)     # ツールを有効にしたとき。callback(キーの名前) -> 受け取ったら True
    keys.uninstall()
    keys.modifiers()           # 今押している (Shift, Ctrl)。ドラッグの途中で押した / 離したものも分かる
    timer = keys.single_shot(ms, fn)   # 止めてから ms 後に fn (timer.start() で数え直し、timer.stop())

- Esc もここで受け取る: Maya は Esc でコンテキストの abortAction を呼ぶが、GUI ではドラッグ中・折れ線の
  途中で効かなかった (ユーザーの確認)。描いているもの・選択があるときだけ受け取り、無ければ Maya に渡す
- 修飾キーは押したときの MEvent だけでは、ドラッグを始めてから押した Ctrl が分からない (GUI で 15 度刻みが
  効かなかった)。ドラッグ中・離したときに QApplication.queryKeyboardModifiers で今の状態を読む

- B (押している間だけ。HELD に入れる): volumeColorBrush と同じ。押したとき・離したときを受け取り、
  ほかのアプリに移ったら忘れる。wants("hold:b") が False なら Maya に渡す (B はソフト選択など)
- V (押している間だけ): 編集で点をドラッグしている間に押していると、途中の点 (と閉じたガイドの点) もほかの
  ガイドに乗せる (Maya の V = 点へのスナップと同じ感覚。Alt はビューのカメラの操作に取られるので使わない)。
  wants("hold:v") は編集のモードでガイドを選んでいるときだけ (そうでなければ Maya に渡す)
- 1〜6 は Maya のホットキー (表示の滑らかさ) と重なるが、ツールの対象があるときはこちらで受け取る
- MPxContext にはキーのイベントが無い (Esc だけは abortAction) ので、アプリケーションにフィルターを付ける
- 受け取るのは、マウスが 3D ビューの上で、文字の入力欄にフォーカスが無く、修飾キーが無いときだけ
  (Ctrl+Z だけは別: 線を描いている間は最後の点を戻す。Maya の Undo は描きかけの線を戻せなかった。GUI で確認)
- Maya のホットキー (Delete = 選んだものを消す) より先に受け取るため、ShortcutOverride を accept する
  (callback が受け取らない (選んだガイドが無い) なら Maya に渡す)
"""
import maya.cmds as cmds

__all__ = ["install", "uninstall", "installed", "pointer_over_view", "modifiers", "alt_held", "single_shot", "KEYS", "KEYS_CTRL",
           "HOLD_KEYS", "HELD"]

KEYS = {"Key_Delete": "delete", "Key_Backspace": "back", "Key_Return": "finish", "Key_Enter": "finish",
        "Key_Escape": "cancel", "Key_Tab": "mode", "Key_1": "tool:ring", "Key_2": "tool:freehand", "Key_3": "tool:line", "Key_4": "tool:curve",
        "Key_5": "tool:paint", "Key_6": "tool:bridge", "Key_X": "symmetry", "Key_S": "brushShape",
        "Key_Greater": "region:grow", "Key_Period": "region:grow", "Key_Less": "region:shrink", "Key_Comma": "region:shrink"}
SHIFT_OK = ("region:grow", "region:shrink")   # Shift を押していても受け取る (> / < は Shift+. / Shift+,)
HOLD_KEYS = {"Key_B": "b", "Key_V": "v"}   # 押している間だけのキー (ペイントの B+ドラッグ = 半径、V+点のドラッグ = 途中の点もガイドに乗せる)
HELD = set()                               # 今押している HOLD_KEYS の名前
KEYS_CTRL = {"Key_Z": "undo"}       # Ctrl と組み合わせるもの (描いている線の最後の点を戻す)
_FILTER = []


def _qt():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    return QtCore, QtWidgets


def pointer_over_view():
    _QtCore, QtWidgets = _qt()
    typing = (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox)
    if isinstance(QtWidgets.QApplication.focusWidget(), typing):
        return False
    panel = cmds.getPanel(underPointer=True)
    return bool(panel) and cmds.getPanel(typeOf=panel) == "modelPanel"


def modifiers():
    """今押している (Shift, Ctrl)。Qt のアプリケーションが無ければ (False, False)。"""
    QtCore, QtWidgets = _qt()
    if QtWidgets.QApplication.instance() is None:
        return False, False
    state = QtWidgets.QApplication.queryKeyboardModifiers()
    return bool(state & QtCore.Qt.ShiftModifier), bool(state & QtCore.Qt.ControlModifier)


def alt_held():
    """今 Alt を押しているか (1 リングの円をドラッグ中に動かす)。Qt のアプリケーションが無ければ False。"""
    QtCore, QtWidgets = _qt()
    if QtWidgets.QApplication.instance() is None:
        return False
    return bool(QtWidgets.QApplication.queryKeyboardModifiers() & QtCore.Qt.AltModifier)


def single_shot(ms, callback):
    """1 回だけ鳴るタイマー (start() するたびに数え直す)。Qt のアプリケーションが無ければ None。"""
    QtCore, QtWidgets = _qt()
    if QtWidgets.QApplication.instance() is None:
        return None
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.setInterval(int(ms))
    timer.timeout.connect(callback)
    return timer


def install(callback, eligible=pointer_over_view, wants=None, wheel=None):
    """フィルターを付ける。wants(名前) -> 今そのキーを受け取るか (無ければいつも受け取る)。
    wheel(delta, shift, ctrl) -> True を返したら、そのホイールは Maya に渡さない (カメラのズームにしない)。"""
    uninstall()
    QtCore, QtWidgets = _qt()
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    table = {getattr(QtCore.Qt, key): name for key, name in KEYS.items()}
    ctrl_table = {getattr(QtCore.Qt, key): name for key, name in KEYS_CTRL.items()}
    hold_table = {getattr(QtCore.Qt, key): name for key, name in HOLD_KEYS.items()}
    qt = QtCore.Qt

    class KeyFilter(QtCore.QObject):
        def eventFilter(self, obj, event):
            kind = event.type()
            if kind == QtCore.QEvent.Wheel:
                if wheel is None or not eligible():
                    return False
                angle = event.angleDelta()
                delta = angle.y() or angle.x()      # Shift+ホイールを横の回転にする環境がある
                state = event.modifiers()
                return bool(wheel(delta, bool(state & qt.ShiftModifier), bool(state & qt.ControlModifier)))
            if kind == QtCore.QEvent.ApplicationDeactivate:
                HELD.clear()                     # ほかのアプリに移ると、離したキーを受け取れない
                return False
            if kind in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease) \
                    and event.key() in hold_table and not (event.modifiers() & ~qt.KeypadModifier):
                name = hold_table[event.key()]
                if kind == QtCore.QEvent.KeyRelease:
                    if name in HELD:
                        if not event.isAutoRepeat():
                            HELD.discard(name)
                        return True
                    return False
                if name not in HELD and (not eligible() or (wants is not None and not wants("hold:" + name))):
                    return False
                if kind == QtCore.QEvent.KeyPress:
                    HELD.add(name)
                event.accept()
                return True
            if kind not in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
                return False
            state = event.modifiers() & ~qt.KeypadModifier
            if state == qt.ControlModifier:
                name = ctrl_table.get(event.key())
            elif state == qt.ShiftModifier and table.get(event.key()) in SHIFT_OK:
                name = table.get(event.key())
            elif state:
                return False
            else:
                name = table.get(event.key())
            if name is None or not eligible() or (wants is not None and not wants(name)):
                return False
            if kind == QtCore.QEvent.ShortcutOverride:
                event.accept()
                return True
            if not event.isAutoRepeat():
                callback(name)
            return True

    key_filter = KeyFilter()
    app.installEventFilter(key_filter)
    _FILTER.append(key_filter)
    return key_filter


def uninstall():
    if not _FILTER:
        return
    _QtCore, QtWidgets = _qt()
    app = QtWidgets.QApplication.instance()
    for key_filter in _FILTER:
        if app is not None:
            app.removeEventFilter(key_filter)
    del _FILTER[:]
    HELD.clear()


def installed():
    return bool(_FILTER)
