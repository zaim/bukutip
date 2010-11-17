import settings
from traceback import format_exc
from google.appengine.ext import webapp
from jinja2 import Environment, FileSystemLoader, MemcachedBytecodeCache
from utils import RE_CALLBACK, GqlEncoder


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
    """Handles requests that renders jinja templates"""

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
        template = env.get_template(template_name)
        self.response.out.write(template.render(render_context))

    def _get(self, *args, **kwargs):
        self.error(405)

    def _post(self, *args, **kwargs):
        self.error(405)
