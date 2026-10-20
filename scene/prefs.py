# -*- coding: utf-8 -*-
"""
設定を optionVar (seamGuideSettings) に保存する。既定値と違う項目だけを JSON で 1 つにまとめる
(UVPathCut の scene/prefs.py と同じ)。
"""
import json

import maya.cmds as cmds

from ..core import settings as settings_module

__all__ = ["OPTION_VAR", "OptionVarStorage"]

OPTION_VAR = "seamGuideSettings"


class OptionVarStorage(object):
    def __init__(self, name=OPTION_VAR):
        self.name = name

    def load(self):
        try:
            if not cmds.optionVar(exists=self.name):
                return None
            data = json.loads(cmds.optionVar(query=self.name))
        except (RuntimeError, ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    def save(self, values):
        defaults = settings_module.defaults()
        changed = {key: value for key, value in values.items() if defaults.get(key) != value}
        if changed:
            cmds.optionVar(stringValue=(self.name, json.dumps(changed, sort_keys=True)))
        elif cmds.optionVar(exists=self.name):
            cmds.optionVar(remove=self.name)
