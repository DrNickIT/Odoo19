# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import csv
import io
import logging
import requests
import time
import re

_logger = logging.getLogger(__name__)

class MigrationWizard(models.TransientModel):
    _name = 'otters.migration.wizard'
    _description = 'Master Migratie Tool'

    # --- 1. Bestanden ---
    file_customers = fields.Binary(string="1. Klanten (otters_klanten.csv)", required=True)
    filename_customers = fields.Char()

    file_submissions = fields.Binary(string="2. Verzendzakken (otters_verzendzak.csv)", required=True)
    filename_submissions = fields.Char()

    file_brands = fields.Binary(string="3. Merken (otters_merken.csv)", required=False)
    filename_brands = fields.Char()

    file_products = fields.Binary(string="4. Producten (otters_producten.csv)", required=True)
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
        _logger.info("=== START MIGRATIE (FULL RUN) ===")

        # 1. Klanten
        customer_map = self._process_customers()
        self.env.cr.commit()

        # 2. Zakken
        submission_map = self._process_submissions(customer_map)
        self.env.cr.commit()

        # 3. Merken
        brand_map = self._process_brands()
        self.env.cr.commit()

        # 4. Producten
        count = self._process_products(submission_map, brand_map)
        _logger.info(f"=== PRODUCTEN KLAAR: {count} verwerkt ===")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Klaar!', 'message': f'{count} producten verwerkt.', 'type': 'success', 'sticky': True}
        }

    def _read_csv(self, binary_data):
        if not binary_data: return []
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

            straat = f"{row.get('straat', '')} {row.get('huisnr', '')}".strip()
            bus = row.get('bus')
            if bus and str(bus) != 'nan':
                straat2 = f"Bus {bus}"
            else:
                straat2 = False

            if not partner:
                full_name = f"{row.get('voornaam','')} {row.get('achternaam','')}".strip() or email
                partner = self.env['res.partner'].create({
                    'name': full_name, 'email': email,
                    'street': straat,
                    'street2': straat2,
                    'zip': row.get('postcode', ''), 'city': row.get('gemeente', ''),
                    'x_old_id': str(old_id)
                })
            else:
                vals = {}
                if not partner.x_old_id: vals['x_old_id'] = str(old_id)
                if partner.x_consignment_prefix and partner.x_consignment_prefix.startswith('IMP'):
                    vals['x_consignment_prefix'] = False
                if vals: partner.write(vals)

            iban = row.get('rekeningnummer')
            if not iban or str(iban) == 'nan' or not str(iban).strip():
                iban = row.get('rekeningnummer2')

            if iban and str(iban) != 'nan' and str(iban).strip() != '':
                clean_iban = str(iban).replace(' ', '').strip()
                existing_bank = self.env['res.partner.bank'].search([
                    ('acc_number', '=', clean_iban),
                    ('partner_id', '=', partner.id)
                ], limit=1)
                if not existing_bank:
                    try:
                        self.env['res.partner.bank'].create({
                            'acc_number': clean_iban,
                            'partner_id': partner.id
                        })
                    except Exception as e:
                        pass

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

            schenking_raw = str(row.get('schenking', '')).lower()
            if 'goed doel' in schenking_raw:
                action_val = 'donate'
            elif 'terug' in schenking_raw:
                action_val = 'return'
            else:
                action_val = 'donate'

            if not submission:
                date = row.get('datum_ontvangen') or fields.Date.today()
                partner_iban = partner.bank_ids[:1].acc_number if partner.bank_ids else False

                submission = self.env['otters.consignment.submission'].with_context(skip_sendcloud=True).create({
                    'name': 'Nieuw',
                    'supplier_id': partner.id,
                    'submission_date': date,
                    'state': 'online',
                    'payout_method': 'coupon',
                    'payout_percentage': 0.5,
                    'x_old_id': str(old_bag_id),
                    'action_unaccepted': action_val,
                    'action_unsold': action_val,
                    'agreed_to_terms': True,
                    'agreed_to_clothing_terms': True,
                    'agreed_to_shipping_fee': True,
                    'x_iban': partner_iban
                })

                notities = row.get('notities')
                if notities and str(notities) != 'nan' and str(notities).strip() != '':
                    self.env['otters.consignment.rejected.line'].create({
                        'submission_id': submission.id,
                        'product_name': 'Notitie uit migratie',
                        'reason': 'other',
                        'note': notities
                    })

                oude_code = row.get('code')
                if oude_code:
                    submission.message_post(body=f"<b>Oude Code:</b> {oude_code}")

            mapping[old_bag_id] = submission
        return mapping

    def _process_brands(self):
        if not self.file_brands: return {}
        csv_data = self._read_csv(self.file_brands)
        brand_map = {}
        brand_attribute = self.env['product.attribute'].search([('name', '=', 'Merk')], limit=1)
        if not brand_attribute:
            brand_attribute = self.env['product.attribute'].create({'name': 'Merk', 'create_variant': 'no_variant', 'display_type': 'select'})

        count = 0
        for row in csv_data:
            if count > 0 and count % 50 == 0: self.env.cr.commit()
            old_merk_id = self._clean_id(row.get('merk_id'))
            name = row.get('naam')
            if not old_merk_id or not name: continue
            brand = self.env['otters.brand'].search([('name', '=', name)], limit=1)
            brand_vals = {
                'name': name,
                'description': row.get('omschrijving_nl'),
                'is_published': True,
                'website_meta_title': row.get('seo_titel'),
                'website_meta_description': row.get('seo_description'),
                'website_meta_keywords': row.get('seo_keywords'),
            }
            logo_url = row.get('foto')
            if logo_url and str(logo_url) != 'nan':
                img_data = self._download_image(logo_url)
                if img_data: brand_vals['logo'] = img_data
            if not brand: brand = self.env['otters.brand'].create(brand_vals)
            else: brand.write(brand_vals)
            brand_val = self.env['product.attribute.value'].search([('attribute_id', '=', brand_attribute.id), ('name', '=', name)], limit=1)
            if not brand_val: brand_val = self.env['product.attribute.value'].create({'name': name, 'attribute_id': brand_attribute.id})
            brand_map[old_merk_id] = {'brand_id': brand.id, 'attr_val_id': brand_val.id, 'attr_id': brand_attribute.id}
            count += 1
        return brand_map

    def _process_products(self, submission_map, brand_map):
        csv_data = self._read_csv(self.file_products)
        count = 0
        condition_mapping = {'5 hartjes': '❤️❤️❤️❤️❤️', '4 hartjes': '❤️❤️❤️❤️🤍', '3 hartjes': '❤️❤️❤️🤍🤍', '2 hartjes': '❤️❤️🤍🤍🤍', '1 hartje': '❤️🤍🤍🤍🤍'}
        accessoires_types = ['muts & sjaal', 'hoedjes & petjes', 'tutjes', 'accessoires', 'speelgoed', 'riem', 'haarband', 'rugzakken en tassen', 'slab', 'speenkoord', 'badcape', 'dekentje']

        for row in csv_data:
            if count > 0 and count % 10 == 0: self.env.cr.commit()
            zak_id_product = self._clean_id(row.get('zak_id'))
            old_product_id = self._clean_id(row.get('product_id'))
            name = row.get('naam')
            if not zak_id_product: continue
            submission = submission_map.get(zak_id_product)
            if not submission: continue

            commissie_raw = row.get('commissie')
            if commissie_raw:
                try:
                    comm_val = int(float(str(commissie_raw).replace(',', '.')))
                    method = False; percentage = 0.0
                    if comm_val == 30: method = 'cash'; percentage = 0.30
                    elif comm_val == 50: method = 'coupon'; percentage = 0.50
                    if method:
                        if submission.payout_method != method: submission.write({'payout_method': method, 'payout_percentage': percentage})
                        partner = submission.supplier_id
                        if partner.x_payout_method != method:
                            partner.write({'x_payout_method': method, 'x_cash_payout_percentage': 0.3 if method == 'cash' else 0.0, 'x_coupon_payout_percentage': 0.5 if method == 'coupon' else 0.0})
                except Exception: pass

            default_code = row.get('code')
            domain = []
            if default_code: domain.append(('default_code', '=', default_code))
            if old_product_id:
                if domain: domain = ['|'] + domain + [('x_old_id', '=', str(old_product_id))]
                else: domain = [('x_old_id', '=', str(old_product_id))]
            product = self.env['product.template'].search(domain, limit=1)

            verkocht = str(row.get('verkocht', '')).lower()
            online_verkocht = str(row.get('online_verkocht', '')).lower()
            niet_weergeven = str(row.get('product_niet_weergeven', '')).lower()
            datum_verkocht = str(row.get('datum_verkocht', '')).strip()
            datum_uitbetaald = str(row.get('datum_uitbetaald', '')).strip()
            stock_csv = row.get('stock') or '0'
            try: stock_val = float(stock_csv.replace(',', '.'))
            except: stock_val = 0.0
            def is_empty_date(d): return not d or d == '0000-00-00'

            final_qty = stock_val if (verkocht == 'nee' and online_verkocht == 'nee' and niet_weergeven != 'ja' and is_empty_date(datum_verkocht) and is_empty_date(datum_uitbetaald)) else 0.0
            is_published = False if (niet_weergeven == 'ja' or final_qty <= 0) else True
            internal_description = f"Oorspronkelijk verborgen: {row.get('waarom_niet_weergeven')}" if niet_weergeven == 'ja' and row.get('waarom_niet_weergeven') else False

            product_vals = {
                'name': name, 'submission_id': submission.id, 'is_published': is_published,
                'type': 'consu', 'is_storable': True, 'default_code': default_code, 'x_old_id': str(old_product_id),
                'description_ecommerce': row.get('lange_omschrijving'), 'description_sale': row.get('korte_omschrijving_nl'),
                'website_meta_title': row.get('seo_titel'), 'website_meta_description': row.get('seo_description'), 'website_meta_keywords': row.get('seo_keywords'),
            }
            if internal_description: product_vals['description'] = internal_description

            type_raw = str(row.get('type', '')).strip(); type_lower = type_raw.lower(); maat_raw = str(row.get('maat', '')).strip()
            target_cat_name = 'Kleding'; target_sub_name = type_raw.capitalize()
            if type_lower in accessoires_types: target_cat_name = 'Accessoires'
            elif 'kousen' in type_lower or 'sokken' in type_lower: target_cat_name = 'Schoenen & Kousen'; target_sub_name = 'Kousen'
            elif any(x in type_lower for x in ['schoen', 'laars', 'sneaker', 'sandaal', 'pantoffel']): target_cat_name = 'Schoenen & Kousen'; target_sub_name = 'Schoenen'

            if maat_raw:
                try:
                    clean_maat = re.match(r"(\d+)", maat_raw)
                    if clean_maat and int(clean_maat.group(1)) <= 45 and target_cat_name not in ['Accessoires', 'Schoenen & Kousen']:
                        target_cat_name = 'Schoenen & Kousen'; target_sub_name = 'Schoenen'
                except: pass

            main_cat = self.env['product.public.category'].search([('name', '=', target_cat_name), ('parent_id', '=', False)], limit=1)
            if not main_cat: main_cat = self.env['product.public.category'].create({'name': target_cat_name})
            final_categ_ids = [main_cat.id]
            if target_sub_name:
                sub_cat = self.env['product.public.category'].search([('name', '=', target_sub_name), ('parent_id', '=', main_cat.id)], limit=1)
                if not sub_cat: sub_cat = self.env['product.public.category'].create({'name': target_sub_name, 'parent_id': main_cat.id})
                final_categ_ids.append(sub_cat.id)

            # --- MERK VOORBEREIDING (Nog geen koppeling maken!) ---
            old_merk_id = self._clean_id(row.get('merk_id'))
            brand_data = None
            if old_merk_id and old_merk_id in brand_map:
                brand_data = brand_map[old_merk_id]
                product_vals['brand_id'] = brand_data['brand_id'] # Dit mag wel in vals, dit is een Many2one veld

            product_vals['public_categ_ids'] = [(6, 0, final_categ_ids)]
            int_main = self.env['product.category'].search([('name', '=', target_cat_name), ('parent_id', '=', False)], limit=1)
            if not int_main: int_main = self.env['product.category'].create({'name': target_cat_name})
            final_int_id = int_main.id
            if target_sub_name:
                int_sub = self.env['product.category'].search([('name', '=', target_sub_name), ('parent_id', '=', int_main.id)], limit=1)
                if not int_sub: int_sub = self.env['product.category'].create({'name': target_sub_name, 'parent_id': int_main.id})
                final_int_id = int_sub.id
            product_vals['categ_id'] = final_int_id

            # --- DE CRUCIALE SPLITSING ---
            if product:
                product.write(product_vals)
                self._update_stock(product, final_qty)

                # MERK KOPPELEN (NU HET PRODUCT ZEKER BESTAAT)
                if brand_data:
                    self._add_attribute_by_id(product, brand_data['attr_id'], brand_data['attr_val_id'])

                if not product.product_template_image_ids:
                    extra_fotos = row.get('extra_fotos')
                    if extra_fotos and str(extra_fotos) != 'nan':
                        for idx, url in enumerate(extra_fotos.split(',')):
                            if url:
                                time.sleep(0.3)
                                extra_img = self._download_image(url.strip(), fix_old_id=old_product_id)
                                if extra_img: self.env['product.image'].create({'product_tmpl_id': product.id, 'name': f"{name} - Extra {idx+1}", 'image_1920': extra_img})
            else:
                time.sleep(0.3)
                image_url = row.get('foto')
                product_vals['image_1920'] = self._download_image(image_url, fix_old_id=old_product_id)
                try: product_vals['list_price'] = float(str(row.get('prijs') or '0').replace(',', '.'))
                except: product_vals['list_price'] = 0.0

                # PRODUCT AANMAKEN
                product = self.env['product.template'].create(product_vals)
                self._update_stock(product, final_qty)

                # ATTRIBUTEN TOEVOEGEN (NU KAN HET VEILIG)
                if maat_raw: self._add_attribute(product, 'Schoenmaat' if target_cat_name == 'Schoenen & Kousen' else 'Maat', maat_raw)
                if row.get('merk'): self._add_attribute(product, 'Merk', row.get('merk'))
                if row.get('seizoen'): self._add_attribute(product, 'Seizoen', row.get('seizoen'))
                if row.get('categorie'): self._add_attribute(product, 'Geslacht', row.get('categorie'))
                if row.get('type'): self._add_attribute(product, 'Type', row.get('type'))
                if row.get('staat') in condition_mapping: self._add_attribute(product, 'Conditie', condition_mapping[row.get('staat')])

                # MERK KOPPELEN
                if brand_data:
                    self._add_attribute_by_id(product, brand_data['attr_id'], brand_data['attr_val_id'])

                extra_fotos = row.get('extra_fotos')
                if extra_fotos and str(extra_fotos) != 'nan':
                    for idx, url in enumerate(extra_fotos.split(',')):
                        if url:
                            time.sleep(0.3)
                            extra_img = self._download_image(url.strip(), fix_old_id=old_product_id)
                            if extra_img: self.env['product.image'].create({'product_tmpl_id': product.id, 'name': f"{name} - Extra {idx+1}", 'image_1920': extra_img})
            count += 1
        return count

    def _download_image(self, url, fix_old_id=None):
        if not url or str(url) == 'nan': return False
        if fix_old_id and '/product//' in url: url = url.replace('/product//', f'/product/{fix_old_id}/')
        clean_path = url.lstrip('.').strip().replace('//', '/')
        urls_to_try = [url] if url.startswith('http') else [f"{self.old_site_url}/foto.php?src={('/' + clean_path.lstrip('/'))}", f"{self.old_site_url}{('/' + clean_path.lstrip('/'))}"]
        headers = {'User-Agent': 'Mozilla/5.0'}
        for try_url in urls_to_try:
            try:
                r = requests.get(try_url, headers=headers, timeout=10)
                if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''): return base64.b64encode(r.content)
            except: pass
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
            if not exists: self.env['product.template.attribute.line'].create({'product_tmpl_id': product.id, 'attribute_id': attribute.id, 'value_ids': [(6, 0, [value.id])]})

    def _add_attribute_by_id(self, product, attribute_id, value_id):
        exists = False
        for line in product.attribute_line_ids:
            if line.attribute_id.id == attribute_id and value_id in line.value_ids.ids: exists = True
        if not exists: self.env['product.template.attribute.line'].create({'product_tmpl_id': product.id, 'attribute_id': attribute_id, 'value_ids': [(6, 0, [value_id])]})