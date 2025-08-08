import os
import ctypes
import webbrowser
import pywinstyles
import tkinter as tk
from typing import List
import customtkinter as ctk
from PIL import Image, ImageTk
from fractions import Fraction

# Local imports
from utils import WindowInfo, clean_window_title, invert_hex_color
from constants import UIConstants, Colors, Messages, Fonts, LayoutDefaults
from callbacks import CallbackManager

class CtkGuiManager(ctk.CTk):
    def __init__(self, compact=0, is_admin=False, use_images=0, snap=0, details=0, config_manager=None, asset_manager=None):
        super().__init__()
        self.asset_manager = asset_manager
        self.callback_manager = CallbackManager(self, config_manager, self.asset_manager)
        self.callbacks = self.callback_manager.callbacks
        self.assets_dir = self.callback_manager.assets_dir

        self.config_manager = config_manager

        self.compact_mode = compact
        self.style_dark = ctk.IntVar(value=1)
        self.style = "dark"
        self.ctk_theme_bg = None
        self.config_active = False
        self.applied_config = None
        
        self.colors = Colors()

        self.snap = ctk.IntVar(value=snap)
        self.reapply = ctk.IntVar()
        self.details = ctk.IntVar(value=details)
        self.use_images = ctk.IntVar(value=use_images)
        
        self.application_name = "Ultrawide Window Positioner"
        self.title(self.application_name)

        self.res_x = self.winfo_screenwidth()
        self.res_y = self.winfo_screenheight()

        if snap == 0:
            self.pos_x = (self.res_x // 2) - ((UIConstants.WINDOW_WIDTH if not self.compact_mode else UIConstants.COMPACT_WIDTH) // 2)
        elif snap == 1:
            self.pos_x = -7
        elif snap == 2:
            self.pos_x = self.res_x - (UIConstants.WINDOW_WIDTH if not self.compact_mode else UIConstants.COMPACT_WIDTH) - 7

        self.pos_y = (self.res_y // 2) - ((UIConstants.WINDOW_HEIGHT if not self.compact_mode else UIConstants.COMPACT_HEIGHT) // 2)
        self.geometry(f"{UIConstants.WINDOW_WIDTH}x{UIConstants.WINDOW_HEIGHT}+{self.pos_x}+{self.pos_y}")
        self.minsize(UIConstants.WINDOW_MIN_WIDTH, UIConstants.WINDOW_MIN_HEIGHT)
        
        self.is_admin = is_admin
        self.client_info_missing = self.asset_manager.client_info_missing

        self.default_font = Fonts.TEXT_NORMAL

        self.canvas = None
        self.buttons_container = None
        self.managed_label = None
        self.managed_text = None
        self.ratio_label = None
        self.hovering_layout = False
        self.layout_frame_create_config = None
        self.layout_number = 0

        self.auto_align_layouts = self.config_manager.load_or_create_layouts(self.config_manager.layout_config_file)

        self.buttons = []
        
        self.setup_styles(toggle=False)
        self.scale_gui()
        self.create_layout()
        self.manage_image_buttons()
        self.after(100, self.apply_titlebar_style)

    def setup_styles(self, toggle=True):
        if self.style_dark.get():
            self.style = "dark"
            self.bg_color = 1
        else:
            self.style = "light"
            self.bg_color = 0

        if toggle:
            self.invert_colors()
            self.main_frame.destroy()
            self.create_layout()
            self.manage_image_buttons()

            self.config_files, self.config_names = self.config_manager.list_config_files()
            if self.config_files and self.config_names:
                self.combo_box.configure(values=self.config_names)
                self.combo_box.set(self.config_names[0])
                self.callbacks["config_selected"](self.combo_box)
            else:
                self.combo_box.configure(values=[])
                self.combo_box.set('')
                if self.layout_frame:
                    self.layout_frame.pack_forget()

        ctk.set_appearance_mode(self.style)
        self.apply_titlebar_style()

    def invert_colors(self):
        for attr in dir(self.colors):
            if attr.isupper():
                value = getattr(self.colors, attr)
                if isinstance(value, str):
                    setattr(self.colors, attr, invert_hex_color(value))

    def apply_titlebar_style(self):
        try:
            window = ctypes.windll.user32.GetActiveWindow()
            pywinstyles.apply_style(window, self.style)
            pywinstyles.change_header_color(window, color=self.colors.TITLE_BAR_COLOR)
            pywinstyles.change_title_color(window, color=self.colors.TITLE_TEXT_COLOR)
        except Exception as e:
            print(f"Error applying dark mode to titlebar: {e}")

    def create_button(self,
            parent,
            text,
            command,
            width=UIConstants.BUTTON_WIDTH,
            height=UIConstants.BUTTON_HEIGHT,
            fg_color=None,
            hover_color=None,
            text_color=None,
            state=ctk.NORMAL,
            border_width=2
            ):
        fg_color = fg_color or self.colors.BUTTON_NORMAL
        hover_color = hover_color or self.colors.BUTTON_HOVER
        text_color = text_color or self.colors.TEXT_NORMAL
        button = ctk.CTkButton(
            master=parent,
            text=text,
            command=command,
            width=width,
            height=height,
            state=state,
            fg_color=fg_color,
            hover_color=self.colors.BUTTON_HOVER,
            text_color=self.colors.TEXT_NORMAL,
            border_width=border_width
        )
        if button_list == None:
            button_list = self.buttons
        button_list.append(button)
        return button

    def create_layout(self):

        # Set up frames
        self.main_frame = ctk.CTkFrame(self, fg_color=self.ctk_theme_bg) # Main frame
        self.main_frame.pack(fill=ctk.BOTH, expand=True)

        r, g, b = self.main_frame.winfo_rgb(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"][self.bg_color])
        self.ctk_theme_bg = f'#{r//256:02x}{g//256:02x}{b//256:02x}'

        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color=self.ctk_theme_bg) # Header frame
        self.managed_frame = ctk.CTkFrame(self.main_frame, fg_color=self.ctk_theme_bg) # Managed windows
        self.combo_frame = ctk.CTkFrame(self.main_frame, fg_color=self.ctk_theme_bg) # Config selection menu
        self.layout_container = ctk.CTkFrame(self.main_frame, fg_color=self.ctk_theme_bg) # Layout frame
        self.layout_frame = None  # Will hold the ScreenLayoutFrame
        self.status_frame = ctk.CTkFrame(self.main_frame, fg_color=self.ctk_theme_bg)  # Status frame
        self.button_frame = ctk.CTkFrame(self.main_frame, fg_color=self.ctk_theme_bg) # Buttons main frame
        self.buttons_1_container = ctk.CTkFrame(self.button_frame, fg_color=self.ctk_theme_bg) # First row of buttons
        self.buttons_2_container = ctk.CTkFrame(self.button_frame, fg_color=self.ctk_theme_bg) # Second row of buttons
        self.aot_container = ctk.CTkFrame(self.button_frame, fg_color=self.ctk_theme_bg) # AOT container
        self.images_frame = ctk.CTkFrame(self.button_frame, fg_color=self.ctk_theme_bg) # Images frame

        # Pack frames in the correct order
        self.header_frame.pack(side=ctk.TOP, fill=ctk.BOTH)
        self.managed_frame.pack(side=ctk.TOP, fill=ctk.BOTH)
        self.managed_frame.pack_forget()  # Hide it initially
        self.combo_frame.pack(side=ctk.TOP, fill=ctk.BOTH)
        self.layout_container.pack(side=ctk.TOP, fill=ctk.BOTH, expand=True)
        self.status_frame.pack(side=ctk.TOP, fill=ctk.BOTH)
        self.button_frame.pack(side=ctk.TOP, fill=ctk.BOTH)
        self.buttons_1_container.pack(side=ctk.TOP, fill=ctk.X)
        self.buttons_2_container.pack(side=ctk.TOP, fill=ctk.X)
        self.aot_container.pack(side=ctk.TOP, fill=ctk.BOTH)
        self.images_frame.pack(side=ctk.TOP, fill=ctk.BOTH)

        # Screen resolution label
        self.resolution_label = ctk.CTkLabel(self.header_frame, text=f"{self.res_x} x {self.res_y}")
        self.resolution_label.pack(side=ctk.LEFT, fill=ctk.X, padx=10)

        # User / Admin mode label
        app_mode = "Admin" if self.is_admin else "User"
        self.admin_label = ctk.CTkLabel(self.header_frame, text=f"{app_mode} mode", text_color=self.colors.ADMIN_ENABLED if self.is_admin else self.colors.TEXT_NORMAL)
        self.admin_label.pack(side=ctk.RIGHT, fill=ctk.X, padx=5)

        self.combo_box = ctk.CTkComboBox(self.combo_frame, width=300, command=lambda _: self.callbacks["config_selected"](self.combo_box), state="readonly")
        self.combo_box.pack(side=ctk.LEFT, padx=5, pady=5)
        self.combo_box.bind("<MouseWheel>", self.on_mousewheel)

        self.admin_button = self.create_button(
            self.combo_frame,
            command=self.callbacks.get("restart_as_admin"),
            text="Restart as Admin" if not self.is_admin else "Admin mode",
            state=ctk.DISABLED if self.is_admin else ctk.NORMAL,
            fg_color=self.colors.BUTTON_ACTIVE if self.is_admin else self.colors.BUTTON_NORMAL,
            text_color=self.colors.TEXT_NORMAL,
            height=UIConstants.BUTTON_HEIGHT/1.5,
            )

        self.theme_switch = ctk.CTkSwitch(self.combo_frame, text="light / dark", command=self.setup_styles, variable=self.style_dark, progress_color="black", fg_color="white")
        self.buttons.append(self.theme_switch)

        # Info label
        self.info_label = ctk.CTkLabel(self.status_frame, text=f"")

        # Auto re-apply switch
        self.auto_apply_switch = ctk.CTkSwitch(self.images_frame, text="Auto re-apply", variable=self.reapply, command=self.callbacks.get("auto_reapply"), progress_color=self.colors.TEXT_ALWAYS_ON_TOP, height=UIConstants.BUTTON_HEIGHT/2)
        self.auto_apply_switch.pack(side=ctk.LEFT, padx=10, pady=5)

        self.apply_config_button = self.create_button(self.buttons_1_container, text="Apply config", command=self.callbacks.get("apply_config"))
        self.create_config_button = self.create_button(self.buttons_1_container, text="Create config", command=self.callbacks.get("create_config"))
        self.delete_config_button = self.create_button(self.buttons_1_container, text="Delete config", command=self.callbacks.get("delete_config"))
        self.config_folder_button = self.create_button(self.buttons_1_container, text="Open config folder", command=self.callbacks.get("open_config_folder"))
        self.toggle_compact_button = self.create_button(self.buttons_2_container, text="Toggle compact", command=self.callbacks.get("toggle_compact"))
        self.screenshot_button = self.create_button(self.buttons_2_container, text="Take screenshots", command=self.callbacks.get("screenshot"))
        self.aot_button = self.create_button(self.aot_container, text="Toggle AOT", command=self.callbacks.get("toggle_AOT"), state=ctk.DISABLED, height=UIConstants.BUTTON_HEIGHT/1.5)
        self.aot_label = ctk.CTkLabel(self.aot_container, text=Messages.ALWAYS_ON_TOP_DISABLED, width=UIConstants.BUTTON_WIDTH, anchor='w')

        self.setup_buttons()
        self.format_apply_reset_button()

    def setup_buttons(self):
        self.apply_config_button = self.create_button(parent=self.buttons_1_container, text="Apply config", command=self.callbacks.get("apply_config"))
        self.create_config_button = self.create_button(parent=self.buttons_1_container, text="Create config", command=self.callbacks.get("create_config"))
        self.delete_config_button = self.create_button(parent=self.buttons_1_container, text="Delete config", command=self.callbacks.get("delete_config"))
        self.config_folder_button = self.create_button(parent=self.buttons_1_container, text="Open config folder", command=self.callbacks.get("open_config_folder"))
        self.toggle_compact_button = self.create_button(parent=self.buttons_2_container, text="Toggle compact", command=self.callbacks.get("toggle_compact"))
        self.screenshot_button = self.create_button(parent=self.buttons_2_container, text="Take screenshots", command=self.callbacks.get("screenshot"))
        self.aot_button = self.create_button(parent=self.aot_frame, text="Toggle AOT", command=self.callbacks.get("toggle_AOT"), state=ctk.DISABLED)

        self.admin_button = self.create_button(
            parent=self.combo_frame,
            command=self.callbacks.get("restart_as_admin"),
            text="Restart as Admin" if not self.is_admin else "Admin mode",
            state=ctk.DISABLED if self.is_admin else ctk.NORMAL,
            fg_color=Colors.BUTTON_ACTIVE if self.is_admin else Colors.BUTTON_NORMAL,
            text_color=Colors.TEXT_NORMAL,
            )

        self.admin_button.pack(side=ctk.RIGHT, padx=5)
        self.theme_switch.pack_forget()
        self.theme_switch.pack(side=ctk.RIGHT, padx=5)

        # First line of buttons
        self.apply_config_button.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=5, pady=5)
        self.create_config_button.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=5, pady=5)
        self.delete_config_button.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=5, pady=5)
        self.config_folder_button.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=5, pady=5)

        # Second line of buttons
        self.toggle_compact_button.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=5, pady=5)
        self.screenshot_button.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=5, pady=5)
        
        self.aot_button.pack(side=ctk.LEFT, fill=ctk.X, padx=5, pady=5)

        # Info label
        self.info_label.pack(side=ctk.LEFT, fill=ctk.X, padx=10)

        # AOT status label
        self.aot_label.pack(side=ctk.LEFT, fill=ctk.X, padx=5, pady=5)

    def manage_image_buttons(self, destroy=False):
        if destroy:
            self.snap_on_open_label.destroy()
            self.no_snap_on_open.destroy()
            self.snap_left_on_open.destroy()
            self.snap_right_on_open.destroy()
            self.image_download_button.destroy()
            self.image_folder_button.destroy()
            self.details_switch.destroy()
            self.toggle_images_switch.destroy()
        else:
            # Window details switch
            self.details_switch = ctk.CTkSwitch(self.images_frame, text="Show window details", variable=self.details, command=self.callbacks.get("details"), progress_color=self.colors.TEXT_ALWAYS_ON_TOP)
            self.details_switch.pack(side=ctk.LEFT, padx=10, pady=5)

            # Snap on open buttons and label
            self.snap_right_on_open = ctk.CTkRadioButton(self.images_frame, text="Snap right", variable=self.snap, value=2, command=self.callbacks.get("snap"), width=5, fg_color=self.colors.TEXT_ALWAYS_ON_TOP)
            self.snap_right_on_open.pack(side=ctk.RIGHT, padx=(5, 10), pady=5)

            self.no_snap_on_open = ctk.CTkRadioButton(self.images_frame, text="Center", variable=self.snap, value=0, command=self.callbacks.get("snap"), width=5, fg_color=self.colors.TEXT_ALWAYS_ON_TOP)
            self.no_snap_on_open.pack(side=ctk.RIGHT, padx=5, pady=5)

            self.snap_left_on_open = ctk.CTkRadioButton(self.images_frame, text="Snap left", variable=self.snap, value=1, command=self.callbacks.get("snap"), width=5, fg_color=self.colors.TEXT_ALWAYS_ON_TOP)
            self.snap_left_on_open.pack(side=ctk.RIGHT, padx=5, pady=5)

            self.snap_on_open_label = ctk.CTkLabel(self.aot_container, text="Application position on open:", height=UIConstants.BUTTON_HEIGHT/2)
            self.snap_on_open_label.pack(side=ctk.RIGHT, fill=ctk.X, padx=50, pady=5)

            self.toggle_images_switch = ctk.CTkSwitch(self.images_frame, text="Images", variable=self.use_images, command=self.callbacks.get("toggle_images"), progress_color=self.colors.TEXT_ALWAYS_ON_TOP)
            self.toggle_images_switch.pack(side=ctk.LEFT, fill=ctk.X, padx=5)

            # Image download button
            self.image_download_button = self.create_button(self.buttons_2_container, text="Download images", command=self.callbacks.get("download_images"))
            if self.client_info_missing: self.image_download_button.configure(text="Client info missing", state=ctk.DISABLED)
            self.image_download_button.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=5, pady=5)

        # Image folder button
        self.image_folder_button = self.create_button(parent=self.buttons_2_container, text="Open image folder", command=self.callbacks.get("image_folder"))
        self.image_folder_button.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=5, pady=5)

    def setup_managed_text(self):
        if not hasattr(self, 'managed_frame') or not self.managed_frame.winfo_ismapped():
            self.managed_frame.pack(before=self.button_frame, side=ctk.TOP, fill=ctk.X)
        
        if not self.managed_label:
            self.managed_label = ctk.CTkLabel(self.managed_frame, text="Managed windows:")
            self.managed_label.pack(side=ctk.TOP, anchor=ctk.W)
        
        if not self.managed_text:
            self.managed_text = ctk.CTkTextbox(self.managed_frame, height=80)
            self.managed_text.pack(side=ctk.TOP, fill=ctk.X, expand=False)

    def update_managed_text(self, lines, aot_flags):
        self.managed_text.configure(state=ctk.NORMAL)
        self.managed_text.delete("1.0", ctk.END)

        for i, line in enumerate(lines):
            if aot_flags[i]:
                self.managed_text.insert(ctk.END, line + "\n", "aot")
            else:
                self.managed_text.insert(ctk.END, line + "\n")

        self.managed_text.tag_config("aot", foreground=self.colors.TEXT_ALWAYS_ON_TOP)
        self.managed_text.configure(state=ctk.DISABLED)

    def remove_managed_windows_frame(self):
        if self.managed_label:
            self.managed_label.destroy()
            self.managed_label = None
        if self.managed_text:
            self.managed_text.destroy()
            self.managed_text = None
        self.managed_frame.pack_forget()
    
    def on_mousewheel(self, event):
        values = self.combo_box.cget("values")
        if not values:
            return
        try:
            current_value = self.combo_box.get()
            current_index = values.index(current_value)
        except ValueError:
            current_index = 0
        if event.delta > 0:
            new_index = max(0, current_index - 1)
        else:
            new_index = min(len(values) - 1, current_index + 1)
        if new_index != current_index:
            self.combo_box.set(values[new_index])
            if "config_selected" in self.callbacks:
                self.callbacks["config_selected"](self.combo_box)

    def set_layout_frame(self, windows): 
        if self.layout_frame:
            self.layout_frame.destroy()

        self.layout_frame = ScreenLayoutFrame(self.layout_container, self.res_x, self.res_y, windows, assets_dir=self.assets_dir, use_images=self.use_images, style_dark=self.style_dark, window_details=self.details, ctk_bg=self.ctk_theme_bg)
        self.layout_frame.pack(side=ctk.TOP, fill=ctk.BOTH, expand=True)
        self.layout_frame.canvas.bind("<MouseWheel>", self.on_mousewheel)

    def scale_gui(self):
        if self.compact_mode:
            self.minsize(UIConstants.COMPACT_WIDTH, UIConstants.COMPACT_HEIGHT)
            self.geometry(f"{UIConstants.COMPACT_WIDTH}x1")
            self.update_idletasks()
            height = self.winfo_reqheight()
            self.geometry(f"{UIConstants.COMPACT_WIDTH}x{height}")
        else:
            self.minsize(UIConstants.WINDOW_MIN_WIDTH, UIConstants.WINDOW_MIN_HEIGHT)
            self.geometry(f"{UIConstants.WINDOW_WIDTH}x{UIConstants.WINDOW_HEIGHT}")

    def toggle_compact(self, startup=False):
        if not startup:
            if self.compact_mode == 0:
                self.compact_mode = 1
            else:
                self.compact_mode = 0

        compact_buttons = ['Apply config', 'Create config', 'Delete config', 'Toggle compact', 'Toggle AOT']

        self.buttons = [b for b in self.buttons if b.winfo_exists()]
        
        if self.compact_mode:
            if self.layout_container:
                self.layout_container.pack_forget()

            for button in self.buttons:
                if button.cget("text") in compact_buttons:
                    button.pack(side=ctk.TOP, fill=ctk.X, expand=False, padx=5)
                else:
                    button.pack_forget()

            self.theme_switch.pack_forget()
            self.aot_label.pack(side=ctk.TOP, padx=5, pady=5)
            self.manage_image_buttons(destroy=True)
            self.setup_managed_text()
        else:
            if self.layout_container:
                self.layout_container.pack(before=self.status_frame, side=ctk.TOP, fill=ctk.BOTH, expand=True)

            for button in self.buttons:
                if button.cget("text") in compact_buttons:
                    button.pack_forget()

            self.aot_label.pack_forget()
            
            self.remove_managed_windows_frame()
            self.manage_image_buttons(destroy=False)
            self.setup_styles()
        
        self.scale_gui()

    def format_apply_reset_button(self, selected_config_shortname=None, disable=None):
        if disable is not None:
            state = ctk.DISABLED if disable == 1 else ctk.NORMAL
            self.apply_config_button.configure(state=state)
            return

        if self.config_active:
            self.apply_config_button.configure(text="Reset config", fg_color=self.colors.BUTTON_ACTIVE, hover_color=self.colors.BUTTON_ACTIVE_HOVER)
            self.info_label.configure(text=f"Active config: {selected_config_shortname if selected_config_shortname else self.applied_config}")
            self.aot_button.configure(state=ctk.NORMAL)

        elif not self.config_active:
            self.apply_config_button.configure(text="Apply config", fg_color=self.colors.BUTTON_NORMAL)
            self.info_label.configure(text=f"")
            self.aot_button.configure(state=ctk.DISABLED)
            self.reapply.set(0)

    def create_config_ui(self, parent, window_titles, save_callback, settings_callback, refresh_callback):
        parent.attributes('-disabled', True)
        entry_font = ctk.CTkFont('Consolas 10')

        def on_close():
            parent.attributes('-disabled', False)
            config_win.destroy()

        def confirm_selection():
            selected = [title for title, var in switches.items() if var.get()]
            if not selected:
                tk.messagebox.showerror("Error", "No windows selected")
                return
            if len(selected) > UIConstants.MAX_WINDOWS:
                tk.messagebox.showerror("Error", f"Select up to {UIConstants.MAX_WINDOWS} windows only")
                return
            show_config_settings(selected)

        def validate_int_pair(value, default=(0,0)):
            try:
                x, y = map(int, value.split(','))
                return x, y
            except (ValueError, AttributeError):
                return default

        def show_config_settings(selected_windows):
            for widget in config_win.winfo_children():
                widget.destroy()

            settings_frames = []

            settings_frame = ctk.CTkFrame(config_win, fg_color=self.ctk_theme_bg)
            settings_frame.pack(fill='both', expand=True)

            sorted_windows = sorted(
                selected_windows,
                key=lambda title: int((settings_callback(title) or {}).get("position", "0,0").split(",")[0])
            )

            settings_vars = {}

            for row, title in enumerate(sorted_windows):
                settings_frames.append(ctk.CTkFrame(settings_frame, fg_color=self.ctk_theme_bg))
                settings_frames[row].pack(side='top', fill='x')

                values = settings_callback(title) or {}
                pos_var = ctk.StringVar(value=values.get("position", "0,0"))
                size_var = ctk.StringVar(value=values.get("size", "100,100"))
                aot_var = ctk.BooleanVar(value=values.get("always_on_top", "false") == "true")
                titlebar_var = ctk.BooleanVar(value=values.get("titlebar", "true") == "true")
                name_var = ctk.StringVar(value=clean_window_title(title, sanitize=True))

                settings_vars[title] = [pos_var, size_var, aot_var, titlebar_var, name_var]

                ctk.CTkEntry(settings_frames[row], textvariable=name_var, width=320, font=entry_font).pack(side='left', padx=5, pady=2, fill='x', expand=True)
                
                ctk.CTkLabel(settings_frames[row], text="Position (x,y):", font=entry_font).pack(side='left', padx=5, pady=2, expand=True, anchor='e')
                ctk.CTkEntry(settings_frames[row], textvariable=pos_var, width=80, font=entry_font).pack(side='left', padx=5, pady=2, fill='x', expand=True)
                
                ctk.CTkLabel(settings_frames[row], text="Size (w,h):", font=entry_font).pack(side='left', padx=5, pady=2, expand=True, anchor='e')
                ctk.CTkEntry(settings_frames[row], textvariable=size_var, width=80, font=entry_font).pack(side='left', padx=5, pady=2, fill='x', expand=True)

                ctk.CTkCheckBox(settings_frames[row], text="On Top", variable=aot_var, width=80, font=entry_font, fg_color=self.colors.TEXT_ALWAYS_ON_TOP).pack(side='left', padx=5, pady=2, fill='x', expand=True)
                ctk.CTkCheckBox(settings_frames[row], text="Titlebar", variable=titlebar_var, width=80, font=entry_font, fg_color=self.colors.TEXT_ALWAYS_ON_TOP).pack(side='left', padx=5, pady=2, fill='x', expand=True)

            layout_frame = ctk.CTkFrame(settings_frame, fg_color=self.ctk_theme_bg)
            layout_frame.pack(side='bottom', fill='both', expand=True)

            def update_layout_frame():
                windows = []
                try:
                    for title, vars_ in settings_vars.items():
                        pos, size, aot, titlebar, name_var = vars_
                        name = name_var.get().strip() or ''
                        pos_x, pos_y = validate_int_pair(pos.get())
                        size_w, size_h = validate_int_pair(size.get())
                        windows.append(WindowInfo(name,
                                                pos_x, pos_y,
                                                size_w, size_h,
                                                always_on_top=aot.get() or False,
                                                exists=True,
                                                search_title='',
                                                source_url='',
                                                source=''
                                                ))
                    # Remove the old layout before redrawing
                    if self.layout_frame_create_config:
                        self.layout_frame_create_config.destroy()                    

                    self.layout_frame_create_config = ScreenLayoutFrame(layout_container_create_config,
                                                                self.winfo_screenwidth(),
                                                                self.winfo_screenheight(),
                                                                windows,
                                                                self.assets_dir,
                                                                style_dark=self.style_dark,
                                                                window_details=self.details,
                                                                use_images=self.use_images,
                                                                ctk_bg=self.ctk_theme_bg
                                                                )
                    self.layout_frame_create_config.pack(expand=True, fill='both')
                except Exception as e:
                    print(f"Failed to draw layout: {e}")

            def auto_position():
                screen_width = self.winfo_screenwidth()
                screen_height = self.winfo_screenheight()
                taskbar_height = UIConstants.TASKBAR_HEIGHT
                usable_height = screen_height - taskbar_height
                
                if not len(sorted_windows) in self.auto_align_layouts:
                    in_defaults = '' if len(sorted_windows) not in LayoutDefaults.DEFAULT_LAYOUTS else ' Try to reset to defaults.'
                    self.ratio_label.configure(text=f"No auto-alignment available for {len(sorted_windows)} windows. {in_defaults}")
                    return
                layout_configs = self.auto_align_layouts[len(sorted_windows)]
                layout_max = len(layout_configs) - 1

                side_text = ""

                # 4 windows
                if len(sorted_windows) == 4:
                    layout = layout_configs[self.layout_number]

                    for i, ((rel_x, rel_y), (rel_w, rel_h)) in enumerate(layout):
                        x = int(rel_x * screen_width)
                        y = int(rel_y * usable_height)
                        width = int(rel_w * screen_width)
                        height = int(rel_h * usable_height)

                        settings_vars[sorted_windows[i]][0].set(f"{x},{y}")
                        settings_vars[sorted_windows[i]][1].set(f"{width},{height}")

                    # Set name
                    config_name_var.set(f"{settings_vars[sorted_windows[1]][4].get()} grid {self.layout_number + 1}")

                # 3 windows
                elif len(sorted_windows) == 3:
                    numerator, denominator, weight_1 = layout_configs[self.layout_number]
                    weight_1 = Fraction(weight_1)
                    if not (0 <= weight_1 <= 1):
                        print(f"Invalid weight_1: {weight_1}. Resetting to 1/2.")
                        weight_1 = Fraction(1, 2)
                    weight_2 = 1 - weight_1
                    ratio = Fraction(numerator, denominator)

                    aux_width = screen_width - (screen_height * ratio)
                    left_width = aux_width * weight_1
                    center_width = screen_height * ratio
                    right_width = aux_width * weight_2

                    positions = [
                        (0, 0, left_width, usable_height),
                        (left_width, 0, center_width, screen_height),
                        (left_width + center_width, 0, right_width, usable_height)
                    ]

                    for (x, y, w, h), title in zip(positions, sorted_windows):
                        settings_vars[title][0].set(f'{int(x)},{int(y)}')
                        settings_vars[title][1].set(f'{int(w)},{int(h)}')
                    
                    settings_vars[sorted_windows[1]][2].set(True)  # Set middle window AOT
                    settings_vars[sorted_windows[1]][3].set(False)  # Set middle window titlebar off
                    
                    # Set name
                    config_name_var.set(f"{settings_vars[sorted_windows[1]][4].get()} ({numerator}-{denominator})(L_{weight_1.numerator}-{weight_1.denominator})(R_{weight_2.numerator}-{weight_2.denominator})")

                # 2 windows
                elif len(sorted_windows) == 2:
                    numerator, denominator, side = layout_configs[self.layout_number]
                    ratio = Fraction(numerator, denominator)

                    left_x = 0
                    aot = 1 if side in ('R', 'CL') else 0

                    if side == 'R':
                        side_text = "Right"
                        right_width = screen_height * ratio
                        left_width = screen_width - right_width
                    elif side == 'L':
                        side_text = "Left"
                        left_width = screen_height * ratio
                        right_width = screen_width - left_width
                    elif side == 'CL':
                        side_text = "Center Left"
                        right_width = screen_height * ratio
                        left_width = (screen_width / 2) - (right_width / 2)
                    elif side == 'CR':
                        side_text = "Center Right"
                        left_width = screen_height * ratio
                        right_width = (screen_width / 2) - (left_width / 2)
                        left_x = right_width
                    else:
                        print("Invalid position value")
                        left_width = right_width = 0

                    # Heights
                    left_height = right_height = screen_height if side in ('R', 'L') else usable_height
                    if side == 'CL': right_height = screen_height
                    if side == 'CR': left_height = screen_height

                    # Positions
                    right_x = left_x + left_width if side == 'CR' else left_width

                    # Apply settings
                    settings_vars[sorted_windows[0]][0].set(f'{int(left_x)},0')
                    settings_vars[sorted_windows[0]][1].set(f'{int(left_width)},{int(left_height)}')

                    settings_vars[sorted_windows[1]][0].set(f'{int(right_x)},0')
                    settings_vars[sorted_windows[1]][1].set(f'{int(right_width)},{int(right_height)}')

                    # AOT and titlebar
                    settings_vars[sorted_windows[aot]][2].set(True)
                    settings_vars[sorted_windows[aot]][3].set(False)
                    settings_vars[sorted_windows[not aot]][2].set(False)
                    settings_vars[sorted_windows[not aot]][3].set(True)

                    # Set name
                    config_name_var.set(f"{settings_vars[sorted_windows[aot]][4].get()} {side}_{numerator}-{denominator}")
                else:
                    numerator, denominator, side = layout_configs[self.layout_number]
                    ratio = Fraction(numerator, denominator)

                    x = 0
                    aot = 1

                    window_width = screen_height * ratio

                    if side == 'R':
                        side_text = "Right"
                        x = screen_width - window_width
                    elif side == 'L':
                        side_text = "Left"
                        x = 0
                    elif side == 'C':
                        side_text = "Center"
                        x = (screen_width / 2) - (window_width / 2)
                    else:
                        side_text = "Fullscreen"

                    for i, title in enumerate(sorted_windows):
                        settings_vars[title][0].set(f'{int(x)},0') # Position
                        settings_vars[title][1].set(f'{int(window_width)},{int(screen_height)}') # Size
                        settings_vars[title][2].set(True)   # Always on top
                        settings_vars[title][3].set(False) # Titlebar

                    # Set name
                    config_name_var.set(f"{settings_vars[sorted_windows[0]][4].get()} {side}_{numerator}-{denominator}")

                preset_label_text = f"Preset {self.layout_number + 1}/{layout_max + 1}\t"

                if len(sorted_windows) == 4:
                    self.ratio_label.configure(text=
                        f"{preset_label_text} "
                    )
                elif len(sorted_windows) == 3:
                    self.ratio_label.configure(text=
                        f"{preset_label_text}"
                        f"Aspect: {numerator}/{denominator} "
                        f"Left {weight_1.numerator}/{weight_1.denominator} Right {weight_2.numerator}/{weight_2.denominator}"
                    )
                elif len(sorted_windows) == 2:
                    self.ratio_label.configure(text=
                        f"{preset_label_text}"
                        f"{side_text:10} {numerator}/{denominator}"
                    )
                else:
                    self.ratio_label.configure(text=
                        f"{preset_label_text}"
                        f"{side_text:10} {numerator}/{denominator}"
                    )

                self.layout_number = 0 if self.layout_number >= layout_max else self.layout_number + 1
                update_layout_frame()

            def on_save():
                config_data = {}
                for title, vars_ in settings_vars.items():
                    pos, size, aot, titlebar, name_var = vars_
                    config_data[title] = {
                        'position': pos.get(),
                        'size': size.get(),
                        'always_on_top': aot.get(),
                        'titlebar': titlebar.get(),
                        'name': name_var.get().strip()
                    }
                name = clean_window_title(config_name_var.get(), titlecase=True)
                if not name:
                    ctk.messagebox.showerror("Error", "Config name is required")
                    return
                if save_callback(name, config_data):
                    if refresh_callback:
                        refresh_callback(name)
                    on_close()

            layout_container_create_config = ctk.CTkFrame(layout_frame, fg_color=self.ctk_theme_bg)
            layout_container_create_config.pack(side='top', fill='both', expand=True)
            
            self.create_button(settings_frame, text="Auto align", command=auto_position).pack(side='left', padx=5, pady=(10,0))
            self.create_button(settings_frame, text="Update drawing", command=update_layout_frame).pack(side='left', padx=5, pady=(10,0))

            self.ratio_label = ctk.CTkLabel(settings_frame, text="", font=entry_font)
            self.ratio_label.pack(side='left', padx=5, pady=(10,0))

            save_frame = ctk.CTkFrame(layout_frame, fg_color=self.ctk_theme_bg)
            save_frame.pack(side='top', fill='x', expand=False)

            config_name_var = ctk.StringVar()
            ctk.CTkLabel(save_frame, text="Config Name: ", font=entry_font).pack(side='left', padx=5, pady=5)
            ctk.CTkEntry(save_frame, textvariable=config_name_var, font=entry_font, width=400).pack(side='left', padx=5, pady=5, expand=True, fill='x')

            self.create_button(save_frame, text="Save Config", command=on_save).pack(side='left', padx=10, pady=10, fill='x', expand=True)

            update_layout_frame()

            config_win.geometry(f"{UIConstants.SETTINGS_WIDTH}x{UIConstants.SETTINGS_HEIGHT}")
            config_win.minsize(UIConstants.SETTINGS_WIDTH, UIConstants.SETTINGS_HEIGHT)

        config_win = ctk.CTkToplevel(parent)
        config_win.title("Create Config")

        parent.update_idletasks()
        x = parent.winfo_rootx()
        y = parent.winfo_rooty()
        config_win.geometry(f"+{x}+{y}")
        config_win.update_idletasks()
        config_win.minsize(config_win.winfo_width(), config_win.winfo_height())
        config_win.protocol("WM_DELETE_WINDOW", on_close)
        config_win.transient(parent)
        config_win.lift()
        config_win.focus_set()

        self.after(100, self.apply_titlebar_style)

        selection_frame = ctk.CTkFrame(config_win, fg_color=self.ctk_theme_bg)
        selection_frame.pack(fill='both', expand=True)

        ctk.CTkLabel(selection_frame, text="Select windows (max 4):", font=entry_font).pack()

        switches = {}
        for title in window_titles:
            clean_title = clean_window_title(title=title, sanitize=True)
            var = ctk.BooleanVar()

            cb = ctk.CTkCheckBox(
                selection_frame,
                text=clean_title,
                variable=var,
                font=entry_font,
                fg_color=self.colors.TEXT_ALWAYS_ON_TOP
            )

            cb.pack(anchor='w', padx=10, pady=5)
            switches[title] = var

        self.create_button(selection_frame, text="Confirm Selection", command=confirm_selection).pack(padx=10, pady=10)


class ScreenLayoutFrame(ctk.CTkFrame):
    def __init__(self, parent, screen_width, screen_height, windows: List[WindowInfo], assets_dir, ctk_bg, use_images=False, style_dark=True, window_details=True):
        super().__init__(parent)
        self.windows = windows
        self.style_dark = style_dark

        self.window_details = window_details.get()

        self.colors = Colors()
        if not self.style_dark:
            for attr in dir(self.colors):
                if attr.isupper():
                    value = getattr(self.colors, attr)
                    if isinstance(value, str):
                        setattr(self.colors, attr, invert_hex_color(value))
        
        self.assets_dir = assets_dir
        self.use_images = use_images.get()

        self.canvas = tk.Canvas(self, bg=ctk_bg)
        self.canvas.configure(highlightthickness=0, bd=0)
        self.canvas.pack(fill=ctk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_resize)

        self.screen_width = screen_width
        self.screen_height = screen_height
        self.taskbar_height = UIConstants.TASKBAR_HEIGHT

        self.line_height = 16

        self.compute_bounds()
    
    def redraw(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.draw_layout(width, height)

    def compute_bounds(self):
        if not self.windows:
            self.min_x, self.min_y = 0, 0
            self.max_x, self.max_y = self.screen_width, self.screen_height
            return

        xs = []
        ys = []
        xs_end = []
        ys_end = []

        for w in self.windows:
            xs.append(w.pos_x)
            ys.append(w.pos_y)
            xs_end.append(w.pos_x + w.width)
            ys_end.append(w.pos_y + w.height)

        self.min_x = min(xs)
        self.min_y = min(ys)
        self.max_x = max(xs_end)
        self.max_y = max(ys_end)

    def on_resize(self, event):
        self.draw_layout(event.width, event.height)

    def draw_text_with_bg(self, canvas, x, y, text, font, text_color, bg_color, anchor="nw", justify="left", line_height=None):
        line_height = line_height or self.line_height
        text_width = len(text) * 7
        # Draw background rectangle
        canvas.create_rectangle(
            x - 2,
            y,
            x + text_width + 2,
            y + line_height,
            fill=bg_color,
            outline=""
        )
        # Draw text
        return canvas.create_text(
            x,
            y,
            text=text,
            fill=text_color,
            font=font,
            anchor=anchor,
            justify=justify
        )


    def draw_layout(self, width, height):
        self.canvas.delete("all")

        padding = 5
        drawable_height = height - padding * 2
        drawable_width = width - padding * 2

        screen_ratio = self.screen_width / self.screen_height
        canvas_ratio = drawable_width / drawable_height

        if canvas_ratio > screen_ratio:
            scale = drawable_height / self.screen_height
            scaled_width = scale * self.screen_width
            x_offset = (drawable_width - scaled_width) / 2 + padding
            y_offset = padding
        else:
            scale = drawable_width / self.screen_width
            scaled_height = scale * self.screen_height
            x_offset = padding
            y_offset = (drawable_height - scaled_height) / 2 + padding

        frame_left = x_offset
        frame_top = y_offset
        frame_right = x_offset + scale * self.screen_width
        frame_bottom = y_offset + scale * self.screen_height
        frame_width = 5

        # Backgound
        self.canvas.create_rectangle(
            frame_left, frame_top, frame_right, frame_bottom,
            outline=self.colors.WINDOW_BORDER, width=frame_width
        )

        # Taskbar
        self.canvas.create_rectangle(
            frame_left,
            frame_bottom - UIConstants.TASKBAR_HEIGHT * scale,
            frame_right,
            frame_bottom,
            fill=self.colors.TASKBAR,
            outline=""
        )

        # Draw window frames
        for win in self.windows:
            x = x_offset + win.pos_x * scale
            y = y_offset + win.pos_y * scale
            w = win.width * scale
            h = win.height * scale

            border_color = self.colors.WINDOW_BORDER
            fill_color = Colors.WINDOW_ALWAYS_ON_TOP if win.always_on_top else self.colors.WINDOW_NORMAL

            # Draw window rectangle
            self.canvas.create_rectangle(
                x, y, x + w, y + h,
                fill=fill_color,
                outline=border_color,
                width=2 if not win.always_on_top else 3
                )

            # Load images
            if self.use_images:
                image_paths = [
                    os.path.join(self.assets_dir, f"{win.search_title.replace(' ', '_').replace(':', '')}.jpg"),
                    os.path.join(self.assets_dir, f"{win.search_title.replace(' ', '_').replace(':', '')}.png")
                ]
                for image_path in image_paths:
                    if os.path.exists(image_path):
                        try:
                            image = Image.open(image_path)
                            image = image.resize((int(w), int(h)), Image.LANCZOS)
                            tk_image = ImageTk.PhotoImage(image)
                            if not hasattr(self, 'tk_images'):
                                self.tk_images = {}
                            self.tk_images[win.search_title] = tk_image
                            self.canvas.create_image(x, y, image=tk_image, anchor=ctk.NW)

                            # Draw source link if present
                            if hasattr(win, "source_url") and win.source_url:
                                link_text = f"Image source {win.source}: {win.source_url}"
                                margin_bottom = 5 * scale
                                link_x = x + (w / 2) - (len(link_text) * 7 / 2)
                                link_y = y + h - margin_bottom - 10

                                link_id = self.draw_text_with_bg(self.canvas,
                                    link_x,
                                    link_y,
                                    link_text,
                                    Fonts.TEXT_NORMAL,
                                    "#1a73e8",
                                    self.colors.WINDOW_NORMAL,
                                )

                                def open_link(event, url=win.source_url):
                                    try:
                                        webbrowser.open_new(url)
                                    except Exception as e:
                                        print(f"Error opening link: {e}")

                                self.canvas.tag_bind(link_id, "<Button-1>", open_link)
                                self.canvas.tag_bind(link_id, "<Enter>", lambda e: self.canvas.config(cursor="hand2"))
                                self.canvas.tag_bind(link_id, "<Leave>", lambda e: self.canvas.config(cursor=""))

                            break
                        except Exception as e:
                            print(f"Error loading image: {e}")

            # Draw text
            info_lines = [
                win.search_title or win.name,
                f"Pos:  {win.pos_x}, {win.pos_y}" if self.window_details else "",
                f"Size: {win.width} x {win.height}" if self.window_details else "",
                f"AOT:  {'Yes' if win.always_on_top else 'No'}" if self.window_details else ""
            ]

            text_color = self.colors.TEXT_NORMAL if not win.always_on_top else Colors.TEXT_NORMAL
            padding_x = 4
            padding_y = 2

            max_lines = int((h - 2 * padding_y) // self.line_height)
            lines_to_draw = info_lines[:max_lines]

            for i, line in enumerate(lines_to_draw):
                if line != "":
                    font_to_use = Fonts.TEXT_BOLD if i == 0 else Fonts.TEXT_NORMAL
                    text_x = x + padding_x
                    text_y = y + padding_y + (i * self.line_height)
                    
                    self.draw_text_with_bg(self.canvas,
                        text_x,
                        text_y,
                        line,
                        font_to_use,
                        text_color,
                        self.colors.WINDOW_NORMAL if not win.always_on_top else Colors.WINDOW_ALWAYS_ON_TOP,                        
                    )

            # Missing text
            if not win.exists:
                missing_text = 'Window missing'
                missing_x = x + (w / 2) - (len(missing_text) * 7 / 2)
                missing_y = y + 2

                self.draw_text_with_bg(self.canvas,
                    missing_x,
                    missing_y,
                    missing_text,
                    Fonts.TEXT_BOLD,
                    self.colors.TEXT_ERROR if not win.always_on_top else Colors.TEXT_ERROR,
                    self.colors.WINDOW_NORMAL if not win.always_on_top else Colors.WINDOW_ALWAYS_ON_TOP,
                )
