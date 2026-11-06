FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r requirements.txt

ARG PRELOAD_DOCLING=true
RUN if [ "$PRELOAD_DOCLING" = "true" ]; then \
        (docling-tools models download || python -c "from docling.document_converter import DocumentConverter; DocumentConverter()") ; \
    fi

COPY . /app

ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

USER app

CMD ["python", "-m", "mcp_servers.case.server"]
