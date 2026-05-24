import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class RoomGameSettings(BaseModel):
    time_limit_seconds: Optional[int] = None
    ultimate_owner_threshold: Optional[float] = None
    mass_bankruptcy_mode: Optional[bool] = None
    min_active_players: Optional[int] = None
    scenario_id: Optional[str] = None


class RoomMeta(BaseModel):
    room_id: str
    name: str
    player_id: str
    created_at: str
    updated_at: str
    game_started_at: Optional[str] = None
    game_settings: RoomGameSettings = Field(default_factory=RoomGameSettings)

def get_rooms_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "rooms"

def get_legacy_db_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "ledger.db"

def get_room_meta_path(room_id: str) -> Path:
    if room_id == "default":
        return Path(__file__).resolve().parents[3] / "data" / "meta.json"
    return get_rooms_dir() / room_id / "meta.json"

def room_exists(room_id: str) -> bool:
    if room_id == "default":
        return get_legacy_db_path().exists() or get_room_meta_path("default").exists()
    room_dir = get_rooms_dir() / room_id
    return room_dir.exists() and room_dir.is_dir() and ((room_dir / "ledger.db").exists() or (room_dir / "meta.json").exists())

def _merge_room_game_settings(current: RoomGameSettings, updates: Dict[str, Any] | RoomGameSettings | None) -> RoomGameSettings:
    if updates is None:
        return current
    if isinstance(updates, RoomGameSettings):
        payload = updates.model_dump(exclude_none=True)
    elif isinstance(updates, dict):
        payload = {k: v for k, v in updates.items() if v is not None}
    else:
        payload = {}
    if not payload:
        return current
    merged = current.model_dump()
    merged.update(payload)
    return RoomGameSettings(**merged)

def load_room_meta(room_id: str) -> Optional[RoomMeta]:
    meta_path = get_room_meta_path(room_id)
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return RoomMeta(**json.load(f))
    except Exception:
        return None

def create_or_update_room_meta(
    room_id: str,
    player_id: str,
    name: Optional[str] = None,
    *,
    game_settings: Dict[str, Any] | RoomGameSettings | None = None,
    ensure_game_started: bool = False,
) -> RoomMeta:
    meta_path = get_room_meta_path(room_id)
    now = datetime.now(timezone.utc).isoformat()
    
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = RoomMeta(**data)
            if name is not None:
                meta.name = name
            meta.updated_at = now
        except Exception:
            meta = RoomMeta(room_id=room_id, name=name or room_id, player_id=player_id, created_at=now, updated_at=now)
    else:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta = RoomMeta(room_id=room_id, name=name or room_id, player_id=player_id, created_at=now, updated_at=now)

    if ensure_game_started and not meta.game_started_at:
        meta.game_started_at = now

    if game_settings is not None:
        meta.game_settings = _merge_room_game_settings(meta.game_settings, game_settings)
    
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(meta.model_dump_json())
    
    return meta

def get_local_rooms() -> List[RoomMeta]:
    rooms = []
    
    # Check legacy default
    legacy_db = get_legacy_db_path()
    legacy_meta = get_room_meta_path("default")
    if legacy_db.exists():
        if legacy_meta.exists():
            try:
                with open(legacy_meta, "r", encoding="utf-8") as f:
                    rooms.append(RoomMeta(**json.load(f)))
            except Exception:
                rooms.append(RoomMeta(room_id="default", name="Legacy Save", player_id="UNKNOWN", created_at="", updated_at=""))
        else:
            rooms.append(RoomMeta(room_id="default", name="Legacy Save", player_id="UNKNOWN", created_at="", updated_at=""))

    rooms_dir = get_rooms_dir()
    if rooms_dir.exists():
        for room_path in rooms_dir.iterdir():
            if room_path.is_dir() and (room_path / "ledger.db").exists():
                meta_file = room_path / "meta.json"
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            rooms.append(RoomMeta(**json.load(f)))
                    except Exception:
                        rooms.append(RoomMeta(room_id=room_path.name, name=room_path.name, player_id="UNKNOWN", created_at="", updated_at=""))
                else:
                    rooms.append(RoomMeta(room_id=room_path.name, name=room_path.name, player_id="UNKNOWN", created_at="", updated_at=""))

    # Sort by updated_at descending
    rooms.sort(key=lambda x: x.updated_at, reverse=True)
    return rooms
