# Brass: Birmingham implementation plan

Rules baseline: Roxley English rulebook, version 2018.11.  No scanned cards,
board art, or publisher prose is stored in the repository.

## Current milestone: playable beta

The `brass_birmingham` plugin is registered as `runnable: true` for CLI, Runner,
MCP, Web, human, API-agent, and Harness matches. It
now contains deterministic seeded setup; player-count-specific official identifier-only
decks and merchant tiles; verified city slots, connection eras, markets, and all
45 player-mat tiles; private-hand projection; action budgets; stable spending
order; action IDs; state validation; and replay-safe transitions.

Build, Sell, Canal and Rail Network (including double rail), Develop, Loan,
Scout, and Pass are implemented as decision-step state machines. Coal, iron, and
beer sources are explicit choices. Resource depletion flips industries and
advances the correct income-track space; market purchases/refills, merchant beer
bonuses, own/opponent resource use, own-industry overbuilding, era cleanup, and
link/industry scoring are active. Random legal strategies are regression-tested
across deterministic seeds through both eras.

The official no-tiles opening exception, single-icon slot priority, level-1
Pottery Rail-era exception, empty player-count Merchant-space coal access and link
scoring, double-rail beer connectivity, and final income-level tie-break are covered
by focused rule scenarios.

The turn scheduler completes both eras, including short final hands, round income,
Canal scoring/cleanup, deterministic discard reshuffling and Rail setup, and final
Rail termination. Negative-income liquidation is an explicit decision step. The
dedicated Web renderer shows players, markets, city slots, industries, links,
merchants, turn order, era, and the current decision without publisher artwork.
The human view also exposes the viewer's cards with readable Chinese city/industry
labels and translates build, resource-source, sale, and network choices.

The mechanics kernel now contains reusable primitives for:

- immutable per-turn action budgets;
- stable metric-based player ordering;
- typed and owned network edges, reachability, and shortest distances;
- candidate resource-source descriptions, without embedding a game's sourcing policy;
- finite price-track markets with explicit purchase and refill order.

## Plugin-owned policies

The plugin, rather than the mechanics kernel, will continue to own card-based
build permission, industry slots and overbuilding, canal/rail era restrictions,
coal/iron/beer sourcing priority, merchant beer, industry flipping, income,
era maintenance, and scoring.

## Delivery sequence

1. Add benchmark metrics and strategy baselines specific to the two-era economy.
2. Continue visual refinement of city geography while retaining the artwork-free UI.

Every complex action is split into `decision_step` choices and continues to use
the common `observe`, `legal_actions`, and `submit_action` tool protocol.
