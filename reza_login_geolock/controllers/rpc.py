import contextlib
import threading

from odoo.http import request, route

from odoo.addons.rpc.controllers import RPC

THREAD_ATTR = "reza_geolock_rpc_client"


@contextlib.contextmanager
def expose_client():
    """Make the caller's address visible to model code for one RPC call.

    odoo.http.router.dispatch_rpc() takes the request off the stack, so res.users code sees request = None for every
    XML-RPC and JSON-RPC call. The address is parked on the thread for the
    call only and always removed, so a later request on the same worker
    thread can never inherit it."""
    thread = threading.current_thread()
    setattr(thread, THREAD_ATTR, (request.httprequest.remote_addr,
                                  request.httprequest.user_agent.string or ""))
    try:
        yield
    finally:
        if hasattr(thread, THREAD_ATTR):
            delattr(thread, THREAD_ATTR)


class GeolockRPC(RPC):
    """Odoo 20 serves /xmlrpc, /xmlrpc/2 and /jsonrpc from the ``rpc`` addon
    (odoo/addons/rpc/controllers). Both XML-RPC routes go through _xmlrpc()."""

    def _xmlrpc(self, service):
        with expose_client():
            return super()._xmlrpc(service)

    @route()
    def jsonrpc(self, service, method, args):
        with expose_client():
            return super().jsonrpc(service, method, args)
