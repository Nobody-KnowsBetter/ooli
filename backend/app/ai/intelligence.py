"""DocGuard's decision engine: exact rules, plus a small local Qwen model for ambiguous sentences."""
from __future__ import annotations

import json
import os
import re
import sys
from abc import ABC, abstractmethod

import httpx

from backend.app.ai.prompts import ANALYSIS_PROMPT_TEMPLATE, SYSTEM_PROMPT
from backend.app.analyzer.models import (
    CandidatePair,
    ChangeType,
    CodeChange,
    DocSection,
    Finding,
    Verdict,
)
from backend.app.analyzer.doc_mapper import clean_value, contains_flag, contains_value

DEFAULT_MODEL = "qwen2.5-coder:3b"
MODEL_TIMEOUT_SECONDS = 180.0
MODEL_CHECK_TIMEOUT_SECONDS = 10.0  # Long enough for a server overseas to reach a tunnel.
MAX_SENTENCES_PER_SECTION = 4


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
            old_val = clean_value(change.old_value)
            new_val = clean_value(change.new_value)
            sym_name = change.symbol_name.split(".")[-1]
            # TIMEOUT_SECONDS -> "timeout", "seconds": how prose usually refers to a symbol.
            name_words = [w for w in re.split(r"[_\W]+", sym_name.lower()) if len(w) > 2]

            for offset, line_text in enumerate(doc_lines):
                if not old_val or not contains_value(old_val, line_text) or contains_value(new_val, line_text):
                    continue

                lowered = line_text.lower()
                names_symbol = sym_name.lower() in lowered or any(
                    re.search(rf"\b{re.escape(w)}", lowered) for w in name_words
                )
                line_no = section.start_line + offset
                found_start_line = found_end_line = line_no
                outdated_excerpt = line_text.strip()
                suggested_fix = re.sub(rf"(?<![\w.]){re.escape(old_val)}(?!\w|\.\d)", new_val, outdated_excerpt)
                evidence = [
                    f"Source code: {change.file_path}:{change.line_number}",
                    f"Diff: {change.diff_hunk}",
                    f"Documentation {section.file_path}:{line_no} says '{old_val}' and not '{new_val}'",
                ]

                if names_symbol:
                    verdict = Verdict.CONFIRMED_DRIFT
                    confidence = 0.98
                    explanation = f"'{sym_name}' changed from '{old_val}' to '{new_val}' in {change.file_path}, but this sentence still says '{old_val}'."
                    break

                # Same value but no mention of the symbol. It may be a coincidence, so keep looking.
                verdict = Verdict.POSSIBLE_DRIFT
                confidence = 0.55
                explanation = f"'{sym_name}' changed from '{old_val}' to '{new_val}', and this sentence mentions '{old_val}' without naming it. It may or may not describe this setting."

        # CLI flags
        elif change.change_type in {ChangeType.FLAG_RENAMED, ChangeType.FLAG_REMOVED}:
            old_flag = str(change.old_value)
            new_flag = change.new_value
            for offset, line_text in enumerate(doc_lines):
                if not contains_flag(old_flag, line_text):
                    continue
                line_no = section.start_line + offset
                found_start_line = found_end_line = line_no
                outdated_excerpt = line_text.strip()
                verdict = Verdict.CONFIRMED_DRIFT
                confidence = 0.97
                if new_flag:
                    explanation = f"Flag '{old_flag}' was renamed to '{new_flag}' in {change.file_path}:{change.line_number}, but this sentence still says '{old_flag}'."
                    suggested_fix = outdated_excerpt.replace(old_flag, str(new_flag))
                else:
                    explanation = f"Flag '{old_flag}' was removed in {change.file_path}, but this sentence still describes it."
                evidence = [f"Source code: {change.file_path}:{change.line_number}", f"Diff: {change.diff_hunk}"]
                break

        elif change.change_type == ChangeType.FLAG_DEFAULT_CHANGED:
            old_val = clean_value(change.old_value)
            new_val = clean_value(change.new_value)
            for offset, line_text in enumerate(doc_lines):
                if (
                    old_val
                    and contains_flag(change.symbol_name, line_text)
                    and contains_value(old_val, line_text)
                    and not contains_value(new_val, line_text)
                ):
                    line_no = section.start_line + offset
                    found_start_line = found_end_line = line_no
                    outdated_excerpt = line_text.strip()
                    verdict = Verdict.CONFIRMED_DRIFT
                    confidence = 0.97
                    explanation = f"The default of '{change.symbol_name}' changed from '{old_val}' to '{new_val}' in {change.file_path}, but this sentence still says '{old_val}'."
                    suggested_fix = re.sub(rf"(?<![\w.]){re.escape(old_val)}(?!\w|\.\d)", new_val, outdated_excerpt)
                    evidence = [f"Source code: {change.file_path}:{change.line_number}", f"Diff: {change.diff_hunk}"]
                    break

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
                    suggested_fix = ""  # Removing it takes a human rewrite, so we don't propose text.
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


class QwenProvider(BaseAIProvider):
    """Uses a small Qwen model, running locally through Ollama, for what rules can't decide.

    Rules handle exact matches. When a sentence has the old value but doesn't name the setting
    ("Requests give up after 30 seconds"), the model decides if it's about that setting or a coincidence.
    The model only answers yes or no, so it can't invent a sentence or a fix.
    """

    def __init__(self) -> None:
        self.heuristic = HeuristicAIProvider()

    def evaluate(self, pair: CandidatePair) -> Finding:
        finding = self.heuristic.evaluate(pair)
        if finding.verdict != Verdict.POSSIBLE_DRIFT:
            return finding

        # Several sentences in a section can hold the old value, and only some may be about this setting.
        old_value = clean_value(pair.change.old_value)
        sentences = [
            (pair.section.start_line + offset, line.strip())
            for offset, line in enumerate(pair.section.content.splitlines())
            if contains_value(old_value, line)
        ]

        for line_no, sentence in sentences[:MAX_SENTENCES_PER_SECTION]:
            answer = self._describes_setting(pair, sentence)
            if answer is None:  # The model failed, so this stays a "possible" for a person to judge.
                return finding
            finding.engine = model_name()
            if answer:
                new_value = clean_value(pair.change.new_value)
                finding.verdict = Verdict.CONFIRMED_DRIFT
                finding.confidence = 0.85
                finding.doc_start_line = finding.doc_end_line = line_no
                finding.outdated_excerpt = sentence
                finding.suggested_fix = re.sub(
                    rf"(?<![\w.]){re.escape(old_value)}(?!\w|\.\d)", new_value, sentence
                )
                finding.explanation = (
                    f"'{pair.change.symbol_name}' changed from '{old_value}' to '{new_value}'. "
                    f"{model_name()} confirmed this sentence is about that setting."
                )
                finding.evidence = [
                    f"Source code: {pair.change.file_path}:{pair.change.line_number}",
                    f"Diff: {pair.change.diff_hunk}",
                    f"{model_name()}: this sentence describes {pair.change.symbol_name}",
                ]
                return finding

        finding.verdict = Verdict.NO_DRIFT_DETECTED
        finding.outdated_excerpt = ""
        finding.suggested_fix = ""
        return finding

    def _describes_setting(self, pair: CandidatePair, sentence: str) -> bool | None:
        """Asks the model. Returns None if it couldn't answer."""
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            symbol_name=pair.change.symbol_name,
            file_path=pair.change.file_path,
            old_value=pair.change.old_value,
            new_value=pair.change.new_value,
            doc_title=pair.section.title,
            sentence=sentence,
        )
        try:
            resp = httpx.post(
                f"{ollama_url()}/api/chat",
                json={
                    "model": model_name(),
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "format": "json",
                    "stream": False,
                    "keep_alive": "1m",  # Gives the memory back soon after a scan.
                    "options": {"temperature": 0, "seed": 42},
                },
                timeout=MODEL_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            return json.loads(resp.json()["message"]["content"])["describes_setting"] is True
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            print(f"Qwen unavailable, keeping this as possible drift: {exc}", file=sys.stderr)
            return None


def ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def model_name() -> str:
    return os.getenv("DOCGUARD_MODEL", DEFAULT_MODEL)


def model_status() -> dict[str, object]:
    """Reports whether Ollama can be reached and has our model, and if not, why."""
    status: dict[str, object] = {
        "model": model_name(),
        "ollama_running": False,
        "model_ready": False,
        "model_problem": "",
    }
    try:
        resp = httpx.get(
            f"{ollama_url()}/api/tags",
            timeout=MODEL_CHECK_TIMEOUT_SECONDS,
            headers={"User-Agent": "DocGuard"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        status["ollama_running"] = True
        installed = {m.get("name") for m in resp.json().get("models", [])}
        status["model_ready"] = model_name() in installed
        if not status["model_ready"]:
            status["model_problem"] = f"Ollama is reachable, but doesn't have {model_name()}."
    except httpx.InvalidURL:
        status["model_problem"] = "OLLAMA_URL isn't a valid address."
    except httpx.UnsupportedProtocol:
        status["model_problem"] = "OLLAMA_URL must start with http:// or https://."
    except httpx.TimeoutException:
        status["model_problem"] = f"No answer from Ollama within {MODEL_CHECK_TIMEOUT_SECONDS:.0f} seconds."
    except httpx.HTTPStatusError as exc:
        status["model_problem"] = f"The Ollama address answered with HTTP {exc.response.status_code}. Check the link in OLLAMA_URL."
    except httpx.HTTPError as exc:
        status["model_problem"] = f"Couldn't connect to Ollama ({type(exc).__name__})."
    except ValueError:
        status["model_problem"] = "The address in OLLAMA_URL answered, but not like Ollama does."
    return status


def selected_provider_name() -> str:
    """The environment variable wins, then the dashboard setting."""
    if os.getenv("DOCGUARD_AI_PROVIDER"):
        return os.environ["DOCGUARD_AI_PROVIDER"].lower()

    from backend.app.database.db import get_settings_data, init_db

    init_db()  # The CLI runs on fresh machines, such as CI, where no database exists yet.
    return (get_settings_data().get("ai_provider") or "qwen").lower()


def get_ai_provider() -> BaseAIProvider:
    if selected_provider_name() == "qwen" and model_status()["model_ready"]:
        return QwenProvider()
    return HeuristicAIProvider()
