# FG Toolbar

## Overview
TestExtension is a PyRevit extension that provides various tools and utilities for Revit users. This extension includes sample scripts, hooks, and panels to enhance your Revit experience.

## Installation
To install the TestExtension, follow these steps:
1. Download the extension files.
2. Place the `TestExtension.extension` folder in your PyRevit extensions directory.
3. Restart Revit and ensure the extension is loaded.

## Features
### Hooks
- `command-before-exec[ID_FILE_IMPORT].py`: A hook script that runs before file import commands.

### Libraries
- `lib/Samples/`: Contains various sample scripts for different Revit tasks.
  - `CreateElements.py`: Script to create elements in Revit.
  - `FilteredElementCollector.py`: Script to filter and collect elements.
  - `Parameters.py`: Script to manage parameters.
  - `Selection.py`: Script to handle element selection.
  - `TemplateDynamo.py`: Dynamo template script.
  - `TemplatePyRevit.py`: PyRevit template script.
  - `TemplatePyRevitMin.py`: Minimal PyRevit template script.
  - `Transactions.py`: Script to handle transactions.
  - `TranslateCSharp.py`: Script to translate C# code.
  - `ViewsSheets.py`: Script to manage views and sheets.

### Panels
- `About.panel/`: Contains information about the extension.
- `LearnRevitAPI.panel/`: Provides resources to learn the Revit API.
- `PlaceholderPanel.panel/`: Placeholder for future panels.
- `Resources.panel/`: Contains various resources.
- `Security Tools.panel/`: Provides security tools.

## Usage
To use the extension, open Revit and navigate to the `Test Extension` tab. From there, you can access the various panels and tools provided by the extension.

## Contributing
If you would like to contribute to the development of this extension, please follow these steps:
1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Commit your changes and push them to your fork.
4. Submit a pull request with a description of your changes.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Contact
For any questions or issues, please contact the project maintainer at [hayden.fulghum@faithgroupllc.com](mailto:hayden.fulghum@faithgroupllc.com).