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
    RevitLinkInstance,
    StorageType,
    TextNote,
    Transaction,
    ViewDrafting,
    ViewSheet,
    Viewport,
)

import re
import os
import json
import tempfile
import traceback
import clr
from datetime import datetime
from pyrevit import forms, revit, script


try:
    clr.AddReference("System.Data")
    System = __import__("System")
except Exception:
    System = None


doc = revit.doc
logger = script.get_logger()

WORKSET_NAME = "Electronics-TELECOM LAWA SERVING ZONES"
TARGET_PREFIX = "T5-"
EXCLUDED_TERMS = ("TWC", "TSA")
ARCH_ROOM_SCOPE_TERMS = ("LAWA IT", "MPOE", "CELLDAS", "TSA", "TWC", "LAWA RADIO")
IGNORE_NO_SPACE_TERMS = ("TWC", "CELLDAS")
SERVING_ZONE_PARAM = "LAWA SERVING ZONE"

DEFAULT_INTERNAL_OVERRIDES = {
    "T5-1-5B-ER040": "MPOE 1.1",
    "T5-1-5B-ER040.3": "CD 1.1",
    "T5-1-5B-ER040.1": "TWC 1.1",
    "T5-1-5B-TR050": "TSA 1.1",
    "T5-1-5D-TR020": "TSA 1.2",
    "T5-3-5A-TR100.2": "TR 3.1",
    "T5-3-5A-TR100.1": "TWC 3.1",
    "T5-3-5B-TR070.1": "TR 3.2",
    "T5-3-5B-TR070.2": "TWC 3.2",
    "T5-3-5B-TR210": "TR 3.3",
    "T5-3-5B-TR230": "TWC 3.3",
    "T5-3-5C-TR240.2": "TR 3.4",
    "T5-3-5C-TR240.1": "TWC 3.4",
    "T5-4-5B-TR090": "TSA 4.1",
    "T5-4-5B-TR160": "TSA 4.2",
    "South TE": "South TE",
    "T5-2-5D-TR070": "TR 2.1",
    "T5-2-5D-TR080": "TWC 2.1",
    "T5-3-5D-TR020": "TR 3.5",
    "T5-3-5D-TR030": "TWC 3.5",
    "T5-4-5E-TR030": "TR 4.1",
    "T5-4-5E-TR050": "TWC 4.1",
    "T5-4-5F-TR050": "TR 4.2",
    "T5-4-5F-TR060": "TWC 4.2",
    "T5-4-5F-TR010": "TR 4.3",
    "T5-4-5F-TR110": "TWC 4.3",
    "T5-4-5F-100": "RR 4.4",
    "T5-4-5G-TR030": "TR 4.5",
    "T5-4-5G-TR020": "TWC 4.5",
    "T5-2-5G-TR380": "MDF 2.2",
    "T5-2-5G-TR370.1": "CD 2.2",
    "T5-2-5G-TR370": "TWC 2.2",
}
PREFERRED_ARCH_LINK_NAMES = (
    "LAX-CLAX14166-T05-08-A_CC_IN.rvt",
    "CLAX14166-T05-08-A_CC_IN.rvt",
    "LAX-CLAX14166-T05-08-A_HH_IN.rvt",
    "CLAX14166-T05-08-A_HH_IN.rvt",
)


def normalize_key(value):
    if not value:
        return ""
    return " ".join(value.strip().upper().split())


def get_string_param_value(element, param_name):
    try:
        if not element:
            return ""
        parameter = element.LookupParameter(param_name)
        if not parameter:
            return ""
        value = parameter.AsString()
        return value.strip() if value else ""
    except Exception:
        return ""


def get_state_file_path():
    base_dir = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "FG-Tools")
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    return os.path.join(base_dir, "sync_tr_names_state.json")


def load_state_payload():
    state_path = get_state_file_path()
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, "r") as state_file:
            payload = json.load(state_file)
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return {}


def save_state_payload(payload):
    state_path = get_state_file_path()
    try:
        with open(state_path, "w") as state_file:
            json.dump(payload, state_file, indent=2)
    except Exception:
        logger.warning("Could not save Sync TR Names state file: {0}".format(state_path))


def load_previous_link_room_keys():
    payload = load_state_payload()

    room_keys = payload.get("last_link_room_keys", [])
    if not isinstance(room_keys, list):
        return set()
    return set(["{0}".format(item) for item in room_keys if item])


def save_current_link_room_keys(room_keys):
    payload = load_state_payload()
    payload["last_link_room_keys"] = sorted(list(room_keys))
    payload["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_state_payload(payload)


def load_saved_mapping_lookup():
    payload = load_state_payload()
    mappings = payload.get("saved_mapping_lookup", {})
    if not isinstance(mappings, dict):
        return {}

    clean_mappings = {}
    for old_value, new_value in mappings.items():
        old_text = "{0}".format(old_value).strip() if old_value else ""
        new_text = "{0}".format(new_value).strip() if new_value else ""
        if not old_text or not new_text or old_text == new_text:
            continue
        clean_mappings[old_text] = new_text
    return clean_mappings


def save_mapping_lookup(mappings):
    payload = load_state_payload()
    payload["saved_mapping_lookup"] = dict(mappings)
    payload["saved_mapping_saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_state_payload(payload)


def load_internal_override_lookup():
    payload = load_state_payload()
    mappings = payload.get("saved_internal_override_lookup", {})
    if not isinstance(mappings, dict):
        return {}

    clean_mappings = {}
    for arch_value, internal_value in mappings.items():
        arch_text = "{0}".format(arch_value).strip() if arch_value else ""
        internal_text = "{0}".format(internal_value).strip() if internal_value else ""
        if not arch_text or not internal_text:
            continue
        clean_mappings[arch_text] = internal_text
    return clean_mappings


def save_internal_override_lookup(mappings):
    payload = load_state_payload()
    payload["saved_internal_override_lookup"] = dict(mappings)
    payload["saved_internal_override_saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_state_payload(payload)


def build_effective_mappings(base_mappings, internal_override_lookup, use_internal_override):
    clean_base = {}
    for old_value, new_value in (base_mappings or {}).items():
        old_text = (old_value or "").strip()
        new_text = (new_value or "").strip()
        if not old_text or not new_text:
            continue
        clean_base[old_text] = new_text

    if not use_internal_override:
        return clean_base

    effective = {}
    for old_value, arch_room_number in clean_base.items():
        internal_room_number = (internal_override_lookup.get(arch_room_number, "") or "").strip()
        final_value = internal_room_number or arch_room_number
        if old_value == final_value:
            continue
        effective[old_value] = final_value

    for arch_room_number, internal_room_number in (internal_override_lookup or {}).items():
        arch_text = (arch_room_number or "").strip()
        internal_text = (internal_room_number or "").strip()
        if not arch_text or not internal_text or arch_text == internal_text:
            continue
        effective[arch_text] = internal_text

    return effective


def matches_target_scope(text_value):
    if not text_value:
        return False
    return TARGET_PREFIX in text_value.upper()


def contains_excluded_terms(text_value):
    if not text_value:
        return False
    upper_value = text_value.upper()
    return any(term in upper_value for term in EXCLUDED_TERMS)


def is_scoped_arch_room_name(room_name):
    if not room_name:
        return False
    upper_name = room_name.upper()
    return any(term in upper_name for term in ARCH_ROOM_SCOPE_TERMS)


def should_ignore_missing_space_room(room_name):
    if not room_name:
        return False
    upper_name = room_name.upper()
    return any(term in upper_name for term in IGNORE_NO_SPACE_TERMS)


def extract_review_host_tokens(review_text):
    if not review_text:
        return []

    tokens = []
    patterns = [
        r"Unmapped\s+host\s+space:\s*([^\s]+)",
        r"Unmapped\s+target\s+area:\s*([^\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, review_text)
        if not match:
            continue
        token = (match.group(1) or "").strip()
        if token:
            tokens.append(token)

    # Supports ambiguity lines like:
    # Room 'X' (Y) resolves to multiple Area Numbers: A, B.
    ambiguous_match = re.search(r"multiple\s+Area\s+Numbers:\s*(.+)\.$", review_text)
    if ambiguous_match:
        trailing = (ambiguous_match.group(1) or "").strip()
        if trailing:
            for raw_token in trailing.split(","):
                token = (raw_token or "").strip()
                if token:
                    tokens.append(token)

    unique_tokens = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        unique_tokens.append(token)
    return unique_tokens


def add_candidate_token(candidate_counts, token):
    clean_token = (token or "").strip()
    if not clean_token:
        return
    candidate_counts[clean_token] = candidate_counts.get(clean_token, 0) + 1


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


class InternalOverrideRow(object):
    def __init__(self, arch_room_number, internal_room_number):
        self.ArchRoomNumber = arch_room_number
        self.InternalRoomNumber = internal_room_number


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
    try:
        if not area:
            return ""
        number_param = area.LookupParameter("Number")
        if not number_param:
            return ""
        value = number_param.AsString()
        return value.strip() if value else ""
    except Exception:
        return ""


def get_element_workset_name(element):
    try:
        workset = doc.GetWorksetTable().GetWorkset(element.WorksetId)
        return workset.Name if workset else ""
    except Exception:
        return ""


def collect_target_areas():
    area_records = []
    areas = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Areas)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    for area in areas:
        try:
            if get_element_workset_name(area) != WORKSET_NAME:
                continue

            number_value = get_area_number(area)
            if not number_value:
                continue

            area_records.append(
                {
                    "element": area,
                    "id": area.Id.IntegerValue,
                    "number": number_value,
                    "name": get_string_param_value(area, "Name"),
                }
            )
        except Exception:
            continue

    return area_records


def collect_valid_tr_numbers():
    values = set()
    for area_record in collect_target_areas():
        values.add(area_record["number"])
    return sorted(values)


def collect_host_spaces():
    spaces = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_MEPSpaces)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    records = []
    for space in spaces:
        try:
            number_value = get_string_param_value(space, "Number")
            name_value = get_string_param_value(space, "Name")
            if not number_value and not name_value:
                continue
            records.append(
                {
                    "element": space,
                    "id": space.Id.IntegerValue,
                    "number": number_value,
                    "name": name_value,
                }
            )
        except Exception:
            continue

    return records


def build_value_index(records, field_name):
    index = {}
    for record in records:
        key = normalize_key(record.get(field_name, ""))
        if not key:
            continue
        if key not in index:
            index[key] = []
        index[key].append(record)
    return index


def pick_single_match(index, raw_value):
    key = normalize_key(raw_value)
    if not key:
        return None, "missing-key"
    matches = index.get(key, [])
    if len(matches) == 1:
        return matches[0], "exact"
    if len(matches) > 1:
        return None, "ambiguous"
    return None, "missing"


def get_index_matches(index, raw_value):
    key = normalize_key(raw_value)
    if not key:
        return []
    return list(index.get(key, []))


def dedupe_records(records):
    unique_records = []
    seen_ids = set()
    for record in records:
        try:
            record_id = record.get("id")
            if not record_id:
                element = record.get("element")
                record_id = element.Id.IntegerValue if element else None
            if not record_id or record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            unique_records.append(record)
        except Exception:
            continue
    return unique_records


def get_loaded_links():
    links = []
    instances = FilteredElementCollector(doc).OfClass(RevitLinkInstance).ToElements()
    for instance in instances:
        try:
            link_doc = instance.GetLinkDocument()
        except Exception:
            link_doc = None
        if not link_doc:
            continue
        link_title = "{0}".format(link_doc.Title or "")
        link_name = "{0}".format(getattr(instance, "Name", "") or "")
        links.append(
            {
                "instance": instance,
                "doc": link_doc,
                "title": link_title,
                "name": link_name,
            }
        )
    return links


def matches_preferred_link(link_record):
    title = (link_record.get("title", "") or "").lower()
    name = (link_record.get("name", "") or "").lower()
    for preferred_name in PREFERRED_ARCH_LINK_NAMES:
        preferred = preferred_name.lower()
        if preferred in title or preferred in name:
            return True
    return False


def select_architectural_links():
    loaded_links = get_loaded_links()
    if not loaded_links:
        return []

    preferred_links = [link for link in loaded_links if matches_preferred_link(link)]
    if preferred_links:
        return preferred_links

    if len(loaded_links) == 1:
        return [loaded_links[0]]

    choices = []
    lookup = {}
    for link in loaded_links:
        label = "{0} | {1}".format(link.get("title", ""), link.get("name", ""))
        choices.append(label)
        lookup[label] = link

    selected = forms.SelectFromList.show(
        choices,
        title="Select Architectural Link(s)",
        button_name="Use Selected Link(s)",
        multiselect=True,
    )
    if not selected:
        return []

    selected_links = []
    for item in selected:
        link = lookup.get(item)
        if link:
            selected_links.append(link)
    return selected_links


def collect_linked_rooms(link_record):
    if not link_record:
        return []

    link_doc = link_record.get("doc")
    if not link_doc:
        return []

    link_name = link_record.get("title", "") or link_record.get("name", "") or ""
    rooms = (
        FilteredElementCollector(link_doc)
        .OfCategory(BuiltInCategory.OST_Rooms)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    records = []
    for room in rooms:
        try:
            number_value = get_string_param_value(room, "Number")
            name_value = get_string_param_value(room, "Name")
            if not number_value and not name_value:
                continue
            if not is_scoped_arch_room_name(name_value):
                continue

            unique_suffix = ""
            try:
                unique_suffix = room.UniqueId or ""
            except Exception:
                unique_suffix = ""
            if not unique_suffix:
                try:
                    unique_suffix = "ID-{0}".format(room.Id.IntegerValue)
                except Exception:
                    unique_suffix = "UNRESOLVED"

            room_unique = "{0}:{1}".format(link_name, unique_suffix)
            records.append(
                {
                    "element": room,
                    "unique_key": room_unique,
                    "number": number_value,
                    "name": name_value,
                    "link_name": link_name,
                }
            )
        except Exception:
            continue

    return records


def build_auto_mappings(area_numbers):
    resolved_mappings = {}
    diagnostics = []
    auto_mapped_items = []
    needs_review_items = []
    broken_items = []
    candidate_counts = {}
    source_room_choices = []
    source_room_lookup = {}
    mapping_health = {
        "resolved": 0,
        "resolved_no_change": 0,
        "total_scoped_rooms": 0,
        "room_ignored_no_space": 0,
        "room_missing_space": 0,
        "room_ambiguous_space": 0,
        "space_missing_area": 0,
        "space_ambiguous_area": 0,
        "room_conflicting_area_numbers": 0,
        "deleted_linked_rooms": [],
        "link_name": "",
    }

    link_records = select_architectural_links()
    if not link_records:
        mapping_health["link_error"] = "No loaded architectural links were selected."
        broken_items.append("No loaded architectural links were selected.")
        return {
            "mappings": resolved_mappings,
            "diagnostics": diagnostics,
            "health": mapping_health,
            "auto_mapped_items": auto_mapped_items,
            "needs_review_items": needs_review_items,
            "broken_items": broken_items,
        }

    link_names = []
    linked_rooms = []
    seen_room_keys = set()
    for link_record in link_records:
        link_label = link_record.get("title", "") or link_record.get("name", "")
        if link_label:
            link_names.append(link_label)

        for room in collect_linked_rooms(link_record):
            room_key = room.get("unique_key", "")
            if room_key and room_key in seen_room_keys:
                continue
            if room_key:
                seen_room_keys.add(room_key)
            linked_rooms.append(room)

    mapping_health["link_name"] = ", ".join(sorted(link_names))
    mapping_health["total_scoped_rooms"] = len(linked_rooms)

    seen_source_rooms = set()
    for room in linked_rooms:
        room_number = (room.get("number", "") or "").strip()
        room_name = (room.get("name", "") or "").strip()
        if not room_number:
            continue
        display = "{0} | {1}".format(room_number, room_name or "[no name]")
        if display in seen_source_rooms:
            continue
        seen_source_rooms.add(display)
        source_room_choices.append(display)
        source_room_lookup[display] = room_number

    source_room_choices.sort()
    current_room_keys = set([room["unique_key"] for room in linked_rooms])
    previous_room_keys = load_previous_link_room_keys()
    deleted_room_keys = sorted(list(previous_room_keys.difference(current_room_keys)))
    mapping_health["deleted_linked_rooms"] = deleted_room_keys
    for deleted_key in deleted_room_keys:
        broken_items.append("Deleted linked room: {0}".format(deleted_key))
    save_current_link_room_keys(current_room_keys)

    spaces = collect_host_spaces()
    target_areas = collect_target_areas()

    spaces_by_number = build_value_index(spaces, "number")
    spaces_by_name = build_value_index(spaces, "name")
    areas_by_number = build_value_index(target_areas, "number")
    areas_by_name = build_value_index(target_areas, "name")
    valid_numbers = set(area_numbers)
    room_number_candidates = {}
    room_number_occurrences = {}
    matched_space_ids = set()
    matched_area_ids = set()

    for room in linked_rooms:
        try:
            room_number = room.get("number", "")
            if not room_number:
                continue

            room_number_occurrences[room_number] = room_number_occurrences.get(room_number, 0) + 1

            space_matches = get_index_matches(spaces_by_number, room.get("number", ""))
            space_match_strategy = "number"
            if not space_matches:
                space_matches = get_index_matches(spaces_by_name, room.get("name", ""))
                space_match_strategy = "name"

            space_matches = dedupe_records(space_matches)
            if not space_matches:
                room_name = room.get("name", "")
                if should_ignore_missing_space_room(room_name):
                    mapping_health["room_ignored_no_space"] += 1
                    diagnostics.append(
                        "Ignored room '{0}' ({1}) with no host space mapping due to ignore list.".format(
                            room.get("number", ""),
                            room_name,
                        )
                    )
                    continue

                mapping_health["room_missing_space"] += 1
                issue_text = "Room '{0}' ({1}) did not resolve to any host space using number/name mapping.".format(
                    room.get("number", ""),
                    room_name,
                )
                diagnostics.append(issue_text)
                needs_review_items.append(issue_text)
                continue

            if len(space_matches) > 1:
                mapping_health["room_ambiguous_space"] += 1

            for space_record in space_matches:
                if space_record.get("id"):
                    matched_space_ids.add(space_record.get("id"))

            area_matches = []
            for space_record in space_matches:
                from_number = get_index_matches(areas_by_number, space_record.get("number", ""))
                if from_number:
                    area_matches.extend(from_number)
                    continue
                from_name = get_index_matches(areas_by_name, space_record.get("name", ""))
                if from_name:
                    area_matches.extend(from_name)

            area_matches = dedupe_records(area_matches)
            if not area_matches:
                mapping_health["space_missing_area"] += 1
                issue_text = "Room '{0}' ({1}) matched {2} space(s) but none resolved to target areas.".format(
                    room.get("number", ""),
                    room.get("name", ""),
                    len(space_matches),
                )
                diagnostics.append(issue_text)
                needs_review_items.append(issue_text)
                continue

            for area_record in area_matches:
                if area_record.get("id"):
                    matched_area_ids.add(area_record.get("id"))

            candidate_numbers = sorted(
                list(
                    set(
                        [
                            area_record.get("number", "")
                            for area_record in area_matches
                            if area_record.get("number", "") in valid_numbers
                        ]
                    )
                )
            )

            if not candidate_numbers:
                mapping_health["space_missing_area"] += 1
                issue_text = "Room '{0}' ({1}) found area records, but no valid target Area Number candidates.".format(
                    room.get("number", ""),
                    room.get("name", ""),
                )
                diagnostics.append(issue_text)
                needs_review_items.append(issue_text)
                continue

            if len(candidate_numbers) > 1:
                mapping_health["space_ambiguous_area"] += 1
                # Surface ambiguity candidates in Host Mapping Tokens so users can
                # manually map the correct old token from Needs Review.
                ambiguous_host_tokens = set(candidate_numbers)
                for space_record in space_matches:
                    host_space_number = (space_record.get("number", "") or "").strip()
                    if host_space_number:
                        ambiguous_host_tokens.add(host_space_number)
                for area_record in area_matches:
                    host_area_number = (area_record.get("number", "") or "").strip()
                    if host_area_number:
                        ambiguous_host_tokens.add(host_area_number)
                for host_token in ambiguous_host_tokens:
                    add_candidate_token(candidate_counts, host_token)

                issue_text = "Room '{0}' ({1}) resolves to multiple Area Numbers: {2}.".format(
                    room.get("number", ""),
                    room.get("name", ""),
                    ", ".join(candidate_numbers),
                )
                diagnostics.append(issue_text)
                needs_review_items.append(issue_text)
                continue

            new_area_number = candidate_numbers[0]

            host_tokens = set()
            host_tokens.add(new_area_number)
            for space_record in space_matches:
                host_space_number = (space_record.get("number", "") or "").strip()
                if host_space_number:
                    host_tokens.add(host_space_number)
            for area_record in area_matches:
                host_area_number = (area_record.get("number", "") or "").strip()
                if host_area_number:
                    host_tokens.add(host_area_number)

            mapped_any_delta = False
            for host_token in sorted(host_tokens):
                add_candidate_token(candidate_counts, host_token)
                if host_token == room_number:
                    continue
                resolved_mappings[host_token] = room_number
                mapped_text = "Auto-mapped host token {0} -> room {1} ({2} space match(es), strategy: {3}).".format(
                    host_token,
                    room_number,
                    len(space_matches),
                    space_match_strategy,
                )
                diagnostics.append(mapped_text)
                auto_mapped_items.append(mapped_text)
                mapping_health["resolved"] += 1
                mapped_any_delta = True

            if not mapped_any_delta:
                no_change_text = "Resolved room {0} with host token(s) already current; no mapping change required.".format(
                    room_number
                )
                diagnostics.append(no_change_text)
                auto_mapped_items.append(no_change_text)
                mapping_health["resolved_no_change"] += 1
        except Exception as ex:
            issue_text = "Room mapping error for '{0}' ({1}): {2}".format(
                room.get("number", ""),
                room.get("name", ""),
                ex,
            )
            broken_items.append(issue_text)
            diagnostics.append(issue_text)
            continue

    for room_number in sorted(room_number_candidates.keys()):
        candidates = sorted(list(room_number_candidates[room_number]))
        mapping_health["room_conflicting_area_numbers"] += 1
        issue_text = "Room number '{0}' has conflicting Area Number candidates across matches: {1}.".format(
            room_number,
            ", ".join(candidates),
        )
        needs_review_items.append(issue_text)
        diagnostics.append(issue_text)

    scoped_spaces = [space for space in spaces if is_scoped_arch_room_name(space.get("name", ""))]
    for space in scoped_spaces:
        if space.get("id") in matched_space_ids:
            continue
        space_number = (space.get("number", "") or "").strip()
        add_candidate_token(candidate_counts, space_number)
        issue_text = "Unmapped host space: {0} ({1}) has no architectural room mapping.".format(
            space_number,
            space.get("name", ""),
        )
        needs_review_items.append(issue_text)
        diagnostics.append(issue_text)

    scoped_areas = [area for area in target_areas if is_scoped_arch_room_name(area.get("name", ""))]
    for area in scoped_areas:
        if area.get("id") in matched_area_ids:
            continue
        area_number = (area.get("number", "") or "").strip()
        add_candidate_token(candidate_counts, area_number)
        issue_text = "Unmapped target area: {0} ({1}) has no architectural room mapping.".format(
            area_number,
            area.get("name", ""),
        )
        needs_review_items.append(issue_text)
        diagnostics.append(issue_text)

    mapping_candidates = []
    for room_number in sorted(candidate_counts.keys()):
        mapping_candidates.append(
            {
                "token": room_number,
                "count": candidate_counts.get(room_number, 0),
            }
        )

    return {
        "mappings": resolved_mappings,
        "diagnostics": diagnostics,
        "health": mapping_health,
        "auto_mapped_items": auto_mapped_items,
        "needs_review_items": needs_review_items,
        "broken_items": broken_items,
        "mapping_candidates": mapping_candidates,
        "source_room_choices": source_room_choices,
        "source_room_lookup": source_room_lookup,
    }


def build_serving_zone_value(area_name, area_number, mpoe_counter):
    if not area_name or not area_number:
        return "", mpoe_counter

    normalized_name = area_name.strip()
    if normalized_name == "LAWA IT":
        return "{0} ROOM {1}".format(normalized_name, area_number), mpoe_counter
    if normalized_name == "MPOE":
        mpoe_counter += 1
        if mpoe_counter == 1:
            return "PRIMARY MPOE {0}".format(area_number), mpoe_counter
        return "SECONDARY MPOE {0}".format(area_number), mpoe_counter

    return "{0} {1}".format(normalized_name, area_number), mpoe_counter


def sync_area_serving_zone_values():
    area_records = collect_target_areas()
    if not area_records:
        return {
            "scanned": 0,
            "updated": 0,
            "changes": [],
            "failures": [],
        }

    # Sorting makes MPOE primary/secondary assignment deterministic.
    sorted_records = sorted(area_records, key=lambda item: item.get("number", ""))
    mpoe_counter = 0
    changes = []
    failures = []

    for area_record in sorted_records:
        area = area_record.get("element")
        area_name = area_record.get("name", "")
        area_number = area_record.get("number", "")
        target_param = area.LookupParameter(SERVING_ZONE_PARAM)

        if not target_param:
            failures.append("Area Id {0} missing parameter '{1}'.".format(area.Id.IntegerValue, SERVING_ZONE_PARAM))
            continue
        if target_param.IsReadOnly:
            failures.append("Area Id {0} has read-only parameter '{1}'.".format(area.Id.IntegerValue, SERVING_ZONE_PARAM))
            continue

        new_value, mpoe_counter = build_serving_zone_value(area_name, area_number, mpoe_counter)
        if not new_value:
            continue

        current_value = target_param.AsString() or ""
        if current_value.strip() == new_value.strip():
            continue

        changes.append(
            {
                "area": area,
                "old": current_value.strip() if current_value else "[empty]",
                "new": new_value,
                "param": target_param,
            }
        )

    if changes:
        tx = Transaction(doc, "{0} - {1}".format(__title__, SERVING_ZONE_PARAM))
        tx.Start()
        try:
            for change in changes:
                change["param"].Set(change["new"])
        finally:
            tx.Commit()

    return {
        "scanned": len(area_records),
        "updated": len(changes),
        "changes": changes,
        "failures": failures,
    }


def collect_sync_targets():
    targets = []

    viewports = FilteredElementCollector(doc).OfClass(Viewport).ToElements()
    for viewport in viewports:
        try:
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
        except Exception:
            continue

    # Collect sheet names
    seen_sheet_ids = set()
    sheets = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
    for sheet in sheets:
        try:
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
        except Exception:
            continue

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


def apply_space_area_updates(mappings):
    updated_space_numbers = 0
    updated_space_names = 0
    updated_area_numbers = 0
    updated_area_names = 0
    replacement_hits = 0
    failures = []

    if not mappings:
        return {
            "updated_space_numbers": 0,
            "updated_space_names": 0,
            "updated_area_numbers": 0,
            "updated_area_names": 0,
            "replacement_hits": 0,
            "failures": [],
        }

    tx = Transaction(doc, "{0} - Space/Area Names and Numbers".format(__title__))
    tx.Start()
    try:
        for space_record in collect_host_spaces():
            space = space_record.get("element")
            if not space:
                continue

            try:
                number_param = space.LookupParameter("Number")
                if number_param and not number_param.IsReadOnly and number_param.StorageType == StorageType.String:
                    current_number = number_param.AsString() or ""
                    updated_number, count, _ = replace_mapped_values(current_number, mappings)
                    if count > 0 and updated_number != current_number:
                        number_param.Set(updated_number)
                        updated_space_numbers += 1
                        replacement_hits += count

                name_param = space.LookupParameter("Name")
                if name_param and not name_param.IsReadOnly and name_param.StorageType == StorageType.String:
                    current_name = name_param.AsString() or ""
                    updated_name, count, _ = replace_mapped_values(current_name, mappings)
                    if count > 0 and updated_name != current_name:
                        name_param.Set(updated_name)
                        updated_space_names += 1
                        replacement_hits += count
            except Exception as ex:
                failures.append("Space Id {0}: {1}".format(space.Id.IntegerValue, ex))

        for area_record in collect_target_areas():
            area = area_record.get("element")
            if not area:
                continue

            try:
                number_param = area.LookupParameter("Number")
                if number_param and not number_param.IsReadOnly and number_param.StorageType == StorageType.String:
                    current_number = number_param.AsString() or ""
                    updated_number, count, _ = replace_mapped_values(current_number, mappings)
                    if count > 0 and updated_number != current_number:
                        number_param.Set(updated_number)
                        updated_area_numbers += 1
                        replacement_hits += count

                name_param = area.LookupParameter("Name")
                if name_param and not name_param.IsReadOnly and name_param.StorageType == StorageType.String:
                    current_name = name_param.AsString() or ""
                    updated_name, count, _ = replace_mapped_values(current_name, mappings)
                    if count > 0 and updated_name != current_name:
                        name_param.Set(updated_name)
                        updated_area_names += 1
                        replacement_hits += count
            except Exception as ex:
                failures.append("Area Id {0}: {1}".format(area.Id.IntegerValue, ex))
    finally:
        tx.Commit()

    return {
        "updated_space_numbers": updated_space_numbers,
        "updated_space_names": updated_space_names,
        "updated_area_numbers": updated_area_numbers,
        "updated_area_names": updated_area_names,
        "replacement_hits": replacement_hits,
        "failures": failures,
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

    base_mappings = results.get("mappings", {})
    effective_mappings = results.get("effective_mappings", base_mappings)
    internal_override_lookup = results.get("internal_override_lookup", {})
    internal_override_enabled = bool(results.get("internal_override_enabled", False))
    lines = []
    lines.append("Old vs. New TR Names Report")
    lines.append("Generated: {0}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    lines.append("")
    lines.append("Mappings")
    lines.append("-" * 80)

    lines.append("- Internal override enabled: {0}".format("Yes" if internal_override_enabled else "No"))
    lines.append("- Base host->architectural mappings: {0}".format(len(base_mappings)))
    lines.append("- Architectural->internal overrides: {0}".format(len(internal_override_lookup)))
    lines.append("- Effective mappings applied: {0}".format(len(effective_mappings)))

    lines.append("")
    lines.append("Base Mappings (Host -> Architectural)")
    lines.append("-" * 80)
    if base_mappings:
        for old_value in sorted(base_mappings.keys()):
            lines.append("- {0} -> {1}".format(old_value, base_mappings[old_value]))
    else:
        lines.append("- No base mappings were applied.")

    lines.append("")
    lines.append("Internal Overrides (Architectural -> Internal)")
    lines.append("-" * 80)
    if internal_override_lookup:
        for arch_value in sorted(internal_override_lookup.keys()):
            lines.append("- {0} -> {1}".format(arch_value, internal_override_lookup[arch_value]))
    else:
        lines.append("- No internal overrides were provided.")

    lines.append("")
    lines.append("Effective Mappings Used For Updates")
    lines.append("-" * 80)
    if effective_mappings:
        for old_value in sorted(effective_mappings.keys()):
            lines.append("- {0} -> {1}".format(old_value, effective_mappings[old_value]))
    else:
        lines.append("- No effective mappings were applied.")

    lines.append("")
    lines.append("Mapping Health")
    lines.append("-" * 80)
    mapping_health = results.get("mapping_health", {})
    if mapping_health:
        lines.append("- Link source: {0}".format(mapping_health.get("link_name", "[none]")))
        if mapping_health.get("link_error"):
            lines.append("- Link status: {0}".format(mapping_health.get("link_error")))
        lines.append("- Scoped architectural rooms: {0}".format(mapping_health.get("total_scoped_rooms", 0)))
        lines.append("- Auto-mapped rooms: {0}".format(mapping_health.get("resolved", 0)))
        lines.append("- Auto-resolved with no changes: {0}".format(mapping_health.get("resolved_no_change", 0)))
        lines.append("- Ignored no-space rooms (TWC/CELLDAS): {0}".format(mapping_health.get("room_ignored_no_space", 0)))
        lines.append("- Rooms missing host spaces: {0}".format(mapping_health.get("room_missing_space", 0)))
        lines.append("- Rooms with ambiguous host spaces: {0}".format(mapping_health.get("room_ambiguous_space", 0)))
        lines.append("- Spaces missing target areas: {0}".format(mapping_health.get("space_missing_area", 0)))
        lines.append("- Spaces with ambiguous target areas: {0}".format(mapping_health.get("space_ambiguous_area", 0)))
        lines.append("- Room numbers with conflicting area candidates: {0}".format(mapping_health.get("room_conflicting_area_numbers", 0)))

        deleted_rooms = mapping_health.get("deleted_linked_rooms", [])
        lines.append("- Deleted linked rooms since last run: {0}".format(len(deleted_rooms)))
        for deleted_room in deleted_rooms[:25]:
            lines.append("  - {0}".format(deleted_room))
        if len(deleted_rooms) > 25:
            lines.append("  - ... and {0} more".format(len(deleted_rooms) - 25))
    else:
        lines.append("- Mapping health diagnostics unavailable.")

    diagnostics = results.get("mapping_diagnostics", {})
    if diagnostics:
        auto_items = diagnostics.get("auto_mapped_items", [])
        needs_items = diagnostics.get("needs_review_items", [])
        broken_items = diagnostics.get("broken_items", [])

        lines.append("- Auto-mapped details shown: {0}".format(min(len(auto_items), 25)))
        for item in auto_items[:25]:
            lines.append("  - {0}".format(item))
        if len(auto_items) > 25:
            lines.append("  - ... and {0} more".format(len(auto_items) - 25))

        lines.append("- Needs review details shown: {0}".format(min(len(needs_items), 25)))
        for item in needs_items[:25]:
            lines.append("  - {0}".format(item))
        if len(needs_items) > 25:
            lines.append("  - ... and {0} more".format(len(needs_items) - 25))

        lines.append("- Broken details shown: {0}".format(min(len(broken_items), 25)))
        for item in broken_items[:25]:
            lines.append("  - {0}".format(item))
        if len(broken_items) > 25:
            lines.append("  - ... and {0} more".format(len(broken_items) - 25))

    lines.append("")
    lines.append("Area Sync")
    lines.append("-" * 80)
    area_sync = results.get("area_sync", {})
    if area_sync:
        lines.append("- Scanned target areas: {0}".format(area_sync.get("scanned", 0)))
        lines.append("- Updated '{0}': {1}".format(SERVING_ZONE_PARAM, area_sync.get("updated", 0)))
        area_failures = area_sync.get("failures", [])
        lines.append("- Area sync failures/skipped: {0}".format(len(area_failures)))
        for failure in area_failures:
            lines.append("  - {0}".format(failure))
    else:
        lines.append("- Area sync did not run.")

    lines.append("")
    lines.append("Primary Updates")
    lines.append("-" * 80)
    space_area_sync = results.get("space_area_sync", {})
    if space_area_sync:
        lines.append("- Updated space numbers: {0}".format(space_area_sync.get("updated_space_numbers", 0)))
        lines.append("- Updated space names: {0}".format(space_area_sync.get("updated_space_names", 0)))
        lines.append("- Updated area numbers: {0}".format(space_area_sync.get("updated_area_numbers", 0)))
        lines.append("- Updated area names: {0}".format(space_area_sync.get("updated_area_names", 0)))
        lines.append("- Space/area replacement hits: {0}".format(space_area_sync.get("replacement_hits", 0)))
        sa_failures = space_area_sync.get("failures", [])
        lines.append("- Space/area failures/skipped: {0}".format(len(sa_failures)))
        for failure in sa_failures:
            lines.append("  - {0}".format(failure))

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


def summarize_items(items, max_items=5):
    if not items:
        return ["- none"]
    lines = []
    for item in items[:max_items]:
        lines.append("- {0}".format(item))
    if len(items) > max_items:
        lines.append("- ... and {0} more".format(len(items) - max_items))
    return lines


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
    def __init__(
        self,
        candidates,
        valid_numbers,
        targets,
        replacement_choices,
        replacement_lookup,
        initial_mappings=None,
        mapping_health=None,
        auto_mapped_items=None,
        needs_review_items=None,
        broken_items=None,
        review_only_mode=False,
        review_only_reason="",
    ):
        forms.WPFWindow.__init__(self, "ui.xaml")

        self.all_targets = targets
        self.targets = []
        self.valid_numbers = valid_numbers
        self.replacement_choices = list(replacement_choices or [])
        self.replacement_lookup = dict(replacement_lookup or {})
        self.arch_room_numbers = sorted(list(set([value for value in self.replacement_lookup.values() if value])))
        self.all_candidates = candidates
        self.candidate_counts = {}
        self.candidate_items = []
        self.mapping_lookup = dict(initial_mappings or {})
        self.internal_override_lookup = load_internal_override_lookup()
        self.override_table = None
        self.mapping_health = mapping_health or {}
        self.auto_mapped_items = list(auto_mapped_items or [])
        self.needs_review_items = list(needs_review_items or [])
        self.broken_items = list(broken_items or [])
        self.review_only_mode = bool(review_only_mode)
        self.review_only_reason = review_only_reason or ""
        self.results = None

        self.oldValuesList.SelectionChanged += self.old_values_selection_changed
        self.newValueCombo.ItemsSource = self.replacement_choices
        self.contextSummaryText.Text = "Select one or more host tokens to prepare mapping."
        self.contextMatchList.ItemsSource = []
        self.previewSummaryText.Text = "Create and save mappings first. View/sheet scanning runs only when Apply is clicked."
        self.matchPreviewList.ItemsSource = []
        # Auto-check override when saved values or defaults are available
        has_saved_overrides = bool(self.internal_override_lookup)
        has_default_overrides = bool(DEFAULT_INTERNAL_OVERRIDES)
        self.enableInternalOverrideCheckBox.IsChecked = has_saved_overrides or has_default_overrides
        self.refresh_mapping_health_panel()
        self.refresh_targets_and_candidates()

    def refresh_mapping_health_panel(self):
        self.autoMappedList.ItemsSource = self.auto_mapped_items
        self.needsReviewList.ItemsSource = self.needs_review_items
        self.brokenList.ItemsSource = self.broken_items

        summary_text = "Auto: {0} | Needs Review: {1} | Broken: {2}".format(
            len(self.auto_mapped_items),
            len(self.needs_review_items),
            len(self.broken_items),
        )
        if self.review_only_mode:
            summary_text = "REVIEW-ONLY MODE | {0}".format(summary_text)
            if self.review_only_reason:
                summary_text = "{0} | Reason: {1}".format(summary_text, self.review_only_reason)
        self.mappingHealthSummaryText.Text = summary_text

    def exclude_special_cases_enabled(self):
        return bool(self.excludeTwcTsaCheckBox.IsChecked)

    def refresh_targets_and_candidates(self):
        self.targets = []
        candidates = list(self.all_candidates)
        self.candidate_counts = {candidate["token"]: candidate["count"] for candidate in candidates}
        self.candidate_items = [CandidateItem(candidate["token"], candidate["count"]) for candidate in candidates]

        self.oldValuesList.ItemsSource = self.candidate_items
        self.refresh_mapping_list()
        self.refresh_override_matrix()
        self.update_preview()
        self.update_context_preview()

    def refresh_override_matrix(self):
        # Defaults are only used as a first-time seed; once any overrides have been
        # saved to disk, the saved values are the sole source of truth.
        use_defaults = not bool(self.internal_override_lookup)

        room_numbers = set()
        clean_mappings = self.get_clean_mappings()
        for room_number in self.arch_room_numbers:
            if room_number:
                room_numbers.add(room_number)
        for room_number in clean_mappings.values():
            if room_number:
                room_numbers.add(room_number)
        for room_number in self.internal_override_lookup.keys():
            if room_number:
                room_numbers.add(room_number)
        if use_defaults:
            for room_number in DEFAULT_INTERNAL_OVERRIDES.keys():
                if room_number:
                    room_numbers.add(room_number)

        existing_lookup = {}
        try:
            self.overrideMatrixGrid.CommitEdit()
            self.overrideMatrixGrid.CommitEdit()
        except Exception:
            pass

        if self.override_table:
            for row in self.override_table.Rows:
                arch_room_number = ("{0}".format(row["ArchRoomNumber"]) if row["ArchRoomNumber"] is not None else "").strip()
                internal_room_number = ("{0}".format(row["InternalRoomNumber"]) if row["InternalRoomNumber"] is not None else "").strip()
                if not arch_room_number:
                    continue
                existing_lookup[arch_room_number] = internal_room_number

        if System is not None:
            new_table = System.Data.DataTable("OverrideMatrix")
            new_table.Columns.Add("ArchRoomNumber")
            new_table.Columns.Add("InternalRoomNumber")
            for room_number in sorted(room_numbers):
                internal_value = existing_lookup.get(room_number, "")
                if not internal_value:
                    internal_value = self.internal_override_lookup.get(room_number, "")
                if not internal_value and use_defaults:
                    internal_value = DEFAULT_INTERNAL_OVERRIDES.get(room_number, "")
                new_row = new_table.NewRow()
                new_row["ArchRoomNumber"] = room_number
                new_row["InternalRoomNumber"] = internal_value
                new_table.Rows.Add(new_row)

            self.override_table = new_table
            self.override_rows = []
            self.overrideMatrixGrid.ItemsSource = self.override_table.DefaultView
            return

        new_rows = []
        for room_number in sorted(room_numbers):
            internal_value = existing_lookup.get(room_number, "")
            if not internal_value:
                internal_value = self.internal_override_lookup.get(room_number, "")
            if not internal_value and use_defaults:
                internal_value = DEFAULT_INTERNAL_OVERRIDES.get(room_number, "")
            new_rows.append(InternalOverrideRow(room_number, internal_value))

        self.override_table = None
        self.override_rows = new_rows
        self.overrideMatrixGrid.ItemsSource = self.override_rows

    def get_override_lookup_from_grid(self):
        try:
            self.overrideMatrixGrid.CommitEdit()
            self.overrideMatrixGrid.CommitEdit()
        except Exception:
            pass

        lookup = {}
        if self.override_table:
            for row in self.override_table.Rows:
                arch_room_number = ("{0}".format(row["ArchRoomNumber"]) if row["ArchRoomNumber"] is not None else "").strip()
                internal_room_number = ("{0}".format(row["InternalRoomNumber"]) if row["InternalRoomNumber"] is not None else "").strip()
                if not arch_room_number:
                    continue
                if not internal_room_number:
                    continue
                lookup[arch_room_number] = internal_room_number
            return lookup

        for row in getattr(self, "override_rows", []):
            arch_room_number = (row.ArchRoomNumber or "").strip()
            internal_room_number = (row.InternalRoomNumber or "").strip()
            if not arch_room_number:
                continue
            if not internal_room_number:
                continue
            lookup[arch_room_number] = internal_room_number
        return lookup

    def internal_override_enabled(self):
        return bool(self.enableInternalOverrideCheckBox.IsChecked)

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
            self.statusText.Text = "{0} model values found | 0 active mappings".format(len(self.candidate_items))
            self.previewSummaryText.Text = "No mappings selected."
            self.matchPreviewList.ItemsSource = []
            return

        self.statusText.Text = "{0} model values found | {1} active mappings".format(
            len(self.candidate_items),
            len(mappings),
        )
        self.previewSummaryText.Text = "Mappings are ready. Click Apply to scan and update view/sheet titles using saved mappings."
        self.matchPreviewList.ItemsSource = []

    def update_context_preview(self):
        selected_old_values = self.get_selected_old_values()
        if not selected_old_values:
            self.contextSummaryText.Text = "Select one or more host tokens to prepare mapping."
            self.contextMatchList.ItemsSource = []
            return

        context_rows = [
            ContextMatchRow(value, "Mapping Token", "Model Mapping", "Token ready for room mapping")
            for value in selected_old_values
        ]
        self.contextSummaryText.Text = "{0} selected token(s) ready for mapping".format(len(selected_old_values))
        self.contextMatchList.ItemsSource = context_rows

    def get_selected_replacement_number(self):
        selected_item = self.newValueCombo.SelectedItem
        if not selected_item:
            return ""
        selected_text = "{0}".format(selected_item)
        return self.replacement_lookup.get(selected_text, "")

    def add_mapping_click(self, sender, args):
        selected_old_items = self.get_selected_old_items()
        replacement_number = self.get_selected_replacement_number()

        if not selected_old_items:
            forms.alert("Select at least one outdated value.", title=__title__, warn_icon=True)
            return
        if not replacement_number:
            forms.alert("Select a replacement architectural room.", title=__title__, warn_icon=True)
            return

        for item in selected_old_items:
            self.mapping_lookup[item.Token] = "{0}".format(replacement_number)

        self.refresh_mapping_list()
        self.refresh_override_matrix()
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
        self.refresh_override_matrix()
        self.update_preview()
        self.update_context_preview()

    def clear_mappings_click(self, sender, args):
        self.mapping_lookup = {}
        self.refresh_mapping_list()
        self.refresh_override_matrix()
        self.update_preview()
        self.update_context_preview()

    def use_needs_review_click(self, sender, args):
        selected_item = self.needsReviewList.SelectedItem
        if not selected_item:
            forms.alert("Select one item from Needs Review first.", title=__title__, warn_icon=True)
            return

        replacement_number = self.get_selected_replacement_number()
        if not replacement_number:
            forms.alert("Select a replacement architectural room first.", title=__title__, warn_icon=True)
            return

        review_text = "{0}".format(selected_item)
        selected_old_values = self.get_selected_old_values()
        host_tokens = [
            value
            for value in selected_old_values
            if value and looks_like_telecom_token(value) and value in self.candidate_counts
        ]

        if not host_tokens:
            extracted_tokens = extract_review_host_tokens(review_text)
            host_tokens = [
                token
                for token in extracted_tokens
                if token and looks_like_telecom_token(token) and token in self.candidate_counts
            ]

        if not host_tokens:
            forms.alert(
                "No valid telecom host token was found for mapping. "
                "Select telecom token(s) in the old values list, then click Use selected Needs Review.",
                title=__title__,
                warn_icon=True,
            )
            return

        for host_token in host_tokens:
            self.mapping_lookup[host_token] = "{0}".format(replacement_number)

        self.refresh_mapping_list()
        self.refresh_override_matrix()
        self.update_preview()
        self.update_context_preview()

    def old_values_selection_changed(self, sender, args):
        self.update_context_preview()

    def exclude_twc_tsa_click(self, sender, args):
        self.refresh_targets_and_candidates()

    def override_mode_click(self, sender, args):
        self.update_preview()

    def apply_click(self, sender, args):
        if self.review_only_mode:
            forms.alert(
                "Apply is disabled in Review-Only Mode.\n"
                "Save mappings only, then rerun when architectural links are available.",
                title=__title__,
                warn_icon=True,
            )
            return

        mappings = self.get_clean_mappings()
        internal_override_lookup = self.get_override_lookup_from_grid()
        use_internal_override = self.internal_override_enabled()

        has_base_mappings = bool(mappings)
        has_overrides = use_internal_override and bool(internal_override_lookup)

        if not has_base_mappings and not has_overrides:
            forms.alert(
                "Create at least one valid mapping, or enable Override and enter internal room numbers.",
                title=__title__,
                warn_icon=True,
            )
            return

        save_internal_override_lookup(internal_override_lookup)
        self.internal_override_lookup = dict(internal_override_lookup)
        effective_mappings = build_effective_mappings(mappings, internal_override_lookup, use_internal_override)
        if not effective_mappings:
            forms.alert(
                "No effective mapping values were produced. Review mapping and override entries.",
                title=__title__,
                warn_icon=True,
            )
            return

        save_mapping_lookup(mappings)

        deleted_rooms = self.mapping_health.get("deleted_linked_rooms", [])
        if deleted_rooms:
            warning_lines = [
                "{0} linked room(s) were deleted or are no longer available since last run.".format(len(deleted_rooms)),
                "Review mappings before applying.",
                "",
                "Examples:",
            ]
            for deleted_room in deleted_rooms[:5]:
                warning_lines.append("- {0}".format(deleted_room))
            if len(deleted_rooms) > 5:
                warning_lines.append("- ... and {0} more".format(len(deleted_rooms) - 5))
            forms.alert("\n".join(warning_lines), title=__title__, warn_icon=True)

        self.all_targets = collect_sync_targets()
        self.targets = filter_targets(self.all_targets, self.exclude_special_cases_enabled())
        matches = find_matches(self.targets, effective_mappings)

        unresolved_count = len(self.needs_review_items) + len(self.broken_items)
        preview_lines = [
            "Preflight Check",
            "",
            "Mappings",
            "- Active mappings: {0}".format(len(mappings)),
            "- Internal override enabled: {0}".format("Yes" if use_internal_override else "No"),
            "- Internal override rows saved: {0}".format(len(internal_override_lookup)),
            "- Effective mappings applied: {0}".format(len(effective_mappings)),
            "- Auto-mapped items: {0}".format(len(self.auto_mapped_items)),
            "- Needs review items: {0}".format(len(self.needs_review_items)),
            "- Broken items: {0}".format(len(self.broken_items)),
            "",
            "Mapping Health",
            "- Scoped architectural rooms: {0}".format(self.mapping_health.get("total_scoped_rooms", 0)),
            "- Auto-mapped changes: {0}".format(self.mapping_health.get("resolved", 0)),
            "- Auto-resolved no-change: {0}".format(self.mapping_health.get("resolved_no_change", 0)),
            "- Ignored no-space rooms: {0}".format(self.mapping_health.get("room_ignored_no_space", 0)),
            "",
            "Projected Updates",
            "- Affected view/sheet items: {0}".format(len(matches)),
            "- Affected by kind:",
            "  - Drafting View Name: {0}".format(len([m for m in matches if m.get("kind") == "Drafting View Name"])),
            "  - View Title on Sheet: {0}".format(len([m for m in matches if m.get("kind") == "View Title on Sheet"])),
            "  - Sheet Name: {0}".format(len([m for m in matches if m.get("kind") == "Sheet Name"])),
            "",
            "Unresolved Examples",
        ]
        preview_lines.extend(summarize_items(self.needs_review_items + self.broken_items, max_items=6))

        if unresolved_count > 0:
            preview_lines.extend(
                [
                    "",
                    "WARNING: {0} unresolved review item(s) exist.".format(unresolved_count),
                    "Apply will continue if you confirm. Unresolved items will not be updated.",
                ]
            )

        confirmed = forms.alert(
            "\n".join(preview_lines),
            title="{0} - Preflight".format(__title__),
            ok=False,
            yes=True,
            no=True,
            warn_icon=unresolved_count > 0,
        )
        if not confirmed:
            return

        self.results = {
            "mapping_health": dict(self.mapping_health),
            "mapping_diagnostics": {
                "auto_mapped_items": list(self.auto_mapped_items),
                "needs_review_items": list(self.needs_review_items),
                "broken_items": list(self.broken_items),
            },
            "internal_override_enabled": use_internal_override,
            "internal_override_lookup": dict(internal_override_lookup),
            "mappings": dict(mappings),
            "effective_mappings": dict(effective_mappings),
        }

        self.results["space_area_sync"] = apply_space_area_updates(effective_mappings)

        if not matches:
            update_results = {
                "updated_drafting_views": 0,
                "updated_view_titles": 0,
                "updated_sheet_names": 0,
                "failures": [],
                "adjustments": [],
            }
        else:
            update_results = apply_updates(matches)
        self.results.update(update_results)
        self.results["area_sync"] = sync_area_serving_zone_values()

        self.results["content_sync"] = apply_drafting_content_updates(effective_mappings)

        export_report = bool(self.exportReportCheckBox.IsChecked)
        if export_report:
            try:
                self.results["report_path"] = export_mappings_report(self.results)
            except Exception as ex:
                self.results["report_error"] = "Failed to export report: {0}".format(ex)

        self.DialogResult = True
        self.Close()

    def save_mapping_only_click(self, sender, args):
        mappings = self.get_clean_mappings()
        internal_override_lookup = self.get_override_lookup_from_grid()
        use_internal_override = self.internal_override_enabled()

        has_base_mappings = bool(mappings)
        has_overrides = use_internal_override and bool(internal_override_lookup)

        if not has_base_mappings and not has_overrides:
            forms.alert(
                "Create at least one valid mapping, or enable Override and enter internal room numbers.",
                title=__title__,
                warn_icon=True,
            )
            return

        internal_override_lookup = self.get_override_lookup_from_grid()
        save_internal_override_lookup(internal_override_lookup)
        self.internal_override_lookup = dict(internal_override_lookup)
        save_mapping_lookup(mappings)

        self.results = {
            "mapping_saved_only": True,
            "updated_drafting_views": 0,
            "updated_view_titles": 0,
            "updated_sheet_names": 0,
            "failures": [],
            "adjustments": [],
            "area_sync": {
                "scanned": 0,
                "updated": 0,
                "changes": [],
                "failures": [],
            },
            "mapping_health": dict(self.mapping_health),
            "mapping_diagnostics": {
                "auto_mapped_items": list(self.auto_mapped_items),
                "needs_review_items": list(self.needs_review_items),
                "broken_items": list(self.broken_items),
            },
            "mappings": dict(mappings),
            "internal_override_lookup": dict(internal_override_lookup),
            "internal_override_enabled": self.internal_override_enabled(),
        }

        forms.alert(
            "Mapping saved. No area, sheet, or view updates were applied.",
            title=__title__,
            warn_icon=False,
        )
        self.DialogResult = True
        self.Close()

    def cancel_click(self, sender, args):
        self.DialogResult = False
        self.Close()


if __name__ == "__main__":
    run_stage = "start"
    try:
        run_stage = "collect_valid_area_numbers"
        valid_numbers = collect_valid_tr_numbers()
        if not valid_numbers:
            forms.alert(
                "No Area Number values were found in workset '{0}'.".format(WORKSET_NAME),
                title=__title__,
                warn_icon=True,
            )
            script.exit()

        run_stage = "build_auto_mappings"
        auto_map_result = build_auto_mappings(valid_numbers)
        initial_mappings = dict(auto_map_result.get("mappings", {}))
        saved_mappings = load_saved_mapping_lookup()
        saved_internal_overrides = load_internal_override_lookup()
        for old_value, new_value in saved_mappings.items():
            if old_value not in initial_mappings:
                initial_mappings[old_value] = new_value

        candidates = auto_map_result.get("mapping_candidates", [])
        mapping_health = auto_map_result.get("health", {})
        auto_mapped_items = auto_map_result.get("auto_mapped_items", [])
        needs_review_items = auto_map_result.get("needs_review_items", [])
        broken_items = auto_map_result.get("broken_items", [])
        source_room_choices = auto_map_result.get("source_room_choices", [])
        source_room_lookup = auto_map_result.get("source_room_lookup", {})
        review_only_mode = bool(mapping_health.get("link_error"))
        review_only_reason = mapping_health.get("link_error", "")

        if review_only_mode and not source_room_choices:
            saved_room_numbers = set(saved_mappings.values())
            # Override-only workflows store architectural room keys here.
            saved_room_numbers.update(saved_internal_overrides.keys())
            saved_room_numbers = sorted(list(saved_room_numbers))
            for room_number in saved_room_numbers:
                label = "{0} | [saved]".format(room_number)
                source_room_choices.append(label)
                source_room_lookup[label] = room_number
            if saved_room_numbers:
                needs_review_items.insert(
                    0,
                    "Review-only mode: architectural links unavailable. Using saved room values for manual mapping.",
                )

        # Allow rerun when override mappings already exist, even if auto-scope
        # candidates and base host->architectural mappings are currently empty.
        if not candidates and not initial_mappings and not saved_internal_overrides:
            forms.alert(
                "No scoped architectural room values were found to establish mappings.",
                title=__title__,
                warn_icon=True,
            )
            script.exit()

        if review_only_mode:
            forms.alert(
                "Automatic link-based mapping could not be initialized: {0}\n\n"
                "Review-Only Mode is active. Save mappings only, then rerun when links are available.".format(mapping_health.get("link_error")),
                title=__title__,
                warn_icon=True,
            )

        run_stage = "init_window"
        window = MappingWindow(
            candidates,
            valid_numbers,
            [],
            source_room_choices,
            source_room_lookup,
            initial_mappings,
            mapping_health,
            auto_mapped_items,
            needs_review_items,
            broken_items,
            review_only_mode,
            review_only_reason,
        )
        run_stage = "show_window"
        dialog_result = window.ShowDialog()
        if not dialog_result or not window.results:
            script.exit()

        logger.success("Sync complete.")
        if window.results.get("mapping_saved_only"):
            print("Mapping saved only. No area, sheet, view, or drafting updates were applied.")
            print("Saved mappings: {0}".format(len(window.results.get("mappings", {}))))
            script.exit()

        print("Updated drafting view names: {0}".format(window.results["updated_drafting_views"]))
        print("Updated view titles on sheet: {0}".format(window.results["updated_view_titles"]))
        print("Updated sheet names: {0}".format(window.results.get("updated_sheet_names", 0)))
        print("Internal override enabled: {0}".format("Yes" if window.results.get("internal_override_enabled") else "No"))
        print("Base mappings saved: {0}".format(len(window.results.get("mappings", {}))))
        print("Internal overrides saved: {0}".format(len(window.results.get("internal_override_lookup", {}))))
        print("Effective mappings applied: {0}".format(len(window.results.get("effective_mappings", {}))))

        space_area_sync = window.results.get("space_area_sync", {})
        if space_area_sync:
            print("Space/Area sync updates:")
            print("- Updated space numbers: {0}".format(space_area_sync.get("updated_space_numbers", 0)))
            print("- Updated space names: {0}".format(space_area_sync.get("updated_space_names", 0)))
            print("- Updated area numbers: {0}".format(space_area_sync.get("updated_area_numbers", 0)))
            print("- Updated area names: {0}".format(space_area_sync.get("updated_area_names", 0)))
            if space_area_sync.get("failures"):
                print("- Space/Area failures/skipped:")
                for failure in space_area_sync.get("failures", []):
                    print("  - {0}".format(failure))

        area_sync = window.results.get("area_sync", {})
        print("Area sync ({0}) updates: {1} of {2} scanned".format(
            SERVING_ZONE_PARAM,
            area_sync.get("updated", 0),
            area_sync.get("scanned", 0),
        ))
        if area_sync.get("failures"):
            print("Area sync failures/skipped:")
            for failure in area_sync.get("failures", []):
                print("- {0}".format(failure))

        mapping_health = window.results.get("mapping_health", {})
        deleted_rooms = mapping_health.get("deleted_linked_rooms", [])
        if deleted_rooms:
            print("Deleted linked rooms since last run: {0}".format(len(deleted_rooms)))
            for deleted_room in deleted_rooms[:10]:
                print("- {0}".format(deleted_room))
            if len(deleted_rooms) > 10:
                print("- ... and {0} more".format(len(deleted_rooms) - 10))

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
    except Exception as ex:
        logger.error("Sync TR Names failed at stage '{0}': {1}".format(run_stage, ex))
        print("Unhandled error in Sync TR Names at stage '{0}': {1}".format(run_stage, ex))
        print(traceback.format_exc())
        forms.alert(
            "Sync TR Names failed with an unexpected error at stage '{0}'.\n"
            "Check the pyRevit output panel for full traceback details.".format(run_stage),
            title=__title__,
            warn_icon=True,
        )