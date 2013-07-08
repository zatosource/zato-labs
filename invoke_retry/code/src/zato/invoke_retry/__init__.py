# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# stdlib
from traceback import format_exc

# anyjson
from anyjson import dumps, loads

# bunch
from bunch import Bunch

# gevent
from gevent import sleep, spawn, spawn_later

# Zato
from zato.common import ZatoException
from zato.common.util import new_cid
from zato.server.service import Service

retry_repeats = 5
retry_seconds = 1

def _retry_failed_msg(so_far, retry_repeats, service_name, retry_seconds, orig_cid, e):
    return '({}/{}) Retry failed for:[{}], retry_seconds:[{}], orig_cid:[{}], e:[{}]'.format(
        so_far, retry_repeats, service_name, retry_seconds, orig_cid, format_exc(e))

def _retry_limit_reached_msg(retry_repeats, service_name, retry_seconds, orig_cid):
    return '({}/{}) Retry limit reached for:[{}], retry_seconds:[{}], orig_cid:[{}]'.format(
        retry_repeats, retry_repeats, service_name, retry_seconds, orig_cid)

class NeedsRetry(ZatoException):
    def __init__(self, cid, inner_exc):
        self.cid = cid
        self.inner_exc = inner_exc
        
    def __repr__(self):
        return '<{} at {} cid:[{}] inner_exc:[{}]>'.format(
            self.__class__.__name__, hex(id(self)), self.cid, format_exc(self.inner_exc) if self.inner_exc else None)

class RetryFailed(ZatoException):
    def __init__(self, remaining, inner_exc):
        self.remaining = remaining
        self.inner_exc = inner_exc
        
    def __repr__(self):
        return '<{} at {} remaining:[{}] inner_exc:[{}]>'.format(
            self.__class__.__name__, hex(id(self)), self.remaining, format_exc(self.inner_exc) if self.inner_exc else None)
        
class InitialResult(object):
    def __init__(self, ok, result=None, exc=None, cid=None):
        self.ok = ok
        self.result = result
        self.exc = exc
        self.exc_formatted = format_exc(self.exc) if self.exc else ''
        self.cid = cid
        self.retries = 0
        
class _InvokeRetry(Service):
    name = 'zato.labs._invoke-retry'
    
    def _retry(self, remaining):
        
        try:
            response = self.invoke(self.req_bunch.service, *self.req_bunch.args, **self.req_bunch.kwargs)
        except Exception, e:
            msg = _retry_failed_msg(
                (self.req_bunch.retry_repeats-remaining)+1, self.req_bunch.retry_repeats,
                self.req_bunch.service, self.req_bunch.retry_seconds, self.req_bunch.orig_cid, e)
            self.logger.info(msg)
            raise RetryFailed(remaining-1, e)
        else:
            return response
    
    def _on_retry_finished(self, g):
        """ A callback method invoked when a retry finishes. Will decide whether it should be
        attempted to retry the invocation again or give up notifying the uses via callback
        service if retry limit is reached.
        """
        # Was there any exception caught when retrying?
        e = g.exception
        
        if e:
            # Can we retry again?
            if e.remaining:
                g = spawn_later(self.req_bunch.retry_seconds, self._retry, e.remaining)
                g.link(self._on_retry_finished)

            # Reached the limit, warn users in logs, invoke callback service and give up.
            else:
                msg = _retry_limit_reached_msg(self.req_bunch.retry_repeats,
                    self.req_bunch.service, self.req_bunch.retry_seconds, self.req_bunch.orig_cid)
                self.logger.warn(msg)
    
    def handle(self):
        # Convert to bunch so it's easier to read everything
        self.req_bunch = Bunch(loads(self.request.payload))

        # Initial retry linked to a retry callback
        g = spawn(self._retry, self.req_bunch.retry_repeats)
        g.link(self._on_retry_finished)
        
class InvokeRetry(Service):
    """ Provides invoke_retry service that lets one invoke service with parametrized
    retries.
    """
    def _get_retry_settings(self, name, **kwargs):
        async_fallback = kwargs.get('async_fallback')
        callback = kwargs.get('callback')
        callback_data = kwargs.get('callback_data')
        retry_repeats = kwargs.get('retry_repeats')
        retry_seconds = kwargs.get('retry_seconds')
        retry_minutes = kwargs.get('retry_minutes')
        
        if async_fallback:
            items = ('callback', 'retry_repeats')
            for item in items:
                value = kwargs.get(item)
                if not value:
                    msg = 'Could not invoke [{}], {}:[{}] was not given'.format(name, item, value)
                    self.logger.error(msg)
                    raise ValueError(msg)
                
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

            try:
                self.server.service_store.name_to_impl_name[callback]
            except KeyError, e:
                msg = 'Service:[{}] does not exist, e:[{}]'.format(callback, format_exc(e))
                self.logger.error(msg)
                raise ValueError(msg)
            
        # Note that internally we use seconds only.
        return async_fallback, callback, callback_data, retry_repeats, retry_seconds or retry_minutes * 60
        
    def invoke_retry(self, name, *args, **kwargs):
        async_fallback, callback, callback_data, retry_repeats, retry_seconds = self._get_retry_settings(name, **kwargs)
        
        # Get rid of arguments our superclass doesn't understand
        for item in('async_fallback', 'callback', 'callback_data', 'retry_repeats', 'retry_seconds', 'retry_minutes'):
            kwargs.pop(item, True)
            
        # Let's invoke the service and find out if it works, maybe we don't need
        # to retry anything.
        
        try:
            result = self.invoke(name, *args, **kwargs)
        except Exception, e:
            
            msg = 'Could not invoke:[{}], cid:[{}], e:[{}]'.format(name, self.cid, format_exc(e))
            self.logger.warn(msg)
            
            # How we handle the exception depends on whether the caller wants us
            # to block or prefers if we retry in background.
            if async_fallback:
                
                # Request to invoke the background service with ..
                retry_request = {
                    'service': name,
                    'retry_repeats': retry_repeats,
                    'retry_seconds': retry_seconds,
                    'orig_cid': self.cid,
                    'args': args,
                    'kwargs': kwargs
                }
                
                # .. invoke the background service and return CID to the caller.
                cid = self.invoke_async(_InvokeRetry.get_name(), dumps(retry_request))
                raise NeedsRetry(cid, e)

            # We are to block while repeating
            else:
                # Repeat the given number of times sleeping for as many seconds as we are told
                remaining = retry_repeats
                result = None
                
                while remaining > 0:
                    try:
                        result = self.invoke(name, *args, **kwargs)
                    except Exception, e:
                        #msg = '({}/{}) Could not invoke with retry:[{}], retry_seconds:[{}], cid:[{}], e:[{}]'.format(
                        #    (retry_repeats-remaining)+1, retry_repeats, name, retry_seconds, self.cid, format_exc(e))
                        msg = _retry_failed_msg((retry_repeats-remaining)+1, retry_repeats, name, retry_seconds, self.cid, e)
                        self.logger.info(msg)
                        sleep(retry_seconds)
                        remaining -= 1
                
                # OK, give up now, there's nothing more we can do
                if not result:
                    msg = _retry_limit_reached_msg(retry_repeats, name, retry_seconds, self.cid)
                    self.logger.warn(msg)
                    raise ZatoException(None, msg)

        else:
            # All good, simply return the response
            return result

class Callback(Service):
    def handle(self):
        self.logger.info('Callback called')

class BackgroundService(Service):
    x = 0
    def handle(self):
        if self.x == 0:
            self.x += 1
            raise TypeError('zzz')
        else:
            return 'zzz'
        
class Example1(InvokeRetry):
    name = 'zato.labs.invoke-retry.example1'
    def handle(self):
        kwargs = {'retry_repeats':retry_repeats, 'retry_seconds':retry_seconds}
        
        try:
            response = self.invoke_retry('invoke-retry.background-service', **kwargs)
        except Exception, e:
            self.logger.error(format_exc(e))
        
class Example2(InvokeRetry):
    name = 'zato.labs.invoke-retry.example2'
    def handle(self):
        kwargs = {
            'callback':Callback.get_name(),
            'callback_data': {'foo':'bar'},
            'retry_repeats':retry_repeats, 
            'retry_seconds':retry_seconds,
            'async_fallback':True
        }
        
        try:
            response = self.invoke_retry('invoke-retry.background-service', **kwargs)
        except NeedsRetry, e:
            cid = e.cid

class Example3(InvokeRetry):
    name = 'zato.labs.invoke-retry.example3'
    def handle(self):
        kwargs = {
            'callback':Callback.get_name(),
            'callback_data': {'foo':'bar'},
            'retry_repeats':retry_repeats, 
            'retry_seconds':retry_seconds
        }
        
        cid = self.invoke_async_retry('invoke-retry.background-service', **kwargs)
