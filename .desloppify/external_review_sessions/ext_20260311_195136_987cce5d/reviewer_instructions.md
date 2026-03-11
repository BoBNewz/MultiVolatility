# External Blind Review Session

Session id: ext_20260311_195136_987cce5d
Session token: f701da3ea5fe20a74bdb45ce84eac62e
Blind packet: /Users/max/Desktop/Tools/MultiVolatility/.desloppify/review_packet_blind.json
Template output: /Users/max/Desktop/Tools/MultiVolatility/.desloppify/external_review_sessions/ext_20260311_195136_987cce5d/review_result.template.json
Claude launch prompt: /Users/max/Desktop/Tools/MultiVolatility/.desloppify/external_review_sessions/ext_20260311_195136_987cce5d/claude_launch_prompt.md
Expected reviewer output: /Users/max/Desktop/Tools/MultiVolatility/.desloppify/external_review_sessions/ext_20260311_195136_987cce5d/review_result.json

Happy path:
1. Open the Claude launch prompt file and paste it into a context-isolated subagent task.
2. Reviewer writes JSON output to the expected reviewer output path.
3. Submit with the printed --external-submit command.

Reviewer output requirements:
1. Return JSON with top-level keys: session, assessments, issues.
2. session.id must be `ext_20260311_195136_987cce5d`.
3. session.token must be `f701da3ea5fe20a74bdb45ce84eac62e`.
4. Include issues with required schema fields (dimension/identifier/summary/related_files/evidence/suggestion/confidence).
5. Use the blind packet only (no score targets or prior context).
