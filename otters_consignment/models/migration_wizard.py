# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import csv
import io
import logging
import requests
import time

_logger = logging.getLogger(__name__)

class MigrationWizard(models.TransientModel):
    _name = 'otters.migration.wizard'
    _description = 'Master Migratie Tool'

    # --- INPUT VELDEN ---
    file_customers = fields.Binary(string="1. Klanten (otters_klanten.csv)", required=True)
    filename_customers = fields.Char()

    file_submissions = fields.Binary(string="2. Verzendzakken (otters_verzendzak.csv)", required=True)
    filename_submissions = fields.Char()

    file_products = fields.Binary(string="3. Producten (otters_producten.csv)", required=True)
    filename_products = fields.Char()

    old_site_url = fields.Char(string="Oude Website URL", default="https://www.ottersenflamingos.be")

    def _clean_id(self, value):
        if not value: return False
        try:
            cleaned = str(int(float(str(value).replace(',', '.'))))
            return cleaned
        except:
            return str(value).strip()

    def _update_stock(self, product_tmpl, qty):
        """
        Forceert de voorraad in Odoo via een stock.quant aanpassing.
        Dit is de enige juiste manier voor 'storable' producten.
        """
        try:
            # We hebben de product.product (variant) nodig, niet de template
            product_variant = product_tmpl.product_variant_id
            if not product_variant:
                return

            # Zoek de standaard voorraadlocatie (meestal WH/Stock)
            warehouse = self.env['stock.warehouse'].search([], limit=1)
            location = warehouse.lot_stock_id

            if not location:
                _logger.warning("Geen standaard voorraadlocatie gevonden!")
                return

            # Maak of update de Quant (De voorraadregel)
            self.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': product_variant.id,
                'location_id': location.id,
                'inventory_quantity': float(qty),
            }).action_apply_inventory()

        except Exception as e:
            _logger.warning(f"Kon voorraad niet updaten voor {product_tmpl.name}: {e}")

    def start_migration(self):
        _logger.info("=== START MIGRATIE WIZARD (UPDATE MODUS) ===")

        # STAP 1 & 2 blijven hetzelfde (die slaan we over als ze er al zijn)
        customer_map = self._process_customers()
        submission_map = self._process_submissions(customer_map)

        # STAP 3: PRODUCTEN (Nu met UPDATE logica)
        count = self._process_products(submission_map)
        _logger.info(f"=== PRODUCTEN KLAAR: {count} verwerkt/geupdate ===")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Update Voltooid',
                'message': f'{count} producten zijn bijgewerkt met de juiste stock!',
                'type': 'success',
                'sticky': True,
            }
        }

    # ... _read_csv, _process_customers, _process_submissions blijven ongewijzigd ...
    # KOPIEER DEZE HIERONDER OPNIEUW VOOR DE VOLLEDIGHEID

    def _read_csv(self, binary_data):
        try:
            file_content = base64.b64decode(binary_data).decode('utf-8')
        except UnicodeDecodeError:
            file_content = base64.b64decode(binary_data).decode('latin-1')
        first_line = file_content.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','
        return csv.DictReader(io.StringIO(file_content), delimiter=delimiter)

    def _process_customers(self):
        csv_data = self._read_csv(self.file_customers)
        mapping = {}
        for row in csv_data:
            old_id = self._clean_id(row.get('klant_id'))
            email = row.get('username')
            if not old_id or not email: continue

            # ... (rest van klant logica blijft identiek, update alleen mapping) ...
            domain = ['|', ('email', '=ilike', email.strip()), ('x_old_id', '=', str(old_id))]
            partner = self.env['res.partner'].search(domain, limit=1)

            if not partner:
                # Alleen aanmaken als niet bestaat
                voornaam = row.get('voornaam', '')
                achternaam = row.get('achternaam', '')
                full_name = f"{voornaam} {achternaam}".strip() or email
                partner = self.env['res.partner'].create({
                    'name': full_name, 'email': email,
                    'x_consignment_prefix': f"IMP{old_id}", 'x_old_id': str(old_id)
                })
            mapping[old_id] = partner
        return mapping

    def _process_submissions(self, customer_map):
        csv_data = self._read_csv(self.file_submissions)
        mapping = {}
        for row in csv_data:
            old_bag_id = self._clean_id(row.get('zak_id'))
            old_customer_id = self._clean_id(row.get('KlantId'))
            if not old_bag_id or not old_customer_id: continue

            partner = customer_map.get(old_customer_id)
            if not partner: continue

            domain = ['|', ('name', '=', f"IMPORT-{old_bag_id}"), ('x_old_id', '=', str(old_bag_id))]
            submission = self.env['otters.consignment.submission'].search(domain, limit=1)

            if not submission:
                date = row.get('datum_ontvangen') or fields.Date.today()
                submission = self.env['otters.consignment.submission'].create({
                    'name': f"IMPORT-{old_bag_id}", 'supplier_id': partner.id,
                    'submission_date': date, 'state': 'processing',
                    'payout_method': 'coupon', 'payout_percentage': 0.5,
                    'x_old_id': str(old_bag_id)
                })
            mapping[old_bag_id] = submission
        return mapping

    def _process_products(self, submission_map):
        csv_data = self._read_csv(self.file_products)
        count = 0

        condition_mapping = {
            '5 hartjes': '❤️❤️❤️❤️❤️', '4 hartjes': '❤️❤️❤️❤️🤍',
            '3 hartjes': '❤️❤️❤️🤍🤍', '2 hartjes': '❤️❤️🤍🤍🤍', '1 hartje': '❤️🤍🤍🤍🤍'
        }

        for row in csv_data:
            if count > 0 and count % 10 == 0: _logger.info(f"... {count} producten verwerkt ...")

            zak_id_product = self._clean_id(row.get('zak_id'))
            old_product_id = self._clean_id(row.get('product_id'))
            name = row.get('naam')

            if not zak_id_product: continue
            submission = submission_map.get(zak_id_product)
            if not submission: continue

            default_code = row.get('code')

            # --- 1. ZOEK HET PRODUCT (Bestaat het al?) ---
            domain = []
            if default_code: domain.append(('default_code', '=', default_code))
            if old_product_id:
                if domain: domain = ['|'] + domain + [('x_old_id', '=', str(old_product_id))]
                else: domain = [('x_old_id', '=', str(old_product_id))]

            product = self.env['product.template'].search(domain, limit=1)

            # --- 2. BEPAAL NIEUWE STOCK ---
            verkocht = str(row.get('verkocht', '')).lower()
            online_verkocht = str(row.get('online_verkocht', '')).lower()
            stock_csv = row.get('stock') or '0'
            try:
                stock_val = float(stock_csv.replace(',', '.'))
            except:
                stock_val = 0.0

            # De Regel: Alleen stock als NOG NIET verkocht (offline of online)
            if verkocht == 'nee' and online_verkocht == 'nee':
                final_qty = stock_val
            else:
                final_qty = 0.0

            # --- 3. MAAK OF UPDATE ---
            product_vals = {
                'name': name,
                'submission_id': submission.id,
                'is_published': True, # Altijd gepubliceerd
                'type': 'consu', 'is_storable': True,
                # Als je al bestaat, updaten we de code en ID niet per se, maar wel handig
                'default_code': default_code,
                'x_old_id': str(old_product_id),
                # We updaten omschrijvingen ook
                'website_description': row.get('lange_omschrijving'),
                'description_sale': row.get('korte_omschrijving_nl'),
            }

            if product:
                # UPDATE BESTAAND PRODUCT
                product.write(product_vals)
                # Stock updaten van bestaand product
                self._update_stock(product, final_qty)

                # We skippen foto download bij update om tijd te besparen (tenzij je dat wil)
                # count += 1
                # continue
            else:
                # NIEUW PRODUCT
                # Alleen bij nieuwe producten downloaden we de foto (traag)
                time.sleep(0.5)
                image_url = row.get('foto')
                product_vals['image_1920'] = self._download_image(image_url)

                # Prijs alleen zetten bij aanmaken (of wil je die ook updaten?)
                prijs_raw = row.get('prijs') or '0'
                try: product_vals['list_price'] = float(str(prijs_raw).replace(',', '.'))
                except: product_vals['list_price'] = 0.0

                product = self.env['product.template'].create(product_vals)

                # Stock zetten voor nieuw product
                self._update_stock(product, final_qty)

                # Kenmerken en fotos toevoegen (alleen bij nieuw)
                if row.get('maat'): self._add_attribute(product, 'Maat', row.get('maat'))
                if row.get('merk'): self._add_attribute(product, 'Merk', row.get('merk'))
                if row.get('seizoen'): self._add_attribute(product, 'Seizoen', row.get('seizoen'))
                if row.get('categorie'): self._add_attribute(product, 'Doelgroep', row.get('categorie'))
                if row.get('type'): self._add_attribute(product, 'Categorie', row.get('type'))

                staat = row.get('staat')
                if staat in condition_mapping:
                    self._add_attribute(product, 'Conditie', condition_mapping[staat])

                extra_fotos = row.get('extra_fotos')
                if extra_fotos and str(extra_fotos) != 'nan':
                    urls = extra_fotos.split(',')
                    for idx, url in enumerate(urls):
                        if url:
                            time.sleep(0.2)
                            extra_img = self._download_image(url.strip())
                            if extra_img:
                                self.env['product.image'].create({
                                    'product_tmpl_id': product.id,
                                    'name': f"{name} - Extra {idx+1}",
                                    'image_1920': extra_img
                                })

            count += 1

        return count

    def _download_image(self, url):
        if not url or str(url) == 'nan': return False
        if url.startswith('..'): url = self.old_site_url + url.lstrip('.')
        elif not url.startswith('http'): url = self.old_site_url + '/' + url.lstrip('/')
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200: return base64.b64encode(r.content)
        except Exception: pass
        return False

    def _add_attribute(self, product, att_name, val_name):
        if not val_name or str(val_name) == 'nan': return
        vals = str(val_name).replace('&', '|').replace(' en ', '|').split('|')
        for v in vals:
            v = v.strip()
            if not v: continue
            attribute = self.env['product.attribute'].search([('name', '=ilike', att_name)], limit=1)
            if not attribute: attribute = self.env['product.attribute'].create({'name': att_name, 'create_variant': 'no_variant'})
            value = self.env['product.attribute.value'].search([('attribute_id', '=', attribute.id), ('name', '=ilike', v)], limit=1)
            if not value: value = self.env['product.attribute.value'].create({'name': v, 'attribute_id': attribute.id})

            # Check of waarde al bestaat op product om dubbels te voorkomen bij update
            exists = False
            for line in product.attribute_line_ids:
                if line.attribute_id.id == attribute.id and value.id in line.value_ids.ids:
                    exists = True

            if not exists:
                self.env['product.template.attribute.line'].create({
                    'product_tmpl_id': product.id,
                    'attribute_id': attribute.id,
                    'value_ids': [(6, 0, [value.id])]
                })
