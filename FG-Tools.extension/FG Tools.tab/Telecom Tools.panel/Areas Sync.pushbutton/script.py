# -*- coding: utf-8 -*-
__title__ = "Areas Sync"
__doc__ = """Deprecated command.

Area synchronization has been consolidated into Sync TR Names.
Use Sync TR Names for mapping + area sync + view/sheet propagation.
"""

from Autodesk.Revit.UI import TaskDialog


dialog = TaskDialog(__title__)
dialog.MainInstruction = "Areas Sync has moved"
dialog.MainContent = (
    "This command is now deprecated.\n\n"
    "Use 'Sync TR Names' in Telecom Tools for the unified workflow:\n"
    "1) Room/Space/Area mapping\n"
    "2) LAWA SERVING ZONE sync\n"
    "3) View/sheet title updates"
)
dialog.Show()
