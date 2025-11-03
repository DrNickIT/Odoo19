from odoo import models
from odoo.fields import Domain

class Website(models.Model):
    _inherit = 'website'

    def sale_product_domain(self):
        """
        Deze methode wordt overgeërfd om de standaard product query aan te passen.
        (Odoo 19 versie)
        """
        # 1. Haal het standaard domein op (bv. 'is_published = True')
        domain = super().sale_product_domain()

        # 2. Zoek naar producten die we willen *verbergen*.
        #    Dit zijn producten die GEEN service zijn EN geen voorraad hebben.
        #    We moeten .sudo() gebruiken omdat de publieke gebruiker
        #    de voorraadvelden niet mag lezen.
        ProductTemplateSudo = self.env['product.template'].sudo()

        out_of_stock_domain = [
            ('type', '!=', 'service'),  # Services negeren we
            '|',                       # OF...
            ('qty_available', '<=', 0),
            ('virtual_available', '<=', 0)
        ]

        # 3. Voer de 'dure' query uit met sudo
        #    We halen alleen de IDs op, dat is alles wat we nodig hebben.
        out_of_stock_product_ids = ProductTemplateSudo.search(out_of_stock_domain).ids

        # 4. Voeg een simpele, veilige 'exclusion' toe aan het hoofddomein.
        #    De publieke gebruiker kan perfect een 'id not in' query uitvoeren.
        if out_of_stock_product_ids:
            exclusion_domain = [('id', 'not in', out_of_stock_product_ids)]
            # Gebruik Domain.AND om de domeinen correct samen te voegen
            return Domain.AND([domain, exclusion_domain])

        # Als er geen producten zonder voorraad zijn, geef gewoon het basisdomein terug
        return domain
