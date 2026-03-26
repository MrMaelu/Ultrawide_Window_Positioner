"""Helper functions for the GUI components."""

def resolve_titlebar(*, override: str, default: bool) -> bool:
    """Determine whether the titlebar should be shown based on override and default values."""
    if override == "on":
        return False
    if override == "off":
        return True
    return default



def format_apply_button(parent, selected_config_shortname: str | None) -> None:
    """Set the state and color for apply and reset buttons."""
    if parent.config_active:
        parent.apply_config_button.setStyleSheet(f"""
            QPushButton {{
                background: {parent.colors.BUTTON_ACTIVE};
                border-radius: 10px;
                border: 2px solid {parent.colors.BORDER_COLOR};
                padding: 5px;
                height: 54px;
            }}
            QPushButton:hover {{
                background: {parent.colors.BUTTON_ACTIVE_HOVER};
            }}
            """)

        parent.apply_config_button.setText("Reset active config")

        parent.info_label.setText(
            f"Active: {
            selected_config_shortname
            if selected_config_shortname
            else parent.applied_config_name
            }",
        )
        parent.aot_button.setEnabled(bool(parent.win_man.topmost_windows))
    else:
        parent.apply_config_button.setStyleSheet(f"""
            QPushButton {{
                background: {parent.colors.BUTTON_NORMAL};
                border-radius: 10px;
                border: 2px solid {parent.colors.BORDER_COLOR};
                padding: 5px;
                height: 54px;
            }}
            QPushButton:hover {{
                background: {parent.colors.BUTTON_HOVER};
            }}
            """)

        parent.apply_config_button.setText("Apply config")
        parent.info_label.setText("")
        parent.aot_button.setEnabled(bool(parent.win_man.topmost_windows))
