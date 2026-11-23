FROM python:3.11-slim

# iproute2 trae "tc", que se usa para simular latencia de red entre nodos
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Se descargan los pesos de GPT-2 en la imagen (~500 MB) para no depender de internet al ejecutar
RUN python -c "from transformers import GPT2LMHeadModel, GPT2TokenizerFast; \
GPT2LMHeadModel.from_pretrained('gpt2'); GPT2TokenizerFast.from_pretrained('gpt2')"

COPY src/ src/
ENV PYTHONPATH=/app/src
