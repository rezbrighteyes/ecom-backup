# -*- coding: utf-8 -*-

from . import models
from . import wizard


def _post_init_hook(env):
    query = """
        update product_product set external_api_id = id where external_api_id is null;
    """
    env.cr.execute(query)
