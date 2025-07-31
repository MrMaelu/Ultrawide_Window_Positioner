import os
from typing import List
from fractions import Fraction
from PIL import Image, ImageTk
import pywinstyles
import ctypes

import customtkinter as ctk
import tkinter as tk

# Local imports
from lib.config_manager import ConfigManager
from lib.utils import WindowInfo, clean_window_title
from lib.constants import UIConstants, Colors, Messages, Fonts, LayoutDefaults, WindowStyles

class CtkGuiManager(ctk.CTk):
    def __init__(self, callbacks=None, compact=False, is_admin=False, use_images=False, snap=0, client_info_missing=True):
        super().__init__()
        self.compact_mode = compact
        
        self.snap = ctk.IntVar(value=snap)
        self.reapply = ctk.IntVar()

        self.title("Window Manager")
        self.configure(bg=Colors.BACKGROUND)

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
        
        self.is_admin = is_admin

        self.client_info_missing = client_info_missing

        self.default_font = Fonts.TEXT_NORMAL
        self.canvas = None
        self.buttons_container = None
        self.managed_label = None
        self.managed_text = None

        self.ratio_label = None

        self.hovering_layout = False

        self.callbacks = callbacks or {}

        self.layout_frame_create_config = None
        self.use_images = use_images
        self.assets_dir = None

        self.auto_align_layouts = ConfigManager.load_or_create_layouts()

        self.layout_number = 0

        self.setup_styles()
        self.create_layout()
        self.manage_image_buttons(destroy=False)
        self.after(100, self.apply_titlebar_style)

    def setup_styles(self):
        ctk.set_appearance_mode("dark")

    def apply_titlebar_style(self):
        try:
            window = ctypes.windll.user32.GetActiveWindow()
            pywinstyles.apply_style(window, 'dark')
            pywinstyles.change_header_color(window, color=WindowStyles.TITLE_BAR_COLOR)
            pywinstyles.change_title_color(window, color=WindowStyles.TITLE_TEXT_COLOR)
        except Exception as e:
            print(f"Error applying dark mode to titlebar: {e}")

    def create_button(self, parent, text, command):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=UIConstants.BUTTON_WIDTH,
            state=ctk.NORMAL,
            fg_color=Colors.BUTTON_NORMAL,
            hover_color=Colors.BUTTON_HOVER,
            border_width=1
        )

    def create_layout(self):
        # Main frame
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill=ctk.BOTH, expand=True)

        # Header frame
        header_frame = ctk.CTkFrame(self.main_frame)
        header_frame.pack(side=ctk.TOP, fill=ctk.X)

        # Managed windows
        self.managed_frame = ctk.CTkFrame(self.main_frame)
        self.managed_frame.pack(side=ctk.TOP, fill=ctk.X)  # Pack here to fix order
        self.managed_frame.pack_forget()  # Hide it initially

        # Screen resolution label
        self.resolution_label = ctk.CTkLabel(header_frame, text=f"{self.res_x} x {self.res_y}")
        self.resolution_label.pack(side=ctk.LEFT, fill=ctk.X)

        # User / Admin mode label
        app_mode = "Admin" if self.is_admin else "User"
        self.admin_label = ctk.CTkLabel(header_frame, text=f"{app_mode} mode")
        self.admin_label.pack(side=ctk.RIGHT, fill=ctk.X)
        
        # Config selection menu
        combo_frame = header_frame = ctk.CTkFrame(self.main_frame)
        combo_frame.pack(side=ctk.TOP, fill=ctk.X)
        
        self.combo_box = ctk.CTkComboBox(combo_frame, width=300)
        self.combo_box.pack(side=ctk.LEFT)
        self.combo_box.bind("<<ComboboxSelected>>", lambda e: self.callbacks["config_selected"](e))
        self.combo_box.bind("<MouseWheel>", self.on_mousewheel)

        # Layout frame placeholder
        self.layout_container = ctk.CTkFrame(self.main_frame)
        self.layout_container.pack(side=ctk.TOP, fill=ctk.BOTH, expand=True)
        self.layout_frame = None  # Will hold the ScreenLayoutFrame

        # Info label
        self.info_label = ctk.CTkLabel(self.layout_container, text=f"")
        self.info_label.pack(side=ctk.BOTTOM, fill=ctk.X)

        # Button section
        self.button_frame = ctk.CTkFrame(self.main_frame)
        self.button_frame.pack(side=ctk.TOP, fill=ctk.X)

        # Main buttons frame
        main_buttons = ctk.CTkFrame(self.button_frame)
        main_buttons.pack(side=ctk.TOP, fill=ctk.X)
        
        # Buttons
        buttons_1 = [
            ("Apply config", self.callbacks.get("apply_config")),
            ("Create config", self.callbacks.get("create_config")),
            ("Delete config", self.callbacks.get("delete_config")),
            ("Open config folder", self.callbacks.get("open_config_folder")),
        ]
        
        buttons_2 = [
            ("Toggle images", self.callbacks.get("toggle_images")),
            ("Toggle compact", self.callbacks.get("toggle_compact") or self.toggle_compact),
            ("Take screenshots", self.callbacks.get("screenshot")),
            ("Restart as Admin", self.callbacks.get("restart_as_admin")),
        ]

        # First line of buttons
        self.buttons_1_container = ctk.CTkFrame(main_buttons)
        self.buttons_1_container.pack(side=ctk.TOP, fill=ctk.X, expand=True, anchor=ctk.CENTER)
        total_buttons_1_width = len(buttons_1) * 100
        self.buttons_1_container.configure(width=total_buttons_1_width)

        # Second line of buttons
        self.buttons_2_container = ctk.CTkFrame(main_buttons)
        self.buttons_2_container.pack(side=ctk.TOP, fill=ctk.X, expand=True, anchor=ctk.CENTER)
        total_buttons_2_width = len(buttons_2) * 100
        self.buttons_2_container.configure(width=total_buttons_2_width)

        for name, command in buttons_1:
            btn = self.create_button(self.buttons_1_container, text=name, command=command)
            btn.pack(side=ctk.LEFT, fill=ctk.X, expand=False, padx=5, pady=5)

        for name, command in buttons_2:
            btn = self.create_button(self.buttons_2_container, text=name, command=command)
            btn.pack(side=ctk.LEFT, fill=ctk.X, expand=False, padx=5, pady=5)
            if name == "Toggle images" and self.use_images: btn.configure(text="Toggle images", fg_color=Colors.BUTTON_ACTIVE, hover_color=Colors.BUTTON_ACTIVE_HOVER)
            if name == "Restart as Admin" and self.is_admin: btn.configure(text="Running in admin mode", state=ctk.DISABLED, fg_color=Colors.WINDOW_ALWAYS_ON_TOP)

        # AOT container
        self.aot_container = ctk.CTkFrame(self.button_frame)
        self.aot_container.pack(side=ctk.TOP, fill=ctk.X)
        self.aot_frame = ctk.CTkFrame(self.aot_container)
        self.aot_frame.pack(side=ctk.TOP, fill=ctk.X)

        self.aot_button = self.create_button(self.aot_frame, text="Toggle AOT", command=self.callbacks.get("toggle_AOT"))
        self.aot_button.pack(side=ctk.LEFT, fill=ctk.X, expand=False, padx=5, pady=5)

        # AOT status label
        self.aot_label = ctk.CTkLabel(self.aot_frame, text=Messages.ALWAYS_ON_TOP_DISABLED, width=UIConstants.BUTTON_WIDTH, anchor='w')
        self.aot_label.pack(side=ctk.LEFT, fill=ctk.X, expand=False, padx=5, pady=5)

        # Images frame
        self.images_frame = ctk.CTkFrame(self.aot_container)
        self.images_frame.pack(side=ctk.TOP, fill=ctk.X)

        # Auto re-apply checkbutton
        self.auto_apply_checkbutton = ctk.CTkCheckBox(self.images_frame, text="Auto re-apply", variable=self.reapply, command=self.callbacks.get("auto_reapply"))
        self.auto_apply_checkbutton.pack(side=ctk.LEFT, padx=5, pady=5)

    def manage_image_buttons(self, destroy=False):
        if destroy:
            self.snap_on_open_label.destroy()
            self.snap_left_on_open.destroy()
            self.snap_right_on_open.destroy()
            self.image_download_button.destroy()
            self.image_folder_button.destroy()
        else:
            # Snap on open buttons and label
            self.snap_right_on_open = ctk.CTkCheckBox(self.images_frame, text="Right", variable=self.snap, onvalue=2, offvalue=0, command=self.callbacks.get("snap"), width=5)
            self.snap_right_on_open.pack(side=ctk.RIGHT, padx=5, pady=5)

            self.snap_left_on_open = ctk.CTkCheckBox(self.images_frame, text="Left", variable=self.snap, onvalue=1, offvalue=0, command=self.callbacks.get("snap"), width=5)
            self.snap_left_on_open.pack(side=ctk.RIGHT, padx=5, pady=5)

            self.snap_on_open_label = ctk.CTkLabel(self.images_frame, text="Snap application on open:")
            self.snap_on_open_label.pack(side=ctk.RIGHT, fill=ctk.X, padx=5, pady=5)


            # Image download button
            self.image_download_button = self.create_button(self.aot_frame, text="Download images", command=self.callbacks.get("download_images"))
            if self.client_info_missing: self.image_download_button.configure(text="Client info missing", state=ctk.DISABLED)
            self.image_download_button.pack(side=ctk.LEFT, fill=ctk.X, expand=False, padx=5, pady=5)

            # Image folder button
            self.image_folder_button = self.create_button(self.aot_frame, text="Open image folder", command=self.callbacks.get("image_folder"))
            self.image_folder_button.pack(side=ctk.LEFT, fill=ctk.X, expand=False, padx=5, pady=5)

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

        self.managed_text.tag_config("aot", foreground=Colors.TEXT_ALWAYS_ON_TOP)
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
            # Optionally trigger the selection callback
            if "config_selected" in self.callbacks:
                self.callbacks["config_selected"](self.combo_box)

    def set_layout_frame(self, windows): 
        if self.layout_frame:
            self.layout_frame.destroy()

        self.layout_frame = ScreenLayoutFrame(self.layout_container, self.res_x, self.res_y, windows, assets_dir=self.assets_dir, use_images=self.use_images)
        self.layout_frame.pack(fill=ctk.BOTH, expand=True)
        self.layout_frame.canvas.bind("<MouseWheel>", self.on_mousewheel)

    def scale_gui(self):
        if self.compact_mode:
            self.geometry(f"{UIConstants.COMPACT_WIDTH}x1")
            self.update_idletasks()
            height = self.winfo_reqheight()
            self.geometry(f"{UIConstants.COMPACT_WIDTH}x{height}")
        else:
            self.geometry(f"{UIConstants.WINDOW_WIDTH}x{UIConstants.WINDOW_HEIGHT}")

    def toggle_compact(self, startup=False):
        if not startup: self.compact_mode = not self.compact_mode
        if self.compact_mode:
            if self.layout_container:
                self.layout_container.pack_forget()
            
            buttons = ['Apply config', 'Create config', 'Delete config', 'Toggle compact']

            for child in self.buttons_1_container.winfo_children():
                if child.cget("text") in buttons:
                    child.pack(side=ctk.TOP, fill=ctk.X, expand=False, padx=5, pady=5)
                else:
                    child.pack_forget()
            
            for child in self.buttons_2_container.winfo_children():
                if child.cget("text") in buttons:
                    child.pack(side=ctk.TOP, fill=ctk.X, expand=False, padx=5, pady=5)
                else:
                    child.pack_forget()

            self.aot_button.pack(side=ctk.TOP, padx=5, pady=5)
            self.aot_label.pack(side=ctk.TOP, padx=5, pady=5)
            self.manage_image_buttons(destroy=True)

            self.setup_managed_text()
        else:
            if self.layout_container:
                self.layout_container.pack(before=self.button_frame, side=ctk.TOP, fill=ctk.BOTH, expand=True)

            for child in self.buttons_1_container.winfo_children():
                if isinstance(child, ctk.CTkButton):
                    child.pack_forget()
                    child.pack(side=ctk.LEFT, fill=ctk.X, expand=False, padx=5, pady=5)
            
            for child in self.buttons_2_container.winfo_children():
                if isinstance(child, ctk.CTkButton):
                    child.pack_forget()
                    child.pack(side=ctk.LEFT, fill=ctk.X, expand=False, padx=5, pady=5)

            self.aot_button.pack(side=ctk.LEFT, padx=5, pady=5)
            self.aot_label.pack(side=ctk.LEFT, padx=5, pady=5)
            
            self.remove_managed_windows_frame()

            self.manage_image_buttons(destroy=False)
        
        self.scale_gui()

    def create_config_ui(self, parent, window_titles, save_callback, settings_callback, refresh_callback):
        parent.attributes('-disabled', True)
        entry_font = ctk.CTkFont('Consolas 10')

        def on_close():
            parent.attributes('-disabled', False)
            config_win.destroy()

        def confirm_selection():
            selected = [title for title, var in switches.items() if var.get()]
            if not selected:
                ctk.messagebox.showerror("Error", "No windows selected")
                return
            if len(selected) > UIConstants.MAX_WINDOWS:
                ctk.messagebox.showerror("Error", f"Select up to {UIConstants.MAX_WINDOWS} windows only")
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

            settings_frame = ctk.CTkFrame(config_win)
            settings_frame.pack(fill='both', expand=True)

            sorted_windows = sorted(
                selected_windows,
                key=lambda title: int((settings_callback(title) or {}).get("position", "0,0").split(",")[0])
            )

            settings_vars = {}
            ctk.CTkLabel(settings_frame, text="Window name:", font=entry_font).grid(row=0, column=0, sticky='w', padx=5)
            ctk.CTkLabel(settings_frame, text="Position (x,y):", font=entry_font).grid(row=0, column=2)
            ctk.CTkLabel(settings_frame, text="Size (w,h):", font=entry_font).grid(row=0, column=3)
            ctk.CTkLabel(settings_frame, text="On Top", font=entry_font).grid(row=0, column=4, sticky='w')
            ctk.CTkLabel(settings_frame, text="Titlebar", font=entry_font).grid(row=0, column=5, sticky='w')
            for row, title in enumerate(sorted_windows):
                values = settings_callback(title) or {}
                pos_var = ctk.StringVar(value=values.get("position", "0,0"))
                size_var = ctk.StringVar(value=values.get("size", "100,100"))
                aot_var = ctk.BooleanVar(value=values.get("always_on_top", "false") == "true")
                titlebar_var = ctk.BooleanVar(value=values.get("titlebar", "true") == "true")
                name_var = ctk.StringVar(value=clean_window_title(title, sanitize=True))

                settings_vars[title] = [pos_var, size_var, aot_var, titlebar_var, name_var]

                ctk.CTkEntry(settings_frame, textvariable=name_var, width=320, font=entry_font).grid(row=row+1, column=0, sticky='w', padx=5, pady=1, columnspan=4)
                ctk.CTkEntry(settings_frame, textvariable=pos_var, width=80, font=entry_font).grid(row=row+1, column=2)
                ctk.CTkEntry(settings_frame, textvariable=size_var, width=80, font=entry_font).grid(row=row+1, column=3)
                ctk.CTkCheckBox(settings_frame, text="", variable=aot_var, width=80, font=entry_font).grid(row=row+1, column=4, sticky='w')
                ctk.CTkCheckBox(settings_frame, text="", variable=titlebar_var, width=80, font=entry_font).grid(row=row+1, column=5, sticky='w')

            row += 1
            ctk.CTkLabel(settings_frame, text="Config Name: ", font=entry_font).grid(row=row+1, column=2)
            config_name_var = ctk.StringVar()
            ctk.CTkEntry(settings_frame,
                textvariable=config_name_var,
                font=entry_font,
                ).grid(row=row+1, column=3, columnspan=3, sticky='ew', pady=(10,0))

            layout_container_create_config = ctk.CTkFrame(settings_frame)
            layout_container_create_config.grid(row=row+5, column=0, columnspan=7, sticky='nsew')
            settings_frame.rowconfigure(row+5, weight=10)
            for col in range(7):
                settings_frame.columnconfigure(col, weight=1)
            self.layout_frame_create_config = None

            def update_layout_frame():
                windows = []
                try:
                    for title, vars_ in settings_vars.items():
                        pos, size, aot, titlebar, name_var = vars_
                        name = name_var.get().strip() or ''
                        pos_x, pos_y = validate_int_pair(pos.get())
                        size_w, size_h = validate_int_pair(size.get())
                        always_on_top = aot.get() or False
                        window_exists = True
                        windows.append(WindowInfo(name,
                                                pos_x, pos_y,
                                                size_w, size_h,
                                                always_on_top,
                                                window_exists,
                                                search_title=''
                                                ))
                    # Remove the old layout before redrawing
                    if self.layout_frame_create_config:
                        self.layout_frame_create_config.destroy()                    

                    self.layout_frame_create_config = ScreenLayoutFrame(layout_container_create_config,
                                                                self.winfo_screenwidth(),
                                                                self.winfo_screenheight(),
                                                                windows,
                                                                self.assets_dir,
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

                preset_label_text = f"Preset {self.layout_number + 1}/{layout_max + 1}\t\t"

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

            def reset_presets():
                if ctk.messagebox.askyesno("Reset Presets", "Are you sure you want to reset all presets?"):
                    self.auto_align_layouts = ConfigManager.load_or_create_layouts(reset=True)

            update_layout_frame()
            self.create_button(settings_frame, text="Auto align", command=auto_position).grid(row=row+1, column=0, sticky='w', padx=5, pady=(10,0))
            self.create_button(settings_frame, text="Update drawing", command=update_layout_frame).grid(row=row+2, column=0, sticky='w', padx=5, pady=(5,0))
            self.create_button(settings_frame, text="Save Config", command=on_save).grid(row=row+2, column=3, columnspan=3, sticky='ew', padx=0, pady=(5,0))

            self.ratio_label = ctk.CTkLabel(settings_frame, text="", font=entry_font, width=UIConstants.BUTTON_WIDTH)
            self.ratio_label.grid(row=row+3, column=0, columnspan=6, sticky='w')

            config_win.geometry(f"{UIConstants.WINDOW_WIDTH}x{UIConstants.WINDOW_HEIGHT}")

        config_win = ctk.CTkToplevel(parent)
        config_win.title("Create Config")
        config_win.configure(bg=Colors.BACKGROUND)

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

        selection_frame = ctk.CTkFrame(config_win)
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
                font=entry_font
            )

            cb.pack(anchor='w', padx=10, pady=5)
            switches[title] = var

        self.create_button(selection_frame, text="Confirm Selection", command=confirm_selection).pack(padx=10, pady=10)


class ScreenLayoutFrame(ctk.CTkFrame):
    def __init__(self, parent, screen_width, screen_height, windows: List[WindowInfo], assets_dir, use_images=False):
        super().__init__(parent)
        self.windows = windows
        
        self.assets_dir = assets_dir
        self.use_images = use_images

        self.canvas = tk.Canvas(self, bg=Colors.BACKGROUND)
        self.canvas.configure(highlightthickness=0, bd=0)
        self.canvas.pack(fill=ctk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_resize)

        self.screen_width = screen_width
        self.screen_height = screen_height
        self.taskbar_height = UIConstants.TASKBAR_HEIGHT

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
            outline=Colors.WINDOW_BORDER, width=frame_width
        )

        # Taskbar
        self.canvas.create_rectangle(
            frame_left,
            frame_bottom - UIConstants.TASKBAR_HEIGHT * scale,
            frame_right,
            frame_bottom,
            fill=Colors.TASKBAR,
            outline=""
        )

        # Draw window frames
        for win in self.windows:
            x = x_offset + win.pos_x * scale
            y = y_offset + win.pos_y * scale
            w = win.width * scale
            h = win.height * scale

            border_color = Colors.WINDOW_BORDER
            fill_color = Colors.WINDOW_ALWAYS_ON_TOP if win.always_on_top else Colors.WINDOW_NORMAL
                
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
                            break
                        except Exception as e:
                            print(f"Error loading image: {e}")

            # Draw text
            info_lines = [
                win.search_title or win.name,
                f"Pos:  {win.pos_x}, {win.pos_y}",
                f"Size: {win.width} x {win.height}",
                f"AOT:  {'Yes' if win.always_on_top else 'No'}"
            ]

            text_color = Colors.TEXT_NORMAL
            padding_x = 5
            padding_y = 5
            line_height = 16

            max_lines = int((h - 2 * padding_y) // line_height)
            lines_to_draw = info_lines[:max_lines]

            for i, line in enumerate(lines_to_draw):
                font_to_use = Fonts.TEXT_BOLD if i == 0 else Fonts.TEXT_NORMAL
                text_x = x + padding_x
                text_y = y + padding_y + i * line_height
                
                # Text background
                text_width = len(line) * 7.2
                text_height = line_height - 2
                
                self.canvas.create_rectangle(
                    text_x - 2, 
                    text_y - 2, 
                    text_x + text_width, 
                    text_y + text_height, 
                    fill=Colors.WINDOW_NORMAL if not win.always_on_top else Colors.WINDOW_ALWAYS_ON_TOP, 
                    outline=""
                )
                
                # Draw the text on top of the background
                self.canvas.create_text(
                    text_x,
                    text_y,
                    text=line,
                    fill=text_color,
                    font=font_to_use,
                    anchor="nw",
                    justify=ctk.LEFT
                )

            # Missing text
            if not win.exists:
                margin_bottom = 5 * scale
                
                self.canvas.create_rectangle(
                    (x + w / 2) - 26, 
                    (y + h - margin_bottom) - 12, 
                    (x + w / 2) + 28,
                    (y + h - margin_bottom) - 26,
                    fill=Colors.WINDOW_NORMAL if not win.always_on_top else Colors.WINDOW_ALWAYS_ON_TOP, 
                    outline=""
                )
                
                self.canvas.create_text(
                    x + w / 2,
                    y + h - margin_bottom - 20,
                    text="MISSING",
                    fill=Colors.TEXT_ERROR,
                    font=Fonts.TEXT_BOLD,
                    justify=ctk.CENTER
                )
