# Mega-Project Backend Package with Starlette compatibility shim

import starlette.routing
_orig_router_init = starlette.routing.Router.__init__

def _compat_router_init(self, routes=None, redirect_slashes=True, default=None, on_startup=None, on_shutdown=None, lifespan=None, **kwargs):
    _orig_router_init(self, routes=routes, redirect_slashes=redirect_slashes, default=default, lifespan=lifespan)
    self.on_startup = on_startup or []
    self.on_shutdown = on_shutdown or []

starlette.routing.Router.__init__ = _compat_router_init
