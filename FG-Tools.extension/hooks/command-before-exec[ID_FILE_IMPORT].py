# -*- coding: utf-8 -*-
#⬇️ Imports
from pyrevit import revit, EXEC_PARAMS

#--------------------------------------------------
#📦 Variables
sender = __eventsender__ # type: ignore # UIApplication
args   = __eventargs__   # type: ignore # Autodesk.Revit.UI.Events.BeforeExecutedEventArgs
doc = revit.doc

#--------------------------------------------------
#🎯 MAIN

