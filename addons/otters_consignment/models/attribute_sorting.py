# -*- coding: utf-8 -*-
from odoo import models, api

class ProductAttribute(models.Model):
    _inherit = 'product.attribute'

    def action_sort_and_cleanup(self):
        """
        MASTER FUNCTIE: Roept zowel sorteren als opruimen aan.
        Handig voor de knop en de Cron Job.
        """
        # 1. Eerst sorteren
        self.action_sort_values()

        # 2. Dan opruimen (lege merken verbergen)
        self.action_hide_empty_brands()

    def action_hide_empty_brands(self):
        """
        MASTER CLEANUP:
        Zorgt dat Attributes (Filters) EN Brands (Pagina's) synchroon lopen met de voorraad.
        Werkt ook als de data al half is aangepast.
        """
        # 1. Stap 1: Verzamel de 'Witte Lijst' (Alles wat online MAG zijn)
        # We zoeken naar producten die Gepubliceerd zijn EN Voorraad hebben.
        valid_products = self.env['product.template'].search([
            ('is_published', '=', True),
            ('qty_available', '>', 0)
        ])

        # We halen alle attribuutwaarden op die in deze producten gebruikt worden.
        # We filteren specifiek op attributen die 'Merk' of 'Brand' heten.
        valid_value_ids = valid_products.mapped('attribute_line_ids').filtered(
            lambda l: l.attribute_id.name in ['Merk', 'Brand']
        ).mapped('value_ids').ids

        # Haal ook de NAMEN op, want otters.brand is gekoppeld op naam, niet op ID
        valid_brand_names = valid_products.mapped('attribute_line_ids').filtered(
            lambda l: l.attribute_id.name in ['Merk', 'Brand']
        ).mapped('value_ids.name')

        # --- DEEL A: UPDATE DE ATTRIBUTEN (Filters) ---
        target_attrs = self.search([('name', 'in', ['Merk', 'Brand'])])
        for attr in target_attrs:
            all_values = attr.value_ids.with_context(active_test=False)

            # 1. Aanzetten wat op de witte lijst staat (maar nu uit staat)
            to_activate = all_values.filtered(lambda v: v.id in valid_value_ids and not v.active)
            if to_activate:
                to_activate.write({'active': True})

            # 2. Uitzetten wat NIET op de witte lijst staat (maar nu aan staat)
            to_archive = all_values.filtered(lambda v: v.id not in valid_value_ids and v.active)
            if to_archive:
                to_archive.write({'active': False})

        # --- DEEL B: UPDATE DE BRANDS (Pagina's) ---
        # Dit doen we los van de attributen, puur op basis van de namenlijst.

        # 1. Alles AANZETTEN wat op de namenlijst staat
        brands_to_publish = self.env['otters.brand'].with_context(active_test=False).search([
            ('name', 'in', valid_brand_names),
            ('is_published', '=', False) # Alleen pakken die nu fout staan
        ])
        if brands_to_publish:
            brands_to_publish.write({'is_published': True})

        # 2. Alles UITZETTEN wat NIET op de namenlijst staat
        brands_to_unpublish = self.env['otters.brand'].with_context(active_test=False).search([
            ('name', 'not in', valid_brand_names),
            ('is_published', '=', True) # Alleen pakken die nu fout staan
        ])
        if brands_to_unpublish:
            brands_to_unpublish.write({'is_published': False})

    def action_sort_values(self):
        numeric_attributes = ['Maat', 'Schoenmaat']
        alpha_attributes = ['Merk', 'Seizoen', 'Geslacht', 'Type']

        for attr in self:
            if attr.name not in numeric_attributes and attr.name not in alpha_attributes:
                continue

            # --- LOGICA 1: NUMERIEK ---
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