"""Single-observer information-set MCTS against random legal opponents.

Each iteration samples a new world. Tree nodes are keyed by the root player's
observations; edges use semantic actions, never simulation-local action IDs.
Unavailable edges cannot be selected. UCB uses edge availability counts.
After expansion, random rollouts end at max_steps or terminal rankings.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
import math

from .runtime import BaselineAgent, action_key
from .evaluation import value, SCALES, action_prior


@dataclass
class Edge:
    visits: int = 0
    available: int = 0
    total: float = 0.0


@dataclass
class Node:
    edges: dict[str, Edge] = field(default_factory=dict)


class Agent(BaselineAgent):
    algorithm = "ismcts"

    def choose(self, observation, legal, on_stream=None):
        rng, budget = self.start()
        if len(legal) == 1:
            return legal[0]["id"], self.metadata(
                budget,
                automatic=True,
                reason="single_legal_action",
                iterations=0,
                nodes=0,
                root_visits=0,
                evaluated_candidates=0,
            )
        candidates = self.candidates(legal, rng)
        root_keys = {action_key(item["action"]) for item in candidates}
        root = Node()
        tree = {"root": root}
        iterations = 0
        max_steps = self.params["max_steps"]
        if max_steps < len(self.game.decision_seats(self._state)):
            raise ValueError(
                "max_steps must fit one complete simultaneous decision group"
            )
        for _ in range(self.params["iterations"]):
            if budget.expired():
                break
            state = self.sample(rng)
            initial_value = self.evaluate(state)
            path = []
            expanded = False
            used = 0
            at_root = True
            while state["status"] == "active" and not budget.expired():
                seats = self.game.decision_seats(state)
                if used + len(seats) > max_steps:
                    break
                actor = self.seat if self.seat in seats else seats[0]
                actions = (
                    legal
                    if at_root and actor == self.seat
                    else self.game.legal_actions(state, actor)
                )
                if actor == self.seat and not expanded:
                    if at_root:
                        actions = [
                            a for a in actions if action_key(a["action"]) in root_keys
                        ]
                        node = root
                        at_root = False
                    else:
                        view = self.game.observe(state, self.seat)
                        digest = hashlib.sha256(
                            json.dumps(
                                view, sort_keys=True, separators=(",", ":")
                            ).encode()
                        ).hexdigest()
                        node = tree.setdefault(digest, Node())
                        actions = self.candidates(actions, rng)
                    for item in actions:
                        node.edges.setdefault(
                            action_key(item["action"]), Edge()
                        ).available += 1
                    unvisited = [
                        a
                        for a in actions
                        if not node.edges[action_key(a["action"])].visits
                    ]
                    if unvisited:
                        # Resolve staged-action ties using public tactical knowledge;
                        # equally preferred actions retain seeded random order.
                        rng.shuffle(unvisited)
                        selected = max(
                            unvisited,
                            key=lambda item: action_prior(
                                self.game, state, actor, item["action"]
                            ),
                        )
                        expanded = True
                    else:

                        def ucb(item):
                            edge = node.edges[action_key(item["action"])]
                            return edge.total / edge.visits + self.params[
                                "exploration"
                            ] * math.sqrt(
                                math.log(max(1, edge.available)) / edge.visits
                            )

                        selected = max(actions, key=ucb)
                    path.append(node.edges[action_key(selected["action"])])
                else:
                    selected = rng.choice(actions)
                state = self.step(state, actor, selected["action"], rng, budget)
                used += len(seats)
            reward = self.reward(state, initial_value)
            for edge in path:
                edge.visits += 1
                edge.total += reward
            iterations += 1
        # A zero-time search still returns a legal action and records no visits.
        selected = max(
            candidates,
            key=lambda item: (
                root.edges.get(action_key(item["action"]), Edge()).visits,
                root.edges.get(action_key(item["action"]), Edge()).total
                / max(1, root.edges.get(action_key(item["action"]), Edge()).visits),
            ),
        )
        return selected["id"], self.metadata(
            budget,
            iterations=iterations,
            nodes=len(tree),
            evaluated_candidates=sum(edge.visits > 0 for edge in root.edges.values()),
            legal_actions=len(legal),
            candidate_actions=len(candidates),
            root_visits=sum(edge.visits for edge in root.edges.values()),
            opponent_policy="uniform_legal",
            belief="memoryless_uniform",
        )

    def evaluate(self, state):
        return value(
            self.game,
            state,
            self.seat,
            self.params["position_weight"],
            self.params["opponent_weight"],
        )

    def reward(self, state, initial_value):
        if state["status"] == "finished":
            ranks = {row["seat"]: row["rank"] for row in self.game.rankings(state)}
            opponents = [rank for seat, rank in ranks.items() if seat != self.seat]
            if not opponents:
                return 0.5 + 0.5 * math.tanh(
                    (self.evaluate(state) - initial_value) / SCALES[self.game.game_id]
                )
            return sum(
                1 if ranks[self.seat] < rank else 0.5 if ranks[self.seat] == rank else 0
                for rank in opponents
            ) / len(opponents)
        return 0.5 + 0.5 * math.tanh(
            (self.evaluate(state) - initial_value) / SCALES[self.game.game_id]
        )
