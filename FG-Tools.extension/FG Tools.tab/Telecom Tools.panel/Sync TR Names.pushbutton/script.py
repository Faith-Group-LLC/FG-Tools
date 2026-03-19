# -*- coding: utf-8 -*-
__title__ = "Sync TR Names"
__doc__ = """
Version = 3.0
Date = 19.03.2026
_____________________________________________________________________
Description:
Find and update outdated Telecom Room values in on-sheet
view titles and on-sheet drafting view names.

The source of truth is Area `Number` values from the workset:
Electronics-TELECOM LAWA SERVING ZONES
_____________________________________________________________________
Author: Hayden Fulghum
"""

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    StorageType,
    TextNote,
    Transaction,
    ViewDrafting,
    ViewSheet,
    Viewport,
)

import re
import os
import tempfile
from datetime import datetime
from pyrevit import forms, revit, script


doc = revit.doc
logger = script.get_logger()

WORKSET_NAME = "Electronics-TELECOM LAWA SERVING ZONES"
TARGET_PREFIX = "T5-"
EXCLUDED_TERMS = ("TWC", "TSA")


def matches_target_scope(text_value):
    if not text_value:
        return False
    return TARGET_PREFIX in text_value.upper()


def contains_excluded_terms(text_value):
    if not text_value:
        return False
    upper_value = text_value.upper()
    return any(term in upper_value for term in EXCLUDED_TERMS)


def build_target_search_text(*values):
    return " | ".join([value for value in values if value])


def should_exclude_target(target, exclude_special_cases):
    if not exclude_special_cases:
        return False
    return contains_excluded_terms(target.get("search_text", ""))


def filter_targets(targets, exclude_special_cases):
    return [target for target in targets if not should_exclude_target(target, exclude_special_cases)]


class CandidateItem(object):
    def __init__(self, token, count):
        self.Token = token
        self.Count = count
        self.DisplayText = "{0} ({1} matches)".format(token, count)


class MappingRow(object):
    def __init__(self, old_value, new_value, match_count):
        self.OldValue = old_value
        self.NewValue = new_value
        self.MatchCount = match_count


class MatchPreviewRow(object):
    def __init__(self, kind, context, current_value, updated_value, replacements):
        self.Kind = kind
        self.Context = context
        self.CurrentValue = current_value
        self.UpdatedValue = updated_value
        self.Replacements = replacements


class ContextMatchRow(object):
    def __init__(self, old_value, kind, context, current_value):
        self.OldValue = old_value
        self.Kind = kind
        self.Context = context
        self.CurrentValue = current_value


def get_area_number(area):
    number_param = area.LookupParameter("Number")
    if not number_param:
        return ""
    value = number_param.AsString()
    return value.strip() if value else ""


def get_element_workset_name(element):
    try:
        workset = doc.GetWorksetTable().GetWorkset(element.WorksetId)
        return workset.Name if workset else ""
    except Exception:
        return ""


def collect_valid_tr_numbers():
    values = set()
    areas = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Areas)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    for area in areas:
        if get_element_workset_name(area) != WORKSET_NAME:
            continue
        number_value = get_area_number(area)
        if number_value:
            values.add(number_value)

    return sorted(values)


def collect_sync_targets():
    targets = []

    viewports = FilteredElementCollector(doc).OfClass(Viewport).ToElements()
    for viewport in viewports:
        view = doc.GetElement(viewport.ViewId)
        sheet = doc.GetElement(viewport.SheetId)
        if not view or not sheet:
            continue
        if getattr(view, "IsTemplate", False):
            continue

        sheet_name_param = sheet.get_Parameter(BuiltInParameter.SHEET_NAME)
        sheet_name = ""
        if sheet_name_param and sheet_name_param.StorageType == StorageType.String:
            sheet_name = sheet_name_param.AsString() or ""

        view_name = view.Name or ""

        if isinstance(view, ViewDrafting):
            drafting_name = view_name
            if matches_target_scope(drafting_name):
                targets.append(
                    {
                        "kind": "Drafting View Name",
                        "element": view,
                        "value": drafting_name,
                        "context": "Sheet {0}".format(sheet.SheetNumber),
                        "search_text": build_target_search_text(drafting_name, view_name, sheet_name),
                    }
                )

        title_param = view.get_Parameter(BuiltInParameter.VIEW_DESCRIPTION)
        if not title_param or title_param.StorageType != StorageType.String:
            continue

        title_value = title_param.AsString() or ""
        if not matches_target_scope(title_value):
            continue

        targets.append(
            {
                "kind": "View Title on Sheet",
                "element": view,
                "value": title_value,
                "context": "Sheet {0}".format(sheet.SheetNumber),
                "search_text": build_target_search_text(title_value, view_name, sheet_name),
            }
        )

    # Collect sheet names
    seen_sheet_ids = set()
    sheets = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
    for sheet in sheets:
        if sheet.Id.IntegerValue in seen_sheet_ids:
            continue
        seen_sheet_ids.add(sheet.Id.IntegerValue)

        name_param = sheet.get_Parameter(BuiltInParameter.SHEET_NAME)
        if not name_param or name_param.StorageType != StorageType.String:
            continue

        sheet_name = name_param.AsString() or ""
        if not matches_target_scope(sheet_name):
            continue

        targets.append(
            {
                "kind": "Sheet Name",
                "element": sheet,
                "value": sheet_name,
                "context": "Sheet {0}".format(sheet.SheetNumber),
                "search_text": build_target_search_text(sheet_name),
            }
        )

    return targets


def collect_on_sheet_drafting_views():
    drafting_views_by_id = {}
    viewports = FilteredElementCollector(doc).OfClass(Viewport).ToElements()
    for viewport in viewports:
        view = doc.GetElement(viewport.ViewId)
        if not view:
            continue
        if getattr(view, "IsTemplate", False):
            continue
        if isinstance(view, ViewDrafting):
            drafting_views_by_id[view.Id.IntegerValue] = view

    return drafting_views_by_id.values()


def tokenize_text(text):
    if not text:
        return []
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9._/-]*", text)


def looks_like_telecom_token(token):
    if not token or len(token) < 2:
        return False
    has_digit = any(ch.isdigit() for ch in token)
    has_letter = any(ch.isalpha() for ch in token)
    has_separator = any(sep in token for sep in ["-", ".", "_", "/"])
    return has_digit and (has_letter or has_separator)


def collect_outdated_candidates(targets, valid_numbers):
    valid_set = set(valid_numbers)
    hit_count = {}

    for target in targets:
        value = target.get("value", "")
        for token in tokenize_text(value):
            if token in valid_set:
                continue
            if not looks_like_telecom_token(token):
                continue
            hit_count[token] = hit_count.get(token, 0) + 1

    candidates = [{"token": token, "count": count} for token, count in hit_count.items()]
    candidates.sort(key=lambda item: (-item["count"], item["token"]))
    return candidates


def build_mapping_pattern(mappings):
    old_values = [old_value for old_value, new_value in mappings.items() if old_value and new_value and old_value != new_value]
    if not old_values:
        return None

    escaped_values = [re.escape(value) for value in sorted(old_values, key=len, reverse=True)]
    pattern = r"(?<![A-Za-z0-9])({0})(?![A-Za-z0-9])".format("|".join(escaped_values))
    return re.compile(pattern)


def replace_mapped_values(text, mappings):
    if not text:
        return text, 0, []

    pattern = build_mapping_pattern(mappings)
    if not pattern:
        return text, 0, []

    replacements = []

    def replace_match(match):
        old_value = match.group(1)
        new_value = mappings.get(old_value, old_value)
        replacements.append((old_value, new_value))
        return new_value

    updated_text, replace_count = pattern.subn(replace_match, text)
    return updated_text, replace_count, replacements


def find_matches(targets, mappings):
    matches = []
    for target in targets:
        updated_value, replace_count, replacements = replace_mapped_values(target.get("value", ""), mappings)
        if replace_count > 0 and updated_value != target.get("value", ""):
            match = dict(target)
            match["updated_value"] = updated_value
            match["replace_count"] = replace_count
            match["replacements"] = replacements
            matches.append(match)
    return matches


def apply_updates(matches):
    updated_drafting_views = 0
    updated_view_titles = 0
    updated_sheet_names = 0
    failures = []
    adjustments = []
    processed_keys = set()

    drafting_views = FilteredElementCollector(doc).OfClass(ViewDrafting).ToElements()
    existing_drafting_names = set()
    for drafting_view in drafting_views:
        if getattr(drafting_view, "IsTemplate", False):
            continue
        if drafting_view.Name:
            existing_drafting_names.add(drafting_view.Name)

    def make_unique_drafting_name(base_name):
        if base_name not in existing_drafting_names:
            return base_name

        index = 2
        while True:
            candidate = "{0} ({1})".format(base_name, index)
            if candidate not in existing_drafting_names:
                return candidate
            index += 1

    tx = Transaction(doc, __title__)
    tx.Start()
    try:
        for match in matches:
            element = match.get("element")
            kind = match.get("kind", "")
            new_value = match.get("updated_value", "")
            if not element:
                continue

            key = "{0}:{1}".format(kind, element.Id.IntegerValue)
            if key in processed_keys:
                continue

            try:
                if kind == "Drafting View Name":
                    current_name = element.Name or ""
                    existing_drafting_names.discard(current_name)
                    unique_name = make_unique_drafting_name(new_value)
                    if unique_name != new_value:
                        adjustments.append(
                            "Drafting View Name (Id {0}): requested '{1}' but used '{2}' to keep names unique".format(
                                element.Id.IntegerValue,
                                new_value,
                                unique_name,
                            )
                        )
                    element.Name = unique_name
                    existing_drafting_names.add(unique_name)
                    updated_drafting_views += 1
                elif kind == "View Title on Sheet":
                    title_param = element.get_Parameter(BuiltInParameter.VIEW_DESCRIPTION)
                    if title_param and not title_param.IsReadOnly:
                        title_param.Set(new_value)
                        updated_view_titles += 1
                    else:
                        failures.append("Skipped read-only title on view Id {0}".format(element.Id.IntegerValue))
                        continue
                elif kind == "Sheet Name":
                    name_param = element.get_Parameter(BuiltInParameter.SHEET_NAME)
                    if name_param and not name_param.IsReadOnly:
                        name_param.Set(new_value)
                        updated_sheet_names += 1
                    else:
                        failures.append("Skipped read-only sheet name on ViewSheet Id {0}".format(element.Id.IntegerValue))
                        continue
                processed_keys.add(key)
            except Exception as ex:
                failures.append("{0} (Id {1}): {2}".format(kind, element.Id.IntegerValue, ex))
    finally:
        tx.Commit()

    return {
        "updated_drafting_views": updated_drafting_views,
        "updated_view_titles": updated_view_titles,
        "updated_sheet_names": updated_sheet_names,
        "failures": failures,
        "adjustments": adjustments,
    }


def apply_drafting_content_updates(mappings):
    updated_text_notes = 0
    updated_string_parameters = 0
    replacement_hits = 0
    failures = []

    drafting_views = collect_on_sheet_drafting_views()
    tx = Transaction(doc, "{0} - Drafting Content".format(__title__))
    tx.Start()
    try:
        for drafting_view in drafting_views:
            elements = FilteredElementCollector(doc, drafting_view.Id).WhereElementIsNotElementType().ToElements()

            for element in elements:
                try:
                    if isinstance(element, TextNote):
                        current_text = element.Text or ""
                        updated_text, replace_count, replacements = replace_mapped_values(current_text, mappings)
                        if replace_count > 0 and updated_text != current_text:
                            element.Text = updated_text
                            updated_text_notes += 1
                            replacement_hits += replace_count
                        continue

                    for parameter in element.Parameters:
                        if parameter.StorageType != StorageType.String:
                            continue
                        if parameter.IsReadOnly:
                            continue

                        current_value = parameter.AsString()
                        if not current_value:
                            continue

                        updated_value, replace_count, replacements = replace_mapped_values(current_value, mappings)
                        if replace_count > 0 and updated_value != current_value:
                            parameter.Set(updated_value)
                            updated_string_parameters += 1
                            replacement_hits += replace_count
                except Exception as ex:
                    failures.append(
                        "Drafting view {0} element Id {1}: {2}".format(
                            drafting_view.Id.IntegerValue,
                            element.Id.IntegerValue,
                            ex,
                        )
                    )
    finally:
        tx.Commit()

    return {
        "updated_text_notes": updated_text_notes,
        "updated_string_parameters": updated_string_parameters,
        "replacement_hits": replacement_hits,
        "failures": failures,
    }


def export_mappings_report(results):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    candidate_dirs = [
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "Documents"),
        os.path.expanduser("~"),
        tempfile.gettempdir(),
    ]

    report_dir = None
    for candidate_dir in candidate_dirs:
        try:
            if not os.path.exists(candidate_dir):
                continue
            if not os.path.isdir(candidate_dir):
                continue
            test_path = os.path.join(candidate_dir, "_tr_report_write_test.tmp")
            with open(test_path, "w") as test_file:
                test_file.write("ok")
            os.remove(test_path)
            report_dir = candidate_dir
            break
        except Exception:
            continue

    if not report_dir:
        report_dir = tempfile.gettempdir()

    if not os.path.exists(report_dir):
        os.makedirs(report_dir)

    report_path = os.path.join(report_dir, "TR_Name_Mappings_Report_{0}.txt".format(timestamp))

    mappings = results.get("mappings", {})
    lines = []
    lines.append("Old vs. New TR Names Report")
    lines.append("Generated: {0}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    lines.append("")
    lines.append("Mappings")
    lines.append("-" * 80)

    if mappings:
        for old_value in sorted(mappings.keys()):
            lines.append("- {0} -> {1}".format(old_value, mappings[old_value]))
    else:
        lines.append("- No mappings were applied.")

    lines.append("")
    lines.append("Primary Updates")
    lines.append("-" * 80)
    lines.append("- Updated drafting view names: {0}".format(results.get("updated_drafting_views", 0)))
    lines.append("- Updated view titles on sheet: {0}".format(results.get("updated_view_titles", 0)))
    lines.append("- Updated sheet names: {0}".format(results.get("updated_sheet_names", 0)))

    primary_failures = results.get("failures", [])
    lines.append("- Primary failures/skipped: {0}".format(len(primary_failures)))
    for failure in primary_failures:
        lines.append("  - {0}".format(failure))

    adjustments = results.get("adjustments", [])
    lines.append("- Auto-adjustments for uniqueness: {0}".format(len(adjustments)))
    for adjustment in adjustments:
        lines.append("  - {0}".format(adjustment))

    content_sync = results.get("content_sync")
    if content_sync:
        lines.append("")
        lines.append("Optional Drafting Content Updates")
        lines.append("-" * 80)
        lines.append("- Updated text notes: {0}".format(content_sync.get("updated_text_notes", 0)))
        lines.append("- Updated string parameters: {0}".format(content_sync.get("updated_string_parameters", 0)))
        lines.append("- Total replacement hits: {0}".format(content_sync.get("replacement_hits", 0)))
        content_failures = content_sync.get("failures", [])
        lines.append("- Drafting content failures/skipped: {0}".format(len(content_failures)))
        for failure in content_failures:
            lines.append("  - {0}".format(failure))

    with open(report_path, "w") as report_file:
        report_file.write("\n".join(lines))

    return report_path


def summarize_matches(matches):
    lines = []
    max_lines = 25
    for idx, match in enumerate(matches):
        if idx >= max_lines:
            break

        replacement_summary = ", ".join(
            ["{0}->{1}".format(old_value, new_value) for old_value, new_value in match.get("replacements", [])]
        )
        lines.append(
            "- {0} | {1} | '{2}' -> '{3}' | {4}".format(
                match.get("kind", ""),
                match.get("context", ""),
                match.get("value", ""),
                match.get("updated_value", ""),
                replacement_summary,
            )
        )

    if len(matches) > max_lines:
        lines.append("- ... and {0} more".format(len(matches) - max_lines))

    return "\n".join(lines)


def build_preview_rows(matches):
    rows = []
    for match in matches:
        replacements = ", ".join(
            ["{0}->{1}".format(old_value, new_value) for old_value, new_value in match.get("replacements", [])]
        )
        rows.append(
            MatchPreviewRow(
                match.get("kind", ""),
                match.get("context", ""),
                match.get("value", ""),
                match.get("updated_value", ""),
                replacements,
            )
        )
    return rows


def find_value_context_matches(targets, selected_old_values):
    selected_values = [value for value in selected_old_values if value]
    if not selected_values:
        return []

    selected_set = set(selected_values)
    rows = []

    for target in targets:
        current_value = target.get("value", "")
        tokens = set(tokenize_text(current_value))
        matched_values = sorted(tokens.intersection(selected_set))
        for matched_value in matched_values:
            rows.append(
                ContextMatchRow(
                    matched_value,
                    target.get("kind", ""),
                    target.get("context", ""),
                    current_value,
                )
            )

    return rows


class MappingWindow(forms.WPFWindow):
    def __init__(self, candidates, valid_numbers, targets):
        forms.WPFWindow.__init__(self, "ui.xaml")

        self.all_targets = targets
        self.targets = []
        self.valid_numbers = valid_numbers
        self.all_candidates = candidates
        self.candidate_counts = {}
        self.candidate_items = []
        self.mapping_lookup = {}
        self.results = None

        self.oldValuesList.SelectionChanged += self.old_values_selection_changed
        self.newValueCombo.ItemsSource = valid_numbers
        self.contextSummaryText.Text = "Select one or more outdated values to preview full current names/titles."
        self.contextMatchList.ItemsSource = []
        self.previewSummaryText.Text = "Select one or more outdated values, choose a replacement, then click Add / Update Mapping."
        self.matchPreviewList.ItemsSource = []
        self.refresh_targets_and_candidates()

    def exclude_special_cases_enabled(self):
        return bool(self.excludeTwcTsaCheckBox.IsChecked)

    def refresh_targets_and_candidates(self):
        self.targets = filter_targets(self.all_targets, self.exclude_special_cases_enabled())
        candidates = collect_outdated_candidates(self.targets, self.valid_numbers)
        self.candidate_counts = {candidate["token"]: candidate["count"] for candidate in candidates}
        self.candidate_items = [CandidateItem(candidate["token"], candidate["count"]) for candidate in candidates]

        invalid_keys = [old_value for old_value in self.mapping_lookup.keys() if old_value not in self.candidate_counts]
        for old_value in invalid_keys:
            del self.mapping_lookup[old_value]

        self.oldValuesList.ItemsSource = self.candidate_items
        self.refresh_mapping_list()
        self.update_preview()
        self.update_context_preview()

    def get_selected_old_items(self):
        return [item for item in self.oldValuesList.SelectedItems]

    def get_selected_mapping_rows(self):
        return [item for item in self.mappingList.SelectedItems]

    def get_selected_old_values(self):
        return [item.Token for item in self.get_selected_old_items()]

    def get_clean_mappings(self):
        clean_mappings = {}
        for old_value, new_value in self.mapping_lookup.items():
            if not old_value or not new_value:
                continue
            if old_value == new_value:
                continue
            clean_mappings[old_value] = new_value
        return clean_mappings

    def refresh_mapping_list(self):
        self.mappingList.Items.Clear()
        for old_value in sorted(self.mapping_lookup.keys()):
            row = MappingRow(
                old_value,
                self.mapping_lookup[old_value],
                self.candidate_counts.get(old_value, 0),
            )
            self.mappingList.Items.Add(row)

    def update_preview(self):
        mappings = self.get_clean_mappings()
        if not mappings:
            self.statusText.Text = "{0} outdated values found | 0 active mappings".format(len(self.candidate_items))
            self.previewSummaryText.Text = "No mappings selected."
            self.matchPreviewList.ItemsSource = []
            return

        matches = find_matches(self.targets, mappings)
        self.statusText.Text = "{0} outdated values found | {1} active mappings | {2} affected items".format(
            len(self.candidate_items),
            len(mappings),
            len(matches),
        )
        if matches:
            self.previewSummaryText.Text = "Previewing full current and updated values for all matches."
            self.matchPreviewList.ItemsSource = build_preview_rows(matches)
        else:
            self.previewSummaryText.Text = "Current mappings do not affect any eligible on-sheet view titles, drafting view names, or sheet names."
            self.matchPreviewList.ItemsSource = []

    def update_context_preview(self):
        selected_old_values = self.get_selected_old_values()
        if not selected_old_values:
            self.contextSummaryText.Text = "Select one or more outdated values to preview full current names/titles."
            self.contextMatchList.ItemsSource = []
            return

        context_rows = find_value_context_matches(self.targets, selected_old_values)
        self.contextSummaryText.Text = "{0} selected value(s) | {1} context match(es)".format(
            len(selected_old_values),
            len(context_rows),
        )
        self.contextMatchList.ItemsSource = context_rows

    def add_mapping_click(self, sender, args):
        selected_old_items = self.get_selected_old_items()
        new_value = self.newValueCombo.SelectedItem

        if not selected_old_items:
            forms.alert("Select at least one outdated value.", title=__title__, warn_icon=True)
            return
        if not new_value:
            forms.alert("Select a replacement Area Number.", title=__title__, warn_icon=True)
            return

        for item in selected_old_items:
            self.mapping_lookup[item.Token] = "{0}".format(new_value)

        self.refresh_mapping_list()
        self.update_preview()
        self.update_context_preview()

    def remove_mapping_click(self, sender, args):
        selected_rows = self.get_selected_mapping_rows()
        if not selected_rows:
            forms.alert("Select one or more mappings to remove.", title=__title__, warn_icon=True)
            return

        for row in selected_rows:
            if row.OldValue in self.mapping_lookup:
                del self.mapping_lookup[row.OldValue]

        self.refresh_mapping_list()
        self.update_preview()
        self.update_context_preview()

    def clear_mappings_click(self, sender, args):
        self.mapping_lookup = {}
        self.refresh_mapping_list()
        self.update_preview()
        self.update_context_preview()

    def old_values_selection_changed(self, sender, args):
        self.update_context_preview()

    def exclude_twc_tsa_click(self, sender, args):
        self.refresh_targets_and_candidates()

    def apply_click(self, sender, args):
        mappings = self.get_clean_mappings()
        if not mappings:
            forms.alert("Create at least one valid mapping before applying.", title=__title__, warn_icon=True)
            return

        matches = find_matches(self.targets, mappings)
        if not matches:
            forms.alert(
                "Current mappings do not affect any eligible on-sheet view titles, drafting view names, or sheet names.",
                title=__title__,
                warn_icon=True,
            )
            return

        self.results = apply_updates(matches)
        self.results["mappings"] = dict(mappings)

        run_content_sync = bool(self.applyDraftingContentSyncCheckBox.IsChecked)
        if run_content_sync:
            self.results["content_sync"] = apply_drafting_content_updates(mappings)

        export_report = bool(self.exportReportCheckBox.IsChecked)
        if export_report:
            try:
                self.results["report_path"] = export_mappings_report(self.results)
            except Exception as ex:
                self.results["report_error"] = "Failed to export report: {0}".format(ex)

        self.DialogResult = True
        self.Close()

    def cancel_click(self, sender, args):
        self.DialogResult = False
        self.Close()


if __name__ == "__main__":
    valid_numbers = collect_valid_tr_numbers()
    if not valid_numbers:
        forms.alert(
            "No Area Number values were found in workset '{0}'.".format(WORKSET_NAME),
            title=__title__,
            warn_icon=True,
        )
        script.exit()

    targets = collect_sync_targets()
    if not targets:
        forms.alert("No candidate text targets were found in this model.", title=__title__, warn_icon=True)
        script.exit()

    candidates = collect_outdated_candidates(targets, valid_numbers)
    if not candidates:
        forms.alert(
            "No outdated telecom room values were found in on-sheet view titles, drafting view names, or sheet names.",
            title=__title__,
            warn_icon=True,
        )
        script.exit()

    window = MappingWindow(candidates, valid_numbers, targets)
    dialog_result = window.ShowDialog()
    if not dialog_result or not window.results:
        script.exit()

    logger.success("Sync complete.")
    print("Updated drafting view names: {0}".format(window.results["updated_drafting_views"]))
    print("Updated view titles on sheet: {0}".format(window.results["updated_view_titles"]))
    print("Updated sheet names: {0}".format(window.results.get("updated_sheet_names", 0)))

    if "content_sync" in window.results:
        content_sync = window.results["content_sync"]
        print("Drafting content updates (optional step):")
        print("- Updated text notes: {0}".format(content_sync["updated_text_notes"]))
        print("- Updated string parameters: {0}".format(content_sync["updated_string_parameters"]))
        print("- Total replacement hits: {0}".format(content_sync["replacement_hits"]))

        if content_sync["failures"]:
            print("- Drafting content failures/skipped:")
            for failure in content_sync["failures"]:
                print("  - {0}".format(failure))

    if "report_path" in window.results:
        print("Mapping report exported: {0}".format(window.results["report_path"]))
    elif "report_error" in window.results:
        print(window.results["report_error"])

    if window.results["failures"]:
        print("Failures/Skipped:")
        for failure in window.results["failures"]:
            print("- {0}".format(failure))