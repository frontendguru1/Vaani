"""Engine registry: add an engine module, decorate its class with @register, list it in
ENGINE_MODULES. Instances are singletons so a loaded model stays in memory."""

import importlib
import threading

from app.engines.base import EngineError, TTSEngine

ENGINE_MODULES = ("app.engines.xtts", "app.engines.f5_mlx", "app.engines.indicf5")

_classes: dict[str, type[TTSEngine]] = {}
_instances: dict[str, TTSEngine] = {}
_lock = threading.Lock()
_imported = False


def register(cls: type[TTSEngine]) -> type[TTSEngine]:
    _classes[cls.name] = cls
    return cls


def _ensure_imported() -> None:
    global _imported
    if not _imported:
        for mod in ENGINE_MODULES:
            importlib.import_module(mod)
        _imported = True


def engine_names() -> list[str]:
    _ensure_imported()
    return list(_classes)


def get_engine(name: str) -> TTSEngine:
    _ensure_imported()
    with _lock:
        if name not in _instances:
            if name not in _classes:
                raise EngineError(f"Unknown engine '{name}'. Known: {', '.join(_classes)}")
            _instances[name] = _classes[name]()
        return _instances[name]


def all_engines() -> list[TTSEngine]:
    return [get_engine(n) for n in engine_names()]


def reset_for_tests() -> None:
    with _lock:
        for inst in _instances.values():
            if inst.is_loaded:
                inst.unload()
        _instances.clear()
