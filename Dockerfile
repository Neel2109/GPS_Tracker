FROM node:22-alpine AS web-build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html ./
COPY public ./public
COPY src ./src
COPY vite.config.ts tsconfig.json ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY agent ./agent
COPY installer ./installer
COPY build_exe.py TrackGuardApp.pyw ./
COPY --from=web-build /web/dist ./dist

RUN useradd --create-home --uid 10001 trackguard \
    && chown -R trackguard:trackguard /app
USER trackguard

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
