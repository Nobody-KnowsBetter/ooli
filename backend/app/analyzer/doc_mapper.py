"""Code-to-Documentation Candidate Mapper."""
from __future__ import annotations

import difflib
import re
from typing import Optional

from backend.app.analyzer.models import CandidatePair, ChangeType, CodeChange, DocSection

COMMON_WORDS = {
    "main", "git", "run", "test", "help", "app", "sys", "path", "file", "args",
    "data", "text", "get", "set", "docs", "doc", "change", "changes", "line",
    "lines", "code", "item", "items", "parser", "result", "results", "report",
    "reports", "name", "value", "key", "val", "dict", "list", "str", "int", "bool"
}


def map_changes_to_docs(
    changes: list[CodeChange],
    sections: list[DocSection],
    min_score: float = 0.35,
) -> list[CandidatePair]:
    """Finds candidate (CodeChange, DocSection) pairs using deterministic symbol indexing and lexical similarity."""
    candidates: list[CandidatePair] = []

    for change in changes:
        # Added functions rarely invalidate existing documentation
        if change.change_type == ChangeType.FUNCTION_ADDED:
            continue

        sym_name = change.symbol_name.split(".")[-1]  # In case of Class.method or func.param
        raw_sym = change.symbol_name
        old_val = change.old_value
        new_val = change.new_value

        is_common_word = sym_name.lower() in COMMON_WORDS

        for sec in sections:
            score = 0.0
            reasons: list[str] = []

            # 1. Exact symbol mention
            if raw_sym in sec.symbols_mentioned or sym_name in sec.symbols_mentioned:
                score += 0.6
                reasons.append(f"Symbol '{sym_name}' explicitly mentioned")
            elif not is_common_word and re.search(rf"\b{re.escape(sym_name)}\b", sec.content):
                score += 0.45
                reasons.append(f"Symbol '{sym_name}' found in text")

            # 2. Check old value vs new value for constants and configs
            if change.change_type in {ChangeType.CONSTANT_CHANGED, ChangeType.PARAMETER_CHANGED, ChangeType.ENV_VAR_CHANGED}:
                if old_val and old_val in sec.content:
                    score += 0.35
                    reasons.append(f"Old value '{old_val}' present in section")
                if new_val and new_val in sec.content:
                    score -= 0.25

            # 3. For function rename or removal
            if change.change_type in {ChangeType.FUNCTION_RENAMED, ChangeType.FUNCTION_REMOVED}:
                old_func = change.old_value or sym_name
                if old_func in sec.symbols_mentioned:
                    score += 0.6
                    reasons.append(f"Old function name '{old_func}' found in section")
                elif not is_common_word and re.search(rf"\b{re.escape(old_func)}\b", sec.content):
                    score += 0.45
                    reasons.append(f"Old function name '{old_func}' found in text")

            # 4. For parameter changes
            if change.change_type in {ChangeType.PARAMETER_REMOVED, ChangeType.PARAMETER_ADDED}:
                details = change.details
                removed_args = details.get("removed_args", [])
                func_name = details.get("function", sym_name)
                func_in_sec = (func_name in sec.symbols_mentioned) or (func_name in sec.content)

                for r_arg in removed_args:
                    if r_arg in sec.content and func_in_sec:
                        score += 0.5
                        reasons.append(f"Removed parameter '{r_arg}' found near '{func_name}'")

            # 5. For API Endpoints
            if change.change_type == ChangeType.API_ENDPOINT_CHANGED:
                old_ep = change.details.get("old_endpoint", {})
                old_path = old_ep.get("path")
                if old_path and old_path in sec.content:
                    score += 0.65
                    reasons.append(f"Old API path '{old_path}' referenced in doc")

            if score >= min_score:
                candidates.append(
                    CandidatePair(
                        change=change,
                        section=sec,
                        relevance_score=min(score, 1.0),
                        relevance_reason="; ".join(reasons),
                    )
                )

    return candidates
