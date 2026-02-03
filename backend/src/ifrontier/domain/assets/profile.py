from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class AssetProfile:
    symbol: str
    sector: str  # e.g. MILITARY / FINANCE / CONSUMER / TECH


_ASSET_PROFILES: Dict[str, AssetProfile] = {
    "BLUEGOLD": AssetProfile(symbol="BLUEGOLD", sector="MILITARY"),
    "CIVILBANK": AssetProfile(symbol="CIVILBANK", sector="FINANCE"),
    "FOODMART": AssetProfile(symbol="FOODMART", sector="CONSUMER"),
    "NEURALINK": AssetProfile(symbol="NEURALINK", sector="TECH"),
    "MARS_GEN": AssetProfile(symbol="MARS_GEN", sector="ENERGY"),
    "BIO_SYNTH": AssetProfile(symbol="BIO_SYNTH", sector="HEALTHCARE"),
    "ORBIT_LOG": AssetProfile(symbol="ORBIT_LOG", sector="LOGISTICS"),
}


def get_profile(symbol: str) -> Optional[AssetProfile]:
    return _ASSET_PROFILES.get(symbol)
