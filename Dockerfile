FROM python:3.12-slim

RUN pip install --no-cache-dir Pillow==11.1.0

WORKDIR /patterns

ENTRYPOINT ["python", "generate_pattern.py"]
