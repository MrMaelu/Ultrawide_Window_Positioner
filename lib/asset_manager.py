import os
import mss
import requests
import win32gui
import win32con
from PIL import Image

class AssetManager():
    def __init__(self, client_id, client_secret, client_info_missing):
        self.CLIENT_ID = client_id
        self.CLIENT_SECRET = client_secret
        self.client_info_missing = client_info_missing

        self.COMPRESSION = (1024,1024)

        if not self.client_info_missing:
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
                print(f"Failed to get access token: {e}")

    def search(self, query, save_dir='screenshots'):
        try:
            exact_body = f'''
                search "{query}";
                fields name, screenshots;
                limit 10;
            '''
            if not self.client_info_missing:
                resp = requests.post('https://api.igdb.com/v4/games', headers=self.headers, data=exact_body)
                games = resp.json()

                if games:
                    for game in games:
                        if game.get("name").lower() == query.lower():
                            name = game.get('name')
                            screenshot_ids = game.get("screenshots", [])
                            if screenshot_ids:
                                self.get_and_download_screenshots(name, screenshot_ids, save_dir)
                                return True

                    print(f"No exact match for {query}. Creating dummy file.")
                    self.create_dummy(query, save_dir)

                else:
                    print(f"No results for {query}. Creating dummy file.")
                    self.create_dummy(query, save_dir)
            else:
                print("IGDB client info missing, creating dummy file.")
                self.create_dummy(query, save_dir)

        except Exception as e:
            print(f"Search query failed: {e}")

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
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)

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
        try:
            name = query.replace(' ', '_').replace(':', '')
            filename = f"{name}.jpg"
            path = os.path.join(save_dir, filename)
            shade = 100
            image = Image.new('RGB', (1,1), (shade,shade,shade))
            image.save(path)
        except Exception as e:
            print(f"Failed to create dummy image: {e}")

