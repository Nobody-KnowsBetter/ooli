"""Core data models for DocGuard code changes, doc sections, and findings."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Verdict(str, Enum):
    CONFIRMED_DRIFT = "CONFIRMED_DRIFT"
    POSSIBLE_DRIFT = "POSSIBLE_DRIFT"
    NO_DRIFT_DETECTED = "NO_DRIFT_DETECTED"


class ChangeType(str, Enum):
    CONSTANT_CHANGED = "CONSTANT_CHANGED"
    FUNCTION_RENAMED = "FUNCTION_RENAMED"
    FUNCTION_REMOVED = "FUNCTION_REMOVED"
    FUNCTION_ADDED = "FUNCTION_ADDED"
    PARAMETER_CHANGED = "PARAMETER_CHANGED"
    PARAMETER_REMOVED = "PARAMETER_REMOVED"
    PARAMETER_ADDED = "PARAMETER_ADDED"
    RETURN_TYPE_CHANGED = "RETURN_TYPE_CHANGED"
    API_ENDPOINT_CHANGED = "API_ENDPOINT_CHANGED"
    API_ENDPOINT_REMOVED = "API_ENDPOINT_REMOVED"
    API_ENDPOINT_ADDED = "API_ENDPOINT_ADDED"
    CLASS_CHANGED = "CLASS_CHANGED"
    ENV_VAR_CHANGED = "ENV_VAR_CHANGED"
    OTHER = "OTHER"


@dataclass
class CodeChange:
    file_path: str
    change_type: ChangeType
    symbol_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    line_number: int = 1
    diff_hunk: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocSection:
    file_path: str
    title: str
    content: str
    start_line: int
    end_line: int
    code_blocks: list[str] = field(default_factory=list)
    symbols_mentioned: set[str] = field(default_factory=set)


@dataclass
class CandidatePair:
    change: CodeChange
    section: DocSection
    relevance_score: float = 0.0
    relevance_reason: str = ""


@dataclass
class Finding:
    verdict: Verdict
    confidence: float  # 0.0 to 1.0
    source_file: str
    changed_symbol: str
    doc_file: str
    doc_start_line: int
    doc_end_line: int
    outdated_excerpt: str
    explanation: str
    suggested_fix: str
    change_type: ChangeType = ChangeType.OTHER
    code_diff: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "confidence": round(self.confidence, 2),
            "source_file": self.source_file,
            "changed_symbol": self.changed_symbol,
            "doc_file": self.doc_file,
            "doc_start_line": self.doc_start_line,
            "doc_end_line": self.doc_end_line,
            "outdated_excerpt": self.outdated_excerpt,
            "explanation": self.explanation,
            "suggested_fix": self.suggested_fix,
            "change_type": self.change_type.value,
            "code_diff": self.code_diff,
            "evidence": self.evidence,
        }

