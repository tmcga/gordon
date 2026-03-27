"""Strategy registry — discover, register, and instantiate strategies."""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, ClassVar

from gordon.strategy.base import Strategy

log = logging.getLogger(__name__)


class StrategyRegistry:
    """Central catalogue of available strategy classes.

    Strategies are stored by **name** (lower-cased class name with
    underscores, e.g. ``SmaCrossover`` -> ``sma_crossover``).
    """

    def __init__(self) -> None:
        self._strategies: dict[str, type[Strategy]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, strategy_class: type[Strategy]) -> None:
        """Register a strategy class under its canonical name."""
        name = _class_to_name(strategy_class.__name__)
        if name in self._strategies:
            log.warning(
                "Overwriting strategy %r (%s -> %s)",
                name,
                self._strategies[name].__name__,
                strategy_class.__name__,
            )
        self._strategies[name] = strategy_class
        log.debug("Registered strategy %r -> %s", name, strategy_class)

    def get(self, name: str, **kwargs: Any) -> Strategy:
        """Instantiate a strategy by name.

        Parameters
        ----------
        name:
            Registry key (e.g. ``"sma_crossover"``).
        **kwargs:
            Forwarded to the strategy constructor. ``strategy_id``
            defaults to *name* if not provided.
        """
        key = name.lower()
        if key not in self._strategies:
            available = ", ".join(sorted(self._strategies)) or "(none)"
            raise KeyError(f"Unknown strategy {name!r}. Available: {available}")
        cls = self._strategies[key]
        kwargs.setdefault("strategy_id", key)
        return cls(**kwargs)

    def list_strategies(self) -> list[str]:
        """Return sorted list of registered strategy names."""
        return sorted(self._strategies)

    _ALLOWED_EXTENSIONS: ClassVar[set[str]] = {".py"}

    def discover(self, path: Path) -> int:
        """Import every ``*.py`` file under *path* and register Strategy subclasses.

        Returns the number of newly-registered strategy classes.

        Only ``.py`` files are loaded; ``__init__.py`` and other dunder files
        are skipped.  The *path* must be an existing directory.
        """
        resolved = Path(path).resolve()
        if not resolved.is_dir():
            raise ValueError(f"Strategy path is not a directory: {resolved}")

        # Warn for paths outside the package tree
        package_root = Path(__file__).resolve().parent.parent
        if not str(resolved).startswith(str(package_root)):
            log.warning(
                "Discovering strategies from outside the package: %s",
                resolved,
            )

        count = 0
        for py_file in sorted(resolved.glob("*.py")):
            # Skip dunder files and non-.py extensions
            if py_file.name.startswith("__"):
                continue
            if py_file.suffix not in self._ALLOWED_EXTENSIONS:
                continue
            try:
                module = _import_file(py_file)
            except Exception:
                log.exception("Failed to import %s", py_file)
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, Strategy)
                    and obj is not Strategy
                    and _class_to_name(obj.__name__) not in self._strategies
                ):
                    self.register(obj)
                    count += 1
        return count

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._strategies

    def __len__(self) -> int:
        return len(self._strategies)

    def __repr__(self) -> str:
        return f"StrategyRegistry({len(self._strategies)} strategies)"


# ------------------------------------------------------------------
# Module-level default registry
# ------------------------------------------------------------------

default_registry = StrategyRegistry()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _class_to_name(class_name: str) -> str:
    """Convert CamelCase to snake_case."""
    chars: list[str] = []
    for i, ch in enumerate(class_name):
        if ch.isupper() and i > 0:
            chars.append("_")
        chars.append(ch.lower())
    return "".join(chars)


def _import_file(path: Path) -> object:
    """Import a Python file by path and return the module object."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
