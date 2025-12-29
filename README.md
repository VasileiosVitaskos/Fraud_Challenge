# Fraud_Challenge

## Overview
This system runs a Red Team fraud simulation alongside a Blue Team (Governor) that detects and bans fraudulent activity using Topological Data Analysis (TDA).

## Architecture
- **Red Team Agent** (`agent_client.py`): AI-powered money laundering simulation
- **Blue Team Governor** (`Governor.py`): Real-time fraud detection using TDA
- **Redis**: Communication channel between red and blue teams
- **Docker**: Containerized environment for the simulation

## Setup Instructions

### 1. Prerequisites
- Docker and Docker Compose installed
- Python 3.10+ (for local testing)
- Redis running (via Docker)

### 2. Environment Variables
Create a `.env` file in the project root:
```bash
# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379

# Gemini API Keys (add multiple for rotation)
GEMINI_KEY_1=your_api_key_here
GEMINI_KEY_2=your_second_api_key_here
GEMINI_KEY_3=your_third_api_key_here
```

## Running the System

### Option 1: Using Docker Compose
```bash
# Build the containers
docker-compose build

# Start both systems
docker-compose up

# Stop everything
docker-compose down
```

### Option 2: Local Development
```bash
# Terminal 1 - Start Redis
docker run -p 6379:6379 redis:7-alpine

# Terminal 2 - Start Governor (Blue Team)
cd src/blue_team
python Governor.py

# Terminal 3 - Start Agent (Red Team)
cd src/red_team
python agent_client.py
```

## How It Works

### Red Team (Attacker)
1. Starts with $150,000 in a "dirty" account
2. Uses AI to decide money laundering strategies:
   - **Smurf Split**: Distribute money across bot accounts
   - **Mix Chain**: Layer transactions through multiple hops
   - **Fake Commerce**: Create legitimate-looking purchases
   - **Cash Out**: Move clean money to final account
3. Goal: Clean at least $75,000 without getting caught

### Blue Team (Defender)
1. Monitors Redis stream for incoming transactions
2. Buffers transactions for analysis
3. Every N transactions, runs TDA analysis:
   - Creates distance matrix based on transaction amounts
   - Uses Ripser to find topological features (cycles)
   - Detects circular money flow patterns (layering)
4. Bans users involved in suspicious patterns
5. Publishes ban commands back to Redis

### Communication Flow
```
Red Team → Redis Stream (money_flow) → Blue Team
Blue Team → Redis Stream (ban_commands) → Red Team
```

## Monitoring

### Check Redis Streams
```bash
# Connect to Redis
docker exec -it <redis-container-id> redis-cli

# View transaction stream
XREAD COUNT 10 STREAMS money_flow 0

# View ban commands
XREAD COUNT 10 STREAMS ban_commands 0
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f red-team
docker-compose logs -f blue-team
```

## Troubleshooting

### Redis Connection Issues
```bash
# Check if Redis is running
docker ps | grep redis

# Test Redis connection
redis-cli ping
```

### Docker Build Issues
```bash
# Clean rebuild
docker-compose down -v
docker-compose build --no-cache
docker-compose up
```
