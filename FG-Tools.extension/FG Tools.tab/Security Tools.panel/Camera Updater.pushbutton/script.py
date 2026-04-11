# -*- coding: utf-8 -*-
__title__   = "Camera Updater"
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

2. Automate Your Boring Work

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

import math

#.NET Imports
import clr
clr.AddReference('System')
from System.Collections.Generic import List

from pyrevit import script, forms


# ╦  ╦╔═╗╦═╗╦╔═╗╔╗ ╦  ╔═╗╔═╗
# ╚╗╔╝╠═╣╠╦╝║╠═╣╠╩╗║  ║╣ ╚═╗
#  ╚╝ ╩ ╩╩╚═╩╩ ╩╚═╝╩═╝╚═╝╚═╝
#==================================================
app    = __revit__.Application # type: ignore
uidoc  = __revit__.ActiveUIDocument # type: ignore
doc    = __revit__.ActiveUIDocument.Document # type: ignore #type:Document
targetFamilyName = "FG-CAMERA"
xamlfile = script.get_bundle_file('ui.xaml')


# ╔╦╗╔═╗╦╔╗╔
# ║║║╠═╣║║║║
# ╩ ╩╩ ╩╩╝╚╝
#==================================================

def _get_camera_param(element, param_name):
    """Safely read a string parameter; returns '<missing>' if absent."""
    param = element.LookupParameter(param_name)
    if not param:
        return "<missing>"
    value = param.AsString()
    return value if value else "<empty>"


# Function to collect FG camera elements
def camera_Collector():
    # Select Camera Families By Target Family Name
    family_symbols = FilteredElementCollector(doc) \
        .OfClass(Family) \
        .ToElements()
    camera_families = list(filter(lambda x: (targetFamilyName in x.Name), family_symbols))
    family_ids = [fs_id for family in camera_families for fs_id in family.GetFamilySymbolIds()]

    # Create Filter for Camera Elements w/ Target Family Name
    ElementFilter = LogicalOrFilter([FamilyInstanceFilter(doc, id) for id in family_ids])

    # Collect Cameras
    cam_collector = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_SecurityDevices) \
        .WherePasses(ElementFilter) \
        .ToElements()
    return cam_collector

# Function to generate a string of the selected camera's data
def print_single_camdata(element):
    if isinstance(element, FamilyInstance):
        camId         = element.Id
        levelId       = _get_camera_param(element, 'LEVEL ID')
        buildingSector = _get_camera_param(element, 'BUILDING SECTOR')
        camMark       = _get_camera_param(element, 'Mark')
        camNum = "{}-{}-{}".format(levelId, buildingSector, camMark)
        prompt = "The data for security camera {} are:\n".format(camNum)
        location = element.Location
        if isinstance(location, LocationPoint):
            point            = location.Point
            rotation_degrees = location.Rotation * (180.0 / math.pi)
            prompt += "Id: {}, Cam#: {}, Name: {}, Location: (X: {:.2f}, Y: {:.2f}, Z: {:.2f}), Rotation: {:.2f} degrees\n".format(
                camId, camNum, element.Name, point.X, point.Y, point.Z, rotation_degrees
            )
        else:
            prompt += "Name: {}, Location: Not a point, Rotation: Not available\n".format(element.Name)
    else:
        prompt = "Element ID: {}, Type: {}\n".format(element.Id, element.GetType().Name)
    return prompt

# Generates wrapper for list items in camera selection dialog
class listOption(forms.TemplateListItem):
    @property
    def name(self):
        return "Option: {}-{}-{}".format(
            _get_camera_param(self.item, 'LEVEL ID'),
            _get_camera_param(self.item, 'BUILDING SECTOR'),
            _get_camera_param(self.item, 'Mark'),
        )
# Generates dialog for selecting camera by number
camsInProject = camera_Collector()
ops = [listOption(element) for element in camsInProject]

select_cam = forms.SelectFromList.show(ops,
                                       title='Select Camera to Modify',
                                       multiselect=False,
                                       button_name='Select Camera'
                                       ) 

if not select_cam:
    forms.alert("No camera selected.", title=__title__)
else:
    print(print_single_camdata(select_cam))

#==================================================