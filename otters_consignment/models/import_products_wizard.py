# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import csv
import io
import logging

_logger = logging.getLogger(__name__)

class ImportProductsWizard(models.TransientModel):
    _name = 'otters.consignment.import_products_wizard'
    _description = 'Wizard om producten te importeren in een inzending'

    file_data = fields.Binary(string="CSV-bestand", required=True)
    filename = fields.Char(string="Bestandsnaam")

    CONDITION_MAPPING = {
        '5': '❤️❤️❤️❤️❤️',
        '4': '❤️❤️❤️❤️🤍',
        '3': '❤️❤️❤️🤍🤍',
        '2': '❤️❤️🤍🤍🤍',
        '1': '❤️🤍🤍🤍🤍',
        '0': 'Ongekend',
    }

    BASE_FIELDS = [
        'name', 'naam', 'titel',
        'price', 'prijs', 'verkoopprijs',
        'category', 'categorie',
        'condition_number', 'conditie', 'staat',
        'submission_id', 'id',
        'code', 'default_code', 'interne referentie', 'ref',
        'image_url',
        'seo_title', 'meta title',
        'seo_description', 'meta description',
        'website_description', 'omschrijving'
    ]

    def import_products(self):
        """ Leest het CSV-bestand en creëert de producten en hun kenmerken. """
        self.ensure_one()
        submission_id = self.env.context.get('active_id')
        if not submission_id:
            raise UserError(_("Kan de actieve inzending niet vinden."))

        submission = self.env['otters.consignment.submission'].browse(submission_id)

        if not self.filename or not self.filename.lower().endswith('.csv'):
            raise UserError(_("Selecteer a.u.b. een .csv-bestand."))

        try:
            # 1. Decodeer en detecteer delimiter
            file_content = base64.b64decode(self.file_data).decode('utf-8')
            first_line = file_content.split('\n')[0]
            delimiter = ';' if first_line.count(';') > first_line.count(',') else ','

            _logger.info(f"Import Wizard: Gedetecteerde delimiter is '{delimiter}'")

            csv_data = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)

            # Headers normaliseren
            normalized_fieldnames = [x.strip().replace('\ufeff', '') for x in (csv_data.fieldnames or [])]
            csv_data.fieldnames = normalized_fieldnames

            products_to_create = []
            base_fields_lower = [f.lower() for f in self.BASE_FIELDS]

            # --- START LOOP PER RIJ ---
            for row in csv_data:

                # 1. Basis Velden Ophalen (Nu via de nette methode onderaan)
                name = self._get_csv_value(row, ['name', 'naam', 'titel'])
                if not name: continue

                price_str = self._get_csv_value(row, ['price', 'prijs', 'verkoopprijs']).replace(',', '.') or '0.0'
                category_name = self._get_csv_value(row, ['category', 'categorie'])
                condition_num_str = self._get_csv_value(row, ['condition_number', 'conditie', 'staat'])
                default_code = self._get_csv_value(row, ['code', 'default_code', 'interne referentie', 'ref'])

                # SEO & Omschrijving
                seo_title = self._get_csv_value(row, ['seo_title', 'meta title'])
                seo_description = self._get_csv_value(row, ['seo_description', 'meta description'])
                website_description = self._get_csv_value(row, ['website_description', 'omschrijving'])

                try: price = float(price_str)
                except ValueError: price = 0.0

                # 2. Product Values
                product_vals = {
                    'name': name,
                    'list_price': price,
                    'submission_id': submission.id,
                    'is_published': True,
                    'type': 'consu',
                    'is_storable': True,
                    'qty_available': 1,
                    'default_code': default_code,
                    'website_meta_title': seo_title,
                    'website_meta_description': seo_description,
                    'website_description': website_description,
                }

                # 3. Categorieën
                if category_name:
                    category = self.env['product.public.category'].search([('name', '=ilike', category_name)], limit=1)
                    if not category:
                        category = self.env['product.public.category'].create({'name': category_name})
                    product_vals['public_categ_ids'] = [(6, 0, [category.id])]

                # 4. Attributen Verwerken
                attribute_lines_commands = []

                # Conditie
                if condition_num_str and condition_num_str in self.CONDITION_MAPPING:
                    val_name = self.CONDITION_MAPPING[condition_num_str]
                    self._process_attribute_value('Conditie', val_name, attribute_lines_commands)

                # Dynamische kolommen
                for header in row.keys():
                    if not header: continue
                    att_name = header.strip().replace('\ufeff', '')
                    val_name_raw = row[header].strip()

                    if att_name.lower() in base_fields_lower or not val_name_raw:
                        continue

                    # Merk
                    if att_name.lower() in ['merk', 'brand']:
                        brand = self.env['otters.brand'].search([('name', '=ilike', val_name_raw)], limit=1)
                        if not brand: brand = self.env['otters.brand'].create({'name': val_name_raw})
                        product_vals['brand_id'] = brand.id

                    # Kenmerken
                    self._process_attribute_value(att_name, val_name_raw, attribute_lines_commands)

                if attribute_lines_commands:
                    product_vals['attribute_line_ids'] = attribute_lines_commands

                products_to_create.append(product_vals)

            if products_to_create:
                self.env['product.template'].create(products_to_create)

        except Exception as e:
            raise UserError(_("Fout bij het verwerken van het bestand: %s") % str(e))

        return {'type': 'ir.actions.act_window_close'}

    # -------------------------------------------------------------------------
    # HULPFUNCTIES (Nu netjes apart)
    # -------------------------------------------------------------------------

    def _get_csv_value(self, row, key_list):
        """ Zoekt case-insensitive naar een waarde in de CSV rij op basis van een lijst mogelijke headers. """
        for k in key_list:
            # 1. Exacte match in keys
            if k in row and row[k]:
                return row[k].strip()

            # 2. Case-insensitive match in keys
            for header in row.keys():
                if header.lower() == k.lower() and row[header]:
                    return row[header].strip()
        return ''

    def _process_attribute_value(self, att_name, val_string, commands_list):
        """ Verwerkt attributen en maakt APARTE regels aan (bv 122/128 -> 2 lijnen). """
        clean_string = str(val_string).replace('/', '|').replace('&', '|').replace(' en ', '|')
        values = [v.strip() for v in clean_string.split('|') if v.strip()]

        attribute = self.env['product.attribute'].search([('name', '=ilike', att_name)], limit=1)
        if not attribute:
            attribute = self.env['product.attribute'].create({'name': att_name, 'create_variant': 'no_variant'})

        for v in values:
            value = self.env['product.attribute.value'].search([
                ('attribute_id', '=', attribute.id),
                ('name', '=ilike', v)
            ], limit=1)

            if not value:
                value = self.env['product.attribute.value'].create({
                    'name': v,
                    'attribute_id': attribute.id,
                    'sequence': 10
                })

            commands_list.append((0, 0, {
                'attribute_id': attribute.id,
                'value_ids': [(6, 0, [value.id])],
            }))