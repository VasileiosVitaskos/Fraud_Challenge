# Χρησιμοποιούμε Python
FROM python:3.10-slim

# Φάκελος εργασίας
WORKDIR /app

# Αντιγραφή requirements.txt πρώτα (για caching)
COPY requirements.txt .

# Εγκατάσταση βιβλιοθηκών από requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Αντιγραφή όλου του κώδικα μέσα στο container
COPY . .

# Ορίζουμε το Python Path
ENV PYTHONPATH=/app

# Ενεργοποίηση unbuffered output για άμεση εμφάνιση logs
ENV PYTHONUNBUFFERED=1

# ΕΝΤΟΛΗ ΕΚΚΙΝΗΣΗΣ: Τρέχουμε το agent_client.py
CMD ["python", "src/red_team/agent_client.py"]