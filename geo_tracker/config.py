"""Project configuration (TOML) and the brand model."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Brand:
    name: str
    domain: str
    aliases: tuple[str, ...] = ()

    @property
    def all_names(self) -> tuple[str, ...]:
        """Every string that counts as a mention: name, aliases and the bare domain."""
        return (self.name, *self.aliases, self.domain)


@dataclass
class Config:
    client: Brand | None                 # None = market study: all brands are tracked equally
    competitors: list[Brand] = field(default_factory=list)
    keywords_file: Path | None = None
    repeats: int = 3
    engine: str = "replay"
    db_path: Path = Path("geo.db")
    temperature: float | None = None     # None = the provider's default
    system_prompt: str | None = None     # None = send only the question, like a user would
    min_interval: float = 1.0            # seconds between requests

    @property
    def brands(self) -> list[Brand]:
        return [self.client, *self.competitors] if self.client else list(self.competitors)

    @property
    def title(self) -> str:
        return self.client.name if self.client else "market study"


def _brand(d: dict) -> Brand:
    return Brand(name=d["name"], domain=d["domain"].lower(), aliases=tuple(d.get("aliases", ())))


def load_config(path: str | Path) -> Config:
    """[client] is optional. Without it, [[competitors]] (or [[brands]]) are all tracked as equals."""
    path = Path(path)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    run = raw.get("run", {})
    return Config(
        client=_brand(raw["client"]) if "client" in raw else None,
        competitors=[_brand(c) for c in [*raw.get("competitors", []), *raw.get("brands", [])]],
        keywords_file=(base / run["keywords_file"]) if "keywords_file" in run else None,
        repeats=int(run.get("repeats", 3)),
        engine=run.get("engine", "replay"),
        db_path=base / run.get("db_path", "geo.db"),
        temperature=float(run["temperature"]) if "temperature" in run else None,
        system_prompt=run.get("system_prompt") or None,
        min_interval=float(run.get("min_interval", 1.0)),
    )
