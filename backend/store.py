"""Save / load RunRecord, TournamentRecord, datasets as JSON under data_store/."""

import json
import os
from pathlib import Path
from typing import Any, Optional

from backend.config import RUNS_DIR, TOURNAMENTS_DIR, DATASETS_DIR


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _read(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def save_run(record: dict) -> None:
    run_id = record["run_id"]
    _write(RUNS_DIR / f"{run_id}.json", record)


def load_run(run_id: str) -> Optional[dict]:
    return _read(RUNS_DIR / f"{run_id}.json")


def delete_run(run_id: str) -> bool:
    path = RUNS_DIR / f"{run_id}.json"
    if path.exists():
        os.remove(path)
        return True
    return False


def list_runs() -> list[dict]:
    results = []
    for p in sorted(RUNS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = _read(p)
            if data:
                # Return slim summary
                results.append({
                    "run_id": data.get("run_id"),
                    "model_id": data.get("model_id"),
                    "model_label": data.get("model_label"),
                    "model_color": data.get("model_color"),
                    "dataset": data.get("dataset"),
                    "metrics": data.get("metrics"),
                    "status": data.get("status"),
                    "created_at": data.get("created_at"),
                    "mode": data.get("mode"),
                    "tournament_id": data.get("tournament_id"),
                })
        except Exception:
            pass
    return results


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------

def save_tournament(record: dict) -> None:
    tid = record["tournament_id"]
    _write(TOURNAMENTS_DIR / f"{tid}.json", record)


def load_tournament(tid: str) -> Optional[dict]:
    return _read(TOURNAMENTS_DIR / f"{tid}.json")


def list_tournaments() -> list[dict]:
    results = []
    for p in sorted(TOURNAMENTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = _read(p)
            if data:
                results.append({
                    "tournament_id": data.get("tournament_id"),
                    "name": data.get("name"),
                    "dataset": data.get("dataset"),
                    "model_ids": data.get("model_ids"),
                    "leaderboard": data.get("leaderboard"),
                    "status": data.get("status"),
                    "progress": data.get("progress"),
                    "created_at": data.get("created_at"),
                })
        except Exception:
            pass
    return results


# ---------------------------------------------------------------------------
# Dataset (uploaded CSV)
# ---------------------------------------------------------------------------

def save_dataset(dataset_id: str, data: dict) -> None:
    _write(DATASETS_DIR / f"{dataset_id}.json", data)


def load_dataset(dataset_id: str) -> Optional[dict]:
    return _read(DATASETS_DIR / f"{dataset_id}.json")


def list_datasets() -> list[str]:
    return [p.stem for p in DATASETS_DIR.glob("*.json")]
