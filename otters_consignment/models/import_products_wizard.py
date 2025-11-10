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

    # Mapping van het cijfer uit de CSV naar de hartjes-waarde in Odoo
    CONDITION_MAPPING = {
        '5': '❤️❤️❤️❤️❤️',
        '4': '❤️❤️❤️❤️🤍',
        '3': '❤️❤️❤️🤍🤍',
        '2': '❤️❤️🤍🤍🤍',
        '1': '❤️🤍🤍🤍🤍',
        '0': 'Ongekend',
    }

    # Lijst met kolommen die GEEN kenmerken zijn, maar basis productvelden
    BASE_FIELDS = [
        'name', 'price', 'category', 'condition_number', 'submission_id', 'id', 'default_code',
        'image_url', 'seo_title', 'seo_description', 'website_description'
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
            file_content = base64.b64decode(self.file_data).decode('utf-8')

            # Gebruik puntkomma als delimiter
            csv_data = csv.DictReader(io.StringIO(file_content), delimiter=';')

            products_to_create = []

            all_headers = csv_data.fieldnames
            base_fields_lower = [f.lower() for f in self.BASE_FIELDS]

            # --- START LOOP PER RIJ ---
            for row in csv_data:
                name = row.get('name')
                price_str = row.get('price', '0.0').replace(',', '.') # Vervang komma door punt
                category_name = row.get('category')
                condition_num_str = row.get('condition_number')
                seo_title = row.get('seo_title', '').strip()
                seo_description = row.get('seo_description', '').strip()
                website_description_content = row.get('website_description', '').strip()
                default_code = row.get('code', '').strip()

                if not name:
                    _logger.warning("Rij overgeslagen: geen 'name' gevonden.")
                    continue

                    # Conversie van Prijs
                try:
                    price = float(price_str)
                except ValueError:
                    raise UserError(_("Ongeldige prijs '%s' gevonden voor product '%s'.") % (price_str, name))

                # --- Basis Product Waarden ---
                product_vals = {
                    'name': name,
                    'list_price': price,
                    # Btw-instelling wordt nu extern beheerd, dus taxes_id is hier niet nodig
                    'submission_id': submission.id,
                    'is_published': True,
                    # Correct voor voorraadtracking in een Storable Product
                    'type': 'consu',
                    'is_storable': True,
                    'qty_available': 1,
                    'website_meta_title': seo_title,
                    'website_meta_description': seo_description,
                    'website_description': website_description_content,
                    'default_code': default_code
                }

                # --- Categorieën Verwerking ---
                if category_name:
                    category_name = category_name.strip()
                    category = self.env['product.public.category'].search([('name', '=ilike', category_name)], limit=1)
                    if not category:
                        category = self.env['product.public.category'].create({'name': category_name})

                    product_vals['public_categ_ids'] = [(6, 0, [category.id])]

                # --- DYNAMISCHE ATTRIBUTEN (KENMERKEN) VERWERKING ---
                attribute_lines_commands = []

                # 1. Verwerk de Conditie
                if condition_num_str and condition_num_str in self.CONDITION_MAPPING:
                    val_name = self.CONDITION_MAPPING[condition_num_str]
                    att_name = 'Conditie'
                    self._process_attribute_value(att_name, val_name, attribute_lines_commands)

                # 2. Verwerk alle andere dynamische kolommen
                for header in all_headers:
                    att_name = header.strip()
                    val_name_raw = row.get(header, '').strip()

                    # Controleer: GEEN basisveld & er staat een waarde
                    if att_name.lower() not in base_fields_lower and val_name_raw:

                        # Splits op verticale streep (|)
                        val_names = [v.strip() for v in val_name_raw.split('|') if v.strip()]

                        for val_name in val_names:
                            self._process_attribute_value(att_name, val_name, attribute_lines_commands)

                if attribute_lines_commands:
                    product_vals['attribute_line_ids'] = attribute_lines_commands

                products_to_create.append(product_vals)

            # 3. Creëer de producten
            if products_to_create:
                self.env['product.template'].create(products_to_create)

        except Exception as e:
            raise UserError(_("Fout bij het verwerken van het bestand: %s") % str(e))

        return {'type': 'ir.actions.act_window_close'}

    def _process_attribute_value(self, att_name, val_name, commands_list):
        """ Hulpfunctie om één kenmerknaam en één waarde te zoeken/creëren en aan de commandolijst toe te voegen. """

        # A. Zoek/Creëer het Attribuut
        attribute = self.env['product.attribute'].search([('name', '=ilike', att_name)], limit=1)
        if not attribute:
            attribute = self.env['product.attribute'].create({
                'name': att_name,
                'create_variant': 'no_variant'
            })

        # B. Zoek/Creëer de Attribuutwaarde
        value = self.env['product.attribute.value'].search([
            ('attribute_id', '=', attribute.id),
            ('name', '=ilike', val_name)
        ], limit=1)
        if not value:
            value = self.env['product.attribute.value'].create({
                'name': val_name,
                'attribute_id': attribute.id,
                'sequence': 10,
            })

        # C. Creëer de Commando voor de Attribuut Lijn
        commands_list.append((0, 0, {
            'attribute_id': attribute.id,
            'value_ids': [(6, 0, [value.id])],
        }))
