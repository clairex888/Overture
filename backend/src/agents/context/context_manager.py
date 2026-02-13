"""
Context Manager for the Overture multi-agent system.
Manages the shared context layer that teaches agents investment best practices
and allows users to customize with their own IP/preferences.
"""
from dataclasses import dataclass, field
from typing import Any

@dataclass
class InvestmentContext:
    """Structured investment context for agents."""
    base_principles: list[str]
    idea_generation_guidelines: dict[str, Any]
    validation_criteria: dict[str, Any]
    execution_rules: dict[str, Any]
    risk_management_rules: dict[str, Any]
    user_overrides: dict[str, Any] = field(default_factory=dict)

class ContextManager:
    """
    Manages the shared context layer that teaches agents investment best practices.
    Provides base context (standard best practices) + user-customizable overlays.
    """
    def __init__(self):
        self._base_context = self._build_base_context()
        self._user_contexts: dict[str, dict] = {}

    def _build_base_context(self) -> InvestmentContext:
        """Build the standard investment best practices context."""
        return InvestmentContext(
            base_principles=[
                "Always validate ideas with multiple independent data sources",
                "Size positions according to conviction and risk tolerance",
                "Never risk more than 2% of portfolio on a single trade",
                "Cut losses quickly, let winners run",
                "Consider macro environment and cross-asset correlations",
                "Be skeptical of crowded trades and consensus views",
                "Understand the thesis completely before entering any position",
                "Always have a clear exit plan before entering",
                "Monitor thesis validity continuously, not just price",
                "Diversify across timeframes, asset classes, and strategies",
            ],
            idea_generation_guidelines={
                "min_sources_for_idea": 2,
                "prefer_contrarian": True,
                "filter_noise_threshold": 0.3,
                "prioritize_catalysts": True,
                "screen_intervals": {"fundamental": "daily", "technical": "hourly", "news": "continuous"},
                "idea_quality_checklist": [
                    "Clear thesis with specific catalyst",
                    "Identifiable entry and exit points",
                    "Asymmetric risk/reward (>2:1)",
                    "Not highly correlated with existing positions",
                    "Supported by multiple data points",
                ],
            },
            validation_criteria={
                "min_backtest_sample_size": 20,
                "min_confidence_to_proceed": 0.6,
                "require_fundamental_check": True,
                "require_risk_assessment": True,
                "max_correlation_with_portfolio": 0.7,
                "reasoning_checks": [
                    "Is the thesis falsifiable?",
                    "What would invalidate this idea?",
                    "Is this priced in already?",
                    "What's the base rate for this type of trade?",
                ],
            },
            execution_rules={
                "max_position_size_pct": 5.0,
                "default_stop_loss_pct": 5.0,
                "min_risk_reward_ratio": 2.0,
                "scale_in_tranches": 3,
                "prefer_liquid_instruments": True,
                "consider_options_for_asymmetry": True,
                "timing_rules": {
                    "avoid_first_30min": True,
                    "avoid_last_15min": True,
                    "prefer_volume_confirmation": True,
                },
            },
            risk_management_rules={
                "max_portfolio_drawdown_pct": 15.0,
                "max_sector_concentration_pct": 30.0,
                "max_single_name_pct": 10.0,
                "daily_var_limit_pct": 3.0,
                "correlation_alert_threshold": 0.8,
                "rebalance_drift_threshold_pct": 5.0,
            },
        )

    def get_base_context(self) -> InvestmentContext:
        """Return standard best practices context."""
        return self._base_context

    def get_user_context(self, user_id: str) -> dict[str, Any]:
        """Return user-customized context overlays."""
        return self._user_contexts.get(user_id, {})

    def update_user_context(self, user_id: str, updates: dict[str, Any]) -> None:
        """Update user-specific context customizations."""
        if user_id not in self._user_contexts:
            self._user_contexts[user_id] = {}
        self._user_contexts[user_id].update(updates)

    def get_merged_context(self, user_id: str | None = None) -> dict[str, Any]:
        """Get merged context (base + user overrides) for agent consumption."""
        base = {
            "principles": self._base_context.base_principles,
            "idea_generation": self._base_context.idea_generation_guidelines,
            "validation": self._base_context.validation_criteria,
            "execution": self._base_context.execution_rules,
            "risk_management": self._base_context.risk_management_rules,
        }
        if user_id:
            user_ctx = self.get_user_context(user_id)
            # User overrides take precedence
            for key, value in user_ctx.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    base[key].update(value)
                else:
                    base[key] = value
        return base

    def get_context_for_agent(self, agent_type: str, user_id: str | None = None) -> str:
        """Get formatted context string for a specific agent type."""
        ctx = self.get_merged_context(user_id)

        sections = [f"## Investment Principles\n" + "\n".join(f"- {p}" for p in ctx["principles"])]

        if agent_type in ("idea_generator", "idea_validator"):
            guidelines = ctx["idea_generation"]
            sections.append(f"\n## Idea Generation Guidelines\n" +
                          "\n".join(f"- {k}: {v}" for k, v in guidelines.items()))

        if agent_type == "idea_validator":
            validation = ctx["validation"]
            sections.append(f"\n## Validation Criteria\n" +
                          "\n".join(f"- {k}: {v}" for k, v in validation.items()))

        if agent_type == "trade_executor":
            execution = ctx["execution"]
            sections.append(f"\n## Execution Rules\n" +
                          "\n".join(f"- {k}: {v}" for k, v in execution.items()))

        if agent_type in ("risk_manager", "portfolio_constructor", "rebalancer"):
            risk = ctx["risk_management"]
            sections.append(f"\n## Risk Management Rules\n" +
                          "\n".join(f"- {k}: {v}" for k, v in risk.items()))

        return "\n".join(sections)


# Singleton
context_manager = ContextManager()
