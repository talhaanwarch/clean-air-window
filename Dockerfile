FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY .streamlit .streamlit
COPY clean_air clean_air
COPY data/guidance data/guidance

# The embedding index is built on first use; keep it on a volume so a restart
# does not pay for it again.
ENV INDEX_PATH=/cache/guidance-index.npz
VOLUME /cache

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
