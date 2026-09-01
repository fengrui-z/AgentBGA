"""Compact, engine-aligned Ark Nova rules exposed to agent harnesses.

This is not a replacement for legality generation.  It explains the stable
rules behind the engine-issued choices so models do not have to reverse
engineer the game from action IDs.  Card-specific requirements and effects
remain available through ``inspect_card``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_TOPICS: dict[str, dict[str, Any]] = {
    "core": {
        "title": "Core turn and Action-card rules",
        "rules": [
            "Choose one Action card. Its slot (1-5), plus spent X-tokens, is the action strength; upgrading a card changes its rules but does not add strength.",
            "After the action finishes, the chosen Action card moves to slot 1 and the cards previously below it shift one slot to the right.",
            "Instead of using an Action card, you may take 1 X-token (maximum 5); the selected Action card still moves to slot 1.",
            "Legal actions are authoritative for the current state. Use inspect_rules for general rules and inspect_card for a visible card's printed requirements, terrain, icons, and effects; do not infer omitted rules from an action ID.",
        ],
    },
    "cards": {
        "title": "Cards Action I / II",
        "shared": [
            "A normal draw execution advances the Break marker 2 spaces.",
            "Snap takes exactly 1 card from any display position, costs no money, ignores printed card cost, and replaces the normal draw/discard sequence.",
            "The display refills only after the whole action finishes.",
        ],
        "side_I_by_strength": {
            "1": "draw 1, then discard 1",
            "2": "draw 1, discard 0",
            "3": "draw 2, then discard 1",
            "4": "draw 2, discard 0",
            "5": "draw 3, then discard 1; alternatively Snap 1 display card",
        },
        "side_II_by_strength": {
            "1": "draw 1, discard 0",
            "2": "draw 2, then discard 1",
            "3": "draw 2, discard 0; alternatively Snap 1 display card",
            "4": "draw 3, then discard 1; alternatively Snap 1 display card",
            "5": "draw 4, then discard 1; alternatively Snap 1 display card",
        },
        "side_difference": "Cards I draws only from the deck. Cards II may take each drawn card either from the deck or from a display folder currently within the player's Reputation range.",
        "reputation_limit": "While the Cards action card is side I, Reputation is capped at 9 and cannot advance to 10. Upgrade Cards to side II to unlock Reputation 10-15 and the corresponding display folders.",
    },
    "build": {
        "title": "Build Action I / II and zoo-map placement",
        "side_I": "Build exactly 1 available building whose size is at most the action strength. Pay 2 money per occupied hex.",
        "side_II": "Build one or more different buildings whose combined size is at most the action strength. Pay 2 money per hex. This unlocks Reptile House, Large Bird Aviary, and Build-II-restricted map cells; it does not increase action strength.",
        "placement": [
            "If the selected map has no setup buildings, the first building must cover at least one border hex. Map A already starts with a free empty size-3 standard enclosure and kiosk, so every new building must connect to that existing network.",
            "Every later building must be adjacent to at least one existing building.",
            "A building must be fully in bounds, on legal unoccupied cells, and have its printed fixed shape and rotation.",
            "A kiosk must be at axial distance at least 3 from every other kiosk.",
            "Map rewards trigger only when their hex is covered. Use inspect_map(sections=['rewards']) for exact locations and inspect legal placement cells before choosing.",
        ],
        "special_enclosures": "Reptile House and Large Bird Aviary are constructed with Build II. A card printed with one of these special-enclosure options is not forced to use it: when can_use_standard_enclosure is true, choose either an empty standard enclosure at least as large as the printed enclosure size, or spend the printed capacity in the named special enclosure. For example, Frilled Lizard may use a size-2-or-larger standard enclosure or 1 Reptile House capacity.",
    },
    "animals": {
        "title": "Animals Action I / II",
        "side_I_by_strength": {
            "1": "unavailable",
            "2": "play exactly 1 Animal from hand",
            "3": "play exactly 1 Animal from hand",
            "4": "play exactly 1 Animal from hand",
            "5": "play 1 or 2 Animals from hand",
        },
        "side_II_by_strength": {
            "1": "play exactly 1 Animal",
            "2": "play exactly 1 Animal",
            "3": "play 1 or 2 Animals",
            "4": "play 1 or 2 Animals",
            "5": "gain 1 Reputation first, then play 1 or 2 Animals",
        },
        "side_difference": "Animals II may play from hand or from a display folder within Reputation range, paying that folder number in addition to the animal cost, and satisfies requirements that explicitly need Animals II.",
        "legality": [
            "Every printed prerequisite must be met, including matching Partner Zoo, icon thresholds, Reputation/Appeal thresholds, or an upgraded Animals card.",
            "Pay the animal cost after Partner Zoo and other discounts.",
            "Choose a compatible enclosure with enough capacity. Standard enclosures become occupied; special enclosures can hold multiple compatible animals up to capacity.",
            "A printed Reptile House, Large Bird Aviary, or Petting Zoo line is an alternative housing option, not automatically a mandatory requirement. inspect_card.housing_options lists every permitted housing mode and its capacity cost explicitly.",
            "Rock and water requirements mean the chosen enclosure must be adjacent to at least that many distinct printed terrain hexes. These requirements are also recorded as icons after the animal is played.",
            "inspect_card returns the authoritative enclosure size, special-enclosure option, rock/water counts, prerequisites, abilities, icons, and rewards for each visible animal.",
        ],
    },
    "association": {
        "title": "Association Action I / II",
        "tasks": {
            "2": "requires 2 action strength and worker(s), costs 0 money: gain 2 Reputation",
            "3": "requires 3 action strength and worker(s), costs 0 money: take an available Partner Zoo",
            "4": "requires 4 action strength and worker(s), costs 0 money: take an available University",
            "5": "normally requires 5 action strength and worker(s), costs 0 money: support a Conservation Project (the effective strength requirement may be reduced by bonuses)",
        },
        "side_I": "Perform exactly 1 legal task whose required strength fits the action strength.",
        "side_II": "Perform one or more different tasks whose total required strength fits the action strength. It unlocks the third/fourth Partner Zoo and display Conservation Projects within Reputation range. After at least one task, one donation may be made at the current donation cost for 1 Conservation.",
        "money_cost": "The numbers 2/3/4/5 are action-strength requirements, never money prices. Reputation, Partner Zoo, University, and an already available Conservation Project cost 0 money. Only a donation, or the explicitly printed display-folder surcharge for introducing a display Conservation Project, spends money.",
        "project_sources": {
            "displayed_projects": "A displayed base or Zoo Conservation Project can be supported directly when you meet an unclaimed tier; you do not need that project card in hand.",
            "new_projects_side_I": "Association I may introduce a new Conservation Project only from your hand.",
            "new_projects_side_II": "Association II may introduce a new Conservation Project from your hand or from a display folder within Reputation range; only a display card uses the printed folder surcharge.",
        },
        "asset_ladders": {
            "partner_zoos": "1st: no ladder reward; 2nd: upgrade one Action card; 3rd: gain one worker (requires Association II to take); 4th: gain 2 Conservation.",
            "universities": "1st: no ladder reward; 2nd: upgrade one Action card; 3rd: gain 2 Conservation. The printed university reward itself is separate and resolves every time a university is taken.",
        },
        "workers": "Workers committed during Association tasks return during the next Break. Only your own earlier use of the same task during the round increases your worker cost (first use 1, your second use 2); another player's worker never increases your cost. Board supply still restricts Partner Zoo and University choices.",
    },
    "sponsors": {
        "title": "Sponsors Action I / II",
        "side_I": "Either play exactly 1 eligible Sponsor from hand with level at most strength, or advance Break by strength and gain that much money.",
        "side_II": "Either play one or more eligible Sponsors with total level at most strength + 1, from hand or Reputation-range display (display folder surcharge applies), or advance Break by strength and gain twice that much money. Sponsors II also satisfies printed Sponsors-II requirements.",
        "important": [
            "The Break branch is always an alternative even with no Sponsor in hand.",
            "A Sponsor that grants a unique building cannot be played unless one of that building's legal placements exists; placing it is a mandatory part of playing the card.",
            "Sponsor level is not its money cost when played through the normal Sponsors action; display folder surcharge is separate on Sponsors II.",
        ],
    },
    "display_reputation": {
        "title": "Card display, Reputation range, and folder costs",
        "ranges": {
            "Reputation 1": "display folder 1",
            "Reputation 2-3": "folders 1-2",
            "Reputation 4-6": "folders 1-3",
            "Reputation 7-9": "folders 1-4",
            "Reputation 10-12": "folders 1-5; reaching 10 requires Cards II",
            "Reputation 13-15": "folders 1-6",
        },
        "folder_cost": "When Animals II, Sponsors II, or Association II explicitly plays a card from the display, add the printed folder number to the normal cost. Cards II drawing from a Reputation-range folder and the Snap mode do not pay this surcharge.",
    },
    "break_income": {
        "title": "Break and kiosk income",
        "rules": [
            "A Break discards every hand to its limit, clears action-card interaction tokens, recalls Association workers, replenishes Association supplies, refreshes the display, then pays income and recurring player-board rewards.",
            "Use self.next_break_projection for the current exact estimate: Appeal income, kiosk income, guaranteed recurring rewards, workers returned, and required discards.",
            "Each kiosk gains 1 money for each adjacent qualifying building, counting each kiosk/building pair once even if several hexes touch. Qualifying buildings are occupied standard enclosures, pavilions, Petting Zoo, special enclosures (even empty), and unique Sponsor buildings. Empty standard enclosures do not pay kiosk income.",
            "Advancing the Break track gives tempo/income but also shortens the shared game clock.",
        ],
    },
    "interaction_tokens": {
        "title": "Action-card interaction markers",
        "visibility": "The exact affected cards are listed for every player in action_cards and action_token_status. Do not infer a marker from card order alone.",
        "rules": [
            "Constriction is attached to a specific Action card and reduces that card's strength by 2 before X-tokens are added. It is removed after that marked card is used (including taking an X-token instead) or at the next Break.",
            "Venom is attached to a specific Action card. If you use another Action while any Venom remains, reserve/pay 2 money at the end of the turn. Using the marked card (including taking an X-token instead) removes it and avoids or refunds that reserved payment. It is also cleared at the next Break.",
            "A Multiplier marker may be spent to execute its marked Action twice; each execution has its own locked strength and X allocation. The spent marker is removed after the action, and unused Multiplier markers are cleared at the next Break.",
            "Markers can include source_id, identifying the card or effect that placed them. Use inspect_card on a visible source when its printed interaction target matters.",
        ],
    },
    "rewards_keywords": {
        "title": "Common rewards and keywords",
        "rules": {
            "Clever": "After the current action finishes and its Action card moves to slot 1, optionally choose any Action card and move it to slot 1; Clever does not immediately execute another action.",
            "Determination": "After finishing, gain an additional action subject to the printed restriction.",
            "map_rewards": "A covered reward hex resolves immediately unless its rule explicitly says endgame. The selected zoo map's full-coverage +7 Appeal is an endgame reward, not immediate Appeal.",
            "conservation_player_board": "After supporting a Conservation Project, claim one still-available player-board reward. Rewards marked immediate + every Break resolve now and again at later Breaks; immediate-only rewards resolve once. Map 0's first immediate-only option is +1 Association worker; Map A replaces that option with +2 Reputation.",
            "conservation_track": "At 2 Conservation choose one Action-card upgrade or one worker. The 5- and 8-Conservation choices come from the match's displayed bonus tiles (and the multiplayer 5-money fallback where applicable).",
        },
    },
}


def rules_catalog() -> dict[str, Any]:
    """Return the compact topic index advertised to an agent."""
    return {
        "game": "ark_nova",
        "instruction": "Call inspect_rules with one topic when a rule affects the decision; do not guess from legal-action IDs.",
        "topics": [
            {"id": topic, "title": value["title"]}
            for topic, value in _TOPICS.items()
        ],
    }


def rules_resource() -> dict[str, Any]:
    """Return the catalog plus topic payloads for a seat-scoped resource."""
    return {
        **rules_catalog(),
        "details": deepcopy(_TOPICS),
    }


def rule_topic(topic: str) -> dict[str, Any]:
    """Return one bounded rules topic."""
    if topic not in _TOPICS:
        raise ValueError(f"unknown Ark Nova rules topic: {topic}")
    return {"game": "ark_nova", "topic": topic, **deepcopy(_TOPICS[topic])}


def action_card_summary(action: str, upgraded: bool, strength: int) -> str:
    """Describe the current face and strength without expanding a full topic."""
    side = "II" if upgraded else "I"
    strength = max(1, min(5, int(strength)))
    if action == "cards":
        key = "side_II_by_strength" if upgraded else "side_I_by_strength"
        return f"Cards {side} strength {strength}: {_TOPICS['cards'][key][str(strength)]}; advance Break 2."
    if action == "build":
        if upgraded:
            return f"Build II strength {strength}: different buildings, combined size <= {strength}; 2 money/hex; special enclosures and Build-II cells unlocked."
        return f"Build I strength {strength}: exactly 1 building of size <= {strength}; 2 money/hex."
    if action == "animals":
        key = "side_II_by_strength" if upgraded else "side_I_by_strength"
        return f"Animals {side} strength {strength}: {_TOPICS['animals'][key][str(strength)]}."
    if action == "association":
        mode = "different tasks with combined strength" if upgraded else "exactly 1 task"
        return (
            f"Association {side} strength {strength}: {mode} <= {strength}; "
            "task strength requirements are 2/3/4/5, not money costs; "
            "displayed Conservation Projects need no card in hand; ordinary tasks cost 0 money."
        )
    if action == "sponsors":
        if upgraded:
            return f"Sponsors II strength {strength}: Sponsor levels total <= {strength + 1}, or Break +{strength} and money +{strength * 2}."
        return f"Sponsors I strength {strength}: 1 Sponsor of level <= {strength}, or Break +{strength} and money +{strength}."
    return f"{action} {side} strength {strength}"
