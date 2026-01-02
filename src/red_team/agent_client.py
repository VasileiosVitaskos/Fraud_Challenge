import os
import json
import time
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

# --- OPTIMIZATION 1: SILENCE LOGS ---
# Κρύβουμε τα μηνύματα των βιβλιοθηκών για καθαρό terminal
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google.ai").setLevel(logging.WARNING)

try:
    from src.common.redis_client import get_redis_client, reset_simulation_data
except ImportError:
    from common.redis_client import get_redis_client, reset_simulation_data
try:
    from src.common.config import Config
except ImportError:
    from common.config import Config
try:
    from fraud_sim import sim
except ImportError:
    from src.red_team.fraud_sim import sim

load_dotenv()

# Key Loading
api_keys = [val for key, val in os.environ.items() if key.startswith("GEMINI_KEY_")]
if not api_keys:
    api_keys = [os.getenv("GEMINI_API_KEY")] if os.getenv("GEMINI_API_KEY") else []
if not api_keys: raise ValueError("No API keys found!")
print(f"Loaded {len(api_keys)} API Keys.")

MODEL_POOL = [
    "gemini-2.5-flash-lite",             
    "gemini-2.0-flash-lite-preview-02-05", 
    "gemini-2.0-flash-lite-001",         
    "gemini-2.5-flash",                  
]

# --- PROMPT (ΔΕΝ ΤΟ ΠΕΙΡΑΖΟΥΜΕ - ΚΡΑΤΑΜΕ ΤΟ "SMART MODE") ---
SYSTEM_INSTRUCTION = """
ROLE: Expert Money Launderer (Red Team AI).
GOAL: Clean $75,000 without getting caught.

### RULES OF ENGAGEMENT (STRICT) ###
1. **NO PREMATURE CASH OUT**: 
   - You are FORBIDDEN from using "cash_out" unless a bot has > $700. 
   - If bots have $200-$600, you MUST use "mix_chain" to hide the trail.

2. **PLACEMENT (Refill)**:
   - If most bots are empty (< $50), you MUST use "smurf_split".

3. **LAYERING (The Core Job)**:
   - If bots have funds ($50 - $700), use "mix_chain" to shuffle money.
   - Use "fake_commerce" occasionally to confuse the Governor.

4. **EMERGENCY DEFENSE**:
   - If "Banned Bots" > 0, switch to "fake_commerce" immediately to generate noise.

### PRIORITY LOGIC CHAIN ###
IF (Banned_Bots > 0) -> RETURN "fake_commerce"
ELSE IF (Max_Bot_Balance > 750) -> RETURN "cash_out"
ELSE IF (Bots_With_Funds < 2) -> RETURN "smurf_split"
ELSE IF (Max_Bot_Balance > 100) -> RETURN "mix_chain"
ELSE -> RETURN "fake_commerce"

### OUTPUT FORMAT (JSON ONLY) ###
{ 
  "current_phase": "Placement" | "Layering" | "Integration" | "Defense", 
  "selected_tool": "smurf_split" | "mix_chain" | "fake_commerce" | "cash_out"
}
"""

def get_decision_exhaustive(prompt):
    safety = [types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE")]
    
    # --- OPTIMIZATION 2: BAM BAM ROTATION ---
    for i, key in enumerate(api_keys):
        client = genai.Client(api_key=key)
        for model in MODEL_POOL:
            try:
                # Χωρίς print logs εδώ, μόνο αποτέλεσμα
                res = client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", system_instruction=SYSTEM_INSTRUCTION, safety_settings=safety)
                )
                return res, model, i+1
            except Exception as e:
                err = str(e)
                # ΑΜΕΣΟ BREAK για να πάει στο επόμενο κλειδί
                if "429" in err or "500" in err: 
                    break 
                continue
    return None, None, None

def print_final_report(start_equity):
    print("\n" + "="*40)
    print("🏁 SIMULATION OVER - FINAL AUDIT 🏁")
    print("="*40)
    cleaned = sim.users[sim.clean_id]['balance']
    frozen = sim.frozen_assets
    rem = start_equity - cleaned - frozen
    
    print(f"💰 INITIAL EQUITY: ${start_equity:,.0f}")
    print(f"🔴 RED TEAM (Cleaned):   ${cleaned:,.0f}")
    print(f"🔵 BLUE TEAM (Frozen):   ${frozen:,.0f}")
    print(f"⚫ REMAINING / BURNED:   ${rem:,.0f}")
    print("="*40)

def play_game():
    print("🧹 Resetting Redis...") 
    reset_simulation_data(get_redis_client()) 
    print("✨ STARTING OPTIMIZED SIMULATION!")

    PRINT_EVERY_N_TURNS = int(os.getenv("AGENT_PRINT_EVERY", "1"))
    MAX_TURNS = Config.TOTAL_TICKS
    START_EQ = 150000.0 
    last_model = "-"

    for turn in range(1, MAX_TURNS + 1):
        # AI Decision Data
        bots = [d for d in sim.users.values() if d["type"] == "bot" and d["state"] == "active"]
        
        # --- FIX: Διόρθωση της παρένθεσης εδώ ---
        banned = sum(1 for d in sim.users.values() if d["type"] == "bot" and d["state"] == "banned")
        # ----------------------------------------
        
        max_bal = max((b["balance"] for b in bots), default=0.0)
        
        # Υπολογίζουμε πόσα bots έχουν λεφτά
        bots_with_cash = sum(1 for b in bots if b["balance"] > 50)
        
        prompt = f"""
        TURN {turn} STATUS:
        - Dirty Acct: ${sim.users[sim.dirty_id]['balance']:.0f}
        - Active Bots: {len(bots)}
        - Banned Bots: {banned}
        - Bots With Cash (> $50): {bots_with_cash}
        - Richest Bot: ${max_bal:.0f}
        
        LOGIC:
        1. IF (Banned > 0) -> "fake_commerce" (Emergency)
        2. IF (Bots With Cash < 2) -> "smurf_split" (Empty wallets? Refill!)
        3. IF (Richest Bot > 800) -> "cash_out" (Profit)
        4. ELSE -> "mix_chain" (Layering)
        """
        
        res, model, kid = get_decision_exhaustive(prompt)
        decision = None
        if res:
            try:
                decision = json.loads(res.text.replace("```json","").replace("```",""))
                last_model = f"{model} (K{kid})"
            except: pass

        # Execute
        res_msg = "Idle"
        if decision:
            res_msg = sim.execute_instruction(decision)

        sim.generate_background_noise()
        sim.check_for_bans()

        # Output
        if turn % PRINT_EVERY_N_TURNS == 0:
            print(f"\n──────────────── [ ROUND {turn:03} ] ────────────────")
            tool = decision.get('selected_tool', 'UNK').upper() if decision else "THINKING"
            print(f"🤖 AI Action:   {tool} -> {res_msg}")
            
            sim.end_turn_summary(turn)
            
            cln = sim.users[sim.clean_id]['balance']
            frz = sim.frozen_assets
            left = START_EQ - cln - frz
            
            print(f"📊 SCORE:       🔴 Clean: ${cln:,.0f}  |  🔵 Frozen: ${frz:,.0f}  |  ⚫ Left: ${left:,.0f}")
            print(f"🧠 Brain:       {last_model}")

        # Win Conditions
        if cln >= 75000:
            print("\n🎉 RED TEAM WINS!"); print_final_report(START_EQ); break
        if frz >= 75000:
            print("\n👮 BLUE TEAM WINS!"); print_final_report(START_EQ); break
        if left < 5000 and cln < 75000:
             print("\n💀 GAME OVER (Bankrupt)"); print_final_report(START_EQ); break
        
        time.sleep(Config.TICK_DURATION)

if __name__ == "__main__":
    play_game()