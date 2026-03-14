import requests
import hashlib
import random
import time
from collections.abc import Mapping
import config

BASE_URL = config.links["base_url"]


class SessionManager:
    # TODO, have the CrewManager and FleetManager make requests through SessionManager.
    def __init__(self):
        """
        SessionManager constructor
        """
        try:
            self.session = requests.Session()
            self.session.headers.update(self._get_headers())
        except:
            print("Failed to initialize session with game server")
            exit()

        self.resp_debug = 0

        self.game_signed_request = config.cookies["game_signed_request"]
        self.signed_request = config.cookies["signed_request"]
        self.seed = config.seeds["base"]
        try:
            for k in config.user.keys():
                if not config.user[k]:
                    self._set_user_config()
                    break
        except:
            print("Failed to set user data")
            exit()

    def _get_salt(self, seed: str):
        d: list[str] = []
        for i in range(len(seed) - 1, -1, -1):
            c = 90 - ord(seed[i]) + 97
            if c == 139:
                c -= 91
            elif c >= 130:
                c -= 81
            d.insert(0, chr(c))
        return "".join(d)

    def _get_num(self, n: int):
        return (n % 11) * n

    def get_hash(self, seed: str, params_string: str, random_seed: int, secure: bool):
        num = self._get_num(n=random_seed)
        if secure:
            salt = self._get_salt(seed=seed)
            raw = salt + params_string + str(num)
        else:
            raw = params_string + str(num)

        return hashlib.md5(raw.encode()).hexdigest()

    def _get_headers(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/canvas",
            "Cookie": f'PHPSESSID={config.cookies["phpsessid"]}',
        }

    def make_request(
        self,
        endpoint: str,
        params: Mapping[str, str | int | float],
        payload: Mapping[str, str | int],
        secure: bool,
    ):

        new_params = dict(params)
        new_payload = dict(payload)
        ts = int(time.time())

        seed = self.seed
        domain = BASE_URL
        new_params.update(
            {
                "ts": ts,
                "signed_request": self.signed_request,
                "game_signed_request": self.game_signed_request,
                "PHPSESSID": "null",
                "flashsession": "null",
            }
        )
        param_string = f"" + str(new_payload["baseid"]) + str(new_payload["type"])
        hn = random.randint(0, 9999999)
        h = self.get_hash(
            seed=seed, params_string=param_string, random_seed=hn, secure=secure
        )

        new_payload.update(
            {
                "hn": hn,
                "h": h,
            }
        )

        url = f"{domain}/{endpoint}"

        resp = self.session.post(url, params=new_params, data=new_payload)

        resp.raise_for_status()
        return resp.json()

    def _set_user_config(self):
        """
        Populates the user dictionary imported from config.py
        """
        endpoint = config.links["base_load"]
        payload: dict[str, int | str] = {
            "baseid": 0,
            "type": "build",
        }
        resp = self.make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            secure=True,
        )
        if resp["error"] == 0:
            world = -2
            if int(resp["basex"]) < 1200000:
                world = -1
            elif int(resp["basex"]) < 2400000:
                world = 0
            elif int(resp["basex"]) < 3600000:
                world = 1
            elif int(resp["basex"]) < 4800000:
                world = 2
            else:
                world = 3

            config.user.update(
                {
                    "userid": resp["userid"],
                    "baseid": resp["baseid"],
                    "base_x": int(resp["basex"]),
                    "base_y": int(resp["basey"]),
                    "world_index": world,
                }
            )
            return resp
        else:
            print(f"Request failed {resp["error"]}")
