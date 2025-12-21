import os
from dotenv import load_dotenv

load_dotenv()

class Config:
   REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
   REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
   GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
   TICK_DURATION = 2.0
   TOTAL_TICKS = 200 # 6 lepta demo 
   KEY_TRANSACTIONS = "sim:transactions" # LIST ME OLES TIS SUNALAGES
   KEY_BALANCES = "sim:balances"# AC_1 --> AMOUNT
   KEY_BANNED = "sim:banned"    # SET WITH BANNS    
   KEY_GAME_STATE = "sim:state" # TICK , SCORE , STATUS 
   KEY_IDENTITY = "sim:identity" # H PLHROFORIA POIOS EINAI TI PX AC_1 : FRAUDSTER
