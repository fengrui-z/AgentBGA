"""Run complete matches by binding named controllers to seats."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import random
import threading
import time
from typing import Any, Callable

from .agents import AgentError, HARNESS_BACKENDS, PlayerConfig, build_model_agent, random_choice
from .harness import build_harness_agent
from .minimal_harness import build_minimal_agent
from .public_projection import (
    public_action,
    public_action_id,
    public_controller_event,
    public_game_event,
)
from .store import Store
from .usage import build_harness_metrics


EventSink = Callable[[dict[str, Any]], None]
TurnGate = Callable[[], None]
HumanChoice = Callable[[int, int, dict[str, Any], list[dict[str, Any]]], str]


def _automatic_harness_choice(
    config: PlayerConfig, legal: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    """Bypass a model call when a harness-controlled seat has no choice."""
    if config.backend not in HARNESS_BACKENDS or len(legal) != 1:
        return None
    return legal[0]["id"], {
        "backend": config.backend,
        "harness": config.backend,
        "model": config.model,
        "automatic": True,
        "reason": "single_legal_action",
        "attempts": 0,
        "latency_ms": 0.0,
    }


def legacy_players(
    controllers: list[str], *, model: str | None = None,
    base_url: str = "https://api.openai.com/v1", api_key_env: str = "OPENAI_API_KEY",
) -> list[PlayerConfig]:
    players = []
    for seat, backend in enumerate(controllers):
        value: dict[str, Any] = {"name": f"Seat {seat} ({backend})", "backend": backend}
        if backend == "openai":
            value.update(model=model, base_url=base_url, api_key_env=api_key_env)
        players.append(PlayerConfig.from_dict(value, seat))
    return players


def run_match(
    store: Store,
    match_id: str,
    players: list[PlayerConfig] | list[str],
    *,
    model: str | None = None,
    base_url: str = "https://api.openai.com/v1",
    api_key_env: str = "OPENAI_API_KEY",
    max_turns: int | None = None,
    retries: int = 1,
    fallback: str = "random",
    sink: EventSink | None = None,
    turn_gate: TurnGate | None = None,
    human_choice: HumanChoice | None = None,
    harness_factory: Callable[[PlayerConfig, str, int, EventSink], Any] | None = None,
) -> dict[str, Any]:
    version, state, _ = store.load(match_id)
    game = store.game(match_id)
    description = game.describe()
    if max_turns is None:
        max_turns = int(description.get("default_max_turns", 250))
    if not description.get("runnable", True):
        raise ValueError(
            f"{description['name']} is currently {description.get('implementation_status', 'unavailable')} "
            "and cannot run complete matches yet"
        )
    if players and isinstance(players[0], str):
        players = legacy_players(players, model=model, base_url=base_url, api_key_env=api_key_env)  # type: ignore[arg-type]
    configs: list[PlayerConfig] = players  # type: ignore[assignment]
    if len(configs) != state["player_count"]:
        raise ValueError("player/controller count must equal player count")
    store.set_players(match_id, [config.public_dict() for config in configs])
    rngs = [random.Random(state["seed"] * 1009 + seat) for seat in range(state["player_count"])]
    model_agents: dict[int, Any] = {
        seat: build_model_agent(config)
        for seat, config in enumerate(configs)
        if config.backend in {"openai", "anthropic", "gemini"}
    }
    sink_lock = threading.Lock()
    harness_event_lock = threading.Lock()
    attempt_error_lock = threading.Lock()
    interactive_human_lock = threading.Lock()
    pending_harness_events: list[tuple[int, int, dict[str, Any]]] = []
    attempt_errors: dict[int, int] = {}

    def emit(event: dict[str, Any]) -> None:
        if sink:
            with sink_lock:
                sink(event)

    for harness_seat, harness_config in enumerate(configs):
        if harness_config.backend not in HARNESS_BACKENDS:
            continue

        def harness_sink(event: dict[str, Any], seat: int = harness_seat) -> None:
            enriched = {"version": version, "backend": configs[seat].backend, **event}
            enriched = public_controller_event(
                enriched, match_id=match_id, version=version, seat=seat,
            )
            if enriched.get("type") != "harness_output":
                # Agent callbacks can run on worker threads, while sqlite
                # connections remain owned by the runner thread.
                with harness_event_lock:
                    pending_harness_events.append((version, seat, enriched))
            emit(enriched)

        if harness_factory is not None:
            model_agents[harness_seat] = harness_factory(
                harness_config, match_id, harness_seat, harness_sink,
            )
        elif harness_config.backend == "minimal":
            model_agents[harness_seat] = build_minimal_agent(
                harness_config, match_id, harness_seat, event_sink=harness_sink,
                game_id=game.game_id,
            )
        else:
            model_agents[harness_seat] = build_harness_agent(
                harness_config, match_id, harness_seat, event_sink=harness_sink,
            )

    def flush_harness_events() -> None:
        with harness_event_lock:
            buffered = list(pending_harness_events)
            pending_harness_events.clear()
        for event_version, event_seat, event in buffered:
            store.record_harness_event(match_id, event_version, event_seat, event)

    def choose_for_seat(
        seat: int, snapshot_version: int, observation: dict[str, Any],
        legal: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        config = configs[seat]
        metadata: dict[str, Any] = {}
        choice_started = time.monotonic()
        if config.backend == "random":
            return random_choice(legal, rngs[seat]), metadata
        if config.backend == "human":
            if human_choice:
                action_id = human_choice(seat, snapshot_version, observation, legal)
                if action_id not in {item["id"] for item in legal}:
                    raise AgentError("human selected unknown or stale action ID")
                return action_id, metadata
            # A single terminal cannot safely host multiple simultaneous input
            # prompts.  The views are still frozen together, but prompts are
            # presented one at a time.
            with interactive_human_lock:
                print(f"\n{config.name} (seat {seat}), version {snapshot_version}. Legal actions:")
                for index, item in enumerate(legal):
                    print(f"  [{index}] {item['action']}")
                while True:
                    raw = input("Choose action number: ").strip()
                    if raw.isdigit() and int(raw) < len(legal):
                        return legal[int(raw)]["id"], metadata
                    print("Invalid selection.")

        automatic = _automatic_harness_choice(config, legal)
        if automatic is not None:
            return automatic

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            pending = {"reasoning": "", "content": ""}
            last_stream_flush = [time.monotonic()]

            def flush_stream() -> None:
                if not sink:
                    return
                for channel in ("reasoning", "content"):
                    if pending[channel]:
                        emit({"type": "agent_stream", "version": snapshot_version,
                              "seat": seat, "player": config.name,
                              "backend": config.backend, "attempt": attempt + 1,
                              "channel": channel, "delta": pending[channel]})
                        pending[channel] = ""
                last_stream_flush[0] = time.monotonic()

            try:
                emit({"type": "agent_started", "version": snapshot_version,
                      "seat": seat, "player": config.name,
                      "backend": config.backend, "attempt": attempt + 1})

                def stream(channel: str, delta: str) -> None:
                    pending[channel] += delta
                    if time.monotonic() - last_stream_flush[0] >= 0.1:
                        flush_stream()

                action_id, metadata = model_agents[seat].choose(
                    observation, legal, on_stream=stream,
                )
                flush_stream()
                emit({"type": "agent_finished", "version": snapshot_version,
                      "seat": seat, "player": config.name,
                      "backend": config.backend, "attempt": attempt + 1,
                      "agent": metadata})
                return action_id, metadata
            except AgentError as error:
                flush_stream()
                last_error = error
                with attempt_error_lock:
                    attempt_errors[seat] = attempt_errors.get(seat, 0) + 1
                emit({"type": "agent_error", "version": snapshot_version,
                      "seat": seat, "player": config.name,
                      "backend": config.backend, "attempt": attempt + 1,
                      "error": str(error)})
        if fallback == "random":
            return random_choice(legal, rngs[seat]), {
                "fallback": "random", "error": str(last_error),
                "latency_ms": round((time.monotonic() - choice_started) * 1000, 3),
                "attempts": retries + 1,
            }
        raise AgentError(f"{config.name} exhausted retries: {last_error}")

    setup_decision_limit = state.get("player_count", 0) * 2
    with ThreadPoolExecutor(
        max_workers=state["player_count"], thread_name_prefix=f"agentbga-{match_id}",
    ) as executor:
        while state["status"] == "active":
            if turn_gate:
                turn_gate()
            if state["turn_count"] >= max_turns and state.get("phase") != "initial_hand_selection":
                raise RuntimeError(f"match exceeded --max-turns={max_turns}")
            if state.get("phase") == "initial_hand_selection" and state.get("decision_count", 0) > setup_decision_limit:
                raise RuntimeError("initial setup exceeded the decision limit")

            decision_seats = game.decision_seats(state)
            if (not decision_seats or len(decision_seats) != len(set(decision_seats))
                    or any(seat not in range(state["player_count"]) for seat in decision_seats)):
                raise RuntimeError("game returned invalid decision seats")
            snapshot_version = version
            choices: dict[int, tuple[str, dict[str, Any], list[dict[str, Any]]]] = {}
            inputs: dict[int, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
            for seat in decision_seats:
                legal = game.legal_actions(state, seat)
                if not legal:
                    raise RuntimeError(f"seat {seat} has no legal actions")
                observation = game.observe(state, seat)
                observation["state_version"] = snapshot_version
                inputs[seat] = observation, legal

            try:
                if len(decision_seats) == 1:
                    seat = decision_seats[0]
                    observation, legal = inputs[seat]
                    action_id, metadata = choose_for_seat(
                        seat, snapshot_version, observation, legal,
                    )
                    choices[seat] = action_id, metadata, legal
                else:
                    futures = {
                        seat: executor.submit(
                            choose_for_seat, seat, snapshot_version, *inputs[seat],
                        )
                        for seat in decision_seats
                    }
                    for seat in decision_seats:
                        action_id, metadata = futures[seat].result()
                        choices[seat] = action_id, metadata, inputs[seat][1]
            finally:
                flush_harness_events()

            decision_events: list[dict[str, Any]] = []
            for seat in decision_seats:
                action_id, metadata, legal = choices[seat]
                selected_by_id = {
                    item["id"]: item["action"] for item in legal
                }
                if action_id not in selected_by_id:
                    raise AgentError(
                        f"{configs[seat].name} selected unknown or stale action ID",
                    )
                selected = selected_by_id[action_id]
                version, state, events = store.act(match_id, seat, version, selected)
                config = configs[seat]
                if seat in model_agents or metadata:
                    store.record_controller_call(
                        match_id, version, seat, config.backend, metadata,
                    )
                projected_action = public_action(selected)
                projected_action_id = public_action_id(
                    action_id, selected, match_id=match_id,
                    version=snapshot_version, seat=seat,
                )
                decision_events.append({
                    "type": "decision", "match_id": match_id, "version": version,
                    "snapshot_version": snapshot_version,
                    "simultaneous_seats": decision_seats,
                    "seat": seat, "player": config.name, "backend": config.backend,
                    "action_id": projected_action_id, "action": projected_action,
                    "events": [
                        public_game_event(event) for event in events
                        if event.get("type") != "action_accepted"
                    ],
                    "agent": metadata,
                    "turn_count": state["turn_count"],
                    "decision_count": state.get("decision_count", state["turn_count"]),
                })
            # No public decision snapshot is published until every simultaneous
            # choice has been collected and committed.
            for event in decision_events:
                emit(event)
    by_seat = {seat: config.public_dict() for seat, config in enumerate(configs)}
    rankings = [{**row, "player": by_seat[row["seat"]]["name"], "backend": by_seat[row["seat"]]["backend"]}
                for row in game.rankings(state)]
    result = {
        "match_id": match_id, "game": game.game_id, "rules_version": game.rules_version,
        "content_pack_id": state.get("content_pack_id"), "content_hash": state.get("content_hash"),
        "version": version, "turns": state["turn_count"],
        "decisions": state.get("decision_count", state["turn_count"]),
        "players": [{"seat": seat, **config.public_dict()} for seat, config in enumerate(configs)],
        "rankings": rankings,
        "harness_metrics": build_harness_metrics(
            configs, model_agents, store.controller_calls(match_id),
            store.harness_events(match_id), HARNESS_BACKENDS, attempt_errors,
        ),
    }
    emit({"type": "match_finished", **result})
    return result
