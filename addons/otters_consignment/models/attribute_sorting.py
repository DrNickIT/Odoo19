# -*- coding: utf-8 -*-
from odoo import models, api

class ProductAttribute(models.Model):
    _inherit = 'product.attribute'

    def action_sort_values(self):
        """
        Sorteert de waarden van de geselecteerde attributen.
        """
        numeric_attributes = ['Maat', 'Schoenmaat']
        alpha_attributes = ['Merk', 'Seizoen', 'Geslacht', 'Type']

        for attr in self:
            if attr.name not in numeric_attributes and attr.name not in alpha_attributes:
                continue

            # --- LOGICA 1: NUMERIEK (Strikte controle) ---
            if attr.name in numeric_attributes:
                def sort_key_numeric(val):
                    name = val.name.strip()
                    try:
                        return int(name)
                    except ValueError:
                        return 10000

                values = attr.value_ids.filtered(lambda v: v.active)
                sorted_values = sorted(values, key=sort_key_numeric)

                for index, val in enumerate(sorted_values):
                    if val.sequence != index:
                        val.write({'sequence': index})

            # --- LOGICA 2: ALFABETISCH ---
            elif attr.name in alpha_attributes:
                values = attr.value_ids.filtered(lambda v: v.active)
                sorted_values = sorted(values, key=lambda v: v.name.lower())
                for index, val in enumerate(sorted_values):
                    if val.sequence != index:
                        val.write({'sequence': index})