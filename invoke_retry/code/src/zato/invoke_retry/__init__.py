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
from zato.server.service import Service

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
        
class _InvokeRetry(Service):
    name = 'zato.labs._invoke-retry'
    
    def _retry(self, remaining):
        
        try:
            response = self.invoke(self.req_bunch.target, *self.req_bunch.args, **self.req_bunch.kwargs)
        except Exception, e:
            msg = _retry_failed_msg(
                (self.req_bunch.retry_repeats-remaining)+1, self.req_bunch.retry_repeats,
                self.req_bunch.target, self.req_bunch.retry_seconds, self.req_bunch.orig_cid, e)
            self.logger.info(msg)
            raise RetryFailed(remaining-1, e)
        else:
            return response
        
    def _notify_callback(self, is_ok):
        callback_request = {
            'ok': is_ok,
            'orig_cid': self.req_bunch.orig_cid,
            'target': self.req_bunch.target,
            'retry_seconds': self.req_bunch.retry_seconds,
            'retry_repeats': self.req_bunch.retry_repeats,
            'context': self.req_bunch.callback_context
        }
        
        self.invoke_async(self.req_bunch.callback, dumps(callback_request))
    
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

            # Reached the limit, warn users in logs, notify callback service and give up.
            else:
                msg = _retry_limit_reached_msg(self.req_bunch.retry_repeats,
                    self.req_bunch.target, self.req_bunch.retry_seconds, self.req_bunch.orig_cid)
                self.logger.warn(msg)
                self._notify_callback(False)

        # Let the callback know it's all good
        else:
            self._notify_callback(True)
    
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
    name = 'zato.labs.invoke-retry'
    
    def _get_retry_settings(self, target, **kwargs):
        async_fallback = kwargs.get('async_fallback')
        callback = kwargs.get('callback')
        callback_context = kwargs.get('callback_context')
        retry_repeats = kwargs.get('retry_repeats')
        retry_seconds = kwargs.get('retry_seconds')
        retry_minutes = kwargs.get('retry_minutes')
        
        if async_fallback:
            items = ('callback', 'retry_repeats')
            for item in items:
                value = kwargs.get(item)
                if not value:
                    msg = 'Could not invoke [{}], {}:[{}] was not given'.format(target, item, value)
                    self.logger.error(msg)
                    raise ValueError(msg)
                
            if retry_seconds and retry_minutes:
                msg = 'Could not invoke [{}], only one of retry_seconds:[{}] and retry_minutes:[{}] can be given'.format(
                    target, retry_seconds, retry_minutes)
                self.logger.error(msg)
                raise ValueError(msg)
            
            if not(retry_seconds or retry_minutes):
                msg = 'Could not invoke [{}], exactly one of retry_seconds:[{}] or retry_minutes:[{}] must be given'.format(
                    target, retry_seconds, retry_minutes)
                self.logger.error(msg)
                raise ValueError(msg)

            try:
                self.server.service_store.name_to_impl_name[callback]
            except KeyError, e:
                msg = 'Service:[{}] does not exist, e:[{}]'.format(callback, format_exc(e))
                self.logger.error(msg)
                raise ValueError(msg)
            
        # Get rid of arguments our superclass doesn't understand
        for item in('async_fallback', 'callback', 'callback_context', 'retry_repeats', 'retry_seconds', 'retry_minutes'):
            kwargs.pop(item, True)
            
        # Note that internally we use seconds only.
        return async_fallback, callback, callback_context, retry_repeats, retry_seconds or retry_minutes * 60, kwargs
    
    def _invoke_async_retry(self, target, retry_repeats, retry_seconds, orig_cid, callback, callback_context, args, kwargs):
        
        # Request to invoke the background service with ..
        retry_request = {
            'target': target,
            'retry_repeats': retry_repeats,
            'retry_seconds': retry_seconds,
            'orig_cid': orig_cid,
            'callback': callback,
            'callback_context': callback_context,
            'args': args,
            'kwargs': kwargs
        }
        
        return self.invoke_async(_InvokeRetry.get_name(), dumps(retry_request))

    def invoke_async_retry(self, target, *args, **kwargs):
        async_fallback, callback, callback_context, retry_repeats, retry_seconds, kwargs = self._get_retry_settings(target, **kwargs)
        return self._invoke_async_retry(target, retry_repeats, retry_seconds, self.cid, callback, callback_context, args, kwargs)
        
    def invoke_retry(self, target, *args, **kwargs):
        async_fallback, callback, callback_context, retry_repeats, retry_seconds, kwargs = self._get_retry_settings(target, **kwargs)
        
        # Let's invoke the service and find out if it works, maybe we don't need
        # to retry anything.
        
        try:
            result = self.invoke(target, *args, **kwargs)
        except Exception, e:
            
            msg = 'Could not invoke:[{}], cid:[{}], e:[{}]'.format(target, self.cid, format_exc(e))
            self.logger.warn(msg)
            
            # How we handle the exception depends on whether the caller wants us
            # to block or prefers if we retry in background.
            if async_fallback:

                # .. invoke the background service and return CID to the caller.
                cid = self._invoke_async_retry(target, retry_repeats, retry_seconds, self.cid, callback, callback_context, args, kwargs)
                raise NeedsRetry(cid, e)

            # We are to block while repeating
            else:
                # Repeat the given number of times sleeping for as many seconds as we are told
                remaining = retry_repeats
                result = None
                
                while remaining > 0:
                    try:
                        result = self.invoke(target, *args, **kwargs)
                    except Exception, e:
                        msg = _retry_failed_msg((retry_repeats-remaining)+1, retry_repeats, target, retry_seconds, self.cid, e)
                        self.logger.info(msg)
                        sleep(retry_seconds)
                        remaining -= 1
                
                # OK, give up now, there's nothing more we can do
                if not result:
                    msg = _retry_limit_reached_msg(retry_repeats, target, retry_seconds, self.cid)
                    self.logger.warn(msg)
                    raise ZatoException(None, msg)
        else:
            # All good, simply return the response
            return result
