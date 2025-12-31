/** @odoo-module */

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.ConsignmentPortalSettings = publicWidget.Widget.extend({
    selector: '#consignment_settings_form, #consignment_update_form',

    events: {
        'change input[name="payout_method"]': '_onMethodChange',
        'submit': '_onSubmit',
    },

    start: function () {
        this.$ibanInput = this.$('input[name="x_iban"]');

        this.$errorMsg = this.$('#iban_error_msg, #iban_error_msg_modal');

        this._updateRequiredState();
        return this._super.apply(this, arguments);
    },

    _onMethodChange: function () {
        this._updateRequiredState();
    },

    _updateRequiredState: function () {
        const isCash = this.$('input[name="payout_method"][value="cash"]').is(':checked');

        this.$ibanInput.prop('required', isCash);

        if (!isCash) {
            this.$errorMsg.addClass('d-none');
            this.$ibanInput.removeClass('is-invalid');
        }
    },

    _onSubmit: function (ev) {
        const isCash = this.$('input[name="payout_method"][value="cash"]').is(':checked');

        if (isCash) {
            const ibanVal = this.$ibanInput.val().replace(/\s/g, '');
            const ibanRegex = /^[A-Z]{2}[0-9]{2}[a-zA-Z0-9]{1,30}$/;

            if (!ibanVal || !ibanRegex.test(ibanVal)) {
                ev.preventDefault();
                this.$ibanInput.addClass('is-invalid');
                this.$errorMsg.removeClass('d-none');

                // Focus werkt soms lastig in modals, kleine timeout helpt
                setTimeout(() => { this.$ibanInput.focus(); }, 100);
            } else {
                this.$ibanInput.removeClass('is-invalid');
                this.$errorMsg.addClass('d-none');
            }
        }
    }
});