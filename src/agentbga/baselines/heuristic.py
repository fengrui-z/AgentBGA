"""One-ply material plus game-specific position and opponent evaluation."""
from .runtime import BaselineAgent


class Agent(BaselineAgent):
    algorithm = 'heuristic'

    def choose(self, observation, legal, on_stream=None):
        return self.one_ply(observation, legal, strategic=True)
