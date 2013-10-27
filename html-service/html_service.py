# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# stdlib
from cStringIO import StringIO
from logging import DEBUG

# Django
from django.conf import settings
from django.template import Context, Template

# Zato
from zato.server.service import Service

# Configure Django settings when the module is picked up
if not settings.configured:
    settings.configure()

class HTMLService(Service):
    def generate_payload(self, ctx, template):

        # Generate HTML and return response
        c = Context(ctx)
        t = Template(template)
        payload = t.render(c).encode('utf-8')
        
        self.logger.debug('Ctx:[%s]', ctx)
        self.logger.debug('Payload:[%s]', payload)
        
        if self.logger.isEnabledFor(DEBUG):
            buff = StringIO()
            pprint(ctx, buff)
            self.logger.debug(buff.getvalue())
            buff.close()
        
        self.response.payload = payload
        self.response.content_type = 'text/html; charset=utf-8'
