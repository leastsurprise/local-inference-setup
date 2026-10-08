# llama-perf

A [pi coding agent](https://github.com/earendil-works/pi) extension that shows live llama.cpp speed under the editor: context used, prefill and decode t/s with sparklines, and MTP draft acceptance.

```
llama │ ctx 51.2k/262k 20% │ prefill 193 t/s ▃▄▅▆ │ decode 19.9 t/s ▇▆▅▄ │ MTP 82% │ ctrl+x graph
```

- **ctrl+x** (or `/perf`) cycles: compact → decode vs context → prefill vs context → MTP acceptance vs context → compact. `/perf off` and `/perf on` hide and show it.
- **The numbers are llama-server's own.** The extension adds `return_progress` and `timings_per_token` to each `/chat/completions` request, then reads the server's timings from a copy of the response stream (`prompt_n`, `predicted_n`, `cache_n`, `draft_n`, `draft_n_accepted`).
- **It only touches models whose provider is `llamacpp`**, and does nothing in runs without a UI.
- Samples are saved per session in `~/.pi/agent/llama-perf/`, so a resumed session keeps its history.

This is how I watched decode hold up (or not) as context grew, which is what the [posts](../../posts/) measure.

## Install

```sh
cp llama-perf.js ~/.pi/agent/extensions/
```

Restart pi. Standard library only (`node:fs`, `node:os`, `node:path`).
