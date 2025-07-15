import time
import win32gui
import win32con
import pygetwindow as gw

# Local imports
from lib.utils import clean_window_title

class WindowManager:
    def __init__(self):
        self.managed_windows = []
        self.topmost_windows = set()
        self._window_states = {}
        self.ignored_windows = [
            "window manager",
            "program manager",
            "windows input experience",
            "microsoft text input application",
            "settings",
            "windows shell experience host"
        ]


    def apply_window_config(self, config, hwnd, window_name=None):
        if self.is_valid_window(hwnd):
            try:
                if not config:
                    return False
                
                self.add_managed_window(hwnd)
                window = gw.Window(hwnd)
                if window.isMinimized:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)

                if isinstance(config, dict):
                    # Get configuration values
                    has_titlebar = config.get('has_titlebar', True)
                    if 'position' in config and config['position']:
                        position = eval(config['position']) if isinstance(config['position'], str) else config['position']
                    if 'size' in config and config['size']:
                        size = eval(config['size']) if isinstance(config['size'], str) else config['size']
                    if 'always_on_top' in config:
                        always_on_top = config['always_on_top']

                    # Apply settings
                    apply_funcs = {
                        'aot': (self.set_always_on_top, always_on_top),
                        'titlebar': (self.keep_titlebar, has_titlebar),
                        'pos': (self.set_window_position, position[0], position[1]),
                        'size': (self.set_window_size, size[0], size[1])
                    }

                    default_apply_order = [
                        'titlebar',
                        'pos',
                        'size',
                        'aot'
                        ]

                    if window_name == 'Diablo IV':
                        apply_order = ['titlebar', 'pos', 'size', 'aot'] # Example override for specific game
                    else:
                        apply_order = default_apply_order

                    for key in apply_order:
                        args = apply_funcs[key][1:]
                        if args:
                            apply_funcs[key][0](hwnd, *args)
                        time.sleep(0.1)

                return True

            except Exception as e:
                print(f"Error applying window config: {e}")
                return False

# Apply window config helper functions

    def set_always_on_top(self, hwnd, enable):
        if self.is_valid_window(hwnd):
            try:
                flag = win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST
                win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0, 
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                                    win32con.SWP_NOOWNERZORDER)
                
                if enable and hwnd not in self.topmost_windows:
                    self.topmost_windows.add(hwnd)
                elif not enable and hwnd in self.topmost_windows:
                    self.topmost_windows.remove(hwnd)
                    
            except Exception as e:
                print(f"Error setting always on top for hwnd: {hwnd}, enable: {enable}, error: {e}")

    def set_window_position(self, hwnd, x, y):
        if self.is_valid_window(hwnd):
            try:
                rect = win32gui.GetWindowRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
                
                win32gui.SetWindowPos(hwnd, 0, x, y, width, height,
                                    win32con.SWP_NOZORDER | win32con.SWP_NOSIZE)
                return True
            except Exception as e:
                print(f"Error setting window position for {hwnd}: {e}")
                return False

    def set_window_size(self, hwnd, width, height):
        if self.is_valid_window(hwnd):
            try:
                rect = win32gui.GetWindowRect(hwnd)
                x, y = rect[0], rect[1]
                
                win32gui.SetWindowPos(hwnd, 0, x, y, width, height,
                                    win32con.SWP_NOZORDER | win32con.SWP_NOMOVE)
                return True
            except Exception as e:
                print(f"Error setting window size for {hwnd}: {e}")
                return False

    def keep_titlebar(self, hwnd, restore=False):
        if restore:
            return self.restore_window_frame(hwnd)
        if self.is_valid_window(hwnd):
            try:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                style &= ~(win32con.WS_CAPTION | win32con.WS_BORDER | win32con.WS_THICKFRAME)
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                                    win32con.SWP_FRAMECHANGED)
                return True
            except Exception as e:
                print(f"Error making window borderless for hwnd: {hwnd}, error: {e}")
                return False

    def add_managed_window(self, hwnd):
        try:
            if hwnd not in self.managed_windows:
                self.managed_windows.append(hwnd)
                # Store initial window state
                self._window_states[hwnd] = self.get_window_metrics(hwnd)
        except Exception as e:
            print(f"Error adding managed window {hwnd}: {e}")

    def remove_managed_window(self, hwnd):
        try:
            if hwnd in self.managed_windows:
                if hwnd in self._window_states:
                    original_state = self._window_states[hwnd]
                    self.set_window_position(hwnd, 
                                          original_state['position'][0],
                                          original_state['position'][1])
                    self.set_window_size(hwnd, 
                                       original_state['size'][0],
                                       original_state['size'][1])
                    
                    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, 
                                         original_state['style'])
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, 
                                         original_state['exstyle'])
                    
                    del self._window_states[hwnd]
                
                self.managed_windows.remove(hwnd)
                if hwnd in self.topmost_windows:
                    self.topmost_windows.remove(hwnd)

        except Exception as e:
            print(f"Error removing managed window {hwnd}: {e}")

    def reset_all_windows(self):
        windows_to_reset = self.managed_windows.copy()
        for hwnd in windows_to_reset:
            self.set_always_on_top(hwnd, enable=False)
            self.restore_window_frame(hwnd)
            self.remove_managed_window(hwnd)


# Other functions

    def get_always_on_top_status(self):
        count = 0
        if len(self.topmost_windows) == 0:
            return "AOT: None"
        else:
            for hwnd in self.topmost_windows:
                if (win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST) != 0:
                    count += 1

        return f"AOT: {count} window{'s' if count > 1 else ''}"

    def get_window_title(self, hwnd):
        try:
            return win32gui.GetWindowText(hwnd)
        except Exception as e:
            print(f"Error getting window title for {hwnd}: {e}")
            return ""

    def get_window_metrics(self, hwnd):
        try:
            rect = win32gui.GetWindowRect(hwnd)
            return {
                'position': (rect[0], rect[1]),
                'size': (rect[2] - rect[0], rect[3] - rect[1]),
                'style': win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE),
                'exstyle': win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            }
        except Exception as e:
            print(f"Error getting window metrics: {e}")
            return None

    def restore_window_frame(self, hwnd):
        if self.is_valid_window(hwnd):
            try:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                style |= (win32con.WS_CAPTION | win32con.WS_BORDER | win32con.WS_THICKFRAME)
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                                    win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW)
                return True
            except Exception as e:
                print(f"Error restoring window frame for hwnd: {hwnd}, error: {e}")
                return False

    def find_matching_windows(self, config):
        matching_windows = []
        missing_windows = []
        
        try:
            if not config or len(config.sections()) == 0:
                return matching_windows, missing_windows

            all_titles = gw.getAllTitles()
            
            for section in config.sections():
                cleaned_section = clean_window_title(section, sanitize=True)
                window_exists = False
                
                for title in all_titles:
                    if not title:
                        continue
                    cleaned_title = clean_window_title(title, sanitize=True)
                    if cleaned_section in cleaned_title:
                        window = gw.getWindowsWithTitle(title)[0]
                        matching_windows.append({
                            'config_name': section,
                            'window': window,
                            'hwnd': window._hWnd
                        })
                        window_exists = True
                        break
                        
                if not window_exists:
                    missing_windows.append(section)
                    
            return matching_windows, missing_windows
        except Exception as e:
            print(f"Error finding matching windows: {e}")
            return [], []

    def toggle_always_on_top(self, hwnd):
        try:
            if hwnd in self.topmost_windows:
                is_topmost = (win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST) != 0
                flag = win32con.HWND_TOPMOST if not is_topmost else win32con.HWND_NOTOPMOST
                win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOOWNERZORDER)
            
        except Exception as e:
            print(f"Error toggling always-on-top: {e}")
            return False

    def get_all_window_titles(self):
        try:
            def enum_window_callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title and not title.lower() in self.ignored_windows:
                        windows.append(title)
                return True

            windows = []
            win32gui.EnumWindows(enum_window_callback, windows)
            return sorted(windows)
        except Exception as e:
            print(f"Error getting window titles: {e}")
            return []

    def is_valid_window(self, hwnd):
        try:
            return win32gui.IsWindow(hwnd) != 0
        except Exception:
            return False

