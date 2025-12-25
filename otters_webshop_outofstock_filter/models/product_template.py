from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Dit vinkje slaan we op (store=True) zodat we er supersnel op kunnen zoeken.
    x_shop_available = fields.Boolean(string="Beschikbaar in Shop", default=True, index=True)

    def _update_shop_availability(self):
        """
        Berekent of het product in de shop mag staan en slaat dit op.
        """
        for product in self:
            # LOGICA:
            # 1. Diensten (Cadeaubonnen) -> Altijd zichtbaar
            # 2. Goederen -> Moeten fysiek én virtueel op voorraad zijn
            if product.type == 'service':
                is_available = True
            else:
                is_available = product.qty_available > 0 and product.virtual_available > 0

            # Alleen schrijven als de status echt verandert (database optimalisatie)
            if product.x_shop_available != is_available:
                product.x_shop_available = is_available