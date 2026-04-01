# No post-install DB view manipulation needed.
# SS exclusion is handled via t-if="website.name != 'Sunglass Superstore'"
# directly in views/product_page.xml at render time.

def post_init_hook(env):
    pass

def post_update_hook(env):
    pass
