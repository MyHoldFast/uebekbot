import os
import json
import redis
from urllib.parse import urlparse

if os.getenv("MIGRATE"):
    redis_url = os.getenv("REDIS_URL_MIGRATE")
    
    if not redis_url:
        print("Ошибка: переменная окружения REDIS_URL_MIGRATE не установлена.")
        exit(1)
    
    url = urlparse(redis_url)
    
    r = redis.Redis(
        host=url.hostname,
        port=url.port,
        password=url.password if url.password else None,
        ssl=True if url.scheme == "rediss" else False
    )
    
    db_dir = 'db/'
    os.makedirs(db_dir, exist_ok=True) 
    
    for key in r.keys():
        key = key.decode('utf-8')
        if key.endswith('.json'):
            data = r.get(key)
            if data:
                file_path = os.path.join(db_dir, key)
                with open(file_path, 'w') as file:
                    file.write(json.dumps(json.loads(data), indent=4))
                print(f"Data from Redis key {key} has been saved to {file_path}.")
else:
    print("Переменная окружения MIGRATE не установлена.")