import math


def evade(Buffs: list, Alliance_bonus: bool = False, Lab_bonus: bool = False):
    """
    Total Evade = 1 - [(1 - Evade Buff A) x (1 - Evade Buff B) x etc]
    Args:
        Buffs (List): List containing evade buffs.
        Alliance (bool): Apply alliance 10% evade buff.
        Lab_bonus (bool): Apply Lab 20% evade buff.

    Returns:
        float: Calculated evade value.
    """
    Buffers = Buffs[:]
    if Alliance_bonus:
        Buffers.append(10)
    if Lab_bonus:
        Buffers.append(20)

    result = 1
    for b in Buffers:
        result *= 1 - b / 100

    return 1 - result


def damage_buff(Buffs: list, Conquest_yard_bonus: bool = False):
    """
    Total Damage Buff = (1 + Damage Buff A) x (1 + Damage Buff B) x etc - 1
    (this is the value you will see in the Attack tooltip of a ship or defense platform)
    Args:
        Buffs (List): List containing damage buffs.
        Conquest_yard_bonus (int): Apply 10% building damage bonus from conquest yard.

    Returns:
        float: Calculated damage buff.
    """
    Buffers = Buffs[:]
    if Conquest_yard_bonus:
        Buffers.append(10)

    result = 1
    for b in Buffers:
        result *= 1 + b / 100
    return result - 1


def projectile_damage(Base_damage: int, Salvo: int, Multishot: int, Damage_buffs: list):
    """
    Projectile Damage = (Base Damage / Salvo / Base Multishot) x (1 + Damage Buff A) x (1 + Damage Buff B) x etc
    Args:
        Base_damage (int): Base damage of combined weapon damage.
        Salvo (int): Salvo count of the weapon.
        Multishot (int): Multishot of the weapon.
        Damage_buffs (List): List containing damage buffs.

    Returns:
        float: Calculated damage buff.
    """

    return (Base_damage / Salvo / Multishot) * (damage_buff(Damage_buffs) + 1)


def weapon_range(Base_range: int, Buffs: list):
    """
    Total Weapon Range = Base Weapon Range x (1 + Damage Type Range Buff + Weapon Type Range Buff + Self Range Modifier)
    Args:
        Base_range (Int): Base weapon range.
        Buffs (List): List containing range buffs.

    Returns:
        float: Calculated range.
    """

    return Base_range * (1 + sum([buff / 100 for buff in Buffs]))


def cycle_time(
    Base_reload: float,
    Buffs: list,
    Rank_bonus: float = 0.75,
    Salvo: int = 1,
    Salvo_reload: float = 1,
):
    """
    Cycle Time = [Base Reload x (1 - Rank Bonus) / (1 + Reload Buff A + Reload Buff B)] + [(Salvo Count - 1) x Salvo Reload Time]
    Args:
        Base_reload (float): Base weapon reload time.
        Buffs (List): List containing reload buffs.
        Rank_bonus (float): Reload bonus provided by ship rank.
        Salvo (int): Salvo count of the weapon.
        Salvo_reload (float): Salvo reload time.

    Returns:
        float: Calculated reload, rounded up to the nearest 0.2 multiple.

    Example:
        A weapon with 5s reload speed, ranked to the max reload bonus of 75% would shoot roughly 4 times faster -> 5*(1 - 0.75) = 1.25s => 1.4s, rounded up to the nearest 0.2 multiple.
    """
    calculated_reload = Base_reload * (1 - Rank_bonus) / (
        1 + sum([buff / 100 for buff in Buffs])
    ) + ((Salvo - 1) * Salvo_reload)

    print(f"{calculated_reload:.2}")
    if calculated_reload % 0.2 != 0:
        return 0.2 + calculated_reload - calculated_reload % 0.2
    return calculated_reload


def defense(Buffs: list):
    """
    Total Defense = 1 - [(1 - Defense Buff A) x (1 - Defense Buff B) x etc]
    Args:
        Buffs (List): List containing defense buffs.

    Returns:
        float: Calculated defense value.
    """

    Buffers = Buffs[:]
    result = 1
    for b in Buffers:
        result *= 1 - b / 100

    return 1 - result


def defense_survival(Buffs: list):
    """
    Defense = 1 - [1 / (1 + Survival%A + Survival%B)]
    Args:
        Buffs (List): List containing survival buffs.

    Returns:
        float: Calculated survival defense value.
    """

    Buffers = Buffs[:]
    result = 1
    for b in Buffers:
        result += (b / 200) / 100

    return 1 - 1 / result


def damage_taken(Projectile_damage: float, Defense_buffs: list, Survival: float):
    """
    Damage Taken = (Projectile Damage - Deflection - Charged Armor) x (1 - Defense) / (1 + Survival % A + Survival % B)
    (Turret Defense and Splash Reduction are treated as survival)
    Args:
        Projectile_damage (float): Projectile damage.
        Defense_buffs (List): List containing defense buffs.
        Survival (float): Survival value of the ship.

    Returns:
        float: Calculated damage taken.
    """
    result = Projectile_damage * (1 - defense(Defense_buffs))
    if Survival:
        result /= 1 + Survival / 20_000

    return 1 - result


def repair_stats(Damage_times: list):
    """
    Calculates how much damage has been taken for each battle
    Args:
        Damage_times (List): List containing cummulative damage taken after each battle in this format (m.s). Example 7min 20s -> 7.20, 61min 59s -> 61.59

    Returns:
        List: Calculated damage taken in seconds for each battle.

    Example:
        An array [5.10, 10.15, 15.00], would return [310, 305, 285]
    """
    _ = Damage_times[:]
    _.insert(0, 0)
    result = []
    for i in range(len(_) - 1):
        sum_seconds_prev = math.ceil(math.floor(_[i]) * 60 + _[i] % 1 * 100)
        sum_seconds = math.ceil(math.floor(_[i + 1]) * 60 + _[i + 1] % 1 * 100)
        result.append(sum_seconds - sum_seconds_prev)

    return result


def repair_comparisson(Title: str, Params: list, *Data: list):
    """
    Prints a table to compare average, min, max repair times for different parameters.

    Args:
        Data (List): Lists of repair data to use for the table comparisson
        Params (List): List of parameters to be used in the table comparison. (row headers)
    """
    print()
    print("=" * 60)
    print(f"     {Title}     ")
    print("=" * 60)
    data = []
    for l in Data:
        if not l:
            data.append(["–", "–", "–", "–"])
            continue

        _ = repair_stats(l)
        _avg = f"{math.floor(sum(_)/len(_)/60)}m {math.floor(sum(_)/len(_)%60)}s"
        _min = f"{math.floor(min(_)/60)}m {min(_)%60}s"
        _max = f"{math.floor(max(_)/60)}m {max(_)%60}s"
        data.append([_avg, _min, _max, len(_)])

    headers = ["Average", "Min", "Max", "Targets"]
    parameters = Params[:]
    row_format = "{:>12}" * (len(headers) + 1)
    print(row_format.format("", *headers))
    for param, row in zip(parameters, data):
        print(row_format.format(param, *row))


if __name__ == "__main__":
    defenses = [
        "Balistic",
        "Explosive",
        "Penetrative",
        "Radioactive",
        "Concussive",
        "Corrosive",
    ]
