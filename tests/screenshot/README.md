# Screenshot tests — visual regression gate

Скриншот-тесты — **gate перед merge**. При первом падении автоматизированная отладка обязана **остановиться** (см. [`AGENTS.md`](../../AGENTS.md)). Дальше — ручной разбор пользователем по `_report.pdf`.

## Что делает харнесс

Для каждого case-каталога `tests/screenshot/<name>/`:

1. `md2gost convert case.md -o actual.docx --config config.yaml` (CLI из T006)
2. `actual.docx → actual.pdf` через unoserver (XML-RPC, по умолчанию `127.0.0.1:2003`)
3. `actual.pdf` и `expected.pdf` нарезаются на PNG через `pdf2image`
4. Pillow-разность по пикселям; если `pixels_differ > tolerance_pixels` — PDF-кейс упал
5. Артефакты упавших страниц складываются в `_artifacts/<case>/page_NNN/{expected,actual,diff}.png`
6. Для HTML preview enabled-кейсов тот же `expected.pdf` сравнивается с Playwright-скриншотом native HTML preview; page-count/runtime ошибки валят общий screenshot test, а старый exact pixel-diff по умолчанию report-only
7. По завершении сессии собирается `_report.pdf` с тройками `expected | actual | diff (red overlay)` для всех проваленных кейсов

Отдельный `make test-html-calibration` — строгий HTML regression gate. Он
сохраняет expected/actual/layout diff/raw diff для каждой страницы, пишет
JSON/Markdown summary и сравнивает tolerant layout-метрику с просмотренным
`html-calibration-reference.json`.

## Структура case-каталога

```
tests/screenshot/<case-name>/
├── case.md          # markdown
├── config.yaml      # YAML-конфиг ГОСТ (preset + overrides)
├── expected.pdf     # эталонный PDF (генерируется один раз)
├── meta.yaml        # (опц.) tolerance_pixels, dpi
└── README.md        # (опц.) описание
```

`meta.yaml`:

```yaml
tolerance_pixels: 200   # default 50; разница в пикселях, которую считаем шумом
dpi: 100                # default 100; чем выше, тем дольше прогон и точнее diff
validate_docx: true     # default true; см. раздел «Validation gate»
html_enabled: true      # default true только для базовых HTML parity кейсов
html_tolerance_pixels: 500
html_dpi: 100           # default наследует dpi
html_strict_pixels: false
html_known_broken: optional note for disabled HTML parity cases
```

## Запуск

```bash
make test-screenshot
make test-html-calibration
```

Требует поднятого unoserver (`make up` запускает stack локально, либо запускайте через `make test-in-docker`). Если unoserver недоступен — тесты **скипаются** с понятным сообщением (отключается через `MD2GOST_SKIP_IF_NO_UNOSERVER=0`).

`make test-html-calibration` unoserver не использует: oracle — закоммиченные
`expected.pdf`. Для него нужны `poetry install`, Chromium
(`poetry run playwright install chromium`) и Poppler/`pdftoppm`. Все артефакты,
включая успешные, лежат в
`tests/screenshot/_artifacts/html-calibration/`; основной результат —
`summary.json`.

Диагностический прогон без regression thresholds:

```bash
poetry run python tests/screenshot/html_calibration.py --report-only
poetry run python tests/screenshot/html_calibration.py --case 04-lists --report-only
```

Калибровочная layout-метрика считает несовпавшие тёмные пиксели после
однопиксельного antialias tolerance; точный RGB diff также сохраняется. Порог
для aggregate, каждого case и худшей страницы равен
`reference * (1 + relative) + absolute`. Потеря case coverage, page-count
mismatch и изменение размера page image всегда считаются ошибкой.

Переменные окружения:

| Переменная | Default | Назначение |
|---|---|---|
| `UNOSERVER_HOST` | `127.0.0.1` | хост unoserver |
| `UNOSERVER_PORT` | `2003` | XML-RPC порт |
| `MD2GOST_UPDATE_BASELINES` | `0` | при `1` — все `expected.pdf` перезаписываются текущим выводом, тесты скипаются |
| `MD2GOST_SKIP_IF_NO_UNOSERVER` | `1` | при `0` — упасть, а не скипнуть, если unoserver недоступен |
| `MD2GOST_HTML_STRICT_RUNTIME` | `0` | при `1` — упасть, а не скипнуть, если Playwright/HTML runtime недоступен |
| `MD2GOST_HTML_STRICT_PIXELS` | `0` | при `1` — HTML pixel-diff валит тест; по умолчанию HTML pixel-diff только попадает в `_report.pdf` |

## Создать/обновить эталон

```bash
make screenshot-baseline        # перегенерирует expected.pdf для всех кейсов
```

Или вручную:

```bash
MD2GOST_UPDATE_BASELINES=1 poetry run pytest tests/screenshot -v
```

После этого закоммитьте изменённые `expected.pdf`. Делайте это **только** когда уверены, что новый рендеринг — корректный (визуальная сверка по `_report.pdf` или вручную).

## Validation gate

Помимо pixel-diff каждый кейс проходит через структурную валидацию DOCX. Результаты складываются в ту же `CaseFailure` отдельной секцией; кейс **падает**, если есть пиксельный diff **или** хоть одна validation issue с `severity=error` (warnings сами по себе кейс не валят).

### DOCX (`_validators/docx.py`)
- открывается через `python-docx` (`docx.open_failed`)
- все `word/*.xml` и `word/_rels/*.rels` — well-formed XML (`docx.xml_malformed`)
- все internal-relationships (`TargetMode != "External"`) указывают на существующие части пакета (`docx.rels.broken`)
- опционально: XSD-валидация по флагу `MD2GOST_DOCX_XSD=1`. XSD-бандл в репо не лежит — при выставленном флаге без бандла поднимается одна warning-issue `docx.xsd.unavailable`, кейс не падает

### Отключить per-case через `meta.yaml`

```yaml
validate_docx: false
```

`_report.pdf` для каждого упавшего кейса добавляет дополнительную страницу «Validation issues — &lt;case&gt;» со списком issues в формате `[severity] validator.code — message (location)`, сгруппированных по валидатору.

## Чтение `_report.pdf`

Каждая страница отчёта = одна страница одного провалившегося кейса. Слева направо: `expected | actual | diff`. На `diff` красным закрашены пиксели, отличающиеся от эталона. В шапке — имя кейса, номер страницы, число «упавших» пикселей.

Если у кейса есть только validation-issues или page-count mismatch без пиксельных страниц — отрендерится summary/validation page.

## Smoke-кейс

`_smoke/` — минимальный кейс для проверки самого пайплайна. Должен проходить **до** реализации настоящего рендеринга (T010+): пока `convert.py` возвращает пустой `Document`, `expected.pdf` для smoke'а — это PDF-рендер пустого docx.

Эталон для `_smoke/` нужно создать один раз вручную:

```bash
make up                          # поднять unoserver (или make test-in-docker)
make screenshot-baseline         # сгенерирует и закоммитит expected.pdf
```

## Правило при падении

1. Ассистент **останавливается** и пишет краткое сообщение пользователю
2. В сообщении: список упавших кейсов, путь к `tests/screenshot/_report.pdf`
3. Дальше — ручной разбор пользователем
4. Если регрессия легитимна — запустить `make screenshot-baseline`, закоммитить новые эталоны

Обычный HTML parity использует тот же `_report.pdf`. По умолчанию он валит тест только
на критичных ошибках: page-count mismatch, renderer/runtime failure. Pixel-diff
между LibreOffice PDF и Chromium HTML считается диагностикой и не блокирует
merge, пока явно не включён `MD2GOST_HTML_STRICT_PIXELS=1` или
`html_strict_pixels: true`. Для CI-регрессии по известному междвижковому шуму
используется `make test-html-calibration`, а не exact pixel mode.

Длинные table/listing cases можно временно держать с `html_enabled: false` и
`html_known_broken`, если preview model ещё не умеет повторить page-break
семантику DOCX/LibreOffice (например, manual continuation chunks или native
table/listing split). Короткие cases должны оставаться включёнными, чтобы
геометрия таблиц, caption, ширины, alignment и listing highlighting не
регрессировали.

## Что НЕ коммитить

- `_artifacts/` — диагностические PNG падений (см. `.gitignore`)
- `_report.pdf` — генерируется заново каждой сессией (см. `.gitignore`)
