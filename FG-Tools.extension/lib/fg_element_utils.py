# -*- coding: utf-8 -*-
"""
Shared element utility functions for FG-Tools scripts.
"""

from Autodesk.Revit.DB import ElementId, FamilyInstance, LocationCurve, LocationPoint
from fg_string_utils import safe_string


def get_parent_or_host(element):
    """
    Return (parent_element, source_label) for nested FamilyInstances.

    Tries SuperComponent first, then Host. Returns (None, '') if neither exists.
    """
    try:
        if isinstance(element, FamilyInstance):
            parent = element.SuperComponent
            if parent:
                return parent, "SuperComponent"
    except Exception:
        pass

    try:
        if isinstance(element, FamilyInstance):
            host = element.Host
            if host:
                return host, "Host"
    except Exception:
        pass

    return None, ""


def get_probe_point(element):
    """
    Return a representative XYZ point for an element.

    Tries LocationPoint, then mid-point of LocationCurve, then bounding box
    center. Returns None if no point can be derived.
    """
    try:
        location = element.Location
        if isinstance(location, LocationPoint):
            return location.Point
        if isinstance(location, LocationCurve) and location.Curve:
            return location.Curve.Evaluate(0.5, True)
    except Exception:
        pass

    try:
        bbox = element.get_BoundingBox(None)
        if bbox:
            return (bbox.Min + bbox.Max) * 0.5
    except Exception:
        pass

    return None


def get_element_family_info(element):
    """
    Return (category_name, family_name, type_name) strings for reporting.

    Falls back gracefully when any attribute is unavailable.
    """
    category_name = ""
    family_name = ""
    type_name = ""

    try:
        if element.Category:
            category_name = safe_string(element.Category.Name)
    except Exception:
        pass

    try:
        if isinstance(element, FamilyInstance) and element.Symbol:
            family_name = safe_string(element.Symbol.FamilyName)
            type_name = safe_string(element.Symbol.Name)
    except Exception:
        pass

    if not family_name:
        family_name = safe_string(getattr(element, "Name", ""))

    return category_name, family_name, type_name


def get_level_name_from_level_id(element, doc):
    """
    Read the element's LevelId and return the level's Name string.

    Returns '' if no valid level is found.
    """
    try:
        level_id = element.LevelId
        if level_id and level_id != ElementId.InvalidElementId:
            level = doc.GetElement(level_id)
            if level and getattr(level, "Name", None):
                return safe_string(level.Name)
    except Exception:
        pass
    return ""
