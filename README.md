# Battle pirates Auto script

The python script is meant to automate specific elements of the game. Saving You time by not needing to do repetitive and boring tasks. This includes: crew rolling, target hunting, at base fleet repairing.

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install the required libraries.

```bash
pip install requests websocket-client
```

## Usage

Before starting the script, variables inside **./config.py** must be set. The variables can be accessed/extracted by inspecting network traffic, while having the game open inside a browser.

```python
seeds = {
    # Set once ↓
    "world": "",
    # Reset weekly ↓
    "base": "",
}

configs_main = {
    # Set once ↓
    "userid": 0,
    "baseid": 0,
    # Reset after every relocation ↓
    "base_x": 0,
    "base_y": 0,
    "world_index": 0,
    # Reset after every game refresh ↓
    "phpsessid": "",
    "signed_request": "",
    "game_signed_request": "",
    "map_signed_request": "",
}
```

To populate **_world_index_**, **_map_signed_request_** variables:

1. Go to worldmap and launch a fleet.
2. Inspect element the page, navigate to network tab and start recording traffic.
3. Select a fleet and move it.
4. Look for request **_updateMapObjects2_** in network logs.
5. Inside the request url you will find the 2 variables.

To populate the other **_configs_main_** variables:

1. Go to worldmap and launch a fleet.
2. Inspect element the page, navigate to network tab and start recording traffic.
3. Go to base.
4. Look for request **_api/bm/base/load?_** in network logs.
5. Inside the request url you will find **_signed_request_**, **_game_signed_request_** variables.
6. In response headers, under "_set-cookie_" you will find **_PHPSESSID_**.
7. The rest of the variables can be found in the request response.

To populate **_seeds_** variables:

8. Find the requests "_call stack_" / "_initiators_" section.
9. Look for a call stack that has/starts with "_.dispatchRequest_", it should point to a line of code "_BattlePirates.js:xxx_", "xxx" - line. Go to that line of code. Inside the function look for "**null != n ? n : "111aaaaaaa11a1a1a11a1a1a1a1a11a1"**". The long string of numbers and letter will be the **_world_** variable inside of **_seeds_**. In this case it's "111aaaaaaa11a1a1a11a1a1a1a1a11a1".
10. Similar to step 9, look for a call stack that has "_.getBase_". Go to the function, inside the function, you should see something similar - "**ja.loadRequest(... + "api/bm/base/load", "aaaaaaaaaaaaaabbbb33333355555aa", ... ,c, d)**". Similar to step 9, the long string of numbers and letter will be the **_base_** variable inside of **_seeds_**. In this case it's "aaaaaaaaaaaaaabbbb33333355555aa".

After these variables are set and a user defined scenario is described, the script can be started.

```python
# starts the script
python .\BP_fleet_manager.py
```

## Example

```python
# An example of a user defined scenario.
# Set timeout to 50 minutes from now
tout = time.time() + 60 * 50
# Get Demolition crew from storage
demo = cm._pick_crew(crew_id=13002)
# Assign crew to fleet 1
cm._assign_crew(long_crew_id=demo["id"], fleet_id="1")
# Assign fleet 1 to hunt level 51 targets
fm.hunt_targets(
    fleet_id="1",
    gs_fleet_id="1",
    level=51,
    types=720,
    timeout=tout,
    clock=6,
    map_speed=125,
    ship_count=5,
    target_template=False,
    base_repair=True,
)
# Delete the crew that was assigned to fleet 1
cm._release_crew(crew=demo)
```
