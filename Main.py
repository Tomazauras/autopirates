import threading
import time
from SessionManager import SessionManager
from CrewManager import CrewManager
from FleetManager import FleetManager
from BaseManager import BaseManager


def crew_scenario():
    """
    Sends out fleets [1-5] to hunt uranium targets, each containing a single ship that can destroy the uranium target. Once all fleets are sent out, 20 Threads are inniated to roll for crews.
    """
    tout = time.time() + 60 * 20
    threads: list[threading.Thread] = []
    for i in range(1, 6):
        t = threading.Thread(
            target=fm.hunt_targets,
            args=(str(i), str(i), "13", "343", "1", tout, 12, 443.5, False, False),
        )
        threads.append(t)
        t.start()
        time.sleep(15)

    for i in range(6, 8):
        t = threading.Thread(
            target=fm.hunt_targets,
            args=(
                str(i),
                str(i),
                "13",
                "343",
                "1",
                tout,
                12,
                406.25,
                False,
                False,
            ),
        )
        threads.append(t)
        t.start()
        time.sleep(5)

    threading.Thread(
        target=cm.print_status,
        args=(tout,),
    ).start()
    cm.set_defaults(40)
    for i in range(40):
        threading.Thread(
            target=cm.fill_crews,
            args=(tout, i),
        ).start()
        time.sleep(0.2)

    for t in threads:
        t.join()

    for i in range(1, 8):
        fm.lazy_repair(str(i), str(i))
        fm.manage_fleet(str(i), "", "")


if __name__ == "__main__":
    try:
        sm = SessionManager()
        with sm.session:
            cm = CrewManager(session_manager=sm)
            fm = FleetManager(session_manager=sm)
            bm = BaseManager(session_manager=sm)

            # Scenario can be created by calling the respective manager functions..

    except KeyboardInterrupt:
        print("shutdown. keyboard interput")
