# -*- coding: utf-8 -*-
"""
Shared parameter reading utilities for FG-Tools scripts.

All helpers return '' (never None) so callers can safely use truthiness checks
without extra null-guards.
"""

from Autodesk.Revit.DB import ElementId


def get_param_string(element, param_names):
    """
    Return the first non-empty string value from candidate parameter names.

    Accepts a single name (str) or a list of names. Tries AsString() first,
    then AsValueString() as a fallback. Returns '' if no value is found.
    """
    if isinstance(param_names, str):
        param_names = [param_names]

    for name in param_names:
        try:
            param = element.LookupParameter(name)
            if not param:
                continue
            value = param.AsString() or param.AsValueString()
            if value and value.strip():
                return value.strip()
        except Exception:
            continue

    return ""


def get_param_string_with_type_fallback(element, param_names, doc):
    """
    Read a parameter value from the instance, falling back to its type element.

    Useful for parameters that may only be set on the family type.
    """
    value = get_param_string(element, param_names)
    if value:
        return value

    try:
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            type_element = doc.GetElement(type_id)
            if type_element:
                return get_param_string(type_element, param_names)
    except Exception:
        pass

    return ""
