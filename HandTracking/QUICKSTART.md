# Hand tracking on a teammate's Windows computer

This module is self-contained. The original `shadow` folder is not needed.

1. Install **Python 3.11, 64-bit** from https://www.python.org/downloads/ and enable **Add Python to PATH**. Reopen the terminal after installation.
2. Open the repository's root `project.godot` in Godot and run `main.tscn` (F5). Do not open the nested demo project for the integrated game.
3. Double-click `HandTracking/start_camera.bat`. The launcher creates `.venv` locally and installs requirements automatically. The tracker downloads its hand model on the first camera run. Internet is required for this initial setup.
4. Show two hands to the camera. Press **N** to calibrate the near distance and **F** for the far distance. Press **Q** in the camera window to exit.

For a camera-free connection test, run `start_simulation.bat` instead. The simulation intentionally cycles distance continuously; its colors will keep changing. Stop it with Ctrl+C. Do not run simulation and camera senders together. Run only one Godot receiver on port 4242.

If the wrong camera opens, run from PowerShell:

```powershell
.\start_camera.ps1 --camera 1
```

The default UDP destination is `127.0.0.1:4242`; Godot and the tracker must run on the same computer. Allow Windows desktop apps to access the camera, and close other apps using it.

Commit these launchers, source code, requirements and documentation. Do not commit `.venv`, `__pycache__`, downloaded `.task` models, `.download` files or Godot caches. Each teammate creates their own local environment. Existing shader/runtime issues must be resolved separately; a successful tracker startup does not validate game rendering.
