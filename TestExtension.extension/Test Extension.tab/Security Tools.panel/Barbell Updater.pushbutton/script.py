# -*- coding: utf-8 -*-
__title__   = "Barbell Updater"
__doc__     = """Version = 1.2
Date    = 14.03.2025
________________________________________________________________
Description:

This script collects all linked models in the Revit document, presents a
modal dialogue for the user to select a linked model, finds all Door
elements and instances of the family FG-ACS DOOR BARBELL in the selected
model, creates sets of intersecting Door and FG-ACS DOOR BARBELL pairs,
updates the DOOR ID parameter in each FG-ACS DOOR BARBELL with the Mark
parameter value from the corresponding Door, and prints out a list of
updated DOOR ID values and corresponding FG-ACS DOOR BARBELL element IDs.

________________________________________________________________
How-To:

1. Select the models containing doors and set the Family Name to be checked. Will default to FG-ACS DOOR BARBELL
    if no input is provided.
2. Confirm the number of doors and barbells found.
3. Confirm the intersecting pairs found.
4. Select the pairs to update the DOOR ID parameter.
5. Confirm the updated DOOR ID values.

________________________________________________________________
TODO:
[FEATURE] - Allow selection of parameter from doors to be used for updating DOOR ID in FG-ACS DOOR BARBELL.
[FEATURE] - Allow selection of parameter from FG-ACS DOOR BARBELL to be updated with DOOR ID from doors.
________________________________________________________________
Last Updates:
- [14.03.2025] v1.2 Updated script to fix SelectionMode error, set default family name, and use default if no input.
    Icon updated.
- [13.03.2025] v1.1 Updated script to collect linked models, present a modal
  dialogue, find Door elements and FG-ACS DOOR BARBELL instances, create
  intersecting pairs, update DOOR ID parameter, and print updated values.
- [15.06.2024] v1.0 Change Description
- [10.06.2024] v0.5 Change Description
- [05.06.2024] v0.1 Change Description 
________________________________________________________________
Author: Faith Group"""

# ╦╔╦╗╔═╗╔═╗╦═╗╔╦╗╔═╗
# ║║║║╠═╝║ ║╠╦╝ ║ ╚═╗
# ╩╩ ╩╩  ╚═╝╩╚═ ╩ ╚═╝
#==================================================
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons

#.NET Imports
import clr
clr.AddReference('System')
from System.Collections.Generic import List
from pyrevit import forms, script, revit
from System.Windows.Controls import SelectionMode  # Add this import

# ╦  ╦╔═╗╦═╗╦╔═╗╔╗ ╦  ╔═╗╔═╗
# ╚╗╔╝╠═╣╠╦╝║╠═╣╠╩╗║  ║╣ ╚═╗
#  ╚╝ ╩ ╩╩╚═╩╩ ╩╚═╝╩═╝╚═╝╚═╝
#==================================================
app    = __revit__.Application
uidoc  = __revit__.ActiveUIDocument
doc    = __revit__.ActiveUIDocument.Document #type:Document

# ╔╦╗╔═╗╦╔╗╔
# ║║║╠═╣║║║║
# ╩ ╩╩ ╩╩╝╚╝
#==================================================

# Collect all linked models
collector = FilteredElementCollector(doc).OfClass(RevitLinkInstance)
linked_models = [link.Name for link in collector]

# Present a dropdown list to select the desired linked models and input for barbell family name
class BarbellFamilyInput(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, 'ui.xaml')
        self.linked_models_list.ItemsSource = linked_models
        self.linked_models_list.SelectionMode = SelectionMode.Extended  # Use SelectionMode.Extended
        self.barbell_family_name_input.Text = "FG-ACS DOOR BARBELL"  # Set default family name
        self.ok_button.Click += self.on_ok
        self.cancel_button.Click += self.on_cancel

    def on_ok(self, sender, e):
        self.selected_model_names = [item for item in self.linked_models_list.SelectedItems]
        self.barbell_family_name = self.barbell_family_name_input.Text or "FG-ACS DOOR BARBELL"  # Use default if no input
        self.Close()

    def on_cancel(self, sender, e):
        self.selected_model_names = None
        self.barbell_family_name = None
        self.Close()

dialog = BarbellFamilyInput()
dialog.ShowDialog()

selected_model_names = dialog.selected_model_names
barbell_family_name = dialog.barbell_family_name

if not selected_model_names or not barbell_family_name:
    forms.alert("Operation cancelled by user.", title="Cancelled")
    script.exit()

"""
Checks if there is more than one intersecting door for a given barbell.
Raises an exception if more than one door is found.
"""
def check_OnetoOne(barbell, intersecting_doors):
    if len(intersecting_doors) > 1:
        raise Exception("More than one door found for FG-ACS DOOR BARBELL instance: {}".format(barbell.Id))

"""
Checks for intersections between doors and barbells.
If more than one door intersects with a barbell, chooses the closest door.
Returns a list of intersecting door and barbell pairs.
"""
def check_intersection(doc, check_OnetoOne, linked_doc, doors, barbells):
    intersecting_pairs = []
    for barbell in barbells:
        intersecting_doors = []
        barbell_bbox = barbell.get_BoundingBox(doc.ActiveView)
        for door in doors:
            door_bbox = door.get_BoundingBox(linked_doc.ActiveView)
            if Outline(barbell_bbox.Min, barbell_bbox.Max).Intersects(Outline(door_bbox.Min, door_bbox.Max), 0.0):
                intersecting_doors.append(door)
        
        if intersecting_doors:
            # Choose the closest door if more than one intersects
            closest_door = min(intersecting_doors, key=lambda door: barbell_bbox.Min.DistanceTo(door.get_BoundingBox(linked_doc.ActiveView).Min))
            intersecting_pairs.append((closest_door, barbell))
    return intersecting_pairs

if selected_model_names:
    selected_models = [link for link in collector if link.Name in selected_model_names]
    linked_docs = [model.GetLinkDocument() for model in selected_models]

    # Find all Door elements in the selected linked models
    doors = []
    for linked_doc in linked_docs:
        door_collector = FilteredElementCollector(linked_doc).OfCategory(BuiltInCategory.OST_Doors).WhereElementIsNotElementType()
        doors.extend([door for door in door_collector])

    # Find all instances of the specified barbell family in the host document
    barbell_collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_SecurityDevices).OfClass(FamilyInstance)
    barbells = [barbell for barbell in barbell_collector if barbell.Symbol.Family.Name == barbell_family_name]

    # Show a dialog with the counts of all found doors and barbells
    doors_count = len(doors)
    barbells_count = len(barbells)
    combined_message = "Doors found: {}\nBarbells found: {}".format(doors_count, barbells_count)
    confirmed = forms.alert(combined_message, title="Found Doors and Barbells", yes=True, no=True)
    if not confirmed:
        forms.alert("Operation cancelled by user.", title="Cancelled")
        script.exit()

    # Create sets of intersecting Door and FG-ACS DOOR BARBELL pairs
    intersecting_pairs = []
    for linked_doc in linked_docs:
        intersecting_pairs.extend(check_intersection(doc, check_OnetoOne, linked_doc, doors, barbells))

    # Show a dialog with the intersecting pairs found and allow user to confirm selection
    if intersecting_pairs:
        pairs_message = "\n".join(["Door ID: {} - Barbell ID: {}".format(door.Id, barbell.Id) for door, barbell in intersecting_pairs])
        confirmed = forms.alert(pairs_message, title="Intersecting Pairs Found", yes=True, no=True)
        if not confirmed:
            forms.alert("Operation cancelled by user.", title="Cancelled")
            script.exit()
    else:
        forms.alert("No intersecting pairs found.", title="Intersecting Pairs Found")
        script.exit()

    # Filter pairs with mismatching marks and DOOR IDs
    mismatching_pairs = []
    for door, barbell in intersecting_pairs:
        door_mark = door.LookupParameter("Mark").AsString()
        door_id_params = [param for param in barbell.Parameters if param.Definition.Name == "DOOR ID"]
        for param in door_id_params:
            current_door_id = param.AsString()
            if current_door_id != door_mark:
                mismatching_pairs.append((door, barbell, current_door_id, door_mark))

    # Show a multi-select dialog for mismatching pairs
    if mismatching_pairs:
        items = ["Door ID: {} - Barbell ID: {} (Current DOOR ID: {}, New DOOR ID: {})".format(door.Id, barbell.Id, current_door_id, door_mark) for door, barbell, current_door_id, door_mark in mismatching_pairs]
        selected_items = forms.SelectFromList.show(items, title="Select Pairs to Update", multiselect=True, button_name='Update Selected', cancel_button=True)
        if not selected_items:
            forms.alert("No pairs selected for update.", title="Cancelled")
            script.exit()

        # Process the selected pairs
        selected_pairs = [mismatching_pairs[items.index(item)] for item in selected_items]
        updated_pairs = []
        with Transaction(doc, "Update DOOR ID parameters") as t:
            t.Start()
            for door, barbell, current_door_id, door_mark in selected_pairs:
                door_id_params = [param for param in barbell.Parameters if param.Definition.Name == "DOOR ID"]
                for param in door_id_params:
                    if param.AsString() != door_mark:
                        param.Set(door_mark)
                        updated_pairs.append((current_door_id, door_mark, barbell.Id))
            t.Commit()

        # Print out the list of updated DOOR ID values and corresponding FG-ACS DOOR BARBELL element IDs
        if updated_pairs:
            message = "\n".join(["Updated DOOR ID from {} to {} for FG-ACS DOOR BARBELL ID: {}".format(old_id, new_id, barbell_id) for old_id, new_id, barbell_id in updated_pairs])
            forms.alert(message, title="Updated Door IDs")
        else:
            forms.alert("No updates were made.", title="Updated Door IDs")
    else:
        forms.alert("No mismatching pairs found.", title="No Updates Needed")

#==================================================