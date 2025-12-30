import hashlib
import struct
import requests
import websocket
import random
import math
import time
import json
import os
import threading
from collections import defaultdict
from winotify import Notification

import config

BASE_URL = config.links["base_url"]
WORLD_MAP_URL = config.links["world_map_url"]
LOG_FOLDER = os.getcwd() + "\logs"


def get_salt(seed):
    d = []
    for i in range(len(seed) - 1, -1, -1):
        c = 90 - ord(seed[i]) + 97
        if c == 139:
            c -= 91
        elif c >= 130:
            c -= 81
        d.insert(0, chr(c))
    return "".join(d)


def get_num(n):
    return (n % 11) * n


def get_hash(seed, params_string, random_seed, secure):
    num = get_num(random_seed)
    if secure:
        salt = get_salt(seed)
        raw = salt + params_string + str(num)
    else:
        raw = params_string + str(num)

    return hashlib.md5(raw.encode()).hexdigest()


def _get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/canvas",
        "Cookie": f'PHPSESSID={config.configs["phpsessid"]}',
    }


class CrewManager:
    def __init__(self, session):
        self.session = session
        self.userid = config.configs["userid"]
        self.seed = config.seeds["base"]
        self.game_signed_request = config.configs["game_signed_request"]
        self.signed_request = config.configs["signed_request"]

        self.whitelist = config.whitelist_crews
        self.blacklist = config.blacklist_crews
        self.crew_names = config.crews

        self.uranium_storage = 0
        self.uranium_limit = 1000
        self.remaining_slots = 0
        self.crew_storage = []
        self._set_crews()
        self._set_uranium()

        self.claimed_crews = set()
        self.claim_lock = threading.Lock()

        self.can_roll = defaultdict(bool)
        self.delete_last_roll = defaultdict(bool)

        self.roll_history = defaultdict(int)
        self.status = defaultdict(int)
        self.roll_history_counts = defaultdict(list)
        self.last_gold_roll = defaultdict(int)

    def _calc_h_hn(self, params, seed):
        hn = random.randint(0, 9999999)
        h = get_hash(seed, params, hn, secure=True)
        return hn, h

    def _generate_hash_string(self, params, action):
        string = ""
        if action == 0:
            string += str(params["packId"])
        elif action == 1 or action == 2:
            string += str(params["transactionId"])
        elif action == 3:
            string += str(params["id"])
        elif action == 4:
            string += str(params["currencyid"])
            string += str(params["userid"])
        elif action == 5:
            pass
        elif action == 6:
            string += str(params["fleet_id"])
            string += str(params["id"])
        return string

    def _make_request(
        self,
        endpoint,
        params=None,
        payload=None,
        post=False,
        action=0,
    ):
        """
        0 - create\n\t
        1 - reroll\n\t
        2 - accept\n\t
        3 - delete\n\t
        4 - uranium balance\n\t
        5 - crews storage\n\t
        6 - assign\n\t
        """
        if params is None:
            params = {}

        if payload is None:
            payload = {}

        ts = int(time.time())
        seed = self.seed
        param_string = self._generate_hash_string(payload, action)
        hn, h = self._calc_h_hn(param_string, seed)
        params.update(
            {
                "ts": ts,
                "signed_request": self.signed_request,
                "game_signed_request": self.game_signed_request,
                "PHPSESSID": "null",
                "flashsession": "null",
            }
        )

        payload.update({"hn": str(hn), "h": h})

        url = f"{BASE_URL}/{endpoint}"
        if post:
            resp = self.session.post(url, params=params, data=payload)
        else:
            resp = self.session.get(url, params=params)

        resp.raise_for_status()
        return resp.json()

    def _set_uranium(self):
        endpoint = "player/getCurrencyBalance"
        payload = {"userid": self.userid, "currencyid": 1}
        resp = self._make_request(endpoint, payload=payload, action=4, post=True)
        self.uranium_storage = resp["balances"]["1"]["amount"]
        return resp

    def _set_crews(self):
        endpoint = "/api/bm/roguecrew/read"
        resp = self._make_request(endpoint, post=True, action=5)
        self.remaining_slots = resp["remainingSlots"]
        self.crew_storage = resp["items"]
        return resp

    def _create_crew(self):
        endpoint = "api/bm/roguecrew/create"
        payload = {"packId": "9"}
        self.uranium_storage -= 1000
        return self._make_request(endpoint, payload=payload, post=True, action=0)

    def _reroll_crew(self, transaction_id):
        endpoint = "api/bm/roguecrew/reroll"
        payload = {"transactionId": transaction_id}
        self.uranium_storage -= 800
        return self._make_request(endpoint, payload=payload, post=True, action=1)

    def _accept_crew(self, transaction_id):
        endpoint = "api/bm/roguecrew/accept"
        payload = {"transactionId": transaction_id}
        return self._make_request(endpoint, payload=payload, post=True, action=2)

    def _delete_crew(self, long_crew_id):
        endpoint = "api/bm/roguecrew/delete"
        payload = {"id": long_crew_id}
        return self._make_request(endpoint, payload=payload, post=True, action=3)

    def _assign_crew(self, long_crew_id, fleet_id):
        endpoint = "api/bm/roguecrew/assign"
        payload = {"id": long_crew_id, "fleet_id": fleet_id}
        return self._make_request(endpoint, payload=payload, post=True, action=6)

    def _claim_crew(self, long_crew_id):
        with self.claim_lock:
            if long_crew_id in self.claimed_crews:
                return False
            self.claimed_crews.add(long_crew_id)
            return True

    def _release_crew(self, crew):
        with self.claim_lock:
            self.claimed_crews.discard(crew["id"])
            self.crew_storage.remove(crew)
            self._delete_crew(crew["id"])

    def _pick_crew(self, crew_id):
        for crew in self.crew_storage:
            if int(crew["crew_id"]) == crew_id and crew["fleet_id"] == "0":
                if self._claim_crew(long_crew_id=crew["id"]):
                    return crew
        return None

    def _roll_crew(self, thread):
        if self.uranium_storage < self.uranium_limit or self.remaining_slots < 2:
            # print("Uranium ended or crews full. Cant buy")
            self.can_roll[thread] = False
            return None, None

        resp = self._create_crew()
        transaction_id = int(resp["purchase"]["transactionId"])
        crew_id = int(resp["purchase"]["items"][0]["crew_id"])

        while crew_id not in self.whitelist:
            self.roll_history[thread][crew_id] += 1

            if self.uranium_storage < self.uranium_limit:
                # print("Uranium ended. Cant reroll")
                self.can_roll[thread] = False
                self.delete_last_roll[thread] = True
                break

            resp = self._reroll_crew(transaction_id=transaction_id)
            transaction_id = int(resp["purchase"]["transactionId"])
            crew_id = int(resp["purchase"]["items"][0]["crew_id"])

        resp = self._accept_crew(transaction_id=transaction_id)
        return resp["item"]["crew_id"], resp["item"]["id"]

    def _print_status(self):
        print(f"====== Crew Status ======")
        print(f"Rolls : {self.status[0]}")
        for key, value in self.status.items():
            if key in self.whitelist:
                print(f"{self.crew_names[key]} : {value}")

    def _log_history(self):
        time_format = ""
        time_format += str(time.localtime().tm_yday)
        time_format += "_"
        time_format += str(time.localtime().tm_hour)
        time_format += "_"
        time_format += str(time.localtime().tm_min)
        time_format += "_"
        time_format += str(time.localtime().tm_sec)

        output = {"Total_rolls": 0}
        output["Roll_history"] = defaultdict(int)
        B = defaultdict(int)
        A = defaultdict(int)
        E = defaultdict(int)
        C = defaultdict(int)

        for t in self.roll_history.keys():
            output["Total_rolls"] += sum(self.roll_history[t].values())

            for key, value in self.roll_history[t].items():
                output["Roll_history"][key] += value
                crew_name = self.crew_names[key].split(maxsplit=1)
                if crew_name[0] == "(B)":
                    B[crew_name[1]] += value
                elif crew_name[0] == "(A)":
                    A[crew_name[1]] += value
                elif crew_name[0] == "(E)":
                    E[crew_name[1]] += value
                elif crew_name[0] == "(C)":
                    C[crew_name[1]] += value

        output["Basic_rolls"] = sum(B.values())
        output["Basic_crews"] = B

        output["Advanced_rolls"] = sum(A.values())
        output["Advanced_crews"] = A

        output["Elite_rolls"] = sum(E.values())
        output["Elite_crews"] = E

        output["Core_rolls"] = sum(C.values())
        output["Core_crews"] = C

        if len(self.roll_history_counts[13001]) > 0:
            output["Average_Grease"] = sum(self.roll_history_counts[13001]) / len(
                self.roll_history_counts[13001]
            )
            output["Grease_roll_counts"] = self.roll_history_counts[13001]
        if len(self.roll_history_counts[13002]) > 0:
            output["Average_Demo"] = sum(self.roll_history_counts[13002]) / len(
                self.roll_history_counts[13002]
            )
            output["Demo_roll_counts"] = self.roll_history_counts[13002]

        with open(
            f"{LOG_FOLDER}\\log_{time_format}.json",
            "w",
        ) as f:
            json.dump(output, f)

    def _set_defaults(self, thread_count):
        """
        Sets the uranium limit for rolling crews with headway to spare for multithreaded operations

        :param self: Description
        :param thread_count: Description
        """
        self.uranium_limit = thread_count * 1000 * 2
        for thread in range(0, thread_count):
            self.can_roll[thread] = (
                self.uranium_storage > self.uranium_limit and self.remaining_slots > 2
            )
            self.roll_history[thread] = defaultdict(int)
            self.last_gold_roll[thread] = defaultdict(int)

    def fill_crews(self, timeout, thread=0):
        while time.time() < timeout and self.remaining_slots > 2:
            if not self.can_roll[thread]:
                if self.uranium_storage > self.uranium_limit:
                    self.can_roll[thread] = True
                    # print(f"Resuming crews T-{thread}")
                else:
                    # print(f"Pausing crews T-{thread}")
                    time.sleep(5)
                    self._set_uranium()
                    continue

            crew_id, crew_id_long = self._roll_crew(thread=thread)
            if self.delete_last_roll[thread]:
                self._delete_crew(long_crew_id=crew_id_long)
                self.delete_last_roll[thread] = False
            else:
                self.roll_history[thread][crew_id] += 1
                self.status[crew_id] += 1
                self.status[0] += sum(self.roll_history[thread].values())
                self.roll_history[thread] = defaultdict(int)
                self.remaining_slots -= 1
                self._print_status()
                # self.roll_history_counts[crew_id].append(
                #     sum(self.roll_history[thread].values())
                #     - self.last_gold_roll[thread][crew_id]
                # )
                # self.last_gold_roll[thread][crew_id] = sum(
                #     self.roll_history[thread].values()
                # )

            self._set_uranium()
        # print(f"T-{thread} finished rolling")

    def flush_crews(self, blacklist=True):
        self._set_crews()
        for crew in self.crew_storage:
            if blacklist:
                if int(crew["crew_id"]) in self.blacklist:
                    self._delete_crew(crew["id"])
                    print(f'deleted {self.crew_names[int(crew["crew_id"])]}')
            else:
                self._delete_crew(crew["id"])
                print(f'deleted {self.crew_names[int(crew["crew_id"])]}')


class FleetManager:
    def __init__(self, session):
        self.session = session
        self.userid = config.configs["userid"]
        self.seed = config.seeds["base"]
        self.world_map_seed = config.seeds["world"]
        self.game_signed_request = config.configs["game_signed_request"]
        self.map_signed_request = config.configs["map_signed_request"]
        self.signed_request = config.configs["signed_request"]
        self.world_index = config.configs["world_index"]
        self.baseid = config.configs["baseid"]
        self.base_x = config.configs["base_x"]
        self.base_y = config.configs["base_y"]

        self.map_ids = {}
        self.ship_ids = defaultdict(str)
        self.claimed_targets = set()
        self.claim_lock = threading.Lock()
        self.repair_lock = threading.Lock()

        self.positions = {}
        self.pos_lock = threading.Lock()

        self.clock_map = {
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
        self._clock_unit = {}
        for h, (cx, cy) in self.clock_map.items():
            m = math.hypot(cx, cy) or 1.0
            self._clock_unit[h] = (cx / m, cy / m)

    def _calc_h_hn(self, params, seed, secure):
        hn = random.randint(0, 9999999)
        h = get_hash(seed, params, hn, secure)
        return hn, h

    def _generate_hash_string(self, params, action):
        """
        0 - launch\n\t ""
        1 - move\n\t "seed mapid mapReq worldindex"
        2 - locator  "count levels minhp types"
        3 - add/remove ship
        4 - repair fleet
        5 - instant rep
        """
        string = ""
        if action == 1:
            string += self.world_map_seed
            string += params["actions"]
            string += str(params["id"])
            string += params["map_signed_request"]
            string += str(params["worldindex"])
        elif action == 2:
            if params.get("campaignId", False):
                string += params["campaignId"]
            if params.get("count", False):
                string += params["count"]
            if params.get("levels", False):
                string += params["levels"]
            if params.get("minHealth", False):
                string += params["minHealth"]
            if params.get("types", False):
                string += params["types"]
        return string

    def _make_request(
        self,
        endpoint,
        params=None,
        payload=None,
        post=False,
        put=False,
        secure=True,
        action=0,
        base="kx",
    ):
        if params is None:
            params = {}

        if payload is None:
            payload = {}

        ts = int(time.time())

        if base == "kx":
            seed = self.seed
            domain = BASE_URL
            params.update(
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
            params.update(
                {
                    "game_signed_request": self.game_signed_request,
                    "map_signed_request": self.map_signed_request,
                }
            )

        if action == 2:
            param_string = self._generate_hash_string(payload, action)
        else:
            param_string = self._generate_hash_string(params, action)
        hn, h = self._calc_h_hn(param_string, seed, secure)
        if action == 2:
            payload.update(
                {
                    "hn": hn,
                    "h": h,
                }
            )
        else:
            params.update(
                {
                    "hn": hn,
                    "h": h,
                }
            )

        url = f"{domain}/{endpoint}"

        if post:
            if payload:
                if action == 0 or action == 5:
                    resp = self.session.post(url, params=params, json=payload)
                elif action == 2:
                    resp = self.session.post(url, params=params, data=payload)
            else:
                resp = self.session.post(url, params=params)
        elif put:
            resp = self.session.put(url, params=params, json=payload)
        else:
            resp = self.session.get(url, params=params)

        resp.raise_for_status()
        return resp.json()

    def _distance(self, fleet_id, target_x, target_y):
        last_x, last_y = self._get_position(fleet_id=fleet_id)
        delta_x = last_x - target_x
        delta_y = last_y - target_y
        return math.hypot(delta_x, delta_y)

    def _travel_time(self, distance, map_speed):
        return distance / (map_speed * 4)

    def _filter_by_distance(
        self, fecthed_targets, fleet_id, level=False, max_distance=30000
    ):
        targets = []
        for target in fecthed_targets["bookmarks"]:
            dist = self._distance(
                fleet_id=fleet_id,
                target_x=target["x"] * 100,
                target_y=target["y"] * 100,
            )

            if dist > max_distance:
                continue

            if level:
                if target["level"] == level:
                    targets.append((target["x"], target["y"], dist, target["id"]))
            else:
                targets.append((target["x"], target["y"], dist, target["id"]))

        if not targets:
            return None

        return sorted(targets, key=lambda target: target[2])

    def _claim_target(self, target_id):
        with self.claim_lock:
            if target_id in self.claimed_targets:
                return False
            self.claimed_targets.add(target_id)
            return True

    def _release_target(self, target_id):
        with self.claim_lock:
            self.claimed_targets.discard(target_id)

    def _pick_target(self, targets):
        for t in targets:
            if self._claim_target(t[3]):
                return t
        return None

    def _fetch_locator_targets(self, level, types):
        endpoint = "api/bm/bookmarks/npctargets"
        payload = {
            "count": "100",
            "levels": str(level),
            "minHealth": "100",
            "types": str(types),
        }
        return self._make_request(endpoint, payload=payload, action=2, post=True)

    def _vengence_targets(self, fleet_id):
        endpoint = "api/bm/bookmarks/vengeanceoutsector"
        payload = {}
        resp = self._make_request(endpoint, payload=payload, action=2, post=True)
        targets = {"bookmarks": []}
        for target in resp["bookmarks"]:
            if (
                target["rank"] == "3"
                or target["rank"] == "4"
                or (target["rank"] == "2" and target["level"] > 100)
            ):
                continue
            targets["bookmarks"].append(target)

        endpoint = "api/bm/bookmarks/vengeanceinsector"
        resp = self._make_request(endpoint, payload=payload, action=2, post=True)
        for target in resp["bookmarks"]:
            if (
                target["rank"] == "3"
                or target["rank"] == "4"
                or (target["rank"] == "2" and target["level"] > 100)
            ):
                continue
            targets["bookmarks"].append(target)
        return self._filter_by_distance(resp, fleet_id, False, 50000)

    def _get_approach_clock(self, fleet_id, target_x, target_y):
        last_x, last_y = self._get_position(fleet_id=fleet_id)

        tx = target_x * 100
        ty = target_y * 100

        # Vector from target to fleet's last known position
        dx = last_x - tx
        dy = last_y - ty
        mag = math.hypot(dx, dy)
        if mag < 1e-6:
            return 12

        ux, uy = dx / mag, dy / mag

        # Pick the clock whose unit vector has the largest dot product with (ux,uy)
        best_h = 12
        best_dot = -1.0
        for h, (cx, cy) in self._clock_unit.items():
            dot = ux * cx + uy * cy
            if dot > best_dot:
                best_dot = dot
                best_h = h
        return best_h

    def _pre_launch_payload(self, fleet_id):
        response = self.get_fleets()
        fleet_payload = {
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
                break

        return fleet_payload

    def _get_ship_ids(self, fleet_id):
        response = self.get_fleets()
        fleet_payload = {
            "ships": {},
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
                break
        if not self.ship_ids[fleet_id]:
            self.ship_ids[fleet_id] = fleet_payload
        return fleet_payload

    def _fleet_docked(self, fleet_id):
        response = self.get_fleets()
        for k, v in response.items():
            if k == "fleets":
                for fleet in v:
                    if fleet["id"] == fleet_id:
                        if fleet["is_on_map"]:
                            self.map_ids[fleet["id"]] = fleet["mapId"]
                        return fleet["is_on_map"] == False

    def _fleet_in_combat(self, fleet_id, map_speed):
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
            return str(combat_guid), int(engage_id), server_url
        return None, None, None

    def _update_position(self, fleet_id, x, y):
        with self.pos_lock:
            self.positions[fleet_id] = (x, y)

    def _get_position(self, fleet_id):
        with self.pos_lock:
            return self.positions.get(fleet_id, (self.base_x, self.base_y))

    def _manage_fleet(self, fleet_id, gs_fleet_id=False, fleet_layout=""):
        if gs_fleet_id:
            endpoint = f"dock/base/fleets/{gs_fleet_id}"
        else:
            endpoint = f"dock/base/fleets/{fleet_id}"
        payload = {"ships": {}}

        for flp in self.ship_ids.get(fleet_id).get("ships").keys():
            if flp not in fleet_layout:
                payload["ships"][flp] = {"id": None}
            else:
                payload["ships"][flp] = self.ship_ids[fleet_id]["ships"][flp]

        return self._make_request(endpoint, payload=payload, put=True, action=3)

    def _fuse(self, instance_id, source_id, amount):
        """
        Experimental.

        Loading a fuseable object inside a browser session,
        sending a fuse request through the help of the script,
        lastly coming back to the browser session and sending the fuse request leads to a bug/crash.

        Following the steps - double crafting can be achieved. This is logged as an error on the server side!
        USE WITH CAUTION

        :param self: Description
        :param source_id: Description
        :param amount: Description
        """
        endpoint = "base/transitions"
        payload = {
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
        return self._make_request(endpoint, payload=payload, post=True, action=5)

    def _start_campaign_encounter(
        self,
        level,
        fleet_id,
        gs_fleet_id,
        ship_count,
        map_speed,
        base_repair=False,
    ):
        level_template = []
        with open(level, "r") as f:
            for line in f.readlines():
                cmd_hex, delay_str = line.split(maxsplit=2)
                cmd_bytes = bytes.fromhex(cmd_hex)
                delay = float(delay_str)
                level_template.append((cmd_bytes, delay))

        combat_guid, engage_id, server_url = self._fleet_in_combat(
            fleet_id=fleet_id, map_speed=map_speed
        )

        websocket = self.start_engagement(
            combat_guid=combat_guid,
            engage_id=engage_id,
            user_id=self.userid,
            server_url=server_url,
            return_ws=True,
        )

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
                    ship_count=ship_count,
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

    def _handle_heartbeat(self, websocket, battle_end_event):
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

    def _ws_handshake(self, combat_guid: str, engage_id: int, user_id: int) -> str:
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
        ws = websocket.create_connection(
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

    def repair_fleet(self, fleet_id):
        endpoint = "dock/base/repair"
        payload = {"fleet": int(fleet_id)}
        return self._make_request(endpoint, payload=payload, put=True, action=4)

    def repair_speed_up(self, fleet_id):
        endpoint = "dock/base/repair/default"
        payload = {
            "fleet": fleet_id,
            "seconds": 300,
            "purchase_type": "free",
            "currency_id": 0,
            "quantity": 1,
        }
        return self._make_request(endpoint, payload=payload, post=True, action=5)

    def get_fleets(self):
        """Returns all docked/active fleets for this user."""
        endpoint = f"users/{self.userid}/dock/base/fleets"
        return self._make_request(endpoint)

    def launch(self, fleet_id):
        """
        Possible failure \n
        \t'success': False, 'error': 'Fleet is not in a launchable state'
        """
        fleet_id = str(fleet_id)
        if not self._fleet_docked(fleet_id):
            print("Fleet is locked / out in worldmap")
            return "Fleet is locked / out in worldmap"

        endpoint = f"dock/base/fleets/{fleet_id}"
        payload = self._pre_launch_payload(fleet_id)
        resp = self._make_request(endpoint, payload=payload, action=0, post=True)
        self._fleet_docked(fleet_id)
        # print(f"[Fleet-{fleet_id}] launched")
        return resp

    def move(
        self,
        fleet_id,
        x,
        y,
        map_speed,
        return_dock=False,
        attack=False,
        clock=False,
        engage_radius=100,
        in_combat_check=False,
    ):
        """
        param string for hash
        world_seed action mapid world_index
        """

        if clock:
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
        params = {
            "actions": action_string,
            "id": self.map_ids[fleet_id],
            "worldindex": self.world_index,
        }
        return self._make_request(
            endpoint,
            params=params,
            secure=False,
            action=1,
            base="web",
        )

    def lazy_repair(self, fleet_id, gs_fleet_id, ship_count):
        if not self._fleet_docked(fleet_id=fleet_id):
            print("Send fleet to dock first")
            time.sleep(25)

        if ship_count > 1 or fleet_id != gs_fleet_id:
            self._manage_fleet(fleet_id=fleet_id)
            time.sleep(2)

        fleet_layout = ""
        for i in range(1, ship_count + 1):
            fleet_layout += str(i)
            if ship_count > 1 or fleet_id != gs_fleet_id:
                self._manage_fleet(
                    fleet_id=fleet_id,
                    gs_fleet_id=gs_fleet_id,
                    fleet_layout=fleet_layout,
                )
                time.sleep(2)
            resp = self.repair_fleet(fleet_id=gs_fleet_id)
            repair_time = resp["complete_time"] - resp["currenttime"]
            if repair_time > 300:
                print(
                    f"[== Repair ==] [Fleet-{fleet_id}] Waiting {repair_time - 300} s"
                )
                time.sleep(repair_time - 300)
            time.sleep(1)
            self.repair_speed_up(fleet_id=gs_fleet_id)
            time.sleep(1)

        if fleet_id != gs_fleet_id:
            self._manage_fleet(
                fleet_id=fleet_id, gs_fleet_id=gs_fleet_id, fleet_layout=""
            )
            time.sleep(2)
            self._manage_fleet(fleet_id=fleet_id, fleet_layout=fleet_layout)

    def hunt_targets(
        self,
        fleet_id,
        gs_fleet_id,
        level,
        types,
        timeout,
        clock=12,
        map_speed=443.5,
        ship_count=5,
        target_template=False,
        base_repair=False,
    ):
        self._get_ship_ids(fleet_id=fleet_id)
        self.launch(fleet_id=fleet_id)
        time.sleep(2)

        level_template = []
        if target_template:
            with open(target_template, "r") as f:
                for line in f.readlines():
                    cmd_hex, delay_str = line.split(maxsplit=2)
                    cmd_bytes = bytes.fromhex(cmd_hex)
                    delay = float(delay_str)
                    level_template.append((cmd_bytes, delay))
        while time.time() < timeout:
            targets = self._filter_by_distance(
                fecthed_targets=self._fetch_locator_targets(level=level, types=types),
                fleet_id=fleet_id,
                level=level,
                max_distance=80000,
            )

            if not targets:
                print(f"[Fleet-{fleet_id}] Could not find targets close to base")
                time.sleep(60)
                continue

            target = self._pick_target(targets=targets)

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
                        # print(f"[Fleet-{fleet_id}] Battle ended and connection closed.")
                    else:
                        self.start_engagement(
                            combat_guid=combat_guid,
                            engage_id=engage_id,
                            user_id=self.userid,
                            server_url=server_url,
                        )

                time.sleep(2)
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
                print(f"[Fleet-{fleet_id}] {(timeout - time.time()) / 60 :f} min left")

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
                        ship_count=ship_count,
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


def test_entrace(fleet_id, map_speed, level, types, clock):
    fm._fleet_docked(fleet_id)
    targets = fm._filter_by_distance(
        fecthed_targets=fm._fetch_locator_targets(level=level, types=types),
        fleet_id=fleet_id,
        level=level,
    )
    target = fm._pick_target(targets=targets)
    fm.move(fleet_id, target[0] * 100, target[1] * 100, map_speed, False, False, clock)


def crew_scenario():
    """
    Sends out fleets [1-5], each containing a single ship that can destroy the Uranium target. Once all fleets are sent out, rolling for crews is slowly engaged.
    """
    tout = time.time() + 60 * 30
    for i in range(1, 6):
        threading.Thread(
            target=fm.hunt_targets,
            args=(str(i), str(i), 13, 343, tout, 12, 443.5, 1, False, False),
        ).start()
        time.sleep(15)

    cm._set_defaults(25)
    for i in range(20):
        threading.Thread(
            target=cm.fill_crews,
            args=(tout, i),
        ).start()
        time.sleep(1)


def camp_scenario(campaign_levels: list):
    """
    Experimental.
    Function accepts level templates for a campaign to be completed by fleet 1, the campaign must be started and a battle has to be engaged by the user.
    After those steps, the script can be continued and level is done following the template provided.

    :param campaign_levels: Description
    :type campaign_levels: list
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
                fm._start_campaign_encounter(
                    level=level,
                    fleet_id="1",
                    gs_fleet_id="1",
                    ship_count=1,
                    map_speed=406,
                    base_repair=False,
                )


if __name__ == "__main__":
    try:
        config.configs = config.configs_main
        SESSION = requests.Session()
        SESSION.headers.update(_get_headers())
        with SESSION:
            cm = CrewManager(SESSION)
            fm = FleetManager(SESSION)

            # Scenario can be created by calling the respective manager functions..

    except KeyboardInterrupt:
        print("shutdown. keyboard interput")
    # comment out if not on a windows platform
    except:
        print("Err")
        toast = Notification(
            app_id="Battle pirates script",
            title="Encountered error",
            msg="Unhandled exception occured.",
            duration="long",
        )
        toast.show()
