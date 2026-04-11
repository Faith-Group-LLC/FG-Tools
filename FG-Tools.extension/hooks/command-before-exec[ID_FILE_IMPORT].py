# -*- coding: utf-8 -*-
#⬇️ Imports
from pyrevit import revit, EXEC_PARAMS

#--------------------------------------------------
#📦 Variables
sender = __eventsender__ # UIApplication
args   = __eventargs__   # Autodesk.Revit.UI.Events.BeforeExecutedEventArgs
doc = revit.doc

#--------------------------------------------------
#🎯 MAIN

