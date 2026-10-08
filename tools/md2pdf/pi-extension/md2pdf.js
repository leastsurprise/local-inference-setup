/**
 * md2pdf: keep FILE.pdf beside every .md file that holds a ```mermaid block.
 * After pi's write or edit of such a file, or a bash command that changed one
 * (e.g. a script regenerating a report), run `md2pdf` and append the outcome
 * to the tool result, so the model sees a failed diagram and fixes it. Silent
 * where md2pdf is not installed.
 *
 * Install: copy to ~/.pi/agent/extensions/ and put tools/md2pdf/md2pdf on PATH
 * (or set MD2PDF to its full path).
 *
 * @param {import("../core/extensions/types.ts").ExtensionAPI} pi
 */
import { existsSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join, resolve } from "node:path";

const findOnPath = (name) =>
  (process.env.PATH ?? "").split(delimiter).map((d) => join(d, name)).find((p) => existsSync(p));
const MD2PDF = process.env.MD2PDF || findOnPath("md2pdf") || "";
// Never walked for bash-changed files: bulky, and never hold human-facing docs.
const PRUNE = [".git", "node_modules", "data", "_extracted", ".venv*", "venv*", "__pycache__"];
const MAX_BASH_FILES = 10;

const hasMermaid = (file) => {
  try { return /^ *```mermaid/m.test(readFileSync(file, "utf8")); } catch { return false; }
};
const pdfIsCurrent = (file) => {
  try { return statSync(file.replace(/\.md$/, ".pdf")).mtimeMs >= statSync(file).mtimeMs; } catch { return false; }
};

export default function md2pdfExtension(pi) {
  const bashStarted = new Map();

  const render = async (file, signal) => {
    try {
      const r = await pi.exec(MD2PDF, [file], { signal, timeout: 180000 });
      return r.code === 0
        ? `md2pdf: wrote ${file.replace(/\.md$/, ".pdf")}`
        : `md2pdf FAILED for ${file} (exit ${r.code}), no PDF written. Fix the mermaid block and save again:\n${(r.stderr || r.stdout).trim()}`;
    } catch (err) {
      return `md2pdf FAILED for ${file}: ${err?.message ?? err}`;
    }
  };

  const changedByBash = async (cwd, sinceMs, signal) => {
    const prune = PRUNE.flatMap((n, i) => (i ? ["-o", "-name", n] : ["-name", n]));
    const since = `@${Math.floor(sinceMs / 1000) - 1}`;
    const r = await pi.exec("find", [cwd, "(", ...prune, ")", "-prune", "-o",
      "-type", "f", "-name", "*.md", "-newermt", since, "-print"], { signal, timeout: 15000 });
    return r.stdout.split("\n").filter(Boolean);
  };

  pi.on("tool_call", async (event) => {
    if (event.toolName === "bash") bashStarted.set(event.toolCallId, Date.now());
  });

  pi.on("tool_result", async (event, ctx) => {
    if (!MD2PDF || !existsSync(MD2PDF)) return;
    let files = [];
    if (event.toolName === "write" || event.toolName === "edit") {
      const p = event.input?.path;
      if (event.isError || typeof p !== "string" || !p.endsWith(".md")) return;
      files = [resolve(ctx.cwd, p.replace(/^~(?=\/)/, homedir()))];
    } else if (event.toolName === "bash") {
      const started = bashStarted.get(event.toolCallId);
      bashStarted.delete(event.toolCallId);
      if (started === undefined) return;
      try { files = await changedByBash(ctx.cwd, started, ctx.signal); } catch { return; }
      files = files.filter((f) => !pdfIsCurrent(f));
    } else {
      return;
    }
    files = files.filter(hasMermaid);
    if (!files.length) return;

    const notes = [];
    for (const f of files.slice(0, MAX_BASH_FILES)) notes.push(await render(f, ctx.signal));
    if (files.length > MAX_BASH_FILES) {
      notes.push(`md2pdf: ${files.length - MAX_BASH_FILES} more changed .md files not rendered; run md2pdf on them if they are human-facing.`);
    }
    return { content: [...(event.content ?? []), { type: "text", text: notes.join("\n") }] };
  });
}
