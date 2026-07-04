# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import unicodedata
import re
import uuid

try:
    import segno
except ImportError:
    segno = False

class PayoutSessionWizard(models.TransientModel):
    _name = 'otters.payout.session.wizard'
    _description = 'Uitbetaal Sessie'

    queue_partner_ids = fields.Many2many('res.partner', string="Wachtrij")
    queue_count = fields.Integer(string="Aantal te gaan", compute='_compute_queue_count')
    current_partner_id = fields.Many2one('res.partner', string="Huidige Leverancier", readonly=True)
    line_ids = fields.Many2many('sale.order.line', string="Te Betalen Items", readonly=True)
    total_amount = fields.Monetary(string="Totaalbedrag", currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    qr_image = fields.Binary("QR Code", readonly=True)
    qr_filename = fields.Char("Bestandsnaam", default="qr.png")

    # --- Status indicatoren voor de interface ---
    payout_method_missing = fields.Boolean(compute='_compute_payout_flags')
    is_cash = fields.Boolean(compute='_compute_payout_flags')
    is_coupon = fields.Boolean(compute='_compute_payout_flags')

    @api.depends('queue_partner_ids')
    def _compute_queue_count(self):
        for w in self:
            w.queue_count = len(w.queue_partner_ids)

    @api.depends('line_ids')
    def _compute_payout_flags(self):
        """ Controleert de exacte status van de openstaande lijnen """
        for w in self:
            methods = w.line_ids.mapped('product_id.submission_id.payout_method')
            w.payout_method_missing = any(not m for m in methods) or not methods
            w.is_cash = 'cash' in methods and not w.payout_method_missing
            w.is_coupon = 'coupon' in methods and not w.payout_method_missing

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        # Zoek ALLE onbetaalde verkooplijnen
        unpaid_lines = self.env['sale.order.line'].search([
            ('x_is_paid_out', '=', False),
            ('order_id.state', 'in', ['sale', 'done']),
            ('qty_delivered', '>', 0),
            ('product_id.submission_id', '!=', False)
        ])

        partners_to_pay = unpaid_lines.mapped('product_id.submission_id.supplier_id')

        if not partners_to_pay:
            return res

        res['queue_partner_ids'] = [(6, 0, partners_to_pay.ids)]

        first_partner = partners_to_pay[0]
        data = self._prepare_partner_data(first_partner, unpaid_lines)
        res.update(data)

        return res

    def _prepare_partner_data(self, partner, all_unpaid_lines=None):
        if not all_unpaid_lines:
            all_unpaid_lines = self.env['sale.order.line'].search([
                ('x_is_paid_out', '=', False),
                ('order_id.state', 'in', ['sale', 'done']),
                ('qty_delivered', '>', 0),
                ('product_id.submission_id.supplier_id', '=', partner.id)
            ])
        else:
            all_unpaid_lines = all_unpaid_lines.filtered(
                lambda l: l.product_id.submission_id.supplier_id == partner
            )

        amount = sum(all_unpaid_lines.mapped('x_computed_commission'))

        # Bereken QR-code bedrag enkel op basis van de 'cash' lijnen van deze partner
        cash_lines = all_unpaid_lines.filtered(lambda l: l.product_id.submission_id.payout_method == 'cash')
        cash_amount = sum(cash_lines.mapped('x_computed_commission'))

        qr_image = self._generate_qr(partner, cash_amount) if cash_amount > 0 else False

        return {
            'current_partner_id': partner.id,
            'line_ids': [(6, 0, all_unpaid_lines.ids)],
            'total_amount': amount,
            'currency_id': partner.currency_id.id or self.env.company.currency_id.id,
            'qr_image': qr_image
        }

    def _clean_qr_text(self, text):
        if not text: return ''
        normalized = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
        return re.sub(r'[^a-zA-Z0-9 \-\.,\']', '', normalized)

    def _generate_qr(self, partner, amount):
        if not segno or not partner.bank_ids: return False
        iban = partner.bank_ids[0].acc_number.replace(' ', '').upper()
        bic = partner.bank_ids[0].bank_id.bic or ''
        name = self._clean_qr_text(partner.name)[:70]
        comm = self._clean_qr_text("Uitbetaling Otters en Flamingo's. Dankjewel voor je vertrouwen. Marleen")
        qr_content = f"BCD\n002\n1\nSCT\n{bic}\n{name}\n{iban}\nEUR{amount:.2f}\n\n\n{comm}"
        buff = io.BytesIO()
        try:
            qr = segno.make(qr_content, error='M')
            qr.save(buff, kind='png', scale=4)
            return base64.b64encode(buff.getvalue())
        except:
            return False

    def action_pay_and_next(self):
        """ Markeer als betaald (en maak automatisch coupons/mails aan indien nodig) """
        self.ensure_one()

        if self.line_ids:
            # --- VEILIGHEIDSCHECK: Is de methode wel ingevuld? ---
            methods = self.line_ids.mapped('product_id.submission_id.payout_method')
            if any(not m for m in methods) or not methods:
                raise UserError(_("Kan deze actie niet uitvoeren: Er ontbreekt een uitbetaalmethode op de inzending. Controleer of dit Cash of Coupon is."))

            # --- 1. LOGICA VOOR WAARDEBONNEN (COUPON) ---
            coupon_lines = self.line_ids.filtered(lambda l: l.product_id.submission_id.payout_method == 'coupon')
            if coupon_lines:
                coupon_amount = sum(coupon_lines.mapped('x_computed_commission'))
                if coupon_amount > 0:

                    # A. Zoek of maak eerst het specifieke product aan met de juiste naam voor het winkelmandje
                    gift_card_product = self.env['product.product'].search([
                        ('name', '=', "Otters en Flamingo's Waardebon"),
                        ('type', '=', 'service')
                    ], limit=1)

                    if not gift_card_product:
                        gift_card_product = self.env['product.product'].create({
                            'name': "Otters en Flamingo's Waardebon",
                            'type': 'service',
                            'taxes_id': False,
                            'list_price': 0,
                        })

                    # B. Zoek of maak het programma "Otters en Flamingo's Waardebonnen"
                    program = self.env['loyalty.program'].search([
                        ('name', '=', "Otters en Flamingo's Waardebonnen"),
                        ('program_type', '=', 'gift_card')
                    ], limit=1)

                    if not program:
                        program = self.env['loyalty.program'].create({
                            'name': "Otters en Flamingo's Waardebonnen",
                            'program_type': 'gift_card',
                            'applies_on': 'future',
                            'trigger': 'auto',
                            'portal_visible': True,
                            'portal_point_name': 'Euro',
                            'currency_id': self.env.company.currency_id.id,
                        })

                    # C. REPARATIE / VERPLICHTE SYNC: Zorg dat de beloning ALTIJD aan dit product hangt
                    reward = self.env['loyalty.reward'].search([('program_id', '=', program.id)], limit=1)
                    if reward:
                        if reward.discount_line_product_id != gift_card_product:
                            reward.write({'discount_line_product_id': gift_card_product.id})
                    else:
                        self.env['loyalty.reward'].create({
                            'program_id': program.id,
                            'reward_type': 'discount',
                            'discount_mode': 'per_point',
                            'discount': 1.0,
                            'discount_line_product_id': gift_card_product.id,
                        })

                    if not self.current_partner_id.email:
                        raise UserError(f"FOUT: Klant '{self.current_partner_id.name}' heeft geen e-mailadres!")

                    coupon_template = self.env.ref('otters_consignment.mail_template_consignment_coupon_payout', raise_if_not_found=False)
                    if not coupon_template:
                        raise UserError("FOUT: Het e-mail sjabloon voor de bon is niet gevonden.")

                    coupon_code = f"OTTERS-{uuid.uuid4().hex[:8].upper()}"
                    card = self.env['loyalty.card'].create({
                        'program_id': program.id,
                        'code': coupon_code,
                        'points': coupon_amount,
                        'partner_id': self.current_partner_id.id,
                    })

                    try:
                        coupon_template.sudo().send_mail(
                            card.id,
                            force_send=True,
                            email_values={'email_to': self.current_partner_id.email}
                        )
                    except Exception as e:
                        raise UserError(f"Oeps! Odoo kon de e-mail voor de bon niet samenstellen. Foutmelding: {e}")

            # --- 2. MARKEER ALLES ALS BETAALD IN DE DATABASE ---
            self.line_ids.write({
                'x_is_paid_out': True,
                'x_payout_date': fields.Date.context_today(self),
            })

            for line in self.line_ids:
                perc = line.product_id.submission_id.payout_percentage
                amount = line.price_total * perc
                line.write({
                    'x_fixed_commission': amount,
                    'x_fixed_percentage': perc
                })

        # Uit de wachtrij halen en volgende laden
        self.write({'queue_partner_ids': [(3, self.current_partner_id.id)]})
        return self._load_next_step()

    def action_skip_and_next(self):
        self.ensure_one()
        self.write({'queue_partner_ids': [(3, self.current_partner_id.id)]})
        return self._load_next_step()

    def _load_next_step(self):
        if not self.queue_partner_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Klaar!',
                    'message': 'Alle geselecteerde leveranciers (cash & coupons) zijn verwerkt.',
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }

        next_partner = self.queue_partner_ids[0]
        data = self._prepare_partner_data(next_partner)
        self.write(data)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'otters.payout.session.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }