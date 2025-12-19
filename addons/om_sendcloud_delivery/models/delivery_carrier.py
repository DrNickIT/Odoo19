import requests
import base64
import json
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(selection_add=[
        ('sendcloud', 'Sendcloud')
    ], ondelete={'sendcloud': 'set default'})

    sendcloud_method_type = fields.Selection([
        ('house', 'Thuislevering'),
        ('pickup', 'Servicepunt Levering')
    ], string="Sendcloud Methode", default='house')

    sendcloud_shipping_id = fields.Char(string="Sendcloud Verzendmethode ID", help="Optioneel ID van de vervoerder in Sendcloud")

    def sendcloud_rate_shipment(self, order):
        return {
            'success': True,
            'price': 0.0,
            'error_message': False,
            'warning_message': False
        }

    def sendcloud_send_shipping(self, pickings):
        res = []
        company = self.env.company
        public_key = company.sendcloud_public_key
        secret_key = company.sendcloud_secret_key

        if not public_key or not secret_key:
            raise UserError("Sendcloud API keys zijn niet ingesteld bij Instellingen > Voorraad!")

        for picking in pickings:
            try:
                payload = self._prepare_sendcloud_payload(picking)
                url = "https://panel.sendcloud.sc/api/v2/parcels"
                auth = (public_key, secret_key)
                headers = {'Content-Type': 'application/json'}

                response = requests.post(url, json=payload, auth=auth, headers=headers)

                if response.status_code not in [200, 201]:
                    raise UserError(f"Sendcloud Fout ({response.status_code}): {response.text}")

                data = response.json().get('parcel', {})
                tracking = data.get('tracking_number')

                label_url = data.get('label', {}).get('normal_printer')
                if isinstance(label_url, list) and len(label_url) > 0:
                    label_url = label_url[0]

                if label_url:
                    self._save_label_attachment(picking, label_url)

                res.append({
                    'exact_price': 0.0,
                    'tracking_number': tracking,
                })

            except Exception as e:
                raise UserError(f"Fout bij Sendcloud: {str(e)}")
        return res

    def _prepare_sendcloud_payload(self, picking):
        partner = picking.partner_id
        weight = picking.shipping_weight
        if weight <= 0.0:
            weight = 5.0

        # --- SLIMME SPLITSING ---
        street_name, house_number = self._split_street_number(partner.street)

        # Als er een busnummer in street2 zit, voegen we die toe aan het huisnummer voor Sendcloud
        # Sendcloud verwacht: house_number="20 a" (waarbij 'a' de toevoeging is)
        full_house_number = house_number
        if partner.street2:
            # Voorkom dubbele 'Bus' vermelding als het al in het nummer zit
            # We vervangen 'Bus' en 'bus' door niets, en plakken het achter het huisnummer
            toevoeging = partner.street2.replace('Bus', '').replace('bus', '').strip()
            full_house_number = f"{full_house_number} {toevoeging}".strip()

        vals = {
            "name": partner.name,
            "address": street_name,
            "house_number": full_house_number,
            "city": partner.city,
            "postal_code": partner.zip,
            "country": partner.country_id.code,
            "request_label": False,
            "email": partner.email or "",
            "telephone": partner.phone or "",
            "weight": str(weight),
            "order_number": picking.origin or picking.name
        }

        if self.sendcloud_shipping_id:
            vals['shipping_method'] = int(self.sendcloud_shipping_id)

        if self.sendcloud_method_type == 'pickup':
            so = picking.sale_id
            if not so.sendcloud_service_point_id:
                raise UserError("Geen servicepunt geselecteerd in de order!")
            vals['to_service_point'] = so.sendcloud_service_point_id

        return {"parcel": vals}

    def _split_street_number(self, full_street):
        if not full_street:
            return "", ""

        match = re.match(r'^(.*?)\s+(\d+.*)$', full_street.strip())

        if match:
            return match.group(1), match.group(2)
        return full_street, ""

    def _save_label_attachment(self, picking, url):
        try:
            pdf_content = requests.get(url).content
            attachment = self.env['ir.attachment'].create({
                'name': f"Label_{picking.name}.pdf",
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': 'stock.picking',
                'res_id': picking.id,
                'mimetype': 'application/pdf'
            })
            picking.message_post(body="Sendcloud Label", attachment_ids=[attachment.id])
        except Exception:
            pass

    def sendcloud_get_tracking_link(self, picking):
        return f"https://tracking.sendcloud.sc/{picking.carrier_tracking_ref}"

    def sendcloud_cancel_shipment(self, picking):
        pass