"""Agent state models for the Overture system.

Tracks agent execution logs, task queues, and orchestration state
for the multi-agent hedge fund system.
"""

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class AgentType(str, enum.Enum):
    """Classification of agent roles in the system."""

    IDEA_GENERATOR = "idea_generator"
    IDEA_VALIDATOR = "idea_validator"
    TRADE_EXECUTOR = "trade_executor"
    TRADE_MONITOR = "trade_monitor"
    PORTFOLIO_CONSTRUCTOR = "portfolio_constructor"
    RISK_MANAGER = "risk_manager"
    REBALANCER = "rebalancer"
    KNOWLEDGE_CURATOR = "knowledge_curator"
    EDUCATOR = "educator"


class AgentLogStatus(str, enum.Enum):
    """Outcome status of an agent action."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"


class AgentTaskStatus(str, enum.Enum):
    """Lifecycle status of an agent task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentLog(Base):
    """Log entry for a single agent action or invocation.

    Captures the full context of an agent execution including
    input/output data, LLM usage, timing, and outcome status.
    Used for observability, debugging, and cost tracking.
    """

    __tablename__ = "agent_logs"

    agent_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    agent_type: Mapped[AgentType] = mapped_column(
        Enum(AgentType, name="agent_type", native_enum=False),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    input_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[AgentLogStatus] = mapped_column(
        Enum(AgentLogStatus, name="agent_log_status", native_enum=False),
        nullable=False,
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    token_usage: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Token usage breakdown: prompt_tokens, completion_tokens, total_tokens, cost",
    )

    # AgentLog only has created_at (no updated_at needed for immutable logs),
    # but we inherit both from Base. That is acceptable.

    def __repr__(self) -> str:
        return (
            f"<AgentLog(id={self.id!r}, agent_name={self.agent_name!r}, "
            f"action={self.action!r}, status={self.status!r})>"
        )


class AgentTask(Base):
    """A task in the agent orchestration queue.

    Represents a unit of work to be executed by an agent,
    supporting priority scheduling, hierarchical task
    decomposition via parent_task_id, and result tracking.
    """

    __tablename__ = "agent_tasks"

    task_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[AgentTaskStatus] = mapped_column(
        Enum(AgentTaskStatus, name="agent_task_status", native_enum=False),
        nullable=False,
        default=AgentTaskStatus.PENDING,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Higher values indicate higher priority",
    )
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    assigned_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    parent_task_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    parent_task: Mapped[Optional["AgentTask"]] = relationship(
        "AgentTask",
        remote_side="AgentTask.id",
        back_populates="subtasks",
        lazy="selectin",
    )
    subtasks: Mapped[list["AgentTask"]] = relationship(
        "AgentTask",
        back_populates="parent_task",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<AgentTask(id={self.id!r}, task_type={self.task_type!r}, "
            f"status={self.status!r}, priority={self.priority!r})>"
        )
