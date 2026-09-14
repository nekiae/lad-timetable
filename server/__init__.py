"""HTTP-обёртка над ядром ЛАД (src/lad).

Ядро ничего не знает про веб: сервер только хранит школы, запускает солвер
в отдельном процессе и отдаёт результат браузеру. См. docs/PLAN.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
