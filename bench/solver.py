"""Стенд замеров солвера — сравнивать варианты алгоритма цифрами, а не на глаз.

Один и тот же вход, одинаковые сиды и бюджет. По каждому прогону:
  • first  — секунды до первой законной сетки;
  • zero   — секунды до нуля нарушений норм (пусто — не дошли);
  • tail   — какие нормы оставались перед нулём и на какой секунде (что держит хвост);
  • итог по валидатору: нарушения норм, окна и выходы учителей, разброс дней,
    разброс трудности, структурные конфликты.

Запуск (по одному за раз: прогоны делят процессор, параллельные замеры врут):

    .venv/bin/python bench/solver.py --label baseline
    .venv/bin/python bench/solver.py data/school_big.json --budget 120 --seeds 1 2 3 --out bench/results.jsonl

Вариант алгоритма задаётся кодом, а метка `--label` подписывает строку в --out,
чтобы потом сравнить «baseline» и «draft-comfort» рядом.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import lad.solve as lad_solve  # noqa: E402
from lad.solve import Rules, assign_rooms, solve  # noqa: E402
from lad.quality import measure  # noqa: E402
from lad.tables import build_school, tables_from_dict  # noqa: E402
from lad.validate import check  # noqa: E402

NORMS = "Нарушений норм"


def _value(text: str):
    """«0.6» → 0.6, «true» → True, «8» → 8, остальное — строкой."""
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def _pairs(items: list[str]) -> dict:
    return {k: _value(v) for k, _, v in (item.partition("=") for item in items)}


def run(school, budget: float, seed: int, params: dict | None = None) -> dict:
    started = time.monotonic()
    marks: dict = {"first": None, "zero": None, "tail": {}}

    def on_progress(p) -> None:
        now = time.monotonic() - started
        if not p.metrics:
            return
        if marks["first"] is None:
            marks["first"] = now
        if NORMS in p.metrics and marks["zero"] is None:
            if p.metrics[NORMS] == 0:
                marks["zero"] = now
            else:
                marks["tail"] = {"at": round(now, 1), **{k: v for k, v in p.norms.items() if v}}

    result = solve(school, max_seconds=budget, rules=Rules(), on_progress=on_progress,
                   params={"random_seed": seed, **(params or {})})
    lessons = assign_rooms(school, result.lessons) if result.ok else []
    report = check(school, lessons) if lessons else None
    row = {
        "seed": seed,
        "status": result.status,
        "first": round(marks["first"], 1) if marks["first"] is not None else None,
        "zero": round(marks["zero"], 1) if marks["zero"] is not None else None,
        "tail": marks["tail"],
        "lessons": len(lessons),
    }
    if report:
        row.update({
            "norms": len(report.norm_violations),
            "conflicts": len(report.structural_violations),
            "teacher_gaps": report.teacher_gaps,
            "teacher_days": report.teacher_days,
            "class_spread": report.class_spread,
            "difficulty_spread": report.difficulty_spread,
        })
        # Логика сверх норм (lad/quality.py): ровность дней, понедельник, разнесённость.
        quality = measure(school, lessons)
        row.update({k: v for k, v in quality.items() if k != "examples"})
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("school", nargs="?", default=str(ROOT / "data" / "school.json"))
    parser.add_argument("--budget", type=float, default=120)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--out", help="дописать строки JSON в этот файл")
    parser.add_argument("--tune", nargs="*", default=[], metavar="КЛЮЧ=ЗНАЧЕНИЕ",
                        help="ручки lad.solve.TUNING, например draft_comfort=true draft_share=0.6")
    parser.add_argument("--params", nargs="*", default=[], metavar="КЛЮЧ=ЗНАЧЕНИЕ",
                        help="параметры CP-SAT, например num_workers=8")
    args = parser.parse_args()

    tune, params = _pairs(args.tune), _pairs(args.params)
    unknown = set(tune) - set(lad_solve.TUNING)
    if unknown:
        sys.exit(f"нет таких ручек в TUNING: {sorted(unknown)}; есть {sorted(lad_solve.TUNING)}")
    lad_solve.TUNING.update(tune)

    raw = json.loads(Path(args.school).read_text(encoding="utf-8"))
    school, problems = build_school(tables_from_dict(raw), raw.get("settings") or {}, raw.get("wishes"))
    if problems:
        sys.exit(f"данные с проблемами: {problems[:3]}")
    print(f"{args.label}: {Path(args.school).name}, {len(school.classes)} кл., бюджет {args.budget:.0f} с, "
          f"сиды {args.seeds}, tune={tune or '—'}, params={params or '—'}", flush=True)

    rows = []
    for seed in args.seeds:
        row = run(school, args.budget, seed, params)
        rows.append(row)
        print(f"  seed={seed} first={row['first']}s zero={row['zero']}s norms={row.get('norms')} "
              f"gaps={row.get('teacher_gaps')} days={row.get('teacher_days')} spread={row.get('class_spread')} "
              f"diff={row.get('difficulty_spread')} conflicts={row.get('conflicts')} tail={row['tail']}", flush=True)
        print(f"         логика: дни±3={row.get('classes_spread_3plus')} Пн-пик={row.get('monday_heavy')} "
              f"2ч-подряд={row.get('adjacent_two')} 3ч-подряд={row.get('three_in_row')} "
              f"день-ради-урока={row.get('teacher_single_days')} длинный-день={row.get('teacher_longest_day')}",
              flush=True)
        if args.out:
            with open(args.out, "a", encoding="utf-8") as f:
                f.write(json.dumps({"label": args.label, "school": Path(args.school).name,
                                    "budget": args.budget, "tune": tune, "params": params, **row},
                                   ensure_ascii=False) + "\n")

    def median(key: str):
        values = [r[key] for r in rows if r.get(key) is not None]
        return statistics.median(values) if values else None

    print(f"  медианы: first={median('first')}s zero={median('zero')}s norms={median('norms')} "
          f"gaps={median('teacher_gaps')} days={median('teacher_days')} spread={median('class_spread')}")
    print(f"           дни±3={median('classes_spread_3plus')} Пн-пик={median('monday_heavy')} "
          f"2ч-подряд={median('adjacent_two')} 3ч-подряд={median('three_in_row')} "
          f"день-ради-урока={median('teacher_single_days')}")


if __name__ == "__main__":
    main()
