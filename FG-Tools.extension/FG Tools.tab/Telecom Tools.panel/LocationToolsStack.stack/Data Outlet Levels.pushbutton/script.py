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

# EXTRA: You can remove them.
__author__ = "Hayden Fulghum" # Script's Author
__helpurl__ = "https://github.com/baptistelechat/pyrevit-with-vscode" # Link that can be opened with F1 when hovered over the tool in Revit UI.
__min_revit_ver__ = 2025 # Limit your Scripts to certain Revit versions if it's not compatible due to RevitAPI Changes.
# __highlight__ = "new" # Button will have an orange dot + Description in Revit UI ("new" | "updated"
# __context__ = [ "selection", "active-section-view"] # Make it available only if Active view is Section and something is Selected
# __context__     = ["Walls", "Floors", "Roofs"] # Make your button available only when certain categories are selected. Or Revit/View Types.

# 🔗 For extra bundle metadata: https://pyrevitlabs.notion.site/Bundle-Metadata-9fa4911c14fa49c48e715421400f1427
# 🔗 For extra bundle context: https://pyrevitlabs.notion.site/Bundle-Context-630fa1f3611f4ee0aa15d290275e7ef3

# ╦╔╦╗╔═╗╔═╗╦═╗╔╦╗╔═╗
# ║║║║╠═╝║ ║╠╦╝ ║ ╚═╗
# ╩╩ ╩╩  ╚═╝╩╚═ ╩ ╚═╝ IMPORTS 📚
# ==================================================
# Regular + Autodesk
import os, sys, math, datetime, time, re # Regular Imports
from Autodesk.Revit.DB import * # Import everything from DB or Import only classes that are used. (from Autodesk.Revit.DB import Transaction, FilteredElementCollector)

# pyRevit
from pyrevit import revit, forms, script # import pyRevit modules.

# Custom Imports
# from Snippets._selection import get_selected_elements # lib import
# from Snippets._convert import convert_internal_to_m # lib import

# .NET Imports
import clr # Common Language Runtime. Makes .NET libraries accessible
clr.AddReference("System") # Reference System.dll for import.
from System.Collections.Generic import List # List<ElementType>() <- it's special type of list from .NET framework that RevitAPI requires

# ╦  ╦╔═╗╦═╗╦╔═╗╔╗ ╦  ╔═╗╔═╗
# ╚╗╔╝╠═╣╠╦╝║╠═╣╠╩╗║  ║╣ ╚═╗
#  ╚╝ ╩ ╩╩╚═╩╩ ╩╚═╝╩═╝╚═╝╚═╝ VARIABLES 📄
# ==================================================
doc = revit.doc # Document class from RevitAPI that represents project. Used to Create, Delete, Modify and Query elements from the project.
uidoc = revit.uidoc # UIDocument class from RevitAPI that represents Revit project opened in the Revit UI.
app = revit.HOST_APP # Represents the Autodesk Revit Application, providing access to documents, options and other application wide data and settings.
rvt_year = int(doc.Application.VersionNumber) # Get current Revit version in a pyRevit-safe way.
PATH_SCRIPT = os.path.dirname(__file__) # Absolute path to the folder where script is placed.

# GLOBAL VARIABLES

# - Place global variables here.
logger = script.get_logger()
output = script.get_output()

LEVEL_ID_PARAMETER_NAME = "LEVEL ID"
SCHEDULE_LEVEL_PARAMETER_CANDIDATES = [
    "Schedule Level",
    "SCHEDULE LEVEL",
    "Level",
    "LEVEL",
    "Reference Level",
]

LEVEL_PREFIX_PATTERN = re.compile(r"^LEVEL\s*0?(\d+)\s*-\s*", re.IGNORECASE)
WCS_CIVIL_LEVEL_KEY = "WCS CIVIL 0.0"

ALLOWED_DATA_OUTLET_BUILTIN_CATEGORIES = [
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
]

# ╔═╗╦ ╦╔╗╔╔═╗╔╦╗╦╔═╗╔╗╔╔═╗
# ╠╣ ║ ║║║║║   ║ ║║ ║║║║╚═╗
# ╚  ╚═╝╝╚╝╚═╝ ╩ ╩╚═╝╝╚╝╚═╝ FUNCTIONS 🛠️
# ==================================================

# - Place local functions here. If you might use any functions in other scripts, consider placing it in the lib folder.
def _get_selected_schedule():
    selected_ids = list(uidoc.Selection.GetElementIds())
    if not selected_ids:
        return None

    first_selected = doc.GetElement(selected_ids[0])
    if isinstance(first_selected, ViewSchedule):
        return first_selected

    return None


def _get_schedule_category_id_int(schedule_view):
    try:
        return schedule_view.Definition.CategoryId.IntegerValue
    except Exception:
        return None


def _try_get_schedule_category_name(schedule_view):
    try:
        cat_id = schedule_view.Definition.CategoryId
        if cat_id and cat_id != ElementId.InvalidElementId:
            category = Category.GetCategory(doc, cat_id)
            if category and category.Name:
                return category.Name
    except Exception:
        pass

    return ""


def _is_multi_category_schedule(schedule_view):
    cat_int = _get_schedule_category_id_int(schedule_view)
    if cat_int is None:
        return False
    return cat_int == ElementId.InvalidElementId.IntegerValue


def _is_data_outlet_schedule(schedule_view):
    name_text = (schedule_view.Name or "").strip().lower()
    cat_name = (_try_get_schedule_category_name(schedule_view) or "").strip().lower()

    # Keep schedule picker focused on data outlet intent by name and known categories.
    if "data outlet" in name_text:
        return True
    if "data" in name_text and "outlet" in name_text:
        return True
    if "data" in cat_name and "device" in cat_name:
        return True

    cat_int = _get_schedule_category_id_int(schedule_view)
    if cat_int is None:
        return False

    allowed_cat_ids = set(int(bic) for bic in ALLOWED_DATA_OUTLET_BUILTIN_CATEGORIES)
    return cat_int in allowed_cat_ids


def _is_allowed_schedule(schedule_view):
    if not schedule_view or schedule_view.IsTemplate:
        return False
    return _is_multi_category_schedule(schedule_view) or _is_data_outlet_schedule(schedule_view)


def _get_allowed_schedules():
    schedules = (
        FilteredElementCollector(doc)
        .OfClass(ViewSchedule)
        .ToElements()
    )

    allowed = []
    for sched in schedules:
        if _is_allowed_schedule(sched):
            allowed.append(sched)

    return sorted(allowed, key=lambda s: (s.Name or "").lower())


class ScheduleOption(forms.TemplateListItem):
    @property
    def name(self):
        schedule = self.item
        cat_name = _try_get_schedule_category_name(schedule) or "Multi-Category"
        return "{} | {}".format(schedule.Name, cat_name)


def _pick_schedule():
    allowed_schedules = _get_allowed_schedules()
    if not allowed_schedules:
        forms.alert(
            "No eligible schedules found. Create/select a Data Outlet or Multi-Category schedule.",
            title=__title__,
            exitscript=True,
        )

    options = [ScheduleOption(s) for s in allowed_schedules]
    selected = forms.SelectFromList.show(
        options,
        title="Select Data Outlet Schedule",
        button_name="Use Schedule",
        multiselect=False,
    )

    if not selected:
        forms.alert("No schedule selected.", title=__title__, exitscript=True)

    return selected


def _get_parameter_string_value(element, param_names):
    for param_name in param_names:
        param = element.LookupParameter(param_name)
        if not param:
            continue

        value = param.AsString() or param.AsValueString()
        if value and value.strip():
            return value.strip()

    return ""


def _try_get_parent_or_host_element(element):
    # Shared nested family instances often expose SuperComponent; if not, try Host.
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


def _try_get_level_text_from_level_id(element):
    try:
        level_id = element.LevelId
        if level_id and level_id != ElementId.InvalidElementId:
            level = doc.GetElement(level_id)
            if level and getattr(level, "Name", None):
                return _safe_string(level.Name)
    except Exception:
        pass

    return ""


def _get_effective_schedule_level_text(element):
    # 1) Try direct schedule-level style parameters on the element itself.
    level_text = _get_parameter_string_value(element, SCHEDULE_LEVEL_PARAMETER_CANDIDATES)
    if level_text:
        return level_text, False, "Direct element schedule level parameter"

    # 2) Fall back to the element's own LevelId name.
    level_text = _try_get_level_text_from_level_id(element)
    if level_text:
        return level_text, False, "Direct element LevelId"

    # 3) For nested/shared outlets, use parent host family level.
    parent, parent_source = _try_get_parent_or_host_element(element)
    if parent:
        level_text = _get_parameter_string_value(parent, SCHEDULE_LEVEL_PARAMETER_CANDIDATES)
        if not level_text:
            level_text = _try_get_level_text_from_level_id(parent)
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
    level_text = _get_parameter_string_value(element, SCHEDULE_LEVEL_PARAMETER_CANDIDATES)
    if level_text:
        return level_text

    return _try_get_level_text_from_level_id(element)


def _normalize_level_key(level_text):
    cleaned = re.sub(r"\s+", " ", level_text or "").strip().upper()
    return cleaned


def _collect_available_schedule_levels(elements):
    available_levels = set()
    for element in elements:
        level_text = _get_parameter_string_value(element, SCHEDULE_LEVEL_PARAMETER_CANDIDATES)
        normalized = _normalize_level_key(level_text)
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


def _collect_schedule_elements(schedule_view):
    return list(
        FilteredElementCollector(doc, schedule_view.Id)
        .WhereElementIsNotElementType()
        .ToElements()
    )


def _safe_string(value):
    try:
        text = "{}".format(value or "")
    except Exception:
        text = ""
    return text.strip()


def _build_inspection_record(element, issue, level_text, reason=""):
    category_name = ""
    family_name = ""
    type_name = ""

    try:
        if element.Category:
            category_name = _safe_string(element.Category.Name)
    except Exception:
        pass

    try:
        if isinstance(element, FamilyInstance) and element.Symbol:
            family_name = _safe_string(element.Symbol.FamilyName)
            type_name = _safe_string(element.Symbol.Name)
    except Exception:
        pass

    if not family_name:
        family_name = _safe_string(getattr(element, "Name", ""))

    return {
        "id": element.Id.IntegerValue,
        "element_id": element.Id,
        "issue": issue,
        "reason": _safe_string(reason),
        "schedule_level": _safe_string(level_text),
        "category": category_name,
        "family": family_name,
        "type": type_name,
    }


def _set_level_ids_for_schedule(schedule_view):
    elements = _collect_schedule_elements(schedule_view)
    available_levels = _collect_available_schedule_levels(elements)
    level_id_lookup = _derive_level_id_lookup(available_levels)

    if not elements:
        return {
            "total": 0,
            "updated": 0,
            "skipped_no_level": 0,
            "skipped_unmapped_level": 0,
            "skipped_wcs_civil": 0,
            "used_host_level_fallback": 0,
            "skipped_missing_level_id": 0,
            "skipped_read_only": 0,
            "unchanged": 0,
            "unmapped_examples": [],
            "inspection_items": [],
            "derived_level_rules": {},
        }

    summary = {
        "total": len(elements),
        "updated": 0,
        "skipped_no_level": 0,
        "skipped_unmapped_level": 0,
        "skipped_wcs_civil": 0,
        "used_host_level_fallback": 0,
        "skipped_missing_level_id": 0,
        "skipped_read_only": 0,
        "unchanged": 0,
        "unmapped_examples": [],
        "inspection_items": [],
        "derived_level_rules": level_id_lookup,
    }

    for element in elements:
        level_id_param = element.LookupParameter(LEVEL_ID_PARAMETER_NAME)
        existing = ""
        if level_id_param:
            existing = (level_id_param.AsString() or "").strip()

        direct_level_text = _try_get_direct_schedule_level_text(element)
        normalized_direct_level = _normalize_level_key(direct_level_text)
        resolved_direct_level_id = level_id_lookup.get(normalized_direct_level)

        # Fast path: if the element already has the correct LEVEL ID from its own level data,
        # skip host fallback and parameter write work entirely.
        if existing and resolved_direct_level_id and existing == resolved_direct_level_id:
            summary["unchanged"] += 1
            continue

        level_text = direct_level_text
        used_host_fallback = False
        level_diagnostic_reason = "Direct element schedule level/LevelId"
        if not level_text:
            level_text, used_host_fallback, level_diagnostic_reason = _get_effective_schedule_level_text(element)
            if used_host_fallback:
                summary["used_host_level_fallback"] += 1

        if not level_text:
            summary["skipped_no_level"] += 1
            summary["inspection_items"].append(
                _build_inspection_record(
                    element,
                    "Missing schedule level",
                    level_text,
                    reason=level_diagnostic_reason,
                )
            )
            continue

        normalized_level = _normalize_level_key(level_text)
        if normalized_level == WCS_CIVIL_LEVEL_KEY:
            summary["skipped_wcs_civil"] += 1
            summary["inspection_items"].append(
                _build_inspection_record(
                    element,
                    "Invalid host level (WCS Civil 0.0)",
                    level_text,
                    reason=level_diagnostic_reason,
                )
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

# ╔═╗╦  ╔═╗╔═╗╔═╗╔═╗╔═╗
# ║  ║  ╠═╣╚═╗╚═╗║╣ ╚═╗
# ╚═╝╩═╝╩ ╩╚═╝╚═╝╚═╝╚═╝ CLASSES 📦
# ==================================================

# - Place local classes here. If you might use any classes in other scripts, consider placing it in the lib folder.

# ╔╦╗╔═╗╦╔╗╔
# ║║║╠═╣║║║║
# ╩ ╩╩ ╩╩╝╚╝ MAIN 🎯
# ==================================================
# 📝 For input display: https://pyrevitlabs.notion.site/Effective-Input-ea95e95282a24ba9b154ef88f4f8d056
# 🎨 For output display: https://pyrevitlabs.notion.site/Effective-Output-43baf34d2ca247ada8e040bcb86613a2
# 📊 For data visualization: https://pyrevitlabs.notion.site/Visualizing-Data-fd778a0b67354ff581aa340619b87803

if __name__ == '__main__':
    selected_schedule = _pick_schedule()

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
print(':page_facing_up: Template has been developed by Baptiste LECHAT and inspired by Erik FRITS.')