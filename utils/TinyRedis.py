import redis
import re
import ssl
import os

class Query:
    def __init__(self):
        self._query = {}

    def __getattr__(self, item):
        self._current_key = item
        return self

    def __eq__(self, other):
        self._query[self._current_key] = other
        return self

class TinyRedisDB:
    def __init__(self, db_name=None, url=None):
        url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis = self._connect_via_url(url)
        #self.redis.flushdb()
        self.db_name = db_name or "default_db"

    def _connect_via_url(self, url):
        match = re.match(r'(?P<scheme>rediss?)://((?P<user>[^:]+):(?P<password>[^@]+)@)?(?P<host>[^:]+):(?P<port>\d+)', url)
        if not match:
            raise ValueError("Invalid Redis URL format")
        user, password, host, port, scheme = match.group('user'), match.group('password'), match.group('host'), int(match.group('port')), match.group('scheme')
        ssl_options = {'ssl': True, 'ssl_cert_reqs': ssl.CERT_NONE} if scheme == 'rediss' else {}
        return redis.StrictRedis(host=host, port=port, username=user, password=password, decode_responses=True, **ssl_options) if user and password else redis.StrictRedis(host=host, port=port, decode_responses=True, **ssl_options)

    def insert(self, data):
        record_id = self.redis.incr(f"{self.db_name}:next_id")
        data['_id'] = record_id
        self.redis.hset(f"{self.db_name}:record:{record_id}", mapping=data)
        return record_id

    def update(self, fields, query):
        updated = 0
        for record in self.search(query):
            self.redis.hset(f"{self.db_name}:record:{record['_id']}", mapping=fields)
            updated += 1
        return updated

    def remove(self, query):
        deleted = 0
        for record in self.search(query):
            self.redis.delete(f"{self.db_name}:record:{record['_id']}")
            deleted += 1
        return deleted

    def search(self, query):
        return [record for record in self.all() if self._matches(record, query._query)]

    def get(self, query):
        records = self.search(query)
        return records[0] if records else None

    def all(self):
        return [self.redis.hgetall(key) for key in self.redis.keys(f"{self.db_name}:record:*") if self.redis.type(key) == 'hash']

    def _matches(self, record, query):
        for key, value in query.items():
            record_value = record.get(key)
            if isinstance(value, int):
                if record_value is None or int(record_value) != value:
                    return False
            elif record_value != value:
                return False
        return True
