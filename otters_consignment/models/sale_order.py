# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_review_mail_sent = fields.Boolean(string="Review Mail Verzonden", default=False, copy=False)

    @api.model
    def _cron_send_review_emails(self):
        now = fields.Datetime.now()
        ICP = self.env['ir.config_parameter'].sudo()

        # 1. HAAL CONFIGURATIE OP
        launch_date_str = ICP.get_param('otters_consignment.review_launch_date')
        # Haal aantal dagen op (gebruik 5 als fallback als het veld leeg is)
        delay_days = int(ICP.get_param('otters_consignment.review_delay_days') or 5)

        if not launch_date_str:
            _logger.info("Geen lanceerdatum ingesteld voor review mails. Cron job gestopt.")
            return

        launch_date = fields.Datetime.from_string(launch_date_str)
        # Bereken de doel-datum op basis van de instelling
        target_date = now - timedelta(days=delay_days)

        # 2. ZOEK DE ORDERS
        orders_to_mail = self.search([
            ('state', 'in', ['sale', 'done']),
            ('date_order', '<=', target_date), # X dagen oud of ouder
            ('date_order', '>=', launch_date), # Maar na de lanceerdatum
            ('x_review_mail_sent', '=', False)
        ])

        # 3. VERSTUUR MAILS
        template = self.env.ref('otters_consignment.mail_template_google_review_request', raise_if_not_found=False)

        if not template:
            _logger.warning("E-mail template voor Google Review niet gevonden!")
            return

        for order in orders_to_mail:
            order.x_review_mail_sent = True
            if order.partner_id.email:
                template.send_mail(order.id, force_send=True)
                order.message_post(body=f"Automatische Google Review e-mail verzonden ({delay_days} dagen na bestelling).")