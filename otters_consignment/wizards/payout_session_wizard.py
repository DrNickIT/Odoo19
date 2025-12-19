# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io

try:
    import segno
except ImportError:
    segno = False

class PayoutSessionWizard(models.TransientModel):
    _name = 'otters.payout.session.wizard'
    _description = 'Uitbetaal Sessie'

    # --- De Wachtrij ---
    # We slaan hier alle partner ID's op die we nog moeten doen
    queue_partner_ids = fields.Many2many('res.partner', string="Wachtrij")
    queue_count = fields.Integer(string="Aantal te gaan", compute='_compute_queue_count')

    # --- De Huidige Leverancier ---
    current_partner_id = fields.Many2one('res.partner', string="Huidige Leverancier", readonly=True)

    # --- De Data voor het Scherm ---
    line_ids = fields.Many2many('sale.order.line', string="Te Betalen Items", readonly=True)
    total_amount = fields.Monetary(string="Totaalbedrag", currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)

    # --- QR Code ---
    qr_image = fields.Binary("QR Code", readonly=True)
    qr_filename = fields.Char("Bestandsnaam", default="qr.png")

    @api.depends('queue_partner_ids')
    def _compute_queue_count(self):
        for w in self:
            w.queue_count = len(w.queue_partner_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        # 1. Zoek ALLE leveranciers die nog geld krijgen (Cash + Onbetaald)
        # We zoeken eerst de lijnen om zeker te zijn dat er bedragen open staan
        unpaid_lines = self.env['sale.order.line'].search([
            ('x_is_paid_out', '=', False),
            ('order_id.state', 'in', ['sale', 'done']),
            ('product_id.submission_id.payout_method', '=', 'cash'),
            ('product_id.submission_id', '!=', False)
        ])

        # Unieke partners uit deze lijnen halen
        partners_to_pay = unpaid_lines.mapped('product_id.submission_id.supplier_id')

        if not partners_to_pay:
            return res # Wordt straks afgevangen in de view of start actie

        res['queue_partner_ids'] = [(6, 0, partners_to_pay.ids)]

        # 2. Setup de eerste partner alvast
        first_partner = partners_to_pay[0]
        data = self._prepare_partner_data(first_partner, unpaid_lines)
        res.update(data)

        return res

    def _prepare_partner_data(self, partner, all_unpaid_lines=None):
        """ Hulpfunctie om de view velden te vullen voor een specifieke partner """
        if not all_unpaid_lines:
            # Zoek opnieuw als we geen cache hebben (tijdens de loop)
            all_unpaid_lines = self.env['sale.order.line'].search([
                ('x_is_paid_out', '=', False),
                ('order_id.state', 'in', ['sale', 'done']),
                ('product_id.submission_id.supplier_id', '=', partner.id),
                ('product_id.submission_id.payout_method', '=', 'cash')
            ])
        else:
            # Filter uit de bestaande set
            all_unpaid_lines = all_unpaid_lines.filtered(
                lambda l: l.product_id.submission_id.supplier_id == partner
            )

        amount = sum(all_unpaid_lines.mapped('x_computed_commission'))

        # Genereer QR
        qr_image = self._generate_qr(partner, amount)

        return {
            'current_partner_id': partner.id,
            'line_ids': [(6, 0, all_unpaid_lines.ids)],
            'total_amount': amount,
            'currency_id': partner.currency_id.id or self.env.company.currency_id.id,
            'qr_image': qr_image
        }

    def _generate_qr(self, partner, amount):
        if not segno: return False
        if not partner.bank_ids: return False # Geen QR als geen bank

        iban = partner.bank_ids[0].acc_number.replace(' ', '').upper()
        bic = partner.bank_ids[0].bank_id.bic or ''
        name = partner.name[:70]
        comm = f"Uitbetaling Otters en Flamingo's. Dankjewel voor je vertrouwen. Marleen"

        qr_content = f"BCD\n002\n1\nSCT\n{bic}\n{name}\n{iban}\nEUR{amount:.2f}\n\n\n{comm}"

        buff = io.BytesIO()
        try:
            qr = segno.make(qr_content, error='M')
            qr.save(buff, kind='png', scale=4)
            return base64.b64encode(buff.getvalue())
        except:
            return False

    def action_pay_and_next(self):
        """ Markeer als betaald en laad de volgende """
        self.ensure_one()

        # 1. MARKEER HUIDIGE ALS BETAALD
        if self.line_ids:
            self.line_ids.write({
                'x_is_paid_out': True,
                'x_payout_date': fields.Date.context_today(self),
                'x_fixed_commission': 0 # Wordt normaal door compute gedaan, maar voor zekerheid
            })
            # Odoo's rapport berekent commissie dynamisch tenzij vastgelegd.
            # We moeten de berekende commissie vastleggen!
            for line in self.line_ids:
                amount = line.price_total * line.product_id.submission_id.payout_percentage
                line.x_fixed_commission = amount

        # 2. VERWIJDER HUIDIGE UIT DE WACHTRIJ
        self.write({'queue_partner_ids': [(3, self.current_partner_id.id)]})

        # 3. LADEN DE VOLGENDE (OF STOPPEN)
        return self._load_next_step()

    def action_skip_and_next(self):
        """ Sla over (doe niets met data) en laad de volgende """
        self.ensure_one()
        # Gewoon uit de wachtrij halen
        self.write({'queue_partner_ids': [(3, self.current_partner_id.id)]})
        return self._load_next_step()

    def _load_next_step(self):
        # Is er nog iemand in de rij?
        if not self.queue_partner_ids:
            # KLAAR! Toon regenboog.
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Klaar!',
                    'message': 'Alle geselecteerde leveranciers zijn verwerkt.',
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }

        # Pak de volgende
        next_partner = self.queue_partner_ids[0]

        # Bereken data
        data = self._prepare_partner_data(next_partner)

        # Schrijf data naar DEZE wizard (zodat we in dezelfde popup blijven)
        self.write(data)

        # Herlaad de view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'otters.payout.session.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }