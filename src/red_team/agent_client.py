import os
import json
import time
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

# --- OPTIMIZATION 1: SILENCE LOGS ---
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

SYSTEM_INSTRUCTION = """
ROLE: Expert Money Launderer (Red Team AI)
OBJECTIVE: Launder $150,000. Win condition: Clean $75,000.

### CRITICAL UNDERSTANDING ###
You have $150,000 in the dirty account. Even if you only clean $75k, YOU WIN.
Your PRIMARY goal: Transfer ALL $150k from dirty account to bots, then clean it gradually.

### STRATEGIC FRAMEWORK ###

**PHASE 1: PLACEMENT (Empty the Dirty Account)**
GOAL: Move all $150k from dirty account to bots WITHOUT getting caught.

RULES:
1. NEVER smurf to all bots at once - MAXIMUM 3-4 bots per round
2. Send SIGNIFICANT amounts ($5,000 - $15,000 per bot, NOT small $100-300!)
3. You do NOT need to act every round - SKIP when uncertain
4. Spread placement across 10-20 rounds minimum

EXAMPLE PLACEMENT STRATEGY:
- Round 1: SKIP (let civilian noise build)
- Round 2: Smurf $40k to 3 bots ($12k, $15k, $13k)
- Round 3-4: SKIP or fake_commerce (create noise)
- Round 5: Smurf $35k to 3 different bots
- Round 6-8: SKIP + fake_commerce
- Round 9: Smurf remaining $30k to 3 bots
- Round 10+: Dirty account empty ✓

**PHASE 2: LAYERING (Mandatory Cleaning - SLOW & GRADUAL)**
GOAL: Layer ALL smurfed funds gradually over 40-60 rounds to avoid detection.

CRITICAL RULE: 
- ANY bot that received smurf funds MUST go through GRADUAL layering BEFORE cash out!
- NEVER: Smurf → Cash Out (instant detection!)
- ALWAYS: Smurf → SLOW layering (40+ rounds) → Cash Out

GRADUAL LAYERING STRATEGY (40-60 rounds):
1. After smurfing, wait 1-2 rounds
2. Start ALTERNATING pattern:
   - Round N: mix_chain (layers $4k-$6k in small $500-$1000 txs)
   - Round N+1: fake_commerce (creates noise, breaks pattern)
   - Round N+2: mix_chain (continue layering)
   - Round N+3: fake_commerce (more noise)
   - Repeat for 40-60 rounds total

3. NEVER do mix_chain consecutively! Always alternate with fake_commerce
4. Each mix_chain layers only $4k-$6k (looks natural)
5. Total layering time: 40-60 rounds (realistic slow cleaning)
6. Only cash out AFTER 40+ rounds of gradual layering

**PHASE 3: INTEGRATION (Cash Out)**
GOAL: Move cleaned funds to clean account (ONLY after 40+ rounds of layering).

RULES:
1. NEVER cash out before Round 50 (need time for layering!)
2. Only cash out bots that have been through MULTIPLE layering cycles
3. Cash out 1-2 bots at a time MAXIMUM
4. Wait 3-5 rounds between cash out operations

**PHASE 4: EMERGENCY PROTOCOL (If Bans Detected)**
IF any bots get banned:
1. IMMEDIATELY switch to fake_commerce ONLY
2. SKIP for 2-4 rounds (let the graph fill with civilian noise)
3. Reassess: Have more bans happened? If yes, continue skipping
4. If no new bans for 3+ rounds, cautiously resume with small operations

### TOOL USAGE GUIDE ###

**smurf_split**: 
- Use: Transfer dirty money to bots
- When: Dirty account has significant balance (>$30k)
- Frequency: Every 3-5 rounds during placement phase
- Amount: Large amounts ($10k-$15k per bot) to minimize transaction count

**fake_commerce**:
- Use: Create noise, obscure patterns
- When: Before/after smurfing, during layering, emergency situations
- Frequency: Often! This is your camouflage
- Purpose: Makes the transaction graph complex and harder to analyze

**mix_chain**:
- Use: MANDATORY cleaning step between smurf and cash out
- When: After bots receive smurf funds
- Frequency: 2-3 times per batch of smurfed bots
- Purpose: Breaks direct trails from dirty → bot → clean

**cash_out**:
- Use: Final step - move cleaned money to victory
- When: Bot balance > $700 AND has been through layering
- Frequency: 1-2 bots per round, never immediately after smurf
- Condition: Bot must have NO direct connection to recent dirty account activity

**SKIP (return null/wait)**:
- Use: When situation is uncertain, after bans, during cooling periods
- When: Strategic patience is needed
- Frequency: 30-40% of rounds should be skips/fake_commerce
- Purpose: Let civilian noise accumulate, reduce detection risk

### DECISION PRIORITY LOGIC ###

1. IF (Banned_Bots > 0):
   → EMERGENCY: fake_commerce OR skip for 2-4 rounds
   → Reassess after cooling period

2. IF (Dirty_Balance > $50,000):
   → PLACEMENT PHASE
   → Every 3-5 rounds: smurf_split to 3-4 bots (large amounts)
   → Between smurfing: fake_commerce + skip

3. IF (Any_Bot_Has_Unsent_Smurf_Funds):
   → LAYERING PHASE (MANDATORY!)
   → fake_commerce → mix_chain → mix_chain → (wait)
   → NEVER skip layering!

4. IF (Bots_With_Clean_Funds > 0 AND Balance > $700):
   → INTEGRATION PHASE
   → Cash out 1-2 bots that completed layering
   → Wait 3-5 rounds before next cash out

5. ELSE:
   → MAINTENANCE: fake_commerce or skip
   → Build noise, wait for safe opportunity

### STRATEGIC TIMING (Extended Layering Period) ###
- Rounds 1-5: Reconnaissance (fake_commerce, build baseline noise)
- Rounds 5-15: Active placement (smurf 3-4 bots every 3-5 rounds)
- Rounds 15-70: GRADUAL LAYERING (40-60 rounds total!)
  * Alternate: mix_chain → fake_commerce → mix_chain → fake_commerce
  * Each mix_chain: $4k-$6k only (small amounts)
  * NEVER consecutive mix_chain (always break with fake_commerce)
  * This is THE MOST IMPORTANT phase - takes longest!
- Rounds 70-100: Gradual cash out (1-2 bots per 5 rounds)
- Rounds 100+: Final integration + patience

### OUTPUT FORMAT (JSON ONLY) ###
{
  "current_phase": "Reconnaissance" | "Placement" | "Layering" | "Integration" | "Emergency",
  "selected_tool": "smurf_split" | "mix_chain" | "fake_commerce" | "cash_out",
  "parameters": {
    "num_bots": 3,                    // ONLY for smurf_split: how many bots to target
    "amount_range": [10000, 15000]    // ONLY for smurf_split: $ range per bot
  },
  "reasoning": "Brief tactical explanation (max 15 words)"
}

CRITICAL: For smurf_split, ALWAYS include parameters to control batch size and amounts!

EXAMPLES:

1. Placement Phase - Strategic Large Transfer:
{
  "current_phase": "Placement",
  "selected_tool": "smurf_split",
  "parameters": {
    "num_bots": 3,
    "amount_range": [12000, 15000]
  },
  "reasoning": "Emptying dirty account to 3 bots with large amounts"
}

2. Layering Phase:
{
  "current_phase": "Layering",
  "selected_tool": "mix_chain",
  "parameters": {},
  "reasoning": "Breaking transaction trails through bot network"
}

3. Reconnaissance Phase:
{
  "current_phase": "Reconnaissance",
  "selected_tool": "fake_commerce",
  "parameters": {},
  "reasoning": "Building civilian noise baseline"
}

4. Integration Phase:
{
  "current_phase": "Integration",
  "selected_tool": "cash_out",
  "parameters": {},
  "reasoning": "Cashing out layered funds"
}

NOTE: If you decide to SKIP this round, use fake_commerce with empty parameters:
{
  "current_phase": "Reconnaissance",
  "selected_tool": "fake_commerce",
  "parameters": {},
  "reasoning": "Building civilian noise / Letting detection cool down"
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
                    config=types.GenerateContentConfig(response_mime_type="application/json", system_instruction=SYSTEM_INSTRUCTION, safety_settings=safety)
                )
                return res, model, i+1
            except Exception as e:
                err = str(e)
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
    
    # Additional stats
    banned_bots = sum(1 for u, d in sim.users.items() 
                      if d['type'] == 'bot' and d['state'] == 'banned')
    print(f"🤖 BOTS ELIMINATED:      {banned_bots}/{sim.total_bots}")
    print(f"⚠️ FALSE POSITIVES:      {sim.false_positives}")
    
    # Strategic metrics
    dirty_remaining = sim.users[sim.dirty_id]['balance']
    bots_with_funds = sum(1 for u, d in sim.users.items() 
                         if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 0)
    print(f"💼 DIRTY ACCOUNT LEFT:   ${dirty_remaining:,.0f}")
    print(f"🤖 BOTS WITH FUNDS:      {bots_with_funds}")
    print("="*40)

def play_game():
    print("🧹 Resetting Redis...") 
    reset_simulation_data(get_redis_client()) 
    print("✨ STARTING STRATEGIC SIMULATION!")
    print("📊 ENHANCED WIN CONDITIONS:")
    print("   - Red Team: Clean $75k OR survive 200 rounds")
    print("   - Blue Team: Freeze $75k OR ban 90% of bots")
    print("   - Auto-Loss: 10 False Positives = Governor disqualified")
    print("\n🎯 STRATEGIC OBJECTIVE:")
    print("   1. Empty dirty account ($150k) → bots (3-4 at a time)")
    print("   2. Layer funds through mix_chain (MANDATORY)")
    print("   3. Cash out cleaned funds gradually (1-2 bots/round)")
    print("   4. Use fake_commerce for noise & skip when uncertain\n")

    PRINT_EVERY_N_TURNS = int(os.getenv("AGENT_PRINT_EVERY", "1"))
    MAX_TURNS = Config.TOTAL_TICKS
    START_EQ = 150000.0 
    last_model = "-"
    
    # Track smurfed bots for layering requirement
    bots_need_layering = set()
    last_ban_turn = 0

    for turn in range(1, MAX_TURNS + 1):
        # ========== GOVERNOR PRIORITY: Check FIRST ===========
        # Simulate realistic banking: fraud detection has first priority
        sim.generate_background_noise()
        sim.check_for_bans()
        
        # AI Decision Data
        bots = [d for d in sim.users.values() if d["type"] == "bot" and d["state"] == "active"]
        banned = sum(1 for d in sim.users.values() if d["type"] == "bot" and d["state"] == "banned")
        max_bal = max((b["balance"] for b in bots), default=0.0)
        bots_with_cash = sum(1 for b in bots if b["balance"] > 50)
        dirty_balance = sim.users[sim.dirty_id]['balance']
        
        # Check if new bans happened
        if banned > last_ban_turn:
            turns_since_ban = 0
            last_ban_turn = banned
        else:
            turns_since_ban = turn - (last_ban_turn if last_ban_turn > 0 else 0)
        
        # Calculate bots that need layering
        bots_need_cleaning = len(bots_need_layering)
        
        prompt = f"""
TURN {turn}/{MAX_TURNS} - STRATEGIC STATUS:

💰 ACCOUNTS:
- Dirty Account: ${dirty_balance:,.0f} (GOAL: Empty this to bots)
- Clean Account: ${sim.users[sim.clean_id]['balance']:,.0f} (GOAL: Reach $75k)
- Frozen Assets: ${sim.frozen_assets:,.0f}

🧼 LAYERING PROGRESS:
- Total Smurfed: ${sim.total_smurfed:,.0f}
- Total Layered: ${sim.total_layered:,.0f}
- Unlayered: ${sim.total_smurfed - sim.total_layered:,.0f} ({((sim.total_smurfed - sim.total_layered) / sim.total_smurfed * 100) if sim.total_smurfed > 0 else 0:.0f}%)
- Layering Complete: {'YES ✅' if (sim.total_smurfed - sim.total_layered) < 5000 else 'NO ❌ - Keep layering!'}

🤖 BOT NETWORK:
- Active Bots: {len(bots)}/15
- Banned Bots: {banned}
- Bots With Funds (>$50): {bots_with_cash}
- Richest Bot: ${max_bal:.0f}
- Bots Needing Layering: {bots_need_cleaning}

🚨 THREAT ASSESSMENT:
- Recent Bans: {banned} total
- Turns Since Last Ban: {turns_since_ban}
- Detection Risk: {"CRITICAL - Emergency Mode!" if turns_since_ban < 3 and banned > 0 else "HIGH - Be Cautious" if turns_since_ban < 5 else "MEDIUM - Proceed Carefully" if dirty_balance > 100000 else "LOW - Operational"}

📊 PHASE GUIDANCE:
- Current Phase: {"EMERGENCY" if turns_since_ban < 3 and banned > 0 else "PLACEMENT" if dirty_balance > 30000 else "LAYERING" if bots_need_cleaning > 0 else "INTEGRATION" if bots_with_cash > 0 else "RECONNAISSANCE"}
- Recommended Action: {"fake_commerce + SKIP (cool down)" if turns_since_ban < 3 and banned > 0 else "smurf_split (3-4 bots, large amounts)" if dirty_balance > 50000 and turn % 4 == 0 else "mix_chain (clean smurfed funds)" if bots_need_cleaning > 0 else "cash_out (1-2 bots)" if max_bal > 700 else "fake_commerce (build noise)"}

🎯 STRATEGIC REMINDERS:
1. Smurf in BATCHES: 3-4 bots max, large amounts ($10k-$15k each)
2. ALWAYS layer: smurf → fake_commerce → mix_chain → wait → cash_out
3. NEVER: Direct smurf → cash out (instant detection!)
4. Skip when uncertain: fake_commerce counts as a safe skip
5. If banned: Emergency mode - fake_commerce only for 3-5 rounds

DECIDE YOUR NEXT MOVE:
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
            tool = decision.get("selected_tool")
            
            # Track smurfed bots for layering requirement
            if tool == "smurf_split":
                # After smurfing, mark these bots as needing layering
                smurfed_bots = [u for u, d in sim.users.items() 
                               if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 0]
                bots_need_layering.update(smurfed_bots)
            
            elif tool == "mix_chain":
                # After layering, mark bots as cleaned
                # (Remove from needs-layering set after sufficient mixing)
                if (sim.total_smurfed - sim.total_layered) <= 5000:  # All smurfed funds layered
                    bots_need_layering.clear()
                    
            res_msg = sim.execute_instruction(decision)

            if tool == "cash_out":
                # After cash out, remove from layering requirement
                cashed_bots = [u for u, d in sim.users.items() 
                              if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] < 100]
                for bot in cashed_bots:
                    bots_need_layering.discard(bot)
            
            

        # Output
        if turn % PRINT_EVERY_N_TURNS == 0:
            print(f"\n──────────────── [ ROUND {turn:03} ] ────────────────")
            tool = decision.get('selected_tool', 'UNK').upper() if decision else "THINKING"
            reasoning = decision.get('reasoning', '') if decision else ''
            print(f"🤖 AI Action:   {tool} -> {res_msg}")
            if reasoning:
                print(f"💭 Reasoning:   {reasoning}")
            
            sim.end_turn_summary(turn)
            
            cln = sim.users[sim.clean_id]['balance']
            frz = sim.frozen_assets
            left = START_EQ - cln - frz
            dirty_left = sim.users[sim.dirty_id]['balance']
            
            print(f"📊 SCORE:       🔴 Clean: ${cln:,.0f}  |  🔵 Frozen: ${frz:,.0f}  |  ⚫ Left: ${left:,.0f}")
            print(f"💼 STATUS:      Dirty: ${dirty_left:,.0f}  |  Bots Needing Layering: {len(bots_need_layering)}")
            print(f"🧠 Brain:       {last_model}")

        # ========== ENHANCED WIN CONDITIONS ==========
        
        cln = sim.users[sim.clean_id]['balance']
        frz = sim.frozen_assets
        left = START_EQ - cln - frz
        
        # NEW: Blue Team Perfect Win (90% of bots eliminated)
        banned_bots = sum(1 for u, d in sim.users.items() 
                         if d['type'] == 'bot' and d['state'] == 'banned')
        bot_elimination_rate = banned_bots / sim.total_bots if sim.total_bots > 0 else 0
        
        if bot_elimination_rate >= 0.9:
            print(f"\n👮 🎯 BLUE TEAM PERFECT WIN!")
            print(f"Bot Network Destroyed: {banned_bots}/{sim.total_bots} bots eliminated ({bot_elimination_rate*100:.0f}%)")
            print_final_report(START_EQ)
            break
        
        # NEW: Blue Team Catastrophic Failure (Too many False Positives)
        if sim.false_positives >= 10:
            print(f"\n🚫 💥 BLUE TEAM DISQUALIFIED!")
            print(f"REASON: {sim.false_positives} False Positives (limit: 10)")
            print("Too many innocent users banned. Governor system shut down for review.")
            print("\n🎉 RED TEAM WINS BY DEFAULT!")
            print_final_report(START_EQ)
            break
        
        # ORIGINAL: Red Team Wins (Cleaned $75k)
        if cln >= 75000:
            print("\n🎉 RED TEAM WINS!")
            print(f"Successfully laundered ${cln:,.0f}")
            print_final_report(START_EQ)
            break
        
        # ORIGINAL: Blue Team Wins (Frozen $75k)
        if frz >= 75000:
            print("\n👮 BLUE TEAM WINS!")
            print(f"Successfully froze ${frz:,.0f} in fraud assets")
            print_final_report(START_EQ)
            break
        
        # ORIGINAL: Bankrupt (Ran out of money)
        if left < 5000 and cln < 75000:
            print("\n💀 GAME OVER (Bankrupt)")
            print(f"Remaining funds: ${left:,.0f} (too low to continue)")
            print_final_report(START_EQ)
            break
        
        # ========== END WIN CONDITIONS ==========
        
        time.sleep(Config.TICK_DURATION)

if __name__ == "__main__":
    play_game()