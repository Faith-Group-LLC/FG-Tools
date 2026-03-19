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

#.NET Imports
import clr
clr.AddReference('System')
clr.AddReference('System.Windows.Forms')
clr.AddReference('IronPython.Wpf')

import wpf
from System import Windows
from pyrevit import script,forms,EXEC_PARAMS
from pyrevit import UI

from System.Collections.Generic import List


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

# Function to generate and concatenate a string of camera element IDs, Cam #s, Location Data and Rotation Data
def print_camdata(collector):
    prompt = "The security cameras in the current model are:\n"
    for element in collector:
        if isinstance(element, FamilyInstance):
            # Extract Element Id
            camId = element.Id
            # Extract Camera Number
            levelId = element.LookupParameter('LEVEL ID').AsString()
            buildingSector = element.LookupParameter('BUILDING SECTOR').AsString()
            camMark = element.LookupParameter('Mark').AsString()
            camNum = "{}-{}-{}".format(
                    levelId, buildingSector, camMark
                )
            # Extract the location of the FamilyInstance
            location = element.Location
            if isinstance(location, LocationPoint):
                point = location.Point
                transform = location.Rotation
                # Convert rotation from radians to degrees
                rotation_degrees = transform * (180 / 3.14159265358979)
                # Format and print the location and rotation details using .format() for IronPython compatibility
                prompt += "Id: {}, Cam#: {}, Name: {}, Location: (X: {:.2f}, Y: {:.2f}, Z: {:.2f}), Rotation: {:.2f} degrees\n".format(
                    camId, camNum, element.Name, point.X, point.Y, point.Z, rotation_degrees
                )
            else:
                # If location is not a point, handle accordingly
                prompt += "Name: {}, Location: Not a point, Rotation: Not available\n".format(element.Name)
        else:
            # Handle cases where the element is not a FamilyInstance
            prompt += "Element ID: {}, Type: {}\n".format(element.Id, element.GetType().Name)
    return prompt

# Function to generate a string of the selected cameras data
def print_single_camdata(element):
    if isinstance(element, FamilyInstance):
        # Extract Element Id
        camId = element.Id
        # Extract Camera Number
        levelId = element.LookupParameter('LEVEL ID').AsString()
        buildingSector = element.LookupParameter('BUILDING SECTOR').AsString()
        camMark = element.LookupParameter('Mark').AsString()
        camNum = "{}-{}-{}".format(
                levelId, buildingSector, camMark
            )
        prompt = "The data for security camera {} are:\n".format(camNum)
        # Extract the location of the FamilyInstance
        location = element.Location
        if isinstance(location, LocationPoint):
            point = location.Point
            transform = location.Rotation
            # Convert rotation from radians to degrees
            rotation_degrees = transform * (180 / 3.14159265358979)
            # Format and print the location and rotation details using .format() for IronPython compatibility
            prompt += "Id: {}, Cam#: {}, Name: {}, Location: (X: {:.2f}, Y: {:.2f}, Z: {:.2f}), Rotation: {:.2f} degrees\n".format(
                camId, camNum, element.Name, point.X, point.Y, point.Z, rotation_degrees
            )
        else:
            # If location is not a point, handle accordingly
            prompt += "Name: {}, Location: Not a point, Rotation: Not available\n".format(element.Name)
    else:
        # Handle cases where the element is not a FamilyInstance
        prompt += "Element ID: {}, Type: {}\n".format(element.Id, element.GetType().Name)
    return prompt

# Generates wrapper for list items in camera selection dialog
class listOption(forms.TemplateListItem):
    @property
    def name(self):
        return "Option: {}-{}-{}".format(
            self.item.LookupParameter('LEVEL ID').AsString(),
            self.item.LookupParameter('BUILDING SECTOR').AsString(),
            self.item.LookupParameter('Mark').AsString()
            )
# Generates dialog for selecting camera by number
camsInProject = camera_Collector()
ops = [listOption(element) for element in camsInProject]

select_cam = forms.SelectFromList.show(ops,
                                       title='Select Camera to Modify',
                                       multiselect=False,
                                       button_name='Select Camera'
                                       ) 

print(print_single_camdata(select_cam))

#==================================================