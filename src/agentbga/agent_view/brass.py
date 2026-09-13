"""Brass-only semantic projection; inputs have already passed seat privacy rules."""
from copy import deepcopy
from ..legal_action_query import MAX_REPLY_BYTES, reply_bytes


def table(items, columns):
    return {"columns": columns, "rows": [[item.get(k) for k in columns] for item in items]}


def compact_observation(observation, version):
    result = {key: deepcopy(value) for key, value in observation.items()
              if key not in {"board", "players", "implementation_status"}}
    result.update({
        "schema_version": "agentbga.brass-observation.v1", "state_version": version,
        "details": {"tool": "inspect", "inspect_ref": "observation",
                    "instruction": "Tables retain all rows. Use inspect_ref for full attributes, map topology and tile costs; follow next_cursor with the same ref."},
    })
    players = []
    for index, player in enumerate(observation["players"]):
        row = {key: deepcopy(value) for key, value in player.items()
               if key not in {"industry_stacks", "removed_industries", "discard", "hand"}}
        if player["seat"] == observation["viewer_seat"]:
            row["hand"] = deepcopy(player["hand"])
        stacks = [{"industry": kind, "remaining": len(tiles),
                   "next_level": tiles[0]["level"] if tiles else None}
                  for kind, tiles in player["industry_stacks"].items()]
        row["industry_stacks"] = table(stacks, ["industry", "remaining", "next_level"])
        row["industry_stacks"]["inspect_ref"] = f"observation/players/{index}/industry_stacks"
        row["discard_count"] = len(player["discard"])
        row["discard_ref"] = f"observation/players/{index}/discard"
        row["removed_count"] = len(player["removed_industries"])
        row["removed_ref"] = f"observation/players/{index}/removed_industries"
        players.append(row)
    result["players"] = players
    board = observation["board"]
    result["board"] = {
        "industries": table(board["industries"], ["id", "industry", "level", "owner", "location", "slot_id", "resources", "flipped", "vp", "link_icons", "beer_to_sell"]),
        "links": table(board["links"], ["connection_id", "owner", "era"]),
        "merchant_locations": deepcopy(board["merchant_locations"]),
        "locations_ref": "observation/board/locations",
        "connections_ref": "observation/board/connection_spaces",
    }
    for key in ("industries", "links"):
        result["board"][key]["inspect_ref"] = f"observation/board/{key}"
    # Defensive overflow: preserve the full global overview as a bounded resource,
    # and explicitly advertise its absence in the initial response. Never drop rows.
    if reply_bytes(result) > MAX_REPLY_BYTES:
        overview = result["board"]
        result["board"] = {"inspect_ref": "overview/board", "deferred": True,
                           "industry_count": len(board["industries"]), "link_count": len(board["links"]),
                           "instruction": "Inspect overview/board for the complete global board before choosing an action."}
        return result, overview
    return result, None


def resource_aliases(observation):
    aliases = {}
    for key, value in observation["board"].items():
        aliases[f"observation/board/{key}"] = value
    for index, player in enumerate(observation["players"]):
        for key in ("industry_stacks", "discard", "removed_industries"):
            aliases[f"observation/players/{index}/{key}"] = player[key]
    return aliases
