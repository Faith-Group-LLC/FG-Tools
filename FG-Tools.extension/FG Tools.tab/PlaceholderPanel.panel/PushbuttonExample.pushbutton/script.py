# -*- coding: utf-8 -*-
__title__   = "Space Sync"
__doc__     = """Version = 1.0
Date    = 15.06.2024
________________________________________________________________
Description:

This is the placeholder for a .pushbutton
You can use it to start your pyRevit Add-In

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
- [15.06.2024] v1.0 Change Description
- [10.06.2024] v0.5 Change Description
- [05.06.2024] v0.1 Change Description 
________________________________________________________________
Author: Erik Frits"""

# ╦╔╦╗╔═╗╔═╗╦═╗╔╦╗╔═╗
# ║║║║╠═╝║ ║╠╦╝ ║ ╚═╗
# ╩╩ ╩╩  ╚═╝╩╚═ ╩ ╚═╝
#==================================================
from Autodesk.Revit.DB import *

#.NET Imports
import clr
clr.AddReference('System')
from System.Collections.Generic import List


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
    raise Exception(f"Workset '{target_workset_name}' not found.")

areas_to_update = [a for a in collector if a.WorksetId == target_workset_id]

if not areas_to_update:
    logger = __revit__.ActiveUIDocument.Application.WriteJournalComment
    logger(f"No Area elements found in workset '{target_workset_name}'", True)
else:
    with Transaction(doc, "Set LAWA SERVING ZONE on Areas") as t:
        t.Start()
        for area in areas_to_update:
            name_param = area.LookupParameter("Name")
            number_param = area.LookupParameter("Number")
            target_param = area.LookupParameter("LAWA SERVING ZONE")

            if name_param is None or number_param is None or target_param is None:
                continue

            name_val = name_param.AsString() or ""
            number_val = number_param.AsString() or ""
            new_value = f"{name_val} {number_val}".strip()

            if new_value:
                target_param.Set(new_value)

        t.Commit()

#==================================================
#🚫 DELETE BELOW
