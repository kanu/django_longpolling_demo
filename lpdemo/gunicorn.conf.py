import os
import sys
from gevent import monkey

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__))))

workers = 1
worker_class = 'gevent'


# bind = '127.0.0.1:8100'
# reload = True


# make sure everything is monkeypatched
def do_post_fork(server, worker):
    monkey.patch_all(thread=False)

post_fork = do_post_fork


