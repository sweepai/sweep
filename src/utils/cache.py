from redis import Redis

# Connect to the Redis server
r = Redis.from_url("rediss://default:AVNS_GmEi8S4YR4cEua3NCUR@sweep-redis-do-user-14125018-0.b.db.ondigitalocean.com:25061")
# Set a value
r.set('foo', 'bar')
# Get a value
value = r.get('foo')
print(value)  # Prints: b'bar'
# Set multiple values
r.mset({"key1": "value1", "key2": "value2"})

# Get multiple values
values = r.mget(["key1", "key2"])
print(values)  # Prints: [b'value1', b'value2']
import pdb; pdb.set_trace()
