---
title: "md-table-fit"
audience: [human, llm]
published: 2026-10-02
subject: "Usage and behaviour of md_table_fit.py, which wraps only Markdown table blocks to fit within 160 characters, plus --join, the unwrapper, a read-only view that rejoins split rows."
outcomes:
  - "Rewrite, check or preview over-wide tables in a file or folder."
  - "Read a reflowed table correctly with --join."
  - "Understand how lines are broken, what dividers mean, and the exit codes."
---

# md-table-fit — keep Markdown tables within 160 characters

Rewrites **only the table blocks** in a Markdown file, so that no table line
is wider than 160 characters. Every other line is left byte-for-byte alone.
The output is always an aligned GFM pipe table. Python 3 standard library only.

It comes in two halves:

- **The wrapper** (default) splits long rows so a table reads in a terminal,
  an 80/160-column editor or a PDF without sideways scrolling.
- **The unwrapper** (`--join`) gives the exact reverse as a read-only view:
  each split row back on one line, so `grep` and an LLM see whole rows.
  [`md2pdf`](../md2pdf/) uses it to print tables unsplit.

```mermaid
flowchart LR
    W["wide table<br/>one row per line"] -->|md_table_fit.py| F["fitted table<br/>rows split, dividers"]
    F -->|--join view| W
    F -->|people read| R["editor, terminal, GitHub"]
```

```sh
python3 tools/md-table-fit/md_table_fit.py FILE.md              # rewrite in place
python3 tools/md-table-fit/md_table_fit.py docs/                # every *.md under a folder
python3 tools/md-table-fit/md_table_fit.py --check FILE.md      # report only; exit 1 if any table is over-wide
python3 tools/md-table-fit/md_table_fit.py --stdout FILE.md     # preview, write nothing
python3 tools/md-table-fit/md_table_fit.py --width 120 FILE.md  # another limit (default 160)
python3 tools/md-table-fit/md_table_fit.py --join FILE.md       # read-only view: split rows rejoined
python3 tools/md-table-fit/md_table_fit.py --all FILE.md        # fit even without audience front matter
```

## Which files it touches

By default, only files whose YAML front matter says people read them:
`audience: [human]` or `audience: [human, llm]`. It skips a file that only an
LLM reads (`[llm]`), one that code parses (any `machine`), and one with no
front matter. Those keep one table row per line, because an agent or a parser
reads them line by line. A file named on the command line says why it was
skipped; a folder run prints a count. `--join` works on every file, and stdin
is always processed. **`--all` turns the gate off** and fits every file named
or found.

```yaml
---
audience: [human, llm]
---
```

The gate exists because a table that an agent or a script reads line by line
should keep one row per line. If you don't use front matter, use `--all`.

## What it does

A table that already fits is re-aligned. In a table that does not fit, each
cell is word-wrapped to its column, and a row continues on extra physical rows
whose other cells are left empty. In a table with any split row, a divider row
of spaced dashes (`- - -`) separates every pair of rows. There is none above the
first body row and none below the last. A table with no split row gets no
dividers:

```
| Column        | Meaning                                  | Source     |
| ------------- | ---------------------------------------- | ---------- |
| `OrderDate`   | Date the order was placed; drives the    | `[TICKET]` |
|               | **30-day** return window.                |            |
| - - - - - - - | - - - - - - - - - - - - - - - - - - - -  | - - - - -  |
| `ReturnBy`    | `OrderDate` + 30 days                    | `[CODE]`   |
```

A divider between every row, not just around the split ones, is what makes a
split table exactly reversible. Each block between dividers is one row.

The tool also tries hard not to wrap the first column, so a row's first line is
easy to spot.

### How it breaks lines

- **At spaces, never inside a link**, and not inside a code span if the span
  fits on a row by itself.
- **Markup is closed and reopened across a break.** A code span or `**bold**`
  run cut by a row break is closed at the end of the row and reopened on the
  next (`` `a b` `` → `` `a` `` / `` `b` ``), so each physical cell renders
  correctly by itself.
- **Column widths are searched**, not just shared out. In order, it minimises:
  text overflowing its column, a header wrapping, and then a row score. The row
  score is physical rows, divider rows included, plus a penalty for each of
  these:
  - an extra line in the first column: +1;
  - a word split mid-word: +3;
  - a link split, which breaks it: +12.

  So a long link is only broken when keeping it whole would cost a dozen or
  more extra rows.
- **A word wider than any column it could get** (rare: a long path in a narrow
  table) is split after `.`, `_`, `/` and the like where possible, and noted.
  The row is ended with `↩`, which means "this word continues on the next row".
  A long code span is preferably split at one of its own spaces, and that
  space is kept at the end of the row.

## Reading split tables: `--join` (the unwrapper)

`--join` prints the file with each split row rejoined onto one line, dividers
removed, `↩` splits glued back, and reopened markup dropped. It writes nothing.
Rejoined rows are not padded, so lines can be long. Use it whenever an exact
name or a whole row matters:

```sh
python3 tools/md-table-fit/md_table_fit.py --join FILE.md                       # read the tables
python3 tools/md-table-fit/md_table_fit.py --join docs/ | grep -n 'OrderDate'   # search a folder
```

With more than one file, each starts with a `==> path <==` line. Line numbers
are the view's, not the file's.

It rejoins a block only if re-wrapping the rejoined text at that column width
reproduces every physical line exactly. Otherwise the block is shown as it is,
and nothing is ever merged by guesswork. Measured on a 249-table working repo
(fit each original, then `--join`):

- **242 come back exactly as written.**
- **The other 7 are shown unjoined, as physical rows; nothing is lost.**
  - 3 have a header too wide for one line. Its overflow can't be told from a
    split first row, so it shows as the first data row.
  - 4 have only one body row, and it is split. With no divider in the table,
    one split row can't be told from several short rows.
- **No long name (12+ characters) that `grep` found in an original is missing
  from the `--join` view.** In the fitted files themselves, 159 were.

Re-running is a no-op.

## What to know

- **A split row renders as several rows.** GitHub and VS Code show each
  physical row as its own table row, with blank cells where a column did not
  wrap, and a divider as a row of dashes. That is the price of staying under 160
  in GFM, which has no multi-line cells.
- **Why spaced dashes.** An unbroken run of dashes, however it's padded, is a
  legal header-delimiter cell in GFM. Lenient renderers start a new table at
  such a row, even though a strict parser reads it as an ordinary row. A
  delimiter cell must be one unbroken run, so `- - -` can never be mistaken
  for one.
- **`↩` is a reserved character.** A row ending in `↩` is read as a mid-word
  split. Don't end a table cell with it in your own text.
- **Dividers are regenerated.** A row whose cells are all spaced dashes counts
  as a divider. So do the shapes earlier versions wrote (`| -----   |`,
  `|  ---  |`, `| ----- |`). When a table has to be refitted, dividers are
  dropped and placed afresh. A table that already fits keeps its dividers,
  redrawn in the current form. A data row whose every cell is `- -`, or 3+
  unbroken dashes, would be taken for a divider; a `-` placeholder is safe.
- **A refit doesn't rejoin earlier splits.** If you edit a table this tool
  already split and it no longer fits, each physical row is wrapped again on
  its own. To reflow it properly, join the row's lines back into one first.
- **The header must be one line** in GFM. If it can't fit, its overflow goes
  into the first body row(s), followed by a divider, and a `note:` says so.
  Shorten the header text. `--join` can't rejoin the overflow (see above).
- **Cell text is never changed.** Each wrap is checked to keep every
  non-whitespace character in order. The only additions are the closing and
  reopening markup at a row break, and `↩` after a mid-word split.
- **Hand-made soft wraps are joined back up.** A row continued on a next line
  that starts `<br>` with no leading pipe is merged into its row before wrapping.
  GFM renders those as broken rows.
- **`<br>` in a cell** stays in the text, and the row breaks after it.
- **Pipes inside code spans** do not split a cell. If that gives the wrong cell
  count for a row (an unbalanced backtick, say), the tool falls back to GFM's
  rule that every unescaped pipe splits.
- **A row with more cells than the header** is kept as an extra column (GFM
  would drop the excess silently), and noted. Fix the source.
- **Width is counted in characters.** East Asian wide characters count as two.
  An editor that draws `—`, `→` or `§` double-width will show those rows
  slightly misaligned.
- **Not touched:** tables inside fenced code blocks, tables inside blockquotes,
  and HTML tables.
- **Cannot fit:** a table with more columns than 160 can hold (about 26) is
  left as is and reported, and the exit code is 1. If anything unexpected goes
  wrong inside one table, that table is left as is and reported. The rest of
  the file is still processed.
- Folders are searched for `*.md`, skipping dot-folders, `venv*`,
  `node_modules`, `_vendor` and `_extracted`. Don't point it
  at folders of generated or machine-read Markdown.

## Exit codes

| Mode      | 0                          | 1                                                      |
| --------- | -------------------------- | ------------------------------------------------------ |
| rewrite   | every table now fits       | a table could not be made to fit (reported)            |
| `--check` | no table is over the width | at least one table is over the width (each one listed) |
