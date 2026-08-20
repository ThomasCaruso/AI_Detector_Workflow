from __future__ import annotations
from abc import ABC, abstractmethod


class Provider(ABC):
    @property
    def identity(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str:
        raise NotImplementedError
