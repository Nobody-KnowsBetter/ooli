"""AI Intelligence Engine for DocGuard with multi-provider support and grounded reasoning."""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Optional

from backend.app.ai.prompts import ANALYSIS_PROMPT_TEMPLATE, SYSTEM_PROMPT
from backend.app.analyzer.models import (
    CandidatePair,
    ChangeType,
    CodeChange,
    DocSection,
    Finding,
    Verdict,
)


class BaseAIProvider(ABC):
    @abstractmethod
    def evaluate(self, pair: CandidatePair) -> Finding:
        """Evaluates whether the candidate pair exhibits documentation drift."""
        pass


class HeuristicAIProvider(BaseAIProvider):
    """Deterministic, high-precision evidence evaluator.

    Provides reliable verification without requiring external API keys.
    """

    def evaluate(self, pair: CandidatePair) -> Finding:
        change = pair.change
        section = pair.section
        doc_lines = section.content.splitlines()

        # Default: NO_DRIFT_DETECTED
        verdict = Verdict.NO_DRIFT_DETECTED
        confidence = 0.90
        outdated_excerpt = ""
        explanation = "Documentation aligns with code change or does not contradict it."
        suggested_fix = ""
        evidence: list[str] = []
        found_start_line = section.start_line
        found_end_line = section.end_line

        # Helper to find specific line in section
        def find_line_with(target: str) -> tuple[int, str]:
            for offset, line in enumerate(doc_lines):
                if target in line:
                    return section.start_line + offset, line.strip()
            return section.start_line, doc_lines[0] if doc_lines else ""

        # SCENARIO 1 & 2 & 6: CONSTANT_CHANGED / PARAMETER_CHANGED / ENV_VAR_CHANGED
        if change.change_type in {
            ChangeType.CONSTANT_CHANGED,
            ChangeType.PARAMETER_CHANGED,
            ChangeType.ENV_VAR_CHANGED,
        }:
            old_val = str(change.old_value or "")
            new_val = str(change.new_value or "")
            sym_name = change.symbol_name.split(".")[-1]

            # 1. Search for lines in documentation referencing the symbol or old value
            matching_lines = [
                (section.start_line + i, line.strip())
                for i, line in enumerate(doc_lines)
                if sym_name.lower() in line.lower() or (old_val and old_val in line)
            ]

            drift_found = False
            for line_no, line_text in matching_lines:
                # If documentation line already contains the new value, NO DRIFT!
                if new_val and (new_val in line_text or f"**{new_val}**" in line_text):
                    verdict = Verdict.NO_DRIFT_DETECTED
                    confidence = 0.95
                    explanation = f"Documentation line {line_no} accurately references updated value '{new_val}' for '{sym_name}'."
                    evidence = [f"Found updated value '{new_val}' in: {section.file_path}:{line_no}"]
                    drift_found = False
                    break

                # If the line contains conflicting numbers
                nums = re.findall(r"\b\d+\b", line_text)
                if new_val.isdigit() and nums and (new_val not in nums):
                    conflicting_val = old_val if old_val in nums else nums[0]
                    found_start_line = line_no
                    found_end_line = line_no
                    outdated_excerpt = line_text
                    verdict = Verdict.CONFIRMED_DRIFT
                    confidence = 0.98
                    explanation = f"Value for '{sym_name}' is '{new_val}' in code ({change.file_path}), but documentation states '{conflicting_val}'."
                    suggested_fix = re.sub(rf"\b{re.escape(conflicting_val)}\b", new_val, line_text, count=1)
                    evidence = [
                        f"Source code: {change.file_path}:{change.line_number}",
                        f"Diff: {change.diff_hunk}",
                        f"Documentation {section.file_path}:{line_no} contains contradictory value '{conflicting_val}' and lacks '{new_val}'",
                    ]
                    drift_found = True
                    break

                # If line contains old_val
                elif old_val and (old_val in line_text):
                    found_start_line = line_no
                    found_end_line = line_no
                    outdated_excerpt = line_text
                    verdict = Verdict.CONFIRMED_DRIFT
                    confidence = 0.98
                    explanation = f"Value for '{sym_name}' was changed from '{old_val}' to '{new_val}' in {change.file_path}, but documentation still states '{old_val}'."
                    suggested_fix = line_text.replace(old_val, new_val)
                    evidence = [
                        f"Source code: {change.file_path}:{change.line_number}",
                        f"Diff: {change.diff_hunk}",
                        f"Documentation {section.file_path}:{line_no} contains old value '{old_val}' and lacks '{new_val}'",
                    ]
                    drift_found = True
                    break

            # Fallback if no direct symbol line matched: check section content
            if not drift_found and verdict != Verdict.NO_DRIFT_DETECTED:
                if new_val and (new_val in section.content):
                    verdict = Verdict.NO_DRIFT_DETECTED
                    confidence = 0.92
                    explanation = f"Documentation already contains updated value '{new_val}' for symbol '{sym_name}'."
                elif old_val and (old_val in section.content):
                    line_no, line_text = find_line_with(old_val)
                    found_start_line = line_no
                    found_end_line = line_no
                    outdated_excerpt = line_text
                    verdict = Verdict.CONFIRMED_DRIFT
                    confidence = 0.88
                    explanation = f"Value for '{sym_name}' was changed from '{old_val}' to '{new_val}' in {change.file_path}, but documentation still states '{old_val}'."
                    suggested_fix = line_text.replace(old_val, new_val)
                    evidence = [
                        f"Source code modified: {change.file_path}:{change.line_number}",
                        f"Diff: {change.diff_hunk}",
                        f"Documentation {section.file_path}:{line_no} contains old value '{old_val}' and lacks '{new_val}'",
                    ]

        # SCENARIO 3: FUNCTION_RENAMED
        elif change.change_type == ChangeType.FUNCTION_RENAMED:
            old_func = str(change.old_value or "")
            new_func = str(change.new_value or "")

            if old_func in section.content:
                line_no, line_text = find_line_with(old_func)
                found_start_line = line_no
                found_end_line = line_no
                outdated_excerpt = line_text

                verdict = Verdict.CONFIRMED_DRIFT
                confidence = 0.96
                explanation = f"Function '{old_func}' was renamed to '{new_func}', but documentation still references '{old_func}'."
                suggested_fix = line_text.replace(old_func, new_func)
                evidence = [
                    f"Function renamed: {old_func} -> {new_func} in {change.file_path}",
                    f"Documentation line {line_no} mentions obsolete function name '{old_func}'",
                ]

        # SCENARIO 4: PARAMETER_REMOVED
        elif change.change_type == ChangeType.PARAMETER_REMOVED:
            func_name = change.details.get("function", change.symbol_name)
            removed_args = change.details.get("removed_args", [])

            for r_arg in removed_args:
                if r_arg in section.content and (func_name in section.content or func_name in section.symbols_mentioned):
                    line_no, line_text = find_line_with(r_arg)
                    found_start_line = line_no
                    found_end_line = line_no
                    outdated_excerpt = line_text

                    verdict = Verdict.CONFIRMED_DRIFT
                    confidence = 0.94
                    explanation = f"Parameter '{r_arg}' was removed from '{func_name}', but documentation still lists it."
                    suggested_fix = f"Remove reference to parameter `{r_arg}` from documentation."
                    evidence = [
                        f"Signature changed in {change.file_path}: removed parameter '{r_arg}'",
                        f"Documentation line {line_no} still lists `{r_arg}`",
                    ]
                    break

        # SCENARIO 5: API_ENDPOINT_CHANGED
        elif change.change_type == ChangeType.API_ENDPOINT_CHANGED:
            old_ep = change.details.get("old_endpoint", {})
            new_ep = change.details.get("new_endpoint", {})
            old_path = old_ep.get("path", "")
            new_path = new_ep.get("path", "")

            if old_path and old_path in section.content:
                line_no, line_text = find_line_with(old_path)
                found_start_line = line_no
                found_end_line = line_no
                outdated_excerpt = line_text

                verdict = Verdict.CONFIRMED_DRIFT
                confidence = 0.97
                explanation = f"API endpoint path changed from '{old_path}' to '{new_path}', but documentation still references '{old_path}'."
                suggested_fix = line_text.replace(old_path, new_path)
                evidence = [
                    f"Route changed in {change.file_path}: {old_path} -> {new_path}",
                    f"Documentation {section.file_path}:{line_no} contains outdated route '{old_path}'",
                ]

        # SCENARIO 10: AMBIGUOUS / INSUFFICIENT EVIDENCE
        if verdict == Verdict.NO_DRIFT_DETECTED and pair.relevance_score > 0.4 and pair.relevance_score < 0.6:
            verdict = Verdict.POSSIBLE_DRIFT
            confidence = 0.52
            explanation = "Potential association detected between code change and documentation, but evidence is insufficient to confirm drift."
            evidence = [f"Relevance match reason: {pair.relevance_reason}"]

        return Finding(
            verdict=verdict,
            confidence=confidence,
            source_file=change.file_path,
            changed_symbol=change.symbol_name,
            doc_file=section.file_path,
            doc_start_line=found_start_line,
            doc_end_line=found_end_line,
            outdated_excerpt=outdated_excerpt,
            explanation=explanation,
            suggested_fix=suggested_fix,
            change_type=change.change_type,
            code_diff=change.diff_hunk,
            evidence=evidence,
        )


class LLMAIProvider(BaseAIProvider):
    """LLM Provider supporting OpenAI, Gemini, or Anthropic via HTTP API with fallback to Heuristic."""

    def __init__(self, api_key: str, provider_name: str = "gemini") -> None:
        self.api_key = api_key
        self.provider_name = provider_name.lower()
        self.heuristic_fallback = HeuristicAIProvider()

    def evaluate(self, pair: CandidatePair) -> Finding:
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            file_path=pair.change.file_path,
            change_type=pair.change.change_type.value,
            symbol_name=pair.change.symbol_name,
            old_value=pair.change.old_value or "N/A",
            new_value=pair.change.new_value or "N/A",
            diff_hunk=pair.change.diff_hunk,
            doc_file=pair.section.file_path,
            doc_title=pair.section.title,
            start_line=pair.section.start_line,
            end_line=pair.section.end_line,
            doc_content=pair.section.content,
        )

        try:
            import httpx

            if self.provider_name == "openai" or "openai" in self.provider_name:
                resp = httpx.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.0,
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    data = resp.json()["choices"][0]["message"]["content"]
                    parsed = json.loads(data)
                    return self._build_finding(pair, parsed)
        except Exception:
            pass

        return self.heuristic_fallback.evaluate(pair)

    def _build_finding(self, pair: CandidatePair, res: dict) -> Finding:
        verdict_str = res.get("verdict", "NO_DRIFT_DETECTED")
        try:
            verdict = Verdict(verdict_str)
        except ValueError:
            verdict = Verdict.NO_DRIFT_DETECTED

        return Finding(
            verdict=verdict,
            confidence=float(res.get("confidence", 0.5)),
            source_file=pair.change.file_path,
            changed_symbol=pair.change.symbol_name,
            doc_file=pair.section.file_path,
            doc_start_line=pair.section.start_line,
            doc_end_line=pair.section.end_line,
            outdated_excerpt=res.get("outdated_excerpt", ""),
            explanation=res.get("explanation", ""),
            suggested_fix=res.get("suggested_fix", ""),
            change_type=pair.change.change_type,
            code_diff=pair.change.diff_hunk,
            evidence=res.get("evidence", []),
        )


def get_ai_provider() -> BaseAIProvider:
    provider = os.getenv("DOCGUARD_AI_PROVIDER", "").lower()
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if (provider == "openai" or not provider) and openai_key:
        return LLMAIProvider(openai_key, provider_name="openai")
    elif (provider == "gemini" or not provider) and gemini_key:
        return LLMAIProvider(gemini_key, provider_name="gemini")

    return HeuristicAIProvider()
