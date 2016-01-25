from json import loads, dumps
import redis
from time import time
import logging

import gevent
from gevent.lock import RLock


from random import choice
from string import digits, letters

from django.conf import settings

redis_connection = redis.StrictRedis(*settings.REDIS_CONNECTION)

PUBSUB_CHANNEL = "ROOM"

LISTEN_TIMEOUT = 10


def generate_id(n):
    return ''.join(choice(digits + letters) for x in xrange(n))

class InvalidSessionId(Exception): 
    pass

class SessionManager(object):

    SESSIONS_VARNAME = "SESSIONS"
    SESSION_MANAGER_CHANNEL = "SESSION_MANAGER"

    def __init__(self):
        self._sessions = {}
        self._read_lock = RLock()
        gevent.spawn(self.orphan_cleaning)

    def __getitem__(self, key):
        return self._sessions[key]

    def __setitem__(self, key, client):
        self._sessions[key] = client

    def disconnect(self, session_id):
        try:
            client = self._sessions.pop(session_id, None)

            self.send_disconnect_client_event(client)
            del client

        except Exception:
            pass

    def get(self, session_id):
        """
        Get the ClientSession with the given session_id while updateing its "last used"
        timestamp.
        """
        try:
            client = self._sessions[session_id]
        except KeyError:
            raise InvalidSessionId(session_id)

        self.keep_alive(session_id)
        return client

    def keep_alive(self, session_id):
        """
        Sets or updates a timestamp for this session_id in a redis sorted set.
        The timestamp works as "last used" time so that a process can easily
        find and remove timedout clients.
        Returns `True` if the timestamp was set, `False` if it was updated.
        """
        return redis_connection.zadd(self.SESSIONS_VARNAME, time(), session_id)

    def create_client(self, name):
        # a unique impossible to guess uid similar to the django session_id 
        session_id = generate_id(16)

        client_data = {'name': name, 'joined': time()}
        client = ClientSession(session_id, client_data)

        self._sessions[session_id] = client
        self.keep_alive(session_id)
        self.send_connect_client_event(client)
        return client

    def send_connect_client_event(self, client):
        event = {
            "type": "connected",
            "client": client.data,
            "msg": "{} connected.".format(client.data['name'])
        }
        redis_connection.publish(PUBSUB_CHANNEL, dumps(event))

    def send_disconnect_client_event(self, client):
        event = {
            "type": "disconnect",
            "client": client.data,
            "msg": "{} disconnected.".format(client.data['name'])
        }
        redis_connection.publish(PUBSUB_CHANNEL, dumps(event))


    def send_beep(self, client):
        event = {
            "type": "beep",
            "client": client.data,
            "msg": "{} beeped!".format(client.data['name'])
        }
        redis_connection.publish(PUBSUB_CHANNEL, dumps(event))


    def orphan_cleaning(self):
        while True:
            self._orphan_cleaning()
            gevent.sleep(5)

    def _orphan_cleaning(self):
        """
        Removes sessions that were not used for a amount of time.
        """
        timeout = time() - 30
        pipe = redis_connection.pipeline()
        pipe.zrangebyscore(self.SESSIONS_VARNAME, '-inf', timeout)
        pipe.zremrangebyscore(self.SESSIONS_VARNAME, '-inf', timeout)
        orphans, deleted = pipe.execute()
        for session_id in orphans:
            self.disconnect(session_id)



session_manager = SessionManager()

class ClientSession(object):
    
    def __init__(self, session_id, data):
        self.data = data
        self.session_id = session_id
        self._unacked = []
        self._pubsub = redis_connection.pubsub()

        self._read_lock = RLock()

        self.start_listen()

    def start_listen(self):
        self._pubsub.subscribe(PUBSUB_CHANNEL)

    def stop_listen(self):
        self._pubsub.unsubscribe(PUBSUB_CHANNEL)
        self._pubsub = None


    def _listen(self):
        while True:
            msg = self._pubsub.get_message()
            if msg:
                if msg['type'] == 'message':
                    with self._read_lock:
                        self._unacked.append({
                            "id": generate_id(6),
                            "data": loads(msg["data"])
                        })
            else:
                break

    def get_messages(self, acks=None):

        if acks:
            with self._read_lock:
                self._unacked = [msg for msg in self._unacked if msg["id"] not in acks]

        stop = time() + LISTEN_TIMEOUT

        self._listen()

        while not self._unacked and time() < stop:
            self._listen()

            gevent.sleep(0.1)

        return self._unacked[:]

