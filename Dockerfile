FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY .streamlit .streamlit
COPY clean_air clean_air
COPY data data

# The embedding index ships prebuilt in data/; the app rebuilds it only if the
# guidance text or the embedding model changes. Hosts such as Render set PORT.
EXPOSE 8501
CMD streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true --browser.gatherUsageStats=false
