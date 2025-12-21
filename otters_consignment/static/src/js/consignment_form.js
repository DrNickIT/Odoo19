/** @odoo-module */

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.ConsignmentForm = publicWidget.Widget.extend({
    selector: '#consignment_form', // Zorg dat je <form> dit ID heeft in de XML!

    events: {
        // LET OP: De naam in de database/HTML is 'x_payout_method_temp', niet 'payout_method'
        'change input[name="x_payout_method_temp"]': '_onPayoutMethodChange',
        'click #submit_btn_custom': '_onSubmitClick',
        'mouseenter #av_tooltip_trigger': '_onTooltipEnter',
        'mouseleave #av_tooltip_trigger': '_onTooltipLeave',
    },

    start: function () {
        this.$ibanContainer = this.$('#iban_container');
        this.$ibanInput = this.$('#x_iban');
        this.$ibanConfirm = this.$('#x_iban_confirm');
        this.$errorMsg = this.$('#iban_error');

        // --- 1. DE DRIE CHECKBOXEN ---
        this.$termsCheckbox = this.$('#agreed_terms');           // Algemene voorwaarden
        this.$clothingCheckbox = this.$('#agreed_to_clothing_terms'); // Kleding voorwaarden
        this.$shippingCheckbox = this.$('#agreed_to_shipping_fee');   // 8 euro

        this.$realSubmitBtn = this.$('#real_submit_btn');

        this._toggleIbanVisibility();
        return this._super.apply(this, arguments);
    },

    _onPayoutMethodChange: function () {
        this._toggleIbanVisibility();
    },

    _toggleIbanVisibility: function () {
        // We checken of de radiobutton met ID 'payoutCash' aangevinkt is
        const isCash = this.$('#payoutCash').is(':checked');

        if (isCash) {
            this.$ibanContainer.removeClass('d-none');
            this.$ibanInput.prop('required', true);
            this.$ibanConfirm.prop('required', true);
        } else {
            this.$ibanContainer.addClass('d-none');
            this.$ibanInput.val('').prop('required', false);
            this.$ibanConfirm.val('').prop('required', false);
            this.$errorMsg.addClass('d-none');
        }
    },

    _onSubmitClick: function (ev) {
        ev.preventDefault();
        let isValid = true;

        // --- 2. VALIDATIE VAN DE 3 VINKJES ---

        // Check A: Algemene Voorwaarden
        if (this.$termsCheckbox.length && !this.$termsCheckbox.is(':checked')) {
            this.$termsCheckbox[0].setCustomValidity("Je moet akkoord gaan met de algemene voorwaarden.");
            this.$termsCheckbox[0].reportValidity();
            isValid = false;
        } else {
            if(this.$termsCheckbox.length) this.$termsCheckbox[0].setCustomValidity("");
        }

        // Check B: Kleding Voorwaarden (Alleen als A al goed was, om popup spam te voorkomen)
        if (isValid && this.$clothingCheckbox.length && !this.$clothingCheckbox.is(':checked')) {
            this.$clothingCheckbox[0].setCustomValidity("Je moet akkoord gaan met de kledingvoorwaarden.");
            this.$clothingCheckbox[0].reportValidity();
            isValid = false;
        } else {
            if(this.$clothingCheckbox.length) this.$clothingCheckbox[0].setCustomValidity("");
        }

        // Check C: Verzendkosten
        if (isValid && this.$shippingCheckbox.length && !this.$shippingCheckbox.is(':checked')) {
            this.$shippingCheckbox[0].setCustomValidity("Je moet akkoord gaan met de verzendkostenregel.");
            this.$shippingCheckbox[0].reportValidity();
            isValid = false;
        } else {
            if(this.$shippingCheckbox.length) this.$shippingCheckbox[0].setCustomValidity("");
        }

        // --- 3. IBAN LOGICA ---
        const isCash = this.$('#payoutCash').is(':checked');
        if (isValid && isCash) {
            const ibanVal = this.$ibanInput.val().replace(/\s/g, '');
            const ibanConfirmVal = this.$ibanConfirm.val().replace(/\s/g, '');

            if (ibanVal !== ibanConfirmVal) {
                this._showError("De rekeningnummers komen niet overeen.");
                this.$ibanInput.focus();
                isValid = false;
            } else {
                // Simpele BE IBAN regex, mag je zo strikt maken als je wilt
                const ibanRegex = /^[A-Z]{2}[0-9]{2}[a-zA-Z0-9]{1,30}$/;
                if (!ibanRegex.test(ibanVal)) {
                    this._showError("Dit lijkt geen geldig IBAN nummer.");
                    this.$ibanInput.focus();
                    isValid = false;
                } else {
                    this._hideError();
                }
            }
        }

        if (isValid && !this.$el[0].checkValidity()) {
            this.$el[0].reportValidity();
            isValid = false;
        }

        if (isValid) {
            console.log("Validatie OK -> Verzenden maar!");
            if (this.$realSubmitBtn.length) {
                this.$realSubmitBtn[0].click();
            } else {
                this.$el[0].submit();
            }
        }
    },

    _onTooltipEnter: function () {
        this.$('#hover-av').removeClass('d-none');
    },

    _onTooltipLeave: function () {
        this.$('#hover-av').addClass('d-none');
    },

    _showError: function (msg) {
        this.$errorMsg.text(msg).removeClass('d-none');
    },

    _hideError: function () {
        this.$errorMsg.addClass('d-none');
    }
});