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
        try:
            product_variant = product_tmpl.product_variant_id
            if not product_variant: return
            warehouse = self.env['stock.warehouse'].search([], limit=1)
            location = warehouse.lot_stock_id
            if not location: return
            self.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': product_variant.id,
                'location_id': location.id,
                'inventory_quantity': float(qty),
            }).action_apply_inventory()
        except Exception as e:
            pass

    def start_migration(self):
        _logger.info("=== START MIGRATIE (MET NAAM GENERATIE FIX) ===")
        customer_map = self._process_customers()
        submission_map = self._process_submissions(customer_map)
        count = self._process_products(submission_map)
        _logger.info(f"=== PRODUCTEN KLAAR: {count} verwerkt ===")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Klaar!', 'message': f'{count} producten verwerkt.', 'type': 'success', 'sticky': True}
        }

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

            domain = ['|', ('email', '=ilike', email.strip()), ('x_old_id', '=', str(old_id))]
            partner = self.env['res.partner'].search(domain, limit=1)

            # Gegevens voorbereiden
            full_name = f"{row.get('voornaam','')} {row.get('achternaam','')}".strip() or email

            if not partner:
                # NIEUW: GEEN 'x_consignment_prefix' invullen!
                # Laat Odoo dat zelf berekenen (Kathleen Daems -> KDA)
                partner = self.env['res.partner'].create({
                    'name': full_name, 'email': email,
                    'street': f"{row.get('straat', '')} {row.get('huisnr', '')}".strip(),
                    'zip': row.get('postcode', ''), 'city': row.get('gemeente', ''),
                    # 'x_consignment_prefix': f"IMP{old_id}", <--- DEZE REGEL IS WEG!
                    'x_old_id': str(old_id)
                })
            else:
                vals = {}
                if not partner.x_old_id:
                    vals['x_old_id'] = str(old_id)

                # CORRECTIE: Als de klant al een "foute" import-prefix heeft (IMP...), reset hem dan!
                if partner.x_consignment_prefix and partner.x_consignment_prefix.startswith('IMP'):
                    vals['x_consignment_prefix'] = False # Leegmaken zodat hij herberekend wordt

                if vals:
                    partner.write(vals)

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

            submission = self.env['otters.consignment.submission'].search([('x_old_id', '=', str(old_bag_id))], limit=1)

            if not submission:
                date = row.get('datum_ontvangen') or fields.Date.today()

                # We sturen 'Nieuw'. Jouw submission.py zal nu zien dat de partner geen prefix heeft (of een nieuwe moet krijgen)
                # en zal KDA aanmaken in plaats van IMP.
                submission = self.env['otters.consignment.submission'].with_context(skip_sendcloud=True).create({
                    'name': 'Nieuw',
                    'supplier_id': partner.id,
                    'submission_date': date,
                    'state': 'processing',
                    'payout_method': 'coupon',
                    'payout_percentage': 0.5,
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

            # Commissie
            commissie_raw = row.get('commissie')
            if commissie_raw:
                try:
                    comm_val = int(float(str(commissie_raw).replace(',', '.')))
                    method = False; percentage = 0.0
                    if comm_val == 30: method = 'cash'; percentage = 0.30
                    elif comm_val == 50: method = 'coupon'; percentage = 0.50
                    if method:
                        if submission.payout_method != method:
                            submission.write({'payout_method': method, 'payout_percentage': percentage})
                        partner = submission.supplier_id
                        if partner.x_payout_method != method:
                            partner.write({
                                'x_payout_method': method,
                                'x_cash_payout_percentage': 0.3 if method == 'cash' else 0.0,
                                'x_coupon_payout_percentage': 0.5 if method == 'coupon' else 0.0
                            })
                except Exception: pass

            default_code = row.get('code')
            domain = []
            if default_code: domain.append(('default_code', '=', default_code))
            if old_product_id:
                if domain: domain = ['|'] + domain + [('x_old_id', '=', str(old_product_id))]
                else: domain = [('x_old_id', '=', str(old_product_id))]

            product = self.env['product.template'].search(domain, limit=1)

            # Stock
            verkocht = str(row.get('verkocht', '')).lower()
            online_verkocht = str(row.get('online_verkocht', '')).lower()
            datum_verkocht = str(row.get('datum_verkocht', '')).strip()
            datum_uitbetaald = str(row.get('datum_uitbetaald', '')).strip()
            stock_csv = row.get('stock') or '0'
            try: stock_val = float(stock_csv.replace(',', '.'))
            except: stock_val = 0.0

            def is_empty_date(d): return not d or d == '0000-00-00'
            if (verkocht == 'nee' and online_verkocht == 'nee' and
                is_empty_date(datum_verkocht) and is_empty_date(datum_uitbetaald)):
                final_qty = stock_val
            else:
                final_qty = 0.0

            product_vals = {
                'name': name, 'submission_id': submission.id,
                'is_published': True, 'type': 'consu', 'is_storable': True,
                'default_code': default_code, 'x_old_id': str(old_product_id),
                'description_ecommerce': row.get('lange_omschrijving'),
                'description_sale': row.get('korte_omschrijving_nl'),
                'website_meta_title': row.get('seo_titel'),
                'website_meta_description': row.get('seo_description'),
                'website_meta_keywords': row.get('seo_keywords'),
            }

            if product:
                # UPDATE
                product.write(product_vals)
                self._update_stock(product, final_qty)

                if not product.product_template_image_ids:
                    extra_fotos = row.get('extra_fotos')
                    if extra_fotos and str(extra_fotos) != 'nan':
                        urls = extra_fotos.split(',')
                        for idx, url in enumerate(urls):
                            if url:
                                time.sleep(0.2)
                                extra_img = self._download_image(url.strip(), fix_old_id=old_product_id)
                                if extra_img:
                                    self.env['product.image'].create({
                                        'product_tmpl_id': product.id,
                                        'name': f"{name} - Extra {idx+1}",
                                        'image_1920': extra_img
                                    })
            else:
                # NIEUW
                time.sleep(0.5)
                image_url = row.get('foto')
                product_vals['image_1920'] = self._download_image(image_url, fix_old_id=old_product_id)

                prijs_raw = row.get('prijs') or '0'
                try: product_vals['list_price'] = float(str(prijs_raw).replace(',', '.'))
                except: product_vals['list_price'] = 0.0

                product = self.env['product.template'].create(product_vals)
                self._update_stock(product, final_qty)

                if row.get('maat'): self._add_attribute(product, 'Maat', row.get('maat'))
                if row.get('merk'): self._add_attribute(product, 'Merk', row.get('merk'))
                if row.get('seizoen'): self._add_attribute(product, 'Seizoen', row.get('seizoen'))
                if row.get('categorie'): self._add_attribute(product, 'Doelgroep', row.get('categorie'))
                if row.get('type'): self._add_attribute(product, 'Categorie', row.get('type'))
                staat = row.get('staat')
                if staat in condition_mapping:
                    self._add_attribute(product, 'Conditie', condition_mapping[staat])

                # Extra fotos (Nieuw)
                extra_fotos = row.get('extra_fotos')
                if extra_fotos and str(extra_fotos) != 'nan':
                    urls = extra_fotos.split(',')
                    for idx, url in enumerate(urls):
                        if url:
                            time.sleep(0.2)
                            extra_img = self._download_image(url.strip(), fix_old_id=old_product_id)
                            if extra_img:
                                self.env['product.image'].create({
                                    'product_tmpl_id': product.id,
                                    'name': f"{name} - Extra {idx+1}",
                                    'image_1920': extra_img
                                })

            count += 1
        return count

    def _download_image(self, url, fix_old_id=None):
        if not url or str(url) == 'nan': return False

        # ID REPARATIE
        if fix_old_id and '/product//' in url:
            url = url.replace('/product//', f'/product/{fix_old_id}/')
            _logger.info(f"URL FIXED: {url}")

        clean_path = url.lstrip('.').strip()
        clean_path = clean_path.replace('//', '/')

        urls_to_try = []

        if url.startswith('http'):
            urls_to_try.append(url)
        else:
            path_with_slash = '/' + clean_path.lstrip('/')
            urls_to_try.append(f"{self.old_site_url}/foto.php?src={path_with_slash}")
            urls_to_try.append(f"{self.old_site_url}{path_with_slash}")

        headers = {'User-Agent': 'Mozilla/5.0'}

        for try_url in urls_to_try:
            try:
                r = requests.get(try_url, headers=headers, timeout=10)
                if r.status_code == 200:
                    if 'image' in r.headers.get('Content-Type', ''):
                        return base64.b64encode(r.content)
            except Exception as e:
                pass

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

            exists = False
            for line in product.attribute_line_ids:
                if line.attribute_id.id == attribute.id and value.id in line.value_ids.ids: exists = True

            if not exists:
                self.env['product.template.attribute.line'].create({
                    'product_tmpl_id': product.id,
                    'attribute_id': attribute.id,
                    'value_ids': [(6, 0, [value.id])]
                })