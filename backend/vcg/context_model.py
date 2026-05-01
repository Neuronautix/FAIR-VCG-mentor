import dataclasses
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ResearchContext:
    domain: str = ""                    # "pharmacology"|"neuroscience"|"toxicology"|"oncology"|"other"
    study_type: str = ""                # "dose_response"|"parallel_group"|"longitudinal"|"observational"
    design: str = ""                    # "parallel_group"|"crossover"|"repeated_measures"
    n_timepoints: Optional[int] = None
    confirmed_by_user: bool = False


@dataclass
class ColumnRoles:
    subject_id: Optional[str] = None
    treatment_col: Optional[str] = None
    treatment_value: Optional[str] = None   # e.g. "DrugA_10mg"
    control_value: Optional[str] = None     # e.g. "Vehicle"
    outcome_cols: List[str] = field(default_factory=list)
    covariate_cols: List[str] = field(default_factory=list)
    time_col: Optional[str] = None
    exclude_cols: List[str] = field(default_factory=list)


@dataclass
class VCGConfig:
    method: str = "auto"               # "bootstrap"|"synthetic"|"auto"
    n_synthetic: int = 30
    seed: int = 42
    bootstrap_iters: int = 1000
    confidence_level: float = 0.95


@dataclass
class OrchestratorTurn:
    role: str                           # "agent"
    content: str                        # markdown message
    state: str                          # current state name
    options: List[str] = field(default_factory=list)   # quick-reply buttons
    context_delta: Dict[str, Any] = field(default_factory=dict)
    ready_to_build: bool = False


def context_to_dict(ctx: ResearchContext) -> dict:
    return dataclasses.asdict(ctx)


def roles_to_dict(roles: ColumnRoles) -> dict:
    return dataclasses.asdict(roles)


def config_to_dict(cfg: VCGConfig) -> dict:
    return dataclasses.asdict(cfg)


def dict_to_context(d: dict) -> ResearchContext:
    return ResearchContext(
        domain=d.get("domain", ""),
        study_type=d.get("study_type", ""),
        design=d.get("design", ""),
        n_timepoints=d.get("n_timepoints"),
        confirmed_by_user=d.get("confirmed_by_user", False),
    )


def dict_to_roles(d: dict) -> ColumnRoles:
    return ColumnRoles(
        subject_id=d.get("subject_id"),
        treatment_col=d.get("treatment_col"),
        treatment_value=d.get("treatment_value"),
        control_value=d.get("control_value"),
        outcome_cols=d.get("outcome_cols", []),
        covariate_cols=d.get("covariate_cols", []),
        time_col=d.get("time_col"),
        exclude_cols=d.get("exclude_cols", []),
    )


def dict_to_config(d: dict) -> VCGConfig:
    return VCGConfig(
        method=d.get("method", "auto"),
        n_synthetic=d.get("n_synthetic", 30),
        seed=d.get("seed", 42),
        bootstrap_iters=d.get("bootstrap_iters", 1000),
        confidence_level=d.get("confidence_level", 0.95),
    )


def DEFAULT_VCG_SESSION() -> dict:
    return {
        "research_context": context_to_dict(ResearchContext()),
        "column_roles": roles_to_dict(ColumnRoles()),
        "vcg_config": config_to_dict(VCGConfig()),
        "conversation": [],
        "vcg_status": "not_started",
        "vcg_error": None,
        "vcg_results": None,
    }
