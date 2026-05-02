import re
from datetime import datetime
from typing import Any, Dict, List

from vcg.constants import CONTROL_KEYWORDS as _CONTROL_KEYWORDS_LIST

_CONTROL_KEYWORDS = set(_CONTROL_KEYWORDS_LIST)

STATES = [
    "GREETING",
    "TREATMENT_CONFIRM",
    "ENDPOINT_SELECT",
    "COVARIATE_SELECT",
    "SAMPLE_SIZE",
    "METHOD_SELECT",
    "SUMMARY_CONFIRM",
    "READY_TO_BUILD",
    "BUILDING",
    "DONE",
    "ERROR",
]

class VCGOrchestrator:
    """
    Rule-based conversation engine for VCG setup.
    Generates context-aware questions from profiler output.
    Builds ResearchContext through dialogue without requiring an external AI API.
    """

    def __init__(self, session: Dict[str, Any]):
        self.session = session
        self.columns = session["columns"]
        self.ts = session["table_structure"]
        self.import_info = session["import_info"]

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> dict:
        """Generate the first agent message."""
        return self._generate_greeting()

    def respond(self, user_message: str) -> dict:
        """Process a user reply and generate the next agent message."""
        self._add_user_msg(user_message)
        state = self._current_state()

        handlers = {
            "GREETING": self._handle_greeting,
            "TREATMENT_CONFIRM": self._handle_treatment,
            "ENDPOINT_SELECT": self._handle_endpoints,
            "COVARIATE_SELECT": self._handle_covariates,
            "SAMPLE_SIZE": self._handle_sample_size,
            "METHOD_SELECT": self._handle_method,
            "SUMMARY_CONFIRM": self._handle_confirm,
        }
        handler = handlers.get(state)
        if handler:
            return handler(user_message)
        return self._agent_msg(
            "I'm not sure how to proceed. You can use the **VCG Wizard** to review all settings.",
            state, ["Open Wizard"]
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_yes_no(text: str) -> bool:
        """Return True if text expresses affirmation, False otherwise."""
        t = text.lower().strip()
        return bool(re.search(r"\b(yes|yeah|yep|yup|sure|ok|okay|correct|go|proceed|generate|confirm|all)\b", t))

    def _vcg(self) -> dict:
        return self.session["vcg"]

    def _conv(self) -> list:
        return self._vcg()["conversation"]

    def _current_state(self) -> str:
        for msg in reversed(self._conv()):
            if msg["role"] == "agent":
                return msg.get("state", "GREETING")
        return "GREETING"

    def _add_user_msg(self, text: str) -> None:
        self._conv().append({"role": "user", "content": text, "timestamp": datetime.now().isoformat()})

    def _agent_msg(self, content: str, state: str, options: List[str], ready_to_build: bool = False) -> dict:
        msg = {
            "role": "agent",
            "content": content,
            "state": state,
            "options": options,
            "ready_to_build": ready_to_build,
            "timestamp": datetime.now().isoformat(),
        }
        self._conv().append(msg)
        return msg

    def _treatment_candidates(self) -> List[dict]:
        return [c for c in self.columns if c["inferred_type"] == "experimental_condition"]

    def _measurement_cols(self) -> List[str]:
        return [c["name"] for c in self.columns if c["inferred_type"] == "measurement"]

    def _covariate_candidates(self) -> List[str]:
        bio_names = {"sex", "gender", "age", "strain", "genotype", "breed", "species"}
        return [
            c["name"] for c in self.columns
            if c["inferred_type"] == "biological_descriptor"
            and c["name"].lower() in bio_names
        ]

    # ── State generators ───────────────────────────────────────────────────────

    def _generate_greeting(self) -> dict:
        n_rows = self.import_info["n_rows"]
        n_cols = self.import_info["n_columns"]
        entity = self.ts.get("primary_entity", "entity")
        measurements = self._measurement_cols()
        candidates = self._treatment_candidates()

        lines = [f"I've analysed your dataset — **{n_rows} rows, {n_cols} columns**."]

        if candidates:
            col = candidates[0]
            vals = col.get("sample_values", [])[:6]
            lines.append(f"\n**Detected group column**: `{col['name']}` → {', '.join(f'`{v}`' for v in vals)}")

        if measurements:
            lines.append(f"**Detected measurements**: {', '.join(f'`{m}`' for m in measurements[:5])}")

        lines.append(f"**Primary entity**: {entity}")
        lines.append("\nDoes this look like a pre-clinical pharmacology, toxicology, or dose-response study?")

        return self._agent_msg(
            "\n".join(lines), "GREETING",
            ["Yes, that's correct", "No, let me describe it"]
        )

    def _handle_greeting(self, reply: str) -> dict:
        if self._parse_yes_no(reply):
            ctx = self._vcg()["research_context"]
            if not ctx.get("study_type"):
                ctx["study_type"] = "pre_clinical_in_vivo"
        return self._ask_treatment()

    def _ask_treatment(self) -> dict:
        candidates = self._treatment_candidates()
        if candidates:
            col = candidates[0]
            vals = col.get("sample_values", [])[:8]
            self._vcg()["column_roles"]["treatment_col"] = col["name"]

            control_guess = next(
                (v for v in vals if any(k in str(v).lower() for k in _CONTROL_KEYWORDS)), None
            )
            if control_guess:
                other_vals = [v for v in vals if v != control_guess]
                treatment_guess = other_vals[0] if other_vals else None
                content = (
                    f"I think **`{col['name']}`** is your group column.\n\n"
                    f"Values: {', '.join(f'`{v}`' for v in vals)}\n\n"
                    f"Is **`{control_guess}`** the **control group** (e.g. vehicle/untreated)?"
                )
                options = [f"Yes, `{control_guess}` is control"] + [f"`{v}` is control" for v in other_vals[:3]] + ["None of these"]
                self._vcg()["column_roles"]["control_value"] = str(control_guess)
                if treatment_guess:
                    self._vcg()["column_roles"]["treatment_value"] = str(treatment_guess)
            else:
                content = (
                    f"I think **`{col['name']}`** is your group column.\n\n"
                    f"Values found: {', '.join(f'`{v}`' for v in vals)}\n\n"
                    "Which value is the **control group** (e.g. vehicle, untreated)?"
                )
                options = [f"`{v}`" for v in vals[:5]]
        else:
            cat_cols = [c for c in self.columns if c["inferred_type"] in ("experimental_condition", "categorical")]
            content = (
                "I couldn't automatically detect a treatment/group column.\n\n"
                "Which column identifies treatment vs. control groups?"
            )
            options = [c["name"] for c in cat_cols[:6]] + ["I'll set it in the Wizard"]

        return self._agent_msg(content, "TREATMENT_CONFIRM", options)

    def _handle_treatment(self, reply: str) -> dict:
        roles = self._vcg()["column_roles"]
        candidates = self._treatment_candidates()
        if candidates:
            vals = candidates[0].get("sample_values", [])
            # Try to identify which value the user chose as control
            for v in vals:
                if str(v).lower() in reply.lower() or reply.strip().strip("`'\"") == str(v):
                    roles["control_value"] = str(v)
                    others = [str(ov) for ov in vals if str(ov) != str(v)]
                    if others:
                        roles["treatment_value"] = others[0]
                    break
        return self._ask_endpoints()

    def _ask_endpoints(self) -> dict:
        measurements = self._measurement_cols()
        if not measurements:
            measurements = [c["name"] for c in self.columns if c["data_type"] in ("number", "integer")][:6]

        if measurements:
            content = (
                f"Which **measurements** should the VCG replicate?\n\n"
                f"Detected: {', '.join(f'`{m}`' for m in measurements)}"
            )
            options = ["All of the above"] + measurements[:4] + ["I'll select in the Wizard"]
        else:
            content = "I couldn't detect numeric measurement columns. Which columns are your primary outcomes?"
            options = [c["name"] for c in self.columns if c["data_type"] in ("number", "integer")][:6]

        return self._agent_msg(content, "ENDPOINT_SELECT", options)

    def _handle_endpoints(self, reply: str) -> dict:
        roles = self._vcg()["column_roles"]
        measurements = self._measurement_cols()
        if not measurements:
            measurements = [c["name"] for c in self.columns if c["data_type"] in ("number", "integer")]

        if "all" in reply.lower() or "wizard" in reply.lower():
            roles["outcome_cols"] = measurements
        else:
            selected = [m for m in measurements if m.lower() in reply.lower() or reply.lower().strip("`'\" ") == m.lower()]
            roles["outcome_cols"] = selected if selected else measurements

        return self._ask_covariates()

    def _ask_covariates(self) -> dict:
        covs = self._covariate_candidates()
        if covs:
            content = (
                f"Should the VCG be **balanced** on {', '.join(f'`{c}`' for c in covs)}?\n\n"
                "Balancing ensures the VCG matches the control group's covariate distribution."
            )
            options = ["Yes, balance on all"] + [f"Balance on `{c}`" for c in covs[:3]] + ["No, skip"]
        else:
            content = "No biological covariates detected (sex, strain, age). Should I balance on any other column?"
            bio_cols = [c["name"] for c in self.columns if c["inferred_type"] == "biological_descriptor"][:4]
            options = ["No, skip balancing"] + bio_cols

        return self._agent_msg(content, "COVARIATE_SELECT", options)

    def _handle_covariates(self, reply: str) -> dict:
        roles = self._vcg()["column_roles"]
        covs = self._covariate_candidates()
        reply_lower = reply.lower()

        if "skip" in reply_lower or not self._parse_yes_no(reply):
            roles["covariate_cols"] = []
        elif "all" in reply_lower:
            roles["covariate_cols"] = covs
        else:
            selected = [c for c in covs if c.lower() in reply_lower]
            roles["covariate_cols"] = selected if selected else covs

        return self._ask_sample_size()

    def _ask_sample_size(self) -> dict:
        n_rows = self.import_info["n_rows"]
        n_estimate = max(5, n_rows // 4)
        recommended = min(n_estimate * 3, 150)
        opts = [str(x) for x in sorted({n_estimate * 2, recommended, min(n_estimate * 5, 200)})]

        content = (
            f"How many **virtual control subjects** should I generate?\n\n"
            f"Standard practice is 3–5× the concurrent control group size.\n"
            f"_(Estimated control group: ~{n_estimate} subjects → recommended: **{recommended}**)_"
        )
        return self._agent_msg(content, "SAMPLE_SIZE", opts + ["Custom"])

    def _handle_sample_size(self, reply: str) -> dict:
        config = self._vcg()["vcg_config"]
        numbers = re.findall(r"\d+", reply)
        config["n_synthetic"] = int(numbers[0]) if numbers else 90
        return self._ask_method()

    def _ask_method(self) -> dict:
        n_rows = self.import_info["n_rows"]
        n_control = max(5, n_rows // 4)

        if n_control >= 15:
            rec = "bootstrap"
            reason = f"N≈{n_control} is adequate for parametric bootstrap with Gaussian copula (preserves correlations between endpoints)."
        else:
            rec = "synthetic"
            reason = f"N≈{n_control} is small — KDE/Normal sampling is more conservative."

        content = (
            f"**Recommended method**: `{rec}`\n_{reason}_\n\n"
            "- **Bootstrap** (Gaussian copula): fits marginal distributions, preserves inter-endpoint correlations\n"
            "- **Synthetic** (KDE/Normal): independently samples each endpoint, best for very small N\n"
            "- **Auto**: I choose based on your data _(recommended)_"
        )
        return self._agent_msg(content, "METHOD_SELECT",
                               ["Auto (recommended)", "Bootstrap", "Synthetic", "Explain difference"])

    def _handle_method(self, reply: str) -> dict:
        config = self._vcg()["vcg_config"]
        reply_lower = reply.lower()

        if "explain" in reply_lower:
            content = (
                "**Bootstrap** fits the best statistical distribution (Normal/Log-Normal/Gamma) to each "
                "endpoint and uses a Gaussian copula to preserve correlations. Best for N≥15.\n\n"
                "**Synthetic (KDE)** uses kernel density estimation or a Normal distribution to independently "
                "sample each endpoint. Faster, more conservative, ideal for N<15.\n\n"
                "Which would you like?"
            )
            return self._agent_msg(content, "METHOD_SELECT", ["Auto (recommended)", "Bootstrap", "Synthetic"])

        if "bootstrap" in reply_lower:
            config["method"] = "bootstrap"
        elif "synthetic" in reply_lower:
            config["method"] = "synthetic"
        else:
            config["method"] = "auto"

        return self._ask_summary()

    def _ask_summary(self) -> dict:
        roles = self._vcg()["column_roles"]
        config = self._vcg()["vcg_config"]
        method = config["method"].title() if config["method"] != "auto" else "Auto-select"

        rows = [
            f"| Treatment column | `{roles.get('treatment_col') or 'not set'}` |",
            f"| Control group | `{roles.get('control_value') or 'not set'}` |",
            f"| Endpoints | {', '.join(f'`{c}`' for c in roles.get('outcome_cols', [])) or '_none_'} |",
            f"| Covariates balanced | {', '.join(f'`{c}`' for c in roles.get('covariate_cols', [])) or '_none_'} |",
            f"| VCG size | {config.get('n_synthetic', 30)} subjects |",
            f"| Method | {method} |",
            f"| Seed | {config.get('seed', 42)} |",
        ]
        content = "**Ready to build.** Summary:\n\n| Parameter | Value |\n|---|---|\n" + "\n".join(rows) + "\n\nShall I proceed?"
        return self._agent_msg(content, "SUMMARY_CONFIRM", ["Yes, generate VCG", "Modify settings"])

    def _handle_confirm(self, reply: str) -> dict:
        if self._parse_yes_no(reply):
            self._vcg()["research_context"]["confirmed_by_user"] = True
            return self._agent_msg(
                "Starting VCG generation. Running:\n"
                "1. **Data Ingestion Agent** — validating your data\n"
                "2. **Standardization Agent** — harmonising units and handling missing values\n"
                "3. **VCG Builder Agent** — generating synthetic controls\n"
                "4. **Statistics Agent** — effect sizes, power, diagnostics\n\n"
                "_This usually takes 2–10 seconds…_",
                "READY_TO_BUILD", [], ready_to_build=True
            )
        return self._agent_msg(
            "No problem. You can modify settings in the **VCG Wizard** or continue chatting.",
            "SUMMARY_CONFIRM",
            ["Open Wizard", "Change control group", "Change endpoints", "Change sample size"]
        )
