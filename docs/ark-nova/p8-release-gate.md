# P8 · Official-base runnable integration and release gate

P8 connects the P1–P7 rules modules to the versioned AgentBGA game protocol.
The default Ark Nova rules version is now `base-1.2-faq-v2-semantic.1`; the
former controlled core remains selectable as
`base-1.2-controlled-core.6` for exact replay of existing matches.

## Runnable setup

- The validated content pack creates the physical 212-card Zoo deck: 128
  Animals, 64 Sponsors, and 20 Zoo Conservation Projects.
- The setup also shuffles all 12 Base Projects, deals two of the 11 Final
  Scoring cards to each player, and creates five Action cards per seat. A
  four-player game therefore contains the documented 255 physical cards:
  235 base card faces plus four sets of five Action cards.
- Each seat privately keeps four of eight starting Zoo cards. Map 0 then opens
  engine-issued starter-placement choices for a free size-3 enclosure followed
  by a kiosk. Starter buildings obey border/adjacency and fixed-polyhex rules
  and cannot cover printed placement bonuses.
- Reputation starts at 1, Appeal and Conservation at 0, money at 25, and the
  Animals Action card starts in slot 1 while the other four cards are shuffled.
- Solo setup replaces Final Scoring card 009 because its relative-player rule
  has no solo target. Solo starts at 20 Appeal by default (10 and 0 are
  selectable difficulties) and uses the exact 7/6/5/4/3/2-token round clock.

## Complete match lifecycle

- The plugin exposes only engine-generated legal actions and translates rule
  rejection into the common game-rule error without mutating the supplied
  snapshot.
- A pending shared Break is entered automatically after the triggering action.
  The ordered discard, token clearing, worker recall, association replenishment,
  display refresh, income, and reset sequence can pause in serializable choice
  windows.
- Break income reads the official Appeal-income table and adds Sponsor/player-
  board income. Kiosk income is calculated live from adjacent unique buildings,
  special enclosures, occupied standard enclosures, and pavilions; one multihex
  building counts only once per kiosk and an empty standard enclosure scores 0.
- Track crossing is checked only at the end of a turn or during a Break. Every
  other player receives one final turn after an end-of-turn trigger; after a
  Break trigger every player, including the trigger, receives one final turn.
  If Conservation 10 did not already resolve the global Final Scoring choice,
  the engine opens a private discard choice for every player before scoring.
- Solo Breaks perform shared Break steps 1–5 but do not reset a Break token.
  The first four block donation costs 2/5/7/10; the fifth places the token next
  to 12 without blocking it. The game ends after exactly 27 turns and records
  the official nonnegative-score solo win condition.
- All 11 interactive base Animals use their structured blue-stripe replacement
  in solo games (Inventive, Sprint, Clever, or Determination) rather than
  silently dropping multiplayer interaction effects.
- Final Scoring resolves compiled card effects first and then calculates the
  opposing Appeal/Conservation track distance, with supported projects as the
  tie breaker.

## Hidden information and Web protocol

- `observe(state, seat)` reveals only that seat's hand, initial draw, and Final
  Scoring cards while retaining every player's public map and assets.
- `observe_spectator(state)` is a separate omniscient browser projection for
  agent-only matches. Match agents never receive it.
- The Web action adapter recognizes both the historical controlled-core action
  vocabulary and the official semantic-domain vocabulary. Generic semantic
  choice windows render from engine-provided option labels.

## Automated gate

`tests/test_ark_nova_official_p8_release.py` verifies:

1. all 235 base card faces are transcribed and the 51 cross-card modifiers have
   no unresolved dispatch;
2. deterministic setup, physical counts, privacy, all solo replacements, the
   27-turn solo clock, Map 0 starter buildings, and official Break income;
3. rejection atomicity;
4. same-card and cross-card simultaneous-effect ordering; and
5. an end-to-end path from initial hand selection through track crossing, final
   turns, private Final Scoring discard, card scoring, track-distance scoring,
   ranking, and terminal legal-action closure.

The Web gate additionally type-checks and lints the client, builds the static
export, validates its four rendered-HTML contracts, and opens a real local
two-human match. The smoke test must remain on the initial-hand decision after
the live-update delay, expose the game board, Association board, player map,
and legal choices, and produce no browser console errors.

The pack manifest remains `draft` and the runtime reports
`official_base_candidate`, not `released`: nine advanced maps are intentionally
outside the requested Map 0 scope, and independent human double-review metadata
has not been fabricated. This editorial status does not disable the fully
programmed 235 base card faces.
