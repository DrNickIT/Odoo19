# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import zipfile
import io
import logging
import re # Nodig voor flexibele matching

_logger = logging.getLogger(__name__)

class ImageUploadWizard(models.TransientModel):
    _name = 'otters.image.upload.wizard'
    _description = 'Wizard voor bulk upload van productafbeeldingen'

    zip_file = fields.Binary(string="ZIP-bestand met Afbeeldingen", required=True)
    filename = fields.Char(string="Bestandsnaam")

    def upload_images(self):
        """
        Leest een ZIP-bestand, matcht bestanden aan product.template.default_code
        en wijst ze toe als hoofdimage (_1 / (1)) of secundaire images.
        """
        self.ensure_one()

        if not self.filename or not self.filename.lower().endswith('.zip'):
            raise UserError(_("Selecteer a.u.b. een .zip-bestand."))

        # Decode de binaire ZIP-file
        zip_content = base64.b64decode(self.zip_file)

        try:
            with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as z:

                product_updates = {}

                for member in z.infolist():
                    file_name = member.filename

                    # 1. Skip mappen, verborgen of niet-afbeeldingen
                    if member.is_dir() or not re.search(r'\.(jpe?g|png)$', file_name, re.IGNORECASE):
                        continue

                    # 2. Extract de CODE en het nummer
                    code = None
                    index = None

                    # --- Patroon 1: CODE_1.jpg (CODE_VOLGNUMMER.ext) ---
                    match_underscore = re.match(r'(.+?)_(\d+)\.(jpe?g|png)$', file_name, re.IGNORECASE)

                    # --- Patroon 2: CODE (1).jpg (CODE (VOLGNUMMER).ext) ---
                    match_parentheses = re.match(r'(.+?)\s*\((?P<index>\d+)\)\.(jpe?g|png)$', file_name, re.IGNORECASE)

                    if match_underscore:
                        # Haal code en index uit Patroon 1
                        code = match_underscore.group(1).upper().strip()
                        index = int(match_underscore.group(2))

                    elif match_parentheses:
                        # Haal code en index uit Patroon 2
                        code = match_parentheses.group(1).upper().strip()
                        index = int(match_parentheses.group('index'))

                    else:
                        _logger.warning(f"Afbeeldingsnaam {file_name} kon niet gematcht worden aan een geldige conventie (CODE_N.jpg of CODE (N).jpg).")
                        continue

                    # 3. Zoek het product
                    product = self.env['product.template'].search([('default_code', '=ilike', code)], limit=1)
                    if not product:
                        _logger.warning(f"Product met code {code} niet gevonden. Afbeelding {file_name} overgeslagen.")
                        continue

                    # 4. Lees het binaire bestand
                    image_binary = z.read(member)
                    image_base64 = base64.b64encode(image_binary)

                    if product.id not in product_updates:
                        product_updates[product.id] = {'main_image': None, 'secondary_images': [], 'name': product.name}

                    # 5. Bepaal of het hoofd- of secundaire afbeelding is
                    if index == 1:
                        # Index 1 is de hoofdafbeelding (image_1920)
                        product_updates[product.id]['main_image'] = image_base64
                    else:
                        # Index 2 of hoger zijn secundaire afbeeldingen (product.image)
                        product_updates[product.id]['secondary_images'].append({
                            'name': f"{product_updates[product.id]['name']} - {index}",
                            'image_1920': image_base64,
                            'product_tmpl_id': product.id
                        })

                # --- UPDATE DATABASE RECORDS ---

                # A. Creëer Secundaire Afbeeldingen (met sudo om ACL's van portal user te omzeilen)
                new_image_records = []
                for product_id, data in product_updates.items():
                    new_image_records.extend(data['secondary_images'])

                if new_image_records:
                    self.env['product.image'].sudo().create(new_image_records)

                # B. Update Hoofdafbeeldingen
                for product_id, data in product_updates.items():
                    if data['main_image']:
                        # Update de hoofdafbeelding (image_1920) op de product.template
                        self.env['product.template'].browse(product_id).sudo().write({
                            'image_1920': data['main_image']
                        })

        except zipfile.BadZipFile:
            raise UserError(_("Ongeldig ZIP-bestand."))
        except Exception as e:
            _logger.error(f"Fout bij verwerken ZIP: {e}")
            raise UserError(_("Fout bij verwerken ZIP: %s") % str(e))

        return {'type': 'ir.actions.act_window_close'}
