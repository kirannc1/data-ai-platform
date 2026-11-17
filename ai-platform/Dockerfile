FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY domains ./domains
RUN mkdir -p /opt/spark-jars \
    && printf 'print("Spark dependencies resolved")\n' > /tmp/resolve_jars.py \
    && spark-submit --master 'local[1]' \
        --conf spark.jars.ivy=/tmp/build-ivy \
        --packages io.delta:delta-spark_2.12:3.3.3,org.apache.hadoop:hadoop-aws:3.3.4 \
        /tmp/resolve_jars.py \
    && cp /tmp/build-ivy/jars/*.jar /opt/spark-jars/ \
    && rm -rf /tmp/build-ivy /tmp/resolve_jars.py
RUN groupadd --gid 10001 sparkapp \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin sparkapp
ENV HOME=/home/sparkapp
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "ai_platform.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
