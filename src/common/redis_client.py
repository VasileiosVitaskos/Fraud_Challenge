import redis
import sys
import logging

#Όλες οι ρυθμίσεις μας όπως ΧΟΣΤ ΠΟΡΤ απο το CONFIG.PY αυτό το αρχέιο δεν πρέπει να αλλάξει 

from src.common.config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_redis_client():
    try:


        #edw pame na sundethoume decode_repsonses=True epitrepei to reddis na gurnaei str oxi bytes
        client = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                decode_responses=True,
                socket_timeout=5 # An kanei panw apo 5 deuterolepta kane disc
                )

        client.ping()
        logger.info(f"Connected to Redis at {Config.REDIS_HOST}:{Config.REDIS_PORT}")
        return client
    except redis.ConnectionError:
        logger.error("I COULD'T CONNECT TO REDIS.")
        print(f"\n kane kati apo auta:")
        print(f"bara 'docker ps'")
        print(f"check'{Config.REDIS_HOST}'")
        print(f"Sto Docker 'redis-broker'\n")

        sys.exit(1)

def reset_simulation_data(client):

    logger.warning("Cleaning old run data")
    keys_to_delete = [ Config.KEY_TRANSACTIONS, Config.KEY_BALANCES, Config.KEY_BANNED, Config.KEY_GAME_STATE, "sim:identity" ]
    client.delete(*keys_to_delete)
    logget.info("Cleaned ready to run again")
