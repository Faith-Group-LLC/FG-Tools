# -*- coding: utf-8 -*-
__title__   = "Areas Sync"
__doc__     = """Version = 0.1.0-a
Date    = 18.03.2026
________________________________________________________________
Description:

Syncs area elements in the specified workset by setting their "LAWA SERVING ZONE" parameter from name + number.

________________________________________________________________
How-To:

1. [Hold ALT + CLICK] on the button to open its source folder.
You will be able to override this placeholder.

2. Automate Your Boring Work ;)

________________________________________________________________
TODO:
[FEATURE] - Describe Your ToDo Tasks Here
________________________________________________________________
Last Updates:
- [18.03.2026] 0.1.0-a (updated by Hayden Fulghum) Change Description
________________________________________________________________
Author: Hayden Fulghum"""

# ╦╔╦╗╔═╗╔═╗╦═╗╔╦╗╔═╗
# ║║║║╠═╝║ ║╠╦╝ ║ ╚═╗
# ╩╩ ╩╩  ╚═╝╩╚═ ╩ ╚═╝
#==================================================
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import TaskDialog, TaskDialogResult, TaskDialogCommandLinkId

#.NET Imports
import clr
clr.AddReference('System')
from System.Collections.Generic import List


# ╦  ╦╔═╗╦═╗╦╔═╗╔╗ ╦  ╔═╗╔═╗
# ╚╗╔╝╠═╣╠╦╝║╠═╣╠╩╗║  ║╣ ╚═╗
#  ╚╝ ╩ ╩╩╚═╩╩ ╩╚═╝╩═╝╚═╝╚═╝
#==================================================
app    = __revit__.Application  # type: ignore
uidoc  = __revit__.ActiveUIDocument  # type: ignore
doc    = __revit__.ActiveUIDocument.Document  # type: ignore


# ╔╦╗╔═╗╦╔╗╔
# ║║║╠═╣║║║║
# ╩ ╩╩ ╩╩╝╚╝
#==================================================




#🤖 Automate Your Boring Work Here

target_workset_name = "Electronics-TELECOM LAWA SERVING ZONES"
collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Areas).WhereElementIsNotElementType()

# Find the target workset id
workset_collector = FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
target_workset_id = None
for ws in workset_collector:
    if ws.Name == target_workset_name:
        target_workset_id = ws.Id
        break

if target_workset_id is None:
    raise Exception("Workset '{0}' not found.".format(target_workset_name))

areas_to_update = [a for a in collector if a.WorksetId == target_workset_id]

if not areas_to_update:
    logger = __revit__.ActiveUIDocument.Application.WriteJournalComment # type: ignore
    logger("No Area elements found in workset '{0}'".format(target_workset_name), True)
else:
    # Counter for MPOE names to assign PRIMARY / SECONDARY
    mpoe_counter = 0
    
    # First pass: collect all changes to display to user
    changes = []
    for area in areas_to_update:
        name_param = area.LookupParameter("Name")
        number_param = area.LookupParameter("Number")
        target_param = area.LookupParameter("LAWA SERVING ZONE")

        if name_param is None or number_param is None or target_param is None:
            continue

        name_val = (name_param.AsString() or "").strip()
        number_val = (number_param.AsString() or "").strip()

        if not number_val:
            continue

        if name_val == "LAWA IT":
            new_value = "{0} ROOM {1}".format(name_val, number_val)
        elif name_val == "MPOE":
            mpoe_counter += 1
            if mpoe_counter == 1:
                new_value = "PRIMARY MPOE {0}".format(number_val)
            else:
                new_value = "SECONDARY MPOE {0}".format(number_val)
        else:
            new_value = "{0} {1}".format(name_val, number_val)

        current_value = (target_param.AsString() or "").strip()
        if current_value != new_value:
            changes.append({
                'area': area,
                'old': current_value if current_value else "[empty]",
                'new': new_value,
                'param': target_param
            })
    
    if changes:
        # Build dialog message
        dialog_msg = "The following {0} area(s) will be updated:\n\n".format(len(changes))
        for change in changes:
            dialog_msg += "Old: {0}\nNew: {1}\n\n".format(change['old'], change['new'])
        
        # Show confirmation dialog
        task_dialog = TaskDialog("Confirm Area Sync")
        task_dialog.MainInstruction = "Confirm Area Sync Operation"
        task_dialog.MainContent = dialog_msg
        task_dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Proceed with Update")
        task_dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, "Cancel Operation")
        task_dialog.DefaultButton = TaskDialogResult.CommandLink2
        
        result = task_dialog.Show()
        
        if result == TaskDialogResult.CommandLink1:
            with Transaction(doc, "Set LAWA SERVING ZONE on Areas") as t:
                t.Start()
                for change in changes:
                    change['param'].Set(change['new'])
                t.Commit()
        else:
            logger = __revit__.ActiveUIDocument.Application.WriteJournalComment # type: ignore
            logger("Area sync operation cancelled by user.", True)
    else:
        logger = __revit__.ActiveUIDocument.Application.WriteJournalComment # type: ignore
        logger("No area changes needed.", True)

#==================================================
#🚫 DELETE BELOW
