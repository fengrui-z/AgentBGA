"""Shared budget accounting, sampled simulation and controller lifecycle."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import random
import time

from .config import BASELINE_VERSION
from .sampling import sample_state
from .evaluation import action_prior, value


def action_key(action):
    return json.dumps(action,sort_keys=True,separators=(',',':'))


class Budget:
    def __init__(self, milliseconds):
        self.started=time.monotonic()
        self.deadline=self.started+milliseconds/1000 if milliseconds else float('inf')
        self.steps=0
    def expired(self):
        return time.monotonic()>=self.deadline


class BaselineAgent:
    algorithm=''
    def __init__(self,game,seat,params):
        self.game,self.seat,self.params=game,seat,params
        self._state=None
        self.version=0
    def bind(self,state,version):
        # Isolated snapshot; never mutate the runner's state or share across seats.
        self._state=deepcopy(state)
        self.version=version
    def start(self):
        if self._state is None:
            raise RuntimeError('baseline must be bound to a decision snapshot')
        # Independent of the hidden game seed. Resuming a decision regenerates
        # exactly the same stream when time_limit_ms=0.
        material=f"{self.params['seed']}:{self.seat}:{self.version}:{self.algorithm}"
        seed=int.from_bytes(hashlib.sha256(material.encode()).digest()[:8],'big')
        return random.Random(seed),Budget(self.params['time_limit_ms'])
    def sample(self,rng):
        return sample_state(self.game,self._state,self.seat,rng)
    def candidates(self,legal,rng):
        choices=list(legal)
        rng.shuffle(choices)
        limit=self.params['max_candidates']
        if not limit or len(choices)<=limit:
            return choices
        # Stratify by action type so large payment/placement families do not
        # crowd every other type out of the search candidate set.
        groups={}
        for choice in choices:
            groups.setdefault(choice['action']['type'],[]).append(choice)
        chosen=[]
        while groups and len(chosen)<limit:
            for key in list(groups):
                chosen.append(groups[key].pop())
                if not groups[key]: del groups[key]
                if len(chosen)==limit: break
        return chosen
    def step(self,state,seat,action,rng,budget):
        # Freeze all simultaneous decisions before committing the first one.
        seats=self.game.decision_seats(state)
        choices={s:(action if s==seat else rng.choice(self.game.legal_actions(state,s))['action']) for s in seats}
        for s in seats:
            state,_=self.game.apply_action(state,s,choices[s])
            budget.steps+=1
        return state
    def metadata(self,budget,**extra):
        return {'backend':self.algorithm,'algorithm':self.algorithm,'algorithm_version':BASELINE_VERSION,
                'algorithm_params':self.params,'latency_ms':round((time.monotonic()-budget.started)*1000,3),
                'simulation_steps':budget.steps,'budget_exhausted':budget.expired(),**extra}
    def one_ply(self,observation,legal,*,strategic):
        rng,budget=self.start()
        candidates=self.candidates(legal,rng)
        state=self.sample(rng)
        weight=self.params.get('position_weight',0) if strategic else 0
        opponent=self.params.get('opponent_weight',0) if strategic else 0
        best=candidates[0];best_value=float('-inf');evaluated=0
        # Common random numbers across actions avoid rewarding lucky draws.
        simulation_seed=rng.getrandbits(64)
        for candidate in candidates:
            if budget.expired():break
            after=self.step(state,self.seat,candidate['action'],random.Random(simulation_seed),budget)
            score=value(self.game,after,self.seat,weight,opponent)+action_prior(self.game,state,self.seat,candidate['action'])
            if score>best_value:
                best,best_value=candidate,score
            evaluated+=1
        return best['id'],self.metadata(budget,evaluated_candidates=evaluated,iterations=0,nodes=0,
                                       legal_actions=len(legal),candidate_actions=len(candidates))
