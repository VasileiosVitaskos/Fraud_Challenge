import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

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

# --- KEY LOADING ---
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
    "gemini-2.0-flash",                  
]

# --- 🧠 THE BIG BRAIN IS BACK (DETAILED STRATEGY) ---
SYSTEM_INSTRUCTION = """
ROLE: Expert Money Launderer (Red Team AI).
GOAL: Clean $75,000 without getting caught.

### RULES OF ENGAGEMENT (STRICT) ###

1. **NO PREMATURE CASH OUT**: 
   - You are FORBIDDEN from using "cash_out" unless a bot has > $700. 
   - If bots have $200-$600, you MUST use "mix_chain" to hide the trail.

2. **PLACEMENT (Refill)**:
   - If most bots are empty (< $50), you MUST use "smurf_split".
   - Do not let the network starve.

3. **LAYERING (The Core Job)**:
   - This is the most important phase.
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
  "selected_tool": "smurf_split" | "mix_chain" | "fake_commerce" | "cash_out",
  "reasoning": "Why you chose this based on the logic chain."
}
"""

def get_decision_exhaustive(prompt):
    safety = [types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE")]
    for i, key in enumerate(api_keys):
        client = genai.Client(api_key=key)
        for model in MODEL_POOL:
            try:
                res = client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json", 
                        system_instruction=SYSTEM_INSTRUCTION, 
                        safety_settings=safety,
                        temperature=0.3 # Low temperature = More logical/strict
                    )
                )
                return res, model, i+1
            except Exception as e:
                if "429" in str(e) or "500" in str(e): 
                    print(f"⚠️ Key {i+1} / {model} Error. Switching...")
                    break 
                continue
    return None, None, None

def print_final_report(start_equity):
    print("\n" + "="*40)
    print("🏁 SIMULATION OVER - FINAL AUDIT 🏁")
    print("="*40)
    
    cleaned = sim.users[sim.clean_id]['balance']
    frozen = sim.frozen_assets
    # Η απλή αφαίρεση που ζήτησες:
    remaining_equity = start_equity - cleaned - frozen
    
    print(f"💰 INITIAL EQUITY: ${start_equity:,.2f}")
    print(f"🔴 RED TEAM (Cleaned):   ${cleaned:,.2f}")
    print(f"🔵 BLUE TEAM (Frozen):   ${frozen:,.2f}")
    print(f"⚫ REMAINING / BURNED:   ${remaining_equity:,.2f}")
    print("="*40)

def play_game():
    print("🧹 Resetting Redis...") 
    reset_simulation_data(get_redis_client()) 
    print("✨ STARTING SIMULATION!")

    PRINT_EVERY_N_TURNS = int(os.getenv("AGENT_PRINT_EVERY", "10"))
    MAX_TURNS = Config.TOTAL_TICKS
    
    # Σταθερό αρχικό ποσό για τους υπολογισμούς
    STARTING_EQUITY = 150000.0 
    last_model = "None"

    for turn in range(1, MAX_TURNS + 1):
        if turn == 1 or turn % PRINT_EVERY_N_TURNS == 0:
            print(f"\n--- TURN {turn} ---")

        # --- DATA SNAPSHOT ---
        bots = [d for d in sim.users.values() if d["type"] == "bot" and d["state"] == "active"]
        banned_bots_count = sum(1 for d in sim.users.values() if d["type"] == "bot" and d["state"] == "banned")
        max_bot_bal = max((b["balance"] for b in bots), default=0.0)
        
        prompt = f"""
        [TURN {turn} STATUS]
        - Dirty Account: ${sim.users[sim.dirty_id]['balance']:.2f}
        - Active Bots: {len(bots)}
        - Banned Bots: {banned_bots_count}
        - Richest Bot: ${max_bot_bal:.2f}
        
        DECISION: Check 'Richest Bot'. If < $50 -> smurf_split. If > $700 -> cash_out. Else -> mix_chain.
        """
        
        res, model, key_idx = get_decision_exhaustive(prompt)
        current_decision = None
        
        if res:
            try:
                current_decision = json.loads(res.text.replace("```json","").replace("```",""))
                last_model = f"{model} (Key {key_idx})"
                print(f"🤖 AI: {current_decision.get('selected_tool', 'UNK').upper()} ({current_decision.get('current_phase')})")
            except: pass

        if current_decision:
            res_msg = sim.execute_instruction(current_decision)
            if turn % PRINT_EVERY_N_TURNS == 0: print(f"Result: {res_msg}")

        sim.generate_background_noise()
        sim.check_for_bans()
        sim.end_turn_summary(turn)

        # --- SCOREBOARD (Η Απλή Αφαίρεση) ---
        cleaned = sim.users[sim.clean_id]['balance']
        frozen = sim.frozen_assets
        # Υπολογισμός υπολοίπου με απλή αφαίρεση
        accounting_left = STARTING_EQUITY - cleaned - frozen

        if turn % PRINT_EVERY_N_TURNS == 0:
            print(f"\n📊 SCOREBOARD (Round {turn})")
            print(f"   🔴 CLEANED:     ${cleaned:,.2f}  (Goal: $75k)")
            print(f"   🔵 FROZEN:      ${frozen:,.2f}  (Limit: $75k)")
            print(f"   ⚫ LEFT/BURNED: ${accounting_left:,.2f}")
            print(f"   🧠 BRAIN:       {last_model}")
            print("   -------------------------------\n")

        # --- GAME OVER CONDITIONS ---
        
        # 1. Red Team Wins
        if cleaned >= 75000:
            print("\n🎉 RED TEAM WINS! (Money Laundered Successfully)")
            print_final_report(STARTING_EQUITY); break
        
        # 2. Blue Team Wins (Frozen > 75k - System Lockdown)
        # Εδώ είναι η αλλαγή που ζήτησες
        if frozen >= 75000:
            print("\n👮 BLUE TEAM WINS! (System Lockdown: Excessive Frozen Assets)")
            print_final_report(STARTING_EQUITY); break
            
        # 3. Bankruptcy (No money left to play)
        # Αν τα λεφτά που έχουν μείνει είναι λιγότερα από 5000€ και δεν έχουμε πιάσει τον στόχο
        if accounting_left < 5000 and cleaned < 75000:
             print("\n💀 GAME OVER (Red Team Bankrupt - No funds left)")
             print_final_report(STARTING_EQUITY); break

        if turn == MAX_TURNS:
            print("\n⏱️ TIME OUT - DRAW")
            print_final_report(STARTING_EQUITY); break
        
        time.sleep(Config.TICK_DURATION)
if __name__ == "__main__":
    play_game()