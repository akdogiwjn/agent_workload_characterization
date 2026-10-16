# v1→v2 修正记录

```json
{
  "v1_errors": [
    "v1 counted only same-category transitions and omitted cross-category transitions",
    "v1 named accumulated run action totals contiguous_known_run_counts rather than segment counts",
    "v1 treated every AST Call found by ast.walk as ordered action evidence, including unsupported structures",
    "v1 classified unknown calls as other and did not retain actual score/reward values"
  ],
  "v2_changes": {
    "status_counts": {
      "valid": 21,
      "partial": 87
    },
    "source_call_syntax_count_total": 3241101,
    "supported_action_count_total": 3241101,
    "pooled_category_counts": {
      "click": 9236,
      "pointer": 636,
      "scroll": 1867,
      "text_or_key": 3225612,
      "wait": 3750
    },
    "pooled_transition_counts": {
      "click->click": 5522,
      "click->pointer": 145,
      "click->scroll": 458,
      "click->text_or_key": 2823,
      "click->wait": 265,
      "pointer->click": 118,
      "pointer->pointer": 415,
      "pointer->scroll": 17,
      "pointer->text_or_key": 75,
      "pointer->wait": 11,
      "scroll->click": 522,
      "scroll->pointer": 16,
      "scroll->scroll": 1032,
      "scroll->text_or_key": 268,
      "scroll->wait": 22,
      "text_or_key->click": 2613,
      "text_or_key->pointer": 40,
      "text_or_key->scroll": 314,
      "text_or_key->text_or_key": 3221060,
      "text_or_key->wait": 1503,
      "wait->click": 441,
      "wait->pointer": 20,
      "wait->scroll": 46,
      "wait->text_or_key": 1379,
      "wait->wait": 1850
    }
  },
  "withdrawn_observations": [
    "v1 valid/partial counts and pooled static counts are not retained as complete-action coverage",
    "v1 other/sequence claims for unsupported or unknown calls are withdrawn"
  ],
  "still_supported": [
    "the fixed MiniMax-M3 local scope and input hashes",
    "descriptive static composition within the explicitly supported grammar",
    "separate done/reward/result evidence without a derived success label"
  ],
  "limits": [
    "actual GUI execution count, timing, resources, and semantic success remain unknown",
    "numeric result values are preserved without assigning task-success meaning"
  ]
}
```
