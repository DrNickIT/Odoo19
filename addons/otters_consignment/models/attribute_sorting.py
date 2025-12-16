# -*- coding: utf-8 -*-
from odoo import models, api
import re

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

    def action_sort_values(self):
        # Haal ALLE attributen op
        all_attrs = self.search([])

        # Mapping voor S/M/L maten (voor het geval die in 'Maat' voorkomen)
        size_map = {
            'xxs': 1, 'xs': 2, 's': 3, 'm': 4, 'l': 5, 'xl': 6, 'xxl': 7,
            'one size': 100
        }

        for attr in all_attrs:
            # We werken alleen met de actieve waarden
            values = attr.value_ids.filtered(lambda v: v.active)
            attr_name = attr.name.lower()

            # --- LOGICA 1: MAAT & SCHOENMAAT (Numeriek) ---
            if attr_name in ['maat', 'schoenmaat']:
                def sort_key_numeric(val):
                    name = val.name.lower().strip()

                    # 1. Check S/M/L mapping
                    if name in size_map: return size_map[name]

                    # 2. Pak het eerste getal (bv "92" uit "92/98")
                    numbers = re.findall(r'\d+', name)
                    if numbers: return int(numbers[0])

                    # 3. Geen getal? Helemaal achteraan.
                    return 10000

                sorted_values = sorted(values, key=sort_key_numeric)

            # --- LOGICA 2: CONDITIE (Hartjes) ---
            elif attr_name in ['conditie', 'staat']:
                def sort_key_hearts(val):
                    name = val.name
                    if '❤️' in name:
                        # 5 hartjes = sequence 1 (bovenaan)
                        # 1 hartje = sequence 5
                        return 6 - name.count('❤️')
                    return 100 # Geen hartje? Achteraan.

                sorted_values = sorted(values, key=sort_key_hearts)

            # --- LOGICA 3: ALFABETISCH (De Standaard) ---
            else:
                # Case insensitive sorteren
                sorted_values = sorted(values, key=lambda v: v.name.lower())

            # --- TOEPASSEN ---
            # We schrijven de sequence alleen als die veranderd is (performance)
            for index, val in enumerate(sorted_values):
                if val.sequence != index:
                    val.write({'sequence': index})


    def action_hide_empty_brands(self):
        # --- STAP A: WAT MAG ER ONLINE STAAN? (De Witte Lijst) ---
        # Zoek alle producten die Gepubliceerd zijn EN Voorraad hebben
        valid_products = self.env['product.template'].search([
            ('is_published', '=', True),
            ('qty_available', '>', 0)
        ])

        # 1. Verzamel alle gebruikte attribute waarden ID's (Van ALLE attributen)
        valid_value_ids = valid_products.mapped('attribute_line_ids.value_ids').ids

        # 2. Verzamel de gebruikte Merknamen (voor de Brand Pages)
        valid_brand_names = valid_products.mapped('attribute_line_ids').filtered(
            lambda l: l.attribute_id.name in ['Merk', 'Brand']
        ).mapped('value_ids.name')


        # --- STAP B: UPDATE ALLE ATTRIBUTEN (Filters) ---
        # We pakken gewoon ALLE attributen uit het systeem
        all_attrs = self.search([])

        for attr in all_attrs:
            all_values = attr.value_ids.with_context(active_test=False)

            # 1. Aanzetten wat op de witte lijst staat (maar nu uit staat)
            to_activate = all_values.filtered(lambda v: v.id in valid_value_ids and not v.active)
            if to_activate:
                to_activate.write({'active': True})

            # 2. Uitzetten wat NIET op de witte lijst staat (maar nu aan staat)
            to_archive = all_values.filtered(lambda v: v.id not in valid_value_ids and v.active)
            if to_archive:
                to_archive.write({'active': False})


        # --- STAP C: UPDATE DE MERK PAGINA'S (Otters Brands) ---
        # 1. Brands AANZETTEN
        brands_to_publish = self.env['otters.brand'].with_context(active_test=False).search([
            ('name', 'in', valid_brand_names),
            ('is_published', '=', False)
        ])
        if brands_to_publish:
            brands_to_publish.write({'is_published': True})

        # 2. Brands UITZETTEN
        brands_to_unpublish = self.env['otters.brand'].with_context(active_test=False).search([
            ('name', 'not in', valid_brand_names),
            ('is_published', '=', True)
        ])
        if brands_to_unpublish:
            brands_to_unpublish.write({'is_published': False})