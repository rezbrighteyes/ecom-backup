from datetime import timedelta

from odoo import api, fields, models


class RezaWebsiteCartAttempt(models.Model):
    _name = "reza.website.cart.attempt"
    _description = "Anonymous Website Cart Creation Attempt"
    _order = "create_date desc"

    website_id = fields.Many2one("website", required=True, index=True, ondelete="cascade")
    ip_hash = fields.Char(required=True, index=True)
    product_id = fields.Many2one(
        "product.product", required=True, index=True, ondelete="cascade"
    )

    @api.model
    def check_and_record(
        self, website_id, ip_hash, product_id, hour_limit, day_limit, product_hour_limit
    ):
        now = fields.Datetime.now()
        base_domain = [
            ("website_id", "=", website_id),
            ("ip_hash", "=", ip_hash),
        ]
        hour_domain = base_domain + [("create_date", ">=", now - timedelta(hours=1))]
        hour_count = self.search_count(hour_domain)
        day_count = self.search_count(
            base_domain + [("create_date", ">=", now - timedelta(days=1))]
        )
        product_hour_count = self.search_count(
            hour_domain + [("product_id", "=", product_id)]
        )
        if (
            hour_count >= hour_limit
            or day_count >= day_limit
            or product_hour_count >= product_hour_limit
        ):
            return False
        self.create(
            {
                "website_id": website_id,
                "ip_hash": ip_hash,
                "product_id": product_id,
            }
        )
        return True

    @api.model
    def _cron_remove_old_attempts(self):
        cutoff = fields.Datetime.now() - timedelta(days=2)
        self.search([("create_date", "<", cutoff)]).unlink()
