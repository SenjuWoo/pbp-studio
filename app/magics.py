# PBP Studio -- magic move-sets for custom characters.
# Source of truth: ordered magic name table inside castle.exe (verified by extracting the
# string block at 0x1c6100..0x1c6300 of the shipped game executable). The XML field
# <magictype> in pbp.xml indexes this list. "Default Magic" fits index 1, which is exactly
# what the shipped template (data/pbplocal/violet/pbp.xml) carries, so the list is 0-based.
# The in-game chooser shows 26 of these; "Default Magic" and "Blaster" are internal/hidden.
# NOTE: pending live confirmation -- pick a magic in-game once and compare pbp.xml after.

MAGIC_TABLE = [
    (0, "Poison"),
    (1, "Default Magic"),
    (2, "Ice"),
    (3, "Lightning"),
    (4, "Bomb A"),
    (5, "Fire"),
    (6, "Knife A"),
    (7, "Barbaric"),
    (8, "Bee"),
    (9, "Buzzsaw"),
    (10, "Healing"),
    (11, "Blaster"),
    (12, "Vine B"),
    (13, "Vine A"),
    (14, "Bomb B"),
    (15, "Sand"),
    (16, "Knife C"),
    (17, "Knife B"),
    (18, "Necrotic"),
    (19, "Wind"),
    (20, "Dark"),
    (21, "Lava"),
    (22, "Smoke"),
    (23, "Snow"),
    (24, "Smith"),
    (25, "Pink"),
    (26, "Paint"),
    (27, "BattleBlock"),
]

# The order the in-game "Choose Magic" grid displays (page 1 then page 2, verified from the
# DLC screenshots): only these are offered for custom characters.
UI_ORDER = [
    "Poison", "Lightning", "Ice", "Fire",
    "Bomb A", "Bomb B", "Barbaric", "Buzzsaw",
    "Knife A", "Knife B", "Knife C", "Bee",
    "Vine A", "Vine B", "Sand", "Wind",
    "Lava", "Snow", "Dark", "Smoke",
    "Healing", "Necrotic", "Pink", "Smith",
    "BattleBlock", "Paint",
]

_BY_NAME = {name: idx for idx, name in MAGIC_TABLE}


def magic_number(name: str) -> int:
    """pbp.xml <magictype> value for a magic display name."""
    return _BY_NAME[name]


def ui_magics():
    """[(number, name)] in the in-game chooser order, ready for the UI grid."""
    return [(_BY_NAME[n], n) for n in UI_ORDER]


if __name__ == "__main__":
    for num, name in ui_magics():
        print(num, name)
    assert magic_number("Default Magic") == 1  # matches shipped violet template
