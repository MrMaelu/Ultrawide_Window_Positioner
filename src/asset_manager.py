import os
import mss
import win32con, win32gui, win32api, win32process
from PIL import Image
import threading
import importlib
import requests

IGNORE_LIST = [
    'discord',
    'steam',
    'microsoft edge',
    'opera',
    'firefox',
    'google chrome',
]

class AssetManager():
    def __init__(self, base_path):
        self.base_path = base_path
        self.assets_dir = ''

        self.headers = None

        self.CLIENT_ID = ''
        self.CLIENT_SECRET = ''
        self.igdb_api_missing = True

        self.RAWG_API_KEY = ''
        self.rawg_api_missing = True

        self.client_info_missing = True

        self.COMPRESSION = (1024,1024)

        self.secrets_status = None
        self.client_info_missing = None

        threading.Thread(target=self.threaded_startup, daemon=True).start()

    def threaded_startup(self):
        self.assets_dir = os.path.join(self.base_path, "assets")
        if not os.path.exists(self.assets_dir): os.makedirs(self.assets_dir)

        try:
            import requests
        except Exception:
            print("Failed to import requests. Downloads disabled.")
            self.client_info_missing = True
            return

        self.secrets_status = self.load_client_secrets()
        self.client_info_missing = self.igdb_api_missing and self.rawg_api_missing
        if not self.igdb_api_missing:
            self.load_igdb_client_info()

    def load_client_secrets(self):
        # Check if IGDB secrets are added
        secrets = None
        try:
            secrets = importlib.import_module("client_secrets")
        except ModuleNotFoundError:
            return False

        if secrets:
            self.CLIENT_ID = ''
            self.CLIENT_SECRET = ''
            self.RAWG_API_KEY = ''

            if hasattr(secrets, 'CLIENT_ID'):
                self.CLIENT_ID = secrets.CLIENT_ID
            if hasattr(secrets, 'CLIENT_SECRET'):
                self.CLIENT_SECRET = secrets.CLIENT_SECRET
            if hasattr(secrets, 'RAWG_API_KEY'):
                self.RAWG_API_KEY = secrets.RAWG_API_KEY

            if (self.CLIENT_ID.strip() != '' and self.CLIENT_SECRET.strip() != ''):
                self.igdb_api_missing = False

            if self.RAWG_API_KEY.strip() != '':
                self.rawg_api_missing = False
            return True

    def load_igdb_client_info(self):
        self.auth_url = 'https://id.twitch.tv/oauth2/token'
        self.params = {
            'client_id': self.CLIENT_ID,
            'client_secret': self.CLIENT_SECRET,
            'grant_type': 'client_credentials'
        }

        try:
            self.access_token = requests.post(self.auth_url, params=self.params).json()['access_token']
            self.headers = {
                'Client-ID': self.CLIENT_ID,
                'Authorization': f'Bearer {self.access_token}'
            }
        except Exception as e:
            self.access_token = None

    def search(self, query, save_dir='screenshots'):
        if query.lower() in IGNORE_LIST:
            print(f"Search query '{query}' is in ignore list.")
            self.create_dummy(query, save_dir)
            return 'ignored', '', ''
        try:
            exact_body = f'''
                search "{query}";
                fields name, screenshots;
                limit 10;
            '''
            if not self.client_info_missing and self.headers:
                resp = requests.post('https://api.igdb.com/v4/games', headers=self.headers, data=exact_body)
                games = resp.json()

                if games:
                    for game in games:
                        if game.get("name").lower() == query.lower():
                            name = game.get('name')
                            screenshot_ids = game.get("screenshots", [])
                            if screenshot_ids:
                                self.get_and_download_screenshots(name, screenshot_ids, save_dir)
                                return True, 'IGDB','https://www.igdb.com/games/' + name.replace(' ', '-').lower()

                    return self.try_rawg(query, save_dir)
                else:
                    return self.try_rawg(query, save_dir)
            else:
                return self.try_rawg(query, save_dir)

        except Exception as e:
            print(f"Search query failed: {e}")

    def try_rawg(self, query, save_dir):
        if self.RAWG_API_KEY:
            success, rawg_url = self.search_rawg(query, save_dir)
            if success:
                return True, 'RAWG', rawg_url
            else:
                return False, False, False
        else:
            self.create_dummy(query, save_dir)
            return False, False, False

    def search_rawg(self, query, save_dir):
        try:
            url = f"https://api.rawg.io/api/games"
            params = {
                "key": self.RAWG_API_KEY,
                "search": query,
                "page_size": 10,
            }
            resp = requests.get(url, params=params)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    for game in results:
                        if game.get("name", "").lower() == query.lower():
                            name = game.get("name", query)
                            slug = game.get("slug", "")
                            rawg_url = f"https://rawg.io/games/{slug}"
                            screenshots_url = f"https://api.rawg.io/api/games/{game['id']}/screenshots"
                            shots_resp = requests.get(screenshots_url, params={"key": self.RAWG_API_KEY})
                            if shots_resp.status_code == 200:
                                shots = shots_resp.json().get("results", [])
                                if shots:
                                    for i, shot in enumerate(shots):
                                        img_url = shot.get("image")
                                        if img_url:
                                            if i == len(shots) - 1:
                                                filename = f"{name.replace(' ', '_').replace(':', '')}.jpg"
                                                self.download_image(img_url, save_dir, filename)
                                    return True, rawg_url
            print(f"RAWG: No screenshots found for {query}")
            return False, None
        except Exception as e:
            print(f"RAWG search failed: {e}")
            return False, None

    def get_and_download_screenshots(self, game_name, ids, save_dir):
        try:
            id_list = ','.join(str(i) for i in ids)
            body = f'''
                fields url;
                where id = ({id_list});
            '''
            resp = requests.post('https://api.igdb.com/v4/screenshots', headers=self.headers, data=body)
            if resp.status_code == 200:
                urls = resp.json()
                for i, shot in enumerate(urls):
                    url = "https:" + shot['url'].replace('t_thumb', 't_1080p')
                    game_name = game_name.replace(' ', '_').replace(':', '')
                    filename = f"{game_name}.jpg"
                    self.download_image(url, save_dir, filename)
                    return True
            else:
                print("Failed to fetch screenshots:", resp.status_code, resp.text)
                return False
        except Exception as e:
            print(f"get_and_download failed: {e}")

    def download_image(self, url, folder, filename):
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, filename)

            r = requests.get(url, stream=True)
            if r.status_code == 200:
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
                try:
                    img = Image.open(path)
                    img.thumbnail(self.COMPRESSION)
                    img.save(path)
                except Exception as e:
                    print(f"Failed to compress {path}: {e}")
            else:
                print(f"Failed to download {url} (status {r.status_code})")
        except Exception as e:
            print(f"Downloading image failed: {e}")

    def bring_to_front(self, hwnd):
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
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )
            # Immediately remove always-on-top so normal stacking returns
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_NOTOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )
        except Exception as e:
            print(f"Failed to bring window to front: {e}")

    def get_window_rect(self, hwnd):
        rect = win32gui.GetWindowRect(hwnd)
        return {'top': rect[1], 'left': rect[0], 'width': rect[2] - rect[0], 'height': rect[3] - rect[1]}

    def capture_window(self, hwnd, save_path):
        self.bring_to_front(hwnd)
        with mss.mss() as sct:
            bbox = self.get_window_rect(hwnd)
            sct_img = sct.grab(bbox)
            img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
            img.thumbnail(self.COMPRESSION)
            img.save(save_path)

    def create_dummy(self, query, save_dir):
        return
        try:
            name = query.replace(' ', '_').replace(':', '')
            filename = f"{name}.jpg"
            path = os.path.join(save_dir, filename)
            shade = 100
            image = Image.new('RGB', (1,1), (shade,shade,shade))
            image.save(path)
        except Exception as e:
            print(f"Failed to create dummy image: {e}")

