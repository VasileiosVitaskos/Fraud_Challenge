# Χρησιμοποιούμε Python
FROM python:3.10-slim

# Φάκελος εργασίας
WORKDIR /app

# Εγκατάσταση βιβλιοθηκών (Hardcoded για σιγουριά)
RUN pip install --no-cache-dir google-genai redis python-dotenv

# Αντιγραφή όλου του κώδικα μέσα στο container
COPY . .

# Ορίζουμε το Python Path
ENV PYTHONPATH=/app

# ΕΝΤΟΛΗ ΕΚΚΙΝΗΣΗΣ: Τρέχουμε το agent_client.py
CMD ["python", "src/red_team/agent_client.py"]
