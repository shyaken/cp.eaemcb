# Author: Zhang Huangbin <zhb@iredmail.org>

import sys
import os
import types
import datetime
from base64 import b64encode
import web
import ldap
from ldap.dn import escape_dn_chars
import settings
from libs import iredutils
from libs.ldaplib import attrs

session = web.config.get('_session')


def convert_keyword_to_dn(keyword, accountType='user'):
    '''Convert keyword and account type to DN.'''
    keyword = web.safestr(keyword).strip().replace(' ', '')
    keyword = escape_dn_chars(keyword)
    accountType == web.safestr(accountType)

    # No matter what account type is, try to get a domain name.
    domain = keyword.split('@', 1)[-1]

    # Validate account type.
    if accountType not in attrs.ACCOUNT_TYPES_ALL:
        return 'INVALID_ACCOUNT_TYPE'

    # Validate keyword.
    # Keyword is email address.
    if accountType in attrs.ACCOUNT_TYPES_EMAIL and \
       not iredutils.is_email(keyword):
        return 'INVALID_MAIL'

    # Keyword is domain name.
    if accountType in attrs.ACCOUNT_TYPES_DOMAIN and \
       not iredutils.is_domain(keyword):
        return 'INVALID_DOMAIN_NAME'

    # Convert keyword to DN.
    if accountType == 'user':
        dn = '%s=%s,%s%s=%s,%s' % (
            attrs.RDN_USER, keyword,
            attrs.DN_BETWEEN_USER_AND_DOMAIN,
            attrs.RDN_DOMAIN, domain,
            settings.ldap_basedn,
        )
    elif accountType == 'maillist':
        dn = '%s=%s,%s%s=%s,%s' % (
            attrs.RDN_MAILLIST, keyword,
            attrs.DN_BETWEEN_MAILLIST_AND_DOMAIN,
            attrs.RDN_DOMAIN, domain,
            settings.ldap_basedn,
        )
    elif accountType == 'maillistExternal':
        dn = '%s=%s,%s%s=%s,%s' % (
            attrs.RDN_MAILLIST_EXTERNAL, keyword,
            attrs.DN_BETWEEN_MAILLIST_EXTERNAL_AND_DOMAIN,
            attrs.RDN_DOMAIN, domain,
            settings.ldap_basedn,
        )
    elif accountType == 'alias':
        dn = '%s=%s,%s%s=%s,%s' % (
            attrs.RDN_ALIAS, keyword,
            attrs.DN_BETWEEN_ALIAS_AND_DOMAIN,
            attrs.RDN_DOMAIN, domain,
            settings.ldap_basedn,
        )
    elif accountType == 'admin':
        dn = '%s=%s,%s' % (
            attrs.RDN_ADMIN, keyword,
            settings.ldap_domainadmin_dn,
        )
    elif accountType == 'catchall':
        dn = '%s=@%s,%s%s=%s,%s' % (
            attrs.RDN_CATCHALL, domain,
            attrs.DN_BETWEEN_CATCHALL_AND_DOMAIN,
            attrs.RDN_DOMAIN, domain,
            settings.ldap_basedn,
        )
    elif accountType == 'domain':
        dn = '%s=%s,%s' % (
            attrs.RDN_DOMAIN, keyword,
            settings.ldap_basedn,
        )

    return dn


# Generate hashed password from plain text for LDAP value 'userPassword'.
def generate_ldap_password(password, pwscheme=settings.LDAP_DEFAULT_PASSWD_SCHEME,):
    pwscheme = pwscheme.upper()

    if pwscheme == 'SSHA512':
        pw = iredutils.generate_ssha512_password(password)
    elif pwscheme == 'SSHA':
        pw = iredutils.generate_ssha_password(password)
    elif pwscheme == 'MD5':
        pw = iredutils.generate_md5_password(password)
    else:
        pw = password

    return pw


# Check password.
def checkPassword(hashed_password, password):
    hashed_bytes = decode(hashed_password[6:])
    digest = hashed_bytes[:20]
    salt = hashed_bytes[20:]
    hr = hashlib.sha1(password)
    hr.update(salt)
    return digest == hr.digest()


def getLdifOfSingleAttr(attr, value, default='None'):
    if value is not None and value != '':
        ldif = [(attr, [value.encode('utf-8')])]
    else:
        ldif = [(attr, [default.encode('utf-8')])]

    return ldif


def getSingleModAttr(attr, value, default='None'):
    # Default value is string 'None', not None (NoneType).
    if value is not None and value != '' and value != u'':
        mod_attrs = [(ldap.MOD_REPLACE, attr, value.encode('utf-8'))]
    else:
        if default is not None and default != 'None':
            mod_attrs = [(ldap.MOD_REPLACE, attr, default.encode('utf-8'))]
        else:
            mod_attrs = [(ldap.MOD_REPLACE, attr, default)]

    return mod_attrs


def getExceptionDesc(e, key='msg'):
    if isinstance(e, types.InstanceType):
        try:
            msg = ''
            for k in ['info', 'desc', 'matched', ]:
                if k in e.args[0].keys():
                    msg += e.args[0][k] + ' '
            return msg
        except:
            return str(e)
    else:
        return str(e)


def getAccountSettingFromLdapQueryResult(queryResult, key='domainName',):
    """Get account setting from LDAP query result. Return a dictionary.

    >>> queryResult = [
    ...         ('dn', {'var': ['value', 'value',], ... })
    ...     ]

    >>> allAccountSettings = {
    ...     'key': {
    ...             'var': 'value',
    ...             'var': 'value',
    ...             ...
    ...             },
    ...     ...
    ... }
    """
    allAccountSettings = {}
    if len(queryResult) > 0:
        for d in queryResult:
            if d[1].get('accountSetting', None) is not None:
                accountSettings = {}

                for setting in d[1]['accountSetting']:
                    if len(setting.split(':', 1)) == 2:
                        k, v = setting.split(':', 1)
                        if k in ['defaultQuota', 'minPasswordLength', 'maxPasswordLength', \
                                 'numberOfUsers', 'numberOfAliases', 'numberOfLists', ]:
                            # Value of these settings must be interger or '-1'.
                            # '-1' means not allowed to add this kind of account.
                            if v.isdigit() or v == '-1':
                                accountSettings[k] = v
                        else:
                            accountSettings[k] = v

                allAccountSettings[d[1][key][0]] = accountSettings

    return allAccountSettings


def getDaysOfShadowLastChange(year=None, month=None, day=None):
    """Return number of days since 1970-01-01."""
    today = datetime.date.today()

    if year is None:
        year = today.year

    if month is None:
        month = today.month

    if day is None:
        day = today.day

    try:
        return (datetime.date(year, month, day) - datetime.date(1970, 1, 1)).days
    except:
        return 0
