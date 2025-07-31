class LayoutDefaults:
    # Format: (aspect_ratio_w, aspect_ratio_h, alignment) for 1 window
    ONE_WINDOW = [
        (32, 9, 'X'),
        (21, 9, 'C'),
        (16, 9, 'C'),
        (4, 3, 'C'),

        (21, 9, 'L'),
        (16, 9, 'L'),
        (4, 3, 'L'),

        (21, 9, 'R'),
        (16, 9, 'R'),
        (4, 3, 'R'),
    ]

    # Format: (aspect_ratio_w, alignment) for 2 windows
    TWO_WINDOWS = [
        (21, 9, 'R'),
        (16, 9, 'R'),
        (4, 3, 'R'),

        (21, 9, 'L'),
        (16, 9, 'L'),
        (4, 3, 'L'),

        (21, 9, 'CL'),
        (16, 9, 'CL'),
        (4, 3, 'CL'),

        (21, 9, 'CR'),
        (16, 9, 'CR'),
        (4, 3, 'CR'),
    ]

    # Format: (aspect_ratio_w, aspect_ratio_h, left_weight) for 3 windows
    THREE_WINDOWS = [
        (21, 9, '1/2'),
        (16, 9, '1/2'),
        (4, 3, '1/2'),

        (21, 9, '2/3'),
        (16, 9, '2/3'),
        (4, 3, '2/3'),

        (21, 9, '3/5'),
        (16, 9, '3/5'),
        (4, 3, '3/5'),

        (21, 9, '2/5'),
        (16, 9, '2/5'),
        (4, 3, '2/5'),
    ]

    FOUR_WINDOWS = [
        # layout 0: four equal horizontal windows
        [((0, 0), (1/4, 1)), ((1/4, 0), (1/4, 1)), ((1/2, 0), (1/4, 1)), ((3/4, 0), (1/4, 1))],
        
        # layout 1: 1 & 2 stacked left half, 3 & 4 side-by-side on right half
        [((0, 0), (1/2, 1/2)), ((0, 1/2), (1/2, 1/2)), ((1/2, 0), (1/4, 1)), ((3/4, 0), (1/4, 1))],

        # layout 2: 1 & 2 side-by-side left half, 3 & 4 stacked right half
        [((0, 0), (1/4, 1)), ((1/4, 0), (1/4, 1)), ((1/2, 0), (1/2, 1/2)), ((1/2, 1/2), (1/2, 1/2))],

        # layout 3: four equally sized 2x2 grid
        [((0, 0), (1/2, 1/2)), ((1/2, 0), (1/2, 1/2)), ((0, 1/2), (1/2, 1/2)), ((1/2, 1/2), (1/2, 1/2))],
    ]


    # Unified dictionary for simplified access
    DEFAULT_LAYOUTS = {
        1: ONE_WINDOW,
        2: TWO_WINDOWS,
        3: THREE_WINDOWS,
        4: FOUR_WINDOWS,
    }

class UIConstants:
    # Window dimensions
    WINDOW_WIDTH = 900
    WINDOW_HEIGHT = 500
    COMPACT_WIDTH = 180
    COMPACT_HEIGHT = 250
    BUTTON_WIDTH = 215
    COMPACT_BUTTON_WIDTH = 80
    CANVAS_HEIGHT = 240
    TASKBAR_HEIGHT = 48
    MAX_WINDOWS = 4
    WINDOW_TITLE_MAX_LENGTH = 24
    
    # UI element sizes
    MARGIN = (2,2,2,2)  # (top, right, bottom, left)
    PADDING = 0
    LINE_HEIGHT = 20
    FONT_SIZE = 8
    MANAGED_WINDOWS_WIDTH = 165
    MANAGED_WINDOWS_HEIGHT = (FONT_SIZE + 12) * MAX_WINDOWS
    CONFIG_DROPDOWN_WIDTH = 250
    LABEL_WIDTH = 60

    # Layout constants
    DEFAULT_ALIGN = 'center'  # Valid values: 'left', 'center', 'right'
    DEFAULT_DIRECTION = 'column'  # Valid values: 'row', 'column'

class Colors:
    # Background colors
    BACKGROUND = "#202020"
    TASKBAR = "#666666"
    
    # Window colors
    WINDOW_NORMAL = "#404040"
    WINDOW_ALWAYS_ON_TOP = "#306030"
    WINDOW_BORDER = "#050505"
    DIM_BORDER = "#555555"
    
    # Text colors
    TEXT_NORMAL = "#FFFFFF"
    TEXT_ERROR = "#FFFF00"
    TEXT_ALWAYS_ON_TOP = "#50A050"
    TEXT_DIM = "#555555"

    # Add these for darker backgrounds
    WINDOW_NORMAL_DARK = "#2A2A2A"
    WINDOW_ALWAYS_ON_TOP_DARK = "#104010"
    WINDOW_MISSING_DARK = "#3F1F1F"

    # Buttons
    BUTTON_NORMAL = BACKGROUND
    BUTTON_HOVER = "#404040"
    BUTTON_ACTIVE = "#205020"
    BUTTON_ACTIVE_HOVER = "#306030"
    BUTTON_DISABLED = WINDOW_NORMAL_DARK

    # Status colors
    ADMIN_ENABLED = "green"
    ADMIN_DISABLED = "red"

class Messages:
    # Status messages
    CLICK_TARGET = "Click on the target window..."
    WINDOW_SELECT_FAILED = "Window selection failed or cancelled."
    ALWAYS_ON_TOP_DISABLED = "AOT: None"
    SELECT_CONFIG = "Select a configuration"
    
    # Error messages
    ERROR_TOO_MANY_WINDOWS = f"Please select {UIConstants.MAX_WINDOWS} or fewer windows"
    ERROR_NO_WINDOWS = "Please select at least one window"
    ERROR_NO_APP = "Error: Application reference not set"
    ERROR_TOGGLE_COMPACT = "Error toggling compact mode: {}"
    ERROR_GUI_CREATION = "Error creating GUI: {}"
    ERROR_NO_CONFIG = "No config found"

class WindowStyles:
    TITLE_BAR_COLOR = '#000000'
    TITLE_TEXT_COLOR = '#FFFFFF'
    BORDER_COLOR = '#101010'

class Fonts:
    TEXT_NORMAL = ("Consolas", 10, "normal")
    TEXT_BOLD = ("Consolas", 10, "bold")
    TEXT_TITLE = ("Consolas", 11, "bold")
    #TEXT_NORMAL = ("Segoe UI", 10, "normal")
    #TEXT_BOLD = ("Segoe UI", 10, "bold")
