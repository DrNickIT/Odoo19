from odoo import models, api
from odoo.fields import Domain

class WebsiteSnippetFilter(models.Model):
    _inherit = 'website.snippet.filter'

    @api.model
    def _get_products(self, mode, context):
        context = context.copy() if context else {}
        current_domain = context.get('search_domain') or []

        # 1. Filter: Gebruik het snelle vinkje
        stock_domain = [('x_shop_available', '=', True)]

        new_domain = Domain.AND([current_domain, stock_domain])
        context['search_domain'] = new_domain

        # 2. Haal producten op
        products = super()._get_products(mode, context)

        # 3. Sortering (Nieuwste eerst, maar Diensten achteraan)
        if products and products._name in ['product.product', 'product.template']:
            products = products.sorted(key=lambda p: p.create_date, reverse=True)
            products = products.sorted(key=lambda p: p.type or '')

        return products

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