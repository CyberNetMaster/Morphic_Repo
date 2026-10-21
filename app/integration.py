"""App connections to grounded explanations, agent exploration and local exports."""
from __future__ import annotations

import io
import json
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

from morphic import agent
from morphic.bundle import create_bundle
from morphic.cache import artifact_names, code_version, load_results
from morphic.materials import library_hash
from morphic.problem import Problem

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".plans" / "live_runs"


def export_signature(folder: str) -> tuple:
    """Invalidate downloads when source artifacts, libraries or exporter change."""
    directory = Path(folder)
    results = load_results(directory)
    files = []
    for name in sorted(artifact_names(results)):
        path = directory / name
        if path.exists():
            stat = path.stat()
            files.append((name, stat.st_size, stat.st_mtime_ns))
    return code_version(), library_hash(), tuple(files)


def export_downloads(folder: str) -> tuple[bytes, bytes]:
    """Return the exact PDF embedded in the bundle, and the bundle itself."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="export-", dir=OUTPUT) as tmp:
        path = create_bundle(folder, Path(tmp) / "run.zip")
        bundle = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        return archive.read("report.pdf"), bundle


class AgentJob:
    """One session-owned job; workers never call Streamlit or mutate the checked part."""

    def __init__(self, problem: Problem, max_rounds: int = 5, path: Path | None = None):
        self.problem = problem.model_copy(deep=True)
        self.max_rounds = max_rounds
        self.path = path or OUTPUT / "agent" / f"{uuid.uuid4().hex}.json"
        self.started = time.perf_counter()
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.messages: list[str] = []
        self.log: agent.ExploreLog | None = None
        self.error = ""

    def status(self, text: str) -> None:
        with self.lock:
            self.messages.append(text)

    def snapshot(self) -> dict:
        with self.lock:
            return dict(done=self.done.is_set(), messages=list(self.messages), log=self.log,
                        error=self.error, seconds=time.perf_counter() - self.started)

    def run(self) -> None:
        try:
            log = agent.explore(self.problem.model_copy(deep=True), max_rounds=self.max_rounds,
                                source="Streamlit Compare", use_llm=True, status=self.status)
            # Preserve the complete start so the recommendation can be reviewed later.
            saved = log.to_dict() | {"starting_problem": self.problem.model_dump(mode="json")}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
            with self.lock:
                self.log = log
        except Exception as exc:
            # Never expose provider request details or credentials in the UI.
            with self.lock:
                self.error = f"Exploration failed ({type(exc).__name__}). You can retry."
        finally:
            self.done.set()


def start_agent(problem: Problem, max_rounds: int = 5) -> AgentJob:
    job = AgentJob(problem, max_rounds)
    threading.Thread(target=job.run, name="morphic-agent", daemon=True).start()
    return job


def recommended_problem(start: Problem, log: agent.ExploreLog) -> Problem:
    """Replay the actual proposals through the chosen round, including pad translations."""
    if not log.rounds or agent.knobs_of(start) != log.rounds[0].knobs:
        raise ValueError("This exploration belongs to a different starting problem")
    target = log.recommendation["round"]
    current = start.model_copy(deep=True)
    for row in log.rounds:
        if row.proposal is not None:
            current = agent.apply_proposal(current, row.proposal)
        if agent.knobs_of(current) != row.knobs:
            raise ValueError("The exploration log does not reproduce its saved settings")
        if row.index == target:
            return current
    raise ValueError("The recommended round is missing")
