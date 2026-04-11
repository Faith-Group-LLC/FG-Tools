# -*- coding: utf-8 -*-
__title__ = "Data Outlet Sectors"
__doc__ = """
Version = 1.0
Date = 03.04.2026
_____________________________________________________________________
Description:
Populate BUILDING SECTOR for data outlets in a selected schedule using
ZONE 5A-5G scope boxes.

Key behavior:
- Uses a schedule picker scoped to Data Outlet and Multi-Category schedules
- Assigns BUILDING SECTOR when an outlet lies inside one matching ZONE scope box
- Resolves overlapping ZONE scope boxes by choosing the nearest scope-box center
- Falls back to the host family for read-only nested outlets and verifies propagation
_____________________________________________________________________
Author: Hayden Fulghum
"""
__author__ = "Hayden Fulghum"
__min_revit_ver__ = 2025

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FamilyInstance,
    FilteredElementCollector,
    Outline,
    Transaction,
)

import re
from pyrevit import forms, revit, script

# Shared FG-Tools utilities
from fg_constants import PARAM_BUILDING_SECTOR
from fg_string_utils import safe_string, normalize
from fg_param_utils import get_param_string
from fg_element_utils import get_element_family_info, get_parent_or_host, get_probe_point
from fg_schedule_utils import collect_schedule_elements, pick_schedule

doc    = revit.doc
uidoc  = revit.uidoc
logger = script.get_logger()
output = script.get_output()

ZONE_SCOPE_BOX_PATTERN    = re.compile(r"\bZONE\s*(5[A-G])\b", re.IGNORECASE)
SCOPE_BOX_Z_EXTENSION_FEET = 30.0

# ╔═╗╦ ╦╔╗╔╔═╗╔╦╗╦╔═╗╔╗╔╔═╗
# ╠╣ ║ ║║║║║   ║ ║║ ║║║║╚═╗
# ╚  ╚═╝╝╚╝╚═╝ ╩ ╩╚═╝╝╚╝╚═╝ FUNCTIONS 🛠️
# ==================================================

def _collect_zone_scope_boxes():
    scope_boxes = []
    elements = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_VolumeOfInterest)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    for element in elements:
        name_text = safe_string(getattr(element, "Name", ""))
        match     = ZONE_SCOPE_BOX_PATTERN.search(name_text)
        if not match:
            continue

        try:
            bbox = element.get_BoundingBox(None)
        except Exception:
            bbox = None

        if not bbox:
            continue

        sector = normalize(match.group(1))
        scope_boxes.append(
            {
                "element":    element,
                "element_id": element.Id,
                "name":       name_text,
                "sector":     sector,
                "bbox":       bbox,
                "outline":    Outline(bbox.Min, bbox.Max),
                "center":     (bbox.Min + bbox.Max) * 0.5,
            }
        )

    return sorted(scope_boxes, key=lambda item: (item["sector"], item["name"]))


def _point_inside_bbox(point, bbox, tolerance=0.0, z_extension=0.0):
    if not point or not bbox:
        return False
    return (
        bbox.Min.X - tolerance <= point.X <= bbox.Max.X + tolerance
        and bbox.Min.Y - tolerance <= point.Y <= bbox.Max.Y + tolerance
        and bbox.Min.Z - tolerance <= point.Z <= bbox.Max.Z + tolerance + z_extension
    )


def _choose_scope_box_for_point(point, scope_boxes):
    matches = [
        box for box in scope_boxes
        if _point_inside_bbox(point, box["bbox"], z_extension=SCOPE_BOX_Z_EXTENSION_FEET)
    ]
    if not matches:
        return None, []
    if len(matches) == 1:
        return matches[0], matches

    closest = min(
        matches,
        key=lambda item: (point.DistanceTo(item["center"]), item["sector"], item["name"]),
    )
    return closest, matches


def _build_inspection_record(element, issue, probe_point=None, reason="", matches=None):
    category_name, family_name, type_name = get_element_family_info(element)

    point_text    = ""
    if probe_point:
        point_text = "X={0:.3f}, Y={1:.3f}, Z={2:.3f}".format(
            probe_point.X, probe_point.Y, probe_point.Z
        )

    matched_zones = ["{} ({})".format(item["sector"], item["name"]) for item in (matches or [])]

    return {
        "id":            element.Id.IntegerValue,
        "element_id":    element.Id,
        "issue":         issue,
        "reason":        safe_string(reason),
        "probe_point":   point_text,
        "matched_zones": matched_zones,
        "category":      category_name,
        "family":        family_name,
        "type":          type_name,
    }


def _handle_read_only_sector_parameter(
    element, sector_param, target_sector, probe_point, matches, summary, host_assignments,
):
    parent, parent_source = get_parent_or_host(element)
    if not parent:
        summary["skipped_read_only"]          += 1
        summary["skipped_hostless_read_only"] += 1
        summary["inspection_items"].append(
            _build_inspection_record(
                element,
                "Read-only BUILDING SECTOR with no host family",
                probe_point=probe_point,
                reason="Resolved target sector: {}. No SuperComponent/Host found.".format(target_sector),
                matches=matches,
            )
        )
        return

    host_key    = parent.Id.IntegerValue
    prior_target = host_assignments.get(host_key)
    if prior_target and prior_target != target_sector:
        summary["skipped_read_only"]    += 1
        summary["skipped_host_conflict"] += 1
        summary["inspection_items"].append(
            _build_inspection_record(
                element,
                "Conflicting host BUILDING SECTOR targets",
                probe_point=probe_point,
                reason=(
                    "Resolved target sector: {0}. {1} Id {2} already assigned target {3} in this run."
                ).format(target_sector, parent_source, host_key, prior_target),
                matches=matches,
            )
        )
        return

    host_param = parent.LookupParameter(PARAM_BUILDING_SECTOR)
    if not host_param:
        summary["skipped_read_only"]                  += 1
        summary["skipped_host_missing_parameter"]     += 1
        summary["inspection_items"].append(
            _build_inspection_record(
                element,
                "Host missing BUILDING SECTOR parameter",
                probe_point=probe_point,
                reason="Resolved target sector: {}. {} Id {} has no writable parameter to drive the nested outlet.".format(
                    target_sector, parent_source, host_key,
                ),
                matches=matches,
            )
        )
        return

    if host_param.IsReadOnly:
        summary["skipped_read_only"]           += 1
        summary["skipped_host_read_only"]      += 1
        summary["inspection_items"].append(
            _build_inspection_record(
                element,
                "Host BUILDING SECTOR is also read-only",
                probe_point=probe_point,
                reason="Resolved target sector: {}. {} Id {} cannot be updated.".format(
                    target_sector, parent_source, host_key,
                ),
                matches=matches,
            )
        )
        return

    host_assignments[host_key] = target_sector
    host_existing = get_param_string(host_param if False else parent, PARAM_BUILDING_SECTOR)
    host_changed  = False

    if normalize(get_param_string(parent, PARAM_BUILDING_SECTOR)) != target_sector:
        host_param.Set(target_sector)
        host_changed = True

    # Regenerate is intentional here: Revit must propagate the host parameter
    # change to the nested outlet before we can verify the result.
    doc.Regenerate()

    nested_value = get_param_string(element, PARAM_BUILDING_SECTOR)
    if normalize(nested_value) == target_sector:
        summary["verified_host_propagation"] += 1
        if host_changed:
            summary["updated"]                  += 1
            summary["updated_via_host_fallback"] += 1
        else:
            summary["unchanged"] += 1
        return

    summary["skipped_read_only"]                    += 1
    summary["skipped_host_propagation_failed"]      += 1
    summary["inspection_items"].append(
        _build_inspection_record(
            element,
            "Host BUILDING SECTOR did not propagate to nested outlet",
            probe_point=probe_point,
            reason=(
                "Resolved target sector: {0}. {1} Id {2} now reads '{3}', "
                "but nested outlet still reads '{4}'."
            ).format(
                target_sector,
                parent_source,
                host_key,
                get_param_string(parent, PARAM_BUILDING_SECTOR) or "<blank>",
                nested_value or "<blank>",
            ),
            matches=matches,
        )
    )


def _set_building_sectors_for_schedule(schedule_view):
    elements         = collect_schedule_elements(schedule_view, doc)
    scope_boxes      = _collect_zone_scope_boxes()
    host_assignments = {}

    summary = {
        "total":                          len(elements),
        "scope_boxes":                    len(scope_boxes),
        "updated":                        0,
        "updated_via_host_fallback":      0,
        "unchanged":                      0,
        "single_zone_matches":            0,
        "resolved_multi_zone_matches":    0,
        "verified_host_propagation":      0,
        "skipped_no_point":               0,
        "skipped_no_zone":                0,
        "skipped_missing_parameter":      0,
        "skipped_read_only":              0,
        "skipped_hostless_read_only":     0,
        "skipped_host_missing_parameter": 0,
        "skipped_host_read_only":         0,
        "skipped_host_conflict":          0,
        "skipped_host_propagation_failed": 0,
        "inspection_items":               [],
        "zone_names":                     ["{} ({})".format(b["sector"], b["name"]) for b in scope_boxes],
    }

    if not scope_boxes:
        return summary

    for element in elements:
        sector_param = element.LookupParameter(PARAM_BUILDING_SECTOR)
        existing     = get_param_string(element, PARAM_BUILDING_SECTOR)

        probe_point = get_probe_point(element)
        if not probe_point:
            summary["skipped_no_point"] += 1
            summary["inspection_items"].append(
                _build_inspection_record(
                    element,
                    "No readable element location",
                    reason="Could not derive a point from Location or BoundingBox.",
                )
            )
            continue

        selected_scope_box, matches = _choose_scope_box_for_point(probe_point, scope_boxes)
        if not selected_scope_box:
            summary["skipped_no_zone"] += 1
            summary["inspection_items"].append(
                _build_inspection_record(
                    element,
                    "Not inside any ZONE 5x scope box",
                    probe_point=probe_point,
                    reason="No matching scope box contains the outlet point.",
                )
            )
            continue

        target_sector = selected_scope_box["sector"]
        if len(matches) == 1:
            summary["single_zone_matches"]         += 1
        else:
            summary["resolved_multi_zone_matches"] += 1

        if not sector_param:
            summary["skipped_missing_parameter"] += 1
            summary["inspection_items"].append(
                _build_inspection_record(
                    element,
                    "Missing BUILDING SECTOR parameter",
                    probe_point=probe_point,
                    reason="Resolved target sector: {}".format(target_sector),
                    matches=matches,
                )
            )
            continue

        if normalize(existing) == target_sector:
            summary["unchanged"] += 1
            continue

        if sector_param.IsReadOnly:
            _handle_read_only_sector_parameter(
                element, sector_param, target_sector, probe_point, matches,
                summary, host_assignments,
            )
            continue

        if sector_param.Set(target_sector):
            summary["updated"] += 1

    return summary

# ╔╦╗╔═╗╦╔╗╔
# ║║║╠═╣║║║║
# ╩ ╩╩ ╩╩╝╚╝ MAIN 🎯
# ==================================================
if __name__ == '__main__':
    selected_schedule = pick_schedule(doc, uidoc, __title__)

    transaction = Transaction(doc, __title__)
    transaction.Start()

    try:
        result = _set_building_sectors_for_schedule(selected_schedule)
        transaction.Commit()
    except Exception as ex:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        logger.exception("Data Outlet Sectors failed: {}".format(ex))
        forms.alert("Failed to update BUILDING SECTOR values. See pyRevit output for details.", title=__title__)
        raise

    report_lines = [
        "Schedule: {}".format(selected_schedule.Name),
        "Elements in schedule: {}".format(result["total"]),
        "Detected ZONE scope boxes: {}".format(result["scope_boxes"]),
        "Updated BUILDING SECTOR: {}".format(result["updated"]),
        "Updated via host fallback: {}".format(result["updated_via_host_fallback"]),
        "Unchanged: {}".format(result["unchanged"]),
        "Single-zone matches: {}".format(result["single_zone_matches"]),
        "Resolved overlapping zones: {}".format(result["resolved_multi_zone_matches"]),
        "Verified nested host propagation: {}".format(result["verified_host_propagation"]),
        "Skipped (no readable point): {}".format(result["skipped_no_point"]),
        "Skipped (not in any zone): {}".format(result["skipped_no_zone"]),
        "Skipped (missing BUILDING SECTOR parameter): {}".format(result["skipped_missing_parameter"]),
        "Skipped (read-only BUILDING SECTOR): {}".format(result["skipped_read_only"]),
        "Skipped (read-only with no host): {}".format(result["skipped_hostless_read_only"]),
        "Skipped (host missing BUILDING SECTOR): {}".format(result["skipped_host_missing_parameter"]),
        "Skipped (host BUILDING SECTOR read-only): {}".format(result["skipped_host_read_only"]),
        "Skipped (conflicting host targets): {}".format(result["skipped_host_conflict"]),
        "Manual review (host write did not propagate): {}".format(result["skipped_host_propagation_failed"]),
    ]

    if result["zone_names"]:
        report_lines.append("Zone scope boxes used:")
        for zone_name in result["zone_names"]:
            report_lines.append("- {}".format(zone_name))

    report = "\n".join(report_lines)
    print(report)

    if result["inspection_items"]:
        print("\nOutlets requiring manual review:")
        for idx, item in enumerate(result["inspection_items"], 1):
            element_ref = output.linkify(item["element_id"])
            detail = (
                "{0}. {1} | Element: {2} | Category: {3} | Family: {4} | Type: {5} | "
                "Point: {6} | Matches: {7} | Reason: {8}"
            ).format(
                idx,
                item["issue"],
                element_ref,
                item["category"] or "-",
                item["family"] or "-",
                item["type"] or "-",
                item["probe_point"] or "<none>",
                ", ".join(item["matched_zones"]) if item["matched_zones"] else "-",
                item.get("reason") or "-",
            )
            print(detail)

    forms.alert(report, title=__title__)
    logger.success(':chequered_flag: Script is finished.')
