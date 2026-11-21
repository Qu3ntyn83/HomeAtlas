FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends nmap snmp ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV HOMEATLAS_DATA=/data HOMEATLAS_PORT=8099 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os,urllib.request as u;u.urlopen('http://127.0.0.1:%s/healthz'%os.environ['HOMEATLAS_PORT'],timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${HOMEATLAS_PORT}"]
