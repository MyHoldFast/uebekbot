import os
from dotenv import load_dotenv

load_dotenv()

class DB:
    def __init__(self, filepath: str):
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            from utils.TinyRedis import Query, TinyRedisDB
            self.db = TinyRedisDB(url=redis_url, db_name=filepath)
            self.Query = Query
        else:
            from tinydb import Query, TinyDB
            self.db = TinyDB(filepath)
            self.Query = Query

    def get_db(self):
        return self.db, self.Query
