"""Mechanical transcription of the 72 base tiles (publisher tile list, p. 22).

Edges run N/E/S/W. Field ports run clockwise: NW, NE on the north
edge, EN, ES, SE, SW, WS, WN. A road separates the two ports of its
edge; a city occupies the whole edge. Feature IDs stay local to a tile
when it rotates. Artwork and decorative gardens are not game data.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache


SOURCE = "https://cdn.svc.asmodee.net/production-zman/uploads/2024/10/Carcassonne-Big-Box-Rulebook.pdf"


def _tile(count, cities=(), roads=(), fields=(), *, shield=False, monastery=False):
    features = []
    for kind, groups in (("city", cities), ("road", roads)):
        for i, edges in enumerate(groups):
            features.append({"id": f"{kind[0]}{i}", "kind": kind, "ports": list(edges),
                             "shields": int(shield and kind == "city" and i == 0)})
    for i, (ports, adjacent) in enumerate(fields):
        features.append({"id": f"f{i}", "kind": "field", "ports": list(ports),
                         "cities": [f"c{j}" for j in adjacent], "shields": 0})
    if monastery:
        features.append({"id": "m0", "kind": "monastery", "ports": [], "shields": 0})
    edges = ["field"] * 4
    for feature in features:
        if feature["kind"] in ("city", "road"):
            for edge in feature["ports"]:
                edges[edge] = feature["kind"]
    return {"count": count, "edges": edges, "features": features}


# Orientations match the publisher's A-X reference chart, not a sorted edge code.
CATALOG = {
    "A": _tile(2, roads=((2,),), fields=((range(8), ()),), monastery=True),
    "B": _tile(4, fields=((range(8), ()),), monastery=True),
    "C": _tile(1, cities=((0, 1, 2, 3),), shield=True),
    "D": _tile(4, cities=((0,),), roads=((1, 3),), fields=(((2, 7), (0,)), ((3, 4, 5, 6), ()))),
    "E": _tile(5, cities=((0,),), fields=(((2, 3, 4, 5, 6, 7), (0,)),)),
    "F": _tile(2, cities=((1, 3),), fields=(((0, 1), (0,)), ((4, 5), (0,))), shield=True),
    "G": _tile(1, cities=((1, 3),), fields=(((0, 1), (0,)), ((4, 5), (0,)))),
    "H": _tile(3, cities=((1,), (3,)), fields=(((0, 1, 4, 5), (0, 1)),)),
    "I": _tile(2, cities=((0,), (3,)), fields=(((2, 3, 4, 5), (0, 1)),)),
    "J": _tile(3, cities=((0,),), roads=((1, 2),), fields=(((2, 5, 6, 7), (0,)), ((3, 4), ()))),
    "K": _tile(3, cities=((0,),), roads=((2, 3),), fields=(((2, 3, 4, 7), (0,)), ((5, 6), ()))),
    "L": _tile(3, cities=((0,),), roads=((1,), (2,), (3,)),
               fields=(((2, 7), (0,)), ((3, 4), ()), ((5, 6), ()))),
    "M": _tile(2, cities=((0, 1),), fields=(((4, 5, 6, 7), (0,)),), shield=True),
    "N": _tile(3, cities=((0, 1),), fields=(((4, 5, 6, 7), (0,)),)),
    "O": _tile(2, cities=((0, 3),), roads=((1, 2),),
               fields=(((2, 5), (0,)), ((3, 4), ())), shield=True),
    "P": _tile(3, cities=((0, 3),), roads=((1, 2),), fields=(((2, 5), (0,)), ((3, 4), ()))),
    "Q": _tile(1, cities=((0, 1, 3),), fields=(((4, 5), (0,)),), shield=True),
    "R": _tile(3, cities=((0, 1, 3),), fields=(((4, 5), (0,)),)),
    "S": _tile(2, cities=((0, 1, 3),), roads=((2,),),
               fields=(((4,), (0,)), ((5,), (0,))), shield=True),
    "T": _tile(1, cities=((0, 1, 3),), roads=((2,),), fields=(((4,), (0,)), ((5,), (0,)))),
    "U": _tile(8, roads=((0, 2),), fields=(((1, 2, 3, 4), ()), ((0, 5, 6, 7), ()))),
    "V": _tile(9, roads=((2, 3),), fields=(((5, 6), ()), ((0, 1, 2, 3, 4, 7), ()))),
    "W": _tile(4, roads=((1,), (2,), (3,)), fields=(((0, 1, 2, 7), ()), ((3, 4), ()), ((5, 6), ()))),
    "X": _tile(1, roads=((0,), (1,), (2,), (3,)),
               fields=(((1, 2), ()), ((3, 4), ()), ((5, 6), ()), ((7, 0), ()))),
}
TILES = {f"{code}-{i}": code for code, tile in CATALOG.items() for i in range(1, tile["count"] + 1)}
START_TILE = "D-1"


@lru_cache(maxsize=96)
def oriented(code: str, rotation: int) -> dict:
    """Internal read-only geometry; callers publishing it must copy it."""
    tile = deepcopy(CATALOG[code])
    tile["edges"] = [tile["edges"][(i - rotation) % 4] for i in range(4)]
    for feature in tile["features"]:
        field = feature["kind"] == "field"
        feature["ports"] = sorted((p + rotation * (2 if field else 1)) % (8 if field else 4)
                                  for p in feature["ports"])
    return tile
