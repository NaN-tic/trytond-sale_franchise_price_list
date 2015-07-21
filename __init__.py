# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .price_list import *
from .sale import *


def register():
    Pool.register(
        Franchise,
        FranchisePriceList,
        FranchisePriceListFranchise,
        PriceList,
        PriceListLine,
        UpdateFranchisePriceListStart,
        UpdateFranchisePriceListEnd,
        Sale,
        module='sale_franchise_price_list', type_='model')
    Pool.register(
        OpenFranchisePriceList,
        UpdateFranchisePriceList,
        module='sale_franchise_price_list', type_='wizard')
