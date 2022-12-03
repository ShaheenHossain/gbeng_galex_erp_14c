galex.define('iap.redirect_galex_credit_widget', function(require) {
"use strict";

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');


var IapGalexERPCreditRedirect = AbstractAction.extend({
    template: 'iap.redirect_to_galex_credit',
    events : {
        "click .redirect_confirm" : "galex_redirect",
    },
    init: function (parent, action) {
        this._super(parent, action);
        this.url = action.params.url;
    },

    galex_redirect: function () {
        window.open(this.url, '_blank');
        this.do_action({type: 'ir.actions.act_window_close'});
        // framework.redirect(this.url);
    },

});
core.action_registry.add('iap_galex_credit_redirect', IapGalexERPCreditRedirect);
});
