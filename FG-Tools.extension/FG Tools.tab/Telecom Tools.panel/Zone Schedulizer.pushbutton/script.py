# -*- coding: utf-8 -*-
__title__ = "Zone Schedulizer"
__doc__ = """
Version = 1.0
Date = 03.04.2026
_____________________________________________________________________
Description:
Create telecom data outlet schedules by TR/LEVEL ID/BUILDING SECTOR.

- Skips creation where a managed schedule already exists.
- Deletes managed schedules that are currently empty.
- Creates only schedules that contain at least one data outlet.
- Shows create/update/delete preview and asks for confirmation.
_____________________________________________________________________
Author: Hayden Fulghum
"""
__author__ = "Hayden Fulghum"
__min_revit_ver__ = 2025

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FamilyInstance,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    Phase,
    PhaseFilter,
    ScheduleFieldType,
    ScheduleFilter,
    ScheduleFilterType,
    ScheduleSortGroupField,
    Transaction,
    ViewSchedule,
)

import re
from pyrevit import forms, revit, script


doc = revit.doc
logger = script.get_logger()


DATA_OUTLET_CATEGORY = BuiltInCategory.OST_DataDevices
DATA_OUTLET_CATEGORIES = [
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
]
SCHEDULE_NAME_PATTERN = re.compile(r"^TELECOM\s*-\s*(.+?)\s*-\s*(L\d+)\s*/\s*(5[A-G])$", re.IGNORECASE)
VALID_SECTORS = set(["5A", "5B", "5C", "5D", "5E", "5F", "5G"])

PARAM_SPACE_NUMBER = ["Space Number", "SPACE NUMBER", "Space: Number", "SPACE: NUMBER"]
PARAM_LEVEL_ID = ["LEVEL ID", "Level ID", "LEVEL_ID"]
PARAM_BUILDING_SECTOR = ["BUILDING SECTOR", "Building Sector"]
PARAM_OUTLET_TYPE = ["Outlet Type", "OUTLET TYPE", "Type"]
PARAM_SYSTEM = ["FG User Field 1", "System", "SYSTEM"]
PARAM_DATA_PORTS = ["Data Ports", "DATA PORTS", "Data Port", "DATA PORT"]
PARAM_SYSTEM_ID = ["SYSTEM ID", "System ID"]
PARAM_FAMILY_AND_TYPE = ["Family and Type", "FAMILY AND TYPE"]
PARAM_MARK = ["Mark", "MARK"]
PARAM_ACTIVE_DATA_PORTS = ["ACTIVE DATA PORTS", "Active Data Ports"]
PARAM_COMMENT = ["Comment", "COMMENT"]
PARAM_LEVEL = ["Level", "LEVEL"]
SPACE_NUMBER_BUILTIN_CANDIDATES = [
    "SPACE_ASSOC_ROOM_NUMBER",
    "RBS_SPACE_NUMBER_PARAM",
    "ROOM_NUMBER",
]

SCHEDULE_SUB_DISCIPLINE_VALUE = "T_TELECOM - PACKAGE 3"
SCHEDULE_SUB_DISCIPLINE_PIA_VALUE = "SYSTEM DIAGRAM"
SCHEDULE_BIM_VARIABLE_VALUE = "02_DOCUMENTATION"
SCHEDULE_PHASE_NAME = "T5 Reno - Package 3"
SCHEDULE_PHASE_FILTER_NAME = "Show New"


def _get_revit_year():
    try:
        return int(doc.Application.VersionNumber)
    except Exception:
        return 0


def _text(value):
    if value is None:
        return ""
    return "{0}".format(value).strip()


def _normalize(value):
    return _text(value).upper()


def _parse_level_sort_key(level_text):
    match = re.match(r"^L(\d+)$", _normalize(level_text))
    if not match:
        return (9999, _normalize(level_text))
    return (int(match.group(1)), _normalize(level_text))


def _get_param_text(element, param_name_candidates):
    # Read instance first, then fallback to type parameters if needed.
    for name in param_name_candidates:
        try:
            param = element.LookupParameter(name)
            if not param:
                continue
            value = param.AsString() or param.AsValueString()
            value = _text(value)
            if value:
                return value
        except Exception:
            continue

    type_element = None
    try:
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            type_element = doc.GetElement(type_id)
    except Exception:
        type_element = None

    if type_element:
        for name in param_name_candidates:
            try:
                param = type_element.LookupParameter(name)
                if not param:
                    continue
                value = param.AsString() or param.AsValueString()
                value = _text(value)
                if value:
                    return value
            except Exception:
                continue

    return ""


def _get_built_in_param_text(element, builtin_param_names):
    for builtin_name in builtin_param_names:
        try:
            builtin_param = getattr(BuiltInParameter, builtin_name, None)
            if builtin_param is None:
                continue

            param = element.get_Parameter(builtin_param)
            if not param:
                continue

            value = param.AsString() or param.AsValueString()
            value = _text(value)
            if value:
                return value
        except Exception:
            continue

    return ""


def _get_phase_candidates():
    phases = []
    try:
        phases = [phase for phase in doc.Phases]
    except Exception:
        phases = []

    # Query newer phases first; outlets are typically associated to current-phase spaces.
    return list(reversed(phases))


def _get_space_number_from_space(space):
    if not space:
        return ""
    return _text(getattr(space, "Number", ""))


def _get_space_number_from_family_instance(element):
    if not isinstance(element, FamilyInstance):
        return ""

    try:
        number_value = _get_space_number_from_space(element.Space)
        if number_value:
            return number_value
    except Exception:
        pass

    for phase in _get_phase_candidates():
        try:
            number_value = _get_space_number_from_space(element.get_Space(phase))
            if number_value:
                return number_value
        except Exception:
            continue

    return ""


def _get_element_probe_point(element):
    try:
        location = element.Location
        if isinstance(location, LocationPoint):
            return location.Point
        if isinstance(location, LocationCurve):
            curve = location.Curve
            if curve:
                return curve.Evaluate(0.5, True)
    except Exception:
        return None
    return None


def _get_space_number_from_doc_lookup(element):
    point = _get_element_probe_point(element)
    if not point:
        return ""

    for phase in _get_phase_candidates():
        try:
            space = doc.GetSpaceAtPoint(point, phase)
            number_value = _get_space_number_from_space(space)
            if number_value:
                return number_value
        except Exception:
            continue

    try:
        space = doc.GetSpaceAtPoint(point)
        number_value = _get_space_number_from_space(space)
        if number_value:
            return number_value
    except Exception:
        pass

    return ""


def _get_space_number_text(element):
    number_value = _get_space_number_from_family_instance(element)
    if number_value:
        return number_value

    number_value = _get_space_number_from_doc_lookup(element)
    if number_value:
        return number_value

    value = _get_built_in_param_text(element, SPACE_NUMBER_BUILTIN_CANDIDATES)
    if value:
        return value

    return _get_param_text(element, PARAM_SPACE_NUMBER)


def _collect_data_outlets():
    outlet_by_id = {}

    for category in DATA_OUTLET_CATEGORIES:
        try:
            elements = (
                FilteredElementCollector(doc)
                .OfCategory(category)
                .WhereElementIsNotElementType()
                .ToElements()
            )
        except Exception:
            elements = []

        for element in elements:
            outlet_by_id[element.Id.IntegerValue] = element

    return list(outlet_by_id.values())


def _collect_combo_counts(elements):
    combo_counts = {}
    level_ids = set()
    stats = {
        "total": 0,
        "missing_tr": 0,
        "missing_level": 0,
        "missing_sector": 0,
        "invalid_level": 0,
        "invalid_sector": 0,
        "valid": 0,
    }

    for element in elements:
        stats["total"] += 1
        tr_value = _get_space_number_text(element)
        level_id = _normalize(_get_param_text(element, PARAM_LEVEL_ID))
        building_sector = _normalize(_get_param_text(element, PARAM_BUILDING_SECTOR))

        if not tr_value:
            stats["missing_tr"] += 1
            continue

        if not level_id:
            stats["missing_level"] += 1
            continue

        if not building_sector:
            stats["missing_sector"] += 1
            continue

        if not re.match(r"^L\d+$", level_id):
            stats["invalid_level"] += 1
            continue

        if building_sector not in VALID_SECTORS:
            stats["invalid_sector"] += 1
            continue

        level_ids.add(level_id)
        combo_key = (tr_value, level_id, building_sector)
        combo_counts[combo_key] = combo_counts.get(combo_key, 0) + 1
        stats["valid"] += 1

    return combo_counts, sorted(list(level_ids), key=_parse_level_sort_key), stats


def _build_schedule_name(tr_value, level_id, building_sector):
    return "TELECOM - {0} - {1} / {2}".format(_text(tr_value), _normalize(level_id), _normalize(building_sector))


def _collect_existing_managed_schedules():
    existing = {}
    schedules = (
        FilteredElementCollector(doc)
        .OfClass(ViewSchedule)
        .ToElements()
    )

    for schedule in schedules:
        try:
            if schedule.IsTemplate:
                continue
        except Exception:
            continue

        name = _text(schedule.Name)
        if SCHEDULE_NAME_PATTERN.match(name):
            existing[name] = schedule

    return existing


def _find_named_element(element_class, name_text):
    target = _normalize(name_text)
    if not target:
        return None

    try:
        elements = FilteredElementCollector(doc).OfClass(element_class).ToElements()
    except Exception:
        return None

    for element in elements:
        if _normalize(getattr(element, "Name", "")) == target:
            return element

    return None


def _set_text_parameter(element, param_name, param_value):
    try:
        parameter = element.LookupParameter(param_name)
        if not parameter or parameter.IsReadOnly:
            return False
        return parameter.Set(_text(param_value))
    except Exception:
        return False


def _set_elementid_parameter(element, builtin_param, target_element):
    if not target_element:
        return False

    try:
        parameter = element.get_Parameter(builtin_param)
        if not parameter or parameter.IsReadOnly:
            return False
        return parameter.Set(target_element.Id)
    except Exception:
        return False


def _apply_schedule_sorting_parameters(schedule_view):
    _set_text_parameter(schedule_view, "SUB-DISCIPLINE", SCHEDULE_SUB_DISCIPLINE_VALUE)
    _set_text_parameter(schedule_view, "SUB-DISCIPLINE PIA", SCHEDULE_SUB_DISCIPLINE_PIA_VALUE)
    _set_text_parameter(schedule_view, "BIM Variable", SCHEDULE_BIM_VARIABLE_VALUE)

    target_phase = _find_named_element(Phase, SCHEDULE_PHASE_NAME)
    target_phase_filter = _find_named_element(PhaseFilter, SCHEDULE_PHASE_FILTER_NAME)

    phase_set = _set_elementid_parameter(schedule_view, BuiltInParameter.VIEW_PHASE, target_phase)
    phase_filter_set = _set_elementid_parameter(schedule_view, BuiltInParameter.VIEW_PHASE_FILTER, target_phase_filter)

    if not phase_set:
        logger.warning("Could not set schedule phase for: {0}".format(schedule_view.Name))
    if not phase_filter_set:
        logger.warning("Could not set schedule phase filter for: {0}".format(schedule_view.Name))


def _get_schedule_outlet_count(schedule_view):
    try:
        return (
            FilteredElementCollector(doc, schedule_view.Id)
            .WhereElementIsNotElementType()
            .GetElementCount()
        )
    except Exception:
        return 0


def _find_schedulable_field(definition, target_names):
    desired = set([_normalize(x) for x in target_names])
    for schedulable in definition.GetSchedulableFields():
        try:
            field_name = _normalize(schedulable.GetName(doc))
            if field_name in desired:
                return schedulable
        except Exception:
            continue
    return None


def _add_visible_field(definition, target_names):
    desired = set([_normalize(x) for x in target_names])

    try:
        for field_id in definition.GetFieldOrder():
            existing_field = definition.GetField(field_id)
            if not existing_field:
                continue
            if _normalize(existing_field.GetName()) in desired:
                return existing_field
    except Exception:
        pass

    schedulable = _find_schedulable_field(definition, target_names)
    if not schedulable:
        return None
    try:
        return definition.AddField(schedulable)
    except Exception:
        return None


def _add_filter_field(definition, target_names):
    field = _add_visible_field(definition, target_names)
    if not field:
        return None
    try:
        field.IsHidden = True
    except Exception:
        pass
    return field


def _try_add_filter(definition, schedule_field, filter_type, filter_value=None):
    if not schedule_field:
        return False

    try:
        if filter_value is None:
            definition.AddFilter(ScheduleFilter(schedule_field.FieldId, filter_type))
        else:
            definition.AddFilter(ScheduleFilter(schedule_field.FieldId, filter_type, filter_value))
        return True
    except Exception:
        return False


def _try_add_sort_by_field(definition, schedule_field):
    if not schedule_field:
        return False


def _try_add_data_ports_exists_filter(definition, schedule_field):
    if not schedule_field:
        return False

    if _try_add_filter(definition, schedule_field, ScheduleFilterType.HasParameter):
        return True

    # Some API versions expose this condition as HasValue instead.
    try:
        return _try_add_filter(definition, schedule_field, ScheduleFilterType.HasValue)
    except Exception:
        return False

    try:
        definition.AddSortGroupField(ScheduleSortGroupField(schedule_field.FieldId))
        return True
    except Exception:
        return False


def _configure_schedule(schedule_view, tr_value, level_id, building_sector):
    definition = schedule_view.Definition

    # Build a concise grouped summary by outlet type and system.
    definition.IsItemized = False

    # Match the existing schedule setup order as closely as possible.
    _add_visible_field(definition, PARAM_SYSTEM_ID)
    _add_visible_field(definition, PARAM_FAMILY_AND_TYPE)
    _add_visible_field(definition, PARAM_MARK)
    outlet_type_field = _add_visible_field(definition, PARAM_OUTLET_TYPE)
    count_field = definition.AddField(ScheduleFieldType.Count)
    data_ports_field = _add_visible_field(definition, PARAM_DATA_PORTS)
    _add_visible_field(definition, PARAM_ACTIVE_DATA_PORTS)
    system_field = _add_visible_field(definition, PARAM_SYSTEM)
    _add_visible_field(definition, PARAM_COMMENT)
    _add_visible_field(definition, PARAM_LEVEL)
    _add_visible_field(definition, PARAM_BUILDING_SECTOR)
    _add_visible_field(definition, PARAM_SPACE_NUMBER)

    if system_field:
        try:
            system_field.ColumnHeading = "System"
        except Exception:
            pass

    if data_ports_field:
        try:
            data_ports_field.ColumnHeading = "Data Ports"
        except Exception:
            pass

    if count_field:
        try:
            count_field.ColumnHeading = "Total Devices"
        except Exception:
            pass

    filter_space_field = _add_visible_field(definition, PARAM_SPACE_NUMBER)
    filter_level_field = _add_visible_field(definition, PARAM_LEVEL_ID)
    filter_sector_field = _add_visible_field(definition, PARAM_BUILDING_SECTOR)

    filter_data_ports_field = _add_visible_field(definition, PARAM_DATA_PORTS)
    filter_outlet_type_field = _add_visible_field(definition, PARAM_OUTLET_TYPE)

    _try_add_data_ports_exists_filter(definition, filter_data_ports_field)
    _try_add_filter(definition, filter_space_field, ScheduleFilterType.Equal, _text(tr_value))
    _try_add_filter(definition, filter_outlet_type_field, ScheduleFilterType.NotContains, "TSA")
    _try_add_filter(definition, filter_sector_field, ScheduleFilterType.Equal, _normalize(building_sector))
    _try_add_filter(definition, filter_level_field, ScheduleFilterType.Equal, _normalize(level_id))

    _try_add_sort_by_field(definition, outlet_type_field)

    if not outlet_type_field:
        logger.warning("Schedule missing Outlet Type field: {0}".format(schedule_view.Name))
    if not system_field:
        logger.warning("Schedule missing System field (FG User Field 1): {0}".format(schedule_view.Name))
    if not data_ports_field:
        logger.warning("Schedule missing Data Ports field: {0}".format(schedule_view.Name))


def _create_outlet_schedule():
    # Prefer Multi-Category schedules to include all supported outlet categories.
    try:
        return ViewSchedule.CreateSchedule(doc, ElementId.InvalidElementId)
    except Exception:
        return ViewSchedule.CreateSchedule(doc, ElementId(DATA_OUTLET_CATEGORY))


def _build_preview_lines(title, rows):
    lines = [title]
    if not rows:
        lines.append("- None")
        return lines

    for row in rows:
        lines.append("- {0} (Data Outlets: {1})".format(row["name"], row["count"]))
    return lines


def _build_confirmation_message(to_create, to_update, to_delete, available_level_ids, stats):
    lines = [
        "This operation will synchronize telecom schedules using TR / LEVEL ID / BUILDING SECTOR.",
        "Select Yes to Proceed (apply create/update/delete actions), or No to Abort.",
        "",
        "Proceeding will:",
        "- Create missing schedules with data outlets: {0}".format(len(to_create)),
        "- Keep existing schedules already matching a valid combo: {0}".format(len(to_update)),
        "- Delete existing managed schedules that are currently empty: {0}".format(len(to_delete)),
        "",
        "Outlet scan summary:",
        "- Total scanned: {0}".format(stats.get("total", 0)),
        "- Valid for schedule generation: {0}".format(stats.get("valid", 0)),
        "- Missing Space Number: {0}".format(stats.get("missing_tr", 0)),
        "- Missing LEVEL ID: {0}".format(stats.get("missing_level", 0)),
        "- Missing BUILDING SECTOR: {0}".format(stats.get("missing_sector", 0)),
        "- Invalid LEVEL ID format (expected L#): {0}".format(stats.get("invalid_level", 0)),
        "- Invalid BUILDING SECTOR (expected 5A-5G): {0}".format(stats.get("invalid_sector", 0)),
        "",
        "Detected LEVEL ID values: {0}".format(", ".join(available_level_ids) if available_level_ids else "None"),
        "",
        "Detailed schedule list:",
    ]

    lines.extend(_build_preview_lines("Create", to_create))
    lines.append("")
    lines.extend(_build_preview_lines("Update (already exists)", to_update))
    lines.append("")
    lines.extend(_build_preview_lines("Delete (empty)", to_delete))
    return "\n".join(lines)


if __name__ == '__main__':
    if _get_revit_year() < __min_revit_ver__:
        forms.alert(
            "This tool supports Revit {0}+ only.".format(__min_revit_ver__),
            title=__title__,
            exitscript=True,
        )

    all_outlets = _collect_data_outlets()
    combo_counts, available_level_ids, outlet_stats = _collect_combo_counts(all_outlets)
    existing_schedules = _collect_existing_managed_schedules()

    to_delete = []
    for schedule_name, schedule in existing_schedules.items():
        schedule_count = _get_schedule_outlet_count(schedule)
        if schedule_count <= 0:
            to_delete.append(
                {
                    "name": schedule_name,
                    "count": 0,
                    "schedule": schedule,
                }
            )

    for row in to_delete:
        existing_schedules.pop(row["name"], None)

    to_create = []
    to_update = []

    sorted_combos = sorted(
        combo_counts.items(),
        key=lambda kv: (_normalize(kv[0][0]), _parse_level_sort_key(kv[0][1]), _normalize(kv[0][2])),
    )

    for combo_key, outlet_count in sorted_combos:
        tr_value, level_id, building_sector = combo_key
        schedule_name = _build_schedule_name(tr_value, level_id, building_sector)

        existing_schedule = existing_schedules.get(schedule_name)
        if existing_schedule:
            to_update.append(
                {
                    "name": schedule_name,
                    "count": _get_schedule_outlet_count(existing_schedule),
                    "schedule": existing_schedule,
                }
            )
            continue

        to_create.append(
            {
                "name": schedule_name,
                "count": outlet_count,
                "tr": tr_value,
                "level": level_id,
                "sector": building_sector,
            }
        )

    confirmation_message = _build_confirmation_message(
        to_create,
        to_update,
        to_delete,
        available_level_ids,
        outlet_stats,
    )

    proceed = forms.alert(
        confirmation_message,
        title=__title__,
        yes=True,
        no=True,
        ok=False,
    )

    if not proceed:
        logger.warning("Zone Schedulizer cancelled by user.")
        script.exit()

    if not to_create and not to_delete and not to_update:
        forms.alert("No schedule creation, update, or deletion required.", title=__title__)
        logger.success("Zone Schedulizer complete. Nothing changed.")
        script.exit()

    transaction = Transaction(doc, __title__)
    transaction.Start()
    try:
        for row in to_delete:
            doc.Delete(row["schedule"].Id)

        for row in to_update:
            _apply_schedule_sorting_parameters(row["schedule"])

        for row in to_create:
            schedule = _create_outlet_schedule()
            schedule.Name = row["name"]
            _configure_schedule(schedule, row["tr"], row["level"], row["sector"])
            _apply_schedule_sorting_parameters(schedule)

        transaction.Commit()
    except Exception as ex:
        transaction.RollBack()
        logger.exception("Zone Schedulizer failed: {0}".format(ex))
        forms.alert("Zone Schedulizer failed. See pyRevit output for details.", title=__title__)
        script.exit()

    summary_lines = [
        "Created schedules: {0}".format(len(to_create)),
        "Existing schedules (updated list): {0}".format(len(to_update)),
        "Deleted empty schedules: {0}".format(len(to_delete)),
    ]
    forms.alert("\n".join(summary_lines), title=__title__)
    logger.success("Zone Schedulizer completed successfully.")