import json
from typing import TypedDict
import random
import time
import threading
from collections import defaultdict
from collections.abc import Mapping
import config
from SessionManager import SessionManager

BASE_URL = config.links["base_url"]


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

        if self.session_manager.resp_debug:
            # print(resp.text)
            print(new_params)
            print(new_payload)
            print(json.dumps(resp.json(), indent=1))

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

    def print_status(self, timeout: float):
        """
        Print information about the current crew roll session.
        """
        while time.time() < timeout:
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
            time.sleep(5)

    def set_defaults(self, thread_count: int):
        """
        Adjusts self.uranium_limit and self.remaining_slots in response to thread_count.

        Args:
            thread_count (int): The numbers of threads to use when rolling crews and setting limits.
        """
        self.uranium_limit *= thread_count * 1.2
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

    def flush_crews(self, blacklist: list[int]):
        """
        Delete crews from storage based on blacklist.

        Args:
            blacklist (list): Use a blacklist defined in config.py or provide your own, containing crew ids / types to delete from storage.
        """
        if not self.crew_storage:
            self._set_crews()
        for crew in self.crew_storage:
            if blacklist:
                if int(crew["crew_id"]) in blacklist:
                    self._delete_crew(int(crew["id"]))
                    print(f'deleted {self.crew_names[int(crew["crew_id"])]}')
            else:
                self._delete_crew(int(crew["id"]))
                print(f'deleted {self.crew_names[int(crew["crew_id"])]}')
