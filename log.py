# -*- coding: utf-8 -*-
"""スクリプトエディタに出すメッセージ (頭に LOG_PREFIX)。Maya が無ければ print。"""
from .constants import LOG_PREFIX

__all__ = ["info", "warning"]


def info(message):
    try:
        import maya.api.OpenMaya as om
        om.MGlobal.displayInfo("{}: {}".format(LOG_PREFIX, message))
    except ImportError:
        print("{}: {}".format(LOG_PREFIX, message))


def warning(message):
    try:
        import maya.api.OpenMaya as om
        om.MGlobal.displayWarning("{}: {}".format(LOG_PREFIX, message))
    except ImportError:
        print("{}: 警告: {}".format(LOG_PREFIX, message))
