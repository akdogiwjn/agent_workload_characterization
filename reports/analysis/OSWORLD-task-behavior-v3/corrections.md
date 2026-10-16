# v2→v3 修正记录

{
  "v2_to_v3": {
    "group1": {
      "old_formula": "input_tokens + output_tokens + cache_read_input_tokens + cache_creation_input_tokens",
      "new_formula": "input_tokens + cache_read_input_tokens + cache_creation_input_tokens",
      "request_level_derived_stats": {
        "n": 35272,
        "missing": 0,
        "min": 4002.0,
        "q1": 68885.25,
        "median": 90676.5,
        "q3": 116143.75,
        "iqr": 47258.5,
        "max": 283471.0
      },
      "task_level_derived_stats": {
        "n": 108,
        "missing": 0,
        "min": 750685.0,
        "q1": 18329848.25,
        "median": 28366961.0,
        "q3": 44480432.5,
        "iqr": 26150584.25,
        "max": 66992883.0
      },
      "old_v2_request_level_derived_stats": {
        "n": 35272,
        "missing": 0,
        "min": 4049.0,
        "q1": 69099.75,
        "median": 90878.5,
        "q3": 116399.25,
        "iqr": 47299.5,
        "max": 285162.0
      },
      "comparison_field": "numeric_totals.input_tokens_including_cache"
    },
    "group2": {
      "old": "native unknown was a literal category in sequence tokens",
      "fixed": "unknown native records are retained in counts but become None boundaries; invalid JSON breaks both sequences",
      "native_unknown_action_count": 51093,
      "old_v2_unknown_transition_total": 50873,
      "new_v3_unknown_transition_total": 0
    },
    "group3": {
      "old": "not_applicable native representations and usage missingness could appear as zero",
      "fixed": "native denominators and usage source/call/field missingness are separate; valid distributions exclude not_applicable",
      "native_denominators": {
        "MiniMax-M3": {
          "total_records": 108,
          "not_applicable": 108
        },
        "claude-opus-4-7": {
          "total_records": 108,
          "applicable": 108
        },
        "claude-sonnet-4-6-max": {
          "total_records": 108,
          "applicable": 108
        },
        "claude-sonnet-4-6-medium": {
          "total_records": 108,
          "applicable": 108
        },
        "gpt-5.5": {
          "total_records": 108,
          "applicable": 108
        },
        "gpt-5.6": {
          "total_records": 107,
          "applicable": 107
        },
        "qwen3.7": {
          "total_records": 108,
          "not_applicable": 108
        }
      },
      "usage_missingness": {
        "source_missing_usage_count": 10,
        "calls_usage_missing": 0,
        "usage_field_missing": {}
      }
    },
    "group4": {
      "old": "constant task revision and partial actual-file check were insufficient evidence",
      "fixed": "local HF tree cache evidence is consumed and registered; actual and registered inventory sets plus hashes are checked",
      "task_version_evidence": {
        "status": "local_cache_evidence",
        "path": "data/raw/public/osworld2_tasks/v2026.06.24/.cache/huggingface/trees/e7996f4cc850be108e510bd8433c63ee7b8303dd.json",
        "expected_revision": "e7996f4cc850be108e510bd8433c63ee7b8303dd",
        "sha256": "9c76453f6bb27d69367e6e2b5a20987ca3927b17ed106a924692bb5e40beca29",
        "historical_execution_binding": "unknown"
      },
      "analysis_code": [
        "scripts/osworld_task_behavior.py",
        "scripts/osworld_minimax_behavior.py"
      ]
    }
  },
  "unchanged": [
    "task semantics extraction remains static and non-executing",
    "task labels remain overlapping source-based labels",
    "static/native saved records are not proof of actual GUI execution",
    "no resource, duration, billing or model-ranking claims"
  ],
  "remaining_unknown": [
    "historical runtime task-version binding",
    "upstream authentication beyond local cache/inventory evidence",
    "actual execution count and timing"
  ]
}
