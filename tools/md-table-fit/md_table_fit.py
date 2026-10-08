#!/usr/bin/env python3
"""Fit Markdown pipe tables to a maximum line width (default 160).

Only table blocks are rewritten; every other line is left byte-for-byte alone.
Tables inside fenced code blocks are ignored. The output is always an aligned
GFM pipe table.

A table that fits is just re-aligned. In a table that does not fit, each cell is
word-wrapped to its column and a row is continued on extra physical rows whose
other cells are empty:

  | Column    | Meaning                           |
  | --------- | --------------------------------- |
  | OrderDate | Date the order was placed; drives |
  |           | the 30-day return window.         |

Breaking is markup-aware: a code span or **bold** run cut by a row break is
closed at the end of the row and reopened on the next; a link is never cut.
Column widths are searched to use as few physical rows as possible.

Usage:
  md_table_fit.py FILE_OR_DIR ...         rewrite in place
  md_table_fit.py --check FILE_OR_DIR ... report over-wide tables, exit 1 if any
  md_table_fit.py --stdout FILE           print the result, do not write
  md_table_fit.py --join FILE_OR_DIR ...  print split rows rejoined (read-only view)
  md_table_fit.py --all FILE_OR_DIR ...   fit every file, ignoring front matter

By default only files whose YAML front matter says `audience: [human]` or
`[human, llm]` are fitted or checked; every other file (only an LLM reads it,
code parses it, or it has no front matter) is skipped. --all fits them all.
stdin is always processed.
  md_table_fit.py -                       stdin -> stdout
"""

import argparse
import os
import re
import sys
import unicodedata

DEFAULT_WIDTH = 160
MIN_COL = 3          # a delimiter cell needs at least '---'
SPLIT_MARK = '\u21a9'  # '↩' ends a row where a word was cut mid-word; --join removes it
SPLIT_WORD_ROWS = 3  # a word split mid-word costs as much as this many extra rows
SPLIT_LINK_ROWS = 12 # ...and a split (so broken) link this many

FENCE_RE = re.compile(r'^( {0,3})(`{3,}|~{3,})')
DELIM_CELL_RE = re.compile(r'^\s*:?-+:?\s*$')
BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
SOFT_WRAP_RE = re.compile(r'^<br\s*/?>\s*', re.IGNORECASE)
LINK_RE = re.compile(r'!?\[[^\]]*\]\([^)]*\)')
SKIP_DIRS = {'node_modules', '_vendor', '__pycache__', '_extracted'}


# ── width ────────────────────────────────────────────────────────────────

def disp_width(text):
    width = 0
    for ch in text:
        if unicodedata.combining(ch) or ch in '​‍️':
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
    return width


def pad(text, width, align):
    gap = width - disp_width(text)
    if gap <= 0:
        return text
    if align == 'right':
        return ' ' * gap + text
    if align == 'center':
        return ' ' * (gap // 2) + text + ' ' * (gap - gap // 2)
    return text + ' ' * gap


# ── pipe-table parsing ───────────────────────────────────────────────────

def split_row(line, ncols=None):
    """Split a pipe-table row on unescaped pipes outside code spans.

    GFM splits inside code spans too; pandoc and most authors do not. Pipes in
    code spans are protected unless that gives the wrong cell count and the GFM
    split gives the right one.
    """
    cells = _split(line, protect_code=True)
    if ncols is not None and len(cells) != ncols:
        gfm = _split(line, protect_code=False)
        if len(gfm) == ncols:
            return gfm
    return cells


def _split(line, protect_code):
    body = line.strip()
    cells, cur, i = [], [], 0
    while i < len(body):
        ch = body[i]
        if protect_code and ch == '`':
            run = re.match(r'`+', body[i:]).group(0)
            close = re.compile(r'(?<!`)' + run + r'(?!`)').search(body, i + len(run))
            if close:
                cur.append(body[i:close.end()])
                i = close.end()
                continue
            cur.append(run)
            i += len(run)
            continue
        if ch == '\\' and i + 1 < len(body):
            cur.append(body[i:i + 2])
            i += 2
            continue
        if ch == '|':
            cells.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append(''.join(cur))
    if body.startswith('|'):
        cells = cells[1:]
    if body.endswith('|') and not body.endswith('\\|') and cells:
        cells = cells[:-1]
    return [c.strip() for c in cells]


def has_pipe(line):
    return bool(re.search(r'(?<!\\)\|', line))


def is_delim(line, ncols):
    if not has_pipe(line):
        return False
    cells = split_row(line)
    return len(cells) == ncols and all(DELIM_CELL_RE.match(c) for c in cells)


def alignment(delim_cell):
    c = delim_cell.strip()
    left, right = c.startswith(':'), c.endswith(':')
    if left and right:
        return 'center'
    if right:
        return 'right'
    if left:
        return 'left'
    return None


# ── markup-aware tokens ──────────────────────────────────────────────────
#
# A cell is cut into Pieces at spaces (never inside a link, nor inside a code
# span with unusual spacing). Markup state is positional: for every character we
# know whether it sits inside a code span (and which delimiter) and whether
# **bold** is open before it. A piece, or a chunk of an over-long piece, takes
# its state from its first and last character, so a row break anywhere can close
# the open markup and reopen it on the next row.

def _code_spans(cell):
    """[(start, end, delim)] for each closed code span."""
    spans, i = [], 0
    while True:
        m = re.compile(r'`+').search(cell, i)
        if not m:
            return spans
        run = m.group(0)
        close = re.compile(r'(?<!`)' + run + r'(?!`)').search(cell, m.end())
        if not close:
            i = m.end()
            continue
        spans.append((m.start(), close.end(), run))
        i = close.end()


class Cell:
    def __init__(self, text):
        self.text = text
        n = len(text)
        self.code = [None] * n            # delimiter if the char is inside code-span content
        nobreak = [False] * n
        self.odd_spacing = set()          # code spans with unusual spacing: never cut at their spaces
        self.in_link = set()              # cut points strictly inside a link
        spans = _code_spans(text)
        for s, e, d in spans:
            inner = text[s + len(d):e - len(d)]
            for k in range(s + len(d), e - len(d)):
                self.code[k] = d
            # A code span is kept whole; hard_split may still cut it at a space if it is
            # wider than its column, unless its spacing is unusual.
            if '  ' in inner or inner != inner.strip() or '`' in inner:
                self.odd_spacing.update(range(s, e))
            for k in range(s, e):
                nobreak[k] = True
        for m in LINK_RE.finditer(text):
            if not any(s <= m.start() < e for s, e, _ in spans):
                for k in range(m.start(), m.end()):
                    nobreak[k] = True
                self.in_link.update(range(m.start() + 1, m.end()))
        self.nobreak = nobreak
        # bold[k]: is **bold** open just before char k (k == n: at the end)
        self.bold = [False] * (n + 1)
        state, k = False, 0
        while k < n:
            self.bold[k] = state
            if text.startswith('**', k) and self.code[k] is None and (k == 0 or text[k - 1] != '\\'):
                self.bold[k + 1] = state
                state = not state
                k += 2
                continue
            k += 1
        self.bold[n] = state
        self.pieces = []
        start = None
        for k in range(n + 1):
            if k == n or (text[k].isspace() and not nobreak[k]):
                if start is not None:
                    self.pieces.append(Piece(self, start, k))
                start = None
            elif start is None:
                start = k


class Piece:
    __slots__ = ('cell', 'start', 'end', 'brk', 'mark')

    def __init__(self, cell, start, end, brk=None, mark=False):
        self.cell, self.start, self.end, self.mark = cell, start, end, mark
        if brk is None:
            text = cell.text[start:end]
            brk = any(cell.code[start + m.start()] is None for m in BR_RE.finditer(text))
        self.brk = brk

    @property
    def text(self):
        return self.cell.text[self.start:self.end]

    @property
    def code_in(self):
        return self.cell.code[self.start]

    @property
    def code_out(self):
        return self.cell.code[self.end - 1]

    @property
    def bold_in(self):
        return self.cell.bold[self.start]

    @property
    def bold_out(self):
        return self.cell.bold[self.end]


def render_line(line, final=False):
    """Join the pieces of one physical cell line, closing/reopening markup at its ends.

    The cell's final line gets no closing markup: anything still open there was
    open in the source too.
    """
    if not line:
        return ''
    first, last = line[0], line[-1]
    head = ('**' if first.bold_in else '') + (first.code_in or '')
    tail = '' if final else \
        (last.code_out or '') + ('**' if last.bold_out else '') + (SPLIT_MARK if last.mark else '')
    return head + ' '.join(p.text for p in line) + tail


def hard_split(piece, width):
    """Split a piece too wide for its column.

    Cut points, best first: a space inside a code span (kept at the end of the
    chunk), just after punctuation, anywhere else. Never next to a backtick or '*'
    (that would tear a delimiter), and inside a link only when nothing else fits.
    Every chunk but the last ends its row with SPLIT_MARK, so --join can glue the
    chunks back together with no space.
    """
    cell, text = piece.cell, piece.cell.text

    def fits(a, b, mark=False):
        return disp_width(render_line([Piece(cell, a, b, brk=False, mark=mark)])) <= width

    def legal(k, allow_link):
        if text[k - 1] in '`*' or (k < len(text) and text[k] in '`*'):
            return False
        return allow_link or k not in cell.in_link

    chunks, start = [], piece.start
    while start < piece.end and not fits(start, piece.end):
        limit = start + 1
        while limit < piece.end and fits(start, limit + 1, mark=True):
            limit += 1
        space = max((j for j in range(start + 1, limit)
                     if text[j] == ' ' and cell.code[j] and j not in cell.odd_spacing),
                    default=None)
        if space is not None and space - start > (limit - start) // 3:
            chunks.append(Piece(cell, start, space + 1, brk=True, mark=True))
            start = space + 1
            continue
        cut = max((j + 1 for j in range(start, limit) if text[j] in '._/\\-],;)' and legal(j + 1, False)),
                  default=None)
        if cut is None or cut - start <= (limit - start) // 2:
            cut = max((k for k in range(start + 1, limit + 1) if legal(k, False)), default=None) \
                or max((k for k in range(start + 1, limit + 1) if legal(k, True)), default=None) \
                or limit
        chunks.append(Piece(cell, start, cut, brk=True, mark=True))
        start = cut
    if start < piece.end:
        chunks.append(Piece(cell, start, piece.end, brk=piece.brk))
    else:
        chunks[-1].brk, chunks[-1].mark = piece.brk, False
    return chunks


def wrap(cell, width):
    """Greedy wrap of a Cell into lines no wider than width.

    Returns (lines, words split, links split).
    """
    lines, cur, split, links = [], [], 0, 0
    queue = []
    for p in cell.pieces:
        if disp_width(render_line([p])) > width:
            queue += hard_split(p, width)
            split += 1
            links += any(k in cell.in_link for k in range(p.start, p.end))
        else:
            queue.append(p)
    for p in queue:
        if cur and disp_width(render_line(cur + [p])) > width:
            lines.append(cur)
            cur = []
        cur.append(p)
        if p.brk:
            lines.append(cur)
            cur = []
    if cur or not lines:
        lines.append(cur)
    return [render_line(line, final=(k == len(lines) - 1)) for k, line in enumerate(lines)], split, links


def check_preserved(cell, lines):
    """Every non-space character of the cell survives, in order (added markup excepted)."""
    joined = re.sub(r'\s', '', ''.join(lines))
    want = re.sub(r'\s', '', cell)
    it = iter(joined)
    if not all(ch in it for ch in want):
        raise AssertionError('cell content changed while wrapping: %r' % cell)


# ── table layout ─────────────────────────────────────────────────────────

def water_fill(demands, budget):
    """Give each column up to its demand, sharing the budget equally among the rest."""
    alloc = [0] * len(demands)
    remaining = sorted(range(len(demands)), key=lambda i: demands[i])
    while remaining:
        share = budget // len(remaining)
        i = remaining[0]
        if demands[i] <= share:
            alloc[i] = demands[i]
            budget -= demands[i]
            remaining.pop(0)
            continue
        extra = budget - share * len(remaining)
        for k, j in enumerate(sorted(remaining)):
            alloc[j] = share + (1 if k < extra else 0)
        break
    return alloc


class Layout:
    def __init__(self, header, rows):
        self.cells = [[Cell(c) for c in r] for r in [header] + rows]
        self.ncols = len(header)
        self.cache = {}

    def col_lines(self, col, width):
        key = (col, width)
        if key not in self.cache:
            self.cache[key] = [wrap(r[col], width) for r in self.cells]
        return self.cache[key]

    def cost(self, widths):
        """Smaller is better: (overflow, header lines, row score, total cell lines).

        Row score is physical rows (dividers included), plus one per extra line in the first column (a
        wrapped first cell blurs where one row ends and the next begins), plus a
        penalty per word, and a bigger one per link, split mid-word.
        """
        per_col = [self.col_lines(c, w) for c, w in enumerate(widths)]
        overflow = sum(max(0, disp_width(line) - w)
                       for c, w in enumerate(widths) for lines, _, _ in per_col[c] for line in lines)
        links = sum(l for c in range(self.ncols) for _, _, l in per_col[c])
        splits = sum(s for c in range(self.ncols) for _, s, _ in per_col[c])
        heights = [max(len(per_col[c][r][0]) for c in range(self.ncols)) for r in range(len(self.cells))]
        groups = ([([0] * (heights[0] - 1), True)] if heights[0] > 1 else []) + \
                 [([0] * h, h > 1) for h in heights[1:]]
        dividers = sum(1 for row in with_separators(groups) if row is SEPARATOR)
        lines = sum(len(per_col[c][r][0]) for c in range(self.ncols) for r in range(len(self.cells)))
        first_extra = sum(len(lines) - 1 for lines, _, _ in per_col[0][1:])
        return (overflow, heights[0],
                sum(heights) + dividers + first_extra + SPLIT_WORD_ROWS * splits + SPLIT_LINK_ROWS * links, lines)


def choose_widths(layout, natural, budget):
    longest = [max([MIN_COL] + [disp_width(render_line([p])) for r in layout.cells for p in r[c].pieces])
               for c in range(layout.ncols)]
    floors = water_fill([max(MIN_COL, min(n, l)) for n, l in zip(natural, longest)], budget)
    extra = water_fill([n - f for n, f in zip(natural, floors)], budget - sum(floors))
    widths = [f + e for f, e in zip(floors, extra)]

    # Local search: move width between columns while it saves physical rows.
    best = layout.cost(widths)
    steps = (16, 8, 4, 2, 1)
    improved = True
    while improved:
        improved = False
        for step in steps:
            for a in range(layout.ncols):
                for b in range(layout.ncols):
                    if a == b or widths[a] - step < MIN_COL or widths[b] + step > natural[b]:
                        continue
                    trial = list(widths)
                    trial[a] -= step
                    trial[b] += step
                    cost = layout.cost(trial)
                    if cost < best:
                        best, widths, improved = cost, trial, True
    return widths


SEPARATOR = None      # marks a divider row in a list of physical rows
# A divider row is drawn with spaced dashes ('| - - - - |'). A run of unbroken
# dashes, however padded, is a legal header-delimiter cell, and lenient renderers
# start a new table at such a row; spaced dashes can never be a delimiter.
# Dividers from earlier versions ('| ---   |', '|  ---  |', '| ----- |') are
# recognised too, by their exact shape, and redrawn.
DIVIDER_CELL_RE = re.compile(r'^-(?: -)+$')
OLD_DIVIDER_LINE_RE = re.compile(r'^\s*\|(?:(?: -+   )|(?:  -+  ))(?:\|(?:(?: -+   )|(?:  -+  )))*\|\s*$')
OLD_DIVIDER_CELL_RE = re.compile(r'^-{3,}$')


def is_divider(raw_line):
    if OLD_DIVIDER_LINE_RE.match(raw_line):
        return True
    cells = split_row(raw_line)
    return bool(cells) and all(DIVIDER_CELL_RE.match(c) or OLD_DIVIDER_CELL_RE.match(c) for c in cells)


def divider_cell(width):
    return ('- ' * width)[:width].rstrip()


def with_separators(groups):
    """Flatten [(physical rows, was split)] into body rows.

    If any group was split, every pair of adjacent groups gets a divider between
    them (none at the very top or bottom, never two in a row). Then each block
    between dividers is exactly one logical row, which is what lets --join rejoin
    rows exactly. A table with no split row gets no dividers.
    """
    out = []
    split_table = any(split for _, split in groups)
    for g, (rows, _) in enumerate(groups):
        if split_table and g:
            out.append(SEPARATOR)
        out += rows
    return out


def render_table(indent, aligns, physical, widths):
    def row_line(cells):
        if cells is SEPARATOR:
            return indent + '| ' + ' | '.join(pad(divider_cell(w), w, None) for w in widths) + ' |'
        return indent + '| ' + ' | '.join(pad(c, w, a) for c, w, a in zip(cells, widths, aligns)) + ' |'

    def delim(w, a):
        if a == 'center':
            return ':' + '-' * (w - 2) + ':'
        if a == 'right':
            return '-' * (w - 1) + ':'
        if a == 'left':
            return ':' + '-' * (w - 1)
        return '-' * w

    out = [row_line(physical[0]), indent + '| ' + ' | '.join(delim(w, a) for w, a in zip(widths, aligns)) + ' |']
    return out + [row_line(r) for r in physical[1:]]


def fit_table(indent, header, aligns, rows, width):
    """Return (lines, (words split, links split), header_wrapped); lines is None if the columns cannot fit."""
    ncols = len(aligns)
    natural = [max([MIN_COL] + [disp_width(r[i]) for r in [header] + rows if r is not SEPARATOR])
               for i in range(ncols)]
    budget = width - disp_width(indent) - (3 * ncols + 1)
    if sum(natural) <= budget:
        return render_table(indent, aligns, [header] + rows, natural), (0, 0), False
    rows = [r for r in rows if r is not SEPARATOR]            # dividers are regenerated below
    if budget < ncols * MIN_COL:
        return None, (0, 0), False

    layout = Layout(header, rows)
    widths = choose_widths(layout, natural, budget)
    per_col = [layout.col_lines(c, w) for c, w in enumerate(widths)]
    groups, split, links_split = [], 0, 0
    header_lines = 1
    for r, cells in enumerate([header] + rows):
        wrapped = [per_col[c][r][0] for c in range(ncols)]
        links_split += sum(per_col[c][r][2] for c in range(ncols))
        split += sum(per_col[c][r][1] for c in range(ncols))
        for cell, lines in zip(cells, wrapped):
            check_preserved(cell, lines)
        height = max(len(l) for l in wrapped)
        lines = [[l[k] if k < len(l) else '' for l in wrapped] for k in range(height)]
        if r == 0:
            # GFM allows one header line; cost() puts that first, and if it still wraps
            # the overflow becomes the first body row(s), set off like a split row.
            header_lines = height
            head = lines[0]
            if height > 1:
                groups.append((lines[1:], True))
        else:
            groups.append((lines, height > 1))
    physical = [head] + with_separators(groups)
    # Tighten each column to what it uses.
    widths = [max(MIN_COL, max(disp_width(row[c]) for row in physical if row is not SEPARATOR))
              for c in range(ncols)]
    return render_table(indent, aligns, physical, widths), (split, links_split), header_lines > 1


# ── --join: rejoin split rows ────────────────────────────────────────────

def join_cell(lines):
    """Undo wrap() for one cell: glue its physical lines back into the source text.

    After a SPLIT_MARK the next line continues the same word: drop the mark and
    the closing/reopening markup around the break, and glue with no space. Any
    other break was at a space, inside no code span; if the line ends with '**'
    and the next starts with '**', that is bold closed and reopened, so drop both.
    """
    text = lines[0]
    for nxt in lines[1:]:
        if text.endswith(SPLIT_MARK):
            text = re.sub(r'`*$', '', re.sub(r'\*\*$', '', text[:-len(SPLIT_MARK)]))
            nxt = re.sub(r'^`*', '', re.sub(r'^\*\*', '', nxt))
            text += nxt
        elif text.endswith('**') and nxt.startswith('**'):
            text = text[:-2] + ' ' + nxt[2:]
        else:
            text += ' ' + nxt
    return text


def join_rows(rows, widths):
    """If rows are one logical row split by this tool, return it rejoined, else None.

    The test is exact: re-wrapping the rejoined cells at the column widths must
    reproduce every physical line.
    """
    joined = []
    for c, w in enumerate(widths):
        lines = [r[c] for r in rows]
        while lines and not lines[-1]:
            lines.pop()
        if not lines:
            joined.append('')
            continue
        if '' in lines:
            return None
        cell = join_cell(lines)
        if wrap(Cell(cell), w)[0] != lines:
            return None
        joined.append(cell)
    return joined


def join_table(indent, header, delim_line, rows):
    """Rejoin a table this tool split: one line per logical row, no dividers."""
    widths = [len(c) for c in split_row(delim_line)]
    data = [r for r in rows if r is not SEPARATOR]
    if any(disp_width(c) > w for r in [header] + data for c, w in zip(r, widths)):
        widths = None                     # not laid out by this tool: rejoin nothing

    segments, cur = [], []
    for r in rows:
        if r is SEPARATOR:
            segments.append(cur)
            cur = []
        else:
            cur.append(r)
    segments.append(cur)
    segments = [seg for seg in segments if seg]

    # Only a table with dividers was split by this tool, and there each block
    # between dividers is one logical row. (A table with no dividers is either
    # unsplit or a single split row; that cannot be told from several short
    # rows, so it is left as is.)
    out = []
    has_dividers = any(r is SEPARATOR for r in rows)
    for seg in segments:
        merged = join_rows(seg, widths) if widths and has_dividers and len(seg) > 1 else None
        out += [merged] if merged else seg

    def line(cells):
        return indent + '| ' + ' | '.join(cells) + ' |'
    return [line(header), delim_line] + [line(r) for r in out]


# ── document walk ────────────────────────────────────────────────────────

def process(text, width, path='<stdin>', output_lines=False, join=False):
    """Return (new_text, problems, notes), each a list of (path, line_no, message).

    problems: tables wider than `width` in the input. notes: warnings that never fail a run.
    Line numbers point into the output when output_lines is set, else into the input.
    """
    lines = text.split('\n')
    out, problems, notes = [], [], []
    fence = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = FENCE_RE.match(line)
        if fence:
            out.append(line)
            if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= len(fence) and not line.strip()[len(m.group(2)):].strip():
                fence = None
            i += 1
            continue
        if m:
            fence = m.group(2)
            out.append(line)
            i += 1
            continue

        if has_pipe(line) and i + 1 < len(lines):
            header = split_row(line)
            if is_delim(lines[i + 1], len(header)):
                at = (len(out) if output_lines else i) + 1
                indent = re.match(r'^\s*', line).group(0)
                aligns = [alignment(c) for c in split_row(lines[i + 1])]
                j = i + 2
                raw_rows = []
                while j < len(lines) and lines[j].strip() and has_pipe(lines[j]) and not FENCE_RE.match(lines[j]):
                    body = lines[j].strip()
                    # A hand-made soft wrap: "<br> rest of cell | next |" with no leading pipe.
                    if raw_rows and SOFT_WRAP_RE.match(body):
                        raw_rows[-1] += ' ' + SOFT_WRAP_RE.sub('', body)
                    else:
                        raw_rows.append(body)
                    j += 1
                rows = [SEPARATOR if is_divider(r) else split_row(r, len(header)) for r in raw_rows]
                ncols = max([len(header)] + [len(r) for r in rows if r is not SEPARATOR])
                if ncols > len(header):
                    notes.append((path, at, 'a row has %d cells but the header %d: kept as an extra '
                                  'column (GFM would drop it); fix the source' % (ncols, len(header))))
                aligns += [None] * (ncols - len(aligns))
                header += [''] * (ncols - len(header))
                rows = [r if r is SEPARATOR else r + [''] * (ncols - len(r)) for r in rows]
                original = lines[i:j]
                if join:
                    try:
                        out += join_table(indent, header, lines[i + 1], rows)
                    except Exception as exc:      # never let one table abort the file
                        problems.append((path, at, 'internal error, table shown as is (%s: %s)'
                                         % (type(exc).__name__, exc)))
                        out += original
                    i = j
                    continue
                try:
                    new, split, header_wrapped = fit_table(indent, header, aligns, rows, width)
                except Exception as exc:          # never let one table abort the file
                    problems.append((path, at, 'internal error, table left as is (%s: %s)'
                                     % (type(exc).__name__, exc)))
                    new, split, header_wrapped = original, (0, 0), False
                if new is None:
                    problems.append((path, at, '%d columns cannot fit in %d (left as is)' % (ncols, width)))
                    new = original
                else:
                    if max(disp_width(l) for l in original) > width:
                        problems.append((path, at, 'table %d wide' % max(disp_width(l) for l in original)))
                    if split[0]:
                        notes.append((path, at, '%d word(s) longer than their column were split across rows%s'
                                      % (split[0], ', %d of them links (now broken)' % split[1] if split[1] else '')))
                    if header_wrapped:
                        notes.append((path, at, 'header too wide for one line: its overflow is in the first '
                                      'body row(s)'))
                out += new
                i = j
                continue

        out.append(line)
        i += 1
    return '\n'.join(out), problems, notes


def audience(text):
    """The `audience` list from a file's YAML front matter, or None if it has none.

    Accepts `audience: [human, llm]`, `audience: human` and a block list.
    """
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        return None
    for end in range(1, len(lines)):
        if lines[end].strip() in ('---', '...'):
            break
    else:
        return None
    fm = lines[1:end]
    for k, line in enumerate(fm):
        m = re.match(r'^audience:\s*(.*)$', line)
        if not m:
            continue
        value = m.group(1).strip()
        if value.startswith('['):
            return [v.strip().strip('"\'').lower() for v in value.strip('[]').split(',') if v.strip()]
        if value:
            return [value.strip('"\'').lower()]
        items = []
        for item in fm[k + 1:]:
            mm = re.match(r'^\s+-\s*(.+)$', item)
            if not mm:
                break
            items.append(mm.group(1).strip().strip('"\'').lower())
        return items
    return None


FITTABLE_AUDIENCES = ({'human'}, {'human', 'llm'})


def fit_allowed(text):
    """Only files whose front matter says people read them are fitted:
    `audience: [human]` or `[human, llm]`.

    A file only an LLM reads (`[llm]`) or that code parses (any `machine`) keeps
    its tables one row per line, and so does a file with no front matter, since
    nobody has said who reads it. An LLM reading a fitted file uses --join.
    """
    aud = audience(text)
    return aud is not None and set(aud) in FITTABLE_AUDIENCES


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs
                                 if not d.startswith('.') and d not in SKIP_DIRS and not d.startswith('venv'))
                for f in sorted(files):
                    if f.lower().endswith('.md'):
                        yield os.path.join(root, f)
        else:
            yield p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='+', help="Markdown files or directories (recursed for *.md), or '-' for stdin")
    ap.add_argument('--width', type=int, default=DEFAULT_WIDTH, help='maximum line width (default %(default)s)')
    ap.add_argument('--check', action='store_true', help='report over-wide tables only; exit 1 if any')
    ap.add_argument('--stdout', action='store_true', help='print the result instead of writing files')
    ap.add_argument('--join', action='store_true',
                    help='print a read-only view with split rows rejoined, one line per row; never writes')
    ap.add_argument('--all', action='store_true',
                    help='fit every file, ignoring the front-matter audience gate')
    args = ap.parse_args(argv)

    if args.join:
        paths = ['-'] if args.paths == ['-'] else list(iter_files(args.paths))
        for path in paths:
            if path == '-':
                text = sys.stdin.read()
            else:
                with open(path, encoding='utf-8', newline='') as fh:
                    text = fh.read().replace('\r\n', '\n')
            new, problems, _ = process(text, args.width, path, output_lines=True, join=True)
            for p, ln, msg in problems:
                print('%s:%d: %s' % (p, ln, msg), file=sys.stderr)
            if len(paths) > 1:
                print('==> %s <==' % path)
            sys.stdout.write(new if new.endswith('\n') else new + '\n')
        return 0

    if args.paths == ['-']:
        new, problems, notes = process(sys.stdin.read(), args.width, output_lines=not args.check)
        for path, ln, msg in problems + notes:
            print('%s:%d: %s' % (path, ln, msg), file=sys.stderr)
        if not args.check:
            sys.stdout.write(new)
        return 1 if args.check and problems else 0

    failed = changed = skipped = 0
    explicit = {p for p in args.paths if not os.path.isdir(p)}
    for path in iter_files(args.paths):
        with open(path, encoding='utf-8', newline='') as fh:
            text = fh.read()
        if not args.all and not fit_allowed(text):
            skipped += 1
            if path in explicit:
                aud = audience(text.replace('\r\n', '\n'))
                print('%s: skipped: %s' % (path, 'audience is [%s]; only [human] or [human, llm] files are fitted'
                                           % ', '.join(aud)
                                           if aud is not None else 'no front matter with an audience'),
                      file=sys.stderr)
            if args.stdout:
                sys.stdout.write(text)
            continue
        crlf = '\r\n' in text
        new, problems, notes = process(text.replace('\r\n', '\n'), args.width, path,
                                       output_lines=not args.check)
        if crlf:
            new = new.replace('\n', '\r\n')
        unfixable = [p for p in problems if 'left as is' in p[2]]
        report = problems if args.check else unfixable
        for p, ln, msg in report:
            print('%s:%d: %s' % (p, ln, msg), file=sys.stderr)
        failed += len(report)
        for p, ln, msg in notes:
            print('%s:%d: note: %s' % (p, ln, msg), file=sys.stderr)
        if args.check:
            continue
        if args.stdout:
            sys.stdout.write(new)
        elif new != text:
            with open(path, 'w', encoding='utf-8', newline='') as fh:
                fh.write(new)
            changed += 1
            print('rewrote %s' % path)
    if skipped:
        print('%d file(s) skipped: audience not [human] or [human, llm]' % skipped, file=sys.stderr)
    if not args.check and not args.stdout:
        print('%d file(s) rewritten' % changed, file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
