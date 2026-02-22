"""Sample service layer for testing import and call graph extraction."""

from typing import List
from tests.fixtures.python_sample.models import Animal, Dog, find_oldest


class AnimalShelter:
    """Manages a collection of animals awaiting adoption."""

    def __init__(self):
        self._animals: List[Animal] = []

    def admit(self, animal: Animal) -> None:
        """Add an animal to the shelter."""
        self._animals.append(animal)

    def discharge(self, name: str) -> Animal | None:
        """Remove and return an animal by name."""
        for i, a in enumerate(self._animals):
            if a.name == name:
                return self._animals.pop(i)
        return None

    def find_oldest_resident(self) -> Animal | None:
        """Return the oldest animal currently in the shelter."""
        return find_oldest(self._animals)

    def list_dogs(self) -> List[Dog]:
        """Return all dogs in the shelter."""
        return [a for a in self._animals if isinstance(a, Dog)]

    def count(self) -> int:
        return len(self._animals)
