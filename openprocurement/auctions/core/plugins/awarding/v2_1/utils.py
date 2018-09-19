from itertools import izip_longest
from barbecue import chef

from openprocurement.api.utils import (
    get_now,
    calculate_business_date
)

from openprocurement.auctions.core.interfaces import IAuctionManager
from openprocurement.auctions.core.plugins.awarding.base.utils import (
    make_award,
    check_lots_awarding,
    add_award_route_url,
    set_award_status_unsuccessful,
    get_bids_to_qualify
)

from openprocurement.auctions.core.plugins.awarding.base.predicates import (
    awarded_and_lots_predicate
)


def create_awards(request):
    """
        Function create NUMBER_OF_BIDS_TO_BE_QUALIFIED awards objects
        First award always in pending.verification status
        others in pending.waiting status
    """
    auction = request.validated['auction']
    auction.status = 'active.qualification'
    now = get_now()
    auction.awardPeriod = type(auction).awardPeriod({'startDate': now})
    awarding_type = request.content_configurator.awarding_type
    bids = chef(auction.bids, auction.features or [], [], True)
    # minNumberOfQualifiedBids == 1
    bids_to_qualify = get_bids_to_qualify(bids)
    for bid, status in izip_longest(bids[:bids_to_qualify], ['pending.verification'], fillvalue='pending.waiting'):
        bid = bid.serialize()
        award = make_award(request, auction, bid, status, now, parent=True)
        if bid['status'] == 'invalid':
            set_award_status_unsuccessful(award, now)
        if award.status == 'pending.verification':
            award.verificationPeriod = award.paymentPeriod = award.signingPeriod = {'startDate': now}
            add_award_route_url(request, auction, award, awarding_type)
        auction.awards.append(award)


def switch_to_next_award(request):
    auction = request.validated['auction']
    adapter = request.registry.getAdapter(auction, IAuctionManager)
    now = get_now()
    awarding_type = request.content_configurator.awarding_type
    waiting_awards = [i for i in auction.awards if i['status'] == 'pending.waiting']

    if waiting_awards:
        award = waiting_awards[0]
        award.status = 'pending.verification'
        award.verificationPeriod = award.paymentPeriod = award.signingPeriod = {'startDate': now}
        add_award_route_url(request, auction, award, awarding_type)
    elif all([award.status in ['cancelled', 'unsuccessful'] for award in auction.awards]):
        auction.awardPeriod.endDate = now
        adapter.pendify_auction_status('unsuccessful')


def next_check_awarding(auction):
    checks = []
    if awarded_and_lots_predicate(auction):
        checks = check_lots_awarding(auction)
    return min(checks) if checks else None


def calculate_enddate(auction, period, duration):
    period.endDate = calculate_business_date(period.startDate, duration, auction, True)
    round_to_18_hour_delta = period.endDate.replace(hour=18, minute=0, second=0) - period.endDate
    period.endDate = calculate_business_date(period.endDate, round_to_18_hour_delta, auction, False)
