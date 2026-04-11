# -*- coding: utf-8 -*-
"""
Shared constants used across FG-Tools scripts.

Import specific names as needed, e.g.:
    from fg_constants import PARAM_LEVEL_ID, DATA_OUTLET_CATEGORIES
"""

from Autodesk.Revit.DB import BuiltInCategory

# ── Parameter names ─────────────────────────────────────────────────────────

PARAM_LEVEL_ID = "LEVEL ID"
PARAM_BUILDING_SECTOR = "BUILDING SECTOR"
PARAM_MARK = "Mark"
PARAM_DOOR_ID = "DOOR ID"

# ── Family name identifiers ──────────────────────────────────────────────────

FAMILY_FG_CAMERA = "FG-CAMERA"
FAMILY_FG_BARBELL_DEFAULT = "FG-ACS DOOR BARBELL"

# ── Project-specific codes ───────────────────────────────────────────────────

# Valid building sector codes for this project (5A–5G)
VALID_SECTORS = frozenset(["5A", "5B", "5C", "5D", "5E", "5F", "5G"])

# ── Schedule / level helpers ─────────────────────────────────────────────────

# Candidate parameter names used by Revit to store which level an element is on
SCHEDULE_LEVEL_PARAM_CANDIDATES = [
    "Schedule Level",
    "SCHEDULE LEVEL",
    "Level",
    "LEVEL",
    "Reference Level",
]

# ── Element categories ───────────────────────────────────────────────────────

# Revit categories that may contain data outlet elements
DATA_OUTLET_CATEGORIES = [
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
]
