---
title: "AGENTS.md — working with Mike (global rules for every project)"
audience: [llm]
published: 2026-10-09
subject: "How the user wants every agent to work, in any project: pace, scope, reporting and how to explain things."
outcomes:
  - "Get to the headline fast, list loose ends instead of chasing them, and check in regularly."
  - "Explain top-down with small, rendered Mermaid diagrams."
  - "Know when PONYTAIL.md applies to code work and when a project opts out."
---

# Working with Mike

These rules hold in every project. A project's own AGENTS.md adds to them and
wins where the two conflict.

## Time is money

The user is waiting while you work, and their attention fades. Spend effort
where it changes the answer they asked for. "Time is money" means be fast and
spend tool calls, tokens and reading only where they pay off. It is not a
request to estimate or report any dollar cost.

1. **Headline first.** Check what the user wants and the outcome they expect;
   ask if it is unclear. Do the literal ask, and find the one thing a human
   would see at a glance. Get there in as few steps as you can.
2. **Scope to the ask.** "Transcribe and comment" is not "investigate". A
   project's evidence rules govern the claims you make. They are not a reason
   to make more claims.
3. **List loose ends; do not chase them.** If something does not fit (numbers
   that do not reconcile, a file not where expected, a gap in a series), give
   a one-line guess at the cause (misread? rounding? truncation?). Resolve it
   only if it could change the headline, and only far enough to know whether
   it does.
4. **Then stop and offer a numbered menu:**

   > **Headline:** <one or two sentences>
   >
   > Loose ends — reply with numbers to pursue, or "headline only":
   > 1. <issue> — likely <cause>; ~<cost in tool calls>; buys <value>
   > 2. ...

5. **Check in every ~10 tool calls.** If you have nothing to show by then,
   report where you are and ask whether to continue.

This section does not apply while you execute a checklist step unattended
(a loop runner with no one watching); the runner's instructions govern that.

## How the user learns

The user learns visually and from the top down: the wood first, then only the
trees that serve their aim.

1. **Open with the whole picture.** Begin an answer or document with the big
   picture: what the parts are, how they connect, and where the user's question
   fits. Give detail after that, and only the detail the aim needs. Offer the
   rest as a loose end rather than writing it out.
2. **Draw it.** In any `.md` file a human reads, add a Mermaid diagram wherever
   a picture makes a key idea easier to grasp and remember: data flow
   (`flowchart LR`), process or status stages (`flowchart` or
   `stateDiagram-v2`), who calls whom (`sequenceDiagram`), how records relate
   (`erDiagram`), and how things are grouped (`mindmap`). Put the overview
   diagram near the top. Leave out a diagram that only repeats a short list.
3. **Keep each diagram small enough to read at a glance.** Aim for about 12
   nodes or fewer. Split a bigger picture into an overview plus one diagram per
   part. Label edges with the verb or the key. Every node must name something
   real that the text cites; a diagram claim needs the same evidence as a prose
   claim.
4. **Check that it renders.** A diagram that does not parse is worse than none.
   `mmdc` ([mermaid-cli](https://github.com/mermaid-js/mermaid-cli)) works
   offline:

   ```sh
   mmdc -i FILE.md -o /tmp/check.md      # renders every mermaid block; errors name the bad one
   mmdc -i diagram.mmd -o diagram.svg    # or .png (-s 2 for sharper) to hand over an image
   ```

   Fix any block that fails, and keep the fenced ```` ```mermaid ```` source
   in the `.md` file, because the user's viewer renders it.
5. **Ship a PDF beside it.** Whenever a `.md` file holds a ```` ```mermaid ````
   block, write a PDF of the same name next to it, with the diagrams drawn,
   and rewrite the PDF after every edit to the `.md`. Use `md2pdf`
   ([`../tools/md2pdf`](../tools/md2pdf/)). Under pi, its extension does this
   for you after each `write`, `edit` or `bash` call that changes such a file,
   and adds a line to the tool result. If that line says `md2pdf FAILED`, fix
   the diagram and save again. It skips `data/`, `_extracted/`, `.git`,
   `node_modules` and venvs. Anywhere it does not reach, run it yourself:

   ```sh
   md2pdf FILE.md            # writes FILE.pdf beside it, offline; takes several files
   ```

   A stale or missing PDF counts as unfinished work.

Checklist steps follow these rules too when a step writes a human-facing `.md`
file.

## Building code

Before you write or change code, read `PONYTAIL.md` (installed beside this
file) and follow it.
Skip this step if the project's AGENTS.md says `ponytail: off`. That project
has its own rules for what to write.
