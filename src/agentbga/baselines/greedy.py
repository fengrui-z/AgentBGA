"""One-ply greedy material controller; no strategic position feature."""
from .runtime import BaselineAgent


class Agent(BaselineAgent):
    algorithm = 'greedy'

    def choose(self, observation, legal, on_stream=None):
        return self.one_ply(observation, legal, strategic=False)
