import os
import random
from google import genai
from google.genai import types
from dotenv import load_dotenv
from fraud_sim import sim  # Ensure fraud_sim.py is in the same folder

load_dotenv()

# Setup the Modern Client
# The new SDK handles model routing more reliably
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_ID = "gemini-2.5-flash-lite"

# --- TOOL DEFINITIONS ---

def smurf_split(total_amount: float):
    """Splits money from fraud_dirty into all active bots in random chunks."""
    dirty_data = sim.users[sim.dirty_id]
    if dirty_data['balance'] < total_amount: 
        return "Error: Insufficient funds in dirty account."
    
    active_bots = [uid for uid, d in sim.users.items() if d['type'] == 'bot' and d['state'] == 'active']
    if not active_bots: 
        return "Error: No active bots available."

    actual_distributed = 0
    for bot_id in active_bots:
        # Create a random chunk to make it less predictable
        max_possible = (total_amount / len(active_bots)) * 1.5
        chunk = round(random.uniform(100, max_possible), 2)
        
        if dirty_data['balance'] >= chunk:
            dirty_data['balance'] -= chunk
            sim.users[bot_id]['balance'] += chunk
            actual_distributed += chunk
            
    return f"Success: Distributed ${actual_distributed:.2f} across {len(active_bots)} bots."

def mix_chain(chain_length: int):
    """Moves money through a chain of bots (Layering). Each bot takes 1% commission."""
    eligible = [uid for uid, d in sim.users.items() if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 0]
    if len(eligible) < chain_length: 
        return "Error: Not enough bots with a balance to form a chain."
    
    chain = random.sample(eligible, int(chain_length))
    for i in range(len(chain) - 1):
        sender, receiver = chain[i], chain[i+1]
        amt = sim.users[sender]['balance']
        commission = round(amt * 0.01, 2)
        sim.users[sender]['balance'] = 0
        sim.users[receiver]['balance'] += (amt - commission)
        
    return f"Success: Completed a layering chain of {chain_length} bots."

def fake_commerce():
    """Performs small transfers between active bots to mimic real activity."""
    bots = [uid for uid, d in sim.users.items() if d['type'] == 'bot' and d['state'] == 'active']
    if len(bots) < 2: 
        return "Error: Not enough active bots to simulate commerce."
    
    a, b = random.sample(bots, 2)
    amt = round(random.uniform(10, 50), 2)
    
    if sim.users[a]['balance'] >= amt:
        sim.users[a]['balance'] -= amt
        sim.users[b]['balance'] += amt
        return f"Success: Masked activity with a ${amt} commerce transfer."
    return "Failed: Insufficient bot balance for commerce."

def cash_out():
    """Final Integration: Moves all bot funds > 500 to the fraud_clean account."""
    total = 0
    for uid, d in sim.users.items():
        if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 500:
            bal = d['balance']
            d['balance'] = 0
            sim.users[sim.clean_id]['balance'] += bal
            total += bal
    return f"Success: Integrated ${total:.2f} into the clean account."

# List of tools to pass to the model
tools_list = [smurf_split, mix_chain, fake_commerce, cash_out]

# --- SIMULATION LOOP ---

def play_game():
    print("--- Starting Strategic Fraud Agent Simulation ---")
    
    for turn in range(1, 4):
        print(f"\n--- TURN {turn} ---")
        
        # STRATEGIC FILTER: Filter the users to only show the "Active Game" accounts
        # This ignores civilians to save tokens and focus the AI
        strategic_state = {
            uid: data for uid, data in sim.users.items() 
            if data['type'] in ['fraud_dirty', 'fraud_clean', 'bot']
        }

        # The prompt now asks the agent to look specifically at status/state
        prompt = (
            f"Current Strategic Bank State: {strategic_state}\n"
            "Analyze the 'state' and 'balance' of these accounts. "
            "Choose the most effective tool to move funds toward the clean account "
            "while avoiding accounts marked as 'banned'."
        )

        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=tools_list,
                system_instruction="You are a fraud strategist. Use smurf_split for large dirty sums, "
                                   "mix_chain for layering, and cash_out for integration."
            )
        )
        
        print(f"Agent's Strategy: {response.text}")
        
        # Run the Governor (Detection System) and check for goal completion
        sim.check_for_bans()
        if sim.users[sim.clean_id]['balance'] > 140000:
            print("\nMISSION ACCOMPLISHED: Money has been cleaned.")
            break

if __name__ == "__main__":
    play_game()