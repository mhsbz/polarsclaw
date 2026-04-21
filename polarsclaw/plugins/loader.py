"""PluginLoader — discover and load plugins via entry-points."""

from __future__ import annotations

import importlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from polarsclaw.plugins.models import PluginManifest, PluginState

if TYPE_CHECKING:
    from polarsclaw.config.settings import Settings
    from polarsclaw.plugins.api import PluginAPI

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "polarsclaw.plugins"


class PluginLoader:
    """Discover plugins via ``importlib.metadata`` entry-points and load them.

    Each plugin entry-point must resolve to a module (or object) that exposes a
    callable ``register(api: PluginAPI) -> None``.

    Parameters
    ----------
    settings:
        Application settings.  ``settings.plugin.enabled`` gates the whole
        subsystem; ``settings.plugin.autoload`` (if non-empty) restricts which
        discovered plugins are actually loaded.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._manifests: list[PluginManifest] = []
        self._states: dict[str, PluginState] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[PluginManifest]:
        """Scan installed packages for ``polarsclaw.plugins`` entry-points.

        Returns the discovered manifests and caches them internally.
        """
        if sys.version_info >= (3, 12):
            from importlib.metadata import entry_points
            eps = entry_points(group=_ENTRY_POINT_GROUP)
        else:
            from importlib.metadata import entry_points
            all_eps = entry_points()
            eps = all_eps.get(_ENTRY_POINT_GROUP, [])  # type: ignore[assignment]

        manifests: list[PluginManifest] = []
        for ep in eps:
            manifests.append(
                PluginManifest(
                    name=ep.name,
                    version=getattr(ep.dist, "version", "0.0.0") if ep.dist else "0.0.0",
                    entry_point=ep.value,
                    description=f"Plugin from {ep.value}",
                )
            )

        manifests.extend(self._discover_directory_plugins())

        self._manifests = manifests
        logger.info("Discovered %d plugin(s) via entry-points", len(manifests))
        return list(manifests)

    def _discover_directory_plugins(self) -> list[PluginManifest]:
        """Discover plugins from configured local directories."""
        manifests: list[PluginManifest] = []
        seen_names = {manifest.name for manifest in self._manifests}

        for raw_dir in self._settings.plugin.directories:
            plugin_dir = Path(raw_dir).expanduser()
            if not plugin_dir.is_dir():
                logger.warning("Plugin directory does not exist: %s", plugin_dir)
                continue

            sys.path.insert(0, str(plugin_dir))

            for path in sorted(plugin_dir.iterdir()):
                if path.name.startswith("_"):
                    continue
                if path.is_file() and path.suffix == ".py":
                    name = path.stem
                    entry_point = name
                elif path.is_dir() and (path / "__init__.py").exists():
                    name = path.name
                    entry_point = name
                else:
                    continue

                if name in seen_names:
                    continue

                manifests.append(
                    PluginManifest(
                        name=name,
                        version="0.0.0",
                        entry_point=entry_point,
                        description=f"Plugin from directory {plugin_dir}",
                    )
                )
                seen_names.add(name)

        return manifests

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_all(self, api: PluginAPI) -> None:
        """Load every enabled plugin and invoke its ``register(api)`` hook.

        Plugins that raise during import or registration are logged as
        warnings and skipped — they do not break the rest of the system.
        """
        if not self._settings.plugin.enabled:
            logger.info("Plugin subsystem disabled — skipping load")
            return

        if not self._manifests:
            self.discover()

        autoload = set(self._settings.plugin.autoload) if self._settings.plugin.autoload else None

        for manifest in self._manifests:
            if autoload is not None and manifest.name not in autoload:
                logger.debug("Skipping plugin '%s' (not in autoload list)", manifest.name)
                continue

            try:
                module = importlib.import_module(manifest.entry_point.split(":")[0])
                register_fn = getattr(module, "register", None)

                # Support ``module:object`` form (e.g. ``myplugin.main:register``)
                if ":" in manifest.entry_point:
                    attr = manifest.entry_point.split(":", 1)[1]
                    register_fn = getattr(module, attr, register_fn)

                if register_fn is None or not callable(register_fn):
                    logger.warning(
                        "Plugin '%s' (%s) has no callable register() — skipped",
                        manifest.name,
                        manifest.entry_point,
                    )
                    continue

                register_fn(api)

                self._states[manifest.name] = PluginState(
                    name=manifest.name,
                    enabled=True,
                    loaded_at=datetime.now(timezone.utc),
                )
                logger.info("Loaded plugin '%s' v%s", manifest.name, manifest.version)

            except Exception:
                logger.warning(
                    "Failed to load plugin '%s' — skipping",
                    manifest.name,
                    exc_info=True,
                )
                self._states[manifest.name] = PluginState(
                    name=manifest.name,
                    enabled=False,
                )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def manifests(self) -> list[PluginManifest]:
        return list(self._manifests)

    @property
    def states(self) -> dict[str, PluginState]:
        return dict(self._states)
