# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.translate import _
import logging
import re
import requests
import base64
import json
import logging
import re

_logger = logging.getLogger(__name__)

class ConsignmentSubmission(models.Model):
    _name = 'otters.consignment.submission'
    _description = 'Beheert de inzendingen van kleding door leveranciers.'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin'] # Belangrijk voor Portal

    name = fields.Char(string="Inzending ID", required=True, readonly=True, default='Nieuw', copy=False)
    supplier_id = fields.Many2one('res.partner', string="Leverancier", required=True, tracking=True)
    submission_date = fields.Date(string="Inzendingsdatum", default=fields.Date.context_today, required=True, tracking=True)
    state = fields.Selection([('draft', 'Concept'), ('received', 'Ontvangen'), ('processing', 'In Behandeling'), ('sold', 'Verkocht'), ('done', 'Afgehandeld')], string='Status', default='draft', required=True, tracking=True)
    product_ids = fields.One2many('product.template', 'submission_id', string="Ingezonden Producten")

    # --- Gerelateerde velden voor uitbetaling ---
    payout_method = fields.Selection(
        [('cash', 'Cash'), ('coupon', 'Coupon')],
        string="Payout Method",
        store=True,
        readonly=True,
        tracking=True,
        help="De uitbetaalmethode die definitief is vastgelegd voor deze inzending."
    )
    payout_percentage = fields.Float(
        string="Payout Percentage",
        store=True,
        readonly=True,
        tracking=True,
        help="Het uitbetalingspercentage dat definitief is vastgelegd voor deze inzending."
    )

    # --- VELDEN TERUGGEPLAATST VOOR WHITELIST/REGISTRY INTEGRITEIT (store=False) ---
    x_sender_name = fields.Char(string="Naam Afzender (Tijdelijk)", store=False)
    x_sender_email = fields.Char(string="E-mail Afzender (Tijdelijk)", store=False)
    x_sender_phone = fields.Char(string="Telefoon Afzender (Tijdelijk)", store=False)
    x_sender_street = fields.Char(string="Straat Afzender (Tijdelijk)", store=False)
    x_sender_house_number = fields.Char(string="Huisnummer Afzender (Tijdelijk)", store=False)
    x_sender_city = fields.Char(string="Stad Afzender (Tijdelijk)", store=False)
    x_sender_postal_code = fields.Char(string="Postcode Afzender (Tijdelijk)", store=False)
    x_sender_country_code = fields.Char(string="Landcode Afzender (Tijdelijk)", store=False)
    x_payout_method_temp = fields.Selection(
        [('cash', 'Cash'), ('coupon', 'Coupon')],
        string="Tijdelijke Payout Methode",
        store=False
    )

    # --- LOGICA VOOR VERKOCHTE PRODUCTEN (Strikte check voor financiële correctheid) ---
    def _get_sold_products(self):
        """ Bepaalt welke producten van deze inzending definitief als verkocht moeten worden beschouwd,
            wanneer de order is bevestigd EN de hoeveelheid is gefactureerd.
        """
        # Gebruik sudo() om ACL-fouten te voorkomen bij het zoeken naar Verkooporders door een Portal-gebruiker
        self = self.sudo()
        product_variant_ids = self.product_ids.product_variant_ids.ids

        if not product_variant_ids:
            return self.env['product.template']

        # Zoek alle orderlijnen die:
        sold_lines = self.env['sale.order.line'].sudo().search([
            ('product_id', 'in', product_variant_ids),
            # 1. Bevestigde orderstatus hebben (definitief verkocht)
            ('order_id.state', 'in', ['sale', 'done']),
            # 2. Een gefactureerde hoeveelheid hebben (FINANCIEEL VASTGELEGD)
            ('qty_invoiced', '>', 0),
        ])

        sold_product_templates = sold_lines.mapped('product_template_id')

        # Geef de set van verkochte templates terug die in deze inzending zitten
        return self.product_ids & sold_product_templates

    # --- Create/Write logica voor auto-nummering, percentages en archiveren ---

    def _get_or_create_supplier_prefix(self, supplier):
        """
        Gets or creates a unique prefix for the given supplier.
        e.g., "Tom Hoornaert" -> "TOHO"
        e.g., "Tomas Hoogland" -> "TOHOO" (if "TOHO" is taken)
        """
        # If the supplier already has a prefix, use it.
        if supplier.x_consignment_prefix:
            return supplier.x_consignment_prefix

        # --- If not, generate a new, unique one ---
        if not supplier.name:
            return "PARTNER" # Fallback

        parts = supplier.name.strip().split()
        prefix_base = ""

        if len(parts) >= 2:
            # "Tom Hoornaert" -> "TO" + "HO"
            fn = re.sub(r'[^A-Z0-9]', '', parts[0][:2].upper())
            ln_base = re.sub(r'[^A-Z0-9]', '', parts[-1].upper())

            # Try FN[:2] + LN[:2], then FN[:2] + LN[:3], etc.
            for i in range(2, len(ln_base) + 1):
                prefix_try = fn + ln_base[:i]
                if not prefix_try: continue # Skip if name was weird (e.g., "!!")

                # Check if this prefix is already used by *another* supplier
                if not self.env['res.partner'].search_count([('x_consignment_prefix', '=', prefix_try)]):
                    prefix_base = prefix_try
                    break

            # Fallback if all variations are taken (e.g., TOHO, TOHOO, TOHOOR, ...)
            if not prefix_base:
                prefix_base = fn + ln_base + str(supplier.id)

        elif len(parts) == 1 and parts[0]:
            # "IKEA" -> "IKEA"
            prefix_base = re.sub(r'[^A-Z0-9]', '', parts[0][:4].upper())

        if not prefix_base:
            prefix_base = "INV" # Invalid

        # Save the new prefix to the supplier
        supplier.write({'x_consignment_prefix': prefix_base})
        _logger.info(f"### Generated and saved new prefix '{prefix_base}' for supplier '{supplier.name}'")
        return prefix_base

    # Dit is de enige methode die de binnenkomende data (vals_list) verwerkt.
    @api.model_create_multi
    def create(self, vals_list):
        new_vals_list = []

        for vals in vals_list:

            # --- STAP 1: PARTNER LOGICA (Fix voor Website Formulier) ---
            if vals.get('x_sender_email'):

                # 1. Haal de formulierdata op (gebruik .get() omdat deze velden zijn verwijderd uit de submission model)
                sender_email = vals.pop('x_sender_email')
                temp_payout_method = vals.pop('x_payout_method_temp')

                partner_vals = {
                    'name': vals.pop('x_sender_name'),
                    'email': sender_email,
                    'phone': vals.pop('x_sender_phone'),
                    'street': vals.pop('x_sender_street'),
                    'street2': vals.pop('x_sender_house_number'),
                    'city': vals.pop('x_sender_city'),
                    'zip': vals.pop('x_sender_postal_code'),
                    # Zoek het land op basis van de code (BELANGRIJK: Zorgt dat country_id een ID is)
                    'country_id': self.env['res.country'].search([('code', '=', vals.pop('x_sender_country_code', 'BE'))], limit=1).id,
                }
                # De partner krijgt altijd de laatst gekozen methode als voorkeur
                if temp_payout_method:
                    partner_vals['x_payout_method'] = temp_payout_method

                # 2. Partner Lookup/Creatie
                Partner = self.env['res.partner'].sudo()
                partner = Partner.search([('email', '=ilike', sender_email)], limit=1)

                if partner:
                    partner.write(partner_vals)
                else:
                    partner = Partner.create(partner_vals)

                if not partner.exists():
                    raise UserError(_("Kon de leverancier niet aanmaken/vinden. Aanvraag geweigerd."))

                # 3. CRUCIALE FIX: Voeg de supplier_id toe aan de vals
                vals['supplier_id'] = partner.id

                # 4. Verwijder de tijdelijke x_sender velden uit vals (ze bestaan niet op submission)
                for key in list(vals.keys()):
                    if key.startswith('x_sender_'):
                        vals.pop(key, None)

                # --- STAP 2: VASTLEGGEN VAN PERCENTAGE & METHODE (Financiële Nauwkeurigheid) ---

                # Bepaal en schrijf de percentages op de PARTNER (contractuele afspraak)
                if temp_payout_method:
                    ICP = self.env['ir.config_parameter'].sudo()
                    cash_perc = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
                    coupon_perc = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))

                    write_values = {'x_cash_payout_percentage': 0.0, 'x_coupon_payout_percentage': 0.0}

                    if temp_payout_method == 'cash':
                        write_values['x_cash_payout_percentage'] = cash_perc
                        percentage_to_set = cash_perc
                    else: # coupon
                        write_values['x_coupon_payout_percentage'] = coupon_perc
                        percentage_to_set = coupon_perc

                    partner.sudo().write(write_values)

                    # Vastleggen op de SUBMISSION (historische waarheid)
                    vals['payout_percentage'] = percentage_to_set
                    vals['payout_method'] = temp_payout_method


            # --- STAP 3: AANGEPASTE NUMMERING (Prefix + Sequence) ---

            if vals.get('name', 'Nieuw') == 'Nieuw' and vals.get('supplier_id'):
                partner = self.env['res.partner'].browse(vals['supplier_id'])

                # Zorgt ervoor dat de partner een unieke prefix krijgt (e.g., MANI) en opslaat
                prefix = self._get_or_create_supplier_prefix(partner)

                # Gebruik de Odoo sequence voor alleen het nummer (e.g., 00001)
                next_number = self.env['ir.sequence'].next_by_code('otters.consignment.submission') or '00000'

                # Combineer ze tot de uiteindelijke naam (e.g., MANI_00001)
                vals['name'] = f'{prefix}_{next_number}'

            new_vals_list.append(vals)

        # Roep de standaard create methode aan
        submissions = super(ConsignmentSubmission, self).create(new_vals_list)

        # --- STAP 4: SENDCLOUD API-call (Bedrijfslogica, altijd na create) ---
        for submission in submissions:
            if submission.supplier_id:
                try:
                    # Roep de ingebedde methode aan om het pakket te creëren
                    submission.sudo()._create_sendcloud_parcel()
                except Exception as e:
                    _logger.error(f"FATALE FOUT: Sendcloud API-call mislukt voor inzending {submission.name}: {e}")

        return submissions

    # In submission.py, binnen de ConsignmentSubmission class

    def write(self, vals):
        removed_template_ids = []

        if 'product_ids' in vals:
            new_commands = []

            for command in vals['product_ids']:
                if command[0] == 2 and command[1]:
                    # 1. Onderschep de 'Delete' actie (commando 2)
                    removed_template_ids.append(command[1])

                    # 2. Vervang 'Delete' (2, ID, False) door 'Unlink' (3, ID, False)
                    # Dit zorgt ervoor dat Odoo alleen de link verbreekt,
                    # maar de product.template NIET probeert te verwijderen.
                    new_commands.append((3, command[1], False))
                else:
                    new_commands.append(command)

            if removed_template_ids:
                vals['product_ids'] = new_commands

        # 3. Voer de standaard Odoo write/update uit
        res = super(ConsignmentSubmission, self).write(vals)

        # 4. Archiveer de Product Templates
        if removed_template_ids:
            templates_to_archive = self.env['product.template'].browse(removed_template_ids)

            # Archiveer: zet de 'active' status op False
            templates_to_archive.write({'active': False})

            _logger.info(f"### Product Templates gearchiveerd (active=False): {removed_template_ids}")

        return res

    def _format_phone_be(self, phone_number):
        """Zet een Belgisch telefoonnummer om naar E.164-formaat."""
        if not phone_number:
            return "" # Stuur een lege string, geen 'None'
        clean_phone = re.sub(r'\D', '', phone_number)
        if clean_phone.startswith('32'):
            return f"+{clean_phone}"
        if clean_phone.startswith('0'):
            return f"+32{clean_phone[1:]}"
        return f"+32{clean_phone}"

    # In models/submission.py (binnen de ConsignmentSubmission class)
    def _create_sendcloud_parcel(self):
        self.ensure_one() # Werkt met één record

        partner = self.supplier_id
        submission = self
        post = { # Simuleer 'post' data met velden uit partner/submission
            'phone': partner.phone,
            'street': partner.street,
            'house_number': partner.street2,
            'city': partner.city,
            'postal_code': partner.zip,
            'country': partner.country_id.code,
        }

        # Roep hier de GEHELE OUDE LOGICA van _create_sendcloud_label aan,
        # maar gebruik de lokale variabelen (partner, submission, post).

        _logger.info(f"Attempting to create Sendcloud label for {submission.name}...")
        _logger.info(f"Attempting to create Sendcloud label via V2/PARCELS endpoint for {submission.name}...")

        # Haal de API-sleutels en config op uit Odoo
        ICP = request.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('otters_consignment.sendcloud_api_key')
        api_secret = ICP.get_param('otters_consignment.sendcloud_api_secret')

        # We gebruiken nu weer 'shipping_method_id' (het getal, bv. 8)
        shipping_id = ICP.get_param('otters_consignment.sendcloud_shipping_method_id')

        # Haal de adresgegevens van de WINKEL (ontvanger) op
        store_name = ICP.get_param('otters_consignment.store_name')
        store_street = ICP.get_param('otters_consignment.store_street')
        store_house_number = ICP.get_param('otters_consignment.store_house_number')
        store_city = ICP.get_param('otters_consignment.store_city')
        store_zip = ICP.get_param('otters_consignment.store_zip')
        store_country = ICP.get_param('otters_consignment.store_country_code')
        store_phone_raw = ICP.get_param('otters_consignment.store_phone')

        if not all([api_key, api_secret, shipping_id, store_name, store_street, store_phone_raw]):
            _logger.error("Sendcloud config (API keys, shipping_method_ID, or store address) is incomplete.")
            return

        # We gebruiken de V2/PARCELS endpoint
        url = "https://panel.sendcloud.sc/api/v2/parcels"
        auth = base64.b64encode(f"{api_key}:{api_secret}".encode('utf-8')).decode('ascii')
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}"
        }

        # Formatteer de telefoonnummers
        customer_phone_formatted = self._format_phone_be(post.get('phone'))
        store_phone_formatted = self._format_phone_be(store_phone_raw)

        # De werkende payload-structuur
        payload = {
            "parcel": {
                "request_label": True,
                "is_return": False, # Zoals je hebt getest
                "order_number": submission.name,
                "weight": "5.000",
                "shipping_method": int(shipping_id),

                # --- De WINKEL (Ontvanger) ---
                "name": store_name,
                "company_name": store_name,
                "address": store_street,
                "house_number": store_house_number,
                "city": store_city,
                "postal_code": store_zip,
                "country": store_country, # bv. "BE"
                "telephone": store_phone_formatted,

                # --- De KLANT (Afzender) ---
                "from_name": partner.name,
                "from_address_1": post.get('street'), # Jouw 'from_address_1' fix
                "from_house_number": post.get('house_number'),
                "from_city": post.get('city'),
                "from_postal_code": post.get('postal_code'),
                "from_country": post.get('country'), # bv. "BE"
                "from_telephone": customer_phone_formatted,
                "from_email": partner.email
            }
        }

        _logger.info(f"--- VERZENDE SENDCLOUD V2 PAYLOAD (naar /parcels) ---")
        _logger.info(json.dumps(payload, indent=2))
        _logger.info(f"-------------------------------------------------------")

        # Maak de API-call
        response = requests.post(url, headers=headers, data=json.dumps(payload))

        if response.status_code == 200 or response.status_code == 201:
            # SUCCES!
            data = response.json()
            # De V2 response-structuur
            label_url = data.get('parcel', {}).get('label', {}).get('label_printer')
            _logger.info(f"Sendcloud V2 LABEL created! URL: {label_url}")

        else:
            # FOUT!
            _logger.error(f"Sendcloud V2 API error: {response.status_code} - {response.text}")
            raise Exception(f"Sendcloud V2 API error: {response.text}")

        # ... (De rest van de code, inclusief Sendcloud API call, headers, payload, etc.) ...

        # OPMERKING: De helper _format_phone_be MOET in submission.py of een import staan.
        # Als deze in de oude controllers.py stond, moet je die code ook verplaatsen of importeren.
        # Als _format_phone_be een helper is, definieer deze dan ook in submission.py.

        # ... (API call en foutafhandeling) ...

        return True # Of de label URL
