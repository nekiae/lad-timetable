import { useState } from "react";
import type { Directory, LessonDTO } from "../api";
import { Button, Panel } from "../ui";
import type { Aim } from "./TargetedPrefs";

/** Одно предложение правки: что сказать системе и человеческая формулировка. */
type Fix = { text: string; aim: Aim };

const sameAim = (a: Aim, b: Aim) =>
  a.key === b.key && a.scope === b.scope && a.who === b.who && String(a.value) === String(b.value);

/** «Поправить» — разговор с готовым расписанием.
 *
 * До этого экран умел только двигать уроки по одному руками. Но завуч смотрит
 * на сетку и видит не «переставить этот урок», а правило: «у пятых слишком
 * длинные дни», «Иванова весь день в школе», «информатика не должна быть
 * в понедельник». Здесь клик по уроку превращается в такое правило — оно
 * ложится в пожелания школы и остаётся там, а не пропадает вместе с ходом.
 */
export function FixMenu({ lesson, lessons, dir, aims, onAdd, onRebuild }: {
  lesson: LessonDTO;
  lessons: LessonDTO[];
  dir: Directory;
  aims: Aim[];
  onAdd: (aim: Aim) => void;
  onRebuild: () => void;
}) {
  const [open, setOpen] = useState(false);

  const subject = dir.subjects[lesson.subject_id] ?? "";
  const teacher = dir.teachers[lesson.teacher_id] ?? "";
  const classId = dir.groups[lesson.group_id]?.class_ids[0] ?? "";
  const dayName = dir.days.find((d) => d.n === lesson.day)?.name ?? "";

  // Уроки этого класса в этот день — по ним считаются «сколько их» и «какой
  // он по счёту». Номер по счёту, а не номер урока в сетке: вторая смена
  // начинается с седьмого, и «не позже шестого» она понимает по-своему.
  const sameDay = lessons
    .filter((l) => dir.groups[l.group_id]?.class_ids.includes(classId) && l.day === lesson.day)
    .map((l) => l.period);
  const periods = [...new Set(sameDay)].sort((a, b) => a - b);
  const countToday = periods.length;
  const position = periods.indexOf(lesson.period) + 1;

  const fixes: Fix[] = [];
  if (subject)
    fixes.push({
      text: `«${subject}» не ставить в ${dayName.toLowerCase()}`,
      aim: { scope: "subject", who: subject, key: "subject_not_on_day", value: lesson.day },
    });
  if (classId && countToday > 4)
    fixes.push({
      text: `У ${classId} не больше ${countToday - 1} уроков в день (сейчас ${countToday})`,
      aim: { scope: "class", who: classId, key: "max_lessons_per_day", value: countToday - 1 },
    });
  if (classId && position === countToday && position > 4)
    fixes.push({
      text: `${classId} заканчивать не позже ${position - 1}-го урока`,
      aim: { scope: "class", who: classId, key: "end_by", value: position - 1 },
    });
  if (teacher) {
    fixes.push({
      text: `${teacher}: окна — это очень важно`,
      aim: { scope: "teacher", who: teacher, key: "teacher_gap", value: 3 },
    });
    fixes.push({
      text: `${teacher}: не больше 3 уроков подряд`,
      aim: { scope: "teacher", who: teacher, key: "teacher_max_in_row", value: 3 },
    });
  }
  if (classId)
    fixes.push({
      text: `У ${classId} трудные предметы не в конце дня`,
      aim: { scope: "class", who: classId, key: "late_hard", value: 3 },
    });

  const added = fixes.filter((f) => aims.some((a) => sameAim(a, f.aim)));

  if (!open)
    return <Button onClick={() => setOpen(true)}>Поправить</Button>;

  return (
    <Panel as="div" className="text-small">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-heading">Что здесь не так?</p>
        <button type="button" className="text-pencil underline-offset-4 hover:underline"
                onClick={() => setOpen(false)}>скрыть</button>
      </div>
      <p className="mt-1 text-pencil">
        Это не ход по сетке, а пожелание школы: оно запомнится и будет учитываться
        при каждом составлении.
      </p>
      <ul className="mt-3 space-y-1">
        {fixes.map((fix) => {
          const already = aims.some((a) => sameAim(a, fix.aim));
          return (
            <li key={fix.text}>
              <button type="button" disabled={already} onClick={() => onAdd(fix.aim)}
                      className={already
                        ? "text-left text-pencil"
                        : "text-left text-pen underline-offset-4 hover:underline"}>
                {fix.text}{already ? " — учтено" : ""}
              </button>
            </li>
          );
        })}
      </ul>
      {added.length > 0 && (
        <Button variant="primary" className="mt-3" onClick={onRebuild}>
          Пересобрать с учётом
        </Button>
      )}
    </Panel>
  );
}
