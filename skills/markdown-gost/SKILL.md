---
name: markdown-gost
description: Convert Markdown to GOST 7.32 formatted DOCX/PDF (Russian academic documents) and import DOCX/PDF back to Markdown. Use when the user writes or converts a GOST thesis/report/practice work, asks about markdown-gost CLI commands, or needs the extended Markdown syntax (attributes, captions, templates, bibliography, appendices).
license: MIT
---

# markdown-gost

Markdown → GOST 7.32 DOCX/PDF converter with an HTML preview engine.
Full normative syntax: read `syntax.md` in this skill directory.

## CLI

```bash
markdown-gost convert input.md -o out.docx
markdown-gost convert input.md -o out.pdf            # needs unoserver
markdown-gost convert input.md -o out.docx --config my.yaml
markdown-gost validate input.md
markdown-gost import legacy.docx -o imported.md      # needs pandoc >= 2.19
markdown-gost import legacy.pdf -o imported.md       # needs pandoc + unoserver
```

Config: YAML with presets — `default`, `gost-7-32-2017`, `mirea-practice`
(selected inside the file: `preset: gost-7-32-2017`). PDF needs a running
unoserver (`UNOSERVER_HOST`/`UNOSERVER_PORT`, default 127.0.0.1:2003).

## Syntax cheat sheet

````markdown
# Heading {#id}
# Heading {.unnumbered}
# Appendix Title {.appendix}

![Caption](img.png){width=80%}

| A | B |
|---|---|
| 1 | 2 |

: Table caption {widths="50%, 50%"}

```python
print("listing")
```

: Listing caption

Inline math $e^{i\pi} + 1 = 0$, block math below:

$$
\sum_{i=1}^{n} i
$$
{#sum}

Citation [@book], auto-reference [](#sum), [labelled](#sum),
underline [text]{.underline}.

::: {.template name="titlepage-university"}
title: Practice report
:::

::: {.template name="content" depth=3}
:::

::: {.bibliography}
- id: book
  text: Author. Title. City, 2026.
:::

::: {.page-break}
:::
````

Everything else — attributes grammar, container nesting, error rules —
is in `syntax.md` next to this file (the single source of truth,
shared with the repository).
