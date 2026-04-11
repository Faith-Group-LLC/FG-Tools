# -*- coding: utf-8 -*-
__title__   = "Camera FOV Generator"
__doc__     = """Version = 0.1
Date    = 12.06.2025
________________________________________________________________
Description:

Generate Camera views for each FG camera in the model. Derives camera Field of View 
(FOV) based on the camera's lens length and sensor size.

________________________________________________________________
How-To:

1. [Hold ALT + CLICK] on the button to open its source folder.
You will be able to override this placeholder.

2. Automate Your Boring Work ;)

________________________________________________________________
TODO:
[FEATURE] - Collect all Cameras in the model
[FEATURE] - Calculate the FOV for each camera based of the camera's lens length and sensor size
________________________________________________________________
Last Updates:
- [12.06.2025] v0.1 First Version of Camera FOV Generator
________________________________________________________________
Author: Hayden Fulghum"""

# ╦╔╦╗╔═╗╔═╗╦═╗╔╦╗╔═╗
# ║║║║╠═╝║ ║╠╦╝ ║ ╚═╗
# ╩╩ ╩╩  ╚═╝╩╚═ ╩ ╚═╝
#==================================================
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons

#.NET Imports
import clr
clr.AddReference('System')
from System.Collections.Generic import List # type: ignore
from pyrevit import forms, script, revit
from System.Windows.Controls import SelectionMode  # type: ignore # Add this import


# ╦  ╦╔═╗╦═╗╦╔═╗╔╗ ╦  ╔═╗╔═╗
# ╚╗╔╝╠═╣╠╦╝║╠═╣╠╩╗║  ║╣ ╚═╗
#  ╚╝ ╩ ╩╩╚═╩╩ ╩╚═╝╩═╝╚═╝╚═╝
#==================================================
app    = __revit__.Application # type: ignore
uidoc  = __revit__.ActiveUIDocument # type: ignore
doc    = __revit__.ActiveUIDocument.Document # type: ignore #type:Document


# ╔╦╗╔═╗╦╔╗╔
# ║║║╠═╣║║║║
# ╩ ╩╩ ╩╩╝╚╝
#==================================================

def collect_fg_camera_instances(doc):
    """
    Collect all family instances in the model whose family name contains 'FG-CAMERA'.
    Args:
        doc (Autodesk.Revit.DB.Document): The current Revit document.
    Returns:
        List[FamilyInstance]: List of matching family instances.
    """
    collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    fg_cameras = [fi for fi in collector if 'FG-CAMERA' in fi.Symbol.Family.Name]
    # Print the element IDs of the collected cameras
    for cam in fg_cameras:
        print('FG-CAMERA ElementId:', cam.Id)
    return fg_cameras

collect_fg_camera_instances(doc)
