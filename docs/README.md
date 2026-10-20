# SeamGuide (試作)

有機物 (生き物) のメッシュのシームを、作り手が描いた **ガイド** から作るツール。完全な自動ではなく、
作り手がざっくりした意図 (輪切り・補助線) を描き、ツールがそれをエッジ (シーム) にして UV を切る。四角形のループがきれいなメッシュだけでなく、デシメートした不規則な三角形の
メッシュも対象。左右対称を前提にする。

## 段階

| 段階 | 内容 | 状態 |
|---|---|---|
| 1 | ガイドの計算 (core): 輪切りのガイド・補助線・対称・保存の形 | 済み ([01_guides.md](01_guides.md)) |
| 2 | ガイドを描くツール: 描く・消す・Undo・表示・シーンへの保存 | 済み ([02_tool.md](02_tool.md)) |
| 3 | ガイド -> エッジ (重み付きの最短パス) -> プレビュー -> カット | 済み ([03_seams.md](03_seams.md)) |
| 次 | つなぎ線 (2 本のガイドの間をエッジの最短パスでつなぐ) と境界のガイド (エッジから変換) | 段階 1 (境界のガイド)・2 (つなぎ線の計算)・3 (作成の 6 つなぎ線・編集のボタン)・4 (点の編集)・5 (土台への追従・対称の相手) 済み ([04_bridge_spec.md](04_bridge_spec.md)) |
| 次 | ガイドの統一 (どのガイドも 点 + 区間の作り方 + 点の付き方、同じ編集の操作) | 段階 1 (持ち方)・2 (シーム)・3〜4 (ツールの切り替え。作る道具と編集) 済み。5〜6 (ホイール・戻す操作・相手と追従) も切り替えで作り、GUI の確認待ち ([05_unified_spec.md](05_unified_spec.md)) |

ガイドは **輪切り** (リング)・**補助線** (手描きのフリーハンドと、折れ線の直線のライン)・**カーブ** (置いた点を通る
なめらかな線。点は `anchors` に残す)・**ペイント** (塗った範囲を囲む線。塗った量を `weights` に残す)。

2026-10-18 に、ガイドを使う方法だけに絞った (ユーザーの指定)。それまでに試した段階 4〜7 (開けるかの確認と
縦の線の提案・開いた見込みと歪みの表示とシームで展開・歪みに切れ目の提案・パターン「筒」) は外し、
コード・テスト・解説ごと `scripts/old/SeamGuide_stage7/` に残した (README.md に何があったか)。

## 使い方

```python
import SeamGuide
SeamGuide.tool()     # メッシュを選んでから
```

モードは **作成** と **編集** (Tab・ビューの下のボタン・ツール設定のウィンドウ。1〜4 を押すと作成):
- 作成: 新しいガイドを描くだけ。種類はキーの **1 リング / 2 フリーハンド / 3 ライン / 4 カーブ / 5 ペイント**。
  リング = ドラッグで輪切り (Shift で 15 度刻み。Ctrl+ドラッグは円を広げてカメラの向きに落とす)、フリーハンド = ドラッグで手描き (レイジーマウス)、ライン = クリックで
  直線の折れ線、カーブ = クリックで置いた点を通るなめらかな線、ペイント = ブラシで塗った範囲を囲む線 (突起の根元の
  輪など。べた塗りで Ctrl で消す、B+ドラッグで半径、S でブラシの形 (円 / 画面で見た四角 / ストロークの向きの四角)、> / < で広げる・狭める、Enter で確定。ペイントを選んで 5 で塗り直す)。描いている間の Backspace・Delete・Ctrl+Z = 最後の点を戻す、Esc = やめる。
  ホイールでは動かさない (カメラのズーム)。ガイドの上をクリックしても選ばない
- 編集: できているガイドを選んで直すだけ。選び方は Maya と同じ (クリック / 矩形、Shift 切り替え / Ctrl 外す /
  Ctrl+Shift 足す)。Delete = 消す (対称の相手も)、Ctrl+ホイール = 選んだ閉じたガイドを平行移動、Shift+ホイール = 回す (ホイールだけはカメラのズーム)、Esc = 選択を外す。
  カーブ・ラインを 1 本選ぶと点の印: 点のドラッグ = 動かす、点のクリック = 選ぶ (Delete で消す)、点の Ctrl+クリック = 消す、
  線の上のクリック = 点を足す。カーブ・補助線 (両端だけ印) の端の点を選んでメッシュをクリック = 端から伸ばす
  (対称の相手も合わせる。どれも 1 回の Undo)。線を 2 本選んで「つなぐ」= 近い端どうしを 1 本に (1 本なら閉じる)、
  点を 1 つ選んで「切り離す」= そこで 2 本に (閉じた線は開く)、
  隣り合う 2 点を選んで「切り離す」= その間の区間を消す。点は Shift・矩形でいくつでも選べ、まとめて動かす・消せる
- シーム: ガイドから求めたエッジを赤紫で描く。ビューの下の「UV をカット」「エッジを選択」
詳しくは [02_tool.md](02_tool.md)・[03_seams.md](03_seams.md)。

## 設計で決めたこと

- **ガイドはエッジを使わない**: 表面の上の折れ線 (オブジェクト空間の点の列) で持つ。デシメートした
  三角形のメッシュでも描いた形のまま残り、エッジの流れに引きずられない。エッジにするのは段階 3
- **輪切りのガイドは本当の断面の線**: UVPathCut の輪切りはエッジ (境目) を選ぶが、ここでは平面と三角形の
  交点を結んだ線
- **UVPathCut とは独立**: 平面を作る式 (十数行) だけ写す。リロード・依存の検査を単純にするため
- **numpy が必須**: core は mayapy でテストし、pytest は依存の向きだけを検査する (WeightTable と同じ)
- **Python 3 だけ** (Maya 2022〜)。core は Python 3.7 で動く書き方

## 構成

依存の向きは `tool -> scene -> core` (`tests/SeamGuide/test_dependencies.py` が検査。Qt は `tool/keys.py` だけ)。

| モジュール | 役割 |
|---|---|
| `core/geometry.py` | 視線 2 本の平面・鏡に写す・折れ線の長さと置き直し・最も近い点までの距離 |
| `core/mesh_arrays.py` | `MeshArrays`: 頂点と、面を扇形に分けた三角形 |
| `core/section.py` | 平面の断面の線 (`plane_section`) と、描いた線の範囲の線 (`curves_in_stroke`) |
| `core/stroke.py` | 補助線: 表面に当たった点の区間に分け、間隔を揃える |
| `core/guides.py` | `Guide` / `GuideSet`: 種類 (RING / LINE / CURVE)・番号・対称の相手・置いた点 (anchors)・JSON |
| `core/curve.py` | `catmull_rom`: 置いた点を通る centripetal Catmull-Rom (カーブ) |
| `core/region.py` | ペイント (面ごと): ブラシ (円の中に中心が入る面)・塗った面の境目のエッジ (囲む線)・広げる / 狭める・鏡に写した面 |
| `core/edge_chain.py` | 境界のガイド: エッジの集まりを頂点の列に・UV の境界のエッジ |
| `core/bridge.py` | つなぎ線: シームの上の位置 <-> 頂点・エッジの最短パス・端点 -> 中継点 -> 端点 |
| `core/valley.py` | つなぎ線の通り方「谷」: 頂点ごとのくぼみ・谷ほど安い道の重み |
| `core/path_model.py` | ガイドの統一した持ち方 (点・区間・付き方)・前の版からの変換・保存の形 version 2 |
| `scene/mesh.py` | `Surface`: Maya のメッシュの配列・視線を表面に当てる・表面に寄せる |
| `scene/store.py` | ガイドをシェイプのアトリビュート `seamGuides` に保存 (1 回の Undo) |
| `scene/mirror.py` | 対称の面 (Maya の対称 / オブジェクト X) |
| `scene/targets.py` | `GuideTarget`: 対象のメッシュ (Surface・ガイド・対称の面) |
| `scene/edit.py` | ガイドを探す・足す・消す・拾う (対称の相手も) |
| `core/settings.py` / `core/panel.py` / `core/tool_ui_text.py` | 設定の定義表 (モード)・ビューのボタンの並び・ツール設定のウィンドウの MEL |
| `scene/prefs.py` | 設定を optionVar に保存 |
| `core/edge_path.py` / `core/actions.py` | ガイド -> エッジの道 (重み付きの最短パス) / 操作の表 |
| `scene/seams.py` | `SeamBook` (ガイドごとのシームを覚える)・UV のカット・エッジの選択 |
| `tool/` | コンテキスト・マニピュレータ (ガイドとボタン)・描画・キー・ツール設定のウィンドウ (プラグインは `plug-ins/seamGuide.py`。登録だけ) |

## テスト

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest scripts/tests/SeamGuide                       # 依存の向き
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" scripts\tests\SeamGuide\mayapy\test_guides.py   # 段階 1。2022 でも
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" scripts\tests\SeamGuide\mayapy\test_scene.py    # 段階 2 (scene)
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" scripts\tests\SeamGuide\mayapy\test_tool.py     # 段階 2 (ツール)
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" scripts\tests\SeamGuide\mayapy\test_seams.py    # 段階 3 (シーム・カット)
```
