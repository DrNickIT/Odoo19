from odoo import models, api
from odoo.fields import Domain
import logging

_logger = logging.getLogger(__name__)

class WebsiteSnippetFilter(models.Model):
    _inherit = 'website.snippet.filter'

    @api.model
    def _get_products(self, mode, context):
        """
        Override de _get_products om de 'Newest Products' snippet aan te passen.
        """
        # 1. Context kopiëren en filter instellen (Uitverkocht verbergen)
        # Dit zorgt ervoor dat de database meteen de juiste items pakt (geen gatenkaas).
        context = context.copy() if context else {}
        current_domain = context.get('search_domain') or []

        # Logica: Laat zien als (Service) OF (Fysiek > 0 EN Virtueel > 0)
        stock_domain = [
            '|',
            ('type', '=', 'service'),
            '&', ('qty_available', '>', 0), ('virtual_available', '>', 0)
        ]

        # Voeg samen met bestaande filters via de veilige Odoo methode
        new_domain = Domain.AND([current_domain, stock_domain])
        context['search_domain'] = new_domain

        # 2. Haal de producten op via de standaard Odoo functie
        # Odoo voert nu de zoekopdracht uit met onze nieuwe filter.
        products = super()._get_products(mode, context)

        # 3. SORTERING TOEPASSEN (Python-side)
        # We hebben nu een lijst met producten (bijv. de 8 nieuwste die op voorraad zijn).
        # Nu schudden we die lijst zodat de diensten (cadeaubonnen) onderaan komen.

        if products and products._name in ['product.product', 'product.template']:
            # Stap A: Sorteer alles op datum (nieuwste eerst)
            # (Dit is meestal al zo, maar we forceren het voor de zekerheid)
            products = products.sorted(key=lambda p: p.create_date, reverse=True)

            # Stap B: Sorteer stabiel op type
            # 'service' begint met een S, 'consu'/'product' met een C of P.
            # Door te sorteren op type (A-Z) komen de Services (S) vanzelf achteraan.
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