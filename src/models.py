import json
from dataclasses import asdict, dataclass


@dataclass
class Task:
    task_id: int
    text: str
    completed: bool
    reward_points: int

    @property
    def to_json(self) -> str:
        return json.dumps(asdict(self))

@dataclass
class User:
    user_id: int
    tg_id: int
    balance: int

    @property
    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class Reward:
    reward_id: int
    name: str
    cost: int

    @property
    def to_json(self) -> str:
        return json.dumps(asdict(self))
