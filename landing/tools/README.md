# Снимки лендинга

Проверка вёрстки на телефоне и на десктопе. Playwright намеренно не лежит
в `package.json`: он нужен только здесь, а Vercel тянул бы его на каждой
сборке.

```bash
npm i --no-save playwright && npx playwright install chromium
npm run build && npx next start -p 3100 &
node tools/shot-mobile.mjs /путь/куда/класть   # 390x844, вся страница по экранам
node tools/shot-desktop.mjs /путь/куда/класть  # 1440x900, герой и секция сборки
```

Оба скрипта печатают, вылезает ли что-нибудь за правый край экрана.
