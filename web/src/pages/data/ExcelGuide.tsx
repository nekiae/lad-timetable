import { useEffect, useState } from "react";

import { api, type ExcelGuideDTO } from "../../api";
import { Button, Panel, cx } from "../../ui";

// Как оформить Excel, чтобы он загрузился. Описание колонок приходит с сервера —
// из того же места, что лист «Как заполнять» в шаблоне и разбор при загрузке
// (lad/data_excel.py): подсказка на экране не может разойтись с тем, что
// система на самом деле понимает.
export function ExcelGuide({ id, onClose, onTemplate }: { id: string; onClose: () => void; onTemplate: () => void }) {
  const [guide, setGuide] = useState<ExcelGuideDTO>();
  const [active, setActive] = useState(0);

  useEffect(() => {
    api.excelGuide(id).then(setGuide).catch(() => undefined);
  }, [id]);

  const sheet = guide?.sheets[active];

  return (
    <Panel className="mt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-heading">Как оформить Excel для загрузки</h2>
        <button type="button" className="text-small text-pen underline-offset-4 hover:underline" onClick={onClose}>
          скрыть
        </button>
      </div>

      {/* Это настоящая последовательность действий — поэтому с номерами. */}
      <ol className="mt-4 grid gap-5 md:grid-cols-3">
        <li className="flex gap-3">
          <span className="text-small text-pencil">1</span>
          <span>
            <span className="block font-semibold">Скачайте шаблон</span>
            <span className="mt-1 block text-small text-ink/80">
              Первый лист — «Как заполнять». В колонках с выбором — выпадающие списки, у заголовков — подсказки.
              Если данные уже есть, «Скачать в Excel» даёт тот же файл с ними.
            </span>
            <Button className="mt-2" onClick={onTemplate}>Скачать пустой шаблон</Button>
          </span>
        </li>
        <li className="flex gap-3">
          <span className="text-small text-pencil">2</span>
          <span>
            <span className="block font-semibold">Заполните листы по порядку</span>
            <span className="mt-1 block text-small text-ink/80">
              Классы, Кабинеты, Предметы, Учителя, Нагрузка. Названия классов, предметов и ФИО пишите одинаково
              на всех листах. Синие заголовки — обязательные колонки.
            </span>
          </span>
        </li>
        <li className="flex gap-3">
          <span className="text-small text-pencil">3</span>
          <span>
            <span className="block font-semibold">Загрузите файл</span>
            <span className="mt-1 block text-small text-ink/80">
              Кнопкой «Загрузить из Excel». Заменятся только листы, которые есть в файле, прежние данные останутся
              в истории. Что система не поймёт — покажет с листом, строкой и колонкой.
            </span>
          </span>
        </li>
      </ol>

      {guide && sheet && (
        <div className="mt-6 border-t border-rule pt-4">
          <div className="inline-flex flex-wrap rounded border border-rule bg-sheet p-0.5" role="tablist" aria-label="Листы файла">
            {guide.sheets.map((s, n) => (
              <button key={s.sheet} type="button" role="tab" aria-selected={n === active} onClick={() => setActive(n)}
                      className={cx("rounded-[4px] px-3 py-1 text-small font-medium transition-colors duration-150",
                                    n === active ? "bg-pen text-white" : "text-ink hover:bg-paper")}>
                {s.sheet}
              </button>
            ))}
          </div>
          <p className="mt-3 max-w-prose text-small text-pencil">Лист «{sheet.sheet}». {sheet.about}</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-left text-small">
              <thead>
                <tr className="border-b border-ink/30">
                  <th className="py-2 pr-4 font-semibold">Колонка</th>
                  <th className="py-2 pr-4 font-semibold">Что писать</th>
                  <th className="py-2 font-semibold">Пример</th>
                </tr>
              </thead>
              <tbody>
                {sheet.columns.map((column) => (
                  <tr key={column.name} className="border-b border-rule align-top">
                    <td className="py-2 pr-4">
                      <span className="font-medium">{column.name}</span>
                      {column.required && <span className="block text-pen">обязательно</span>}
                    </td>
                    <td className="py-2 pr-4">
                      {column.hint}
                      {column.kind === "choice" && (
                        <span className="mt-0.5 block text-pencil">Варианты: {column.options.join(", ")}.</span>
                      )}
                      {column.kind === "bool" && <span className="mt-0.5 block text-pencil">да или нет</span>}
                    </td>
                    <td className="py-2 font-narrow">{column.example || <span className="text-pencil">пусто</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Panel>
  );
}
