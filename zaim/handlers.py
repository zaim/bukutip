import datetime
import re
import time
import settings
import django.utils.simplejson as json
from traceback import format_exc
from google.appengine.api import users
from google.appengine.ext import webapp, db
from jinja2 import Environment, FileSystemLoader, MemcachedBytecodeCache

RE_CALLBACK = re.compile(r'^[a-z0-9_\.]+$')


class GqlEncoder(json.JSONEncoder):
    # http://stackoverflow.com/questions/2114659/how-to-serialize-db-model-objects-to-json
    def default(self, obj):
        if hasattr(obj, '__json__'):
            return getattr(obj, '__json__')()

        if isinstance(obj, db.GqlQuery):
            return list(obj)

        elif isinstance(obj, db.Model):
            properties = obj.properties().items()
            output = {}
            for field, value in properties:
                output[field] = getattr(obj, field)
            return output

        elif isinstance(obj, datetime.datetime):
            output = {}
            fields = ['day', 'hour', 'microsecond', 'minute', 'month', 'second', 'year']
            methods = ['ctime', 'isocalendar', 'isoformat', 'isoweekday', 'timetuple']
            for field in fields:
                output[field] = getattr(obj, field)
            for method in methods:
                output[method] = getattr(obj, method)()
            output['epoch'] = time.mktime(obj.timetuple())
            return output

        elif isinstance(obj, datetime.date):
            output = {}
            fields = ['year', 'month', 'day']
            for field in fields:
                output[field] = getattr(obj, field)
            return output

        elif isinstance(obj, time.struct_time):
            return list(obj)

        elif isinstance(obj, users.User):
            output = {}
            methods = ['nickname', 'email', 'auth_domain']
            for method in methods:
                output[method] = getattr(obj, method)()
            return output

        return json.JSONEncoder.default(self, obj)


class JSONHandler(webapp.RequestHandler):
    """Handles requests that returns JSON"""

    def get(self, *args, **kwargs):
        self._output(self._get(*args, **kwargs))

    def post(self, *args, **kwargs):
        self._output(self._post(*args, **kwargs))

    def handle_exception(self, exception, debug_mode):
        err = {"error": str(exception)}
        if debug_mode:
            err['stack_trace'] = format_exc()
        self.response.clear()
        self._output(err)

    def _output(self, obj):
        output = GqlEncoder().encode(obj)
        callback = self.request.get('callback').strip()
        content_type = 'application/json'

        if callback:
            if not RE_CALLBACK.match(callback):
                callback = '_cb'
            output = '%s(%s)' % (callback, output)
            content_type = 'text/javascript'

        self.response.headers['Content-Type'] = content_type
        self.response.out.write(output)

    def _get(self, *args, **kwargs):
        self.error(405)

    def _post(self, *args, **kwargs):
        self.error(405)


class HTMLHandler(webapp.RequestHandler):
    """Handles requests that renders jinja templates
    """
    context_processors = []

    def get(self, *args, **kwargs):
        template, context = self._get(*args, **kwargs)
        if template:
            self.render_to_response(template, context)

    def post(self, *args, **kwargs):
        template, context = self._post(*args, **kwargs)
        if template:
            self.render_to_response(template, context)

    def render_to_response(self, template_name, context=None):
        env = Environment(loader=FileSystemLoader(settings.TEMPLATE_DIRS))
        context = context or {}
        render_context = settings.CONTEXT.copy()
        render_context.update(context)
        for p in HTMLHandler.context_processors:
            p(render_context)
        template = env.get_template(template_name)
        self.response.out.write(template.render(render_context))

    def _get(self, *args, **kwargs):
        self.error(405)

    def _post(self, *args, **kwargs):
        self.error(405)

    @classmethod
    def register_context_processor(cls, processor):
        if callable(processor):
            cls.context_processors.append(processor)
