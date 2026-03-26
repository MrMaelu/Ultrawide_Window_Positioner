"""Log handler for the Ultrawide Window Positioner."""
import logging
from pathlib import Path

"""Rotate log files to keep a history of logs."""
log_folder = Path("logs")
log_path = Path(log_folder / "uwp_debug.log")
log_path_old = Path(log_folder / "uwp_debug_old.log")
log_path_old_old = Path(log_folder / "uwp_debug_old_old.log")

if not log_folder.exists():
    log_folder.mkdir()

try:
    if log_path.exists():
        if log_path_old.exists():
            if log_path_old_old.exists():
                log_path_old_old.unlink()
            log_path_old.rename(log_path_old_old)
        log_path.rename(log_path_old)
except Exception as e:  # noqa: BLE001
    print(f"Could not rotate logs: {e}")  # noqa: T201

def setup_logging()->None:
    """Set up logging."""
    logging.basicConfig(
        level=logging.INFO,
        filename=log_path,
        format="%(asctime)s - %(levelname)s - %(message)s",
        )
