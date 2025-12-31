import logging

_logger = logging.getLogger(__name__)

# 1. Zoek partners die al minstens 1 inzending hebben gedaan
partners = env['res.partner'].search([
    ('submission_ids', '!=', False)
])

_logger.info(f"START MIGRATIE V2: {len(partners)} partners met inzendingen gevonden.")

count = 0
for partner in partners:
    # 2. Zoek de allerlaatste actieve inzending (niet geannuleerd)
    last_submission = env['otters.consignment.submission'].search([
        ('supplier_id', '=', partner.id),
        ('state', '!=', 'cancel')
    ], order='submission_date desc, id desc', limit=1)

    if last_submission:
        vals = {}

        # 3. Payout Methode & Percentage
        # Check: Is het verschillend? (Of leeg op partner)
        if last_submission.payout_method and partner.x_payout_method != last_submission.payout_method:
            vals['x_payout_method'] = last_submission.payout_method

            # Neem percentages over
            if last_submission.payout_method == 'cash':
                vals['x_cash_payout_percentage'] = last_submission.payout_percentage
            else:
                vals['x_coupon_payout_percentage'] = last_submission.payout_percentage

        # 4. Actie Niet Weerhouden
        # Check: Is het verschillend? (Belangrijk omdat default='donate' is)
        if last_submission.action_unaccepted and partner.x_action_unaccepted != last_submission.action_unaccepted:
            vals['x_action_unaccepted'] = last_submission.action_unaccepted

        # 5. Actie Niet Verkocht
        # Check: Is het verschillend?
        if last_submission.action_unsold and partner.x_action_unsold != last_submission.action_unsold:
            vals['x_action_unsold'] = last_submission.action_unsold

        # 6. Schrijven
        if vals:
            partner.write(vals)
            count += 1

            if count % 50 == 0:
                env.cr.commit()
                _logger.info(f"Migratie V2 bezig... {count} partners bijgewerkt.")

# Finale commit & log
env.cr.commit()
_logger.info(f"✅ MIGRATIE V2 KLAAR: Totaal {count} partners zijn effectief gewijzigd.")