# 🕵️‍♂️ Fraud Simulation: Red Team 🔴 vs Blue Team (Governor) 🔵

A self-contained, adversarial **fraud & money‑laundering simulation game** where strategy, detection, and patience collide.

✨ **What this is**  
- **🔴 Red Team (AI Agent):** Attempts to launder dirty funds using bots, layering, and deception.  
- **🔵 Blue Team (Governor):** Monitors the transaction graph in real time, detecting suspicious patterns and banning accounts.  
- **📡 Redis:** Acts as the central nervous system — streaming transactions and broadcasting alerts.

This project is designed for **research, experimentation, and fun** around:
- Fraud detection logic  
- Adversarial agent behavior  
- Graph‑based pattern analysis  
- Game‑theoretic tradeoffs  

---

## 🗂️ Repository Structure

```
.
├─ src/
│  ├─ blue_team/          # 👮 Detection & Enforcement
│  │  ├─ Governor.py
│  │  └─ send_to_redis.py
│  └─ red_team/           # 🕶️ Adversarial AI
│     ├─ agent_client.py
│     └─ fraud_sim.py
├─ Dockerfile             # 🐳 Containerized runtime
├─ docker-compose.yml     # 🧩 Redis + Simulator
├─ graph_visualizer.py    # 📊 Transaction Network Visualization
├─ requirements.txt
└─ README.md
```

---

## 🔄 System Architecture & Data Flow

1. **🧪 Simulation Engine (`fraud_sim.py`)**
   - Generates civilian background noise
   - Executes Red Team actions (smurfing, layering, cash‑out)

2. **📤 Transaction Logging**
   - Every transaction is written to a Redis Stream:
     - **Stream:** `money_flow`

3. **🧠 Blue Team Analysis**
   - Governor ingests recent stream entries
   - Applies graph & topology‑based detection

4. **🚨 Alerts & Enforcement**
   - Alerts pushed to Redis:
     - **List:** `governor:alerts`
   - Simulator bans flagged users and freezes assets

---

## 🏁 Win Conditions

### 🔴 Red Team Victory
- 💰 **Cleaned ≥ $75,000**, OR  
- 🚫 **Blue Team disqualified** (too many false positives)

### 🔵 Blue Team Victory
- ❄️ **Frozen bot assets ≥ $75,000**, OR  
- 🤖 **90%+ of bots banned**

### ⚠️ Automatic Blue Team Disqualification
- ❌ **10 False Positives** (innocent civilians banned)

---

## 🧰 Requirements

### 🖥️ Local Execution
- Python **3.10+**
- Redis (local or containerized)
- Python dependencies:
```bash
pip install -r requirements.txt
```

### 🐳 Docker (Recommended)
- Docker
- Docker Compose

---

## 🔐 Environment Variables

Create a `.env` file at project root:

```bash
REDIS_HOST=redis
REDIS_PORT=6379
```

### 🔑 Gemini API Keys (Required)
```bash
# Single key
GEMINI_API_KEY=your_key_here

# OR multiple keys (auto‑rotation)
GEMINI_KEY_1=your_key_here
GEMINI_KEY_2=your_key_here
```

### ⚙️ Optional
```bash
# Print every N rounds
AGENT_PRINT_EVERY=1
```

---

## ▶️ Run the Simulation (Docker)

```bash
docker compose up --build
```

🎬 **What you’ll see**
- Turn‑by‑turn AI decisions
- Civil vs fraud transaction volume
- Bans, freezes & false positives
- Live score tracking

🛑 Stop:
```bash
docker compose down
```

---

## ▶️ Run Locally (No Docker)

1. Start Redis:
```bash
docker run --rm -p 6379:6379 redis:7
```

2. Launch the agent:
```bash
python src/red_team/agent_client.py
```

---

## 📊 Observability & Debugging

Using `redis-cli`:

### 🔔 Governor Alerts
```bash
redis-cli LRANGE governor:alerts 0 10
```

### 🌊 Transaction Stream
```bash
redis-cli XRANGE money_flow - + COUNT 20
```

### 📡 Live Stream Watch
```bash
redis-cli XREAD BLOCK 0 STREAMS money_flow $
```

---

## 🧠 Blue Team: Detection Techniques

The **Governor** (`src/blue_team/Governor.py`) analyzes a rolling time window using:

- 🔁 **Layering Cycles**  
  Topological persistence via `ripser` on transaction distance matrices

- 🐙 **Smurfing / Hub Detection**  
  High‑volume, high‑fan‑out sender behavior

- 🔺 **Triangle / Structuring Motifs**  
  Graph triangle detection via adjacency matrix powers

Flagged users are banned and their balances frozen in‑simulation.

---

## 🕶️ Red Team: Action Arsenal

The Red Team's Agent may choose from:

- 🧳 `smurf_split` — Distribute dirty funds to small bot batches  
- 🔗 `mix_chain` — Layer funds through bot rings  
- 🛒 `fake_commerce` — Create low‑value noise transactions  
- 💸 `cash_out` — Withdraw cycled (cleaned) funds  

🧠 Strategy & policy live inside:
```
src/red_team/agent_client.py
```

---

## ⚠️ Notes & Gotchas

- Redis **must** be reachable by the simulator
- Docker Compose uses hostname `redis`
- Local runs should set:
```bash
REDIS_HOST=localhost
```
- Missing Gemini keys will raise:
```
ValueError: No API keys found!
```

---

## 🧪 Common Commands

Rebuild & run:
```bash
docker compose up --build
```

Full reset:
```bash
docker compose down -v
```
---

✨ *Built to explore the cat‑and‑mouse game between fraudsters and detection systems.*
