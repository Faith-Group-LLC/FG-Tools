# FG Tools — pyRevit Extension

A pyRevit extension providing Security and Telecom tools for use in Autodesk Revit at Faith Group.

---

## Requirements

- [Autodesk Revit](https://www.autodesk.com/products/revit/) 2019 or later
- [pyRevit](https://github.com/pyrevitlabs/pyRevit/releases/latest) 4.8 or later

---

## Installation

### 1. Install pyRevit

Download and run the latest signed installer from the [pyRevit releases page](https://github.com/pyrevitlabs/pyRevit/releases/latest). Accept the defaults — pyRevit will register itself with all installed versions of Revit automatically.

### 2. Clone this repository

Clone the repo to a local directory. The parent folder matters — pyRevit needs to see the `.extension` folder inside it.

```
git clone https://github.com/Faith-Group-LLC/FG-Tools.git C:\FG-Tools
```

This places `FG-Tools.extension` at `C:\FG-Tools\FG-Tools.extension`.

### 3. Register the extension directory in pyRevit

1. Open Revit and go to the **pyRevit** tab → **pyRevit** panel → **Settings**
2. Scroll to **Custom Extension Directories**
3. Click **Add Folder** and select the parent folder containing `FG-Tools.extension` (e.g. `C:\FG-Tools`)
4. Click **Save Settings** and then **Reload** (or restart Revit)

The **FG Tools** tab will appear in the Revit ribbon after reload.

### Updating

Pull the latest changes from the repo:

```
cd C:\FG-Tools
git pull
```

Then reload pyRevit from the **pyRevit** tab → **Reload**.

---

> **Note — Centralized deployment:** Individual Git-based installation is the current method. A team-wide deployment via pyRevit for Teams is planned for the future. See the [pyRevit for Teams documentation](https://pyrevitlabs.notion.site/) for reference.

---

## Tools

### Security Tools

| Tool | Description |
|------|-------------|
| **Barbell Updater** | Matches FG-ACS DOOR BARBELL elements to their associated Door by DOOR ID, then writes parameter values from the Door back to the Barbell. |
| **Camera FOV Generator** | Calculates Field of View (FOV) for FG camera family instances based on lens length and sensor size parameters, and writes the result back to the model. |
| **Camera Updater** | Reviews and updates parameter data on selected security camera instances, including location, rotation, and identification fields. |

### Telecom Tools

| Tool | Description |
|------|-------------|
| **Sync TR Names** | Synchronizes Telecom Room (TR) names across drafting view names, view titles, and sheet names using Area Number as the source of truth. Supports multi-mapping in a single run with a WPF preview dialog. Persists mapping state between sessions. |
| **Zone Schedulizer** | Builds and manages data outlet schedules organized by TR, Level ID, and Building Sector. Automatically removes empty schedules. |
| **Data Outlet Levels** | Populates the LEVEL ID parameter on data outlet families using schedule-driven level mapping, with fallback support for hosted/nested outlets. |
| **Data Outlet Sectors** | Assigns the BUILDING SECTOR parameter to data outlets based on containment within ZONE 5A–5G scope boxes, with conflict resolution for overlapping zones. |

---

## Contact

[hayden.fulghum@faithgroupllc.com](mailto:hayden.fulghum@faithgroupllc.com)
