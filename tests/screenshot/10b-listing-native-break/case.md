Длинный листинг в режиме по умолчанию (`captions.continuation_break: false`): один сплошной `<w:tbl>`, Word/LO ломает содержимое строки между страницами без вставки подписи продолжения.

```python
import sys
import os
import time
from dataclasses import dataclass
from typing import Iterable, Iterator


@dataclass
class Item:
    """Запись реестра."""

    id: int
    name: str
    payload: bytes


def load(path: str) -> Iterator[Item]:
    with open(path, "rb") as fp:
        while True:
            header = fp.read(8)
            if not header:
                break
            length = int.from_bytes(header[:4], "little")
            id_ = int.from_bytes(header[4:8], "little")
            payload = fp.read(length)
            yield Item(id=id_, name=f"item-{id_}", payload=payload)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: load.py <file>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"missing: {path}", file=sys.stderr)
        return 1
    started = time.monotonic()
    total = 0
    for item in load(path):
        total += len(item.payload)
    elapsed = time.monotonic() - started
    print(f"items loaded; bytes={total} elapsed={elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

: Длинный модуль (native break)

Текст после длинного листинга — для контроля интервала после.
