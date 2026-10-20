# -*- coding: utf-8 -*-
"""名前と既定の値 (Maya に依存しない)。プラグイン (plug-ins/seamGuide.py) とパッケージの両方が使う。"""

LOG_PREFIX = "シームガイド"
GUIDE_ATTRIBUTE = "seamGuides"     # ガイドを保存するメッシュのシェイプの文字列のアトリビュート
SPACING_RATIO = 0.004              # ガイドの点の間隔 (メッシュの外接箱の対角線に対する割合)
MIRROR_TOLERANCE_RATIO = 0.01      # 対称の相手が自分と重なるとみなす距離 (同じ割合)

PLUGIN_NAME = "seamGuide"
CONTEXT_COMMAND = "seamGuideCtx"
TOOL_COMMAND = "seamGuideTool"
TOOL_CONTEXT = "seamGuideContext"
MANIP_NODE = "seamGuideManip"
# 社内・個人用の範囲 (0x00000000〜0x0007ffff)。ほかの自作: 0x0007F201〜F206
MANIP_TYPE_ID = 0x0007F207
PLUGIN_COMMANDS = (CONTEXT_COMMAND, TOOL_COMMAND)
PLUGIN_NODES = (MANIP_NODE,)

# 色 (表示の色。r, g, b)
RING_COLOR = (0.25, 0.85, 1.0)     # 輪切りのガイド
LINE_COLOR = (1.0, 0.55, 0.15)     # 補助線 (ペイント・ライン)
EDGE_COLOR = (0.95, 0.95, 0.95)    # 境界のガイド (既存のエッジから変換したもの)。白 (ほかのガイド・シームと区別)
CURVE_COLOR = (0.75, 0.55, 1.0)    # カーブ
BRIDGE_COLOR = (1.0, 0.4, 0.4)     # つなぎ線
REGION_COLOR = (0.45, 0.95, 0.55)  # ペイント (塗った範囲を囲む線)
PAINT_COLOR = (0.25, 0.55, 1.0)    # 塗った範囲の重ね塗り (線の色とぶつからない青)
PAINT_ALPHA = 0.25                 # 塗った範囲の重ね塗りの不透明度 (線が見えるよう薄く)
PAINT_LINE_COLOR = (1.0, 1.0, 0.0)   # 塗っている間・選んだペイントの囲む線 (前面に描く。黄)
BRUSH_COLOR = (1.0, 1.0, 0.0)      # ブラシの円 (メッシュに当たっている)
BRUSH_RADIUS_RATIO = 0.03          # ブラシの半径の既定 (メッシュの大きさに対する割合)
RESIZE_RATIO = 0.25                # > / < で塗った範囲を広げる・狭める距離 (ブラシの半径に対する割合)
RADIUS_DRAG_PIXELS = 150.0         # B+ドラッグ: 右へこれだけ動かすと半径が 2 倍

PAINT_OFFSET_RATIO = 0.0005        # 重ね塗りの面を法線の向きに浮かせる量 (メッシュの大きさに対する割合)
HANDLE_COLOR = (1.0, 1.0, 1.0)     # 点の印 (選んだカーブ・描いている線。画面の 2D。黒いふちの上に塗る)
HANDLE_SELECTED_COLOR = (1.0, 0.85, 0.0)  # 選んだ点の印
HANDLE_BORDER = (0.0, 0.0, 0.0)    # 点の印のふち
HANDLE_PIXELS = 6                  # 点の印の大きさ (半分。画面の px。ふちは 2 px 外)
HOVER_COLOR = (1.0, 1.0, 0.6)      # マウスの下のガイド
SELECTED_COLOR = (1.0, 1.0, 0.0)   # 選んだガイド
PREVIEW_COLOR = (1.0, 0.95, 0.3)   # ドラッグ中のプレビュー
SEAM_COLOR = (0.95, 0.25, 0.75)    # ガイドから求めたエッジ (シーム。段階 3)
SEAM_WIDTH = 2.0
STROKE_COLOR = (1.0, 1.0, 1.0)     # 描いている線 (画面の 2D)
STRING_COLOR = (0.6, 0.6, 0.6)     # レイジーマウスのひも・折れ線のゴム紐
GUIDE_WIDTH = 2.0
SELECTED_WIDTH = 4.0
PICK_PIXELS = 10.0                 # クリック・ホバーでガイドを拾う距離 (画面の px)
DRAG_PIXELS = 4                    # これ以上動かしたらドラッグ (それ未満はクリック)
SAMPLE_PIXELS = 4                  # 補助線: 画面の線をこの間隔で表面に当てる
LAZY_PIXELS = 20                   # レイジーマウスのひもの長さ (画面の px)
STEP_DEGREES = 15.0                # Ctrl の刻み (輪切りの線・折れ線の区間の向き)
TILT_DEGREES = 3.0                 # Shift+ホイールで輪を傾ける 1 目盛り (Ctrl+Shift は STEP_DEGREES)
SHIFT_FAST = 5                     # Ctrl+ホイールの平行移動は、この目盛りの数ずつ
COMMIT_MS = 500                    # ホイールを止めてから、動かした輪を書く (1 回の Undo) まで
WHEEL_PIXELS = 60                  # ホイールで輪を動かすのは、カーソルが選んだ輪 (か相手) からこの距離 (画面の px) 以内のとき
