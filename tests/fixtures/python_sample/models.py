"""Sample Python models for testing the codelibrarian parser."""

from dataclasses import dataclass
from typing import Optional


class Animal:
    """Base class for all animals."""

    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

    def speak(self) -> str:
        """Return the sound this animal makes."""
        raise NotImplementedError

    def describe(self) -> str:
        return f"{self.name} is {self.age} years old"


class Dog(Animal):
    """A dog that can fetch and speak."""

    def __init__(self, name: str, age: int, breed: str = "unknown"):
        super().__init__(name, age)
        self.breed = breed

    def speak(self) -> str:
        return "Woof!"

    def fetch(self, item: str) -> str:
        """Fetch the given item and return a status string."""
        return f"{self.name} fetched {item}"


class Cat(Animal):
    """A cat that ignores most commands."""

    def speak(self) -> str:
        return "Meow!"


@dataclass
class PetRecord:
    """A record of a pet in the shelter database."""

    id: int
    animal: Animal
    owner: Optional[str] = None

    def is_adopted(self) -> bool:
        return self.owner is not None


def find_oldest(animals: list[Animal]) -> Optional[Animal]:
    """Return the oldest animal from a list, or None if the list is empty."""
    if not animals:
        return None
    return max(animals, key=lambda a: a.age)
