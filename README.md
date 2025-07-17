# Ultrawide Window Positioner

## Manage window layouts with custom configurations

#### This application provides a GUI to create and apply custom window layout configurations.
#### Change position and size, set always-on-top and remove titlebar.
#### Borderless windowed without fullscreen.

***Note: Windows only. No current plan for Linux support.***

## Features:
#### - Create and apply window configurations.  (Stored as 'config_*.ini' files.)
#### - Visual preview of the selected configuration's layout.
#### - Optional screenshot view mode.
- Screenshots can be taken using the "Take screenshots" button, or automatically downloaded from IGDB using the "Download images" button. (API key needed for IGDB.)
- You can also manually add your own screenshots to the image folder.
#### - Toggle Always-on-Top state specifically for windows managed by the *currently applied config*.
#### - Support for multiple configuration files.
#### - Config creation through GUI.
#### - Compact GUI mode available.

## Screenshots
### Main window
<img src="https://i.ibb.co/8n4HxZcB/Skjermbilde-2025-07-15-135700.png" alt="Main window">

### Main window screenshot mode
<img src="https://i.ibb.co/KcQkdzcQ/Skjermbilde-2025-07-15-135820.png" alt="Main window screenshot mode">

### Main window compact mode
<img src="https://i.ibb.co/d4dJqMVC/Skjermbilde-2025-07-15-135828.png" alt="Main window compact mode">

### Config window
<img src="https://i.ibb.co/GvBfJpnQ/Skjermbilde-2025-07-15-135855.png" alt="Config window">


## How to use:
### Create config
1. Click the "Create config" button while your applications are running
2. Select the application windows you would like to manage in the list and click "Confirm selection"
3. Choose the settings you want, type a config name and click "Save config"
   - Choosing an existing file name will overwrite the previous config

- Auto align
   - Click "Auto align" to go through the predefined layouts for the number of windows selected.
   - Custom presets can be configured in ```layout_config.ini```

- Update drawing
   - Will update the screen layout drawing with the current settings

### Apply config
1. Select a configuration from the dropdown menu to preview its layout.
2. Click 'Apply config' to activate the window layout defined in the selected config file.

### Reset config
- Resets currently loaded configuration
### Toggle AOT
- Change the state of windows managed by the ***currently applied config***.
- Useful for temporary access to the start menu or taskbar if it is covered by an application/game.

### Delete config
1. Select the config from the dropdown
2. Click "Delete config"
3. Click "Yes" in the confirmation window
- You can also manually delete the files from the config folder

### Manually edit settings
1. Click the "Open Config Folder" button
2. Open the config file you want to edit in notepad and adjust values
3. Save the config file and close notepad
- Useful for adding search_title override (pending adding this feature to config creation GUI)

### Compact mode
- Click the "Toggle compact" to switch between full and compact mode

### Take screenshots
- This button will take a screenshot of all detected windows from the currently selected configuration and use them for the GUI

### Download images
- This button will download screentshots from IGDB and use them for the GUI
- The "Download images" function requires IGDB Client ID and Client Secret to work. These are not included.

### Toggle images
- Switch between basic and screenshot layout

### Snap application on open
- You can set the application to open snapped to either edge of the screen instead of centered.
- This can be used to avoid opening the application behind a always-on-top window.

## Configuration Format (***'config_\<name\>.ini'***):
```
[Window Title]
position = x,y              # Window position
size = width,height         # Window size
always_on_top = true/false  # Set always-on-top state
titlebar = true/false       # Enable to keep title bar, disable to remove titlebar
search_title = <title>      # Search title override for screenshot download (must be added manually)
```
### Example:
```
[Microsoft Edge]
position = -7,0
size = 1722,1400
always_on_top = false
titlebar = true

[Final Fantasy XIV]
search_title = Final Fantasy XIV Online
position = 1708,0
size = 2560,1440
always_on_top = true
titlebar = false

[Discord]
position = 4268,0
size = 852,1392
always_on_top = false
titlebar = true
```

## Notes:
- Window titles in config are matched partially and case-insensitively against open windows.

## Multi-monitor use

### This application is made with ultrawide monitors in mind (32:9 / 21:9) and will work best on a single monitor setup.

### *Should* work well with similar monitors in a left to right setup, but only limited testing has been done:
   ```
   +-----------------------+ +-----------------------+ +-----------------------+
   |                       | |                       | |                       |
   |                       | |                       | |                       |
   | Monitor 1 = 1920x1080 | | Monitor 2 = 1920x1080 | | Monitor 3 = 1920x1080 |
   |                       | |                       | |                       |
   |                       | |                       | |                       |
   +-----------------------+ +-----------------------+ +-----------------------+
   ```

### It may ***not*** work well with:
#### Multi-monitor setups with different resolutions.
   ```
   +-----------------------+ 
   |                       | +---------------------+
   |                       | |                     |
   | Monitor 1             | | Monitor 2           |
   | 1920x1080             | | 1280x1024           |
   |                       | |                     |
   +-----------------------+ +---------------------+
   ```

#### Multi-monitor setups with vertical positioning.
   ```
   +-----------------------+ 
   |                       |
   |                       |
   | Monitor 1 = 1920x1080 |
   |                       |
   |                       |
   +-----------------------+
   +-----------------------+ 
   |                       |
   |                       |
   | Monitor 2 = 1920x1080 |
   |                       |
   |                       |
   +-----------------------+
   ```
