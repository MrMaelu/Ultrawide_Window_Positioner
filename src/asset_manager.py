"""Asset manager for Ultrawide Window Postioner."""
import importlib
import threading
from pathlib import Path

import mss
import requests
import win32con
import win32gui
from PIL import Image

IGNORE_LIST = [
    "discord",
    "steam",
    "microsoft edge",
    "opera",
    "firefox",
    "google chrome",
]

ACCESS_TOKEN_LENGTH = 30
RESP_OK_CODE = 200

class AssetManager:
    """Handles screenshots and downloads."""

    def __init__(self, base_path:str) -> None:
        """Set up base variables."""
        self.base_path = base_path
        self.assets_dir = ""

        self.headers = None

        self.CLIENT_ID = ""
        self.CLIENT_SECRET = ""
        self.igdb_api_missing = True

        self.RAWG_API_KEY = ""
        self.rawg_api_missing = True

        self.client_info_missing = True

        self.COMPRESSION = (1024,1024)

        self.secrets_status = None
        self.client_info_missing = None

        threading.Thread(target=self.threaded_startup, daemon=True).start()

    def threaded_startup(self) -> None:
        """Split loading slow libraries into separate thread."""
        self.assets_dir = Path(self.base_path, "assets")
        if not Path.exists(self.assets_dir):
            Path.mkdir(self.assets_dir, parents=True, exist_ok=True)

        self.secrets_status = self.load_client_secrets()
        self.client_info_missing = self.igdb_api_missing and self.rawg_api_missing
        if not self.igdb_api_missing:
            self.load_igdb_client_info()
        self.load_igdb_client_info()

    def load_client_secrets(self) -> bool:
        """Check if IGDB secrets are added."""
        secrets = None
        try:
            secrets = importlib.import_module("client_secrets")
        except (ModuleNotFoundError, SyntaxError):
            return False

        if secrets:
            self.CLIENT_ID = ""
            self.CLIENT_SECRET = ""
            self.RAWG_API_KEY = ""

            if hasattr(secrets, "CLIENT_ID"):
                self.CLIENT_ID = secrets.CLIENT_ID
            if hasattr(secrets, "CLIENT_SECRET"):
                self.CLIENT_SECRET = secrets.CLIENT_SECRET
            if hasattr(secrets, "RAWG_API_KEY"):
                self.RAWG_API_KEY = secrets.RAWG_API_KEY

            if (self.CLIENT_ID.strip() != "" and self.CLIENT_SECRET.strip() != ""):
                self.igdb_api_missing = False

            if self.RAWG_API_KEY.strip() != "":
                self.rawg_api_missing = False
            return True
        return False

    def load_igdb_client_info(self) -> None:
        """Load the info from the credentials file."""
        self.auth_url = "https://id.twitch.tv/oauth2/token"
        self.params = {
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "grant_type": "client_credentials",
        }

        self.access_token = requests.post(
            self.auth_url,
            params=self.params,
            timeout=10,
            ).json()["access_token"]

        if len(self.access_token) != ACCESS_TOKEN_LENGTH:
            self.access_token = None
        else:
            self.headers = {
                    "Client-ID": self.CLIENT_ID,
                    "Authorization": f"Bearer {self.access_token}",
                }

    def search(self, query:str, save_dir:str="screenshots") -> tuple[bool, str, str]:
        """Perform the search for screenshots on IGDB and RAWG."""
        if query.lower() in IGNORE_LIST:
            self.create_dummy(query, save_dir)
            return "ignored", "", ""

        exact_body = f"""
            search "{query}";
            fields name, screenshots;
            limit 10;
        """
        if not self.client_info_missing and self.headers:
            resp = requests.post("https://api.igdb.com/v4/games",
                                    headers=self.headers,
                                    data=exact_body,
                                    timeout=10,
                                    )
            games = resp.json()

            if not games:
                return self.try_rawg(query, save_dir)

            for game in games:
                if game.get("name").lower() == query.lower():
                    name = game.get("name")
                    screenshot_ids = game.get("screenshots", [])
                    if screenshot_ids:
                        self.get_and_download_screenshots(
                            name,
                            screenshot_ids,
                            save_dir,
                            )
                        base_url = "https://www.igdb.com/games/"
                        url = base_url + name.replace(" ", "-").lower()
                        return True, "IGDB", url

            return self.try_rawg(query, save_dir)
        return self.try_rawg(query, save_dir)

    def try_rawg(self, query:str, save_dir:str) -> tuple[bool, str, str]:
        """Try to search RAWG for screenshots."""
        if self.RAWG_API_KEY:
            success, rawg_url = self.search_rawg(query, save_dir)
            if success:
                return True, "RAWG", rawg_url
            return False, False, False
        self.create_dummy(query, save_dir)
        return False, False, False

    def search_rawg(self, query:str, save_dir:str) -> tuple[bool, str]:
        """Search for screenshots on RAWG."""
        url = "https://api.rawg.io/api/games"
        params = {
            "key": self.RAWG_API_KEY,
            "search": query,
            "page_size": 10,
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == RESP_OK_CODE:
            results = resp.json().get("results", [])
            for game in results:
                if game.get("name", "").lower() == query.lower():
                    name = game.get("name", query)
                    slug = game.get("slug", "")
                    rawg_url = f"{url}/{slug}"
                    screenshots_url = f"{url}/{game['id']}/screenshots"
                    shots_resp = requests.get(
                        screenshots_url,
                        params={"key": self.RAWG_API_KEY},
                        timeout=10,
                        )

                    if shots_resp.status_code == RESP_OK_CODE:
                        shots = shots_resp.json().get("results", [])
                        for i, shot in enumerate(shots):
                            img_url = shot.get("image")
                            if i == len(shots) - 1:
                                filename = self.filename_from_name(name)
                                self.download_image(img_url, save_dir, filename)
                        return True, rawg_url
        return False, None

    def get_and_download_screenshots(self, game_name:str, ids:str, save_dir:str)->bool:
        """Search for and download screenshots for games."""
        id_list = ",".join(str(i) for i in ids)
        body = f"""
            fields url;
            where id = ({id_list});
        """
        resp = requests.post(
            "https://api.igdb.com/v4/screenshots",
            headers=self.headers,
            data=body,
            timeout=10,
            )
        if resp.status_code == RESP_OK_CODE:
            urls = resp.json()
            for shot in urls:
                url = "https:" + shot["url"].replace("t_thumb", "t_1080p")
                game_name = game_name.replace(" ", "_").replace(":", "")
                filename = f"{game_name}.jpg"
                self.download_image(url, save_dir, filename)
                return True

        return False

    def download_image(self, url:str, folder:str, filename:str) -> None:
        """Download screenshot."""
        Path.mkdir(folder, exist_ok=True, parents=True)
        path = Path(folder, filename)

        r = requests.get(url, stream=True, timeout=10)
        if r.status_code == RESP_OK_CODE:
            with Path.open(path, "wb") as f:
                f.writelines(r.iter_content(1024))

            img = Image.open(path)
            img.thumbnail(self.COMPRESSION)
            img.save(path)

    def bring_to_front(self, hwnd:int) -> None:
        """Bring selected window to front."""
        try:
            if not win32gui.IsWindow(hwnd):
                return
            # Restore if minimized
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # Push to the very top (above everything else)
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
            )
            # Immediately remove always-on-top so normal stacking returns
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_NOTOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
            )
        except (win32gui.error, win32con.ERROR):
            pass

    def get_window_rect(self, hwnd:int) -> None:
        """Get the selected windows rect parameters."""
        rect = win32gui.GetWindowRect(hwnd)
        return {"top": rect[1], "left": rect[0],
                "width": rect[2] - rect[0], "height": rect[3] - rect[1]}

    def capture_window(self, hwnd:int, save_path:str) -> None:
        """Take a screenshot of the window."""
        self.bring_to_front(hwnd)
        with mss.mss() as sct:
            bbox = self.get_window_rect(hwnd)
            sct_img = sct.grab(bbox)
            img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
            img.thumbnail(self.COMPRESSION)
            img.save(save_path)

    def create_dummy(self, query:str, save_dir:str) -> None:
        """Create a dummy placeholder image."""
        return
        name = query.replace(" ", "_").replace(":", "")
        filename = f"{name}.jpg"
        path = Path(save_dir, filename)
        shade = 100
        image = Image.new("RGB", (1,1), (shade,shade,shade))
        image.save(path)

    def filename_from_name(self, name:str) -> str:
        """Convert name to filename."""
        return f"{name.replace(' ', '_').replace(':', '')}.jpg"

