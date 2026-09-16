# Один образ: собранный интерфейс + API. FastAPI отдаёт и то и другое.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 3.13, а не новее: у ortools нет колёс под 3.14.
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir ortools==9.15.6755 pandas==3.0.5 openpyxl==3.1.5 \
        fastapi==0.115.14 "uvicorn[standard]==0.32.1" fpdf2==2.8.8 xlrd==2.0.2
COPY src/ src/
COPY server/ server/
COPY data/sanpin_by.json data/plan_75.json data/school.json data/
# Шрифт для PDF-листов: в нём есть кириллица (lad/sheets.py). Лицензия — OFL.
COPY data/fonts/ data/fonts/
COPY --from=web /web/dist web/dist

# База — на подключаемом томе, иначе школы пропадают при каждом деплое.
ENV LAD_DB=/data/lad.sqlite3
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
