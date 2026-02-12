# Ultrawide Window Positioner
***Updated to use Pyside for GUI (QT)***

## Manage window layouts with custom configurations

#### This application provides a GUI to create and apply custom window layout configurations.
#### Change position and size, set always-on-top and remove titlebar.
#### Borderless windowed without fullscreen.

***Note: Windows only. No current plan for Linux support.***

## Features:
#### - Create and apply window configurations.  (Stored as 'config_*.ini' files.)
#### - Visual preview of the selected configuration's layout.
#### - Multiple presets available for window layout, as well as manual adjustments.
#### - Optional screenshot view mode.
- Screenshots can be taken using the "Take screenshots" button, or automatically downloaded from IGDB or RAWG using the "Download images" button. (API key needed for IGDB/RAWG.)
- You can also manually add your own screenshots to the image folder.
#### - Toggle Always-on-Top state specifically for windows managed by the *currently applied config*.
#### - Set higher process priority for selected applications. (sets it to "above normal".)
#### - Support for multiple configuration files.
#### - Config creation through GUI.
#### - Compact GUI mode available.
#### - Configurable overrides per application available in ```layout_config.ini```

## Screenshots
### Main window
<img src="https://i.ibb.co/Q7c9XKzm/Skjermbilde-2025-09-07-164602.png" alt="Main window">

### Main window screenshot mode
<img src="https://i.ibb.co/rL3rtgF/Skjermbilde-2025-09-07-164651.png" alt="Main window screenshot mode">

### Main window compact mode
<img src="https://i.ibb.co/bjMJNhcB/Skjermbilde-2025-09-07-164705.png" alt="Main window compact mode">

### Config window
<img src="https://i.ibb.co/jPfwgSyH/Skjermbilde-2025-09-07-164734.png" alt="Config window">


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
- Configurable hotkey in ```settings.json```
- Default hotkey: alt + home

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

### Auto-reapply
- Setting this will automatically reapply the current window settings if a change is detected.
- Useful for games that has a lobby and lauches a new game window per match, for example League of Legends.

## Configuration Format (***'config_\<name\>.ini'***):
```
[Window Title]
apply_order = Titlebar,Pos,Size,Aot # Set the order for applying settings
position = x,y                      # Window position
size = width,height                 # Window size
always_on_top = true/false          # Set always-on-top state
titlebar = true/false               # Enable to keep title bar, disable to remove titlebar
process_priority = true/false       # Set priority to "above normal" if true
search_title = <title>              # Search title override for screenshot download (must be added manually)
```
### Example:
```
[DEFAULT]
apply_order = Titlebar,Pos,Size,Aot

[Opera]
apply_order = Titlebar,Pos,Size,Aot
position = -7,0
size = 1720,1401
always_on_top = false
titlebar = true
process_priority = false

[Visual Studio Code]
apply_order = Titlebar,Pos,Size,Aot
position = 1706,-1
size = 2560,1440
always_on_top = false
titlebar = true
process_priority = false

[Discord]
apply_order = Titlebar,Pos,Size,Aot
position = 4264,-1
size = 856,1394
always_on_top = false
titlebar = true
process_priority = false
```

## Notes:
- Window titles in config are matched partially and case-insensitively against open windows.

## Multi-monitor use

### This application is made with ultrawide monitors in mind (32:9 / 21:9) and will work best on a single monitor setup.
### It will apply the settings on the primary monitor only
