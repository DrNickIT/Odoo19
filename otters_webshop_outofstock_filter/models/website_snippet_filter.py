# -*- coding: utf-8 -*-
import logging
from odoo import models
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

class WebsiteSnippetFilter(models.Model):
    _inherit = 'website.snippet.filter'

    def _render(self, template_key, limit, search_domain, with_sample=False, **post):
        # Bepaal veilig welk model de carrousel probeert op te halen
        model_name = False
        if getattr(self, 'filter_id', False) and self.filter_id:
            model_name = self.filter_id.model_id
        elif getattr(self, 'action_server_id', False) and self.action_server_id:
            model_name = self.action_server_id.model_id.model

        # Als het om een product carrousel gaat, pas de SQL query aan!
        if model_name in ['product.product', 'product.template']:
            shop_domain = [
                ('x_shop_available', '=', True),   # 1. Moet beschikbaar zijn in de shop
                ('type', '!=', 'service')          # 2. Mag GEEN dienst/cadeaubon zijn
            ]

            # Combineer veilig Odoo's bestaande domein met ons aangepaste domein
            search_domain = Domain.AND([search_domain or [], shop_domain])

        # Geef de aangepaste zoekopdracht (met limiet) door aan Odoo
        res = super()._render(template_key, limit, search_domain, with_sample=with_sample, **post)
        return res

    def _filter_records_to_values(self, records, is_sample=False, **kwargs):
        """
        STAP 2: DE PYTHON FILTER
        """
        if records and records._name in ['product.product', 'product.template']:
            # Extra veiligheidsnet voor de zichtbaarheid
            records = records.filtered(
                lambda p: p.sudo().x_shop_available if records._name == 'product.template' else p.sudo().product_tmpl_id.x_shop_available
            )

            # Zorg dat de nieuwste producten als eerste in de carrousel staan
            records = records.sorted(key=lambda p: p.sudo().create_date, reverse=True)

        res = super()._filter_records_to_values(records, is_sample=is_sample, **kwargs)
        return res