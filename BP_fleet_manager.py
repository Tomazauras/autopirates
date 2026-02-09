import hashlib
import struct
from typing import NotRequired, TypedDict
import requests
import websocket
import random
import math
import time
import os
import threading
from collections import defaultdict
from collections.abc import Mapping

import config

BASE_URL = config.links["base_url"]
WORLD_MAP_URL = config.links["world_map_url"]
LOG_FOLDER = os.getcwd() + "/logs"


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
        endpoint = "api/bm/base/load"
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
                    "base_x": resp["basex"],
                    "base_y": resp["basey"],
                    "world_index": world,
                }
            )
            return resp
        else:
            print(f"Request failed {resp["error"]}")


class CrewManager:
    """
    A class used for crew interactions inside the game. Creating, deleting, assigning crews.

    Important variables:

    self.whitelist - A list of crew type ids to look up, when deciding which crews to accept during a roll session. Can be set in "config.py"
    """

    def __init__(self, session_manager: SessionManager):
        """
        CrewManager constructor

        Args:
            session_manager (SessionManager): The sessionManager object. Used for interacting with the game server.
        """
        self.session_manager = session_manager
        self.userid = config.user["userid"]
        self.seed = config.seeds["base"]
        self.game_signed_request = config.cookies["game_signed_request"]
        self.signed_request = config.cookies["signed_request"]

        self.whitelist = config.whitelist_crews
        self.blacklist = config.blacklist_crews
        self.crew_names = config.crews

        self.uranium_storage = 0
        self.uranium_limit = 1000
        self.remaining_slots = 0
        self.crew_storage: list[CrewManager.Crew] = []
        self._set_crews()
        self._set_uranium()

        self.claimed_crews: set[int] = set()
        self.claim_lock = threading.Lock()

        self.can_roll: defaultdict[int, bool] = defaultdict(bool)
        self.delete_last_roll: defaultdict[int, bool] = defaultdict(bool)

        self.roll_history: dict[int, dict[int, int]] = {}

    class Crew(TypedDict):
        accepted_at: str
        creation_started_at: str
        crew_id: str
        equipment_started_at: str
        expiration_time: str
        extensions: str
        fleet_id: str
        id: str
        userid: str

    def _generate_hash_string(self, params: Mapping[str, str | int], action: int):
        """
        Generates hash string from params.

        Args:
            params (dict): Dictionary of parameters.
            action (int): Number associated with an action.

        Returns:
            string (str): Parameter aggregate.
        """
        new_params = dict(params)
        string = ""
        if action == 0:
            string += str(new_params["packId"])
        elif action == 1 or action == 2:
            string += str(new_params["transactionId"])
        elif action == 3:
            string += str(new_params["id"])
        elif action == 4:
            string += str(new_params["currencyid"])
            string += str(new_params["userid"])
        elif action == 6:
            string += str(new_params["fleet_id"])
            string += str(new_params["id"])
        return string

    def _make_request(
        self,
        endpoint: str,
        params: Mapping[str, str | int | float],
        payload: Mapping[str, str | int],
        post: bool,
        action: int,
    ):
        """
        Forms a request that is then sent to the game server.

        Args:
            endpoint (str): Request endpoint.
            params (dict): Request query string parameters.
            payload (dict): Request form data.
            post (bool): Is request a Post or a Get.
            action (int): Number associated with an action.
                        0 - create
                        1 - reroll
                        2 - accept
                        3 - delete
                        4 - uranium balance
                        5 - crews storage
                        6 - assign

        Returns:
            resp (dict): Response data in json format.
        """

        new_params = dict(params)
        new_payload = dict(payload)

        ts = int(time.time())
        param_string = self._generate_hash_string(params=new_payload, action=action)
        hn = random.randint(0, 9999999)
        h = self.session_manager.get_hash(
            seed=self.seed, params_string=param_string, random_seed=hn, secure=True
        )
        new_params.update(
            {
                "ts": ts,
                "signed_request": self.signed_request,
                "game_signed_request": self.game_signed_request,
                "PHPSESSID": "null",
                "flashsession": "null",
            }
        )

        new_payload.update({"hn": str(hn), "h": h})

        url = f"{BASE_URL}/{endpoint}"
        if post:
            resp = self.session_manager.session.post(
                url, params=new_params, data=new_payload
            )
        else:
            resp = self.session_manager.session.get(url, params=new_params)

        resp.raise_for_status()
        return resp.json()

    def _set_uranium(self):
        """
        Fetch uranium balance from game server.

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["currency"]
        payload = {"userid": self.userid, "currencyid": 1}
        resp = self._make_request(
            endpoint=endpoint, params={}, payload=payload, post=True, action=4
        )
        self.uranium_storage = resp["balances"]["1"]["amount"]
        return resp

    def _set_crews(self):
        """
        Fetch crew data from game server.

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["read"]
        resp = self._make_request(
            endpoint=endpoint, params={}, payload={}, post=True, action=5
        )
        self.remaining_slots: int = resp["remainingSlots"]
        self.crew_storage = resp["items"]
        return resp

    def _create_crew(self):
        """
        Send a request to game server, to create a crew transaction.

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["create"]
        payload = {"packId": "9"}
        self.uranium_storage -= 1000
        return self._make_request(
            endpoint=endpoint, params={}, payload=payload, post=True, action=0
        )

    def _reroll_crew(self, transaction_id: int):
        """
        Send a request to game server, to create a crew transaction.

        Args:
            transaction_id (int): Id of the transaction.

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["reroll"]
        payload = {"transactionId": transaction_id}
        self.uranium_storage -= 800
        return self._make_request(
            endpoint=endpoint, params={}, payload=payload, post=True, action=1
        )

    def _accept_crew(self, transaction_id: int):
        """
        Send a request to game server, to accept the crew transaction.

        Args:
            transaction_id (int): Id of the transaction.

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["accept"]
        payload = {"transactionId": transaction_id}
        return self._make_request(
            endpoint=endpoint, params={}, payload=payload, post=True, action=2
        )

    def _delete_crew(self, long_crew_id: int):
        """
        Send a request to game server, to delete a crew.

        Args:
            long_crew_id (int): Long id of the crew.

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["delete"]
        payload = {"id": long_crew_id}
        return self._make_request(
            endpoint=endpoint, params={}, payload=payload, post=True, action=3
        )

    def assign_crew(self, long_crew_id: int, fleet_id: str):
        """
        Send a request to game server, to assign a crew to a fleet.

        Args:
            long_crew_id (int): Long id of the crew.
            fleet_id (str): Fleet id. ("1"...."15").

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["assign"]
        payload: dict[str, int | str] = {"id": long_crew_id, "fleet_id": fleet_id}
        return self._make_request(
            endpoint=endpoint, params={}, payload=payload, post=True, action=6
        )

    def _claim_crew(self, long_crew_id: int):
        """
        ***Thread-locked***. Mark a crew as claimed / in-use.

        Args:
            long_crew_id (int): Long id of the crew.

        Returns:
            _ (bool): False if crew is not in-use. Otherwise marks the crew as claimed and returns True.
        """
        with self.claim_lock:
            if long_crew_id in self.claimed_crews:
                return False
            self.claimed_crews.add(long_crew_id)
            return True

    def release_crew(self, crew: CrewManager.Crew):
        """
        ***Thread-locked***. Releases a crew by calling self._delete_crew, updates crew storage.

        Args:
            crew (dict): Crew to be released.
        """
        with self.claim_lock:
            self.claimed_crews.discard(int(crew["id"]))
            self.crew_storage.remove(crew)
            self._delete_crew(int(crew["id"]))

    def pick_crew(self, crew_id: int):
        """
        Picks a crew from crew storage, that is not in-use and is of type crew_id.

        Args:
            crew_id (int): Short crew id (crew type).

        Returns:
            crew (dict): Crew object.
        """
        for crew in self.crew_storage:
            if int(crew["crew_id"]) == crew_id and crew["fleet_id"] == "0":
                if self._claim_crew(long_crew_id=int(crew["id"])):
                    return crew
        return False

    def _roll_crew(self, thread: int):
        """
        Initiates a crew transaction and renews it until a crew with an allowed crew type is met.

        Args:
            thread (int): Thread number.

        Returns:
            tuple (int, int): Crew type, Long crew id
        """
        if self.uranium_storage < self.uranium_limit or self.remaining_slots < 2:
            self.can_roll[thread] = False
            return None, None

        resp = self._create_crew()
        transaction_id = int(resp["purchase"]["transactionId"])
        crew_id = int(resp["purchase"]["items"][0]["crew_id"])

        while crew_id not in self.whitelist:
            self.roll_history[thread][crew_id] += 1

            if self.uranium_storage < self.uranium_limit:
                self.can_roll[thread] = False
                self.delete_last_roll[thread] = True
                break

            resp = self._reroll_crew(transaction_id=transaction_id)
            transaction_id = int(resp["purchase"]["transactionId"])
            crew_id = int(resp["purchase"]["items"][0]["crew_id"])

        resp = self._accept_crew(transaction_id=transaction_id)
        return resp["item"]["crew_id"], resp["item"]["id"]

    def print_status(self):
        """
        Print information about the current crew roll session.
        """
        _: defaultdict[int, int] = defaultdict(int)
        for k in self.roll_history.keys():
            _[0] += sum(self.roll_history[k].values())
            for crew_id, count in self.roll_history[k].items():
                if crew_id in self.whitelist:
                    _[crew_id] += count

        print(f"====== Crew Status ======")
        print(f"Rolls : {_[0]}")
        for key, value in _.items():
            if key in self.whitelist:
                print(f"{self.crew_names[key]} : {value}")

    def set_defaults(self, thread_count: int):
        """
        Adjusts self.uranium_limit and self.remaining_slots in response to thread_count.

        Args:
            thread_count (int): The numbers of threads to use when rolling crews and setting limits.
        """
        self.uranium_limit *= thread_count * 1.4
        self.remaining_slots -= thread_count
        for thread in range(0, thread_count):
            self.can_roll[thread] = (
                self.uranium_storage > self.uranium_limit and self.remaining_slots > 2
            )
            self.roll_history[thread] = defaultdict(int)

    def fill_crews(self, timeout: float, thread: int = 0):
        """
        Starts and manages the crew rolling workflow until timeout is reached or crew storage is filled.

        Args:
            timeout (float): Time offset to the future.
            thread (int): Thread number.
        """
        if thread not in self.roll_history:
            self.roll_history[thread] = defaultdict(int)
        while time.time() < timeout and self.remaining_slots > 2:
            if not self.can_roll[thread]:
                if self.uranium_storage > self.uranium_limit:
                    self.can_roll[thread] = True
                else:
                    time.sleep(5)
                    self._set_uranium()
                    continue

            crew_id, crew_id_long = self._roll_crew(thread=thread)
            if crew_id is not None and crew_id_long is not None:
                if self.delete_last_roll[thread]:
                    self._delete_crew(long_crew_id=crew_id_long)
                    self.delete_last_roll[thread] = False
                else:
                    self.roll_history[thread][crew_id] += 1
                    self.remaining_slots -= 1
            self._set_uranium()

    def flush_crews(self, blacklist: bool):
        """
        Delete all crews from storage.

        Args:
            blacklist (bool): Use a blacklist defined in config.py, containing crew ids / types to delete from storage.
        """
        if not self.crew_storage:
            self._set_crews()
        for crew in self.crew_storage:
            if blacklist:
                if int(crew["crew_id"]) in self.blacklist:
                    self._delete_crew(int(crew["id"]))
                    print(f'deleted {self.crew_names[int(crew["crew_id"])]}')
            else:
                self._delete_crew(int(crew["id"]))
                print(f'deleted {self.crew_names[int(crew["crew_id"])]}')


class FleetManager:
    """
    A class used for fleet interactions inside the game. Managing fleet composition, repairing, launching, moving, engaging a target.
    """

    def __init__(self, session_manager: SessionManager):
        """
        FleetManager constructor

        Args:
            session_manager (SessionManager): The sessionManager object. Used for interacting with the game server.
        """
        self.session_manager = session_manager
        self.seed = config.seeds["base"]
        self.world_map_seed = config.seeds["world"]
        self.game_signed_request = config.cookies["game_signed_request"]
        self.map_signed_request = config.cookies["map_signed_request"]
        self.signed_request = config.cookies["signed_request"]
        self.world_index = config.user["world_index"]
        self.userid = config.user["userid"]
        self.baseid = config.user["baseid"]
        self.base_x = config.user["base_x"]
        self.base_y = config.user["base_y"]

        self.map_ids: dict[str, int] = {}
        self.ship_ids: dict[str, FleetManager.FleetPayload] = {}
        self._get_ship_ids()
        self.claimed_targets: set[int] = set()
        self.claim_lock = threading.Lock()
        self.repair_lock = threading.Lock()

        self.positions: dict[str, tuple[int, int]] = {}
        self.pos_lock = threading.Lock()

        self.clock_map: dict[int, tuple[float, float]] = {
            12: (-1, -1),
            1: (-0.33, -1),
            2: (0.33, -1),
            3: (1, -1),
            4: (1, -0.33),
            5: (1, 0.33),
            6: (1, 1),
            7: (0.33, 1),
            8: (-0.33, 1),
            9: (-1, 1),
            10: (-1, 0.33),
            11: (-1, -0.33),
        }
        self.clock_unit: dict[int, tuple[float, float]] = {}
        for h, (cx, cy) in self.clock_map.items():
            m = math.hypot(cx, cy) or 1.0
            self.clock_unit[h] = (cx / m, cy / m)

    class Ship(TypedDict):
        id: int | None
        dock: NotRequired[str]

    class FleetPayload(TypedDict):
        ships: dict[str, FleetManager.Ship]
        launch: NotRequired[str]

    def _generate_hash_string(
        self,
        params: (
            Mapping[
                str,
                str | int | float | list[str | dict[str, str | int | dict[str, int]]],
            ]
            | FleetManager.FleetPayload
        ),
        action: int,
    ):
        """
        Generates hash string from params.

        Args:
            params (dict): Dictionary of parameters.
            action (int): Number associated with an action.

        Returns:
            string (str): Parameter aggregate.
        """
        new_params = dict(params)
        string = ""
        if action == 1:
            string += self.world_map_seed
            string += str(new_params["actions"])
            string += str(new_params["id"])
            string += str(new_params["map_signed_request"])
            string += str(new_params["worldindex"])
        elif action == 2:
            if new_params.get("campaignId", False):
                string += str(new_params["campaignId"])
            if new_params.get("count", False):
                string += str(new_params["count"])
            if new_params.get("levels", False):
                string += str(new_params["levels"])
            if new_params.get("minHealth", False):
                string += str(new_params["minHealth"])
            if new_params.get("types", False):
                string += str(new_params["types"])
        return string

    def _make_request(
        self,
        endpoint: str,
        params: Mapping[str, str | int | float],
        payload: (
            Mapping[
                str,
                str | int | list[str | dict[str, str | int | dict[str, int]]],
            ]
            | FleetManager.FleetPayload
        ),
        post: bool,
        put: bool,
        secure: bool,
        action: int,
        base: str = "kx",
    ):
        """
        Forms a request that is then sent to the game server.

        Args:
            endpoint (str): Request endpoint.
            params (dict): Request query string parameters.
            payload (dict): Request form data.
            post (bool): Is request a Post or a Get.
            put (bool): Is request a Put or a Get.
            secure (bool): Should request use secure hashing.
            action (int): Number associated with an action.
                        0 - launch\n\t ""
                        1 - move\n\t "seed mapid mapReq worldindex"
                        2 - locator  "count levels minhp types"
                        3 - add/remove ship
                        4 - repair fleet
                        5 - instant rep
            base (str): Is request for Base (kx) or Worldmap.

        Returns:
            resp (dict): Response data in json format.
        """
        new_params = dict(params)
        ts = int(time.time())

        if base == "kx":
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
        else:
            seed = self.world_map_seed
            domain = WORLD_MAP_URL
            new_params.update(
                {
                    "game_signed_request": self.game_signed_request,
                    "map_signed_request": self.map_signed_request,
                }
            )

        if action == 2:
            param_string = self._generate_hash_string(params=payload, action=action)
        else:
            param_string = self._generate_hash_string(params=new_params, action=action)

        hn = random.randint(0, 9999999)
        h = self.session_manager.get_hash(
            seed=seed, params_string=param_string, random_seed=hn, secure=secure
        )

        new_payload = dict(payload)
        if action == 2:
            new_payload.update(
                {
                    "hn": hn,
                    "h": h,
                }
            )
        else:
            new_params.update(
                {
                    "hn": hn,
                    "h": h,
                }
            )

        url = f"{domain}/{endpoint}"

        if post:
            if new_payload:
                if action == 0 or action == 5:
                    resp = self.session_manager.session.post(
                        url, params=new_params, json=new_payload
                    )
                elif action == 2:
                    resp = self.session_manager.session.post(
                        url, params=new_params, data=new_payload
                    )
            else:
                resp = self.session_manager.session.post(url, params=new_params)
        elif put:
            resp = self.session_manager.session.put(
                url, params=new_params, json=new_payload
            )
        else:
            resp = self.session_manager.session.get(url, params=new_params)

        resp.raise_for_status()  # pyright: ignore[reportPossiblyUnboundVariable]
        return resp.json()  # pyright: ignore[reportPossiblyUnboundVariable]

    def _distance(self, fleet_id: str, target_x: int, target_y: int):
        """
        Calculates distance to target, relative to last known position.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            target_x (int): X coordinate of the target.
            target_y (int): Y coordinate of the target.

        Returns:
            distance (float): Distance to target.
        """
        last_x, last_y = self._get_position(fleet_id=fleet_id)
        delta_x = last_x - target_x
        delta_y = last_y - target_y
        return math.hypot(delta_x, delta_y)

    def _travel_time(self, distance: float, map_speed: float):
        """
        Calculates travel time to reach target.

        Args:
            distance (float): Distance to target.
            map_speed (float): Fleet map speed.

        Returns:
            time (float): Travel time to target in seconds.
        """
        return distance / (map_speed * 4)

    def _filter_by_distance(
        self,
        fecthed_targets: list[dict[str, int]],
        fleet_id: str,
        level: str,
        max_distance: int,
    ):
        """
        Filters targets based on distance.

        Args:
            fecthed_targets (dict): A dictionary of fetched targets information.
            fleet_id (str): Fleet id. ("1"...."15").
            level (str): Filter targets to also match level.
            max_distance (int): The max acceptable distance to the target from current fleet position.

        Returns:
            targets (list): Target list, sorted in ascending order by distance to the position of the fleet.
        """
        targets: list[tuple[int, int, float, int]] = []
        for target in fecthed_targets:
            dist = self._distance(
                fleet_id=fleet_id,
                target_x=target["x"] * 100,
                target_y=target["y"] * 100,
            )

            if dist > max_distance:
                continue
            if level:
                # TODO check for ',' in level string, if found do itteration for each level separated by ','
                if target["level"] == int(level):
                    targets.append((target["x"], target["y"], dist, int(target["id"])))
            else:
                targets.append((target["x"], target["y"], dist, int(target["id"])))

        if not targets:
            return False

        return sorted(targets, key=lambda target: target[2])

    def _claim_target(self, target_id: int):
        """
        ***Thread-locked***. Mark a target as claimed / engaged.

        Args:
            target_id (int): Id of the target.

        Returns:
            _ (bool): False if target is not engaged. Otherwise marks the target as claimed and returns True.
        """
        with self.claim_lock:
            if target_id in self.claimed_targets:
                return False
            self.claimed_targets.add(target_id)
            return True

    def _release_target(self, target_id: int):
        """
        ***Thread-locked***. Releases a target, updates claimed target list.

        Args:
            target_id (int): Id of the target.
        """
        with self.claim_lock:
            self.claimed_targets.discard(target_id)

    def _pick_target(self, targets: list[tuple[int, int, float, int]]):
        """
        Picks a target, that is not engaged by other fleets. If no target is available - False.

        Args:
            targets (list): Target list.

        Returns:
            target (dict): Target object.
        """
        for t in targets:
            if self._claim_target(t[3]):
                return t
        return False

    def _fetch_locator_targets(self, level: str, types: str, minHealth: str):
        """
        Fetch targets, that match provided parameters.

        Args:
            level (str): Target levels.
            types (str): Target type ids.
            minHealth (str): Minimum target health (0-100).

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = "api/bm/bookmarks/npctargets"
        payload = {
            "count": "100",
            "levels": level,
            "minHealth": minHealth,
            "types": types,
        }
        return self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=True,
            put=False,
            secure=True,
            action=2,
        )

    def _fetch_vengence_targets(self, fleet_id: str, in_sector: bool):
        """
        Fetch vengence targets, that match provided parameters.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            in_sector (bool): Check for targets in users sector.

        Returns:
            targets (dict): Target list of player bases, sorted in ascending order by distance from fleet_id.
        """
        endpoint = "api/bm/bookmarks/vengeanceoutsector"
        resp = self._make_request(
            endpoint=endpoint,
            params={},
            payload={},
            post=True,
            put=False,
            secure=True,
            action=2,
        )
        targets: dict[str, list[dict[str, int]]] = {"bookmarks": []}
        for target in resp["bookmarks"]:
            if (
                target["rank"] == "3"
                or target["rank"] == "4"
                or (target["rank"] == "2" and target["level"] > 100)
            ):
                continue
            targets["bookmarks"].append(target)

        if in_sector:
            endpoint = "api/bm/bookmarks/vengeanceinsector"
            resp = self._make_request(
                endpoint=endpoint,
                params={},
                payload={},
                post=True,
                put=False,
                secure=True,
                action=2,
            )
            for target in resp["bookmarks"]:
                if (
                    target["rank"] == "3"
                    or target["rank"] == "4"
                    or (target["rank"] == "2" and target["level"] > 100)
                ):
                    continue
                targets["bookmarks"].append(target)
        return self._filter_by_distance(
            fecthed_targets=targets["bookmarks"],
            fleet_id=fleet_id,
            level="",
            max_distance=50000,
        )

    def _get_approach_clock(self, fleet_id: str, target_x: int, target_y: int):
        """
        Calculates best angle of engagement to a target, relative to last known position.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            target_x (int): X coordinate of the target.
            target_y (int): Y coordinate of the target.

        Returns:
            clock (int): Engagement clock position relative to the target.
        """
        last_x, last_y = self._get_position(fleet_id=fleet_id)

        # Vector from target to fleet's last known position
        dx = last_x - target_x
        dy = last_y - target_y
        mag = math.hypot(dx, dy)
        if mag < 1e-6:
            return 12

        ux, uy = dx / mag, dy / mag

        # Pick the clock whose unit vector has the largest dot product with (ux,uy)
        best_h = 12
        best_dot = -1.0
        for h, (cx, cy) in self.clock_unit.items():
            dot = ux * cx + uy * cy
            if dot > best_dot:
                best_dot = dot
                best_h = h
        return best_h

    def _pre_launch_payload(self, fleet_id: str):
        """
        Uses data from **self.get_fleets** to craft payload information for the **self.launch** function.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").

        Returns:
            payload (dict): Dictionary containing fleet and miscellaneous information required for a fleet launch request. If fleet information is not found - False.
        """
        response = self.get_fleets()
        fleet_payload: FleetManager.FleetPayload = {
            "ships": {},
            "launch": "worldmap",
        }
        for k, v in response.items():
            if k == "fleets":
                for fleet in v:
                    if fleet["id"] == fleet_id:
                        for ship in fleet["ships"]:
                            fleet_payload["ships"][ship["actives"]["fltp"]] = {
                                "id": int(ship["actives"]["id"]),
                                "dock": "base",
                            }
                        return fleet_payload
        return False

    def _get_ship_ids(self):
        """
        Uses data from **self.get_fleets** to get the composition of ships for fleets 1-15
        """
        response = self.get_fleets()
        for k, v in response.items():
            if k == "fleets":
                for fleet in v:
                    fleet_payload: FleetManager.FleetPayload = {
                        "ships": {},
                    }
                    for ship in fleet["ships"]:
                        fleet_payload["ships"][ship["actives"]["fltp"]] = {
                            "id": int(ship["actives"]["id"]),
                            "dock": "base",
                        }
                    if not self.ship_ids.get(fleet["id"], False):
                        self.ship_ids[fleet["id"]] = fleet_payload

    def _fleet_docked(self, fleet_id: str):
        """
        Checks if a fleet is docked in base.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").

        Returns:
            docked (bool): True if fleet is docked, False if out in worldmap.
        """
        response = self.get_fleets()
        for k, v in response.items():
            if k == "fleets":
                for fleet in v:
                    if fleet["id"] == fleet_id:
                        if fleet["is_on_map"]:
                            self.map_ids[fleet["id"]] = fleet["mapId"]
                        return not fleet["is_on_map"]

    def _fleet_in_combat(self, fleet_id: str, map_speed: float):
        """
        Checks if a fleet is engaged in combat, by sending a move request.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            map_speed (float): Fleet map speed.

        Returns:
            tuple (str, int, str): If fleet engaged (combat_guid, engage_id, server_url), otherwise (None, None, None).
        """
        last_x, last_y = self._get_position(fleet_id=fleet_id)
        resp = self.move(
            fleet_id=fleet_id,
            x=last_x,
            y=last_y,
            map_speed=map_speed,
            in_combat_check=True,
        )
        combat_guid = resp.get("objects")[0].get("data").get("combat_guid", None)
        if combat_guid is not None:
            engage_id = resp.get("objects")[0].get("actions")[0][1]
            server_url = resp.get("objects")[0].get("actions")[0][3]
            return str(combat_guid), int(engage_id), str(server_url)
        return None, None, None

    def _update_position(self, fleet_id: str, x: int, y: int):
        """
        ***Thread-locked***. Updates last known fleet position to given x, y.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            target_x (int): X coordinate of the target.
            target_y (int): Y coordinate of the target.

        """
        with self.pos_lock:
            self.positions[fleet_id] = (x, y)

    def _get_position(self, fleet_id: str):
        """
        ***Thread-locked***. Returns last known fleet position x, y.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").

        Returns:
            tuple (int, int): Last known x, y of the fleet.
        """
        with self.pos_lock:
            return self.positions.get(fleet_id, (self.base_x, self.base_y))

    def _manage_fleet(
        self, fleet_id: str, gs_fleet_id: str = "", fleet_layout: str = ""
    ):
        """
        Updates fleet composition according to **fleet_layout**.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            gs_fleet_id (str): Fleet id which has a half-repair crew assigned to it. ("1"...."15").
            fleet_layout (str): Fleet composition. E.g. "135" would put ships in slots 1,3 and 5.

        Returns:
            resp (dict): Response data in json format.
        """
        if gs_fleet_id:
            endpoint = f"dock/base/fleets/{gs_fleet_id}"
        else:
            endpoint = f"dock/base/fleets/{fleet_id}"

        payload: FleetManager.FleetPayload = {"ships": {}}
        for flp in self.ship_ids.get(fleet_id, {}).get("ships", {}).keys():
            if flp not in fleet_layout:
                payload["ships"][flp] = {"id": None}
            else:
                payload["ships"][flp] = self.ship_ids[fleet_id]["ships"][flp]

        return self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=False,
            put=True,
            secure=True,
            action=3,
        )

    def _fuse(self, instance_id: str, source_id: int, amount: int):
        """
        Experimental.

        1) Loading a fuse-able item in-game,
        2) sending a fuse request through the script,
        3) coming back to the game and fusing the item leads to a bug/crash.

        Following the steps - double crafting can be achieved. This is logged as an error on the server side!
        USE WITH CAUTION

        To get instanceId inspect network requests while fusing an item in-game.

        Args:
            instance_id (str): id.
            source_id (int): id of the item.
            amount (int): amount to fuse.

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = "base/transitions"
        payload: dict[str, list[str | dict[str, str | int | dict[str, int]]]] = {
            "instanceids": [instance_id],
            "transitions": [
                {
                    "instanceid": instance_id,
                    "buildingType": 76,
                    "transition": "fuse_up_to",
                    "extraData": {
                        "sourceID": source_id,
                        "targetID": source_id + 1,
                        "amount": amount,
                    },
                }
            ],
        }
        return self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=True,
            put=False,
            secure=True,
            action=5,
        )

    def _start_campaign_encounter(
        self,
        level: str,
        fleet_id: str,
        gs_fleet_id: str,
        map_speed: float,
        base_repair: bool,
    ):
        """
        Established a websocket connection with the server handling the fleet engagement, follows a user-defined level template to complete the engagement.

        Args:
            level (str): Target levels.
            fleet_id (str): Fleet id. ("1"...."15").
            gs_fleet_id (str): Fleet id which has a half-repair crew assigned to it. ("1"...."15").
            map_speed (float): Fleet map speed.
            base_repair (bool): Should fleet be repaired after an engagement.

        """
        level_template: list[tuple[bytes, float]] = []
        with open(level, "r") as f:
            for line in f.readlines():
                cmd_hex, delay_str = line.split(maxsplit=2)
                cmd_bytes = bytes.fromhex(cmd_hex)
                delay = float(delay_str)
                level_template.append((cmd_bytes, delay))

        combat_guid, engage_id, server_url = self._fleet_in_combat(
            fleet_id=fleet_id, map_speed=map_speed
        )
        if combat_guid is None or engage_id is None or server_url is None:
            return print("Fleet is not engaged")
        websocket = self.start_engagement(
            combat_guid=combat_guid,
            engage_id=engage_id,
            user_id=self.userid,
            server_url=server_url,
            return_ws=True,
        )
        if websocket is not None:
            battle_end_event = threading.Event()
            hb_thread = threading.Thread(
                target=self._handle_heartbeat,
                args=(websocket, battle_end_event),
                daemon=True,
            )
            hb_thread.start()

            for cmd, delay in level_template:
                websocket.send_binary(cmd)
                time.sleep(delay)

            while not battle_end_event.is_set() and websocket.connected:
                time.sleep(1)

            hb_thread.join(timeout=2)
            if websocket.connected:
                websocket.close()

        if base_repair:
            self.move(
                fleet_id=fleet_id,
                x=self.base_x,
                y=self.base_y,
                map_speed=map_speed,
                return_dock=True,
            )
            time.sleep(3)

            with self.repair_lock:
                self.lazy_repair(
                    fleet_id=fleet_id,
                    gs_fleet_id=gs_fleet_id,
                )

            time.sleep(1)
            self.launch(fleet_id=fleet_id)
            time.sleep(2)
            self.move(
                fleet_id=fleet_id,
                x=self.base_x,
                y=self.base_y,
                map_speed=map_speed,
                return_dock=False,
                attack=False,
                clock=10,
                engage_radius=300,
            )

    def _handle_heartbeat(
        self, websocket: websocket.WebSocket, battle_end_event: threading.Event
    ):
        """
        Checks for heartbeat messages from the server, when a message is received a response is sent back.

        Args:
            websocket: Websocket object.
            battle_end_event: Thread event.

        """
        try:
            while websocket.connected:
                try:
                    msg = websocket.recv()
                    if not msg:
                        continue

                    if msg == b"\x01\x00\x00\x00\x06":
                        # print("Battle end signal received.")
                        battle_end_event.set()
                        break

                    if (
                        isinstance(msg, (bytes, bytearray))
                        and len(msg) == 9
                        and msg.startswith(b"\x05\x00\x00\x00")
                    ):
                        pong = b"\x05\x00\x04" + msg[-4:]
                        websocket.send_binary(pong)
                except Exception as e:
                    print("Heartbeat error:", e)
                    break
        finally:
            pass
            # print("Heartbeat thread stopped")

    def _ws_handshake(self, combat_guid: str, engage_id: int, user_id: int):
        """
        Generate a handshake to use when establishing a websocket connection to the server handling a fleet engagement.

        Args:
            combat_guid (str): Combat guid of the engagement.
            engage_id (int): Engage id of the engagement.
            user_id (int): User id.

        Returns:
            msg (bytes): handshake information for websocket connection.
        """
        msg = bytearray(b"CLN")  # writeUTFBytes("CLN") -> raw ASCII
        msg.extend(struct.pack("<I", user_id))  # little-endian 4-byte int
        msg.extend(struct.pack("<I", engage_id))  # little-endian 4-byte int
        guid_bytes = combat_guid.encode("utf-8")
        msg.extend(
            struct.pack("<H", len(guid_bytes))
        )  # 2-byte length prefix (big-endian seems standard)
        msg.extend(guid_bytes)

        return bytes(msg)

    def start_engagement(
        self,
        combat_guid: str,
        engage_id: int,
        user_id: int,
        server_url: str,
        return_ws: bool = False,
    ):
        """
        Start a websocket connection with the server handling the fleet engagement.

        Args:
            combat_guid (str): Combat guid of the engagement.
            engage_id (int): Engage id of the engagement.
            user_id (int): User id.
            server_url (str): Server url of the server that is handling the engagement.
            return_ws (bool): Return websocket object for further action.

        Returns:
            ws (websocket): Websocket object.
        """
        ws = websocket.create_connection(  # pyright: ignore[reportUnknownMemberType]
            "wss://" + server_url + ":3443",
            header=[
                "Origin: {BASE_URL}",
                "Cache-Control: no-cache",
                "Pragma: no-cache",
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 OPR/120.0.0.0",
            ],
        )
        # send CLN + playerId + engageId + combatGuid
        handshake = self._ws_handshake(
            combat_guid=combat_guid, engage_id=engage_id, user_id=user_id
        )
        ws.send_binary(handshake)
        # # send the 3-byte payload (hex: 01 00 05) AQAF
        ws.send_binary(b"\x01\x00\x05")
        try:
            ws.recv()
            ws.recv()
            # # send the 3-byte payload (hex: 01 00 0F) AQAP
            ws.send_binary(b"\x01\x00\x0f")

            delay = time.time() + 1
            while time.time() < delay:
                ws.recv()

            # send the 3-byte payload (hex: 01 00 14) AQAU
            ws.send_binary(b"\x01\x00\x14")
            ws.recv()

            if return_ws:
                return ws

            # send the 3-byte payload (hex: 01 00 10) AQAQ
            ws.send_binary(b"\x01\x00\x10")
            ws.send_binary(b"\x01\x00\x10")
        except Exception as e:
            print("No response:", e)

    def repair_fleet(self, fleet_id: str):
        """
        Send a repair request to start repairing a fleet.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = "dock/base/repair"
        payload = {"fleet": int(fleet_id)}
        return self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=False,
            put=True,
            secure=True,
            action=4,
        )

    def repair_speed_up(self, fleet_id: str):
        """
        Send a repair speed up request. Used when an ongoing repair is less than 5 minutes from completion.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = "dock/base/repair/default"
        payload: Mapping[str, str | int] = {
            "fleet": fleet_id,
            "seconds": 300,
            "purchase_type": "free",
            "currency_id": 0,
            "quantity": 1,
        }
        return self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=True,
            put=False,
            secure=True,
            action=5,
        )

    def get_fleets(self):
        """
        Returns all docked/active fleets for this user.
        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = f"users/{self.userid}/dock/base/fleets"
        return self._make_request(
            endpoint=endpoint,
            params={},
            payload={},
            post=False,
            put=False,
            secure=True,
            action=0,
        )

    def launch(self, fleet_id: str):
        """
        Launch a fleet out to worldmap.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").

        Returns:
            resp (dict): Response data in json format.
        """
        fleet_id = str(fleet_id)
        if not self._fleet_docked(fleet_id):
            print("Fleet is locked / out in worldmap")
            return "Fleet is locked / out in worldmap"

        endpoint = f"dock/base/fleets/{fleet_id}"
        payload = self._pre_launch_payload(fleet_id)
        if not payload:
            print("Couldn't fetch fleet information")
            return "Couldn't fetch fleet information"
        resp = self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=True,
            put=False,
            secure=True,
            action=0,
        )
        self._fleet_docked(fleet_id)
        return resp

    def move(
        self,
        fleet_id: str,
        x: int,
        y: int,
        map_speed: float,
        return_dock: bool = False,
        attack: int = 0,
        clock: int = 0,
        engage_radius: int = 100,
        in_combat_check: bool = False,
    ):
        """
        Send a move request. This is used for moving the fleet, attacking a target, docking to base.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            x (int): X coordinate of the target.
            y (int): Y coordinate of the target.
            map_speed (float): Fleet map speed.
            return_dock (bool): Is the fleet docking.
            attack (int): target id. 0 if not engaging a target.
            clock (int): Engage target from o'clock.
            engage_radius (int): Engage radius to the target.
            in_combat_check (bool): For logging purposes.

        Returns:
            resp (dict): Response data in json format.
        """

        if not clock:
            clock = self._get_approach_clock(fleet_id=fleet_id, target_x=x, target_y=y)

        dx, dy = self.clock_map[clock]
        x = x + math.ceil(dx * engage_radius)
        y = y + math.ceil(dy * engage_radius)

        log_str = f"[Fleet-{fleet_id}] "
        if return_dock:
            action_string = (
                f'[["move",{x},{y},{map_speed*2},{self.userid}],["dock",{self.baseid}]]'
            )
            log_str += "returning to dock"
        elif attack:
            action_string = f'[["move",{x},{y},{map_speed*2},{self.userid}],["attack",{attack},"platform","kxp"]]'
            log_str += f"attacking target at {x} {y}"
        else:
            action_string = f'[["move",{x},{y},{map_speed*2},{self.userid}]]'
            log_str += f"moving to {x} {y}"

        if not in_combat_check:
            print(log_str)

        self._update_position(fleet_id=fleet_id, x=x, y=y)
        endpoint = "updateMapObjects2.php"
        params: dict[str, str | int] = {
            "actions": action_string,
            "id": self.map_ids[fleet_id],
            "worldindex": self.world_index,
        }
        return self._make_request(
            endpoint=endpoint,
            params=params,
            payload={},
            post=False,
            put=False,
            secure=False,
            action=1,
            base="web",
        )

    def lazy_repair(self, fleet_id: str, gs_fleet_id: str):
        """
        Complete the workflow of repairing a fleet.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            gs_fleet_id (str): Fleet id which has a half-repair crew assigned to it. ("1"...."15").

        """
        if not self._fleet_docked(fleet_id=fleet_id):
            print("Send fleet to dock first")
            time.sleep(25)

        ship_count = self.ship_ids.get(fleet_id, {}).get("ships", {}).__len__()

        if ship_count > 1 or fleet_id != gs_fleet_id:
            self._manage_fleet(fleet_id=fleet_id)
            time.sleep(0.5)

        fleet_layout = ""
        for i in range(1, ship_count + 1):
            fleet_layout += str(i)
            if ship_count > 1 or fleet_id != gs_fleet_id:
                self._manage_fleet(
                    fleet_id=fleet_id,
                    gs_fleet_id=gs_fleet_id,
                    fleet_layout=fleet_layout,
                )
                time.sleep(0.5)
            resp = self.repair_fleet(fleet_id=gs_fleet_id)
            repair_time = resp["complete_time"] - resp["currenttime"]
            if repair_time > 300:
                print(
                    f"[== Repair ==] [Fleet-{fleet_id}] Waiting {repair_time - 300} s"
                )
                time.sleep(repair_time - 300)
            time.sleep(0.5)
            self.repair_speed_up(fleet_id=gs_fleet_id)
            time.sleep(0.5)

        if fleet_id != gs_fleet_id:
            self._manage_fleet(
                fleet_id=fleet_id, gs_fleet_id=gs_fleet_id, fleet_layout=""
            )
            time.sleep(0.5)
            self._manage_fleet(fleet_id=fleet_id, fleet_layout=fleet_layout)

    def hunt_targets(
        self,
        fleet_id: str,
        gs_fleet_id: str,
        level: str,
        types: str,
        minHealth: str,
        timeout: float,
        clock: int = 12,
        map_speed: float = 443.5,
        target_template: str = "",
        base_repair: bool = False,
    ):
        """
        Start the workflow of sending a fleet out to worldmap, to engage a target type - either without breaks until fleet is dead or with returns, after each engagement to repair the fleet in base.

        Args:
            fleet_id (str): Fleet id. ("1"...."15").
            gs_fleet_id (str): Fleet id which has a half-repair crew assigned to it. ("1"...."15").
            level (str): Target levels.
            types (str): Target type ids.
            minHealth (str): Minimum target health (0-100).
            timeout (float): time offset from current timestamp.
            clock (int): Engage target from o'clock.
            map_speed (float): Fleet map speed.
            target_template (str): Path to a user-defined target template to follow.
            base_repair (bool): Should fleet be repaired after an engagement.

        """
        self.launch(fleet_id=fleet_id)
        time.sleep(1)
        level_template: list[tuple[bytes, float]] = []
        if target_template:
            with open(target_template, "r") as f:
                for line in f.readlines():
                    cmd_hex, delay_str = line.split(maxsplit=2)
                    cmd_bytes = bytes.fromhex(cmd_hex)
                    delay = float(delay_str)
                    level_template.append((cmd_bytes, delay))
        while time.time() < timeout:
            fecthed_targets = self._fetch_locator_targets(
                level=level, types=types, minHealth=minHealth
            )
            targets = self._filter_by_distance(
                fecthed_targets=fecthed_targets["bookmarks"],
                fleet_id=fleet_id,
                level=level,
                max_distance=50000,
            )

            if not targets:
                print(f"[Fleet-{fleet_id}] Could not find targets close to base")
                time.sleep(60)
                continue

            target = self._pick_target(targets=targets)

            if not target:
                print(f"[Fleet-{fleet_id}] Could not targets, that are not engaged")
                time.sleep(60)
                continue

            try:
                self.move(
                    fleet_id=fleet_id,
                    x=target[0] * 100,
                    y=target[1] * 100,
                    map_speed=map_speed,
                    attack=target[3],
                    clock=clock,
                )
                time.sleep(self._travel_time(distance=target[2], map_speed=map_speed))
                time.sleep(5)
                combat_guid, engage_id, server_url = self._fleet_in_combat(
                    fleet_id=fleet_id, map_speed=map_speed
                )
                if (
                    combat_guid is not None
                    and engage_id is not None
                    and server_url is not None
                ):
                    if level_template:
                        websocket = self.start_engagement(
                            combat_guid=combat_guid,
                            engage_id=engage_id,
                            user_id=self.userid,
                            server_url=server_url,
                            return_ws=True,
                        )

                        if websocket is not None:
                            battle_end_event = threading.Event()
                            hb_thread = threading.Thread(
                                target=self._handle_heartbeat,
                                args=(websocket, battle_end_event),
                                daemon=True,
                            )
                            hb_thread.start()

                            for cmd, delay in level_template:
                                websocket.send_binary(cmd)
                                time.sleep(delay)

                            while not battle_end_event.is_set() and websocket.connected:
                                time.sleep(1)

                            hb_thread.join(timeout=2)
                            if websocket.connected:
                                websocket.close()
                    else:
                        self.start_engagement(
                            combat_guid=combat_guid,
                            engage_id=engage_id,
                            user_id=self.userid,
                            server_url=server_url,
                        )

                time.sleep(1)
                while True:
                    combat_guid, _, _ = self._fleet_in_combat(
                        fleet_id=fleet_id, map_speed=map_speed
                    )
                    if combat_guid is None:
                        time.sleep(2)
                        break
                    time.sleep(10)
            finally:
                self._release_target(target_id=target[3])
                print(
                    f"[Fleet-{fleet_id}] {(timeout - time.time()) / 60 :.2f} min left"
                )

            if base_repair:
                delay = self._distance(
                    fleet_id=fleet_id, target_x=self.base_x, target_y=self.base_y
                )
                self.move(
                    fleet_id=fleet_id,
                    x=self.base_x,
                    y=self.base_y,
                    map_speed=map_speed,
                    return_dock=True,
                )
                time.sleep(
                    self._travel_time(
                        distance=delay,
                        map_speed=map_speed,
                    )
                )
                time.sleep(3)

                with self.repair_lock:
                    self.lazy_repair(
                        fleet_id=fleet_id,
                        gs_fleet_id=gs_fleet_id,
                    )

                time.sleep(1)
                self.launch(fleet_id=fleet_id)
                time.sleep(2)

        time.sleep(1)
        self.move(
            fleet_id=fleet_id,
            x=self.base_x,
            y=self.base_y,
            map_speed=map_speed,
            return_dock=True,
        )
        time.sleep(3)


def test_entrace(fleet_id: str, map_speed: float, level: str, types: str, clock: int):
    """
    Send out a fleet to a target, at a set clock, relative to the target center.

    Args:
        fleet_id (str): Id of the fleet.
        map_speed (float): Map speed of the fleet.
        level (str): Target level.
        types (str): Target type.
        clock (int): Entrance relative to the target.
    """
    fm.launch(fleet_id=fleet_id)
    targets = fm._filter_by_distance(  # pyright: ignore[reportPrivateUsage]
        fecthed_targets=fm._fetch_locator_targets(  # pyright: ignore[reportPrivateUsage]
            level=level, types=types, minHealth="100"
        ),
        fleet_id=fleet_id,
        level=level,
        max_distance=20000,
    )
    if not targets:
        return print(f"No targets close by found")
    target = fm._pick_target(targets=targets)  # pyright: ignore[reportPrivateUsage]
    if not target:
        return print(f"Target {types} {level} not found")
    fm.move(
        fleet_id=fleet_id,
        x=target[0] * 100,
        y=target[1] * 100,
        map_speed=map_speed,
        return_dock=False,
        attack=False,
        clock=clock,
        engage_radius=100,
        in_combat_check=False,
    )


def crew_scenario():
    """
    Sends out fleets [1-5] to hunt uranium targets, each containing a single ship that can destroy the uranium target. Once all fleets are sent out, 20 Threads are inniated to roll for crews.
    """
    tout = time.time() + 60 * 30
    for i in range(1, 6):
        threading.Thread(
            target=fm.hunt_targets,
            args=(str(i), str(i), 13, 343, tout, 12, 443.5, 1, False, False),
        ).start()
        time.sleep(15)

    for i in range(6, 8):
        threading.Thread(
            target=fm.hunt_targets,
            args=(str(i), str(i), 13, 343, tout, 12, 406, 1, False, False),
        ).start()
        time.sleep(10)

    cm.set_defaults(40)
    for i in range(40):
        threading.Thread(
            target=cm.fill_crews,
            args=(tout, i),
        ).start()
        time.sleep(1)

    while time.time() < tout:
        cm.print_status()
        time.sleep(60)


def camp_scenario(campaign_levels: list[str]):
    """
    Experimental.
    Function accepts level templates for a campaign to be completed by fleet 1, the campaign must be started and a battle has to be engaged by the user.
    After those steps, the script can be continued and level is done following the template provided.

    Args:
        campaign_levels (list): Target template paths.

    Example:
        Given campaign_levels = ["targets/some_target.txt", "targets/some_target2.txt"], function cycles over the templates, waiting for user input to either skip a template or use it.
    """
    while True:
        camp_lvls = campaign_levels[:]
        fm.launch(fleet_id="1")
        time.sleep(3)
        fm.move(
            fleet_id="1",
            x=fm.base_x,
            y=fm.base_y,
            map_speed=406,
            return_dock=False,
            attack=False,
            clock=10,
            engage_radius=300,
            in_combat_check=False,
        )
        while True:
            for level in camp_lvls:
                _ = input(f"Press Enter to do [level-{level}]...")
                if _.strip() == "0":
                    print(f"Skiping Lvl-{level}")
                    continue
                fm._start_campaign_encounter(  # pyright: ignore[reportPrivateUsage]
                    level=level,
                    fleet_id="1",
                    gs_fleet_id="1",
                    map_speed=406,
                    base_repair=False,
                )


if __name__ == "__main__":
    try:
        sm = SessionManager()
        with sm.session:
            cm = CrewManager(session_manager=sm)
            fm = FleetManager(session_manager=sm)

            # Scenario can be created by calling the respective manager functions..

    except KeyboardInterrupt:
        print("shutdown. keyboard interput")
