from urlparse import urlparse

from django.contrib.auth import authenticate, login
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.generic.list_detail import object_list

from itkufs.accounting.models import *
from itkufs.accounting.forms import *

def group_list(request):
    """Lists the user's account groups and accounts, including admin accounts"""

    if not request.user.is_authenticated():
        user = authenticate(request=request)
        if user is not None:
            login(request, user)
        else:
            # FIXME: Redirect to login page
            return HttpResponseForbidden('Forbidden')

    # Build account struct
    accounts = []
    for account in request.user.account_set.all().order_by('name'):
        is_admin = bool(account.group.admins.filter(
            username=request.user.username).count())
        accounts.append((account, is_admin))

    # If not coming from inside and user only got one account,
    # jump directly to account summary
    request_from_inside = ('HTTP_REFERER' in request.META and
        urlparse(request.META['HTTP_REFERER'])[2].startswith(reverse('group-list')))
    if len(accounts) == 1 and not request_from_inside:
        url = reverse('account-summary',
                      kwargs={'group': accounts[0][0].group.slug,
                              'account': accounts[0][0].slug})
        return HttpResponseRedirect(url)

    return render_to_response('accounting/group_list.html',
                              {
                                  'accounts': accounts,
                              },
                              context_instance=RequestContext(request))

def group_summary(request, group):
    """Account group summary and paginated list of accounts"""

    if not request.user.is_authenticated():
        # FIXME: Redirect to login page
        return HttpResponseForbidden('Forbidden')

    # Get account group
    try:
        group = AccountGroup.objects.get(slug=group)
    except AccountGroup.DoesNotExist:
        raise Http404

    if group.admins.filter(id=request.user.id).count():
        is_admin = True
    else:
        is_admin = False

    return render_to_response('accounting/group_summary.html',
                              {
                                  'group': group,
                                  'is_admin': is_admin,
                              },
                              context_instance=RequestContext(request))

def account_summary(request, group, account, page='1'):
    """Account details and a paginated list with recent transactions involving the user"""

    if not request.user.is_authenticated():
        # FIXME: Redirect to login page
        return HttpResponseForbidden('Forbidden')

    # Get account object
    try:
        group = AccountGroup.objects.get(slug=group)
        account = group.account_set.get(slug=account)
    except (AccountGroup.DoesNotExist, Account.DoesNotExist):
        raise Http404

    # Save account in session
    # I think it's a bit of hack to switch account when the referrer is the
    # group-list view, but that view is in fact only used for selecting between
    # your own accounts.
    request_from_group_list = ('HTTP_REFERER' in request.META and
        urlparse(request.META['HTTP_REFERER'])[2] == reverse('group-list'))
    if not 'my_account' in request.session or request_from_group_list:
        request.session['my_account'] = account

    # Check that user is owner of account or admin of account group
    if group.admins.filter(id=request.user.id).count():
        is_admin = True
    elif request.user.id == account.owner.id:
        is_admin = False
    else:
        return HttpResponseForbidden('Forbidden')

    # Get related transactions
    transactions = Transaction.objects.filter(
        Q(from_account=account) | Q(to_account=account)).order_by('-registered')

    # Pass on to generic view
    return object_list(request, transactions,
                       paginate_by=20,
                       page=page,
                       allow_empty=True,
                       template_name='accounting/account_summary.html',
                       extra_context={
                            'is_admin': is_admin,
                            'account': account,
                       },
                       template_object_name='transaction')

def transfer(request, group, account, transfer_type=None):
    """Deposit, withdraw or transfer money"""

    if not request.user.is_authenticated():
        # FIXME: Redirect to login page
        return HttpResponseForbidden('Forbidden')

    # Get account object
    try:
        group = AccountGroup.objects.get(slug=group)
        account = group.account_set.get(slug=account)
    except (AccountGroup.DoesNotExist, Account.DoesNotExist):
        raise Http404

    if group.admins.filter(id=request.user.id).count():
        is_admin = True
    else:
        is_admin = False

    return render_to_response('accounting/transfer.html',
                              {
                                  'is_admin': is_admin,
                                  'account': account,
                              },
                              context_instance=RequestContext(request))

def balance(request, group):
    """FIXME"""

    if not request.user.is_authenticated():
        # FIXME: Redirect to login page
        return HttpResponseForbidden('Forbidden')

    try:
        group = AccountGroup.objects.get(slug=group)
    except AccountGroup.DoesNotExist:
        raise Http404

    if group.admins.filter(id=request.user.id).count():
        is_admin = True
    else:
        is_admin = False

    # Build balance sheet data struct
    accounts = {'As': [], 'Li': [], 'Eq': []}

    # Assets
    for account in group.account_set.filter(type='As'):
        accounts['As'].append((account.name, account.balance()))

    # Equities
    for account in group.account_set.filter(type='Eq'):
        accounts['Eq'].append((account.name, account.balance()))

    # Liabilities, with accumulated data for user accounts
    for account in group.account_set.filter(type='Li', owner__isnull=True):
        accounts['Li'].append((account.name, account.balance()))
    member_balance_sum = sum([a.balance()
        for a in group.account_set.filter(type='Li', owner__isnull=False)])
    accounts['Li'].append(('Member liabilities', member_balance_sum))

    return render_to_response('accounting/balance.html',
                              {
                                  'is_admin': is_admin,
                                  'group': group,
                                  'accounts': accounts,
                              },
                              context_instance=RequestContext(request))