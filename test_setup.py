from src.common.redis_client import get_redis_client
try:
   
    r= get_redis_client()
    r.set("msg", "Hello from Vim")
    print("YES DONE: " + r.get("msg"))
except Exception as e:
    print(e)

