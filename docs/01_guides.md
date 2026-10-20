# 1. ガイドの計算

[目次](README.md)

## 目的

作り手の意図を、エッジに関係なく表面の上の線として持つ。描く道具 (段階 2) とエッジにする計算 (段階 3) の
土台になる、ガイドの形と計算を作る。

## 追加した箇所

| ファイル | 内容 |
|---|---|
| [core/geometry.py](../core/geometry.py) | `plane_from_rays` / `reflect` / `resample` / `mean_nearest_distance` |
| [core/mesh_arrays.py](../core/mesh_arrays.py) | `MeshArrays.fromPolygons` (面を扇形の三角形に) |
| [core/section.py](../core/section.py) | `plane_section` / `curves_in_stroke` |
| [core/stroke.py](../core/stroke.py) | `surface_runs` / `line_points` |
| [core/guides.py](../core/guides.py) | `Guide` / `GuideSet` / `is_self_mirror` |
| [scene/mesh.py](../scene/mesh.py) | `Surface` (`arrays` / `raycast` / `closest` / `toObject`) |

## 仕組み

**輪切りのガイド** (`plane_section`):
1. 描いた線の両端の視線 2 本を含む平面を作る (UVPathCut の輪切りと同じ式)
2. 全頂点の、平面からの符号付きの距離 d を出す (0 は表側)
3. 頂点の表裏が分かれる三角形は、ちょうど 2 本の辺で平面と交わる。2 つの交点を結ぶ線分が断面の一部
4. 交点は辺ごとに 1 つ (隣の三角形と共有) なので、辺を節にして線分をたどると、閉じた輪か、縁で切れた線になる

2〜3 は全三角形の配列の計算、4 は平面と交わる三角形の数だけの Python のループ (全体のごく一部)。

**描いた線の範囲** (`curves_in_stroke`): 平面は視線を含むので、断面の点は画面ではすべて描いた線の延長の上に
写る。線の始点を 0・終点を 1 とした位置に、ほぼ全部の点 (98%) が収まる線だけを残す (腕を横切って描けば、
平面が胴体も切っても、胴体の断面は線の外まで伸びるので外れる)。

**補助線** (`Surface.raycast` -> `line_points`): 画面の線を数 px おきの視線にして表面に当て、当たらない所で
区間に分け、点の間隔を長さで揃える (近くと遠くで間隔を同じにするため)。

**対称**: ガイドの点を対称の面で鏡に写し、`Surface.closest` (MMeshIntersector) で表面に寄せる。左右で頂点の
位置がずれた不規則なメッシュでも表面に乗る。鏡に写した線が元の線とほぼ重なる (中心を通る輪) なら、相手を
作らない (`is_self_mirror`。最も近い点までの距離の平均が許容値以下)。相手どうしは `partner` で互いに指し、
消すときはいっしょに消す。

**保存の形**: `GuideSet.toJson` (`format: SeamGuide.guides`)。段階 2 でメッシュのシェイプの文字列の
アトリビュートに入れる予定 (シーンといっしょに残る)。

## 落とし穴

- `MFnMesh.closestIntersection` は、当たらないと **None を返す** (面の番号が -1 の結果ではない)
- `MMeshIntersector` は単位行列で作ると、問い合わせも結果もオブジェクト空間のまま (ガイドはオブジェクト空間)
- Maya の行列は行ベクトル (`p · M`)。numpy に移すときは `点 @ 行列`

## 実測

| | 2027 | 2022 |
|---|---|---|
| 頂点 30 万・三角形 60 万のメッシュを配列にする | 450 ms | 630 ms |
| 断面 1 回 | 23〜30 ms | 19〜38 ms |

断面はドラッグ中に計算し直しても間に合う速さ (段階 2 でプレビューに使う)。

## 試し方

```
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" scripts\tests\SeamGuide\mayapy\test_guides.py
```

円柱・デシメートした球 (4 つの高さ)・板 (開いた線)・2 本の筒 (線の範囲)・補助線・対称と保存・30 万頂点の速さ。
