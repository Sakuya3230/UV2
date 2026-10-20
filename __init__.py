# -*- coding: utf-8 -*-
"""
SeamGuide: 作り手が描いたガイド (輪切り・補助線) から、有機物のメッシュのシームを作るツール (試作)。

ガイドはエッジを使わない表面の上の線で、エッジにするのは後の段階。段階と設計は docs/README.md。

    import SeamGuide.reloader as r; r.reload().reload_modules()

Python 3 だけ (Maya 2022〜)。numpy が要る (scripts/site-packages/<ver>)。
"""
from .api import *
