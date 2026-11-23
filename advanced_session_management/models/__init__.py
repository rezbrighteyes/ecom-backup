from . import activity_log
from . import login_log
from . import session
from . import models
from . import res_config_settings
from . import edit_value
from . import res_users
# ir_qweb is not loaded on ecom: it monkey-patched http_routing IrQweb only
# to silence a warning, and every storefront page renders through it.
from . import res_device