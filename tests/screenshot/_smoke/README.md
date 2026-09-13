# `_smoke` — minimal screenshot case

Проверяет что весь screenshot-pipeline работает end-to-end: CLI из T006 → unoserver → pdf2image → diff.

Кейс рендерит минимальный документ через `src/md2gost/convert.py` — это smoke-тест всего пайплайна (CLI → unoserver → pdf2image → diff), а не содержания.

После T010 (параграфы) этот кейс начнёт сравниваться с настоящим рендерингом одного параграфа — `expected.pdf` потребует обновления через `make screenshot-baseline`.

`tolerance_pixels: 200` — небольшой запас под недетерминизм рендеринга шрифтов в LibreOffice.
