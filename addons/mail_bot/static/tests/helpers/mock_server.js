galex.define('mail_bot/static/tests/helpers/mock_server.js', function (require) {
"use strict";

const MockServer = require('web.MockServer');

MockServer.include({
    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * @override
     */
    async _performRpc(route, args) {
        if (args.model === 'mail.channel' && args.method === 'init_galexbot') {
            return this._mockMailChannelInitGalexERPBot();
        }
        return this._super(...arguments);
    },

    //--------------------------------------------------------------------------
    // Private Mocked Methods
    //--------------------------------------------------------------------------

    /**
     * Simulates `init_galexbot` on `mail.channel`.
     *
     * @private
     */
    _mockMailChannelInitGalexERPBot() {
        // TODO implement this mock task-2300480
        // and improve test "GalexERPBot initialized after 2 minutes"
    },
});

});
