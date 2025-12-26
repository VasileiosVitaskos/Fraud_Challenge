import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Import the Simulation Engine
try:
    from fraud_sim import sim
except ImportError:
    from src.red_team.fraud_sim import sim

load_dotenv()

# --- 1. KEY LOADING SYSTEM ---
api_keys = [val for key, val in os.environ.items() if key.startswith("GEMINI_KEY_")]
if not api_keys:
    single_key = os.getenv("GEMINI_API_KEY")
    api_keys = [single_key] if single_key else []

if not api_keys:
    raise ValueError("No API keys found! Please check your .env file.")

print(f"Loaded {len(api_keys)} API Keys for exhaustive rotation.")

# --- 2. MODEL POOL ---
MODEL_POOL = [
    "gemini-2.5-flash-lite",             
    "gemini-2.0-flash-lite-preview-02-05", 
    "gemini-2.0-flash-lite-001",         
    "gemini-2.5-flash",                  
    "gemini-2.0-flash",                  
]

# --- 3. STRATEGIC BRAIN ---
SYSTEM_INSTRUCTION = """
ROLE: Advanced Red Team Fraud Agent.
GOAL: Launder money efficiently. 

### STRATEGIC PRIORITIES (Strict Order 1-5) ###

1. HARVEST (Aggressive Integration):
   - Trigger: Is ANY bot balance > $700?
   - Action: Select "cash_out".
   - Logic: Extract profit immediately. Don't let huge balances accumulate.

2. EVASION (Emergency):
   - Trigger: Are any bots "banned"?
   - Action: Select "fake_commerce".
   - Logic: Generate noise to confuse the classifier.

3. RESUPPLY (Critical Low Balance):
   - Trigger: Do fewer than 3 bots have > $50?
   - Action: Select "smurf_split".
   - Logic: You cannot layer (mix_chain) if the network is empty. You must add funds first.

4. CHURN (Safe Layering):
   - Trigger: Do 3+ bots have medium funds ($50 - $700)?
   - Action: Select "mix_chain".
   - Logic: The network is healthy enough to mix funds. Blur the trail.

5. TOP-UP (Placement):
   - Trigger: Are bots generally safe (< $500) AND 'fraud_dirty' > 0?
   - Action: Select "smurf_split".
   - Logic: Keep the pipeline full.

### OUTPUT FORMAT (JSON ONLY) ###
{
  "current_phase": "Harvest" | "Evasion" | "Resupply" | "Churn" | "Top-Up",
  "thought_process": "Short strategic reason.",
  "selected_tool": "cash_out" | "fake_commerce" | "mix_chain" | "smurf_split"
}
"""

def get_decision_exhaustive(prompt):
    """
    Tries EVERY model on Key #1. If all fail, switches to Key #2 and repeats.
    """
    for key_index, current_key in enumerate(api_keys):
        temp_client = genai.Client(api_key=current_key)
        
        for model in MODEL_POOL:
            try:
                response = temp_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        system_instruction=SYSTEM_INSTRUCTION
                    )
                )
                return response, model, key_index + 1
            
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    continue 
                else:
                    print(f"Error {model} (Key {key_index+1}): {e}")
                    continue

    return None, None, None

def print_final_report():
    print("\n" + "="*40)
    print("SIMULATION ENDED")
    print("="*40)
    clean_total = sim.users[sim.clean_id]['balance']
    dirty_acct = sim.users[sim.dirty_id]['balance']
    bot_total = sum(d['balance'] for d in sim.users.values() if d['type'] == 'bot')
    total_dirty_left = dirty_acct + bot_total
    
    print(f"MONEY CLEANED:     ${clean_total:,.2f}")
    print(f"STILL DIRTY:       ${total_dirty_left:,.2f}")
    print("="*40)

def play_game():
    print("--- Starting Strategic Fraud Agent (Dynamic Goal Mode) ---")
    print(f"Goal: Clean > $75,000 (Half of starting funds)")
    print(f"Pool: {len(MODEL_POOL)} models x {len(api_keys)} keys.")
    
    # MAX_TURNS set to 100 to give the agent plenty of time
    MAX_TURNS = 100
    
    for turn in range(1, MAX_TURNS + 1):
        print(f"\n--- TURN {turn} ---")
        
        # 1. GET DATA
        bots = [d for d in sim.users.values() if d['type'] == 'bot' and d['state'] == 'active']
        banned_bots = [d for d in sim.users.values() if d['type'] == 'bot' and d['state'] == 'banned']
        max_bot_bal = max(b['balance'] for b in bots) if bots else 0
        bots_with_funds = len([b for b in bots if b['balance'] > 50])

        prompt = f"""
        DATA SNAPSHOT:
        - Dirty Acct: ${sim.users[sim.dirty_id]['balance']:.2f}
        - Clean Acct: ${sim.users[sim.clean_id]['balance']:.2f}
        - Active Bots: {len(bots)}
        - Bots with > $50: {bots_with_funds}
        - Max Bot Balance: ${max_bot_bal:.2f}
        DECISION: Return JSON.
        """

        # 2. CALL AI
        response, used_model, used_key = get_decision_exhaustive(prompt)
        
        if response is None:
            print("CRITICAL: All API keys and models exhausted.")
            print_final_report()
            break 

        try:
            # 3. EXECUTE
            clean_json = response.text.replace('```json', '').replace('```', '')
            decision = json.loads(clean_json)
            
            print(f"Using: Key #{used_key} | {used_model}")
            print(f"Plan:  {decision.get('current_phase')} -> {decision.get('selected_tool').upper()}")
            
            result = sim.execute_instruction(decision)
            print(f"Result: {result}")
            
        except Exception as e:
            print(f"Parse Error: {e}")

        # 4. BACKGROUND NOISE & CHECKS
        sim.generate_background_noise()
        sim.check_for_bans()
        
        # --- CALCULATE TOTALS ---
        cleaned_amount = sim.users[sim.clean_id]['balance']
        dirty_acct_bal = sim.users[sim.dirty_id]['balance']
        active_bot_bal = sum(d['balance'] for d in sim.users.values() if d['type'] == 'bot' and d['state'] == 'active')
        
        # Total "Playable" Money Remaining (Clean + Dirty + Active Bots)
        # We don't count banned bots because that money is gone forever.
        total_remaining_equity = cleaned_amount + dirty_acct_bal + active_bot_bal

        # --- STATUS REPORT (Every 10 Turns) ---
        if turn % 10 == 0:
            print(f"\n--- ROUND {turn} STATUS REPORT ---")
            print(f" CLEANED:      ${cleaned_amount:,.2f} / $75,000.00")
            print(f" DIRTY LEFT:   ${(dirty_acct_bal + active_bot_bal):,.2f}")
            print(f" BANNED LOST:  ${(150000 - total_remaining_equity):,.2f}")
            print("   -------------------------------\n")

        # --- WIN CONDITION ---
        if cleaned_amount >= 75000:
            print(f"\n>>> MISSION ACCOMPLISHED <<<")
            print(f"Target Reached: ${cleaned_amount:,.2f} Cleaned in {turn} turns.")
            print_final_report()
            break
            
        # --- LOSS CONDITION (Impossible to win) ---
        # If total money left in the system is less than the goal ($75k), we can never win.
        if total_remaining_equity < 75000:
            print(f"\n>>> MISSION FAILED <<<")
            print(f"Too much money lost to bans. Max possible clean: ${total_remaining_equity:,.2f}")
            print_final_report()
            break

        # --- TIMEOUT CONDITION ---
        if turn == MAX_TURNS:
            print(f"\n>>> TIME OUT ({MAX_TURNS} Turns Reached) <<<")
            print_final_report()
            break
            
        print("Sleep (2s)...") 
        time.sleep(2) 

if __name__ == "__main__":
    play_game()