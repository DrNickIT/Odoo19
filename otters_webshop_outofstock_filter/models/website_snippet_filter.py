from odoo import models, api
from odoo.fields import Domain
import logging

_logger = logging.getLogger(__name__)

class WebsiteSnippetFilter(models.Model):
    _inherit = 'website.snippet.filter'

    @api.model
    def _get_products(self, mode, context):
        """
        Override de _get_products om de SQL-zoekopdracht te beïnvloeden.
        """
        # Context kopiëren
        context = context.copy() if context else {}

        # Haal het bestaande domein op
        current_domain = context.get('search_domain') or []

        # Onze stock-filter: qty > 0 EN virtual > 0
        stock_domain = [('qty_available', '>', 0), ('virtual_available', '>', 0)]

        # Gebruik Domain.AND (Odoo 19+)
        new_domain = Domain.AND([current_domain, stock_domain])

        # Zet terug in context
        context['search_domain'] = new_domain

        return super()._get_products(mode, context)

    def _filter_records_to_values(self, records, is_sample=False, **kwargs):
        """
        De 'Harde Check': Filter de resultaten nog eens na via Python.
        TOEVOEGING: **kwargs om 'res_model' en andere toekomstige argumenten op te vangen.
        """
        if records and records._name in ['product.product', 'product.template']:
            # Filter: behoud alleen als qty > 0 en virtual > 0
            records = records.filtered(lambda p: p.qty_available > 0 and p.virtual_available > 0)

        # Geef kwargs netjes door aan super()
        return super()._filter_records_to_values(records, is_sample=is_sample, **kwargs)