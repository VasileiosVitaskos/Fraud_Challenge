import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

try:
    from src.common.config import Config
except ImportError:
    from common.config import Config

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
print(f"👀 DEBUG: Το πρώτο κλειδί είναι: '{api_keys[0][:10]}...'")

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
    Tries EVERY model on Key #1. If it fails due to Rate Limit, it WAITS.
    Only switches keys on fatal errors or repeated failures.
    """
    # Safety settings (Hardcoded here to ensure they are applied)
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
    ]

    for key_index, current_key in enumerate(api_keys):
        temp_client = genai.Client(api_key=current_key)
        
        for model in MODEL_POOL:
            # Δοκιμάζουμε έως 3 φορές το ΙΔΙΟ μοντέλο/κλειδί αν τρώμε 429 (Busy)
            for attempt in range(3):
                try:
                    response = temp_client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            system_instruction=SYSTEM_INSTRUCTION,
                            safety_settings=safety_settings
                        )
                    )
                    return response, model, key_index + 1
                
                except Exception as e:
                    error_msg = str(e)
                    # Αν είναι θέμα Rate Limit (429) ή Server Overload (500/503)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "500" in error_msg:
                        wait_time = 10 + (attempt * 5) # 10s, 15s, 20s
                        print(f"⏳ API Busy/Limit ({model} - Key {key_index+1}). Cooling down {wait_time}s...")
                        time.sleep(wait_time)
                        continue # Ξαναδοκιμάζουμε (Loop attempt)
                    
                    # Αν είναι άλλο error (π.χ. Invalid Key, Bad Request), πάμε επόμενο μοντέλο
                    print(f"⚠️ Error {model} (Key {key_index+1}): {e}")
                    break # Break attempt loop, go to next model

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
    # ---- CONFIG FOR PRINT SPAM ----
    # Πόσο συχνά να δείχνει "TURN header" + detailed agent logs
    PRINT_EVERY_N_TURNS = int(os.getenv("AGENT_PRINT_EVERY", "10"))  # 5 ή 10 recommended
    SHOW_SLEEP_LINE = os.getenv("SHOW_SLEEP_LINE", "0") == "1"       # default off

    MAX_TURNS = Config.TOTAL_TICKS

    for turn in range(1, MAX_TURNS + 1):

        # Print a turn header only every N turns (smooth terminal)
        if turn == 1 or turn % PRINT_EVERY_N_TURNS == 0:
            print(f"\n--- TURN {turn} ---")

        # 1) GET DATA SNAPSHOT
        bots = [d for d in sim.users.values() if d["type"] == "bot" and d["state"] == "active"]
        max_bot_bal = max((b["balance"] for b in bots), default=0.0)
        bots_with_funds = sum(1 for b in bots if b["balance"] > 50)

        prompt = f"""
        DATA SNAPSHOT:
        - Dirty Acct: ${sim.users[sim.dirty_id]['balance']:.2f}
        - Clean Acct: ${sim.users[sim.clean_id]['balance']:.2f}
        - Active Bots: {len(bots)}
        - Bots with > $50: {bots_with_funds}
        - Max Bot Balance: ${max_bot_bal:.2f}
        DECISION: Return JSON.
        """

        # 2) CALL AI
        response, used_model, used_key = get_decision_exhaustive(prompt)

        if response is None:
            print("CRITICAL: All API keys and models exhausted.")
            print_final_report()
            break

        # 3) EXECUTE DECISION
        decision = None
        result = None
        try:
            clean_json = response.text.replace("```json", "").replace("```", "")
            decision = json.loads(clean_json)

            selected_tool = (decision.get("selected_tool") or "").upper()
            phase = decision.get("current_phase")

            # Print compact agent info only occasionally, or always for important tools
            IMPORTANT_TOOLS = {"CASH_OUT","FAKE_COMMERCE"}
            if (turn == 1) or (turn % PRINT_EVERY_N_TURNS == 0) or (selected_tool in IMPORTANT_TOOLS):
                print(f"Using: Key #{used_key} | {used_model}")
                print(f"Plan:  {phase} -> {selected_tool}")

            result = sim.execute_instruction(decision)

            if (turn == 1) or (turn % PRINT_EVERY_N_TURNS == 0) or (selected_tool in IMPORTANT_TOOLS):
                print(f"Result: {result}")

        except Exception as e:
            print(f"Parse Error: {e}")

        # 4) BACKGROUND NOISE & DEFENSE
        sim.generate_background_noise()
        sim.check_for_bans()

        # 5) END-OF-TURN SUMMARY (1 line)
        sim.end_turn_summary(turn_idx=turn)

        # --- CALCULATE TOTALS ---
        cleaned_amount = sim.users[sim.clean_id]["balance"]
        dirty_acct_bal = sim.users[sim.dirty_id]["balance"]
        active_bot_bal = sum(
            d["balance"] for d in sim.users.values()
            if d["type"] == "bot" and d["state"] == "active"
        )

        total_remaining_equity = cleaned_amount + dirty_acct_bal + active_bot_bal

        # --- STATUS REPORT (Every N Turns) ---
        if turn % PRINT_EVERY_N_TURNS == 0:
            print(f"\n--- ROUND {turn} STATUS REPORT ---")
            print(f" CLEANED:      ${cleaned_amount:,.2f} / $75,000.00")
            print(f" DIRTY LEFT:   ${(dirty_acct_bal + active_bot_bal):,.2f}")
            print(f" BANNED LOST:  ${(150000 - total_remaining_equity):,.2f}")
            print("   -------------------------------\n")

        # --- WIN CONDITION ---
        if cleaned_amount >= 75000:
            print("\n>>> MISSION ACCOMPLISHED <<<")
            print(f"Target Reached: ${cleaned_amount:,.2f} Cleaned in {turn} turns.")
            print_final_report()
            break

        # --- LOSS CONDITION ---
        if total_remaining_equity < 75000:
            print("\n>>> MISSION FAILED <<<")
            print(f"Too much money lost to bans. Max possible clean: ${total_remaining_equity:,.2f}")
            print_final_report()
            break

        # --- TIMEOUT CONDITION ---
        if turn == MAX_TURNS:
            print(f"\n>>> TIME OUT ({MAX_TURNS} Turns Reached) <<<")
            print_final_report()
            break

        # --- SLEEP ---
        if SHOW_SLEEP_LINE:
            print(f"Sleep ({Config.TICK_DURATION}s)...")
        time.sleep(Config.TICK_DURATION)


if __name__ == "__main__":
    play_game()
