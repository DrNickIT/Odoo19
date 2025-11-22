import requests
import base64
import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(selection_add=[
        ('sendcloud', 'Sendcloud')
    ], ondelete={'sendcloud': 'set default'})

    sendcloud_public_key = fields.Char(string="Public Key", groups="base.group_system")
    sendcloud_secret_key = fields.Char(string="Secret Key", groups="base.group_system")

    sendcloud_method_type = fields.Selection([
        ('house', 'Thuislevering'),
        ('pickup', 'Servicepunt Levering')
    ], string="Sendcloud Methode", default='house')

    # NIEUW: Het ID van de methode in Sendcloud
    sendcloud_shipping_id = fields.Char(string="Sendcloud Verzendmethode ID", help="Bijv. 8 voor PostNL Standaard. Te vinden in Sendcloud API of URL.", groups="base.group_system")


    def sendcloud_rate_shipment(self, order):
        """
        We geven 0 terug. Odoo gebruikt de standaard velden 'Extra Marge'
        en 'Gratis indien...' om de uiteindelijke prijs voor de klant te bepalen.
        """
        return {
            'success': True,
            'price': 0.0,
            'error_message': False,
            'warning_message': False
        }

    def sendcloud_send_shipping(self, pickings):
        """ Maak label aan bij validatie picking """
        res = []
        for picking in pickings:
            try:
                payload = self._prepare_sendcloud_payload(picking)

                # API Call
                url = "https://panel.sendcloud.sc/api/v2/parcels"
                auth = (self.sendcloud_public_key, self.sendcloud_secret_key)
                headers = {'Content-Type': 'application/json'}

                response = requests.post(url, json=payload, auth=auth, headers=headers)
                response.raise_for_status()

                data = response.json().get('parcel', {})

                tracking = data.get('tracking_number')
                label_url = data.get('label', {}).get('normal_printer', [])

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
        # --- NIEUWE LOGICA VOOR GEWICHT ---
        # Pak het gewicht dat Odoo heeft berekend
        weight = picking.shipping_weight

        # Als het gewicht 0 is (of kleiner), gebruik dan standaard 1.0 kg
        if weight <= 0.0:
            weight = 1.00
        # ----------------------------------
        vals = {
            "name": partner.name,
            "address": partner.street,
            "city": partner.city,
            "postal_code": partner.zip,
            "country": partner.country_id.code,
            "request_label": False,
            "email": partner.email or "",
            "telephone": partner.phone or "",
            "weight": str(weight),
            "order_number": picking.origin or picking.name
        }

        # NIEUW: Voeg het ID toe als het is ingevuld
        if self.sendcloud_shipping_id:
            vals['shipping_method'] = int(self.sendcloud_shipping_id)

        # Specifiek voor Servicepunt
        if self.sendcloud_method_type == 'pickup':
            so = picking.sale_id
            if not so.sendcloud_service_point_id:
                raise UserError("Geen servicepunt geselecteerd in de order!")
            vals['to_service_point'] = so.sendcloud_service_point_id

        return {"parcel": vals}

    def _save_label_attachment(self, picking, url):
        pdf_content = requests.get(url).content
        self.env['ir.attachment'].create({
            'name': f"Label_{picking.name}.pdf",
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'mimetype': 'application/pdf'
        })

    def sendcloud_get_tracking_link(self, picking):
        return f"https://tracking.sendcloud.sc/{picking.carrier_tracking_ref}"

    def sendcloud_cancel_shipment(self, picking):
        pass
