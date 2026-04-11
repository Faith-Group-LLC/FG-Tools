# -*- coding: utf-8 -*-
"""
Shared schedule utility functions for FG-Tools scripts.

Provides schedule filtering, category inspection, a reusable list-item wrapper,
and a schedule picker that pre-selects any eligible schedule already selected
in the Revit UI.
"""

from Autodesk.Revit.DB import Category, ElementId, FilteredElementCollector, ViewSchedule
from pyrevit import forms, revit
from fg_constants import DATA_OUTLET_CATEGORIES


# ── Category helpers ─────────────────────────────────────────────────────────

def get_schedule_category_id_int(schedule_view):
    """Return the integer category ID of a schedule, or None on error."""
    try:
        return schedule_view.Definition.CategoryId.IntegerValue
    except Exception:
        return None


def get_schedule_category_name(schedule_view, doc):
    """Return the human-readable category name of a schedule, or '' on error."""
    try:
        cat_id = schedule_view.Definition.CategoryId
        if cat_id and cat_id != ElementId.InvalidElementId:
            category = Category.GetCategory(doc, cat_id)
            if category and category.Name:
                return category.Name
    except Exception:
        pass
    return ""


# ── Schedule classification ──────────────────────────────────────────────────

def is_multi_category_schedule(schedule_view):
    """Return True if the schedule covers multiple categories."""
    cat_int = get_schedule_category_id_int(schedule_view)
    if cat_int is None:
        return False
    return cat_int == ElementId.InvalidElementId.IntegerValue


def is_data_outlet_schedule(schedule_view, doc):
    """Return True if the schedule is a data outlet schedule by name or category."""
    name_text = (schedule_view.Name or "").strip().lower()
    cat_name = (get_schedule_category_name(schedule_view, doc) or "").strip().lower()

    if "data outlet" in name_text:
        return True
    if "data" in name_text and "outlet" in name_text:
        return True
    if "data" in cat_name and "device" in cat_name:
        return True

    cat_int = get_schedule_category_id_int(schedule_view)
    if cat_int is None:
        return False

    allowed_cat_ids = set(int(bic) for bic in DATA_OUTLET_CATEGORIES)
    return cat_int in allowed_cat_ids


def is_allowed_schedule(schedule_view, doc):
    """Return True if the schedule is eligible for data outlet processing."""
    if not schedule_view or schedule_view.IsTemplate:
        return False
    return is_multi_category_schedule(schedule_view) or is_data_outlet_schedule(schedule_view, doc)


def get_allowed_schedules(doc):
    """Return all eligible data outlet / multi-category schedules, sorted by name."""
    schedules = FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements()
    allowed = [s for s in schedules if is_allowed_schedule(s, doc)]
    return sorted(allowed, key=lambda s: (s.Name or "").lower())


# ── Element collection ───────────────────────────────────────────────────────

def collect_schedule_elements(schedule_view, doc):
    """Return all non-type elements visible in the given schedule view."""
    return list(
        FilteredElementCollector(doc, schedule_view.Id)
        .WhereElementIsNotElementType()
        .ToElements()
    )


# ── Schedule picker UI ───────────────────────────────────────────────────────

class ScheduleOption(forms.TemplateListItem):
    """List-item wrapper for schedule pickers, displaying 'Name | Category'."""

    @property
    def name(self):
        cat_name = get_schedule_category_name(self.item, revit.doc) or "Multi-Category"
        return "{} | {}".format(self.item.Name, cat_name)


def pick_schedule(doc, uidoc, title):
    """
    Prompt the user to select a data outlet schedule.

    If the active Revit selection already contains an eligible schedule it is
    returned immediately without showing the dialog. Calls exitscript if no
    eligible schedules exist or the user cancels.
    """
    selected_ids = list(uidoc.Selection.GetElementIds())
    if selected_ids:
        first = doc.GetElement(selected_ids[0])
        if isinstance(first, ViewSchedule) and is_allowed_schedule(first, doc):
            return first

    allowed_schedules = get_allowed_schedules(doc)
    if not allowed_schedules:
        forms.alert(
            "No eligible schedules found. "
            "Create or select a Data Outlet or Multi-Category schedule.",
            title=title,
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
        forms.alert("No schedule selected.", title=title, exitscript=True)

    return selected
