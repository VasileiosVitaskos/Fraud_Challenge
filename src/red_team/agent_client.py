import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

try:
    from fraud_sim import sim
except ImportError:
    from src.red_team.fraud_sim import sim

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- MODEL POOL ---
MODEL_POOL = [
    "gemini-2.5-flash-lite",             
    "gemini-2.0-flash-lite-preview-02-05", 
    "gemini-2.0-flash-lite-001",         
    "gemini-2.5-flash",                  
    "gemini-2.0-flash",                  
    "gemini-exp-1206",                   
    "gemini-2.0-flash-exp",              
]

SYSTEM_INSTRUCTION = """
ROLE: Advanced Red Team Fraud Agent.
GOAL: Launder $150k from 'fraud_dirty' to 'fraud_clean'.

### DYNAMIC DECISION LOGIC (Follow Priority 1-5) ###

1. CRITICAL RISK (High Balance):
   - Check: Is MAX bot balance > $1,000? 
   - Action: STOP SMURFING. You must select "mix_chain" (to spread funds) or "cash_out" (to exit).
   - Reason: You are exceeding safe limits.

2. EVASION (Bans Detected):
   - Check: Are any bots in 'banned' state?
   - Action: Select "fake_commerce".
   - Reason: You need to generate legitimate-looking traffic to confuse the Governor immediately.

3. INTEGRATION (Cash Out):
   - Check: Do bots have > $500 and are safe?
   - Action: Select "cash_out".

4. LAYERING (Confusion):
   - Check: Do bots have positive balance (but < $500)?
   - Action: Select "mix_chain". 
   - Reason: Keep money moving to avoid stagnation.

5. PLACEMENT (Resupply):
   - Check: Is MAX bot balance < $1,500 AND 'fraud_dirty' > 0?
   - Action: Select "smurf_split".

### OUTPUT FORMAT (JSON ONLY) ###
{
  "current_phase": "Risk Mgmt" | "Evasion" | "Integration" | "Layering" | "Placement",
  "thought_process": "Short strategic reason.",
  "selected_tool": "smurf_split" | "mix_chain" | "fake_commerce" | "cash_out"
}
"""

def get_decision_with_fallback(prompt):
    """
    Tries models in order. Returns (None, None) if ALL fail.
    """
    for model in MODEL_POOL:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    system_instruction=SYSTEM_INSTRUCTION
                )
            )
            return response, model
            
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"⚠️ {model} Exhausted. Switching...")
                continue
            else:
                print(f"❌ Error with {model}: {e}")
                continue

    # If we get here, every single model failed.
    return None, None

def print_final_report():
    print("\n" + "="*40)
    print("SIMULATION STOPPED: RESOURCES EXHAUSTED")
    print("="*40)
    
    # 1. Calculate Clean Money
    clean_total = sim.users[sim.clean_id]['balance']
    
    # 2. Calculate Still Dirty Money (Dirty Account + All Bots)
    dirty_acct = sim.users[sim.dirty_id]['balance']
    
    # Sum up all bots (Active AND Banned)
    bot_total = sum(d['balance'] for d in sim.users.values() if d['type'] == 'bot')
    
    total_dirty_left = dirty_acct + bot_total
    
    print(f"💰 MONEY SUCCESSFULLY CLEANED:  ${clean_total:,.2f}")
    print(f"☢️  MONEY STILL DIRTY:          ${total_dirty_left:,.2f}")
    print(f"    (Source: ${dirty_acct:,.2f} + Bots: ${bot_total:,.2f})")
    print("="*40)

def play_game():
    print("--- Starting Strategic Fraud Agent (Fail-Safe Mode) ---")
    print(f"Model Pool: {len(MODEL_POOL)} models available.")
    
    for turn in range(1, 16):
        print(f"\n--- TURN {turn} ---")
        
        # 1. GET DATA
        bots = [d for d in sim.users.values() if d['type'] == 'bot' and d['state'] == 'active']
        avg_bot_bal = sum(b['balance'] for b in bots) / len(bots) if bots else 0
        max_bot_bal = max(b['balance'] for b in bots) if bots else 0

        prompt = f"""
        DATA SNAPSHOT:
        - Dirty Acct: ${sim.users[sim.dirty_id]['balance']:.2f}
        - Active Bots: {len(bots)}
        - Max Bot Balance: ${max_bot_bal:.2f}
        DECISION: Return JSON.
        """

        # 2. CALL WITH FALLBACK
        response, used_model = get_decision_with_fallback(prompt)
        
        # --- STOP CONDITION ---
        if response is None:
            print("CRITICAL: All models in pool are exhausted.")
            print_final_report()
            break # Exit the loop immediately

        try:
            # 3. EXECUTE
            clean_json = response.text.replace('```json', '').replace('```', '')
            decision = json.loads(clean_json)
            
            print(f"Model Used:   {used_model}")
            print(f"Action:       {decision.get('selected_tool').upper()}")
            
            result = sim.execute_instruction(decision)
            print(f"Result:       {result}")
            
        except Exception as e:
            print(f"Parse Error: {e}")

        # 4. BACKGROUND & CHECKS
        sim.generate_background_noise()
        sim.check_for_bans()
        
        if sim.users[sim.clean_id]['balance'] > 140000:
            print("\n>>> MISSION ACCOMPLISHED <<<")
            print_final_report() # Print stats even on win
            break
            
        print("Short cooling (3s)...") 
        time.sleep(10) 

if __name__ == "__main__":
    play_game()