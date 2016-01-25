import logging
import names
from json import loads, dumps

from django.http import HttpResponse
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from sessions import session_manager, InvalidSessionId

logger = logging.getLogger(__name__)


class LongpollingView(View):


    # def __init__(self, *args, **kwargs):
    #     super(LongpollingView, self).__init__(*args, **kwargs)
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(LongpollingView, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            client = session_manager.get(request.META['HTTP_SESSION_ID'])
        except (KeyError, InvalidSessionId):
            name = names.get_full_name()
            client = session_manager.create_client(name)

            return HttpResponse(dumps({"SESSION_ID": client.session_id, "client": client.data}))

        try:
            acks = loads(request.body).get("acks") or []
        except Exception:
            raise Exception(request.body)
            logger.exception(request.body)

            acks = []

        return HttpResponse(dumps({'messages':client.get_messages(acks)}), content_type='application/json')
        
        
class Beep(View):

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(Beep, self).dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            client = session_manager.get(request.META['HTTP_SESSION_ID'])
        except (KeyError, InvalidSessionId):
            return HttpResponse(status_code=400)

        session_manager.send_beep(client)

        return HttpResponse("ok")