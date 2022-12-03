# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.
import ast

from functools import partial
import logging

from lxml import etree
from lxml.builder import E
from psycopg2 import IntegrityError

from galex.exceptions import AccessError, ValidationError
from galex.tests import common
from galex.tools import mute_logger, view_validation
from galex.addons.base.models.ir_ui_view import (
    transfer_field_to_modifiers, transfer_node_to_modifiers, simplify_modifiers,
)

_logger = logging.getLogger(__name__)


class ViewXMLID(common.TransactionCase):
    def test_model_data_id(self):
        """ Check whether views know their xmlid record. """
        view = self.env.ref('base.view_company_form')
        self.assertTrue(view)
        self.assertTrue(view.model_data_id)
        self.assertEqual(view.model_data_id.complete_name, 'base.view_company_form')

class ViewCase(common.TransactionCase):
    def setUp(self):
        super(ViewCase, self).setUp()
        self.View = self.env['ir.ui.view']

class TestNodeLocator(common.TransactionCase):
    """
    The node locator returns None when it can not find a node, and the first
    match when it finds something (no jquery-style node sets)
    """

    def test_no_match_xpath(self):
        """
        xpath simply uses the provided @expr pattern to find a node
        """
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.foo(), E.bar(), E.baz()),
            E.xpath(expr="//qux"),
        )
        self.assertIsNone(node)

    def test_match_xpath(self):
        bar = E.bar()
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.foo(), bar, E.baz()),
            E.xpath(expr="//bar"),
        )
        self.assertIs(node, bar)

    def test_no_match_field(self):
        """
        A field spec will match by @name against all fields of the view
        """
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.foo(), E.bar(), E.baz()),
            E.field(name="qux"),
        )
        self.assertIsNone(node)

        node = self.env['ir.ui.view'].locate_node(
            E.root(E.field(name="foo"), E.field(name="bar"), E.field(name="baz")),
            E.field(name="qux"),
        )
        self.assertIsNone(node)

    def test_match_field(self):
        bar = E.field(name="bar")
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.field(name="foo"), bar, E.field(name="baz")),
            E.field(name="bar"),
        )
        self.assertIs(node, bar)

    def test_no_match_other(self):
        """
        Non-xpath non-fields are matched by node name first
        """
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.foo(), E.bar(), E.baz()),
            E.qux(),
        )
        self.assertIsNone(node)

    def test_match_other(self):
        bar = E.bar()
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.foo(), bar, E.baz()),
            E.bar(),
        )
        self.assertIs(bar, node)

    def test_attribute_mismatch(self):
        """
        Non-xpath non-field are filtered by matching attributes on spec and
        matched nodes
        """
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.foo(attr='1'), E.bar(attr='2'), E.baz(attr='3')),
            E.bar(attr='5'),
        )
        self.assertIsNone(node)

    def test_attribute_filter(self):
        match = E.bar(attr='2')
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.bar(attr='1'), match, E.root(E.bar(attr='3'))),
            E.bar(attr='2'),
        )
        self.assertIs(node, match)

    def test_version_mismatch(self):
        """
        A @version on the spec will be matched against the view's version
        """
        node = self.env['ir.ui.view'].locate_node(
            E.root(E.foo(attr='1'), version='4'),
            E.foo(attr='1', version='3'),
        )
        self.assertIsNone(node)


class TestViewInheritance(ViewCase):
    def arch_for(self, name, view_type='form', parent=None):
        """ Generates a trivial view of the specified ``view_type``.

        The generated view is empty but ``name`` is set as its root's ``@string``.

        If ``parent`` is not falsy, generates an extension view (instead of
        a root view) replacing the parent's ``@string`` by ``name``

        :param str name: ``@string`` value for the view root
        :param str view_type:
        :param bool parent:
        :return: generated arch
        :rtype: str
        """
        if not parent:
            element = E(view_type, string=name)
        else:
            element = E(view_type,
                E.attribute(name, name='string'),
                position='attributes'
            )
        return etree.tostring(element, encoding='unicode')

    def makeView(self, name, parent=None, arch=None):
        """ Generates a basic ir.ui.view with the provided name, parent and arch.

        If no parent is provided, the view is top-level.

        If no arch is provided, generates one by calling :meth:`~.arch_for`.

        :param str name:
        :param int parent: id of the parent view, if any
        :param str arch:
        :returns: the created view's id.
        :rtype: int
        """
        view = self.View.create({
            'model': self.model,
            'name': name,
            'arch': arch or self.arch_for(name, parent=parent),
            'inherit_id': parent,
            'priority': 5, # higher than default views
        })
        self.view_ids[name] = view
        return view

    def setUp(self):
        super(TestViewInheritance, self).setUp()

        self.patch(self.registry, '_init', False)

        self.model = 'ir.ui.view.custom'
        self.view_ids = {}

        self.a = self.makeView("A")
        self.a1 = self.makeView("A1", self.a.id)
        self.a2 = self.makeView("A2", self.a.id)
        self.a11 = self.makeView("A11", self.a1.id)
        self.a11.mode = 'primary'
        self.makeView("A111", self.a11.id)
        self.makeView("A12", self.a1.id)
        self.makeView("A21", self.a2.id)
        self.a22 = self.makeView("A22", self.a2.id)
        self.makeView("A221", self.a22.id)

        self.b = self.makeView('B', arch=self.arch_for("B", 'tree'))
        self.makeView('B1', self.b.id, arch=self.arch_for("B1", 'tree', parent=self.b))
        self.c = self.makeView('C', arch=self.arch_for("C", 'tree'))
        self.c.write({'priority': 1})

    def test_get_inheriting_views_arch(self):
        self.assertEqual(
            self.view_ids['A'].get_inheriting_views_arch(self.model),
            self.view_ids['A1'] | self.view_ids['A2'] | self.view_ids['A12'] | self.view_ids['A21'] | self.view_ids['A22'] | self.view_ids['A221'])
        self.assertEqual(self.view_ids['A21'].get_inheriting_views_arch(self.model), self.View)
        self.assertEqual(self.view_ids['A11'].get_inheriting_views_arch(self.model), self.view_ids['A111'])

    def test_default_view(self):
        default = self.View.default_view(model=self.model, view_type='form')
        self.assertEqual(default, self.view_ids['A'].id)

        default_tree = self.View.default_view(model=self.model, view_type='tree')
        self.assertEqual(default_tree, self.view_ids['C'].id)

    def test_no_default_view(self):
        self.assertFalse(self.View.default_view(model='does.not.exist', view_type='form'))
        self.assertFalse(self.View.default_view(model=self.model, view_type='graph'))

    def test_no_recursion(self):
        r1 = self.makeView('R1')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            r1.write({'inherit_id': r1.id})

        r2 = self.makeView('R2', r1.id)
        r3 = self.makeView('R3', r2.id)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            r2.write({'inherit_id': r3.id})

        with self.assertRaises(ValidationError), self.cr.savepoint():
            r1.write({'inherit_id': r3.id})

        with self.assertRaises(ValidationError), self.cr.savepoint():
            r1.write({
                'inherit_id': r1.id,
                'arch': self.arch_for('itself', parent=True),
            })

    def test_write_arch(self):
        self.env['res.lang']._activate_lang('fr_FR')

        v = self.makeView("T", arch='<form string="Foo">Bar</form>')
        self.env['ir.translation']._upsert_translations([{
            'type': 'model_terms',
            'name': 'ir.ui.view,arch_db',
            'lang': 'fr_FR',
            'res_id': v.id,
            'src': 'Foo',
            'value': 'Fou',
        }, {
            'type': 'model_terms',
            'name': 'ir.ui.view,arch_db',
            'lang': 'fr_FR',
            'res_id': v.id,
            'src': 'Bar',
            'value': 'Barre',
        }])
        self.assertEqual(v.arch, '<form string="Foo">Bar</form>')

        # modify v to discard translations; this should not invalidate 'arch'!
        v.arch = '<form></form>'
        self.assertEqual(v.arch, '<form></form>')


class TestApplyInheritanceSpecs(ViewCase):
    """ Applies a sequence of inheritance specification nodes to a base
    architecture. IO state parameters (cr, uid, model, context) are used for
    error reporting

    The base architecture is altered in-place.
    """
    def setUp(self):
        super(TestApplyInheritanceSpecs, self).setUp()
        self.base_arch = E.form(
            E.field(name="target"),
            string="Title")

    def test_replace(self):
        spec = E.field(
                E.field(name="replacement"),
                name="target", position="replace")

        self.View.apply_inheritance_specs(self.base_arch, spec)

        self.assertEqual(
            self.base_arch,
            E.form(E.field(name="replacement"), string="Title"))

    def test_delete(self):
        spec = E.field(name="target", position="replace")

        self.View.apply_inheritance_specs(self.base_arch, spec)

        self.assertEqual(
            self.base_arch,
            E.form(string="Title"))

    def test_insert_after(self):
        spec = E.field(
                E.field(name="inserted"),
                name="target", position="after")

        self.View.apply_inheritance_specs(self.base_arch, spec)

        self.assertEqual(
            self.base_arch,
            E.form(
                E.field(name="target"),
                E.field(name="inserted"),
                string="Title"
            ))

    def test_insert_before(self):
        spec = E.field(
                E.field(name="inserted"),
                name="target", position="before")

        self.View.apply_inheritance_specs(self.base_arch, spec)

        self.assertEqual(
            self.base_arch,
            E.form(
                E.field(name="inserted"),
                E.field(name="target"),
                string="Title"))

    def test_insert_inside(self):
        default = E.field(E.field(name="inserted"), name="target")
        spec = E.field(E.field(name="inserted 2"), name="target", position='inside')

        self.View.apply_inheritance_specs(self.base_arch, default)
        self.View.apply_inheritance_specs(self.base_arch, spec)

        self.assertEqual(
            self.base_arch,
            E.form(
                E.field(
                    E.field(name="inserted"),
                    E.field(name="inserted 2"),
                    name="target"),
                string="Title"))

    def test_unpack_data(self):
        spec = E.data(
                E.field(E.field(name="inserted 0"), name="target"),
                E.field(E.field(name="inserted 1"), name="target"),
                E.field(E.field(name="inserted 2"), name="target"),
                E.field(E.field(name="inserted 3"), name="target"),
            )

        self.View.apply_inheritance_specs(self.base_arch, spec)

        self.assertEqual(
            self.base_arch,
            E.form(
                E.field(
                    E.field(name="inserted 0"),
                    E.field(name="inserted 1"),
                    E.field(name="inserted 2"),
                    E.field(name="inserted 3"),
                    name="target"),
                string="Title"))

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_invalid_position(self):
        spec = E.field(
                E.field(name="whoops"),
                name="target", position="serious_series")

        with self.assertRaises(ValueError):
            self.View.apply_inheritance_specs(self.base_arch, spec)

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_incorrect_version(self):
        # Version ignored on //field elements, so use something else
        arch = E.form(E.element(foo="42"))
        spec = E.element(
            E.field(name="placeholder"),
            foo="42", version="7.0")

        with self.assertRaises(ValueError):
            self.View.apply_inheritance_specs(arch, spec)

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_target_not_found(self):
        spec = E.field(name="targut")

        with self.assertRaises(ValueError):
            self.View.apply_inheritance_specs(self.base_arch, spec)


class TestApplyInheritanceWrapSpecs(ViewCase):
    def setUp(self):
        super(TestApplyInheritanceWrapSpecs, self).setUp()
        self.base_arch = E.template(E.div(E.p("Content")))

    def apply_spec(self, spec):
        self.View.apply_inheritance_specs(self.base_arch, spec)

    def test_replace(self):
        spec = E.xpath(
            E.div("$0", {'class': "some"}),
            expr="//p", position="replace")

        self.apply_spec(spec)
        self.assertEqual(
            self.base_arch,
            E.template(E.div(
                E.div(E.p('Content'), {'class': 'some'})
            ))
        )


class TestApplyInheritanceMoveSpecs(ViewCase):
    def setUp(self):
        super(TestApplyInheritanceMoveSpecs, self).setUp()
        self.base_arch = E.template(
            E.div(E.p("Content", {'class': 'some'})),
            E.div({'class': 'target'})
        )
        self.wrapped_arch = E.template(
            E.div("aaaa", E.p("Content", {'class': 'some'}), "bbbb"),
            E.div({'class': 'target'})
        )

    def apply_spec(self, arch, spec):
        self.View.apply_inheritance_specs(arch, spec)

    def test_move_replace(self):
        spec = E.xpath(
            E.xpath(expr="//p", position="move"),
            expr="//div[@class='target']", position="replace")

        self.apply_spec(self.base_arch, spec)
        self.assertEqual(
            self.base_arch,
            E.template(
                E.div(),
                E.p("Content", {'class': 'some'})
            )
        )
        self.apply_spec(self.wrapped_arch, spec)
        self.assertEqual(
            self.wrapped_arch,
            E.template(
                E.div("aaaabbbb"),
                E.p("Content", {'class': 'some'})
            )
        )

    def test_move_inside(self):
        spec = E.xpath(
            E.xpath(expr="//p", position="move"),
            expr="//div[@class='target']", position="inside")

        self.apply_spec(self.base_arch, spec)
        self.assertEqual(
            self.base_arch,
            E.template(
                E.div(),
                E.div(E.p("Content", {'class': 'some'}), {'class': 'target'})
            )
        )
        self.apply_spec(self.wrapped_arch, spec)
        self.assertEqual(
            self.wrapped_arch,
            E.template(
                E.div("aaaabbbb"),
                E.div(E.p("Content", {'class': 'some'}), {'class': 'target'})
            )
        )

    def test_move_before(self):
        spec = E.xpath(
            E.xpath(expr="//p", position="move"),
            expr="//div[@class='target']", position="before")

        self.apply_spec(self.base_arch, spec)
        self.assertEqual(
            self.base_arch,
            E.template(
                E.div(""),
                E.p("Content", {'class': 'some'}),
                E.div({'class': 'target'}),
            )
        )
        self.apply_spec(self.wrapped_arch, spec)
        self.assertEqual(
            self.wrapped_arch,
            E.template(
                E.div("aaaabbbb"),
                E.p("Content", {'class': 'some'}),
                E.div({'class': 'target'}),
            )
        )

    def test_move_after(self):
        spec = E.xpath(
            E.xpath(expr="//p", position="move"),
            expr="//div[@class='target']", position="after")

        self.apply_spec(self.base_arch, spec)
        self.assertEqual(
            self.base_arch,
            E.template(
                E.div(),
                E.div({'class': 'target'}),
                E.p("Content", {'class': 'some'}),
            )
        )
        self.apply_spec(self.wrapped_arch, spec)
        self.assertEqual(
            self.wrapped_arch,
            E.template(
                E.div("aaaabbbb"),
                E.div({'class': 'target'}),
                E.p("Content", {'class': 'some'}),
            )
        )

    def test_move_with_other_1(self):
        # multiple elements with move in first position
        spec = E.xpath(
            E.xpath(expr="//p", position="move"),
            E.p("Content2", {'class': 'new_p'}),
            expr="//div[@class='target']", position="after")

        self.apply_spec(self.base_arch, spec)
        self.assertEqual(
            self.base_arch,
            E.template(
                E.div(),
                E.div({'class': 'target'}),
                E.p("Content", {'class': 'some'}),
                E.p("Content2", {'class': 'new_p'}),
            )
        )

    def test_move_with_other_2(self):
        # multiple elements with move in last position
        spec = E.xpath(
            E.p("Content2", {'class': 'new_p'}),
            E.xpath(expr="//p", position="move"),
            expr="//div[@class='target']", position="after")

        self.apply_spec(self.wrapped_arch, spec)
        self.assertEqual(
            self.wrapped_arch,
            E.template(
                E.div("aaaabbbb"),
                E.div({'class': 'target'}),
                E.p("Content2", {'class': 'new_p'}),
                E.p("Content", {'class': 'some'}),
            )
        )

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_incorrect_move_1(self):
        # cannot move an inexisting element
        spec = E.xpath(
            E.xpath(expr="//p[@name='none']", position="move"),
            expr="//div[@class='target']", position="after")

        with self.assertRaises(ValueError):
            self.apply_spec(self.base_arch, spec)

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_incorrect_move_2(self):
        # move xpath cannot contain any children
        spec = E.xpath(
            E.xpath(E.p("Content2", {'class': 'new_p'}), expr="//p", position="move"),
            expr="//div[@class='target']", position="after")

        with self.assertRaises(ValueError):
            self.apply_spec(self.base_arch, spec)

    def test_incorrect_move_3(self):
        # move won't be correctly applied if not a direct child of an xpath
        spec = E.xpath(
            E.div(E.xpath(E.p("Content2", {'class': 'new_p'}), expr="//p", position="move"), {'class': 'wrapper'}),
            expr="//div[@class='target']", position="after")

        self.apply_spec(self.base_arch, spec)
        self.assertEqual(
            self.base_arch,
            E.template(
                E.div(E.p("Content", {'class': 'some'})),
                E.div({'class': 'target'}),
                E.div(E.xpath(E.p("Content2", {'class': 'new_p'}), expr="//p", position="move"), {'class': 'wrapper'}),
            )
        )


class TestApplyInheritedArchs(ViewCase):
    """ Applies a sequence of modificator archs to a base view
    """


class TestNoModel(ViewCase):
    def test_create_view_nomodel(self):
        view = self.View.create({
            'name': 'dummy',
            'arch': '<template name="foo"/>',
            'inherit_id': False,
            'type': 'qweb',
        })
        fields = ['name', 'arch', 'type', 'priority', 'inherit_id', 'model']
        [data] = view.read(fields)
        self.assertEqual(data, {
            'id': view.id,
            'name': 'dummy',
            'arch': '<template name="foo"/>',
            'type': 'qweb',
            'priority': 16,
            'inherit_id': False,
            'model': False,
        })

    text_para = E.p("", {'class': 'legalese'})
    arch = E.body(
        E.div(
            E.h1("Title"),
            id="header"),
        E.p("Welcome!"),
        E.div(
            E.hr(),
            text_para,
            id="footer"),
        {'class': "index"},)

    def test_qweb_translation(self):
        """
        Test if translations work correctly without a model
        """
        self.env['res.lang']._activate_lang('fr_FR')
        ARCH = '<template name="foo">%s</template>'
        TEXT_EN = "Copyright copyrighter"
        TEXT_FR = u"Copyrighter, tous droits réservés"
        view = self.View.create({
            'name': 'dummy',
            'arch': ARCH % TEXT_EN,
            'inherit_id': False,
            'type': 'qweb',
        })
        self.env['ir.translation'].create({
            'type': 'model_terms',
            'name': 'ir.ui.view,arch_db',
            'res_id': view.id,
            'lang': 'fr_FR',
            'src': TEXT_EN,
            'value': TEXT_FR,
        })
        view = view.with_context(lang='fr_FR')
        self.assertEqual(view.arch, ARCH % TEXT_FR)


class TestTemplating(ViewCase):
    def setUp(self):
        super(TestTemplating, self).setUp()
        self.patch(self.registry, '_init', False)

    def test_branding_inherit(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """<root>
                <item order="1"/>
            </root>
            """
        })
        view2 = self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """<xpath expr="//item" position="before">
                <item order="2"/>
            </xpath>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']

        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        [initial] = arch.xpath('//item[@order=1]')
        self.assertEqual(
            str(view1.id),
            initial.get('data-oe-id'),
            "initial should come from the root view")
        self.assertEqual(
            '/root[1]/item[1]',
            initial.get('data-oe-xpath'),
            "initial's xpath should be within the root view only")

        [second] = arch.xpath('//item[@order=2]')
        self.assertEqual(
            str(view2.id),
            second.get('data-oe-id'),
            "second should come from the extension view")

    def test_branding_inherit_replace_node(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """<hello>
                <world></world>
                <world><t t-esc="hello"/></world>
                <world></world>
            </hello>
            """
        })
        self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """<xpath expr="/hello/world[1]" position="replace">
                <world>Is a ghetto</world>
                <world>Wonder when I'll find paradise</world>
            </xpath>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']

        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        # First world - has been replaced by inheritance
        [initial] = arch.xpath('/hello[1]/world[1]')
        self.assertEqual(
            '/xpath/world[1]',
            initial.get('data-oe-xpath'),
            'Inherited nodes have correct xpath')

        # Second world added by inheritance
        [initial] = arch.xpath('/hello[1]/world[2]')
        self.assertEqual(
            '/xpath/world[2]',
            initial.get('data-oe-xpath'),
            'Inherited nodes have correct xpath')

        # Third world - is not editable
        [initial] = arch.xpath('/hello[1]/world[3]')
        self.assertFalse(
            initial.get('data-oe-xpath'),
            'node containing t-esc is not branded')

        # The most important assert
        # Fourth world - should have a correct oe-xpath, which is 3rd in main view
        [initial] = arch.xpath('/hello[1]/world[4]')
        self.assertEqual(
            '/hello[1]/world[3]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

    def test_branding_inherit_replace_node2(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """<hello>
                <world></world>
                <world><t t-esc="hello"/></world>
                <world></world>
            </hello>
            """
        })
        self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """<xpath expr="/hello/world[1]" position="replace">
                <war>Is a ghetto</war>
                <world>Wonder when I'll find paradise</world>
            </xpath>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']

        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        [initial] = arch.xpath('/hello[1]/war[1]')
        self.assertEqual(
            '/xpath/war',
            initial.get('data-oe-xpath'),
            'Inherited nodes have correct xpath')

        # First world: from inheritance
        [initial] = arch.xpath('/hello[1]/world[1]')
        self.assertEqual(
            '/xpath/world',
            initial.get('data-oe-xpath'),
            'Inherited nodes have correct xpath')

        # Second world - is not editable
        [initial] = arch.xpath('/hello[1]/world[2]')
        self.assertFalse(
            initial.get('data-oe-xpath'),
            'node containing t-esc is not branded')

        # The most important assert
        # Third world - should have a correct oe-xpath, which is 3rd in main view
        [initial] = arch.xpath('/hello[1]/world[3]')
        self.assertEqual(
            '/hello[1]/world[3]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

    def test_branding_inherit_remove_node(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            # The t-esc node is to ensure branding is distributed to both
            # <world/> elements from the start
            'arch': """
                <hello>
                    <world></world>
                    <world></world>

                    <t t-esc="foo"/>
                </hello>
            """
        })
        self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <xpath expr="/hello/world[1]" position="replace"/>
                </data>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']

        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        # Only remaining world but still the second in original view
        [initial] = arch.xpath('/hello[1]/world[1]')
        self.assertEqual(
            '/hello[1]/world[2]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

    def test_branding_inherit_remove_node2(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """
                <hello>
                    <world></world>
                    <world></world>
                </hello>
            """
        })
        self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <xpath expr="/hello/world[1]" position="replace"/>
                </data>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']

        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        # Note: this test is a variant of the test_branding_inherit_remove_node
        # -> in this case, we expect the branding to not be distributed on the
        # <hello/> element anymore but on the only remaining world.
        [initial] = arch.xpath('/hello[1]')
        self.assertIsNone(
            initial.get('data-oe-model'),
            "The inner content of the root was xpath'ed, it should not receive branding anymore")

        # Only remaining world but still the second in original view
        [initial] = arch.xpath('/hello[1]/world[1]')
        self.assertEqual(
            '/hello[1]/world[2]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

    def test_branding_inherit_multi_replace_node(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """
                <hello>
                    <world class="a"></world>
                    <world class="b"></world>
                    <world class="c"></world>
                </hello>
            """
        })
        view2 = self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <xpath expr="//world" position="replace">
                        <world class="new_a"></world>
                        <world class="z"></world>
                    </xpath>
                </data>
            """
        })
        self.View.create({  # Inherit from the child view and target the added element
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view2.id,
            'arch': """
                <data>
                    <xpath expr="//world[hasclass('new_a')]" position="replace">
                        <world class="another_new_a"></world>
                    </xpath>
                </data>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        # Check if the replacement inside the child view did not mess up the
        # branding of elements in that child view
        [initial] = arch.xpath('//world[hasclass("z")]')
        self.assertEqual(
            '/data/xpath/world[2]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

        # Check if the replacement of the first worlds did not mess up the
        # branding of the last world.
        [initial] = arch.xpath('//world[hasclass("c")]')
        self.assertEqual(
            '/hello[1]/world[3]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

    def test_branding_inherit_multi_replace_node2(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """
                <hello>
                    <world class="a"></world>
                    <world class="b"></world>
                    <world class="c"></world>
                </hello>
            """
        })
        self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <xpath expr="//world" position="replace">
                        <world class="new_a"></world>
                        <world class="z"></world>
                    </xpath>
                </data>
            """
        })
        self.View.create({  # Inherit from the parent view but actually target
                            # the element added by the first child view
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <xpath expr="//world" position="replace">
                        <world class="another_new_a"></world>
                    </xpath>
                </data>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        # Check if the replacement inside the child view did not mess up the
        # branding of elements in that child view
        [initial] = arch.xpath('//world[hasclass("z")]')
        self.assertEqual(
            '/data/xpath/world[2]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

        # Check if the replacement of the first worlds did not mess up the
        # branding of the last world.
        [initial] = arch.xpath('//world[hasclass("c")]')
        self.assertEqual(
            '/hello[1]/world[3]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

    def test_branding_inherit_remove_added_from_inheritance(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """
                <hello>
                    <world class="a"></world>
                    <world class="b"></world>
                </hello>
            """
        })
        view2 = self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            # Note: class="x" instead of t-field="x" in this arch, should lead
            # to the same result that this test is ensuring but was actually
            # a different case in old stable versions.
            'arch': """
                <data>
                    <xpath expr="//world[hasclass('a')]" position="after">
                        <world t-field="x"></world>
                        <world class="y"></world>
                    </xpath>
                </data>
            """
        })
        self.View.create({  # Inherit from the child view and target the added element
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view2.id,
            'arch': """
                <data>
                    <xpath expr="//world[@t-field='x']" position="replace"/>
                </data>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        # Check if the replacement inside the child view did not mess up the
        # branding of elements in that child view, should not be the case as
        # that root level branding is not distributed.
        [initial] = arch.xpath('//world[hasclass("y")]')
        self.assertEqual(
            '/data/xpath/world[2]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

        # Check if the child view replacement of added nodes did not mess up
        # the branding of last world in the parent view.
        [initial] = arch.xpath('//world[hasclass("b")]')
        self.assertEqual(
            '/hello[1]/world[2]',
            initial.get('data-oe-xpath'),
            "The node's xpath position should be correct")

    def test_branding_inherit_remove_node_processing_instruction(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """
                <html>
                    <head>
                        <hello></hello>
                    </head>
                    <body>
                        <world></world>
                    </body>
                </html>
            """
        })
        self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <xpath expr="//hello" position="replace"/>
                    <xpath expr="//world" position="replace"/>
                </data>
            """
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)

        head = arch.xpath('//head')[0]
        head_child = head[0]
        self.assertEqual(
            head_child.target,
            'apply-inheritance-specs-node-removal',
            "A node was removed at the start of the <head>, a processing instruction should exist as first child node")
        self.assertEqual(
            head_child.text,
            'hello',
            "The processing instruction should mention the tag of the node that was removed")

        body = arch.xpath('//body')[0]
        body_child = body[0]
        self.assertEqual(
            body_child.target,
            'apply-inheritance-specs-node-removal',
            "A node was removed at the start of the <body>, a processing instruction should exist as first child node")
        self.assertEqual(
            body_child.text,
            'world',
            "The processing instruction should mention the tag of the node that was removed")

        self.View.distribute_branding(arch)

        # Test that both head and body have their processing instruction
        # 'apply-inheritance-specs-node-removal' removed after branding
        # distribution. Note: test head and body separately as the code in
        # charge of the removal is different in each case.
        self.assertEqual(
            len(head),
            0,
            "The processing instruction of the <head> should have been removed")
        self.assertEqual(
            len(body),
            0,
            "The processing instruction of the <body> should have been removed")

    def test_branding_inherit_top_t_field(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """
                <hello>
                    <world></world>
                    <world t-field="a"/>
                    <world></world>
                    <world></world>
                </hello>
            """
        })
        self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <xpath expr="/hello/world[3]" position="after">
                    <world t-field="b"/>
                </xpath>
            """
        })
        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        # First t-field should have an indication of xpath
        [node] = arch.xpath('//*[@t-field="a"]')
        self.assertEqual(
            node.get('data-oe-field-xpath'),
            '/hello[1]/world[2]',
            'First t-field has indication of xpath through dedicated attribute')

        # Second t-field, from inheritance, should also have an indication of xpath
        [node] = arch.xpath('//*[@t-field="b"]')
        self.assertEqual(
            node.get('data-oe-field-xpath'),
            '/xpath/world',
            'Inherited t-field has indication of xpath through dedicated attribute')

        # The most important assert
        # The last world xpath should not have been impacted by the t-field from inheritance
        [node] = arch.xpath('//world[last()]')
        self.assertEqual(
            node.get('data-oe-xpath'),
            '/hello[1]/world[4]',
            "The node's xpath position should be correct")

        # Also test inherit via non-xpath t-field node, direct children of data,
        # is not impacted by the feature
        self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <world t-field="a" position="replace">
                        <world t-field="z"/>
                    </world>
                </data>
            """
        })
        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        node = arch.xpath('//world')[1]
        self.assertEqual(
            node.get('t-field'),
            'z',
            "The node has properly been replaced")

    def test_branding_primary_inherit(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """<root>
                <item order="1"/>
            </root>
            """
        })
        view2 = self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'mode': 'primary',
            'inherit_id': view1.id,
            'arch': """<xpath expr="//item" position="after">
                <item order="2"/>
            </xpath>
            """
        })

        arch_string = view2.with_context(inherit_branding=True).read_combined(['arch'])['arch']

        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        [initial] = arch.xpath('//item[@order=1]')
        self.assertEqual(
            initial.get('data-oe-id'),
            str(view1.id),
            "initial should come from the root view")
        self.assertEqual(
            initial.get('data-oe-xpath'),
            '/root[1]/item[1]',
            "initial's xpath should be within the inherited view only")

        [second] = arch.xpath('//item[@order=2]')
        self.assertEqual(
            second.get('data-oe-id'),
            str(view2.id),
            "second should come from the extension view")
        self.assertEqual(
            second.get('data-oe-xpath'),
            '/xpath/item',
            "second xpath should be on the inheriting view only")

    def test_branding_distribute_inner(self):
        """ Checks that the branding is correctly distributed within a view
        extension
        """
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """<root>
                <item order="1"/>
            </root>"""
        })
        view2 = self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """<xpath expr="//item" position="before">
                <item order="2">
                    <content t-att-href="foo">bar</content>
                </item>
            </xpath>"""
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']

        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        self.assertEqual(
            arch,
            E.root(
                E.item(
                    E.content("bar", {
                        't-att-href': "foo",
                        'data-oe-model': 'ir.ui.view',
                        'data-oe-id': str(view2.id),
                        'data-oe-field': 'arch',
                        'data-oe-xpath': '/xpath/item/content[1]',
                    }), {
                        'order': '2',
                    }),
                E.item({
                    'order': '1',
                    'data-oe-model': 'ir.ui.view',
                    'data-oe-id': str(view1.id),
                    'data-oe-field': 'arch',
                    'data-oe-xpath': '/root[1]/item[1]',
                })
            )
        )

    def test_branding_attribute_groups(self):
        view = self.View.create({
            'name': "Base View",
            'type': 'qweb',
            'arch': """<root>
                <item groups="base.group_no_one"/>
            </root>""",
        })

        arch_string = view.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        self.assertEqual(arch, E.root(E.item({
            'groups': 'base.group_no_one',
            'data-oe-model': 'ir.ui.view',
            'data-oe-id': str(view.id),
            'data-oe-field': 'arch',
            'data-oe-xpath': '/root[1]/item[1]',
        })))

    def test_call_no_branding(self):
        view = self.View.create({
            'name': "Base View",
            'type': 'qweb',
            'arch': """<root>
                <item><span t-call="foo"/></item>
            </root>""",
        })

        arch_string = view.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        self.assertEqual(arch, E.root(E.item(E.span({'t-call': "foo"}))))

    def test_esc_no_branding(self):
        view = self.View.create({
            'name': "Base View",
            'type': 'qweb',
            'arch': """<root>
                <item><span t-esc="foo"/></item>
            </root>""",
        })

        arch_string = view.with_context(inherit_branding=True).read_combined(['arch'])['arch']
        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        self.assertEqual(arch, E.root(E.item(E.span({'t-esc': "foo"}))))

    def test_ignore_unbrand(self):
        view1 = self.View.create({
            'name': "Base view",
            'type': 'qweb',
            'arch': """<root>
                <item order="1" t-ignore="true">
                    <t t-esc="foo"/>
                </item>
            </root>"""
        })
        view2 = self.View.create({
            'name': "Extension",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """<xpath expr="//item[@order='1']" position="inside">
                <item order="2">
                    <content t-att-href="foo">bar</content>
                </item>
            </xpath>"""
        })

        arch_string = view1.with_context(inherit_branding=True).read_combined(['arch'])['arch']

        arch = etree.fromstring(arch_string)
        self.View.distribute_branding(arch)

        self.assertEqual(
            arch,
            E.root(
                E.item(
                    {'t-ignore': 'true', 'order': '1'},
                    E.t({'t-esc': 'foo'}),
                    E.item(
                        {'order': '2'},
                        E.content(
                            {'t-att-href': 'foo'},
                            "bar")
                    )
                )
            ),
            "t-ignore should apply to injected sub-view branding, not just to"
            " the main view's"
        )


class TestViews(ViewCase):

    def test_nonexistent_attribute_removal(self):
        self.View.create({
            'name': 'Test View',
            'model': 'ir.ui.view',
            'inherit_id': self.ref('base.view_view_tree'),
            'arch': """<?xml version="1.0"?>
                        <xpath expr="//field[@name='name']" position="attributes">
                            <attribute name="non_existing_attribute"></attribute>
                        </xpath>
                    """,
        })

    def _insert_view(self, **kw):
        """Insert view into database via a query to passtrough validation"""
        kw.pop('id', None)
        kw.setdefault('mode', 'extension' if kw.get('inherit_id') else 'primary')
        kw.setdefault('active', True)

        keys = sorted(kw)
        fields = ','.join('"%s"' % (k.replace('"', r'\"'),) for k in keys)
        params = ','.join('%%(%s)s' % (k,) for k in keys)

        query = 'INSERT INTO ir_ui_view(%s) VALUES(%s) RETURNING id' % (fields, params)
        self.cr.execute(query, kw)
        return self.cr.fetchone()[0]

    def test_custom_view_validation(self):
        model = 'ir.actions.act_url'
        validate = partial(self.View._validate_custom_views, model)

        # validation of a single view
        vid = self._insert_view(
            name='base view',
            model=model,
            priority=1,
            arch_db="""<?xml version="1.0"?>
                        <tree string="view">
                          <field name="url"/>
                        </tree>
                    """,
        )
        self.assertTrue(validate())     # single view

        # validation of a inherited view
        self._insert_view(
            name='inherited view',
            model=model,
            priority=1,
            inherit_id=vid,
            arch_db="""<?xml version="1.0"?>
                        <xpath expr="//field[@name='url']" position="before">
                          <field name="name"/>
                        </xpath>
                    """,
        )
        self.assertTrue(validate())     # inherited view

        # validation of a second inherited view (depending on 1st)
        self._insert_view(
            name='inherited view 2',
            model=model,
            priority=5,
            inherit_id=vid,
            arch_db="""<?xml version="1.0"?>
                        <xpath expr="//field[@name='name']" position="after">
                          <field name="target"/>
                        </xpath>
                    """,
        )
        self.assertTrue(validate())     # inherited view

    def test_view_inheritance(self):
        view1 = self.View.create({
            'name': "bob",
            'model': 'ir.ui.view',
            'arch': """
                <form string="Base title">
                    <separator name="separator" string="Separator" colspan="4"/>
                    <footer>
                        <button name="action_archive" type="object" string="Next button" class="btn-primary"/>
                        <button string="Skip" special="cancel" class="btn-secondary"/>
                    </footer>
                </form>
            """
        })
        view2 = self.View.create({
            'name': "edmund",
            'model': 'ir.ui.view',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <form position="attributes">
                        <attribute name="string">Replacement title</attribute>
                    </form>
                    <footer position="replace">
                        <footer>
                            <button name="action_archive" type="object" string="New button"/>
                        </footer>
                    </footer>
                    <separator name="separator" position="replace">
                        <p>Replacement data</p>
                    </separator>
                </data>
            """
        })
        view3 = self.View.create({
            'name': 'jake',
            'model': 'ir.ui.view',
            'inherit_id': view1.id,
            'priority': 17,
            'arch': """
                <footer position="attributes">
                    <attribute name="thing">bob tata lolo</attribute>
                    <attribute name="thing" add="bibi and co" remove="tata" separator=" " />
                    <attribute name="otherthing">bob, tata,lolo</attribute>
                    <attribute name="otherthing" remove="tata, bob"/>
                </footer>
            """
        })

        view = self.View.with_context(check_view_ids=[view2.id, view3.id]) \
                        .fields_view_get(view2.id, view_type='form')
        self.assertEqual(view['type'], 'form')
        self.assertEqual(
            etree.fromstring(
                view['arch'],
                parser=etree.XMLParser(remove_blank_text=True)
            ),
            E.form(
                E.p("Replacement data"),
                E.footer(
                    E.button(name="action_archive", type="object", string="New button"),
                    thing="bob lolo bibi and co", otherthing="lolo"
                ),
                string="Replacement title"))

    def test_view_inheritance_text_inside(self):
        """ Test view inheritance when adding elements and text. """
        view1 = self.View.create({
            'name': "alpha",
            'model': 'ir.ui.view',
            'arch': '<form string="F">(<div/>)</form>',
        })
        view2 = self.View.create({
            'name': "beta",
            'model': 'ir.ui.view',
            'inherit_id': view1.id,
            'arch': '<div position="inside">a<p/>b<p/>c</div>',
        })
        view = self.View.with_context(check_view_ids=view2.ids).fields_view_get(view1.id)
        self.assertEqual(view['type'], 'form')
        self.assertEqual(
            view['arch'],
            '<form string="F">(<div>a<p/>b<p/>c</div>)</form>',
        )

    def test_view_inheritance_text_after(self):
        """ Test view inheritance when adding elements and text. """
        view1 = self.View.create({
            'name': "alpha",
            'model': 'ir.ui.view',
            'arch': '<form string="F">(<div/>)</form>',
        })
        view2 = self.View.create({
            'name': "beta",
            'model': 'ir.ui.view',
            'inherit_id': view1.id,
            'arch': '<div position="after">a<p/>b<p/>c</div>',
        })
        view = self.View.with_context(check_view_ids=view2.ids).fields_view_get(view1.id)
        self.assertEqual(view['type'], 'form')
        self.assertEqual(
            view['arch'],
            '<form string="F">(<div/>a<p/>b<p/>c)</form>',
        )

    def test_view_inheritance_text_before(self):
        """ Test view inheritance when adding elements and text. """
        view1 = self.View.create({
            'name': "alpha",
            'model': 'ir.ui.view',
            'arch': '<form string="F">(<div/>)</form>',
        })
        view2 = self.View.create({
            'name': "beta",
            'model': 'ir.ui.view',
            'inherit_id': view1.id,
            'arch': '<div position="before">a<p/>b<p/>c</div>',
        })
        view = self.View.with_context(check_view_ids=view2.ids).fields_view_get(view1.id)
        self.assertEqual(view['type'], 'form')
        self.assertEqual(
            view['arch'],
            '<form string="F">(a<p/>b<p/>c<div/>)</form>',
        )

    def test_view_inheritance_divergent_models(self):
        view1 = self.View.create({
            'name': "bob",
            'model': 'ir.ui.view.custom',
            'arch': """
                <form string="Base title">
                    <separator name="separator" string="Separator" colspan="4"/>
                    <footer>
                        <button name="action_archive" type="object" string="Next button" class="btn-primary"/>
                        <button string="Skip" special="cancel" class="btn-secondary"/>
                    </footer>
                </form>
            """
        })
        view2 = self.View.create({
            'name': "edmund",
            'model': 'ir.ui.view',
            'inherit_id': view1.id,
            'arch': """
                <data>
                    <form position="attributes">
                        <attribute name="string">Replacement title</attribute>
                    </form>
                    <footer position="replace">
                        <footer>
                            <button name="action_unarchive" type="object" string="New button"/>
                        </footer>
                    </footer>
                    <separator name="separator" position="replace">
                        <p>Replacement data</p>
                    </separator>
                </data>
            """
        })
        view3 = self.View.create({
            'name': 'jake',
            'model': 'ir.ui.menu',
            'inherit_id': view1.id,
            'priority': 17,
            'arch': """
                <footer position="attributes">
                    <attribute name="thing">bob</attribute>
                </footer>
            """
        })

        view = self.View.with_context(check_view_ids=[view2.id, view3.id]) \
                        .fields_view_get(view2.id, view_type='form')
        self.assertEqual(view['type'], 'form')
        self.assertEqual(
            etree.fromstring(
                view['arch'],
                parser=etree.XMLParser(remove_blank_text=True)
            ),
            E.form(
                E.p("Replacement data"),
                E.footer(
                    E.button(name="action_unarchive", type="object", string="New button")),
                string="Replacement title"
            ))

    def test_modifiers(self):
        def _test_modifiers(what, expected):
            modifiers = {}
            if isinstance(what, str):
                node = etree.fromstring(what)
                transfer_node_to_modifiers(node, modifiers)
                simplify_modifiers(modifiers)
                assert modifiers == expected, "%s != %s" % (modifiers, expected)
            elif isinstance(what, dict):
                transfer_field_to_modifiers(what, modifiers)
                simplify_modifiers(modifiers)
                assert modifiers == expected, "%s != %s" % (modifiers, expected)

        _test_modifiers('<field name="a"/>', {})
        _test_modifiers('<field name="a" invisible="1"/>', {"invisible": True})
        _test_modifiers('<field name="a" readonly="1"/>', {"readonly": True})
        _test_modifiers('<field name="a" required="1"/>', {"required": True})
        _test_modifiers('<field name="a" invisible="0"/>', {})
        _test_modifiers('<field name="a" readonly="0"/>', {})
        _test_modifiers('<field name="a" required="0"/>', {})
        # TODO: Order is not guaranteed
        _test_modifiers(
            '<field name="a" invisible="1" required="1"/>',
            {"invisible": True, "required": True},
        )
        _test_modifiers(
            '<field name="a" invisible="1" required="0"/>',
            {"invisible": True},
        )
        _test_modifiers(
            '<field name="a" invisible="0" required="1"/>',
            {"required": True},
        )
        _test_modifiers(
            """<field name="a" attrs="{'invisible': [['b', '=', 'c']]}"/>""",
            {"invisible": [["b", "=", "c"]]},
        )

        # The dictionary is supposed to be the result of fields_get().
        _test_modifiers({}, {})
        _test_modifiers({"invisible": True}, {"invisible": True})
        _test_modifiers({"invisible": False}, {})

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_invalid_field(self):
        self.assertInvalid("""
                <form string="View">
                    <field name="name"/>
                    <field name="not_a_field"/>
                </form>
            """, 'Field "not_a_field" does not exist in model "ir.ui.view"')
        self.assertInvalid("""
                <form string="View">
                    <field/>
                </form>
            """, 'Field tag must have a "name" attribute defined')

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_invalid_subfield(self):
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'invalid subfield',
                'model': 'ir.ui.view',
                'arch': """
                    <form string="View">
                        <field name="name"/>
                        <field name="inherit_children_ids">
                            <tree name="Children">
                                <field name="name"/>
                                <field name="not_a_field"/>
                            </tree>
                        </field>
                    </form>
                """,
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_context_in_view(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_id" context="{'stuff': model}"/>
            </form>
        """
        self.View.create({
            'name': 'valid context',
            'model': 'ir.ui.view',
            'arch': arch % '<field name="model"/>',
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid context',
                'model': 'ir.ui.view',
                'arch': arch % '',
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_context_in_subview(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_id" context="{'stuff': model}"/>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid context',
            'model': 'ir.ui.view',
            'arch': arch % ('', '<field name="model"/>'),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid context',
                'model': 'ir.ui.view',
                'arch': arch % ('', ''),
            })
        with self.assertRaises(ValidationError):
            # field is in view but not in subview
            self.View.create({
                'name': 'valid context',
                'model': 'ir.ui.view',
                'arch': arch % ('<field name="model"/>', ''),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_context_in_subview_with_parent(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_id" context="{'stuff': parent.model}"/>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid context',
            'model': 'ir.ui.view',
            'arch': arch % ('<field name="model"/>', ''),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid context',
                'model': 'ir.ui.view',
                'arch': arch % ('', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid context',
                'model': 'ir.ui.view',
                'arch': arch % ('', '<field name="model"/>'),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_context_in_subsubview_with_parent(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_children_ids">
                            <form string="Children">
                                <field name="name"/>%s
                                <field name="inherit_id" context="{'stuff': parent.parent.model}"/>
                            </form>
                        </field>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid context',
            'model': 'ir.ui.view',
            'arch': arch % ('<field name="model"/>', '', ''),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid context',
                'model': 'ir.ui.view',
                'arch': arch % ('', '', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid context',
                'model': 'ir.ui.view',
                'arch': arch % ('', '<field name="model"/>', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid context',
                'model': 'ir.ui.view',
                'arch': arch % ('', '', '<field name="model"/>'),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_id_case(self):
        # id is read by default and should be usable in domains
        self.assertValid("""
            <form string="View">
                <field name="inherit_id" domain="[('id', '=', False)]"/>
            </form>
        """)

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_boolean_case(self):
        arch = """
            <form string="View">
                %s
                <field name="inherit_id" domain="[(%s, '=', %s)]"/>
            </form>
        """
        self.assertValid(arch % ('', '1', '1'))
        self.assertValid(arch % ('', '0', '1'))
        # self.assertInvalid(arch % ('', '1', '0'))
        self.assertValid(arch % ('<field name="name"/>', '0 if name else 1', '1'))
        # self.assertInvalid(arch % ('<field name="name"/><field name="type"/>', "'tata' if name else 'tutu'", 'type'), 'xxxx')
        self.assertInvalid(
            arch % ('', '0 if name else 1', '1'),
            """Field name used in domain of <field name="inherit_id">  ([(0 if name else 1, '=', 1)]) must be present in view but is missing""",
        )

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_in_view(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_id" domain="[('model', '=', model)]"/>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % '<field name="model"/>',
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % '',
            })

    def test_domain_unknown_field(self):
        self.assertInvalid("""
                <form string="View">
                    <field name="name"/>
                    <field name="inherit_id" domain="[('invalid_field', '=', 'res.users')]"/>
                </form>
            """,
            '''Unknown field "ir.ui.view.invalid_field" in domain of <field name="inherit_id"> "[('invalid_field', '=', 'res.users')]"''',
        )

    def test_domain_field_searchable(self):
        arch = """
            <form string="View">
                <field name="name"/>
                <field name="inherit_id" domain="[('%s', '=', 'test')]"/>
            </form>
        """
        # computed field with a search method
        self.assertValid(arch % 'model_data_id')
        # computed field, not stored, no search
        self.assertInvalid(
            arch % 'xml_id',
            '''Unsearchable field "ir.ui.view.xml_id" in path 'xml_id' in domain of <field name="inherit_id"> ="[('xml_id', '=', 'test')]"''',
        )

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_field_no_comodel(self):
        self.assertInvalid("""
            <form string="View">
                <field name="name" domain="[('test', '=', 'test')]"/>
            </form>
        """, "Domain on non-relational field \"name\" makes no sense (domain:[('test', '=', 'test')])")

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_in_subview(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_id" domain="[('model', '=', model)]"/>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % ('', '<field name="model"/>'),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ('', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ('<field name="model"/>', ''),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_in_subview_with_parent(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_id" domain="[('model', '=', parent.model)]"/>
                    </form>
                </field>%s
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % ('<field name="model"/>', '', ''),
        })
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % ('', '', '<field name="model"/>'),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ('', '', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ('', '<field name="model"/>', ''),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_on_field_in_view(self):
        field = self.env['ir.ui.view']._fields['inherit_id']
        self.patch(field, 'domain', "[('model', '=', model)]")

        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_id"/>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % '<field name="model"/>',
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % '',
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_on_field_in_subview(self):
        field = self.env['ir.ui.view']._fields['inherit_id']
        self.patch(field, 'domain', "[('model', '=', model)]")

        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_id"/>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % ('', '<field name="model"/>'),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ('', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ('<field name="model"/>', ''),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_on_field_in_subview_with_parent(self):
        field = self.env['ir.ui.view']._fields['inherit_id']
        self.patch(field, 'domain', "[('model', '=', parent.model)]")

        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_id"/>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % ('<field name="model"/>', ''),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ('', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ('', '<field name="model"/>'),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_on_field_in_noneditable_subview(self):
        field = self.env['ir.ui.view']._fields['inherit_id']
        self.patch(field, 'domain', "[('model', '=', model)]")

        arch = """
            <form string="View">
                <field name="name"/>
                <field name="inherit_children_ids">
                    <tree string="Children"%s>
                        <field name="name"/>
                        <field name="inherit_id"/>
                    </tree>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % '',
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % ' editable="bottom"',
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_on_readonly_field_in_view(self):
        field = self.env['ir.ui.view']._fields['inherit_id']
        self.patch(field, 'domain', "[('model', '=', model)]")

        arch = """
            <form string="View">
                <field name="name"/>
                <field name="inherit_id" readonly="1"/>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch,
        })

        self.patch(field, 'readonly', True)
        arch = """
            <form string="View">
                <field name="name"/>
                <field name="inherit_id"/>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch,
        })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_on_readonly_field_in_subview(self):
        field = self.env['ir.ui.view']._fields['inherit_id']
        self.patch(field, 'domain', "[('model', '=', model)]")

        arch = """
            <form string="View">
                <field name="name"/>
                <field name="inherit_children_ids"%s>
                    <form string="Children">
                        <field name="name"/>
                        <field name="inherit_id"/>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid domain',
            'model': 'ir.ui.view',
            'arch': arch % ' readonly="1"',
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid domain',
                'model': 'ir.ui.view',
                'arch': arch % '',
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_modifier_attribute_is_boolean(self):
        arch = """
            <form string="View">
                <field name="name" readonly="%s"/>
            </form>
        """
        self.assertValid(arch % '1')
        self.assertValid(arch % '0')
        self.assertValid(arch % 'True')
        self.assertInvalid(
            arch % "[('model', '=', '1')]",
            "Attribute readonly evaluation expects a boolean, got [('model', '=', '1')]",
        )

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_in_filter(self):
        arch = """
            <search string="Search">
                <field name="%s"/>
                <filter string="Dummy" name="draft" domain="[('%s', '=', 'dummy')]"/>
            </search>
        """
        self.assertValid(arch % ('name', 'name'))
        self.assertValid(arch % ('name', 'inherit_children_ids.name'))
        self.assertInvalid(
            arch % ('invalid_field', 'name'),
            'Field "invalid_field" does not exist in model "ir.ui.view"',
        )
        self.assertInvalid(
            arch % ('name', 'invalid_field'),
            """Unknown field "ir.ui.view.invalid_field" in domain of <filter name="draft"> "[('invalid_field', '=', 'dummy')]""",
        )
        self.assertInvalid(
            arch % ('name', 'inherit_children_ids.invalid_field'),
            """Unknown field "ir.ui.view.invalid_field" in domain of <filter name="draft"> "[('inherit_children_ids.invalid_field', '=', 'dummy')]""",
        )
        # todo add check for non searchable fields and group by

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_group_by_in_filter(self):
        arch = """
            <search string="Search">
                <filter string="Date" name="month" domain="[]" context="{'group_by':'%s'}"/>
            </search>
        """
        self.assertValid(arch % 'name')
        self.assertInvalid(
            arch % 'invalid_field',
            """Unknown field "invalid_field" in "group_by" value in context="{'group_by':'invalid_field'}""",
        )

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_domain_invalid_in_filter(self):
        # invalid domain: it should be a list of tuples
        self.assertInvalid(
            """ <search string="Search">
                    <filter string="Dummy" name="draft" domain="['name', '=', 'dummy']"/>
                </search>
            """,
            """Invalid domain format while checking ['name', '=', 'dummy'] in domain of <filter name="draft">""",
        )

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_searchpanel(self):
        arch = """
            <search>
                %s
                <searchpanel>
                    %s
                    <field name="groups_id" select="multi" domain="[['%s', '=', %s]]" enable_counters="1"/>
                </searchpanel>
            </search>
        """
        self.assertValid(arch % ('', '<field name="inherit_id"/>', 'view_access', 'inherit_id'))
        self.assertInvalid(
            arch % ('<field name="inherit_id"/>', '', 'view_access', 'inherit_id'),
            """Field inherit_id used in domain of <field name="groups_id">  ([['view_access', '=', inherit_id]]) must be present in view but is missing.""",
        )
        self.assertInvalid(
            arch % ('', '<field name="inherit_id"/>', 'view_access', 'view_access'),
            """Field view_access used in domain of <field name="groups_id">  ([['view_access', '=', view_access]]) must be present in view but is missing.""",
        )
        self.assertInvalid(
            arch % ('', '<field name="inherit_id"/>', 'inherit_id', 'inherit_id'),
            """Unknown field "res.groups.inherit_id" in domain of <field name="groups_id"> "[['inherit_id', '=', inherit_id]]""",
        )
        self.assertInvalid(
            arch % ('', '<field name="inherit_id" select="multi"/>', 'view_access', 'inherit_id'),
            """Field inherit_id used in domain of <field name="groups_id">  ([['view_access', '=', inherit_id]]) is present in view but is in select multi.""",
        )

        arch = """
            <search>
                <searchpanel>
                    <field name="inherit_id" enable_counters="1"/>
                </searchpanel>
                <searchpanel>
                    <field name="inherit_id" enable_counters="1"/>
                </searchpanel>
            </search>
        """
        self.assertInvalid(arch, "Search tag can only contain one search panel")

    def test_groups_field(self):
        arch = """
            <form string="View">
                <field name="name" groups="%s"/>
            </form>
        """
        self.assertValid(arch % 'base.group_no_one')
        self.assertWarning(arch % 'base.dummy')

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_attrs_field(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_id"
                       attrs="{'readonly': [('model', '=', 'ir.ui.view')]}"/>
            </form>
        """
        self.View.create({
            'name': 'valid attrs',
            'model': 'ir.ui.view',
            'arch': arch % '<field name="model"/>',
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid attrs',
                'model': 'ir.ui.view',
                'arch': arch % '',
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_attrs_invalid_domain(self):
        arch = """
            <form string="View">
                <field name="name"/>
                <field name="model"/>
                <field name="inherit_id"
                       attrs="{'readonly': [('model', 'ir.ui.view')]}"/>
            </form>
        """
        self.assertInvalid(
            arch,
            """Invalid domain format while checking {'readonly': [('model', 'ir.ui.view')]} in attrs.readonly""",
        )

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_attrs_subfield(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_id"
                               attrs="{'readonly': [('model', '=', 'ir.ui.view')]}"/>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid attrs',
            'model': 'ir.ui.view',
            'arch': arch % ('', '<field name="model"/>'),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid attrs',
                'model': 'ir.ui.view',
                'arch': arch % ('', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid attrs',
                'model': 'ir.ui.view',
                'arch': arch % ('<field name="model"/>', ''),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_attrs_subfield_with_parent(self):
        arch = """
            <form string="View">
                <field name="name"/>%s
                <field name="inherit_children_ids">
                    <form string="Children">
                        <field name="name"/>%s
                        <field name="inherit_id"
                               attrs="{'readonly': [('parent.model', '=', 'ir.ui.view')]}"/>
                    </form>
                </field>
            </form>
        """
        self.View.create({
            'name': 'valid attrs',
            'model': 'ir.ui.view',
            'arch': arch % ('<field name="model"/>', ''),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid attrs',
                'model': 'ir.ui.view',
                'arch': arch % ('', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'valid attrs',
                'model': 'ir.ui.view',
                'arch': arch % ('', '<field name="model"/>'),
            })

    def test_button(self):
        arch = """
            <form>
                <button type="object" name="%s"/>
            </form>
        """
        self.assertValid(arch % 'action_archive', name='valid button name')
        self.assertInvalid(
            arch % 'wtfzzz', 'wtfzzz is not a valid action on ir.ui.view',
            name='button name is not even a method',
        )
        self.assertInvalid(
            arch % '_check_xml',
            '_check_xml on ir.ui.view is private and cannot be called from a button',
            name='button name is a private method',
        )
        self.assertWarning(arch % 'postprocess_and_fields', name='button name is a method that requires extra arguments')
        arch = """
            <form>
                <button type="action" name="%s"/>
            </form>
        """
        self.assertInvalid(arch % 0, 'Action 0 (id: 0) does not exist for button of type action.')
        self.assertInvalid(arch % 'base.random_xmlid', 'Invalid xmlid base.random_xmlid for button of type action')
        self.assertInvalid('<form><button type="action"/></form>', 'Button must have a name')
        self.assertInvalid('<form><button special="dummy"/></form>', "Invalid special 'dummy' in button")
        self.assertValid(arch % 'base.action_server_module_immediate_install')
        self.assertInvalid(arch % 'base.partner_root', "base.partner_root is of type res.partner, expected a subclass of ir.actions.actions")

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_tree(self):
        arch = """
            <tree>
                <field name="name"/>
                <button type='object' name="action_archive"/>
                %s
            </tree>
        """
        self.assertValid(arch % '')
        self.assertInvalid(arch % '<group/>', "Tree child can only have one of field, button, control, groupby, widget, header tag (not group)")

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_tree_groupby(self):
        arch = """
            <tree>
                <field name="name"/>
                <groupby name="%s">
                    <button type="object" name="action_archive"/>
                </groupby>
            </tree>
        """
        self.assertValid(arch % ('model_data_id'))
        self.assertInvalid(arch % ('type'), "Field 'type' found in 'groupby' node can only be of type many2one, found selection")
        self.assertInvalid(arch % ('dummy'), "Field 'dummy' found in 'groupby' node does not exist in model ir.ui.view")

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_tree_groupby_many2one(self):
        arch = """
            <tree>
                <field name="name"/>
                %s
                <groupby name="model_data_id">
                    %s
                    <button type="object" name="action_archive" attrs="{'invisible': [('noupdate', '=', True)]}" string="Button1"/>
                </groupby>
            </tree>
        """
        self.View.create({
            'name': 'valid groupby',
            'model': 'ir.ui.view',
            'arch': arch % ('', '<field name="noupdate"/>'),
        })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'invalid groupby',
                'model': 'ir.ui.view',
                'arch': arch % ('', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'invalid groupby',
                'model': 'ir.ui.view',
                'arch': arch % ('<field name="noupdate"/>', ''),
            })
        with self.assertRaises(ValidationError):
            self.View.create({
                'name': 'invalid groupby',
                'model': 'ir.ui.view',
                'arch': arch % ('', '<field name="noupdate"/><field name="fake_field"/>'),
            })

    @mute_logger('galex.addons.base.models.ir_ui_view')
    def test_check_xml_on_reenable(self):
        view1 = self.View.create({
            'name': 'valid _check_xml',
            'model': 'ir.ui.view',
            'arch': """
                <form string="View">
                    <field name="name"/>
                </form>
            """,
        })
        view2 = self.View.create({
            'name': 'valid _check_xml',
            'model': 'ir.ui.view',
            'inherit_id': view1.id,
            'active': False,
            'arch': """
                <field name="foo" position="after">
                    <field name="bar"/>
                </field>
            """
        })
        with self.assertRaises(ValidationError):
            view2.active = True

        # Re-enabling the view and correcting it at the same time should not raise the `_check_xml` constraint.
        view2.write({
            'active': True,
            'arch': """
                <field name="name" position="after">
                    <span>bar</span>
                </field>
            """,
        })

    def test_for_in_label(self):
        self.assertValid('<form><field name="model"/><label for="model"/></form>')
        self.assertInvalid(
            '<form><field name="model"/><label/></form>',
            """Label tag must contain a "for". To match label style without corresponding field or button, use 'class="o_form_label"'""",
        )
        self.assertInvalid(
            '<form><label for="model"/></form>',
            "Name or id 'model' used in 'label for' must be present in view but is missing.",
        )

    def test_col_colspan_numerical(self):
        self.assertValid('<form><group col="5"></group></form>')
        self.assertInvalid(
            '<form><group col="alpha"></group></form>',
            "'col' value must be an integer (alpha)",
        )
        self.assertValid('<form><div colspan="5"></div></form>')
        self.assertInvalid(
            '<form><div colspan="alpha"></div></form>',
            "'colspan' value must be an integer (alpha)",
        )

    def test_valid_alerts(self):
        self.assertValid('<form><div class="alert alert-success" role="alert"/></form>')
        self.assertValid('<form><div class="alert alert-success" role="alertdialog"/></form>')
        self.assertValid('<form><div class="alert alert-success" role="status"/></form>')
        self.assertWarning('<form><div class="alert alert-success"/></form>')

    def test_valid_prohibited_none_role(self):
        self.assertWarning('<form><div role="none"/></form>')
        self.assertWarning('<form><div role="presentation"/></form>')

    def test_valid_alternative_image_text(self):
        self.assertValid('<form><img src="a" alt="a image"></img></form>')
        self.assertWarning('<form><img src="a"></img></form>')

    def test_valid_accessibility_icon_text(self):
        self.assertWarning(
            '<form><span class="fa fa-warning"/></form>',
            'A <span> with fa class (fa fa-warning) must have title in its tag, parents, descendants or have text'
        )
        self.assertWarning(
            '<form><button icon="fa-warning"/></form>',
            'A button with icon attribute (fa-warning) must have title in its tag, parents, descendants or have text'
        )
        self.assertValid('<form><button icon="fa-warning"/>text</form>')
        self.assertValid('<form><span class="fa fa-warning"/>text</form>')
        self.assertValid('<form>text<span class="fa fa-warning"/></form>')
        self.assertValid('<form><span class="fa fa-warning">text</span></form>')
        self.assertValid('<form><span title="text" class="fa fa-warning"/></form>')
        self.assertValid('<form><span aria-label="text" class="fa fa-warning"/></form>')

    def test_valid_simili_button(self):
        self.assertWarning('<form><a class="btn"/></form>')
        self.assertValid('<form><a class="btn" role="button"/></form>')

    def test_valid_dialog(self):
        self.assertWarning('<form><div class="modal"/></form>')
        self.assertValid('<form><div role="dialog" class="modal"></div></form>')
        self.assertWarning('<form><div class="modal-header"/></form>')
        self.assertValid('<form><header class="modal-header"/></form>')
        self.assertWarning('<form><div class="modal-footer"/></form>')
        self.assertValid('<form><footer class="modal-footer"/></form>')
        self.assertWarning('<form><div class="modal-body"/></form>')
        self.assertValid('<form><main class="modal-body"/></form>')

    def test_valid_simili_dropdown(self):
        self.assertValid('<form><ul class="dropdown-menu" role="menu"></ul></form>')
        self.assertWarning('<form><ul class="dropdown-menu"></ul></form>')

    def test_valid_simili_progressbar(self):
        self.assertValid('<form><div class="o_progressbar" role="progressbar" aria-valuenow="14" aria-valuemin="0" aria-valuemax="100">14%</div></form>')
        self.assertWarning('<form><div class="o_progressbar" aria-valuenow="14" aria-valuemin="0" aria-valuemax="100">14%</div></form>')
        self.assertWarning('<form><div class="o_progressbar" role="progressbar" aria-valuemin="0" aria-valuemax="100">14%</div></form>')
        self.assertWarning('<form><div class="o_progressbar" role="progressbar" aria-valuenow="14" aria-valuemax="100">14%</div></form>')
        self.assertWarning('<form><div class="o_progressbar" role="progressbar" aria-valuenow="14" aria-valuemin="0" >14%</div></form>')

    def test_valid_simili_tabpanel(self):
        self.assertValid('<form><div class="tab-pane" role="tabpanel"/></form>')
        self.assertWarning('<form><div class="tab-pane"/></form>')

    def test_valid_simili_tablist(self):
        self.assertValid('<form><div class="nav-tabs" role="tablist"/></form>')
        self.assertWarning('<form><div class="nav-tabs"/></form>')

    def test_valid_simili_tab(self):
        self.assertValid('<form><a data-toggle="tab" role="tab" aria-controls="test"/></form>')
        self.assertWarning('<form><a data-toggle="tab" aria-controls="test"/></form>')
        self.assertWarning('<form><a data-toggle="tab" role="tab"/></form>')
        self.assertWarning('<form><a data-toggle="tab" role="tab" aria-controls="#test"/></form>')

    def test_valid_focusable_button(self):
        self.assertValid('<form><a class="btn" role="button"/></form>')
        self.assertValid('<form><button class="btn" role="button"/></form>')
        self.assertValid('<form><select class="btn" role="button"/></form>')
        self.assertValid('<form><input type="button" class="btn" role="button"/></form>')
        self.assertValid('<form><input type="submit" class="btn" role="button"/></form>')
        self.assertValid('<form><input type="reset" class="btn" role="button"/></form>')
        self.assertValid('<form><div type="reset" class="btn btn-group" role="button"/></form>')
        self.assertValid('<form><div type="reset" class="btn btn-toolbar" role="button"/></form>')
        self.assertValid('<form><div type="reset" class="btn btn-ship" role="button"/></form>')
        self.assertWarning('<form><div class="btn" role="button"/></form>')
        self.assertWarning('<form><input type="email" class="btn" role="button"/></form>')

    def test_address_view(self):
        # pe_partner_address_form
        address_arch = """<form><div class="o_address_format"><field name="parent_name"/></div></form>"""
        address_view = self.View.create({
            'name': 'view',
            'model': 'res.partner',
            'arch': address_arch,
            'priority': 900,
        })

        # view can be created without address_view
        form_arch = """<form><field name="id"/><div class="o_address_format"><field name="street"/></div></form>"""
        partner_view = self.View.create({
            'name': 'view',
            'model': 'res.partner',
            'arch': form_arch,
        })

        # default view, no address_view defined
        arch = self.env['res.partner'].fields_view_get(view_id=partner_view.id)['arch']
        self.assertIn('"street"', arch)
        self.assertNotIn('"parent_name"', arch)

        # custom view, address_view defined
        self.env.company.country_id.address_view_id = address_view
        arch = self.env['res.partner'].fields_view_get(view_id=partner_view.id)['arch']
        self.assertNotIn('"street"', arch)
        self.assertIn('"parent_name"', arch)
        # weird result: <form> inside a <form>
        self.assertRegex(arch, r"<form>.*<form>.*</form>.*</form>")

    def test_graph_fields(self):
        self.assertValid('<graph string="Graph"><field name="model" type="row"/><field name="inherit_id" type="measure"/></graph>')
        self.assertInvalid(
            '<graph string="Graph"><label for="model"/><field name="model" type="row"/><field name="inherit_id" type="measure"/></graph>',
            'A <graph> can only contains <field> nodes, found a <label>'
        )

    def assertValid(self, arch, name='valid view'):
        self.View.create({
            'name': name,
            'model': 'ir.ui.view',
            'arch': arch,
        })

    def assertInvalid(self, arch, expected_message=None, name='invalid view'):
        with self.assertRaises(ValidationError) as catcher, mute_logger('galex.addons.base.models.ir_ui_view'):
            self.View.create({
                'name': name,
                'model': 'ir.ui.view',
                'arch': arch,
            })
        message = str(catcher.exception.args[0])
        self.assertIn('\nView name: %s\nError context:\n' % name, message)
        if expected_message:
            self.assertIn(expected_message, message)
        else:
            _logger.warning(message)

    def assertWarning(self, arch, expected_message=None, name='invalid view'):
        with self.assertLogs('galex.addons.base.models.ir_ui_view', level="WARNING") as log_catcher:
            self.View.create({
                'name': name,
                'model': 'ir.ui.view',
                'arch': arch,
            })
        self.assertEqual(len(log_catcher.output), 1, "Exactly one warning should be logged")
        message = log_catcher.output[0]
        self.assertIn('\nView name: %s\nError context:\n' % name, message)
        if expected_message:
            self.assertIn(expected_message, message)


class TestViewTranslations(common.SavepointCase):
    # these tests are essentially the same as in test_translate.py, but they use
    # the computed field 'arch' instead of the translated field 'arch_db'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('fr_FR')
        cls.env['res.lang']._activate_lang('nl_NL')
        cls.env['ir.translation']._load_module_terms(['base'], ['fr_FR', 'nl_NL'])

    def create_view(self, archf, terms, **kwargs):
        view = self.env['ir.ui.view'].create({
            'name': 'test',
            'model': 'res.partner',
            'arch': archf % terms,
        })
        # DLE P70: `_sync_terms_translations`, which delete translations for which there is no value, is called sooner than before
        # because it's called in `_write`, which is called by `flush`, which is called by the `search`.
        # `arch_db` is in `_write` instead of `create` because `arch_db` is the inverse of `arch`.
        # We need to flush `arch_db` before creating the translations otherwise the translation for which there is no value will be deleted,
        # while the `test_sync_update` specifically needs empty translations
        view.flush()
        self.env['ir.translation'].create([
            {
                'type': 'model_terms',
                'name': 'ir.ui.view,arch_db',
                'lang': lang,
                'res_id': view.id,
                'src': src,
                'value': val,
                'state': 'translated',
            }
            for lang, trans_terms in kwargs.items()
            for src, val in zip(terms, trans_terms)
        ])
        return view

    def test_sync(self):
        """ Check translations of 'arch' after minor change in source terms. """
        archf = '<form string="X">%s</form>'
        terms_en = ('Bread and cheeze',)
        terms_fr = ('Pain et fromage',)
        terms_nl = ('Brood and kaas',)
        view = self.create_view(archf, terms_en, en_US=terms_en, fr_FR=terms_fr, nl_NL=terms_nl)

        env_nolang = self.env(context={})
        env_en = self.env(context={'lang': 'en_US'})
        env_fr = self.env(context={'lang': 'fr_FR'})
        env_nl = self.env(context={'lang': 'nl_NL'})

        self.assertEqual(view.with_env(env_nolang).arch, archf % terms_en)
        self.assertEqual(view.with_env(env_en).arch, archf % terms_en)
        self.assertEqual(view.with_env(env_fr).arch, archf % terms_fr)
        self.assertEqual(view.with_env(env_nl).arch, archf % terms_nl)

        # modify source term in view (fixed type in 'cheeze')
        terms_en = ('Bread and cheese',)
        view.with_env(env_en).write({'arch': archf % terms_en})

        # check whether translations have been synchronized
        self.assertEqual(view.with_env(env_nolang).arch, archf % terms_en)
        self.assertEqual(view.with_env(env_en).arch, archf % terms_en)
        self.assertEqual(view.with_env(env_fr).arch, archf % terms_fr)
        self.assertEqual(view.with_env(env_nl).arch, archf % terms_nl)

        view = self.create_view(archf, terms_fr, en_US=terms_en, fr_FR=terms_fr, nl_NL=terms_nl)
        # modify source term in view in another language with close term
        new_terms_fr = ('Pains et fromage',)
        view.with_env(env_fr).write({'arch': archf % new_terms_fr})

        # check whether translations have been synchronized
        self.assertEqual(view.with_env(env_nolang).arch, archf % new_terms_fr)
        self.assertEqual(view.with_env(env_en).arch, archf % terms_en)
        self.assertEqual(view.with_env(env_fr).arch, archf % new_terms_fr)
        self.assertEqual(view.with_env(env_nl).arch, archf % terms_nl)

    def test_sync_update(self):
        """ Check translations after major changes in source terms. """
        archf = '<form string="X"><div>%s</div><div>%s</div></form>'
        terms_src = ('Subtotal', 'Subtotal:')
        terms_en = ('', 'Sub total:')
        view = self.create_view(archf, terms_src, en_US=terms_en)

        translations = self.env['ir.translation'].search([
            ('type', '=', 'model_terms'),
            ('name', '=', "ir.ui.view,arch_db"),
            ('res_id', '=', view.id),
        ])
        self.assertEqual(len(translations), 2)

        # modifying the arch should sync existing translations without errors
        new_arch = archf % ('Subtotal', 'Subtotal:<br/>')
        view.write({"arch": new_arch})
        self.assertEqual(view.arch, new_arch)

        translations = self.env['ir.translation'].search([
            ('type', '=', 'model_terms'),
            ('name', '=', "ir.ui.view,arch_db"),
            ('res_id', '=', view.id),
        ])
        # 'Subtotal' being src==value, it will be discared
        # 'Subtotal:' will be discarded as it match 'Subtotal' instead of 'Subtotal:<br/>'
        self.assertEqual(len(translations), 0)

    def test_cache_consistency(self):
        view = self.env["ir.ui.view"].create({
            "name": "test_translate_xml_cache_invalidation",
            "model": "res.partner",
            "arch": "<form><b>content</b></form>",
        })
        view_fr = view.with_context({"lang": "fr_FR"})
        self.assertIn("<b>", view.arch_db)
        self.assertIn("<b>", view.arch)
        self.assertIn("<b>", view_fr.arch_db)
        self.assertIn("<b>", view_fr.arch)

        # write with no lang, and check consistency in other languages
        view.write({"arch": "<form><i>content</i></form>"})
        self.assertIn("<i>", view.arch_db)
        self.assertIn("<i>", view.arch)
        self.assertIn("<i>", view_fr.arch_db)
        self.assertIn("<i>", view_fr.arch)


class ViewModeField(ViewCase):
    """
    This should probably, eventually, be folded back into other test case
    classes, integrating the test (or not) of the mode field to regular cases
    """

    def testModeImplicitValue(self):
        """ mode is auto-generated from inherit_id:
        * inherit_id -> mode=extension
        * not inherit_id -> mode=primary
        """
        view = self.View.create({
            'inherit_id': None,
            'arch': '<qweb/>'
        })
        self.assertEqual(view.mode, 'primary')

        view2 = self.View.create({
            'inherit_id': view.id,
            'arch': '<qweb/>'
        })
        self.assertEqual(view2.mode, 'extension')

        view2.write({'inherit_id': None})
        self.assertEqual(view2.mode, 'primary')

        view2.write({'inherit_id': view.id})
        self.assertEqual(view2.mode, 'extension')

    @mute_logger('galex.sql_db')
    def testModeExplicit(self):
        view = self.View.create({
            'inherit_id': None,
            'arch': '<qweb/>'
        })
        view2 = self.View.create({
            'inherit_id': view.id,
            'mode': 'primary',
            'arch': '<qweb/>'
        })
        self.assertEqual(view.mode, 'primary')
        self.assertEqual(view2.mode, 'primary')

        with self.assertRaises(IntegrityError):
            self.View.create({
                'inherit_id': None,
                'mode': 'extension',
                'arch': '<qweb/>'
            })

    @mute_logger('galex.sql_db')
    def testPurePrimaryToExtension(self):
        """
        A primary view with inherit_id=None can't be converted to extension
        """
        view_pure_primary = self.View.create({
            'inherit_id': None,
            'arch': '<qweb/>'
        })
        with self.assertRaises(IntegrityError):
            view_pure_primary.write({'mode': 'extension'})
            view_pure_primary.flush()

    def testInheritPrimaryToExtension(self):
        """
        A primary view with an inherit_id can be converted to extension
        """
        base = self.View.create({
            'inherit_id': None,
            'arch': '<qweb/>',
        })
        view = self.View.create({
            'inherit_id': base.id,
            'mode': 'primary',
            'arch': '<qweb/>'
        })

        view.write({'mode': 'extension'})

    def testDefaultExtensionToPrimary(self):
        """
        An extension view can be converted to primary
        """
        base = self.View.create({
            'inherit_id': None,
            'arch': '<qweb/>',
        })
        view = self.View.create({
            'inherit_id': base.id,
            'arch': '<qweb/>'
        })

        view.write({'mode': 'primary'})

    def testChangeInheritOfPrimary(self):
        """
        A primary view with an inherit_id must remain primary when changing the inherit_id
        """
        base1 = self.View.create({
            'inherit_id': None,
            'arch': '<qweb/>',
        })
        base2 = self.View.create({
            'inherit_id': None,
            'arch': '<qweb/>',
        })
        view = self.View.create({
            'mode': 'primary',
            'inherit_id': base1.id,
            'arch': '<qweb/>',
        })
        self.assertEqual(view.mode, 'primary')
        view.write({'inherit_id': base2.id})
        self.assertEqual(view.mode, 'primary')


class TestDefaultView(ViewCase):
    def testDefaultViewBase(self):
        self.View.create({
            'inherit_id': False,
            'priority': 10,
            'mode': 'primary',
            'arch': '<qweb/>',
        })
        view2 = self.View.create({
            'inherit_id': False,
            'priority': 1,
            'mode': 'primary',
            'arch': '<qweb/>',
        })

        default = self.View.default_view(False, 'qweb')
        self.assertEqual(
            default, view2.id,
            "default_view should get the view with the lowest priority for "
            "a (model, view_type) pair"
        )

    def testDefaultViewPrimary(self):
        view1 = self.View.create({
            'inherit_id': False,
            'priority': 10,
            'mode': 'primary',
            'arch': '<qweb/>',
        })
        self.View.create({
            'inherit_id': False,
            'priority': 5,
            'mode': 'primary',
            'arch': '<qweb/>',
        })
        view3 = self.View.create({
            'inherit_id': view1.id,
            'priority': 1,
            'mode': 'primary',
            'arch': '<qweb/>',
        })

        default = self.View.default_view(False, 'qweb')
        self.assertEqual(
            default, view3.id,
            "default_view should get the view with the lowest priority for "
            "a (model, view_type) pair in all the primary tables"
        )


class TestViewCombined(ViewCase):
    """
    * When asked for a view, instead of looking for the closest parent with
      inherit_id=False look for mode=primary
    * If root.inherit_id, resolve the arch for root.inherit_id (?using which
      model?), then apply root's inheritance specs to it
    * Apply inheriting views on top
    """

    def setUp(self):
        super(TestViewCombined, self).setUp()

        self.a1 = self.View.create({
            'model': 'a',
            'arch': '<qweb><a1/></qweb>'
        })
        self.a2 = self.View.create({
            'model': 'a',
            'inherit_id': self.a1.id,
            'priority': 5,
            'arch': '<xpath expr="//a1" position="after"><a2/></xpath>'
        })
        self.a3 = self.View.create({
            'model': 'a',
            'inherit_id': self.a1.id,
            'arch': '<xpath expr="//a1" position="after"><a3/></xpath>'
        })
        # mode=primary should be an inheritance boundary in both direction,
        # even within a model it should not extend the parent
        self.a4 = self.View.create({
            'model': 'a',
            'inherit_id': self.a1.id,
            'mode': 'primary',
            'arch': '<xpath expr="//a1" position="after"><a4/></xpath>',
        })

        self.b1 = self.View.create({
            'model': 'b',
            'inherit_id': self.a3.id,
            'mode': 'primary',
            'arch': '<xpath expr="//a1" position="after"><b1/></xpath>'
        })
        self.b2 = self.View.create({
            'model': 'b',
            'inherit_id': self.b1.id,
            'arch': '<xpath expr="//a1" position="after"><b2/></xpath>'
        })

        self.c1 = self.View.create({
            'model': 'c',
            'inherit_id': self.a1.id,
            'mode': 'primary',
            'arch': '<xpath expr="//a1" position="after"><c1/></xpath>'
        })
        self.c2 = self.View.create({
            'model': 'c',
            'inherit_id': self.c1.id,
            'priority': 5,
            'arch': '<xpath expr="//a1" position="after"><c2/></xpath>'
        })
        self.c3 = self.View.create({
            'model': 'c',
            'inherit_id': self.c2.id,
            'priority': 10,
            'arch': '<xpath expr="//a1" position="after"><c3/></xpath>'
        })

        self.d1 = self.View.create({
            'model': 'd',
            'inherit_id': self.b1.id,
            'mode': 'primary',
            'arch': '<xpath expr="//a1" position="after"><d1/></xpath>'
        })

    def test_basic_read(self):
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.a1.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.a1(),
                E.a3(),
                E.a2(),
            ), arch)

    def test_read_from_child(self):
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.a3.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.a1(),
                E.a3(),
                E.a2(),
            ), arch)

    def test_read_from_child_primary(self):
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.a4.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.a1(),
                E.a4(),
                E.a3(),
                E.a2(),
            ), arch)

    def test_cross_model_simple(self):
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.c2.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.a1(),
                E.c3(),
                E.c2(),
                E.c1(),
                E.a3(),
                E.a2(),
            ), arch)

    def test_cross_model_double(self):
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.d1.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.a1(),
                E.d1(),
                E.b2(),
                E.b1(),
                E.a3(),
                E.a2(),
            ), arch)


class TestOptionalViews(ViewCase):
    """
    Tests ability to enable/disable inherited views, formerly known as
    inherit_option_id
    """

    def setUp(self):
        super(TestOptionalViews, self).setUp()
        self.v0 = self.View.create({
            'model': 'a',
            'arch': '<qweb><base/></qweb>',
        })
        self.v1 = self.View.create({
            'model': 'a',
            'inherit_id': self.v0.id,
            'active': True,
            'priority': 10,
            'arch': '<xpath expr="//base" position="after"><v1/></xpath>',
        })
        self.v2 = self.View.create({
            'model': 'a',
            'inherit_id': self.v0.id,
            'active': True,
            'priority': 9,
            'arch': '<xpath expr="//base" position="after"><v2/></xpath>',
        })
        self.v3 = self.View.create({
            'model': 'a',
            'inherit_id': self.v0.id,
            'active': False,
            'priority': 8,
            'arch': '<xpath expr="//base" position="after"><v3/></xpath>'
        })

    def test_applied(self):
        """ mandatory and enabled views should be applied
        """
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.v0.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.base(),
                E.v1(),
                E.v2(),
            )
        )

    def test_applied_state_toggle(self):
        """ Change active states of v2 and v3, check that the results
        are as expected
        """
        self.v2.toggle_active()
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.v0.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.base(),
                E.v1(),
            )
        )

        self.v3.toggle_active()
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.v0.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.base(),
                E.v1(),
                E.v3(),
            )
        )

        self.v2.toggle_active()
        context = {'check_view_ids': self.View.search([]).ids}
        arch = self.v0.with_context(context).read_combined(['arch'])['arch']
        self.assertEqual(
            etree.fromstring(arch),
            E.qweb(
                E.base(),
                E.v1(),
                E.v2(),
                E.v3(),
            )
        )


class TestXPathExtentions(common.BaseCase):
    def test_hasclass(self):
        tree = E.node(
            E.node({'class': 'foo bar baz'}),
            E.node({'class': 'foo bar'}),
            {'class': "foo"})

        self.assertEqual(
            len(tree.xpath('//node[hasclass("foo")]')),
            3)
        self.assertEqual(
            len(tree.xpath('//node[hasclass("bar")]')),
            2)
        self.assertEqual(
            len(tree.xpath('//node[hasclass("baz")]')),
            1)
        self.assertEqual(
            len(tree.xpath('//node[hasclass("foo")][not(hasclass("bar"))]')),
            1)
        self.assertEqual(
            len(tree.xpath('//node[hasclass("foo", "baz")]')),
            1)


class TestQWebRender(ViewCase):

    def test_render(self):
        view1 = self.View.create({
            'name': "dummy",
            'type': 'qweb',
            'arch': """
                <t t-name="base.dummy">
                    <div><span>something</span></div>
                </t>
        """
        })
        view2 = self.View.create({
            'name': "dummy_ext",
            'type': 'qweb',
            'inherit_id': view1.id,
            'arch': """
                <xpath expr="//div" position="inside">
                    <span>another thing</span>
                </xpath>
            """
        })
        view3 = self.View.create({
            'name': "dummy_primary_ext",
            'type': 'qweb',
            'inherit_id': view1.id,
            'mode': 'primary',
            'arch': """
                <xpath expr="//div" position="inside">
                    <span>another primary thing</span>
                </xpath>
            """
        })

        # render view and child view with an id
        content1 = self.env['ir.qweb'].with_context(check_view_ids=[view1.id, view2.id])._render(view1.id)
        content2 = self.env['ir.qweb'].with_context(check_view_ids=[view1.id, view2.id])._render(view2.id)

        self.assertEqual(content1, content2)

        # render view and child view with an xmlid
        self.env.cr.execute("INSERT INTO ir_model_data(name, model, res_id, module)"
                            "VALUES ('dummy', 'ir.ui.view', %s, 'base')" % view1.id)
        self.env.cr.execute("INSERT INTO ir_model_data(name, model, res_id, module)"
                            "VALUES ('dummy_ext', 'ir.ui.view', %s, 'base')" % view2.id)

        content1 = self.env['ir.qweb'].with_context(check_view_ids=[view1.id, view2.id])._render('base.dummy')
        content2 = self.env['ir.qweb'].with_context(check_view_ids=[view1.id, view2.id])._render('base.dummy_ext')

        self.assertEqual(content1, content2)

        # render view and primary extension with an id
        content1 = self.env['ir.qweb'].with_context(check_view_ids=[view1.id, view2.id, view3.id])._render(view1.id)
        content3 = self.env['ir.qweb'].with_context(check_view_ids=[view1.id, view2.id, view3.id])._render(view3.id)

        self.assertNotEqual(content1, content3)

        # render view and primary extension with an xmlid
        self.env.cr.execute("INSERT INTO ir_model_data(name, model, res_id, module)"
                            "VALUES ('dummy_primary_ext', 'ir.ui.view', %s, 'base')" % view3.id)

        content1 = self.env['ir.qweb'].with_context(check_view_ids=[view1.id, view2.id, view3.id])._render('base.dummy')
        content3 = self.env['ir.qweb'].with_context(check_view_ids=[view1.id, view2.id, view3.id])._render('base.dummy_primary_ext')

        self.assertNotEqual(content1, content3)


class TestValidationTools(common.BaseCase):

    def test_get_domain_idents(self):
        res = view_validation.get_domain_identifiers("['|', ('model', '=', parent.model or need_model), ('need_model', '=', False)]")
        self.assertEqual(res, ({'model', 'need_model'}, {'parent.model', 'need_model'}))

    def test_process_2_level_parents(self):
        res = view_validation.get_domain_identifiers("['|', ('model', '=', parent.parent.model)]")
        self.assertEqual(res, ({'model'}, {'parent.parent.model'}))

    def test_get_dict_asts(self):
        res = view_validation.get_dict_asts("{'test': False, 'required': [('model', '!=', False)], 'invisible': ['|', ('model', '=', parent.model or need_model), ('need_model', '=', False)]}")
        self.assertEqual(set(res.keys()), set(['test', 'required', 'invisible']))
        self.assertIsInstance(res['test'], ast.NameConstant)
        self.assertIsInstance(res['required'], ast.List)
        self.assertIsInstance(res['invisible'], ast.List)
        self.assertEqual(view_validation.get_domain_identifiers(res['invisible']), ({'model', 'need_model'}, {'parent.model', 'need_model'}))

    def test_get_expression_identities(self):
        self.assertEqual(
            view_validation.get_variable_names("context_today().strftime('%Y-%m-%d')"),
            set(),
        )
        self.assertEqual(
            view_validation.get_variable_names("field and field[0] or not field2"),
            {'field', 'field2'},
        )
        self.assertEqual(
            view_validation.get_variable_names("context_today().strftime('%Y-%m-%d') or field"),
            {'field'},
        )
        self.assertEqual(
            view_validation.get_variable_names("(datetime.datetime.combine(context_today(), datetime.time(x,y,z)).to_utc()).strftime('%Y-%m-%d %H:%M:%S')"),
            {'x', 'y', 'z'},
        )

class TestAccessRights(common.TransactionCase):

    @common.users('demo')
    def test_access(self):
        # a user can not access directly a view
        with self.assertRaises(AccessError):
            self.env['ir.ui.view'].search([("model", '=', "res.partner"), ('type', '=', 'form')])

        # but can call fields_view_get
        self.env['res.partner'].fields_view_get(view_type='form')

        # unless he does not have access to the model
        with self.assertRaises(AccessError):
            self.env['ir.ui.view'].fields_view_get(view_type='form')

@common.tagged('post_install', '-at_install', '-standard', 'migration')
class TestAllViews(common.TransactionCase):
    def test_views(self):
        views = self.env['ir.ui.view'].with_context(lang=None).search([])
        for index, view in enumerate(views):
            if index % 500 == 0:
                _logger.info('checked %s/%s views', index, len(views))
            with self.subTest(name=view.name):
                view._check_xml()