You are a focused subagent reviewer for a single holistic investigation batch.

Repository root: /Users/max/Desktop/Tools/MultiVolatility
Blind packet: /Users/max/Desktop/Tools/MultiVolatility/.desloppify/review_packet_blind.json
Batch index: 13
Batch name: design_coherence
Batch rationale: seed files for design_coherence review

DIMENSION TO EVALUATE:

## design_coherence
Are structural design decisions sound — functions focused, abstractions earned, patterns consistent?
Look for:
- Functions doing too many things — multiple distinct responsibilities in one body
- Parameter lists that should be config/context objects — many related params passed together
- Files accumulating issues across many dimensions — likely mixing unrelated concerns
- Deep nesting that could be flattened with early returns or extraction
- Repeated structural patterns that should be data-driven
Skip:
- Functions that are long but have a single coherent responsibility
- Parameter lists where grouping would obscure meaning — do NOT recommend config/context objects or dependency injection wrappers just to reduce parameter count; only group when the grouping has independent semantic meaning
- Files that are large because their domain is genuinely complex, not because they mix concerns
- Nesting that is inherent to the problem (e.g., recursive tree processing)
- Do NOT recommend extracting callable parameters or injecting dependencies for 'testability' — direct function calls are simpler and preferred unless there is a concrete decoupling need

YOUR TASK: Read the code for this batch's dimension. Judge how well the codebase serves a developer from that perspective. The dimension rubric above defines what good looks like. Cite specific observations that explain your judgment.

Mechanical scan evidence — navigation aid, not scoring evidence:
The blind packet contains `holistic_context.scan_evidence` with aggregated signals from all mechanical detectors — including complexity hotspots, error hotspots, signal density index, boundary violations, and systemic patterns. Use these as starting points for where to look beyond the seed files.

Seed files (start here):
- Dockerfiles/memprocfs/memprocfs_server.py
- CLI/multivol/api_server/routes/dump.py
- CLI/multivol/api_server/routes/memprocfs.py
- CLI/multivol/api_server/routes/scan.py
- CLI/multivol/multivol.py
- CLI/multivol/multi_volatility3.py
- CLI/multivol/api_server/routes/files.py
- CLI/multivol/api_server/utils.py
- CLI/multivol/multi_volatility2.py
- CLI/multivol/api_server/routes/docker.py
- CLI/multivol/api_server/database.py
- CLI/multivol/api_server/routes/auth.py
- CLI/multivol/api_server/app.py
- CLI/multivol/api_server/auth.py
- CLI/multivol/api_strings_extension.py
- MCP/multivol_mcp.py

Mechanical concern signals — navigation aid, not scoring evidence:
Confirm or refute each with your own code reading. Report only confirmed defects.
  - [design_concern] CLI/multivol/api_server/app.py
    summary: Design signals from smells
    question: Review the flagged patterns — are they design problems that need addressing, or acceptable given the file's role?
    evidence: Flagged by: smells
    evidence: [smells] 1x Catch block that only logs (swallowed error)
  - [design_concern] CLI/multivol/api_server/auth.py
    summary: Design signals from orphaned, smells
    question: Is this file truly dead, or is it used via a non-import mechanism (dynamic import, CLI entry point, plugin)?
    evidence: Flagged by: orphaned, smells
    evidence: [orphaned] Orphaned file (28 LOC): zero importers, not an entry point
  - [design_concern] CLI/multivol/api_server/database.py
    summary: Design signals from orphaned, smells
    question: Is this file truly dead, or is it used via a non-import mechanism (dynamic import, CLI entry point, plugin)?
    evidence: Flagged by: orphaned, smells
    evidence: [orphaned] Orphaned file (110 LOC): zero importers, not an entry point
  - [design_concern] CLI/multivol/api_server/routes/auth.py
    summary: Design signals from orphaned, smells
    question: Is this file truly dead, or is it used via a non-import mechanism (dynamic import, CLI entry point, plugin)?
    evidence: Flagged by: orphaned, smells
    evidence: [orphaned] Orphaned file (23 LOC): zero importers, not an entry point
  - [design_concern] CLI/multivol/api_strings_extension.py
    summary: Design signals from orphaned, smells
    question: Is this file truly dead, or is it used via a non-import mechanism (dynamic import, CLI entry point, plugin)?
    evidence: Flagged by: orphaned, smells
    evidence: [orphaned] Orphaned file (87 LOC): zero importers, not an entry point
  - [design_concern] MCP/multivol_mcp.py
    summary: Design signals from orphaned, smells
    question: Is this file truly dead, or is it used via a non-import mechanism (dynamic import, CLI entry point, plugin)?
    evidence: Flagged by: orphaned, smells
    evidence: [orphaned] Orphaned file (342 LOC): zero importers, not an entry point
  - [interface_design] CLI/multivol/multi_volatility3.py
    summary: Interface complexity: 17 parameters
    question: Should the parameters be grouped into a config/context object? Which ones belong together? Can the nesting be reduced with early returns, guard clauses, or extraction into helper functions?
    evidence: Flagged by: smells, structural
    evidence: File size: 222 lines
  - [mixed_responsibilities] CLI/multivol/api_server/routes/docker.py
    summary: Issues from 3 detectors — may have too many responsibilities
    question: This file has issues across 3 dimensions (orphaned, smells, structural). Is it trying to do too many things, or is this complexity inherent to its domain? Can the nesting be reduced with early returns, guard clauses, or extraction into helper functions? Is this file truly dead, or is it used via a non-import mechanism (dynamic import, CLI entry point, plugin)?
    evidence: Flagged by: orphaned, smells, structural
    evidence: File size: 111 lines
  - (+4 more concern signals)

Task requirements:
1. Read the blind packet's `system_prompt` — it contains scoring rules and calibration.
2. Start from the seed files, then freely explore the repository to build your understanding.
3. Keep issues and scoring scoped to this batch's dimension.
4. Respect scope controls: do not include files/directories marked by `exclude`, `suppress`, or non-production zone overrides.
5. Return 0-10 issues for this batch (empty array allowed).
6. For design_coherence, use evidence from `holistic_context.scan_evidence.signal_density` — files where multiple mechanical detectors fired. Investigate what design change would address multiple signals simultaneously. Check `scan_evidence.complexity_hotspots` for files with high responsibility cluster counts.
7. Workflow integrity checks: when reviewing orchestration/queue/review flows,
8. xplicitly look for loop-prone patterns and blind spots:
9. - repeated stale/reopen churn without clear exit criteria or gating,
10. - packet/batch data being generated but dropped before prompt execution,
11. - ranking/triage logic that can starve target-improving work,
12. - reruns happening before existing open review work is drained.
13. If found, propose concrete guardrails and where to implement them.
14. Complete `dimension_judgment` for your dimension — all three fields (strengths, issue_character, score_rationale) are required. Write the judgment BEFORE setting the score.
15. Do not edit repository files.
16. Return ONLY valid JSON, no markdown fences.

Scope enums:
- impact_scope: "local" | "module" | "subsystem" | "codebase"
- fix_scope: "single_edit" | "multi_file_refactor" | "architectural_change"

Output schema:
{
  "batch": "design_coherence",
  "batch_index": 13,
  "assessments": {"<dimension>": <0-100 with one decimal place>},
  "dimension_notes": {
    "<dimension>": {
      "evidence": ["specific code observations"],
      "impact_scope": "local|module|subsystem|codebase",
      "fix_scope": "single_edit|multi_file_refactor|architectural_change",
      "confidence": "high|medium|low",
      "issues_preventing_higher_score": "required when score >85.0",
      "sub_axes": {"abstraction_leverage": 0-100, "indirection_cost": 0-100, "interface_honesty": 0-100, "delegation_density": 0-100, "definition_directness": 0-100, "type_discipline": 0-100}  // required for abstraction_fitness when evidence supports it; all one decimal place
    }
  },
  "dimension_judgment": {
    "<dimension>": {
      "strengths": ["0-5 specific things the codebase does well from this dimension's perspective"],
      "issue_character": "one sentence characterizing the nature/pattern of issues from this dimension's perspective",
      "score_rationale": "2-3 sentences explaining the score from this dimension's perspective, referencing global anchors"
    }  // required for every assessed dimension; do not omit
  },
  "issues": [{
    "dimension": "<dimension>",
    "identifier": "short_id",
    "summary": "one-line defect summary",
    "related_files": ["relative/path.py"],
    "evidence": ["specific code observation"],
    "suggestion": "concrete fix recommendation",
    "confidence": "high|medium|low",
    "impact_scope": "local|module|subsystem|codebase",
    "fix_scope": "single_edit|multi_file_refactor|architectural_change",
    "root_cause_cluster": "optional_cluster_name_when_supported_by_history"
  }],
  "retrospective": {
    "root_causes": ["optional: concise root-cause hypotheses"],
    "likely_symptoms": ["optional: identifiers that look symptom-level"],
    "possible_false_positives": ["optional: prior concept keys likely mis-scoped"]
  }
}
