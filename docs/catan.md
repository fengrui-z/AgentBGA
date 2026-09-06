# Catan

AgentBGA supports the 3–4 player base game as a playable beta. The engine follows
the [official 2020 Game Rules and Almanac](https://www.catan.com/sites/default/files/2021-06/catan_base_rules_2020_200707.pdf)
and [base-game FAQ](https://www.catan.com/faq/basegame), using the combined
trade/build phase described in the almanac. Expansions and the two-player variant
are outside this implementation.

```console
./agentbga games describe catan --json
./agentbga run --game catan --players 3 --controllers random,random,random --seed 42
./agentbga match create --game catan --players 4 --seed 42 --json
```

Catan is also available in the local browser table. Choose three or four human,
random, or model-controlled seats. The board shows numbered terrain hexes,
harbors, roads, settlements, cities, and the robber. Human players choose from
the same legal actions exposed to agent seats.

## Rules implemented

- A seeded island of 19 hexes, with 54 intersections, 72 road locations, and
  nine harbors. Each seat places two settlement/road pairs in forward then reverse
  order, receiving starting resources from its second settlement.
- Two-dice production, a finite bank of 19 cards per resource, and bank shortages.
  Settlements and cities produce one and two resources respectively.
- Rolling seven triggers mandatory discards, robber movement, and a random theft
  from a neighboring opponent. The robber blocks its hex's production.
- Road and settlement placement, the distance rule, city upgrades, resource
  costs, and each player's physical piece limits.
- Maritime trade at 4:1, general harbors at 3:1, resource harbors at 2:1, and
  negotiated domestic resource trades.
- The 25-card development deck: knights, Road Building, Year of Plenty,
  Monopoly, and hidden victory points. Non-VP cards cannot be used on the turn
  they are bought, and only one can be played per turn, including before rolling.
- Longest Road and Largest Army awards, including tied holders and roads
  interrupted by another player's settlement. Victory occurs at ten points on
  the winner's own turn.

## Decisions and hidden information

Each command commits one structured decision. Setup, discarding, robber movement,
development-card effects, and domestic trading can require several decisions
within one player's turn. `active_seat` identifies who must decide now;
`turn_seat` identifies whose turn is in progress. Trade responses and discards can
temporarily pass control to another seat.

Domestic trades use a proposal-building sequence to select resource bundles,
followed by the recipient's acceptance, rejection, or counteroffer. Discards are selected incrementally.
These steps keep the legal-action list bounded even when players hold large hands.
An opponent's private resource composition never determines which resources can
be requested in a proposal.

Seat observations reveal that seat's resource and development cards and show
only opponents' hand sizes and public points. Random-generator state, the seed,
and the development deck order stay in authoritative state. Accepted actions
are persisted so a saved match can be verified and replayed exactly, including
dice rolls and thefts. The local browser is a trusted spectator/operator surface
that can switch between seat views; agent controllers receive only their own view.

The engine does not award an artificial victory when an evaluation reaches its
turn limit. As with the other games, the runner reports a limit failure instead.
Random play can be slow because trading and building are optional.

No publisher artwork, scans, or copied rulebook prose is bundled. The board is
drawn from the engine's geometry.
