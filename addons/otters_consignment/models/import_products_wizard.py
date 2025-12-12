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
        'name', 'price', 'category', 'condition_number', 'submission_id', 'id',
        'code', 'default_code', 'interne referentie', 'ref', # Flexibele code namen
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
            # 1. Decodeer het bestand
            file_content = base64.b64decode(self.file_data).decode('utf-8')

            # 2. SLIMME DELIMITER DETECTIE
            # We pakken de eerste regel en kijken of er meer ; of , in staan
            first_line = file_content.split('\n')[0]
            delimiter = ';' if first_line.count(';') > first_line.count(',') else ','

            _logger.info(f"Import Wizard: Gedetecteerde delimiter is '{delimiter}'")

            csv_data = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)

            # 3. Headers normaliseren (strip spaties en BOM karakters zoals \ufeff)
            # Dit fixt het probleem dat 'code' soms '\ufeffcode' is in Excel
            normalized_fieldnames = [x.strip().replace('\ufeff', '') for x in (csv_data.fieldnames or [])]
            csv_data.fieldnames = normalized_fieldnames

            products_to_create = []
            base_fields_lower = [f.lower() for f in self.BASE_FIELDS]

            # --- START LOOP PER RIJ ---
            for row in csv_data:
                # We gebruiken een helper functie om veilig waardes op te halen, ongeacht hoofdletters
                def get_val(key_list):
                    for k in key_list:
                        # Probeer exacte match
                        if k in row and row[k]: return row[k].strip()
                        # Probeer case-insensitive match
                        for header in row.keys():
                            if header.lower() == k.lower() and row[header]:
                                return row[header].strip()
                    return ''

                name = get_val(['name', 'naam', 'titel'])
                if not name: continue # Skip lege rijen

                price_str = get_val(['price', 'prijs', 'verkoopprijs']).replace(',', '.') or '0.0'
                category_name = get_val(['category', 'categorie'])
                condition_num_str = get_val(['condition_number', 'conditie', 'staat'])

                # DE CRUCIALE FIX: Zoek flexibel naar de code
                default_code = get_val(['code', 'default_code', 'interne referentie', 'ref'])

                # Debugging log (zichtbaar in je server logs)
                if not default_code:
                    _logger.warning(f"Geen code gevonden voor product '{name}'. Odoo zal er zelf een genereren.")

                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0

                # --- Basis Product Waarden ---
                product_vals = {
                    'name': name,
                    'list_price': price,
                    'submission_id': submission.id,
                    'is_published': True,
                    'type': 'consu',
                    'is_storable': True,
                    'qty_available': 1,
                    # Hier vullen we de code in. Als deze leeg is (''),
                    # neemt product_template.py het over. Als hij gevuld is, gebruikt Odoo deze.
                    'default_code': default_code
                }

                # --- Categorieën ---
                if category_name:
                    category = self.env['product.public.category'].search([('name', '=ilike', category_name)], limit=1)
                    if not category:
                        category = self.env['product.public.category'].create({'name': category_name})
                    product_vals['public_categ_ids'] = [(6, 0, [category.id])]

                # --- Attributen ---
                attribute_lines_commands = []

                if condition_num_str and condition_num_str in self.CONDITION_MAPPING:
                    val_name = self.CONDITION_MAPPING[condition_num_str]
                    self._process_attribute_value('Conditie', val_name, attribute_lines_commands)

                # Dynamische kolommen
                for header in row.keys():
                    if not header: continue

                    att_name = header.strip().replace('\ufeff', '')
                    val_name_raw = row[header].strip()

                    # Skip als het een basisveld is of leeg
                    if att_name.lower() in base_fields_lower or not val_name_raw:
                        continue

                    # Merk Logica
                    if att_name.lower() in ['merk', 'brand']:
                        brand = self.env['otters.brand'].search([('name', '=ilike', val_name_raw)], limit=1)
                        if not brand:
                            brand = self.env['otters.brand'].create({'name': val_name_raw})
                        product_vals['brand_id'] = brand.id

                    # Attribuut Logica
                    val_names = [v.strip() for v in val_name_raw.split('|') if v.strip()]
                    for val_name in val_names:
                        self._process_attribute_value(att_name, val_name, attribute_lines_commands)

                if attribute_lines_commands:
                    product_vals['attribute_line_ids'] = attribute_lines_commands

                products_to_create.append(product_vals)

            if products_to_create:
                self.env['product.template'].create(products_to_create)

        except Exception as e:
            raise UserError(_("Fout bij het verwerken van het bestand: %s") % str(e))

        return {'type': 'ir.actions.act_window_close'}

    def _process_attribute_value(self, att_name, val_name, commands_list):
        # (Deze hulpfunctie blijft hetzelfde als in de vorige stap)
        attribute = self.env['product.attribute'].search([('name', '=ilike', att_name)], limit=1)
        if not attribute:
            attribute = self.env['product.attribute'].create({'name': att_name, 'create_variant': 'no_variant'})

        value = self.env['product.attribute.value'].search([('attribute_id', '=', attribute.id), ('name', '=ilike', val_name)], limit=1)
        if not value:
            value = self.env['product.attribute.value'].create({'name': val_name, 'attribute_id': attribute.id, 'sequence': 10})

        existing_command = next((x for x in commands_list if x[2]['attribute_id'] == attribute.id), None)
        if existing_command:
            existing_command[2]['value_ids'][0][2].append(value.id)
        else:
            commands_list.append((0, 0, {'attribute_id': attribute.id, 'value_ids': [(6, 0, [value.id])]}))