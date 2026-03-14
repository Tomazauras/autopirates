import json
from typing import Any, TypedDict
import random
import time
from collections.abc import Mapping
import config
from SessionManager import SessionManager

BASE_URL = config.links["base_url"]


class BaseManager:
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
        self.signed_request = config.cookies["signed_request"]
        self.userid = config.user["userid"]
        self.baseid = config.user["baseid"]

        self.rocket_storage: list[BaseManager.Rocket] = []
        self._set_rockets()

    class Rocket(TypedDict):
        completeTime: int
        completed: bool
        itemCode: int
        ready: int
        rocketId: int
        startTime: int
        usedTime: int | None
        userid: int

    def _generate_hash_string(
        self,
        params: Mapping[
            str,
            str | int | float | list[str | dict[str, str | int | dict[str, int]]],
        ],
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
            string += str(new_params["completeTime"])
            string += str(new_params["itemCode"])
            string += str(new_params["startTime"])
        elif action == 2:
            string += str(new_params["expectedGold"])
            string += str(new_params["rocketId"])
            string += str(new_params["seconds"])
        elif action == 4:
            string += str(new_params["listing_id"])
        return string

    def _make_request(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        payload: Mapping[str, Any],
        post: bool,
        put: bool,
        secure: bool,
        action: int,
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
                        -1 - fuse item, build ship
                        1 - build rocket
                        2 - instant rocket
                        3 - setRockets
                        4 - Fm claim
            base (str): Is request for Base (kx) or Worldmap.

        Returns:
            resp (dict): Response data in json format.
        """
        new_params = dict(params)
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

        if action == 1 or action == 2 or action == 4:
            param_string = self._generate_hash_string(params=payload, action=action)
        else:
            param_string = self._generate_hash_string(params=new_params, action=action)

        hn = random.randint(0, 9999999)
        h = self.session_manager.get_hash(
            seed=seed, params_string=param_string, random_seed=hn, secure=secure
        )

        new_payload = dict(payload)
        if action == 1 or action == 2 or action == 4:
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
                if action == 0:
                    resp = self.session_manager.session.post(
                        url, params=new_params, json=new_payload
                    )
                elif action == 1 or action == 2 or action == 4:
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

        if self.session_manager.resp_debug:
            # print(resp.text)
            print(new_params)
            print(new_payload)
            print(
                json.dumps(
                    resp.json(),  # pyright: ignore[reportPossiblyUnboundVariable]
                    indent=1,
                )
            )

        resp.raise_for_status()  # pyright: ignore[reportPossiblyUnboundVariable]
        return resp.json()  # pyright: ignore[reportPossiblyUnboundVariable]

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
        endpoint = config.links["fuse"]
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
            action=-1,
        )

    def _fm_redeem(self, listing_id: str):
        """
        Redeem a forsaken mission listing

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["fm_redeem"]
        payload: dict[str, str] = {
            "listing_id": listing_id,
        }
        return self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=True,
            put=False,
            secure=True,
            action=4,
        )

    def _fetch_event_schedule(self):
        """
        Fetch event data

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["event_schedule"]
        return self._make_request(
            endpoint=endpoint,
            params={},
            payload={},
            post=False,
            put=False,
            secure=True,
            action=5,
        )

    def claim_fm_store(self):
        """
        Buy out everything in the fm store
        """
        _resp = self._fetch_event_schedule()
        _fm_listings = (
            _resp.get("data", {})
            .get("forsaken_mission", {})
            .get("feb_run_2026", {})
            .get("listings", {})
        )
        _max = 0
        for _ in _fm_listings:
            if str(_).startswith("fm/"):
                _max = max(_max, len(_))

        for listing in _fm_listings:
            if str(listing).startswith("fm/"):
                _ = 0
                while True:
                    resp = self._fm_redeem(str(listing))
                    if not resp.get("success", False) or resp.get("error", 0):
                        break
                    _ += 1
                if _ > 0:
                    print(f"claimed [{listing:<{_max}}] times-[ {_} ]")

    def _set_rockets(self):
        """
        Fetch rocket storage

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["rocket_read"]
        resp = self._make_request(
            endpoint=endpoint,
            params={},
            payload={},
            post=True,
            put=False,
            secure=True,
            action=3,
        )
        self.rocket_storage = resp["data"]
        return resp

    def build_rocket(self, rocket: str):
        """
        Start building a rocket.
        Available rockets: quick pinch [1-4], long pinch [1-4]

        Args:
            rocket (str): Name of rocket in this format: rocket_name_level.

        Example:
            Example rocket = q_pinch_1 to start building quick pinch 1 or l_pinch_4 for long pinch 4 etc.

        Returns:
            resp (dict): Response data in json format.
        """

        endpoint = config.links["rocket_build"]
        ts = int(time.time())
        _: dict[str, int] = config.rockets[rocket]
        if not _:
            return print(
                f"failed to fetch rocket info from config, for rocket-[{rocket}]"
            )
        payload = {
            "completeTime": ts + _.get("build_time", 0),
            "itemCode": _.get("item_code", 0),
            "startTime": ts,
        }

        return self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=True,
            put=False,
            secure=True,
            action=1,
        )

    def rocket_speed_up(self):
        """
        Send a rocket speed up request for the curently building rocket. Used when an ongoing build is less than 5 minutes from completion.

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["rocket_spd"]
        rocket = None
        for r in self.rocket_storage:
            if not r["completed"]:
                rocket = r
        if rocket is None:
            print("No rocket is currently being built.")
            return False
        if rocket["completeTime"] - int(time.time()) > 300:
            print(
                f"Wait [{rocket["completeTime"] - int(time.time())-300}]s before trying speedup"
            )
            return False
        payload: Mapping[str, int] = {
            "expectedGold": 0,
            "rocketId": rocket["rocketId"],
            "seconds": rocket["completeTime"] - int(time.time()),
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

    def build_ship(
        self,
        refit: bool,
        ship_id: str,
        payload: Mapping[
            str, bool | int | list[int] | Mapping[str, str | dict[str, int]]
        ],
    ):
        """
        Build or refit a ship in regular yard

        Some notes...
        In this context illegal - item that is meant to be used on a different ship, or should is not available to equip using regular methods.

        If a cic slot is available for the ship, you can equip illegal cics
        Same is true for officers
        Duplicate officers can not be equipped on a hull, sometimes the same is true for cics. Depending if it's a cic meant for a regular ship or a dreadnought.

        You can equip illegal class weapons on a weapon slot regarless of weapon base class.
        Example, equiping multiform missile on a worldeater ship

        Returns:
            resp (dict): Response data in json format.
        """
        endpoint = config.links["build_ship"]
        if refit:
            endpoint += f"/{ship_id}"
        else:
            endpoint += f"/0"

        return self._make_request(
            endpoint=endpoint,
            params={},
            payload=payload,
            post=False,
            put=True,
            secure=True,
            action=-1,
        )
