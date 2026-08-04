"""
Typed failures.

Under the replay cursor every module runs against as little as three days of
data, and against uploads that may be missing whole tables. The rule the API
depends on: a module returns a valid result or raises one of these — never an
unhandled exception, and never a NaN in a headline KPI.

Each carries enough structure for the frontend to render a specific, useful
message ("needs transactions.csv", "needs 6 months, has 2") rather than a
generic error card.
"""

from __future__ import annotations


class AnalysisError(Exception):
    """Base for anything the orchestrator should turn into a non-ok envelope."""

    status = "unavailable"

    def as_dict(self) -> dict:
        return {"status": self.status, "reason": str(self)}


class MissingTable(AnalysisError):
    """A required table was not supplied — typical for partial uploads."""

    status = "unavailable"

    def __init__(self, module: str, required: list[str], present: list[str]):
        self.module = module
        self.required = required
        self.present = present
        missing = [t for t in required if t not in present]
        super().__init__(
            f"{module} requires {', '.join(f'{m}.csv' for m in missing)}"
        )

    def as_dict(self) -> dict:
        return {**super().as_dict(), "module": self.module,
                "required": self.required, "present": self.present}


class InsufficientData(AnalysisError):
    """Tables are present but too small or too short to compute honestly."""

    status = "insufficient_data"

    def __init__(self, module: str, need: str, have: str):
        self.module = module
        self.need = need
        self.have = have
        super().__init__(f"{module} needs {need}; has {have}")

    def as_dict(self) -> dict:
        return {**super().as_dict(), "module": self.module,
                "need": self.need, "have": self.have}


class SchemaError(AnalysisError):
    """An uploaded table could not be reconciled with the expected schema."""

    status = "error"

    def __init__(self, table: str, message: str, column: str | None = None,
                 sample_values: list | None = None):
        self.table = table
        self.column = column
        self.sample_values = sample_values or []
        super().__init__(message)

    def as_dict(self) -> dict:
        return {**super().as_dict(), "table": self.table, "column": self.column,
                "sample_values": self.sample_values}


def require(bundle, module: str, *tables: str) -> None:
    """Raise `MissingTable` unless every named table is present and non-empty."""
    present = list(bundle.tables)
    if not bundle.has(*tables):
        raise MissingTable(module, list(tables), present)
