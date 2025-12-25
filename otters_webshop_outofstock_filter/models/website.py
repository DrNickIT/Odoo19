from odoo import models
from odoo.fields import Domain

class Website(models.Model):
    _inherit = 'website'

    def sale_product_domain(self):
        domain = super().sale_product_domain()

        # NIEUW: Filter op het snelle vinkje
        stock_domain = [('x_shop_available', '=', True)]

        return Domain.AND([domain, stock_domain])