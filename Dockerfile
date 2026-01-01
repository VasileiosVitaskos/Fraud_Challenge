
# Χρησιμοποιούμε Python 3.10 slim (ελαφριά έκδοση)
FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
# Φάκελος εργασίας
WORKDIR /app

# --- ΒΗΜΑ 1: Εγκατάσταση Εργαλείων Συστήματος ---
# Το ripser και το scipy χρειάζονται C++ compilers (g++, build-essential)
# για να χτιστούν σωστά στο Linux. Χωρίς αυτά, το pip install θα αποτύχει.
RUN apt-get update && apt-get install -y \
    build-essential \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# --- ΒΗΜΑ 2: Dependencies ---
# Αντιγράφουμε πρώτα ΜΟΝΟ το requirements.txt για να εκμεταλλευτούμε το caching του Docker
COPY requirements.txt .

# Εγκαθιστούμε τα πάντα από το αρχείο
RUN pip install --no-cache-dir -r requirements.txt

# --- ΒΗΜΑ 3: Αντιγραφή Κώδικα ---
# Αντιγραφή όλου του υπόλοιπου project
COPY . .

# Ορίζουμε το Python Path
ENV PYTHONPATH=/app

# ΕΝΤΟΛΗ ΕΚΚΙΝΗΣΗΣ
CMD ["python", "src/red_team/agent_client.py"]
