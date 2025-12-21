from odoo import models
from odoo.fields import Domain

class Website(models.Model):
    _inherit = 'website'

    def sale_product_domain(self):
        """
        Pas het productdomein aan om uitverkochte producten direct in de SQL-query te filteren.
        Dit is real-time en performant.
        """
        # 1. Haal het standaard domein op (bv. 'is_published = True')
        domain = super().sale_product_domain()

        # 2. Definieer wat we WEL willen zien.
        #    Logica: Een product is zichtbaar als:
        #    (Het is een dienst) OF (Het is fysiek op voorraad EN virtueel op voorraad)
        #
        #    In Odoo Polish Notatie:
        #    ['|', ('type', '=', 'service'), '&', ('qty_available', '>', 0), ('virtual_available', '>', 0)]

        stock_domain = [
            '|',
            ('type', '=', 'service'),        # Laat services altijd zien
            '&',                             # EN... (combineer de volgende twee)
            ('qty_available', '>', 0),       # Fysieke voorraad moet positief zijn
            ('virtual_available', '>', 0)    # Virtuele voorraad (rekening houdend met orders) moet positief zijn
        ]

        # 3. Voeg dit toe aan het bestaande domein.
        #    We gebruiken Domain.AND om zeker te zijn dat we bestaande regels niet overschrijven.
        return Domain.AND([domain, stock_domain])
