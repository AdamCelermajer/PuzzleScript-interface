from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def _jsonable(value: Any) -> JsonValue:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _canonical(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Action:
    """An environment action with an opaque ID and optional parameters."""

    id: str
    data: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    """The smallest environment-neutral observation contract."""

    payload: JsonValue
    status: str = "UNKNOWN"
    progress: JsonValue = None
    available_actions: tuple[str, ...] = ()
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "payload": self.payload,
                "status": self.status,
                "progress": self.progress,
            }
        )


@dataclass(frozen=True)
class Transition:
    sequence: int
    before: Observation
    action: Action
    after: Observation
    episode: int = 1


@dataclass(frozen=True)
class Prediction:
    """A candidate's prospective claim, created before the action executes."""

    expected: Observation | None
    confidence: float = 1.0
    rationale: str = ""


class TheoryCandidate(Protocol):
    candidate_id: str
    parent_id: str | None
    claim: str
    complexity: float

    def predict(
        self,
        history: Sequence[Transition],
        current: Observation,
        action: Action,
    ) -> Prediction:
        """Return a falsifiable prediction without mutating the environment."""


@dataclass(frozen=True)
class Comparison:
    exact: bool
    prospective_accuracy: float
    status_accuracy: float
    progress_accuracy: float
    details: Mapping[str, JsonValue] = field(default_factory=dict)


class EnvironmentContract(Protocol):
    def reset(self) -> Observation: ...

    def step(self, action: Action) -> Observation: ...

    def compare(self, expected: Observation, actual: Observation) -> Comparison: ...


@dataclass(frozen=True)
class FrozenPrediction:
    prediction_id: str
    candidate_id: str
    action: Action
    created_at: str
    current_fingerprint: str
    prediction: Prediction


@dataclass(frozen=True)
class PredictionEvaluation:
    prediction_id: str
    candidate_id: str
    exact: bool | None
    prospective_accuracy: float
    status_accuracy: float
    progress_accuracy: float
    coverage: float
    error: str | None = None


@dataclass(frozen=True)
class ExperimentChoice:
    action: Action
    disagreement: float
    participating_candidates: int


@dataclass(frozen=True)
class SupervisorEvent:
    code: str
    severity: str
    message: str
    evidence: Mapping[str, JsonValue]


@dataclass(frozen=True)
class CycleResult:
    transition: Transition
    predictions: tuple[FrozenPrediction, ...]
    evaluations: tuple[PredictionEvaluation, ...]
    supervisor_events: tuple[SupervisorEvent, ...]


class EvidenceStore:
    """Append-only JSONL evidence owned by the framework, not the candidate."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "evidence.jsonl"
        self._sequence = 0
        if self.path.exists():
            self._sequence = sum(1 for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip())

    def append(self, event_type: str, payload: Any) -> dict[str, JsonValue]:
        self._sequence += 1
        record = {
            "sequence": self._sequence,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "payload": _jsonable(payload),
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        return record


class DeterministicSupervisor:
    """Process watchdog. It detects stagnation without knowing the hidden task."""

    def __init__(
        self,
        *,
        no_change_limit: int = 3,
        repeated_action_limit: int = 4,
        failed_prediction_limit: int = 3,
    ) -> None:
        self.no_change_limit = no_change_limit
        self.repeated_action_limit = repeated_action_limit
        self.failed_prediction_limit = failed_prediction_limit
        self._no_change = 0
        self._same_action = 0
        self._failed_prediction_cycles = 0
        self._last_action: str | None = None

    def reset(self) -> None:
        self._no_change = 0
        self._same_action = 0
        self._failed_prediction_cycles = 0
        self._last_action = None

    def inspect(
        self,
        transition: Transition,
        evaluations: Sequence[PredictionEvaluation],
    ) -> tuple[SupervisorEvent, ...]:
        self._no_change = self._no_change + 1 if transition.before.fingerprint == transition.after.fingerprint else 0
        self._same_action = self._same_action + 1 if transition.action.id == self._last_action else 1
        self._last_action = transition.action.id

        covered = [item for item in evaluations if item.coverage > 0]
        best_accuracy = max((item.prospective_accuracy for item in covered), default=1.0)
        self._failed_prediction_cycles = self._failed_prediction_cycles + 1 if covered and best_accuracy == 0 else 0

        events: list[SupervisorEvent] = []
        if self.no_change_limit and self._no_change >= self.no_change_limit:
            events.append(
                SupervisorEvent(
                    code="repeated_no_change",
                    severity="redirect",
                    message="The recent probes are not changing the observed state. Test a different action family or representation.",
                    evidence={"consecutive_no_change": self._no_change},
                )
            )
            self._no_change = 0
        if self.repeated_action_limit and self._same_action >= self.repeated_action_limit:
            events.append(
                SupervisorEvent(
                    code="repeated_probe",
                    severity="warning",
                    message="The same action has been selected repeatedly without a recorded information-gain justification.",
                    evidence={"action": transition.action.id, "count": self._same_action},
                )
            )
            self._same_action = 0
        if self.failed_prediction_limit and self._failed_prediction_cycles >= self.failed_prediction_limit:
            events.append(
                SupervisorEvent(
                    code="hypothesis_collapse",
                    severity="redirect",
                    message="All participating theories have repeatedly failed prospectively. Generate a competing ontology before continuing.",
                    evidence={"failed_cycles": self._failed_prediction_cycles},
                )
            )
            self._failed_prediction_cycles = 0
        return tuple(events)


class AvoLaboratory:
    """Framework-owned evidence, prediction freezing, execution, and evaluation."""

    def __init__(
        self,
        environment: EnvironmentContract,
        candidates: Sequence[TheoryCandidate],
        evidence_dir: str | Path,
        supervisor: DeterministicSupervisor | None = None,
    ) -> None:
        ids = [candidate.candidate_id for candidate in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Candidate IDs must be unique")
        self.environment = environment
        self.candidates = list(candidates)
        self._candidate_ids = set(ids)
        self.store = EvidenceStore(evidence_dir)
        configure_rendered_frames = getattr(
            self.environment, "set_rendered_frame_output_dir", None
        )
        if callable(configure_rendered_frames):
            configure_rendered_frames(self.store.root / "frames")
        self.supervisor = supervisor or DeterministicSupervisor()
        self.history: list[Transition] = []
        self.current: Observation | None = None
        self.episode = 0

    def reset(self) -> Observation:
        """Initialize a fresh run. Runtime restarts use restart_episode()."""
        self.episode = 1
        self.supervisor.reset()
        self.current = self.environment.reset()
        self.history.clear()
        self.store.append(
            "episode_started",
            {"episode": self.episode, "reason": "run initialized", "observation": self.current},
        )
        for candidate in self.candidates:
            self.store.append(
                "candidate_registered",
                {
                    "candidate_id": candidate.candidate_id,
                    "parent_id": candidate.parent_id,
                    "claim": candidate.claim,
                    "complexity": candidate.complexity,
                },
            )
        return self.current

    def restart_episode(self, reason: str) -> Observation:
        if self.current is None:
            raise RuntimeError("reset() must be called before restarting an episode")
        self.episode += 1
        self.supervisor.reset()
        self.current = self.environment.reset()
        self.store.append(
            "episode_started",
            {"episode": self.episode, "reason": reason, "observation": self.current},
        )
        return self.current

    def restore_checkpoint(self, observation: Observation, checkpoint_id: str) -> Observation:
        self.episode += 1
        self.supervisor.reset()
        self.current = observation
        self.store.append(
            "checkpoint_restored",
            {
                "episode": self.episode,
                "checkpoint_id": checkpoint_id,
                "observation": observation,
            },
        )
        return observation

    def register_candidate(self, candidate: TheoryCandidate) -> None:
        """Admit one agent-authored candidate without controlling how it was created."""
        if candidate.candidate_id in self._candidate_ids:
            return
        if not candidate.candidate_id.strip():
            raise ValueError("Candidate ID cannot be empty")
        if not candidate.claim.strip():
            raise ValueError(f"{candidate.candidate_id} must declare a falsifiable claim")
        self.candidates.append(candidate)
        self._candidate_ids.add(candidate.candidate_id)
        self.store.append(
            "candidate_registered",
            {
                "candidate_id": candidate.candidate_id,
                "parent_id": candidate.parent_id,
                "claim": candidate.claim,
                "complexity": candidate.complexity,
            },
        )

    def _predict(self, candidate: TheoryCandidate, action: Action) -> Prediction:
        if self.current is None:
            raise RuntimeError("reset() must be called before prediction")
        prediction = candidate.predict(tuple(self.history), self.current, action)
        if not isinstance(prediction, Prediction):
            raise TypeError(f"{candidate.candidate_id} returned {type(prediction).__name__}, expected Prediction")
        if not 0 <= prediction.confidence <= 1:
            raise ValueError(f"{candidate.candidate_id} confidence must be between 0 and 1")
        return prediction

    def choose_experiment(self, actions: Sequence[Action]) -> ExperimentChoice:
        if not actions:
            raise ValueError("At least one candidate action is required")
        if self.current is None:
            raise RuntimeError("reset() must be called before choosing an experiment")

        choices: list[ExperimentChoice] = []
        for action in actions:
            expected: list[Observation] = []
            for candidate in self.candidates:
                try:
                    prediction = self._predict(candidate, action)
                except (TypeError, ValueError, RuntimeError):
                    continue
                if prediction.expected is not None:
                    expected.append(prediction.expected)
            pair_scores: list[float] = []
            for left_index, left in enumerate(expected):
                for right in expected[left_index + 1 :]:
                    comparison = self.environment.compare(left, right)
                    agreement = (
                        comparison.prospective_accuracy
                        + comparison.status_accuracy
                        + comparison.progress_accuracy
                    ) / 3
                    pair_scores.append(1 - agreement)
            choices.append(
                ExperimentChoice(
                    action=action,
                    disagreement=sum(pair_scores) / len(pair_scores) if pair_scores else 0.0,
                    participating_candidates=len(expected),
                )
            )
        return max(choices, key=lambda item: (item.disagreement, item.participating_candidates))

    def _freeze_predictions(self, action: Action) -> tuple[FrozenPrediction, ...]:
        assert self.current is not None
        frozen: list[FrozenPrediction] = []
        for candidate in self.candidates:
            created_at = datetime.now(timezone.utc).isoformat()
            prediction_id = f"p_{len(self.history) + 1:04d}_{candidate.candidate_id}"
            try:
                prediction = self._predict(candidate, action)
            except Exception as exc:  # candidate code is deliberately untrusted
                prediction = Prediction(
                    expected=None,
                    confidence=0,
                    rationale=f"candidate error: {type(exc).__name__}: {exc}",
                )
            item = FrozenPrediction(
                prediction_id=prediction_id,
                candidate_id=candidate.candidate_id,
                action=action,
                created_at=created_at,
                current_fingerprint=self.current.fingerprint,
                prediction=prediction,
            )
            frozen.append(item)
            self.store.append("prediction_frozen", item)
        return tuple(frozen)

    def step(self, action: Action) -> CycleResult:
        if self.current is None:
            raise RuntimeError("reset() must be called before step()")
        if self.current.available_actions and action.id not in self.current.available_actions:
            raise ValueError(f"Action {action.id} is not advertised by the environment")

        before = self.current
        predictions = self._freeze_predictions(action)
        actual = self.environment.step(action)
        transition = Transition(
            sequence=len(self.history) + 1,
            before=before,
            action=action,
            after=actual,
            episode=self.episode,
        )
        self.history.append(transition)
        self.current = actual
        self.store.append("transition", transition)

        evaluations: list[PredictionEvaluation] = []
        for frozen in predictions:
            expected = frozen.prediction.expected
            if expected is None:
                evaluation = PredictionEvaluation(
                    prediction_id=frozen.prediction_id,
                    candidate_id=frozen.candidate_id,
                    exact=None,
                    prospective_accuracy=0,
                    status_accuracy=0,
                    progress_accuracy=0,
                    coverage=0,
                    error=frozen.prediction.rationale or "candidate abstained",
                )
            else:
                comparison = self.environment.compare(expected, actual)
                evaluation = PredictionEvaluation(
                    prediction_id=frozen.prediction_id,
                    candidate_id=frozen.candidate_id,
                    exact=comparison.exact,
                    prospective_accuracy=comparison.prospective_accuracy,
                    status_accuracy=comparison.status_accuracy,
                    progress_accuracy=comparison.progress_accuracy,
                    coverage=1,
                )
            evaluations.append(evaluation)
            self.store.append("prediction_evaluated", evaluation)

        supervisor_events = self.supervisor.inspect(transition, evaluations)
        for event in supervisor_events:
            self.store.append("supervisor_event", event)
        return CycleResult(
            transition=transition,
            predictions=predictions,
            evaluations=tuple(evaluations),
            supervisor_events=supervisor_events,
        )
