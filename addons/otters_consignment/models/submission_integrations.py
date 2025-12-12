# -*- coding: utf-8 -*-
from odoo import models, api, _
import logging
import re
import requests
import base64

_logger = logging.getLogger(__name__)

class ConsignmentSubmissionIntegrations(models.AbstractModel):
    """
    Mixin class voor externe integraties (Sendcloud, Mail)
    zodat submission.py schoon blijft.
    """
    _name = 'otters.consignment.integrations'
    _description = 'Consignatie Integraties Mixin'

    # =================================================================================
    # SENDCLOUD LOGICA
    # =================================================================================

    def action_generate_sendcloud_label(self):
        self.ensure_one()

        config = self._get_sendcloud_config()
        if not config:
            return self._return_notification('Fout', 'Sendcloud configuratie ontbreekt.', 'danger')

        payload = self._prepare_sendcloud_payload(config)
        success, result = self._call_sendcloud_api(config, payload)

        if success:
            label_url = result.get('label', {}).get('label_printer')
            tracking_nr = result.get('tracking_number')

            # --- NIEUWE LOGICA: PDF DOWNLOADEN ---
            attachment_id = False
            if label_url:
                try:
                    # 1. Download de PDF met de API keys van de config
                    pdf_response = requests.get(label_url, auth=config['auth'])

                    if pdf_response.status_code == 200:
                        # 2. Maak een Odoo Attachment aan
                        pdf_content = base64.b64encode(pdf_response.content)
                        filename = f"Verzendlabel_{self.name}.pdf"

                        attachment = self.env['ir.attachment'].create({
                            'name': filename,
                            'type': 'binary',
                            'datas': pdf_content,
                            'res_model': 'otters.consignment.submission',
                            'res_id': self.id,
                            'mimetype': 'application/pdf'
                        })
                        attachment_id = attachment.id

                        # 3. Sla het label record op (voor referentie)
                        self.env['otters.consignment.label'].sudo().create({
                            'submission_id': self.id,
                            'label_url': label_url, # We bewaren de URL voor intern gebruik
                            'tracking_number': tracking_nr
                        })
                    else:
                        _logger.error(f"Kon PDF niet downloaden van Sendcloud. Status: {pdf_response.status_code}")

                except Exception as e:
                    _logger.error(f"Fout bij downloaden label PDF: {e}")

            # 4. Stuur de e-mail MET de bijlage
            self._send_label_email(attachment_id)

            return self._return_notification('Succes', 'Label aangemaakt en gemaild!', 'success')
        else:
            error_msg = result if isinstance(result, str) else "Onbekende fout"
            return self._return_notification('Fout', f'Sendcloud API: {error_msg}', 'danger', sticky=True)

    def _get_sendcloud_config(self):
        company = self.env.company
        api_key = company.sendcloud_public_key
        api_secret = company.sendcloud_secret_key

        if not api_key or not api_secret: return False

        ICP = self.env['ir.config_parameter'].sudo()
        config = {
            'auth': (api_key, api_secret),
            'shipping_id': int(ICP.get_param('otters_consignment.sendcloud_shipping_method_id') or 0),
            'store_name': ICP.get_param('otters_consignment.store_name'),
            'store_street': ICP.get_param('otters_consignment.store_street'),
            'store_house_number': ICP.get_param('otters_consignment.store_house_number'),
            'store_city': ICP.get_param('otters_consignment.store_city'),
            'store_zip': ICP.get_param('otters_consignment.store_zip'),
            'store_country': ICP.get_param('otters_consignment.store_country_code'),
            'store_phone': ICP.get_param('otters_consignment.store_phone'),
        }
        if not all(config.values()): return False
        return config

    def _prepare_sendcloud_payload(self, config):
        partner = self.supplier_id
        customer_phone = self._format_phone_be(partner.phone)
        store_phone = self._format_phone_be(config['store_phone'])

        return {
            "parcel": {
                "request_label": True,
                "is_return": False,
                "order_number": self.name,
                "weight": "5.000",
                "shipping_method": config['shipping_id'],
                "name": config['store_name'],
                "company_name": config['store_name'],
                "address": config['store_street'],
                "house_number": config['store_house_number'],
                "city": config['store_city'],
                "postal_code": config['store_zip'],
                "country": config['store_country'],
                "telephone": store_phone,
                "from_name": partner.name,
                "from_address_1": partner.street,
                "from_house_number": partner.street2 or "",
                "from_city": partner.city,
                "from_postal_code": partner.zip,
                "from_country": partner.country_id.code or "BE",
                "from_telephone": customer_phone,
                "from_email": partner.email
            }
        }

    def _call_sendcloud_api(self, config, payload):
        url = "https://panel.sendcloud.sc/api/v2/parcels"
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(url, headers=headers, json=payload, auth=config['auth'])
            response.raise_for_status()
            data = response.json()
            return True, data.get('parcel', {})
        except Exception as e:
            _logger.error(f"Sendcloud API Fout: {str(e)}")
            return False, str(e)

    # =================================================================================
    # MAIL LOGICA
    # =================================================================================

    def _send_confirmation_emails(self, submissions, total_bags):
        if not submissions: return
        primary_submission = submissions[0]

        template_customer = self.env.ref('otters_consignment.mail_template_consignment_confirmation', raise_if_not_found=False)
        if template_customer and primary_submission.supplier_id.email:
            try:
                template_customer.with_context(total_bags=total_bags).sudo().send_mail(primary_submission.id, force_send=True)
            except Exception as e:
                _logger.error(f"Fout mail klant: {e}")

        template_admin = self.env.ref('otters_consignment.mail_template_consignment_admin_alert', raise_if_not_found=False)
        company_email = self.env.company.email
        if template_admin and company_email:
            try:
                template_admin.with_context(total_bags=total_bags).sudo().send_mail(primary_submission.id, force_send=True)
            except Exception as e:
                _logger.error(f"Fout mail admin: {e}")

    def _send_label_email(self, attachment_id=None):
        if not self.supplier_id.email: return

        template = self.env.ref('otters_consignment.mail_template_consignment_label_send', raise_if_not_found=False)
        if template:
            try:
                # Bereid de mail waarden voor
                email_values = {}

                # Als we een bijlage hebben, voegen we die toe
                if attachment_id:
                    email_values['attachment_ids'] = [(4, attachment_id)]

                template.sudo().send_mail(self.id, force_send=True, email_values=email_values)

            except Exception as e:
                _logger.error(f"Label mail fout: {e}")

    # =================================================================================
    # TOOLS & HELPERS
    # =================================================================================

    def _return_notification(self, title, message, type='info', sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': type, 'sticky': sticky}
        }

    def _format_phone_be(self, phone_number):
        if not phone_number: return ""
        clean_phone = re.sub(r'\D', '', phone_number)
        if clean_phone.startswith('32'): return f"+{clean_phone}"
        if clean_phone.startswith('0'): return f"+32{clean_phone[1:]}"
        return f"+32{clean_phone}"