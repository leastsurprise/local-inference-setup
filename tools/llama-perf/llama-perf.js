/**
 * llama-perf: live llama.cpp inference stats under the pi editor.
 *
 * Compact (default, one line):
 *   llama │ ctx 51.2k/262k 20% │ prefill 193 t/s ▃▄▅▆ │ decode 19.9 t/s ▇▆▅▄ │ MTP 82% │ ctrl+x graph
 * Expanded: one of decode, prefill or MTP acceptance plotted against context
 * size for this session, so you can see how it holds up as the context grows.
 * ctrl+x (or /perf) steps compact -> decode -> prefill -> MTP -> compact
 * (MTP only when the server drafts).   /perf off | on   hide/show
 *
 * Numbers are llama-server's own, not client-side guesses. Each request to
 * /chat/completions gets return_progress + timings_per_token added (llama.cpp
 * only, provider "llamacpp"); the response stream is tee'd and the copy parsed
 * for prompt_progress (live prefill) and timings (prompt_n/ms, predicted_n/ms,
 * cache_n, draft_n, draft_n_accepted). pi skips those extra chunk fields.
 * "Recent" = token-weighted over the last RECENT requests. Prefill ignores
 * requests with < MIN_PREFILL new tokens (fixed overhead swamps the rate).
 *
 * Samples persist per session in ~/.pi/agent/llama-perf/<session file name>,
 * so a resumed session keeps its history. Inert without a UI (e.g. pi
 * --mode json runs): no payload change, no fetch hook, no files.
 *
 * Install: copy to ~/.pi/agent/extensions/llama-perf.js; pi loads it on the
 * next launch.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const PROVIDERS = ["llamacpp"];
const KEY = "ctrl+x";
const RECENT = 5;
const SPARK = 8;
const MIN_PREFILL = 32;
const MIN_DECODE = 16;
const ROWS = 8; // chart height in expanded mode (8 levels per row)
const STORE = path.join(os.homedir(), ".pi", "agent", "llama-perf");
const BARS = " ▁▂▃▄▅▆▇█";

// One fetch hook per process, however many times pi reloads the extension
// (session switch, /reload). Each instance just swaps the listener.
const HOOK = Symbol.for("llama-perf.fetch");
function hookFetch() {
	if (globalThis[HOOK]) return globalThis[HOOK];
	const orig = globalThis.fetch;
	const hook = { listener: null };
	globalThis[HOOK] = hook;
	globalThis.fetch = async function (input, init) {
		const res = await orig.call(this, input, init);
		const listener = hook.listener;
		if (!listener || !res.ok || !res.body) return res;
		const url = typeof input === "string" ? input : input instanceof URL ? input.href : input?.url;
		if (!url || !/\/chat\/completions(\?|$)/.test(url)) return res;
		if (!(res.headers.get("content-type") || "").includes("text/event-stream")) return res;
		const [mine, theirs] = res.body.tee();
		listener(mine);
		const out = new Response(theirs, { status: res.status, statusText: res.statusText, headers: res.headers });
		Object.defineProperty(out, "url", { value: res.url });
		return out;
	};
	return hook;
}

// ---- formatting ---------------------------------------------------------------
const k = (n) => (n >= 100000 ? `${Math.round(n / 1000)}k` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${Math.round(n)}`);
const rate = (r) => (r == null ? "–" : r >= 100 ? `${Math.round(r)}` : r.toFixed(1));
const pct = (r) => (r == null ? "–" : `${Math.round(r * 100)}%`);
const dur = (ms) => {
	const m = Math.round(ms / 60000);
	return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}m`;
};
// Y range from the data, not from 0, so a 25 -> 15 t/s slide fills the
// height instead of trimming the top eighth. The labels carry the numbers.
const range = (vals, cap) => {
	const xs = vals.filter((v) => v != null);
	if (!xs.length) return { lo: 0, hi: 1 };
	const min = Math.min(...xs);
	const max = Math.max(...xs);
	const pad = (max - min) * 0.15 || max * 0.1 || 1;
	return { lo: Math.max(0, min - pad), hi: cap ? Math.min(cap, max + pad / 3) : max + pad / 3 };
};
const level = (v, { lo, hi }, steps) => Math.max(1, Math.min(steps, Math.round(((v - lo) / (hi - lo)) * steps)));
const spark = (vals) => {
	const r = range(vals);
	return vals.map((v) => (v == null ? " " : BARS[level(v, r, 8)])).join("");
};
const tick = (n) => `${Math.round(n / 1000)}k`;

// Segments are [text, color?]; widths are counted on the plain text so a line
// never exceeds the terminal (pi-tui rejects over-wide lines).
function fit(segs, width, theme) {
	let out = "";
	let left = width;
	for (const [text, color] of segs) {
		if (left <= 0) break;
		const t = text.length > left ? text.slice(0, left) : text;
		left -= t.length;
		out += color ? theme.fg(color, t) : t;
	}
	return out;
}

// ---- stats --------------------------------------------------------------------
const ctxOf = (s) => s.cache + s.pn; // context when decoding starts
const prefillRate = (ss) => {
	const xs = ss.filter((s) => s.pn >= MIN_PREFILL);
	const ms = xs.reduce((a, s) => a + s.pms, 0);
	return ms > 0 ? (xs.reduce((a, s) => a + s.pn, 0) / ms) * 1000 : null;
};
const decodeRate = (ss) => {
	const xs = ss.filter((s) => s.dn >= MIN_DECODE);
	const ms = xs.reduce((a, s) => a + s.dms, 0);
	return ms > 0 ? (xs.reduce((a, s) => a + s.dn, 0) / ms) * 1000 : null;
};
const acceptRate = (ss) => {
	const dr = ss.reduce((a, s) => a + (s.dr || 0), 0);
	return dr > 0 ? ss.reduce((a, s) => a + (s.da || 0), 0) / dr : null;
};
const lastN = (ss, ok, n) => ss.filter(ok).slice(-n);

/** @param {import("@earendil-works/pi-coding-agent").ExtensionAPI} pi */
export default function (pi) {
	let samples = [];
	let live = null; // { phase: "prefill"|"decode", ctx, progress, rate, accept }
	let mode = "compact"; // compact | expanded | off
	let view = 0; // index into views() while expanded
	let nctx = 0;
	let file = null;
	let tui = null;
	let hook = null;
	let lastPaint = 0;
	let paintTimer = null;

	// Per-token updates arrive ~20/s; repaint at most 4/s.
	const paint = (force) => {
		if (!tui) return;
		const now = Date.now();
		if (force || now - lastPaint > 250) {
			lastPaint = now;
			tui.requestRender();
		} else if (!paintTimer) {
			paintTimer = setTimeout(() => {
				paintTimer = null;
				lastPaint = Date.now();
				tui?.requestRender();
			}, 250);
		}
	};

	const record = (t) => {
		const s = {
			t: Date.now(),
			cache: t.cache_n || 0,
			pn: t.prompt_n || 0,
			pms: t.prompt_ms || 0,
			dn: t.predicted_n || 0,
			dms: t.predicted_ms || 0,
			dr: t.draft_n || 0,
			da: t.draft_n_accepted || 0,
		};
		if (s.pn <= 0 && s.dn <= 0) return;
		samples.push(s);
		if (!file) return;
		try {
			fs.mkdirSync(STORE, { recursive: true });
			fs.appendFileSync(file, JSON.stringify(s) + "\n");
		} catch {}
	};

	// Reads the tee'd copy of one streamed response.
	const consume = async (stream) => {
		let timings = null;
		live = { phase: "prefill", ctx: null, progress: 0, rate: null, accept: null };
		paint(true);
		try {
			const reader = stream.pipeThrough(new TextDecoderStream()).getReader();
			let buf = "";
			for (;;) {
				const { value, done } = await reader.read();
				if (done) break;
				buf += value;
				let nl;
				while ((nl = buf.indexOf("\n")) >= 0) {
					const line = buf.slice(0, nl).trim();
					buf = buf.slice(nl + 1);
					if (!line.startsWith("data:")) continue;
					if (!line.includes('"timings"') && !line.includes('"prompt_progress"')) continue;
					let j;
					try {
						j = JSON.parse(line.slice(5));
					} catch {
						continue;
					}
					const p = j.prompt_progress;
					if (p && p.total) {
						const fresh = (p.processed || 0) - (p.cache || 0);
						live = {
							phase: "prefill",
							ctx: p.processed,
							progress: p.total > p.cache ? fresh / (p.total - p.cache) : 1,
							rate: p.time_ms > 0 && fresh > 0 ? (fresh / p.time_ms) * 1000 : null,
							accept: null,
						};
						paint();
					}
					const t = j.timings;
					if (t) {
						timings = t;
						if ((t.predicted_n || 0) > 0) {
							live = {
								phase: "decode",
								ctx: (t.cache_n || 0) + (t.prompt_n || 0) + t.predicted_n,
								progress: 1,
								rate: t.predicted_per_second || null,
								accept: t.draft_n > 0 ? t.draft_n_accepted / t.draft_n : null,
							};
							paint();
						}
					}
				}
			}
		} catch {
			// aborted or connection dropped: keep whatever timings arrived
		}
		if (timings) record(timings);
		live = null;
		paint(true);
	};

	// ---- rendering --------------------------------------------------------------
	const compact = (width, th) => {
		const last = samples[samples.length - 1];
		const cur = live?.ctx ?? (last ? ctxOf(last) + last.dn : null);
		const segs = [["llama", "accent"], [" │ ", "dim"]];
		if (cur == null && !live) {
			segs.push(["waiting for the first llama.cpp request", "dim"]);
			return [fit(segs, width, th)];
		}
		segs.push(["ctx ", "muted"], [`${k(cur ?? 0)}${nctx ? `/${k(nctx)} ${Math.round(((cur ?? 0) / nctx) * 100)}%` : ""}`]);
		const pre = lastN(samples, (s) => s.pn >= MIN_PREFILL, SPARK);
		const dec = lastN(samples, (s) => s.dn >= MIN_DECODE, SPARK);
		const preR = pre.map((s) => (s.pn / s.pms) * 1000);
		const decR = dec.map((s) => (s.dn / s.dms) * 1000);
		const wide = width >= 96;

		segs.push([" │ ", "dim"], ["prefill ", "muted"]);
		if (live?.phase === "prefill") segs.push([`▶ ${Math.round(live.progress * 100)}% ${rate(live.rate)} t/s`, "warning"]);
		else segs.push([`${rate(prefillRate(pre.slice(-RECENT)))} t/s`]);
		if (wide && preR.length) segs.push([" " + spark(preR), "accent"]);

		segs.push([" │ ", "dim"], ["decode ", "muted"]);
		if (live?.phase === "decode") segs.push([`▶ ${rate(live.rate)} t/s`, "warning"]);
		else segs.push([`${rate(decodeRate(dec.slice(-RECENT)))} t/s`]);
		if (wide && decR.length) segs.push([" " + spark(decR), "accent"]);

		const acc = live?.phase === "decode" && live.accept != null ? live.accept : acceptRate(samples.slice(-RECENT));
		if (acc != null) segs.push([" │ ", "dim"], ["MTP ", "muted"], [pct(acc)]);
		segs.push([" │ ", "dim"], [`${KEY} graph`, "dim"]);
		return [fit(segs, width, th)];
	};

	// One metric as a bar chart over context buckets. Buckets with no requests
	// repeat the last value in dim, so a sparse session still reads as a line.
	const chart = (name, sub, isPct, agg, plotW, xmax, LW) => {
		const cols = [];
		for (let c = 0; c < plotW; c++) {
			const lo = (c * xmax) / plotW;
			const hi = ((c + 1) * xmax) / plotW;
			cols.push(agg(samples.filter((s) => ctxOf(s) >= lo && ctxOf(s) < hi)));
		}
		let carry = null;
		const cells = cols.map((v) => {
			if (v != null) return (carry = v), { v, real: true };
			return carry == null ? null : { v: carry, real: false };
		});
		const yr = range(cols, isPct ? 1 : 0);
		const fmt = isPct ? pct : rate;
		// top row: name + scale top; bottom row: unit + scale bottom
		const edge = (a, b) => a.slice(0, LW - 2 - b.length).padEnd(LW - 2 - b.length) + b + " ";
		const labels = [edge(name, fmt(yr.hi)), edge(sub, fmt(yr.lo))];
		const lines = [];
		for (let r = 0; r < ROWS; r++) {
			const fromBottom = ROWS - 1 - r;
			const mid = Math.floor((ROWS - 1) / 2);
			const label = r === 0 ? labels[0] : r === ROWS - 1 ? labels[1]
				: r === mid ? edge("", fmt(yr.lo + ((yr.hi - yr.lo) * (fromBottom + 0.5)) / ROWS)) : " ".repeat(LW - 1);
			const segs = [[label, r === 0 ? "accent" : "muted"], ["│", "dim"]];
			let run = "";
			let runColor = null;
			for (const cell of cells) {
				let ch = " ";
				let color = null;
				if (cell) {
					const lv = level(cell.v, yr, ROWS * 8);
					ch = BARS[Math.max(0, Math.min(8, lv - fromBottom * 8))];
					color = cell.real ? "accent" : "dim";
				}
				if (color !== runColor && run) segs.push([run, runColor]), (run = "");
				runColor = color;
				run += ch;
			}
			if (run) segs.push([run, runColor]);
			lines.push(segs);
		}
		return lines;
	};

	const views = () => [
		{ name: "decode", sub: "t/s", isPct: false, agg: decodeRate },
		{ name: "prefill", sub: "t/s", isPct: false, agg: prefillRate },
		...(samples.some((s) => s.dr > 0) ? [{ name: "MTP", sub: "accept", isPct: true, agg: acceptRate }] : []),
	];

	const expanded = (width, th) => {
		const LW = 15;
		const plotW = Math.max(10, width - LW);
		const xmax = Math.ceil(Math.max(20000, ...samples.map(ctxOf)) / 20000) * 20000; // quarters land on 5k
		const span = samples.length ? dur(Date.now() - samples[0].t) : "0m";
		const vs = views();
		const v = vs[Math.min(view, vs.length - 1)];
		// tab strip: the shown metric highlighted, the others dim
		const head = [["─ ", "dim"]];
		vs.forEach((x, i) => head.push([i ? " · " : "", "dim"], [x === v ? `[${x.name}]` : x.name, x === v ? "accent" : "dim"]));
		head.push([` vs context · ${samples.length} requests · ${span} `, "muted"]);
		const tail = ` ${KEY} ${view >= vs.length - 1 ? "compact" : "next"} ─`;
		const used = head.reduce((a, [t]) => a + t.length, 0) + tail.length;
		const out = [fit([...head, ["─".repeat(Math.max(0, width - used)), "dim"], [tail, "dim"]], width, th)];
		out.push(compact(width, th)[0]);
		if (!samples.length) return out;
		for (const segs of chart(v.name, v.sub, v.isPct, v.agg, plotW, xmax, LW)) out.push(fit(segs, width, th));
		// x axis: ticks at quarters of xmax
		const axis = Array(plotW).fill("─");
		const labels = Array(plotW).fill(" ");
		for (let q = 0; q <= 4; q++) {
			const col = Math.min(plotW - 1, Math.round((q * (plotW - 1)) / 4));
			axis[col] = "┬";
			const text = q === 0 ? "0" : tick((q * xmax) / 4);
			const at = Math.max(0, Math.min(plotW - text.length, col - (q === 4 ? text.length - 1 : 0)));
			for (let i = 0; i < text.length; i++) labels[at + i] = text[i];
		}
		out.push(fit([[" ".repeat(LW - 1) + "└", "dim"], [axis.join(""), "dim"]], width, th));
		out.push(fit([["context tokens".padEnd(LW), "muted"], [labels.join(""), "muted"]], width, th));
		return out;
	};

	const show = (ctx) => {
		if (!ctx.hasUI) return;
		if (mode === "off") {
			ctx.ui.setWidget("llama-perf", undefined);
			tui = null;
			return;
		}
		ctx.ui.setWidget(
			"llama-perf",
			(t, theme) => {
				tui = t;
				return {
					render: (width) => (mode === "expanded" ? expanded(width, theme) : compact(width, theme)),
					invalidate: () => {},
				};
			},
			{ placement: "belowEditor" },
		);
	};

	const toggle = (ctx, arg) => {
		if (arg === "off" || arg === "on") mode = arg === "off" ? "off" : "compact";
		else if (mode !== "expanded") (mode = "expanded"), (view = 0);
		else if (view + 1 < views().length) view++;
		else mode = "compact";
		show(ctx);
	};

	pi.on("session_start", async (_event, ctx) => {
		if (!ctx.hasUI) return;
		nctx = ctx.model?.contextWindow || 0;
		const sf = ctx.sessionManager.getSessionFile?.();
		file = sf ? path.join(STORE, path.basename(sf)) : null;
		samples = [];
		if (file) {
			try {
				samples = fs
					.readFileSync(file, "utf8")
					.split("\n")
					.filter(Boolean)
					.map((l) => JSON.parse(l));
			} catch {}
		}
		hook = hookFetch();
		hook.listener = consume;
		show(ctx);
	});

	pi.on("session_shutdown", async () => {
		if (hook?.listener === consume) hook.listener = null;
		if (paintTimer) clearTimeout(paintTimer);
		tui = null;
	});

	pi.on("model_select", async (_event, ctx) => {
		nctx = ctx.model?.contextWindow || nctx;
		paint(true);
	});

	pi.on("before_provider_request", (event, ctx) => {
		if (!ctx.hasUI || !PROVIDERS.includes(ctx.model?.provider)) return;
		const p = event.payload;
		if (!p || typeof p !== "object" || !p.stream) return;
		return { ...p, return_progress: true, timings_per_token: true };
	});

	pi.registerShortcut(KEY, {
		description: "llama-perf: cycle compact / decode / prefill / MTP graph",
		handler: async (ctx) => toggle(ctx),
	});

	pi.registerCommand("perf", {
		description: "llama.cpp perf widget: /perf (next graph) | /perf off | /perf on",
		handler: async (args, ctx) => toggle(ctx, (args || "").trim()),
	});
}
