FROM public.ecr.aws/docker/library/postgres:18-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && python3 -m pip install --break-system-packages --no-cache-dir boto3 'psycopg[binary]' \
    && rm -rf /var/lib/apt/lists/*
COPY infra/aws/restore.py /opt/aquanqa/restore.py
ENTRYPOINT ["python3", "/opt/aquanqa/restore.py"]
