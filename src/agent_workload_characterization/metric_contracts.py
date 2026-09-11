"""Pure contract examples, not an adapter or a workload analysis pipeline."""

from .ir import Interval, Template


def template_lengths(template: Template) -> dict:
    """Expand declared lengths, never tokenizer measurements or execution times.

    Unknown inputs propagate to affected outputs; final output does not grow a
    nonexistent next context. Unit semantics stay those declared by the source.
    """
    contexts = [template.initial_input]
    for output, tool in zip(template.assistant_outputs, template.tool_outputs, strict=True):
        previous = contexts[-1]
        contexts.append(None if None in (previous, output, tool) else previous + output + tool)
    outputs = [*template.assistant_outputs, template.final_output]
    return {
        "evidence": "template_parameter",
        "unit": template.unit,
        "model_request_count": template.tool_use_turns + 1,
        "context_inputs": contexts,
        "total_input": None if None in contexts else sum(contexts),
        "max_context": None if None in contexts else max(contexts),
        "total_output": None if None in outputs else sum(outputs),
    }


def interval_totals(intervals: list[Interval]) -> dict[str, int | None]:
    """Closed same-clock work/union only; no inferred run E2E or Agent overhead.

    Empty input is unavailable, not an observed zero. Unknown boundaries or
    cross-clock intervals require caller-side coverage/alignment handling.
    """
    if not intervals:
        return {"work_ns": None, "busy_ns": None, "overlap_ns": None, "observed_span_ns": None}
    if len({item.clock_id for item in intervals}) != 1:
        raise ValueError("cross-clock subtraction is unsupported")
    if any(item.start_ns is None or item.end_ns is None for item in intervals):
        raise ValueError("open intervals need explicit coverage handling")
    if any(item.source != "native_event" for item in intervals):
        raise ValueError("receipt/estimated intervals are not native work boundaries")
    pairs = sorted((item.start_ns, item.end_ns) for item in intervals)
    work = sum(end - start for start, end in pairs)
    left, right = pairs[0]
    busy = 0
    for start, end in pairs[1:]:
        if start > right:
            busy += right - left
            left, right = start, end
        else:
            right = max(right, end)
    busy += right - left
    return {"work_ns": work, "busy_ns": busy, "overlap_ns": work - busy, "observed_span_ns": max(end for _, end in pairs) - pairs[0][0]}
