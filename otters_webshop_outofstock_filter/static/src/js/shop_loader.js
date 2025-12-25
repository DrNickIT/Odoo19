/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.OttersShopLoader = publicWidget.Widget.extend({
    selector: '.o_wsale_products_page',
    events: {
        // 1. Product klikken
        'click .oe_product_image a': '_showLoader',
        'click .o_wsale_product_information a': '_showLoader',

        // 2. Navigatie & Sortering
        'click .pagination a': '_showLoader',
        'click .dropdown-menu a[href*="/shop"]': '_showLoader',
        'click .o_wsale_apply_layout': '_showLoader',

        // 3. Filters (Zijbalk) - Uitgebreider
        'change .js_attributes input': '_showLoader', // Checkboxen
        'input .js_attributes input': '_showLoader',  // Range sliders etc
        'click .js_attributes label': '_showLoader',  // Labels

        // 4. Categorieën
        'click .breadcrumb a': '_showLoader',
        'click a[href*="/shop/category/"]': '_showLoader',
        'click a[href="/shop"]': '_showLoader',
    },

    /**
     * @override
     */
    start: function () {
        // HTML toevoegen als die er nog niet is
        if ($('#otters_page_loader').length === 0) {
            $('body').append(`
                <div id="otters_page_loader">
                    <div class="otters_spinner_container">
                        <i class="fa fa-circle-o-notch fa-spin otters_spinner"></i>
                    </div>
                    <span class="otters_text">Even geduld...</span>
                </div>
            `);
        }

        // Loader verbergen als men de 'terug' knop gebruikt
        window.addEventListener('pageshow', () => {
            $('#otters_page_loader').removeClass('active');
        });

        return this._super.apply(this, arguments);
    },

    _showLoader: function (ev) {
        if (ev.ctrlKey || ev.metaKey) { return; }

        const $target = $(ev.currentTarget);
        // Negeer uitklap-knoppen
        if ($target.data('toggle') === 'collapse' || $target.data('bs-toggle') === 'collapse') {
            return;
        }

        // Negeer links die nergens heen gaan
        const href = $target.attr('href');
        if ($target.is('a') && (!href || href === '#' || href.startsWith('javascript'))) {
            return;
        }

        $('#otters_page_loader').addClass('active');
    },
});