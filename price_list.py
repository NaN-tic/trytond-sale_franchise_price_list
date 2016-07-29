# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from copy import deepcopy
from simpleeval import simple_eval
from sql import Null, Literal
from sql.aggregate import Count
from sql.conditionals import Case
from sql.operators import Exists
from decimal import Decimal

from trytond import backend
from trytond.config import config
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.tools import grouped_slice, reduce_ids
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateAction, StateTransition, StateView, \
    Button
from trytond.modules.product import price_digits
from trytond.modules.product_price_list.price_list import decistmt

__all__ = ['Franchise', 'PriceList', 'PriceListLine',
    'FranchisePriceList', 'FranchisePriceListFranchise', 'SetFranchisesStart',
    'SetFranchises', 'OpenFranchisePriceList', 'UpdateFranchisePriceListStart',
    'UpdateFranchisePriceListEnd', 'UpdateFranchisePriceList']
__metaclass__ = PoolMeta
_ZERO = Decimal('0.0')


class Franchise:
    __name__ = 'sale.franchise'

    price_list = fields.Function(fields.Many2One('product.price_list',
            'Price List'),
        'get_price_list')

    def create_price_list(self):
        'Returns a the price list to create for the franchise'
        pool = Pool()
        PriceList = pool.get('product.price_list')
        price_list = PriceList()
        price_list.name = self.name
        price_list.franchise = self
        return price_list

    @classmethod
    def get_price_list(cls, franchises, name):
        pool = Pool()
        PriceList = pool.get('product.price_list')
        table = PriceList.__table__()
        cursor = Transaction().cursor
        franchise_ids = [x.id for x in franchises]
        for sub_ids in grouped_slice(franchise_ids):
            result = dict.fromkeys(franchise_ids, None)
            cursor.execute(*table.select(table.franchise, table.id,
                    where=reduce_ids(table.franchise, sub_ids)))
            result.update(dict(cursor.fetchall()))
        return result


class PriceList:
    __name__ = 'product.price_list'

    franchise = fields.Many2One('sale.franchise', 'Franchise', readonly=True)

    def compute_public_price(self, party, product, unit_price, quantity, uom,
            pattern=None):
        Uom = Pool().get('product.uom')

        if pattern is None:
            pattern = {}

        pattern = pattern.copy()
        pattern['product'] = product and product.id or None
        pattern['quantity'] = Uom.compute_qty(uom, quantity,
            product.default_uom, round=False) if product else quantity

        for line in self.lines:
            if line.match(pattern):
                with Transaction().set_context(
                        self._get_context_price_list_line(party, product,
                            unit_price, quantity, uom)):
                    return line.get_public_price()
        return unit_price

    def compute_all(self, party, product, unit_price, quantity, uom,
            pattern=None):
        Uom = Pool().get('product.uom')

        if pattern is None:
            pattern = {}

        pattern = pattern.copy()
        pattern['product'] = product and product.id or None
        pattern['quantity'] = Uom.compute_qty(uom, quantity,
            product.default_uom, round=False) if product else quantity

        cost_price = product.cost_price

        for line in self.lines:
            if line.match(pattern):
                with Transaction().set_context(
                        self._get_context_price_list_line(party, product,
                            unit_price, quantity, uom)):
                    return (cost_price,
                        line.get_unit_price(), line.get_public_price())
        return (cost_price, unit_price, unit_price)


class PriceListLine:
    __name__ = 'product.price_list.line'
    public_price_formula = fields.Char('Public Price Formula',
        help=('Python expression that will be evaluated with:\n'
            '- unit_price: the original unit_price'))
    franchise_price_list = fields.Many2One('sale.franchise.price_list',
        'Francise Price List', readonly=True, select=True)

    def get_public_price(self):
        '''
        Return public price (as Decimal)
        '''
        context = Transaction().context.copy()
        context['Decimal'] = Decimal
        formula = (self.public_price_formula if self.public_price_formula else
            self.formula)
        return simple_eval(decistmt(formula), **context)

    def get_franchise_price_list(self):
        pool = Pool()
        FranchisePriceList = pool.get('sale.franchise.price_list')
        price_list = FranchisePriceList()
        price_list.franchises = [self.price_list.franchise]
        price_list.product = self.product
        price_list.sale_price = self.get_unit_price()
        price_list.public_price = self.get_public_price()
        return price_list


class FranchisePriceListFranchise(ModelSQL):
    'Franchise Price List - Franchise'
    __name__ = 'sale.franchise.price_list-sale.franchise'

    price_list = fields.Many2One('sale.franchise.price_list',
        'Franchise Price List', required=True, select=True, ondelete='CASCADE')
    franchise = fields.Many2One('sale.franchise', 'Franchise', required=True,
        select=True, ondelete='CASCADE')


class Template:
    __name__ = 'product.template'
    price_list_cost_price = fields.Numeric('Price List Cost Price',
        digits=price_digits, required=True)

    @classmethod
    def create(cls, vlist):
        for values in vlist:
            if 'cost_price' in values:
                values['price_list_cost_price'] = values['cost_price']
        return super(Template, cls).create(vlist)

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        for _, values in zip(actions, actions):
            if 'cost_price' in values:
                values['price_list_cost_price'] = values['cost_price']
        return super(Template, cls).write(*args)


class FranchisePriceList(ModelSQL, ModelView):
    'Franchise Price List'
    __name__ = 'sale.franchise.price_list'

    franchises = fields.Many2Many('sale.franchise.price_list-sale.franchise',
        'price_list', 'franchise', 'Franchises')
    franchise_name = fields.Function(fields.Char('Franchises'),
        'get_franchise_name')
    product = fields.Many2One('product.product', 'Product', required=True)
    product_type = fields.Function(fields.Char('Sale Type'),
        'on_change_with_product_type', searcher='search_product_type')
    quantity = fields.Float('Quantity', digits=(16, Eval('unit_digits', 2)),
            depends=['unit_digits'])
    unit_digits = fields.Function(fields.Integer('Unit Digits'),
        'on_change_with_unit_digits')
    product_cost_price = fields.Numeric('Cost Price', digits=(16, DIGITS),
        required=True)
    sale_percent = fields.Function(fields.Float('Sale %',
            digits=(4, 4)),
        'on_change_with_sale_percent', setter='set_percent')
    sale_price = fields.Numeric('Sale Price', digits=price_digits,
        required=True)
    sale_price_with_vat = fields.Function(fields.Numeric(
            'Sale Price with VAT', digits=price_digits),
        'on_change_with_sale_price_with_vat')
    public_percent = fields.Function(fields.Float('Public %',
            digits=(4, 4)),
        'on_change_with_public_percent')
    public_price = fields.Numeric('Public Price', digits=price_digits,
        required=True)
    price_list_lines = fields.One2Many('product.price_list.line',
        'franchise_price_list', 'Price List Line', readonly=True)
    franchise_is_set = fields.Function(fields.Boolean('Franchise is set'),
        'get_franchise_is_set')
    quantity_is_set = fields.Function(fields.Boolean('Quantity is set'),
        'get_quantity_is_set')

    @classmethod
    def __setup__(cls):
        super(FranchisePriceList, cls).__setup__()
        cls._buttons.update({
                'set_franchises': {}
                })
        cls._error_messages.update({
                'related_price_lists': ('Can not modify line "%s" because it '
                    'has related price list lines. Please duplicate it.')
                })

    @classmethod
    def __register__(cls, module_name):
        pool = Pool()
        Product = pool.get('product.product')
        Template = pool.get('product.template')
        TableHandler = backend.get('TableHandler')

        cursor = Transaction().cursor
        table = cls.__table__()
        product = Product.__table__()
        template = Template.__table__()

        handler = TableHandler(cursor, cls, module_name)
        template_handler = TableHandler(cursor, Template, module_name)
        exists_product_cost_price = handler.column_exist('product_cost_price')
        exists_price_list_cost_price = template_handler.column_exist(
            'price_list_cost_price')

        super(FranchisePriceList, cls).__register__(module_name)

        # Migrate from 3.4.0: product_cost_price from functional to normal
        if exists_price_list_cost_price and not exists_product_cost_price:
            handler = TableHandler(cursor, cls, module_name)
            template_handler = TableHandler(cursor, Template, module_name)
            cursor.execute(*table.update(
                    columns=[table.product_cost_price],
                    values=[template.price_list_cost_price],
                    from_=[product.join(template,
                            condition=(template.id == product.template))],
                    where=(product.id == table.product)))
            template_handler.drop_column('price_list_cost_price')

    def get_rec_name(self, name):
        qty = self.quantity if self.quantity else ''
        return '%s %s %s' % (self.product.rec_name, self.franchise_name, qty)

    @classmethod
    def search_rec_name(cls, name, clause):
        if clause[1].startswith('!') or clause[1].startswith('not '):
            bool_op = 'AND'
        else:
            bool_op = 'OR'
        return [bool_op,
            ('product.rec_name',) + tuple(clause[1:]),
            ('franchises',) + tuple(clause[1:]),
            ]

    def get_franchise_name(self, name):
        return ','.join(x.name for x in self.franchises)

    @fields.depends('product')
    def on_change_with_unit_digits(self, name=None):
        if self.product:
            return self.product.default_uom.digits
        return 2

    @fields.depends('product')
    def on_change_product(self):
        changes = {}
        if self.product:
            changes['product_cost_price'] = self.product.cost_price
            changes['sale_price'] = self.product.list_price
            changes['public_price'] = self.product.list_price
            self.product_cost_price = changes['product_cost_price']
            self.sale_price = changes['sale_price']
            self.public_price = changes['public_price']
            changes['sale_percent'] = self.on_change_with_sale_percent()
            changes['public_percent'] = self.on_change_with_public_percent()
            changes['sale_price_with_vat'] = (
                self.on_change_with_sale_price_with_vat())
        return changes

    @fields.depends('sale_price_percent', 'sale_price_with_vat',
        'public_percent', 'public_price', 'product')
    def on_change_sale_percent(self):
        changes = {}
        sale_price_with_vat = self.on_change_with_sale_price_with_vat()
        if sale_price_with_vat != self.sale_price_with_vat:
            changes['sale_price_with_vat'] = sale_price_with_vat
            self.sale_price_with_vat = sale_price_with_vat
        public_percent = self.on_change_with_public_percent()
        if public_percent != self.public_percent:
            changes['public_percent'] = public_percent
        return changes

    @fields.depends('product_cost_price', 'sale_price')
    def on_change_with_sale_percent(self, name=None):
        if not self.product_cost_price or not self.sale_price:
            return 0.0
        digits = self.__class__.sale_percent.digits[1]
        return round(float((self.sale_price - self.product_cost_price) /
                self.sale_price), digits)

    @fields.depends('product_cost_price', 'sale_percent')
    def on_change_with_sale_price(self):
        if not self.product_cost_price:
            return _ZERO
        if not self.sale_percent:
            return self.product_cost_price
        digits = self.__class__.sale_price.digits[1]
        return (self.product_cost_price / Decimal(1 - self.sale_percent)
            ).quantize(Decimal(str(10 ** - digits)))

    @fields.depends('product', 'sale_price', 'sale_price_percent',
        methods=['sale_price'])
    def on_change_with_sale_price_with_vat(self, name=None):
        pool = Pool()
        Tax = pool.get('account.tax')
        if not self.product or not self.sale_price:
            return _ZERO
        res = Tax.compute(self.product.template.customer_taxes_used,
            self.sale_price, 1.0)
        price = self.on_change_with_sale_price()
        for row in res:
            price += row['amount']
        digits = self.__class__.sale_price_with_vat.digits[1]
        return price.quantize(Decimal(str(10 ** - digits)))

    @fields.depends('sale_price_with_vat', 'public_price',
        methods=['sale_price_with_vat'])
    def on_change_with_public_percent(self, name=None):
        if not self.sale_price_with_vat or not self.public_price:
            return 0.0
        sale_price_with_vat = self.on_change_with_sale_price_with_vat()
        digits = self.__class__.public_percent.digits[1]
        return round(float((self.public_price - sale_price_with_vat) /
                self.public_price), digits)

    @fields.depends('product')
    def on_change_with_product_type(self, name=None):
        if self.product:
            return ','.join(x.rec_name for x in self.product.template.types)
        return ''

    @classmethod
    def search_product_type(cls, name, clause):
        return [tuple(('product.template.types',))
            + tuple(clause[1:])]

    @classmethod
    def set_percent(cls, records, name, value):
        return

    def get_franchise_is_set(self, name):
        return bool(self.franchise)

    @staticmethod
    def order_quantity(tables):
        table, _ = tables[None]
        return [table.quantity == None, table.quantity]

    @staticmethod
    def order_franchise_is_set(tables):
        pool = Pool()
        Relation = pool.get('sale.franchise.price_list-sale.franchise')
        table, _ = tables[None]
        relation = Relation.__table__()
        return [relation.select(Count(relation.franchise),
                where=(relation.price_list == table.id))]

    def get_quantity_is_set(self, name):
        return bool(self.quantity)

    @staticmethod
    def order_quantity_is_set(tables):
        table, _ = tables[None]
        return [Case((table.quantity == Null, -1), else_=table.quantity)]

    @classmethod
    def syncronize(cls):
        'Syncronizes the current values from template information'
        pool = Pool()
        Product = pool.get('product.product')
        to_create = []
        products = Product.search([
                ('template.salable', '=', True),
                ])
        lines = cls.search([
                ('franchises', '=', None),
                ])
        existing = set(l.product for l in lines)
        for missing_product in set(products) - set(existing):
            cost_price_digits = cls.product_cost_price.digits[1]
            cost_price = (missing_product.cost_price or Decimal(0)).quantize(
                Decimal(str(10 ** - cost_price_digits)))
            list_price_digits = cls.sale_price.digits[1]
            list_price = (missing_product.list_price or Decimal(0)).quantize(
                Decimal(str(10 ** - list_price_digits)))
            to_create.append({
                    'product': missing_product.id,
                    'product_cost_price': cost_price,
                    'sale_price': list_price,
                    'public_price': list_price,
                    })
        if to_create:
            cls.create(to_create)

    def create_price_list_line(self):
        pool = Pool()
        Template = pool.get('product.template')
        Line = pool.get('product.price_list.line')
        line = Line()
        line.price_list = None
        line.product = self.product
        digits = Template.list_price.digits[1]
        line.formula = str(self.sale_price.quantize(
                Decimal(str(10 ** - digits))))
        line.public_price_formula = str(self.public_price.quantize(
                Decimal(str(10 ** - digits))))
        line.quantity = self.quantity
        line.franchise_price_list = self
        return line

    @classmethod
    @ModelView.button_action('sale_franchise_price_list.wizard_set_franchises')
    def set_franchises(cls, price_lists):
        pass

    @classmethod
    def write(cls, *args):
        pool = Pool()
        Template = pool.get('product.template')

        actions = iter(args)
        to_check = []
        for lines, values in zip(actions, actions):
            if (values.get('franchises')
                    or values.get('product_cost_price')
                    or values.get('sale_price')):
                to_check.extend(lines)
                if values.get('franchises'):
                    for line in lines:
                        if line.price_list_lines:
                            cls.raise_user_error('related_price_lists',
                                line.rec_name)
        super(FranchisePriceList, cls).write(*args)

        to_create = []
        template_to_write = []
        for line in cls.browse([x.id for x in to_check]):
            if not line.franchises:
                template_to_write.extend(([line.product.template], {
                            'cost_price': line.product_cost_price,
                            'list_price': line.sale_price,
                            }))
                continue
            if not cls.search([
                        ('product', '=', line.product.id),
                        ('franchises', '=', None),
                        ], count=True):
                to_create.append({
                        'product': line.product.id,
                        'product_cost_price': line.product.cost_price,
                        'sale_price': line.product.list_price,
                        'public_price': line.product.list_price,
                        })
        if template_to_write:
            Template.write(*template_to_write)
        if to_create:
            cls.create(to_create)

    @classmethod
    def delete(cls, lines):
        pool = Pool()
        PriceListLine = pool.get('product.price_list.line')
        to_delete = []
        for line in lines:
            to_delete.extend(line.price_list_lines)
        PriceListLine.delete(to_delete)
        super(FranchisePriceList, cls).delete(lines)

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        default.setdefault('price_list_lines', [])
        return super(FranchisePriceList, cls).copy(lines, default=default)


class SetFranchisesStart(ModelView):
    'Set Franchises Start'
    __name__ = 'sale.franchise.price_list.set_franchises.start'

    price_list = fields.Many2One('sale.franchise.price_list', 'Price List',
        readonly=True, required=True)
    category = fields.Many2One('sale.franchise.category', 'Category')
    franchises = fields.Many2Many('sale.franchise', None, None, 'Franchises')


class SetFranchises(Wizard):
    'Set Franchises'
    __name__ = 'sale.franchise.price_list.set_franchises'

    start = StateView('sale.franchise.price_list.set_franchises.start',
        'sale_franchise_price_list.set_franchises_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Update', 'process', 'tryton-ok', default=True),
            ])
    process = StateTransition()

    def default_start(self, fields):
        pool = Pool()
        PriceList = pool.get('sale.franchise.price_list')
        defaults = {}
        context = Transaction().context
        if context.get('active_model') == 'sale.franchise.price_list':
            price_list = PriceList(context.get('active_id'))
            defaults['price_list'] = price_list.id
            defaults['franchises'] = [x.id for x in price_list.franchises]
        return defaults

    def transition_process(self):
        pool = Pool()
        Franchise = pool.get('sale.franchise')
        franchises = self.start.franchises
        if self.start.category:
            for franchise in Franchise.search([
                        ('categories', 'in', [self.start.category.id]),
                        ]):
                if franchise not in franchises:
                    franchises.append(franchise)
        self.start.price_list.franchises = franchises
        self.start.price_list.save()
        return 'end'


class OpenFranchisePriceList(Wizard):
    'Open Franchise Price List'
    __name__ = 'sale.franchise.price_list.open'

    start = StateTransition()
    result = StateAction(
        'sale_franchise_price_list.act_sale_franchise_price_list')

    def transition_start(self):
        pool = Pool()
        FranchisePriceList = pool.get('sale.franchise.price_list')
        FranchisePriceList.syncronize()
        return 'result'


class UpdateFranchisePriceListStart(ModelView):
    'Update Franchise Price List Start'
    __name__ = 'sale.franchise.price_list.update.start'


class UpdateFranchisePriceListEnd(ModelView):
    'Update Franchise Price List End'
    __name__ = 'sale.franchise.price_list.update.end'


class UpdateFranchisePriceList(Wizard):
    'Update Franchise Price List'
    __name__ = 'sale.franchise.price_list.update'

    start = StateView('sale.franchise.price_list.update.start',
        'sale_franchise_price_list.update_price_list_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Update', 'process', 'tryton-ok', default=True),
            ])
    process = StateTransition()
    result = StateView('sale.franchise.price_list.update.end',
        'sale_franchise_price_list.update_price_list_end_view_form', [
            Button('Ok', 'end', 'tryton-ok', default=True),
            ])

    def get_price_lists(self):
        'Get all the price lists available for franchises'
        pool = Pool()
        PriceList = pool.get('product.price_list')
        Franchise = pool.get('sale.franchise')
        to_create = []
        for franchise in Franchise.search([]):
            if not franchise.price_list:
                to_create.append(franchise.create_price_list()._save_values)
        if to_create:
            with Transaction().set_user(0):
                PriceList.create(to_create)
        return PriceList.search([('franchise', '!=', None)])

    def transition_process(self):
        pool = Pool()
        FranchisePriceList = pool.get('sale.franchise.price_list')
        PriceListLine = pool.get('product.price_list.line')
        price_lists = set(self.get_price_lists())
        to_write = []
        to_create = []
        price_list_created = set()

        def get_values_to_write(line, current_line):
            values = {}
            for field in PriceListLine._fields.keys():
                if (field in ['id', 'price_list'] or
                        not hasattr(line, field)):
                    continue
                value = getattr(line, field)
                if value != getattr(current_line, field):
                    values[field] = value
            if values:
                return ([current_line], values)
            return []

        for seq, franchise_price_list in enumerate(
                FranchisePriceList.search([],
                    order=[
                        ('franchise_is_set', 'DESC'),
                        ('quantity_is_set', 'DESC'),
                        ])):
            line = franchise_price_list.create_price_list_line()
            line.sequence = seq
            done = set()
            for current_line in franchise_price_list.price_list_lines:
                to_write.extend(get_values_to_write(line, current_line))
                done.add(current_line.price_list)
            if franchise_price_list.franchises:
                for franchise in franchise_price_list.franchises:
                    line.price_list = franchise.price_list
                    key = (line.product, line.price_list, line.quantity)
                    price_list_created.add(key)
                    if line.price_list in done:
                        continue
                    existing = PriceListLine.search([
                                ('product', '=', line.product.id),
                                ('price_list', '=', line.price_list.id),
                                ('quantity', '=', line.quantity),
                            ])
                    if existing:
                        for current_line in existing:
                            to_write.extend(get_values_to_write(line,
                                    current_line))
                    else:
                        to_create.append(line._save_values)
                    done.add(line.price_list)
            else:
                for price_list in price_lists - done:
                    line.price_list = price_list
                    key = (line.product, line.price_list, line.quantity)
                    if key in price_list_created:
                        continue
                    to_create.append(line._save_values)
        if to_create:
            PriceListLine.create(to_create)
        if to_write:
            PriceListLine.write(*to_write)
        return 'result'
