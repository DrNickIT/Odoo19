from odoo import models, http
from odoo.fields import Domain
import logging

_logger = logging.getLogger(__name__)

class Website(models.Model):
    _inherit = 'website'

    def sale_product_domain(self):
        # 1. Haal het basis-domein op (inclusief je 'out-of-stock' filter)
        domain = super().sale_product_domain()

        _logger.info("====== 'sale_product_domain' FILTER IS ACTIEF! ======")

        # 2. PROBEER DE HTTP REQUEST TE PAKKEN
        try:
            # Dit is de 'magische' stap: haal de URL-parameters
            # op uit de globale 'http.request'
            if http.request:
                condition_values = http.request.httprequest.args.getlist('condition_rating')

                if condition_values:
                    _logger.info(f"====== GEVONDEN CONDITIES (vanuit Model): {condition_values} ======")

                    # Voeg de conditie-filter toe aan het domein
                    condition_domain = [('condition_rating', 'in', condition_values)]
                    domain = Domain.AND([domain, condition_domain])

        except Exception as e:
            # Vang fouten op als de 'request' niet beschikbaar is
            # (bv. bij cronjobs of backend-acties)
            _logger.warning(f"Kon condition_rating niet filteren (request niet beschikbaar): {e}")

        # 3. Geef het gecombineerde domein terug
        return domain
