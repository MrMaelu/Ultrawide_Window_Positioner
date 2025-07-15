import re
from dataclasses import dataclass

@dataclass
class WindowInfo:
    name: str
    pos_x: int
    pos_y: int
    width: int
    height: int
    always_on_top: bool
    exists: bool
    search_title: str

def clean_window_title(title, sanitize=False, titlecase=True):
    if not title:
        return ""
    
    # Basic cleaning
    title = re.sub(r'[^\x20-\x7E]', '', title)
    title = re.sub(r'\s+', ' ', title)
    title = title.strip().lower()
    
    if sanitize:
        # Additional cleaning for config files
        parts = re.split(r' [-—–] ', title)
        title = parts[-1].strip()
        title = re.sub(r'\s+\d+%$', '', title)
        title = re.sub(r'[<>:"/\\|?*\[\]]', '', title)
    
    if titlecase:
        return title.title()
    else:
        return title
