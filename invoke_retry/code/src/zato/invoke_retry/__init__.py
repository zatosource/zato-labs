# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# stdlib
from traceback import format_exc

# gevent
from gevent import sleep, spawn

# Zato
from zato.common import KVDB, ZatoException
from zato.common.util import new_cid
from zato.server.service import Service

# invoker_name, separator, being_invoked_name, separator, original_request_cid
REDIS_KEY_PATTERN = 'zato:retry:{}{}{}{}{}'

class RetryFailed(Exception):
    def __init__(self, remaining):
        self.remaining = remaining
        
class InitialResult(object):
    def __init__(self, ok, result=None, exc=None, cid=None):
        self.ok = ok
        self.result = result
        self.exc = exc
        self.exc_formatted = format_exc(self.exc) if self.exc else ''
        self.cid = cid
        
class InvocationException(ZatoException):
    """ Raised when it was not possible to invoke a resource or service.
    """
    def __init__(self, cid=None, msg=None, inner_exc=None):
        super(InvocationException, self).__init__(cid, msg)
        self.inner_exc = inner_exc
        
    def __repr__(self):
        return '<{} at {} cid:[{}], msg:[{}], inner_exc:[{}]>'.format(
            self.__class__.__name__, hex(id(self)), self.cid, self.msg, format_exc(self.inner_exc) if self.inner_exc else None)
        
class InvokeRetry(Service):
    
    name = 'zato.labs.invoke-retry'
    
    def _get_retry_settings(self, name, **kwargs):
        items = ('callback', 'retry_repeats')
        for item in items:
            value = kwargs.get(item)
            if not value:
                msg = 'Could not invoke [{}], {}:[{}] was not given'.format(name, item, value)
                self.logger.error(msg)
                raise ValueError(msg)

        callback = kwargs.get('callback')
        retry_repeats = kwargs.get('retry_repeats')

        try:
            self.server.service_store.name_to_impl_name[callback]
        except KeyError, e:
            msg = 'Service:[{}] does not exist, e:[{}]'.format(callback, format_exc(e))
            self.logger.error(msg)
            raise ValueError(msg)
            
        retry_seconds = kwargs.get('retry_seconds')
        retry_minutes = kwargs.get('retry_minutes')
        
        if retry_seconds and retry_minutes:
            msg = 'Could not invoke [{}], only one of retry_seconds:[{}] and retry_minutes:[{}] can be given'.format(
                name, retry_seconds, retry_minutes)
            self.logger.error(msg)
            raise ValueError(msg)
        
        if not(retry_seconds or retry_minutes):
            msg = 'Could not invoke [{}], exactly one of retry_seconds:[{}] or retry_minutes:[{}] must be given'.format(
                name, retry_seconds, retry_minutes)
            self.logger.error(msg)
            raise ValueError(msg)
        
        return retry_repeats, retry_seconds or retry_minutes * 60 # Internally we use seconds only
        
    def invoke_retry(self, name, *args, **kwargs):
        retry_repeats, retry_seconds = self._get_retry_settings(name, **kwargs)
        
        # Get rid of arguments our superclass doesn't understand
        for item in('callback', 'retry_repeats', 'retry_seconds', 'retry_minutes'):
            kwargs.pop(item, True)
            
        # Let's invoke the service and find out if it works, maybe we don't need
        # to retry anything.
        try:
            result = self.invoke(name, *args, **kwargs)
        except Exception, e:
            cid = new_cid() # CID .invoke_async will be initially called with
            return InitialResult(False, None, e, cid)
        else:
            # All good, we can just return the result
            return InitialResult(True, result)

class Callback(Service):
    def handle(self):
        self.logger.info('Callback called')

class BackgroundService(Service):
    def handle(self):
        raise TypeError('zzz')
        
class Example(InvokeRetry):
    def handle(self):
        retry_repeats = 5
        retry_seconds = 1
        retry_minutes = 1
        initial = self.invoke_retry('invoke-retry.background-service', callback=Callback.get_name(),
            retry_repeats=retry_repeats, retry_seconds=retry_seconds)
        if initial.ok:
            self.logger.info('OK')
        else:
            self.logger.warn(initial.exc_formatted)

'''
def on_retry_finished(g):
    e = g.exception
    logger.info('Retr finished')
    if e:
        if e.remaining:
            g = gevent.spawn(retry, e.remaining-1)
            g.link(on_retry_finished)
        else:
            logger.warn('Retry limit reached {} {}'.format(e, e.remaining))
    else:
        logger.info('Finished successfully')

def retry(remaining):
    logger.info('Retr 01')
    #gevent.sleep(1)
    raise RetryFailed(remaining)
    logger.info('Retr 02')

# this handler will be run for each incoming connection in a dedicated greenlet
def echo(env, start_response):
    logger.info('Connection')
    
    remaining = 5
    
    g = gevent.spawn(retry, remaining)
    g.link(on_retry_finished)
    
    start_response('200 OK', [('Content-Type', 'text/html')])
    return ["<b>hello world</b>"]

gevent.wsgi.WSGIServer(('', 6000), echo).serve_forever()
'''