import math
from typing import Sequence


def evade(buffs: list[float], alliance_bonus: bool = False, lab_bonus: bool = False):
    """
    Total Evade = 1 - [(1 - Evade Buff A) x (1 - Evade Buff B) x etc]

    Args:
        buffs (List): List containing evade buffs.
        alliance_bonus (bool): Apply alliance 10% evade buff.
        lab_bonus (bool): Apply Lab 20% evade buff.

    Returns:
        evade (float): Calculated evade value.
    """
    buffers = buffs[:]
    if alliance_bonus:
        buffers.append(10)
    if lab_bonus:
        buffers.append(20)

    result = 1
    for b in buffers:
        result *= 1 - b / 100

    return 1 - result


def damage_buff(buffs: list[float], conquest_yard_bonus: bool = False):
    """
    Total Damage Buff = (1 + Damage Buff A) x (1 + Damage Buff B) x etc - 1
    (this is the value you will see in the Attack tooltip of a ship or defense platform)

    Args:
        buffs (List): List containing damage buffs.
        conquest_yard_bonus (int): Apply 10% building damage bonus from conquest yard.

    Returns:
        buff (float): Calculated damage buff.
    """
    buffers = buffs[:]
    if conquest_yard_bonus:
        buffers.append(10)

    result = 1
    for b in buffers:
        result *= 1 + b / 100
    return result - 1


def projectile_damage(
    base_damage: int, salvo: int, multishot: int, damage_buffs: list[float]
):
    """
    Projectile Damage = (Base Damage / Salvo / Base Multishot) x (1 + Damage Buff A) x (1 + Damage Buff B) x etc

    Args:
        base_damage (int): Base damage of combined weapon damage.
        salvo (int): salvo count of the weapon.
        multishot (int): multishot of the weapon.
        damage_buffs (List): List containing damage buffs.

    Returns:
        damage (float): Calculated damage after applying modifiers.
    """

    return (base_damage / salvo / multishot) * (damage_buff(damage_buffs) + 1)


def weapon_range(base_range: int, buffs: list[float]):
    """
    Total Weapon Range = Base Weapon Range x (1 + Damage Type Range Buff + Weapon Type Range Buff + Self Range Modifier)

    Args:
        base_range (Int): Base weapon range.
        buffs (List): List containing range buffs.

    Returns:
        range (float): Calculated range.
    """

    return base_range * (1 + sum([buff / 100 for buff in buffs]))


def cycle_time(
    base_reload: float,
    buffs: list[float],
    rank_bonus: float = 0.75,
    salvo: int = 1,
    salvo_reload: float = 1,
):
    """
    Cycle Time = [Base Reload x (1 - Rank Bonus) / (1 + Reload Buff A + Reload Buff B)] + [(salvo Count - 1) x salvo Reload Time]

    Args:
        base_reload (float): Base weapon reload time.
        buffs (List): List containing reload buffs.
        rank_bonus (float): Reload bonus provided by ship rank.
        salvo (int): salvo count of the weapon.
        salvo_reload (float): salvo reload time.

    Returns:
        reload (float): Calculated reload, rounded up to the nearest 0.2 multiple.

    Example:
        A weapon with 5s reload speed, ranked to the max reload bonus of 75% would shoot roughly 4 times faster -> 5*(1 - 0.75) = 1.25s => 1.4s, rounded up to the nearest 0.2 multiple.
    """
    calculated_reload = base_reload * (1 - rank_bonus) / (
        1 + sum([buff / 100 for buff in buffs])
    ) + ((salvo - 1) * salvo_reload)

    if calculated_reload % 0.2 != 0:
        return 0.2 + calculated_reload - calculated_reload % 0.2
    return calculated_reload


def defense(buffs: list[float]):
    """
    Total Defense = 1 - [(1 - Defense Buff A) x (1 - Defense Buff B) x etc]

    Args:
        buffs (List): List containing defense buffs.

    Returns:
        defense (float): Calculated defense value.
    """

    buffers = buffs[:]
    result = 1
    for b in buffers:
        result *= 1 - b / 100

    return 1 - result


def defense_survival(buffs: list[float]):
    """
    Defense = 1 - [1 / (1 + Survival%A + Survival%B)]

    Args:
        buffs (List): List containing survival buffs. Or total survival as a single item list.

    Returns:
        defense (float): Calculated defense value.

    Example:
        Calling the function with a single item list **defense_survival([1_500_000])**, is the same as **defense_survival([700_000, 800_000])**.
    """

    buffers = buffs[:]
    result = 1
    for b in buffers:
        result += (b / 200) / 100

    return 1 - 1 / result


def damage_taken(projectile_damage: float, defense_buffs: list[float], survival: float):
    """
    Damage Taken = (Projectile Damage - Deflection - Charged Armor) x (1 - Defense) / (1 + Survival % A + Survival % B)
    (Turret Defense and Splash Reduction are treated as survival)

    Args:
        projectile_damage (float): Projectile damage.
        defense_buffs (List): List containing defense buffs.
        survival (float): Survival value of the ship.

    Returns:
        damage (float): Calculated damage taken.
    """
    result = projectile_damage * (1 - defense(defense_buffs))
    if survival:
        result /= 1 + survival / 20_000

    return 1 - result


def repair_stats(damage_times: Sequence[float | int], raw_seconds: bool = False):
    """
    Calculates how much damage has been taken for each battle

    Args:
        damage_times (List): List containing cummulative damage taken after each battle in this format (m.s). Example 7min 20s -> 7.20, 61min 59s -> 61.59
        raw_seconds (bool): Consider List format in seconds 7min 20s -> 420.

    Returns:
        rep_times (List): Calculated damage taken in seconds for each battle.

    Example:
        An array [5.10, 10.15, 15.00], would return [310, 305, 285]
    """

    _ = list(damage_times)
    _.insert(0, 0)
    result: list[int] = []
    for i in range(len(_) - 1):
        if raw_seconds:
            result.append(int(_[i + 1] - _[i]))
        else:
            sum_seconds_prev = math.ceil(math.floor(_[i]) * 60 + _[i] % 1 * 100)
            sum_seconds = math.ceil(math.floor(_[i + 1]) * 60 + _[i + 1] % 1 * 100)
            result.append(sum_seconds - sum_seconds_prev)

    return result


def repair_comparisson(
    title: str, params: list[str], raw_seconds: bool, *data: Sequence[float | int]
):
    """
    Prints a table to compare average, min, max repair times for different parameters.

    Args:
        title (str): Title of the table.
        params (List): List of parameters to be used in the table comparison. (row headers)
        data (List): Lists of repair data (rows) to use for the comparisson
        raw_seconds (bool): Rep time sequences are in seconds format.
    """
    print()
    print("=" * 60)
    print(f"     {title}     ")
    print("=" * 60)
    table_data: list[list[str]] = []
    for l in data:
        if not l:
            table_data.append(["–", "–", "–", "–"])
            continue

        _ = repair_stats(l, raw_seconds)
        _avg = f"{math.floor(sum(_)/len(_)/60)}m {math.floor(sum(_)/len(_)%60)}s"
        _min = f"{math.floor(min(_)/60)}m {min(_)%60}s"
        _max = f"{math.floor(max(_)/60)}m {max(_)%60}s"
        table_data.append([_avg, _min, _max, str(len(_))])

    headers = ["Average", "Min", "Max", "Targets"]
    parameters = params[:]
    row_format = "{:>12}" * (len(headers) + 1)
    print(row_format.format("", *headers))
    for param, row in zip(parameters, table_data):
        print(row_format.format(param, *row))

    print()


if __name__ == "__main__":
    defenses = [
        "Balistic",
        "Explosive",
        "Penetrative",
        "Radioactive",
        "Concussive",
        "Corrosive",
    ]
