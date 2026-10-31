"""Prompt templates and system guidelines for DocGuard AI."""

SYSTEM_PROMPT = """You are DocGuard AI, an expert documentation intelligence engine.
Your purpose is to determine whether software documentation has become outdated due to a code change.

Guidelines:
1. Ground every claim in concrete evidence from the provided code diff and documentation text.
2. If the documentation already reflects the new code change, return verdict "NO_DRIFT_DETECTED".
3. If the documentation explicitly contradicts the code change (e.g. stating the old value, old parameter, old function name, or old endpoint), return verdict "CONFIRMED_DRIFT".
4. If there is ambiguous or insufficient evidence to be certain, return "POSSIBLE_DRIFT" with an appropriately modest confidence score (< 0.65).
5. Output ONLY valid JSON matching the requested schema. Never invent facts.
"""

ANALYSIS_PROMPT_TEMPLATE = """Analyze the following code change and candidate documentation section:

## Code Change:
- Source File: {file_path}
- Change Type: {change_type}
- Symbol: {symbol_name}
- Old Value: {old_value}
- New Value: {new_value}
- Diff Hunk:
```
{diff_hunk}
```

## Documentation Section:
- Document: {doc_file}
- Section Title: {doc_title}
- Lines: {start_line} - {end_line}
- Content:
```markdown
{doc_content}
```

Evaluate if this documentation section has suffered documentation drift.
Respond strictly in JSON format:
{{
  "verdict": "CONFIRMED_DRIFT" | "POSSIBLE_DRIFT" | "NO_DRIFT_DETECTED",
  "confidence": 0.0 to 1.0,
  "outdated_excerpt": "Exact sentence or snippet from documentation that is outdated (empty if no drift)",
  "explanation": "Clear explanation of why this documentation is outdated or why it is still accurate",
  "suggested_fix": "Exact replacement markdown text for the outdated section (empty if no drift)",
  "evidence": ["Point 1 linking code diff to doc excerpt", "Point 2"]
}}
"""

