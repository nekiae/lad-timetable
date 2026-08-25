"""Оформление приложения — один CSS-блок на всё.

Основа темы живёт в `.streamlit/config.toml` (цвета, шрифты, радиусы) — там
ей и место. Сюда попадает только то, чего темой не выразить: белая карточка
с тенью на сером поле и плашка под иконку.

Стиль: монохром, антиква в заголовках, много воздуха. Ориентир — документ,
а не приложение: расписание уходит завучу и, возможно, в министерство,
и выглядеть должно соответственно.

CSS цепляется за классы `st-key-<key>` — Streamlit проставляет их контейнерам,
у которых задан `key`. Это единственный устойчивый способ адресовать
конкретный блок: data-testid меняются от версии к версии.
"""

import streamlit as st

_LIGHT = {
    "card": "#FFFFFF",
    "border": "#E4E4E7",
    "badge": "#18181B",
    "badge_ink": "#FFFFFF",
    "shadow": "0 1px 2px rgba(9,9,11,.04), 0 16px 40px -12px rgba(9,9,11,.12)",
    "rule": "#E4E4E7",
    "ink": "#18181B",
    "paper": "#FFFFFF",
    "ink_hover": "#3F3F46",
}

_DARK = {
    "card": "#161618",
    "border": "#27272A",
    "badge": "#F4F4F5",
    "badge_ink": "#09090B",
    "shadow": "0 1px 2px rgba(0,0,0,.4), 0 16px 40px -12px rgba(0,0,0,.6)",
    "rule": "#27272A",
    "ink": "#F4F4F5",
    "paper": "#09090B",
    "ink_hover": "#D4D4D8",
}


def palette() -> dict:
    theme = getattr(st.context, "theme", None)
    dark = getattr(theme, "type", "light") == "dark"
    return _DARK if dark else _LIGHT


def inject() -> None:
    """Вставить оформление. Вызывается один раз в начале скрипта."""
    c = palette()
    st.html(f"""
    <style>
      /* Заголовок страницы прижат к верху — Streamlit оставляет там пустоту.
         Но не вплотную: сверху висит панель самого Streamlit, и в облаке она
         выше, чем на своей машине (добавляются Share, звёздочка, GitHub).
         Фиксированные 3rem там не спасали — заголовок «ЛАД» уезжал под панель
         и был срезан наполовину. Поэтому отступ считается от ЕЁ высоты:
         переменную задаёт сам Streamlit, а запасные 3.75rem — на случай,
         если в очередной версии переменную переименуют. */
      .stMainBlockContainer {{
          padding-top: calc(var(--header-height, 3.75rem) + 1.25rem);
      }}

      /* Карточка: белый лист на сером поле, как в бумажной вёрстке */
      .st-key-intro_card {{
          background: {c['card']};
          border: 1px solid {c['border']};
          border-radius: 20px;
          box-shadow: {c['shadow']};
          padding: 2.8rem 3.2rem 2.4rem;
      }}

      /* Плашка под иконку — единственное чёрное пятно на экране */
      .st-key-intro_badge {{
          width: 60px; height: 60px !important; min-height: 60px;
          margin: 0 auto .6rem; padding: 0 !important;
          background: {c['badge']};
          border-radius: 17px;
          display: flex; align-items: center; justify-content: center;
      }}
      .st-key-intro_badge * {{
          color: {c['badge_ink']} !important; margin: 0 !important;
          font-size: 28px !important; line-height: 1 !important;
      }}

      /* Надстрочная метка шага: капитель с разрядкой — приём из типографики
         документов, сразу задаёт тон «официальное», а не «приложение» */
      .st-key-intro_step p {{
          text-transform: uppercase;
          letter-spacing: .18em;
          font-size: .72rem;
          font-weight: 600;
      }}

      /* Тонкая линейка между шапкой карточки и содержанием */
      .lad-rule {{ border-top: 1px solid {c['rule']}; margin: .4rem 0 .8rem; }}

      /* Пункты: иконка отдельной колонкой, текст с висячим отступом */
      .st-key-intro_points p {{ line-height: 1.62; }}

      /* ---- кнопки -----------------------------------------------------
         Главное действие — плашка цвета текста: чёрная на светлой теме,
         светлая на тёмной. Своими руками, потому что Streamlit всегда пишет
         на primary-кнопке БЕЛЫМ, и в монохроме на тёмной теме приходилось бы
         брать мутно-серый фон — кнопка читалась как отключённая. */
      .stButton button, .stDownloadButton button {{
          padding-top: .55rem; padding-bottom: .55rem; font-weight: 500;
      }}
      [data-testid="stBaseButton-primary"] {{
          background-color: {c['ink']} !important;
          border-color: {c['ink']} !important;
          color: {c['paper']} !important;
      }}
      [data-testid="stBaseButton-primary"] * {{ color: {c['paper']} !important; }}
      [data-testid="stBaseButton-primary"]:hover {{
          background-color: {c['ink_hover']} !important;
          border-color: {c['ink_hover']} !important;
      }}
      [data-testid="stBaseButton-primary"]:disabled,
      [data-testid="stBaseButton-primary"][disabled] {{
          background-color: {c['border']} !important;
          border-color: {c['border']} !important;
          opacity: .7;
      }}

      /* Ширина полосы набора: строка в 1500 пикселей нечитаема, глаз теряет
         начало следующей строки. Ограничиваем и центрируем. */
      .stMainBlockContainer {{ max-width: 1200px; margin: 0 auto; }}

      /* ---- рабочее место ---------------------------------------------
         Тот же приём, что и в интро: содержание лежит на белом листе,
         поле вокруг — серое. Вкладки становятся оглавлением этого листа. */
      .stTabs {{
          background: {c['card']};
          border: 1px solid {c['border']};
          border-radius: 18px;
          box-shadow: {c['shadow']};
          padding: 1.4rem 2rem 2rem;
      }}
      .stTabs [data-baseweb="tab-list"] {{ gap: 1.6rem; }}
      /* Активную вкладку Streamlit красит в primaryColor, а он в монохроме
         намеренно приглушён — выбранная вкладка получалась бледнее соседних.
         Возвращаем ей цвет текста и подчёркиваем. */
      .stTabs [data-testid="stTab"][aria-selected="true"],
      .stTabs [data-testid="stTab"][aria-selected="true"] * {{
          color: {c['ink']} !important; font-weight: 600;
      }}
      .stTabs [data-testid="stTab"][aria-selected="true"] {{
          box-shadow: inset 0 -2px 0 0 {c['ink']};
      }}

      /* Мастер — узкая колонка: это форма, а не таблица. Поле ввода во всю
         ширину экрана выглядит как ошибка вёрстки и мешает читать подписи. */
      .st-key-wizard_card {{
          max-width: 720px; margin: 0 auto;
          background: {c['card']};
          border: 1px solid {c['border']};
          border-radius: 20px;
          box-shadow: {c['shadow']};
          padding: 2.4rem 2.8rem 2rem;
      }}

      /* Метрики — карточками: на экране результата это главные цифры */
      .stMetric {{
          background: {c['card']};
          border: 1px solid {c['border']};
          border-radius: 14px;
          padding: 1rem 1.2rem;
      }}

      .stExpander {{ border-radius: 14px; }}
      .stDataFrame {{ border-radius: 12px; overflow: hidden; }}
      .stAlert {{ border-radius: 12px; }}

      /* Шапка: название и подпись стоят плотнее, как в шапке документа */
      .stMainBlockContainer h1 {{ margin-bottom: .1rem; }}
    </style>
    """)
