# -*- coding: utf-8 -*-
__title__ = "Data Outlet Levels" # Name of the button displayed in Revit UI
__doc__ = """
Version = 1.1
Date = 02.04.2026
_____________________________________________________________________
Description:
Populate LEVEL ID for data outlet schedule elements using schedule-driven
level mapping in the selected schedule.

Key behavior:
- Uses a schedule picker scoped to Data Outlet and Multi-Category schedules
- Derives mapping from schedule levels matching: LEVEL 0# - ...
- Ignores and flags WCS Civil 0.0 hosted outlets for manual correction
- Falls back to host family level for nested outlets missing schedule level
- Skips already-correct LEVEL ID values for faster processing
_____________________________________________________________________
Version History:
- [02.04.2026] v1.1 - Added dynamic level derivation, nested host fallback,
  WCS Civil 0.0 surfacing, and performance skip for already-correct values.
- [01.04.2026] v1.0 - Initial release.
_____________________________________________________________________
Author: Hayden Fulghum""" # Button Description shown in Revit UI

__author__ = "Hayden Fulghum"
__helpurl__ = "https://github.com/baptistelechat/pyrevit-with-vscode"
__min_revit_ver__ = 2025

# ╦╔╦╗╔═╗╔═╗╦═╗╔╦╗╔═╗
# ║║║║╠═╝║ ║╠╦╝ ║ ╚═╗
# ╩╩ ╩╩  ╚═╝╩╚═ ╩ ╚═╝ IMPORTS 📚
# ==================================================
import os, re
from Autodesk.Revit.DB import FamilyInstance, Transaction

from pyrevit import revit, forms, script

import clr
clr.AddReference("System")
from System.Collections.Generic import List

# Shared FG-Tools utilities
from fg_constants import PARAM_LEVEL_ID, SCHEDULE_LEVEL_PARAM_CANDIDATES
from fg_string_utils import safe_string, normalize_whitespace
from fg_param_utils import get_param_string
from fg_element_utils import get_parent_or_host, get_level_name_from_level_id
from fg_schedule_utils import collect_schedule_elements, pick_schedule

# ╦  ╦╔═╗╦═╗╦╔═╗╔╗ ╦  ╔═╗╔═╗
# ╚╗╔╝╠═╣╠╦╝║╠═╣╠╩╗║  ║╣ ╚═╗
#  ╚╝ ╩ ╩╩╚═╩╩ ╩╚═╝╩═╝╚═╝╚═╝ VARIABLES 📄
# ==================================================
doc   = revit.doc
uidoc = revit.uidoc
app   = revit.HOST_APP
PATH_SCRIPT = os.path.dirname(__file__)

logger = script.get_logger()
output = script.get_output()

LEVEL_PREFIX_PATTERN = re.compile(r"^LEVEL\s*0?(\d+)\s*-\s*", re.IGNORECASE)
WCS_CIVIL_LEVEL_KEY  = "WCS CIVIL 0.0"

# ╔═╗╦ ╦╔╗╔╔═╗╔╦╗╦╔═╗╔╗╔╔═╗
# ╠╣ ║ ║║║║║   ║ ║║ ║║║║╚═╗
# ╚  ╚═╝╝╚╝╚═╝ ╩ ╩╚═╝╝╚╝╚═╝ FUNCTIONS 🛠️
# ==================================================

def _normalize_level_key(level_text):
    return normalize_whitespace(level_text)


def _get_effective_schedule_level_text(element):
    """Return (level_text, used_host_fallback, diagnostic_reason) for an element."""
    # 1) Direct schedule-level parameter on the element.
    level_text = get_param_string(element, SCHEDULE_LEVEL_PARAM_CANDIDATES)
    if level_text:
        return level_text, False, "Direct element schedule level parameter"

    # 2) Element's own LevelId name.
    level_text = get_level_name_from_level_id(element, doc)
    if level_text:
        return level_text, False, "Direct element LevelId"

    # 3) For nested/shared outlets, use parent host family level.
    parent, parent_source = get_parent_or_host(element)
    if parent:
        level_text = get_param_string(parent, SCHEDULE_LEVEL_PARAM_CANDIDATES)
        if not level_text:
            level_text = get_level_name_from_level_id(parent, doc)
        if level_text:
            return level_text, True, "{} level fallback".format(parent_source)
        return "", False, "{} found but no readable level on host family".format(parent_source)

    if isinstance(element, FamilyInstance):
        return "", False, (
            "No direct level value and no SuperComponent/Host found "
            "(possible orphaned nested outlet)"
        )

    return "", False, "No direct schedule level or level id available"


def _try_get_direct_schedule_level_text(element):
    level_text = get_param_string(element, SCHEDULE_LEVEL_PARAM_CANDIDATES)
    if level_text:
        return level_text
    return get_level_name_from_level_id(element, doc)


def _collect_available_schedule_levels(elements):
    available_levels = set()
    for element in elements:
        level_text = get_param_string(element, SCHEDULE_LEVEL_PARAM_CANDIDATES)
        normalized  = _normalize_level_key(level_text)
        if normalized:
            available_levels.add(normalized)
    return available_levels


def _derive_level_id_lookup(available_level_keys):
    lookup = {}
    for level_key in sorted(available_level_keys):
        if level_key == WCS_CIVIL_LEVEL_KEY:
            continue

        match = LEVEL_PREFIX_PATTERN.match(level_key)
        if not match:
            continue

        try:
            level_num = int(match.group(1))
        except Exception:
            continue

        if level_num <= 0:
            continue

        lookup[level_key] = "L{}".format(level_num)

    return lookup


def _build_inspection_record(element, issue, level_text, reason=""):
    from fg_element_utils import get_element_family_info
    category_name, family_name, type_name = get_element_family_info(element)
    return {
        "id":             element.Id.IntegerValue,
        "element_id":     element.Id,
        "issue":          issue,
        "reason":         safe_string(reason),
        "schedule_level": safe_string(level_text),
        "category":       category_name,
        "family":         family_name,
        "type":           type_name,
    }


def _set_level_ids_for_schedule(schedule_view):
    elements         = collect_schedule_elements(schedule_view, doc)
    available_levels = _collect_available_schedule_levels(elements)
    level_id_lookup  = _derive_level_id_lookup(available_levels)

    if not elements:
        return {
            "total": 0, "updated": 0, "skipped_no_level": 0,
            "skipped_unmapped_level": 0, "skipped_wcs_civil": 0,
            "used_host_level_fallback": 0, "skipped_missing_level_id": 0,
            "skipped_read_only": 0, "unchanged": 0,
            "unmapped_examples": [], "inspection_items": [],
            "derived_level_rules": {},
        }

    summary = {
        "total": len(elements), "updated": 0, "skipped_no_level": 0,
        "skipped_unmapped_level": 0, "skipped_wcs_civil": 0,
        "used_host_level_fallback": 0, "skipped_missing_level_id": 0,
        "skipped_read_only": 0, "unchanged": 0,
        "unmapped_examples": [], "inspection_items": [],
        "derived_level_rules": level_id_lookup,
    }

    for element in elements:
        level_id_param = element.LookupParameter(PARAM_LEVEL_ID)
        existing = (level_id_param.AsString() or "").strip() if level_id_param else ""

        direct_level_text     = _try_get_direct_schedule_level_text(element)
        normalized_direct     = _normalize_level_key(direct_level_text)
        resolved_direct_level = level_id_lookup.get(normalized_direct)

        # Fast path: element already has the correct LEVEL ID from its own level data.
        if existing and resolved_direct_level and existing == resolved_direct_level:
            summary["unchanged"] += 1
            continue

        level_text            = direct_level_text
        used_host_fallback    = False
        level_diagnostic_reason = "Direct element schedule level/LevelId"
        if not level_text:
            level_text, used_host_fallback, level_diagnostic_reason = _get_effective_schedule_level_text(element)
            if used_host_fallback:
                summary["used_host_level_fallback"] += 1

        if not level_text:
            summary["skipped_no_level"] += 1
            summary["inspection_items"].append(
                _build_inspection_record(element, "Missing schedule level", level_text,
                                         reason=level_diagnostic_reason)
            )
            continue

        normalized_level = _normalize_level_key(level_text)
        if normalized_level == WCS_CIVIL_LEVEL_KEY:
            summary["skipped_wcs_civil"] += 1
            summary["inspection_items"].append(
                _build_inspection_record(element, "Invalid host level (WCS Civil 0.0)", level_text,
                                         reason=level_diagnostic_reason)
            )
            continue

        resolved_level_id = level_id_lookup.get(normalized_level)
        if not resolved_level_id:
            summary["skipped_unmapped_level"] += 1
            summary["inspection_items"].append(
                _build_inspection_record(
                    element,
                    "Schedule level does not match 'LEVEL 0# - ...' pattern",
                    level_text,
                    reason=level_diagnostic_reason,
                )
            )
            if len(summary["unmapped_examples"]) < 10:
                summary["unmapped_examples"].append(level_text)
            continue

        if not level_id_param:
            summary["skipped_missing_level_id"] += 1
            continue
        if level_id_param.IsReadOnly:
            summary["skipped_read_only"] += 1
            continue

        if existing == resolved_level_id:
            summary["unchanged"] += 1
            continue

        if level_id_param.Set(resolved_level_id):
            summary["updated"] += 1

    return summary

# ╔╦╗╔═╗╦╔╗╔
# ║║║╠═╣║║║║
# ╩ ╩╩ ╩╩╝╚╝ MAIN 🎯
# ==================================================
if __name__ == '__main__':
    selected_schedule = pick_schedule(doc, uidoc, __title__)

    t = Transaction(doc, __title__)
    t.Start()

    try:
        result = _set_level_ids_for_schedule(selected_schedule)
        t.Commit()
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        logger.exception("Data Outlet Levels failed: {}".format(ex))
        forms.alert("Failed to update LEVEL ID values. See pyRevit output for details.", title=__title__)
        raise

    report_lines = [
        "Schedule: {}".format(selected_schedule.Name),
        "Elements in schedule: {}".format(result["total"]),
        "Updated LEVEL ID: {}".format(result["updated"]),
        "Unchanged: {}".format(result["unchanged"]),
        "Used host family level fallback: {}".format(result["used_host_level_fallback"]),
        "Skipped (no schedule level): {}".format(result["skipped_no_level"]),
        "Skipped (unmapped schedule level): {}".format(result["skipped_unmapped_level"]),
        "Skipped (WCS Civil 0.0): {}".format(result["skipped_wcs_civil"]),
        "Skipped (missing LEVEL ID parameter): {}".format(result["skipped_missing_level_id"]),
        "Skipped (read-only LEVEL ID): {}".format(result["skipped_read_only"]),
    ]

    if result["derived_level_rules"]:
        report_lines.append("Derived level rules from schedule levels:")
        for level_key in sorted(result["derived_level_rules"].keys()):
            report_lines.append(
                "- {} -> {}".format(level_key, result["derived_level_rules"][level_key])
            )

    if result["unmapped_examples"]:
        report_lines.append("Unmapped examples:")
        for level_name in sorted(set(result["unmapped_examples"])):
            report_lines.append("- {}".format(level_name))

    report = "\n".join(report_lines)
    print(report)

    if result["skipped_wcs_civil"]:
        print("\nWCS Civil 0.0 hosting errors:")
        wcs_items = [
            item for item in result["inspection_items"]
            if item.get("issue") == "Invalid host level (WCS Civil 0.0)"
        ]
        for idx, item in enumerate(wcs_items, 1):
            element_ref = output.linkify(item["element_id"])
            print(
                "{0}. Element: {1} | Category: {2} | Family: {3} | Type: {4}".format(
                    idx,
                    element_ref,
                    item["category"] or "-",
                    item["family"] or "-",
                    item["type"] or "-",
                )
            )

    if result["inspection_items"]:
        print("\nOutlets requiring manual review:")
        for idx, item in enumerate(result["inspection_items"], 1):
            element_ref = output.linkify(item["element_id"])
            detail = (
                "{0}. {1} | Element: {2} | Category: {3} | Family: {4} | Type: {5} | "
                "Schedule Level: {6} | Reason: {7}"
            ).format(
                idx,
                item["issue"],
                element_ref,
                item["category"] or "-",
                item["family"] or "-",
                item["type"] or "-",
                item["schedule_level"] or "<empty>",
                item.get("reason") or "-",
            )
            print(detail)

    alert_message = report
    if result["skipped_wcs_civil"]:
        alert_message += (
            "\n\nWARNING: {0} outlet(s) are hosted on WCS Civil 0.0 and were ignored for LEVEL ID mapping. "
            "Review these in pyRevit output under 'WCS Civil 0.0 hosting errors'."
        ).format(result["skipped_wcs_civil"])

    forms.alert(alert_message, title=__title__)

    logger.success(':chequered_flag: Script is finished.')
    print('-' * 50)
