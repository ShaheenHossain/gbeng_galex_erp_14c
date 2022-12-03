galex.define('web.comparison_menu_tests', function (require) {
    "use strict";

    const {
        controlPanel: cpHelpers,
        createControlPanel,
        mock,
    } = require('web.test_utils');

    const { patchDate } = mock;
    const searchMenuTypes = ['filter', 'comparison'];

    QUnit.module('Components', {
        beforeEach() {
            this.fields = {
                birthday: { string: "Birthday", type: "date", store: true, sortable: true },
                date_field: { string: "Date", type: "date", store: true, sortable: true },
                float_field: { string: "Float", type: "float", group_operator: 'sum' },
                foo: { string: "Foo", type: "char", store: true, sortable: true },
            };
            this.cpModelConfig = {
                arch: `
                    <search>
                        <filter name="birthday" date="birthday"/>
                        <filter name="date_field" date="date_field"/>
                    </search>`,
                fields: this.fields,
                searchMenuTypes,
            };
        },
    }, function () {

        QUnit.module('ComparisonMenu');

        QUnit.test('simple rendering', async function (assert) {
            assert.expect(6);

            const unpatchDate = patchDate(1997, 0, 9, 12, 0, 0);
            const params = {
                cpModelConfig: this.cpModelConfig,
                cpProps: { fields: this.fields, searchMenuTypes },
            };
            const controlPanel = await createControlPanel(params);

            assert.containsOnce(controlPanel, ".o_dropdown.o_filter_menu");
            assert.containsNone(controlPanel, ".o_dropdown.o_comparison_menu");

            await cpHelpers.toggleFilterMenu(controlPanel);
            await cpHelpers.toggleMenuItem(controlPanel, "Birthday");
            await cpHelpers.toggleMenuItemOption(controlPanel, "Birthday", "January");

            assert.containsOnce(controlPanel, 'div.o_comparison_menu > button i.fa.fa-adjust');
            assert.strictEqual(controlPanel.el.querySelector('div.o_comparison_menu > button span').innerText.trim(), "Comparison");

            await cpHelpers.toggleComparisonMenu(controlPanel);

            const comparisonOptions = [...controlPanel.el.querySelectorAll(
                '.o_comparison_menu li'
            )];
            assert.strictEqual(comparisonOptions.length, 2);
            assert.deepEqual(
                comparisonOptions.map(e => e.innerText),
                ["Birthday: Previous Period", "Birthday: Previous Year"]
            );

            controlPanel.destroy();
            unpatchDate();
        });

        QUnit.test('activate a comparison works', async function (assert) {
            assert.expect(5);

            const unpatchDate = patchDate(1997, 0, 9, 12, 0, 0);
            const params = {
                cpModelConfig: this.cpModelConfig,
                cpProps: { fields: this.fields, searchMenuTypes },
            };
            const controlPanel = await createControlPanel(params);

            await cpHelpers.toggleFilterMenu(controlPanel);
            await cpHelpers.toggleMenuItem(controlPanel, "Birthday");
            await cpHelpers.toggleMenuItemOption(controlPanel, "Birthday", "January");
            await cpHelpers.toggleComparisonMenu(controlPanel);
            await cpHelpers.toggleMenuItem(controlPanel, "Birthday: Previous Period");

            assert.deepEqual(cpHelpers.getFacetTexts(controlPanel), [
                "Birthday: January 1997",
                "Birthday: Previous Period",
            ]);

            await cpHelpers.toggleFilterMenu(controlPanel);
            await cpHelpers.toggleMenuItem(controlPanel, "Date");
            await cpHelpers.toggleMenuItemOption(controlPanel, "Date", "December");
            await cpHelpers.toggleComparisonMenu(controlPanel);
            await cpHelpers.toggleMenuItem(controlPanel, "Date: Previous Year");

            assert.deepEqual(cpHelpers.getFacetTexts(controlPanel), [
                ["Birthday: January 1997", "Date: December 1996"].join("or"),
                "Date: Previous Year",
            ]);

            await cpHelpers.toggleFilterMenu(controlPanel);
            await cpHelpers.toggleMenuItem(controlPanel, "Date");
            await cpHelpers.toggleMenuItemOption(controlPanel, "Date", "1996");

            assert.deepEqual(cpHelpers.getFacetTexts(controlPanel), [
                "Birthday: January 1997",
            ]);

            await cpHelpers.toggleComparisonMenu(controlPanel);
            await cpHelpers.toggleMenuItem(controlPanel, "Birthday: Previous Year");

            assert.deepEqual(cpHelpers.getFacetTexts(controlPanel), [
                "Birthday: January 1997",
                "Birthday: Previous Year",
            ]);

            await cpHelpers.removeFacet(controlPanel);

            assert.deepEqual(cpHelpers.getFacetTexts(controlPanel), []);

            controlPanel.destroy();
            unpatchDate();
        });

        QUnit.test('no timeRanges key in search query if "comparison" not in searchMenuTypes', async function (assert) {
            assert.expect(1);

            this.cpModelConfig.searchMenuTypes = ['filter'];
            const params = {
                cpModelConfig: this.cpModelConfig,
                cpProps: { fields: this.fields, searchMenuTypes: ['filter'] },
            };
            const controlPanel = await createControlPanel(params);

            await cpHelpers.toggleFilterMenu(controlPanel);
            await cpHelpers.toggleMenuItem(controlPanel, "Birthday");
            await cpHelpers.toggleMenuItemOption(controlPanel, "Birthday", 0);

            assert.notOk("timeRanges" in controlPanel.getQuery());

            controlPanel.destroy();
        });
    });
});
