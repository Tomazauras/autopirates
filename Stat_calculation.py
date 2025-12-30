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


def weapon_range(Base_range: int, Buffs: list):
    """
    Total Weapon Range = Base Weapon Range x (1 + Damage Type Range Buff + Weapon Type Range Buff + Self Range Modifier)
    Args:
        Base_range (Int): Base Weapon Range.
        Buffs (List): List containing range buffs.

    Returns:
        float: Calculated range.
    """
    return Base_range * (1 + sum([buff / 100 for buff in Buffs]))


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


def damage_taken(Projectile_damage: float, Defense_buffs: float, Survival: float):
    """
    Damage Taken = (Projectile Damage - Deflection - Charged Armor) x (1 - Defense) / (1 + Survival % A + Survival % B)
    (Turret Defense from {proj2} takeSplash Reduction are treated as survival)
    Args:
        Projectile_damage (Int): Base Weapon Range.
        Buffs (List): List containing range buffs.

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
    """
    _ = Damage_times[:]
    _.insert(0, 0)
    result = []
    for i in range(len(_) - 1):
        sum_seconds_prev = math.ceil(math.floor(_[i]) * 60 + _[i] % 1 * 100)
        sum_seconds = math.ceil(math.floor(_[i + 1]) * 60 + _[i + 1] % 1 * 100)

        result.append(sum_seconds - sum_seconds_prev)

    return result


def repair_comparisson(Title: str, Crews: list, *Data: list):
    """
    Prints a table to compare average, min, max repair times for different parameters.

    Args:
        Data (List): Lists of repair data to use for the table comparisson

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
    crews = Crews[:]
    row_format = "{:>12}" * (len(headers) + 1)
    print(row_format.format("", *headers))
    for crew, row in zip(crews, data):
        print(row_format.format(crew, *row))


if __name__ == "__main__":
    print()
    # gold cap base
    auto_ss = [
        29.30,
        55.56,
        82.49,
        111.13,
        119.19,
        140.02,
        165.43,
        176.18,
        188.43,
        215.29,
        242.40,
        253.59,
        274.04,
        293.13,
        318.01,
    ]
    # Silver cap base
    auto_ss2 = [
        20.15,
        46.40,
        72.21,
        97.21,
        106.09,
        139.44,
        167.37,
        184.32,
        213.47,
        226.28,
        257.06,
        282.11,
        310.33,
    ]
    # Bronze cap base
    auto_ss3 = [
        26.45,
        48.54,
        62.35,
        85.52,
        111.32,
        124.28,
        146.18,
        170.09,
        192.39,
        206.37,
        235.06,
        262.03,
        289.12,
        316.02,
    ]

    # gold cap evade
    auto_ss_e = [
        18.21,
        43.08,
        64.29,
        85.37,
        107.56,
        133.04,
        156.41,
        180.17,
        208.24,
        232.40,
        257.13,
        269.21,
        297.50,
        311.59,
    ]

    repair_comparisson(
        "Repair times (Auto)",
        [
            "Base ↓",
            "SS (Gold)",
            "SS (Silver)",
            "SS (Bronze)",
            "Extra Ev ↓",
            "SS (Gold)",
        ],
        [],
        auto_ss,
        auto_ss2,
        auto_ss3,
        [],
        auto_ss_e,
    )
