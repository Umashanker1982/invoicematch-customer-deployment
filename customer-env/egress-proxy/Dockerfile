FROM python:3.12-slim
RUN useradd --uid 10002 --no-create-home egressproxy
WORKDIR /proxy
COPY proxy.py allowlist.txt ./
USER egressproxy
EXPOSE 3128
HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD python -c "import socket; socket.create_connection(('127.0.0.1', 3128), 2).close()"
CMD ["python", "-u", "proxy.py"]
